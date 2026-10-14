"""Hentai library metadata.

Each AniDB / MyAnimeList entry is its own TV show. A one-episode OVA still
lives in Season 01. The movie file is renamed into that folder when organize
is on. It is never copied.
"""

import errno
import html
import http.client
import json
import logging
import os
import re
import socket
import ssl
import time
import urllib.parse
from pathlib import Path

from PIL import Image

from scraper_engine import (
    TRAILER_MAX_BYTES,
    artwork_profile,
    copy_bytes_as,
    image_dimensions,
    image_pixels,
    image_request_headers,
    prune_other_artwork,
)

VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.wmv', '.mov'}
SUBTITLE_EXTENSIONS = {'.ass', '.ssa', '.srt', '.sub', '.idx'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
# Windows copy leftovers and release notes that do not belong in a Plex show folder.
_JUNK_NAMES = {
    'thumbs.db', 'desktop.ini', 'important.txt', '重要申明.txt', '.ds_store',
}
_NUMBERED_DUP = re.compile(r'^(?P<base>.+?)\s*\((?P<num>\d+)\)(?P<ext>\.[^.]+)$', re.I)
_SHOW_CACHE = {}
_LAST_REQUEST = 0.0


def _norm(text):
    text = (text or '').casefold()
    return re.sub(r'[^0-9a-z\u3040-\u30ff\u4e00-\u9fff]+', '', text)


def safe_name(text):
    cleaned = re.sub(r'[<>:"/\\|?*]', '', text or '')
    cleaned = re.sub(r'\s+', ' ', cleaned).strip().rstrip('.')
    return cleaned[:140] or 'Unknown'


def parse_release(folder_name, filename):
    """Studio, series title, and episode numbers from a release name."""
    source = filename or folder_name or ''
    base = re.sub(r'\.[^.]+$', '', source)
    base = re.sub(r'v\d+$', '', base, flags=re.IGNORECASE).strip()
    studio = ''
    studio_match = re.search(r'\[([^\[\]]+)\]', base)
    if studio_match:
        studio = studio_match.group(1).strip()
    without_groups = re.sub(r'\[[^\[\]]*\]', ' ', base)
    without_groups = re.sub(
        r'\((?:18禁[^)]*|無修正|有修正|[^)]*(?:DVD|BD|HD|DLrip|WEB|x26[45]|AAC|AC3|Hi10P|AVC|SpursEngine|\d{3,4}x\d{3,4})[^)]*)\)',
        ' ',
        without_groups,
        flags=re.IGNORECASE,
    )
    episode_title = ''
    quoted = re.search(r'[「『]([^」』]+)[」』]', without_groups)
    if quoted:
        episode_title = quoted.group(1).strip()
        without_groups = without_groups.replace(quoted.group(0), ' ')
    episode_start, episode_end = _episode_numbers(without_groups)
    title = without_groups
    for pattern in (
        r'第\s*\d+\s*[話话夜]',
        r'(?i)vol\.?\s*\d+',
        r'(?i)menu\.?\s*\d+',
        r'#\s*\d+',
        r'全\s*\d+\s*[話话]',
        r'\d+\s*[-~～]\s*\d+(?:\.\d+)?',
    ):
        title = re.sub(pattern, ' ', title)
    title = re.sub(r'\s+', ' ', title).strip(' -_')
    # Plex-style "Show (2003)" folders — year is not part of the catalog title.
    title = re.sub(r'\s*\((?:19|20)\d{2}\)\s*$', '', title).strip(' -_')
    if not title:
        title = safe_name(folder_name)
        title = re.sub(r'\s*\((?:19|20)\d{2}\)\s*$', '', title).strip(' -_') or title
    return {
        'studio': studio,
        'title': title,
        'episode_start': episode_start,
        'episode_end': episode_end,
        'episode_title': episode_title,
    }


def _episode_numbers(text):
    pack = re.search(r'全\s*(\d+)\s*[話话]', text)
    if pack:
        count = int(pack.group(1))
        return (1, count) if count > 1 else (1, 1)
    span = re.search(r'(?<!\d)(\d{1,3})\s*[-~～]\s*(\d{1,3})(?:\.\d+)?', text)
    if span:
        start, end = int(span.group(1)), int(span.group(2))
        if 0 < start <= end <= 200:
            return start, end
    single = re.search(r'第\s*(\d+)\s*[話话夜]|vol\.?\s*(\d+)|menu\.?\s*(\d+)|#\s*(\d+)', text, re.IGNORECASE)
    if single:
        number = next(int(part) for part in single.groups() if part)
        return number, number
    return None, None


def _assign_episodes(releases):
    """Fill episode numbers for files that do not have one in the name."""
    used = {item['episode_start'] for item in releases if item['episode_start']}
    next_number = 1
    for item in releases:
        if item['episode_start']:
            continue
        while next_number in used:
            next_number += 1
        item['episode_start'] = next_number
        item['episode_end'] = next_number
        used.add(next_number)
        next_number += 1


_DOWNLOAD_SITE = re.compile(r'(?i)(?:\.com\b|www\.|by1024)')
_EXTRA_STEMS = {'特典', '設定資料', '设定资料', 'sample', 'ncop', 'nced'}


def _keep_video(path):
    """A release file, not a mirror site's duplicate or a bonus extra."""
    if _DOWNLOAD_SITE.search(path.name):
        return False
    stem = re.sub(r'\s*\(\d+\)$', '', path.stem).strip().casefold()
    return stem not in _EXTRA_STEMS


def scan_videos(folder_path):
    """Every video under a folder, skipping trailers and leftover audit copies."""
    root = Path(folder_path)
    found = []
    if not root.is_dir():
        return found
    for path in root.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        if 'Trailers' in path.parts:
            continue
        if '.audit-' in path.name or not _keep_video(path):
            continue
        found.append({
            'file_path': str(path),
            'filename': path.name,
            'folder': str(path.parent),
        })
    return found


def scan_for_ui(folder_path):
    """Rows for the file list. jav_code is the label the page already prints."""
    rows = []
    for item in scan_videos(folder_path):
        folder_name = Path(item['folder']).name
        series = parse_release(folder_name, folder_name)
        parsed = parse_release(folder_name, item['filename'])
        label = series['title'] or parsed['title']
        if parsed['episode_start']:
            label = f"{label} E{parsed['episode_start']:02d}"
        rows.append({
            'file_path': item['file_path'],
            'filename': item['filename'],
            'folder': item['folder'],
            'jav_code': label,
        })
    return rows


def _ipv4_get(url, headers, limit, timeout=20):
    """GET over IPv4. Several of these hosts do not answer on IPv6 from this network."""
    parsed = urllib.parse.urlparse(url)
    infos = socket.getaddrinfo(parsed.hostname, 443, socket.AF_INET, socket.SOCK_STREAM)
    if not infos:
        raise OSError('no IPv4 address')
    context = ssl.create_default_context()
    connection = http.client.HTTPSConnection(parsed.hostname, 443, timeout=timeout, context=context)
    connection.sock = context.wrap_socket(
        socket.create_connection(infos[0][4], timeout),
        server_hostname=parsed.hostname,
    )
    path = parsed.path + (('?' + parsed.query) if parsed.query else '')
    connection.request('GET', path, headers=headers)
    response = connection.getresponse()
    body = response.read(limit)
    status = response.status
    connection.close()
    return status, body


def _ipv4_post(url, payload):
    body = json.dumps(payload).encode('utf-8')
    headers = {
        'User-Agent': 'wooscraper',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Content-Length': str(len(body)),
    }
    parsed = urllib.parse.urlparse(url)
    infos = socket.getaddrinfo(parsed.hostname, 443, socket.AF_INET, socket.SOCK_STREAM)
    if not infos:
        raise OSError('no IPv4 address')
    context = ssl.create_default_context()
    connection = http.client.HTTPSConnection(parsed.hostname, 443, timeout=20, context=context)
    connection.sock = context.wrap_socket(
        socket.create_connection(infos[0][4], 20),
        server_hostname=parsed.hostname,
    )
    connection.request('POST', parsed.path, body=body, headers=headers)
    response = connection.getresponse()
    raw = response.read(2_000_000)
    status = response.status
    connection.close()
    return status, raw


_ANILIST_QUERY = '''
query ($search: String, $adult: Boolean) {
  Page(perPage: 8) {
    media(search: $search, type: ANIME, isAdult: $adult) {
      id
      idMal
      title { romaji english native }
      synonyms
      description(asHtml: false)
      startDate { year }
      averageScore
      coverImage { extraLarge large }
      bannerImage
      studios { nodes { name } }
      streamingEpisodes { title }
      characters(perPage: 8, sort: [ROLE, RELEVANCE]) {
        edges { role node { name { full } image { large } } }
      }
    }
  }
}
'''

# Remote artwork hosts we are allowed to download from.
_ART_HOSTS = (
    'anilist.co',
    'myanimelist.net',
    'anidb.net',
    'getchu.com',
    'duga.jp',
    'dmm.co.jp',
    'hnt.co.jp',
)

# Good enough to skip remaining remote poster sources (roughly 500x600).
_GOOD_POSTER_PIXELS = 300_000


def _anilist_search(title, adult):
    global _LAST_REQUEST
    wait = 0.7 - (time.monotonic() - _LAST_REQUEST)
    if wait > 0:
        time.sleep(wait)
    last_error = None
    for _ in range(3):
        _LAST_REQUEST = time.monotonic()
        try:
            status, raw = _ipv4_post(
                'https://graphql.anilist.co',
                {'query': _ANILIST_QUERY, 'variables': {'search': title, 'adult': adult}},
            )
            if status == 429:
                time.sleep(2)
                last_error = 'rate limited'
                continue
            if status != 200:
                raise OSError(f'HTTP {status}')
            payload = json.loads(raw.decode('utf-8', 'replace'))
            return ((payload.get('data') or {}).get('Page') or {}).get('media') or []
        except Exception as error:
            last_error = error
            time.sleep(0.5)
    logging.warning('AniList search failed for %s: %s', title, last_error)
    return []


def _score_hit(hit, title, studio):
    target = _norm(title)
    if not target:
        return 0
    names = hit.get('title') or {}
    candidates = [names.get('native'), names.get('romaji'), names.get('english')]
    candidates.extend(hit.get('synonyms') or [])
    best = 0
    for name in candidates:
        cleaned = _norm(name)
        if not cleaned:
            continue
        if cleaned == target:
            best = max(best, 100)
        elif target in cleaned or cleaned in target:
            best = max(best, 80)
    if studio:
        studio_names = [item.get('name', '') for item in ((hit.get('studios') or {}).get('nodes') or [])]
        if any(_norm(studio) and (_norm(studio) in _norm(name) or _norm(name) in _norm(studio)) for name in studio_names):
            best += 10
    return best


def _plain_plot(text):
    cleaned = html.unescape(text or '')
    cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()


def lookup_show(title, studio=''):
    """AniList record for a series title. Cached for the life of this process."""
    title = re.sub(r'\s*\((?:19|20)\d{2}\)\s*$', '', (title or '')).strip() or (title or '')
    key = _norm(title) + '|' + _norm(studio)
    if key in _SHOW_CACHE:
        return _SHOW_CACHE[key]
    show = {
        'catalog_id': None,
        'mal_id': None,
        'title': title,
        'original': title,
        'year': None,
        'plot': '',
        'score': None,
        'romaji': None,
        'studio': studio,
        'poster_url': '',
        'picture_urls': [],
        'cover_candidates': [],
        '_covers_ready': False,
        'trailer_url': '',
        'episodes': {},
        'characters': [],
        'matched': False,
    }

    hits = _anilist_search(title, True) or _anilist_search(title, False)
    ranked = sorted(hits, key=lambda hit: _score_hit(hit, title, studio), reverse=True)
    best = ranked[0] if ranked and _score_hit(ranked[0], title, studio) >= 80 else None
    if best:
        names = best.get('title') or {}
        show['matched'] = True
        show['catalog_id'] = best.get('id')
        show['mal_id'] = best.get('idMal')
        show['title'] = names.get('english') or names.get('romaji') or title
        show['romaji'] = names.get('romaji') or ''
        show['original'] = names.get('native') or title
        show['year'] = (best.get('startDate') or {}).get('year')
        show['plot'] = _plain_plot(best.get('description'))
        if best.get('averageScore'):
            show['score'] = round(best['averageScore'] / 10, 1)
        studios = (best.get('studios') or {}).get('nodes') or []
        if studios:
            show['studio'] = studios[0].get('name') or studio
        cover = best.get('coverImage') or {}
        show['poster_url'] = cover.get('extraLarge') or cover.get('large') or ''
        if best.get('bannerImage'):
            show['picture_urls'].append(best['bannerImage'])
        if show['poster_url']:
            show['picture_urls'].append(show['poster_url'])
        for index, episode in enumerate(best.get('streamingEpisodes') or [], start=1):
            episode_title = episode.get('title') or ''
            if episode_title:
                show['episodes'][index] = {'title': episode_title, 'original': ''}
        for edge in ((best.get('characters') or {}).get('edges') or []):
            node = edge.get('node') or {}
            name = ((node.get('name') or {}).get('full') or '').strip()
            image = ((node.get('image') or {}).get('large') or '')
            if name:
                show['characters'].append({'name': name, 'url': image, 'role': edge.get('role') or 'Character'})
            if len(show['characters']) >= 8:
                break
    _SHOW_CACHE[key] = show
    return show


def show_folder_name(show):
    title = safe_name(show.get('title') or 'Unknown')
    year = show.get('year')
    if year:
        return f'{title} ({year})'
    return title


def episode_filename(show_folder, episode_start, episode_end, suffix):
    start = int(episode_start or 1)
    end = int(episode_end or start)
    if end > start:
        marker = f's01e{start:02d}-e{end:02d}'
    else:
        marker = f's01e{start:02d}'
    return f'{show_folder} - {marker}{suffix}'


def _xml(text):
    return (str(text or '')
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


def tvshow_nfo(show):
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<tvshow>',
        f"    <title>{_xml(show.get('title'))}</title>",
        f"    <originaltitle>{_xml(show.get('original'))}</originaltitle>",
    ]
    if show.get('year'):
        lines.append(f"    <year>{int(show['year'])}</year>")
    if show.get('plot'):
        lines.append(f"    <plot>{_xml(show['plot'])}</plot>")
    if show.get('studio'):
        lines.append(f"    <studio>{_xml(show['studio'])}</studio>")
    if show.get('catalog_id'):
        lines.append(f'    <uniqueid type="anilist" default="true">{int(show["catalog_id"])}</uniqueid>')
    if show.get('score'):
        score = show['score']
        lines.append(f'    <rating>{score}</rating>')
        lines.append('    <ratings>')
        lines.append('        <rating name="imdb" max="10" default="true">')
        lines.append(f'            <value>{score}</value>')
        lines.append('        </rating>')
        lines.append('    </ratings>')
    lines.append('    <genre>Hentai</genre>')
    trailer = show.get('trailer_file') or show.get('trailer_url')
    if trailer:
        lines.append(f"    <trailer>{_xml(trailer)}</trailer>")
    for index, person in enumerate(show.get('characters') or []):
        lines.append('    <actor>')
        lines.append(f"        <name>{_xml(person.get('name'))}</name>")
        lines.append(f"        <role>{_xml(person.get('role') or 'Character')}</role>")
        lines.append(f'        <order>{index}</order>')
        if person.get('url'):
            lines.append(f"        <thumb>{_xml(person['url'])}</thumb>")
        lines.append('    </actor>')
    lines.append('</tvshow>')
    return '\n'.join(lines) + '\n'


def episode_nfo(show, release):
    number = int(release.get('episode_start') or 1)
    end = int(release.get('episode_end') or number)
    catalog = (show.get('episodes') or {}).get(number) or {}
    title = release.get('episode_title') or catalog.get('title') or f'Episode {number}'
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<episodedetails>',
        f"    <title>{_xml(title)}</title>",
        f"    <showtitle>{_xml(show.get('title'))}</showtitle>",
        '    <season>1</season>',
        f'    <episode>{number}</episode>',
    ]
    if end > number:
        lines.append(f'    <episodeend>{end}</episodeend>')
    if catalog.get('original'):
        lines.append(f"    <originaltitle>{_xml(catalog['original'])}</originaltitle>")
    if show.get('plot'):
        lines.append(f"    <plot>{_xml(show['plot'])}</plot>")
    if show.get('catalog_id'):
        lines.append(f'    <uniqueid type="anilist">{int(show["catalog_id"])}</uniqueid>')
    lines.append('</episodedetails>')
    return '\n'.join(lines) + '\n'


def present_lookup(folder_name, filename, media_server='plex'):
    """One file, for the page that saves into a folder the server cannot see."""
    label = folder_name
    if re.fullmatch(r'Season \d+', folder_name or '', flags=re.I):
        label = folder_name
    series = parse_release(label, label)
    parsed = parse_release(label, filename)
    parsed['title'] = series['title'] or parsed['title']
    parsed['studio'] = series['studio'] or parsed['studio']
    if not parsed['episode_start']:
        parsed['episode_start'] = 1
        parsed['episode_end'] = 1
    show = lookup_show(parsed['title'], parsed['studio'])
    folder = show_folder_name(show)
    suffix = Path(filename).suffix or '.mkv'
    profile = artwork_profile(media_server)
    # Keep present_lookup fast: AniList URLs only. Catalog covers run on server process/audit.
    cover = show.get('poster_url') or ''
    fanart = (show['picture_urls'][0] if show.get('picture_urls') else '') or cover
    return {
        'found': True,
        'library': 'hentai',
        'matched': show['matched'],
        'title': show['title'],
        'year': show['year'],
        'studio': show['studio'],
        'plot': (show['plot'] or '')[:1200],
        'show_folder': folder,
        'episode_file': episode_filename(folder, parsed['episode_start'], parsed['episode_end'], suffix),
        'show_nfo': tvshow_nfo(show),
        'episode_nfo': episode_nfo(show, parsed),
        'cover_url': cover,
        'fanart_url': fanart,
        'trailer_url': show['trailer_url'],
        'jav_code': folder,
        'artwork': {
            'posters': list(profile['posters']),
            'backgrounds': list(profile['backgrounds']),
            'actor_local': False,
            'remove': _artwork_remove_names(media_server),
            'remove_actors': False,
        },
    }


_COOKIES = {}
_SAMPLE_SUFFIXES = ('.duga.jp', '.dmm.co.jp', '.getchu.com', '.chobit.cc')


def _cookie_site(hostname):
    host = (hostname or '').lower()
    for site in ('chobit.cc', 'duga.jp', 'dmm.co.jp', 'getchu.com', 'hnt.co.jp'):
        if host.endswith(site):
            return site
    return host


def _remember_cookies(hostname, response):
    jar = _COOKIES.setdefault(_cookie_site(hostname), {})
    for key, value in response.getheaders():
        if key.lower() != 'set-cookie' or '=' not in value:
            continue
        pair = value.split(';', 1)[0]
        name, cookie = pair.split('=', 1)
        jar[name.strip()] = cookie.strip()


def _exchange(method, url, body=None, headers=None, limit=2_000_000):
    """HTTPS over IPv4. These catalogs often do not answer on IPv6."""
    parsed = urllib.parse.urlparse(url)
    infos = socket.getaddrinfo(parsed.hostname, 443, socket.AF_INET, socket.SOCK_STREAM)
    if not infos:
        raise OSError('no IPv4 address')
    context = ssl.create_default_context()
    connection = http.client.HTTPSConnection(parsed.hostname, 443, timeout=25, context=context)
    connection.sock = context.wrap_socket(
        socket.create_connection(infos[0][4], 20),
        server_hostname=parsed.hostname,
    )
    path = parsed.path or '/'
    if parsed.query:
        path += '?' + parsed.query
    request_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': '*/*',
    }
    jar = _COOKIES.get(_cookie_site(parsed.hostname), {})
    if jar:
        request_headers['Cookie'] = '; '.join(f'{name}={value}' for name, value in jar.items())
    if headers:
        request_headers.update(headers)
    connection.request(method, path, body=body, headers=request_headers)
    response = connection.getresponse()
    _remember_cookies(parsed.hostname, response)
    payload = response.read(limit)
    status = response.status
    connection.close()
    return status, payload


def _catalog_text(url):
    status, payload = _exchange('GET', url, headers={'Accept': 'text/html'})
    if b'loading page' in payload:
        match = re.search(br'ajax\.get\("([^"]+)"', payload)
        if match:
            check = urllib.parse.urljoin(url, match.group(1).decode('ascii', 'replace'))
            _exchange('GET', check, headers={'X-Requested-With': 'XMLHttpRequest', 'Referer': url})
            status, payload = _exchange('GET', url, headers={'Accept': 'text/html', 'Referer': url})
    if status != 200:
        return ''
    return payload.decode('utf-8', 'replace')


def _sample_host_ok(url):
    host = (urllib.parse.urlparse(url).hostname or '').lower()
    return any(host.endswith(suffix) for suffix in _SAMPLE_SUFFIXES)


def _title_hit(wanted, found):
    left, right = _norm(wanted), _norm(found)
    if len(left) < 4 or len(right) < 4:
        return False
    return left in right or right in left


def _show_names(show):
    names = []
    for text in (show.get('original'), show.get('romaji'), show.get('title')):
        text = (text or '').strip()
        if text and text not in names:
            names.append(text)
    return names


def _chobit_samples(title):
    """Demo movie from chobit, the DLsite sample site. The file host answers from here."""
    _COOKIES.setdefault('chobit.cc', {})['showr18'] = '1'
    page = _catalog_text('https://chobit.cc/s?' + urllib.parse.urlencode({'q_keyword': title}))
    urls = []
    for path, name in re.findall(r'class="work-work-name"><a href="(/[0-9a-z]+)">(.*?)</a>', page):
        if not _title_hit(title, html.unescape(name)):
            continue
        item = _catalog_text('https://chobit.cc' + path)
        chosen = re.search(r'content="(https://file\.chobit\.cc/[^"]+\.mp4)"', item)
        if chosen:
            urls.append(chosen.group(1))
            break
    return urls


def _duga_samples(title):
    """Free sample MP4 from DUGA when the product title is this show."""
    try:
        query = urllib.parse.quote(title.encode('cp932'))
    except UnicodeEncodeError:
        return []
    page = _catalog_text('https://duga.jp/search/=/q=' + query + '/')
    urls = []
    for href, alt in re.findall(r'href="(/ppv/[^"]+/)"[\s\S]{0,700}?alt="([^"]+)"', page):
        if not _title_hit(title, alt):
            continue
        product = _catalog_text('https://duga.jp' + href)
        media = [item for item in re.findall(r'https://[^"\']+\.mp4', product) if _sample_host_ok(item)]
        media.sort(key=lambda item: (0 if item.endswith('movie.mp4') else 1))
        urls.extend(media[:1])
        break
    return urls


def _fanza_sample(content_id):
    """Official FANZA sample address. The file itself is often region-locked."""
    body = json.dumps({
        'query': 'query ($id: ID!) { ppvContent(id: $id) { sample2DMovie { highestMovieUrl } } }',
        'variables': {'id': content_id},
    }).encode('utf-8')
    status, payload = _exchange(
        'POST',
        'https://api.video.dmm.co.jp/graphql',
        body,
        {'Content-Type': 'application/json', 'Origin': 'https://video.dmm.co.jp', 'Referer': 'https://video.dmm.co.jp/'},
    )
    if status != 200:
        return ''
    data = json.loads(payload.decode('utf-8', 'replace'))
    movie = ((data.get('data') or {}).get('ppvContent') or {}).get('sample2DMovie') or {}
    return movie.get('highestMovieUrl') or ''


def _hnt_samples(title):
    """HNT indexes the FANZA sample for a show. DuckDuckGo lists it as a sample catalog."""
    page = _catalog_text('https://anime.hnt.co.jp/?' + urllib.parse.urlencode({'s': title}))
    articles = []
    for href, label in re.findall(r'href="(https://anime\.hnt\.co\.jp/\d+/)"[^>]*>(.*?)</a>', page, re.S):
        label = html.unescape(re.sub(r'<[^>]+>|\s+', ' ', label)).strip()
        if href not in articles and _title_hit(title, label):
            articles.append(href)
        if len(articles) >= 2:
            break
    urls = []
    for href in articles:
        article = _catalog_text(href)
        for media in re.findall(r'https://[^"\']+\.mp4', article):
            if _sample_host_ok(media) and media not in urls:
                urls.append(media)
        if urls:
            continue
        for content_id in re.findall(r'(?:cid|id)(?:%3D|=)([0-9a-z]{6,})', article, re.I):
            sample = _fanza_sample(content_id)
            if sample and sample not in urls:
                urls.append(sample)
            break
    return urls


def _getchu_samples(title):
    """Demo file on Getchu when the adult-anime search title matches."""
    try:
        query = urllib.parse.quote(title.encode('euc-jp'))
    except UnicodeEncodeError:
        return []
    _COOKIES.setdefault('getchu.com', {})['getchu_adalt_flag'] = 'getchu.com'
    status, payload = _exchange(
        'GET',
        f'https://www.getchu.com/php/search.phtml?genre=anime_dvd&search_keyword={query}&gc=gc',
    )
    if status != 200:
        return []
    page = payload.decode('euc-jp', 'replace')
    ids = []
    for product_id, name in re.findall(r'soft\.phtml\?id=(\d+)" class="blueb">([^<]+)', page):
        if product_id not in ids and _title_hit(title, name):
            ids.append(product_id)
    urls = []
    for product_id in ids[:2]:
        status, payload = _exchange('GET', f'https://www.getchu.com/soft.phtml?id={product_id}')
        product = payload.decode('euc-jp', 'replace')
        for media in re.findall(r'https://[^"\']+\.mp4', product, re.I):
            if _sample_host_ok(media) and media not in urls:
                urls.append(media)
        if urls:
            break
    return urls


def _save_sample(url, dest):
    """Stream a catalog sample to disk. Refuse anything that is not a real MP4."""
    if not _sample_host_ok(url):
        return False
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ''
    if 'duga.jp' in host:
        referer = 'https://duga.jp/'
    elif host.endswith('chobit.cc'):
        referer = 'https://chobit.cc/'
    else:
        referer = 'https://video.dmm.co.jp/'
    infos = socket.getaddrinfo(parsed.hostname, 443, socket.AF_INET, socket.SOCK_STREAM)
    if not infos:
        return False
    context = ssl.create_default_context()
    connection = http.client.HTTPSConnection(parsed.hostname, 443, timeout=30, context=context)
    connection.sock = context.wrap_socket(
        socket.create_connection(infos[0][4], 20),
        server_hostname=parsed.hostname,
    )
    path = parsed.path + (('?' + parsed.query) if parsed.query else '')
    connection.request('GET', path, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Referer': referer,
        'Accept': 'video/mp4,*/*',
    })
    response = connection.getresponse()
    if response.status not in (200, 206):
        logging.warning('Sample download HTTP %s for %s', response.status, url)
        connection.close()
        return False
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    header = b''
    try:
        with dest.open('wb') as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                if len(header) < 12:
                    header += chunk
                written += len(chunk)
                if written > TRAILER_MAX_BYTES:
                    break
                handle.write(chunk)
    finally:
        connection.close()
    if written > TRAILER_MAX_BYTES or written < 100_000 or header[4:8] != b'ftyp':
        dest.unlink(missing_ok=True)
        return False
    return True


def _download_show_trailer(show_dir, show):
    """Save Trailers/Preview.mp4 from a store sample, never from YouTube."""
    dest = Path(show_dir) / 'Trailers' / 'Preview.mp4'
    if dest.is_file() and dest.stat().st_size > 100_000:
        show['trailer_file'] = 'Trailers/Preview.mp4'
        return 'trailer already saved'
    saw_sample = False
    tried = set()
    # Try every catalog name (Japanese / romaji / English). Skipping names
    # was leaving trailers undownloaded even when Download trailer was on.
    for finder in (_chobit_samples, _duga_samples, _hnt_samples, _getchu_samples):
        for title in _show_names(show):
            key = (finder.__name__, _norm(title))
            if not title or key in tried:
                continue
            tried.add(key)
            try:
                urls = finder(title)
            except Exception as error:
                logging.warning('Sample search failed for %s: %s', title, error)
                continue
            if not urls:
                continue
            saw_sample = True
            for url in urls[:2]:
                if _save_sample(url, dest):
                    show['trailer_url'] = url
                    show['trailer_file'] = 'Trailers/Preview.mp4'
                    host = urllib.parse.urlparse(url).hostname or 'catalog'
                    return f'trailer saved from {host}'
                dest.unlink(missing_ok=True)
    if saw_sample:
        return 'trailer could not be downloaded'
    return 'no trailer published'



def _art_host_ok(url):
    host = (urllib.parse.urlparse(url).hostname or '').lower()
    return any(host.endswith(suffix) for suffix in _ART_HOSTS)


def _abs_url(base, url):
    if not url:
        return ''
    url = html.unescape(url).strip()
    if url.startswith('//'):
        url = 'https:' + url
    elif url.startswith('/'):
        url = urllib.parse.urljoin(base, url)
    if url.startswith('http://'):
        url = 'https://' + url[7:]
    return url if url.startswith('https://') else ''


def _unique_urls(urls):
    seen = set()
    out = []
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def _getchu_covers(title):
    """Package images from Getchu adult-anime search."""
    try:
        query = urllib.parse.quote(title.encode('euc-jp'))
    except UnicodeEncodeError:
        return []
    _COOKIES.setdefault('getchu.com', {})['getchu_adalt_flag'] = 'getchu.com'
    status, payload = _exchange(
        'GET',
        f'https://www.getchu.com/php/search.phtml?genre=anime_dvd&search_keyword={query}&gc=gc',
    )
    if status != 200:
        return []
    page = payload.decode('euc-jp', 'replace')
    ids = []
    for product_id, name in re.findall(r'soft\.phtml\?id=(\d+)" class="blueb">([^<]+)', page):
        if product_id not in ids and _title_hit(title, name):
            ids.append(product_id)
    urls = []
    for product_id in ids[:2]:
        status, payload = _exchange('GET', f'https://www.getchu.com/soft.phtml?id={product_id}')
        if status != 200:
            continue
        product = payload.decode('euc-jp', 'replace')
        candidates = re.findall(
            r'(?:src|href)="([^"]*(?:image\.getchu\.com|getchu\.com/[^"]+)[^"]*\.(?:jpe?g|png|webp)[^"]*)"',
            product,
            re.I,
        )
        if not candidates:
            candidates = re.findall(
                r'(?:src|href)="([^"]+\.(?:jpe?g|png|webp)[^"]*)"',
                product,
                re.I,
            )
        for raw in candidates:
            url = _abs_url(f'https://www.getchu.com/soft.phtml?id={product_id}', raw)
            low = url.lower()
            if not url or 'banner' in low or 'logo' in low or 'button' in low:
                continue
            if 'package' in low or 'jacket' in low or 'image.getchu.com' in low or 'cover' in low:
                urls.append(url)
            elif url not in urls and len(urls) < 2:
                urls.append(url)
        if urls:
            break
    return _unique_urls(urls)


def _duga_covers(title):
    """Product package image from DUGA."""
    try:
        query = urllib.parse.quote(title.encode('cp932'))
    except UnicodeEncodeError:
        return []
    page = _catalog_text('https://duga.jp/search/=/q=' + query + '/')
    urls = []
    for href, alt in re.findall(r'href="(/ppv/[^"]+/)"[\s\S]{0,700}?alt="([^"]+)"', page):
        if not _title_hit(title, alt):
            continue
        product = _catalog_text('https://duga.jp' + href)
        og = re.search(r'property="og:image"\s+content="([^"]+)"', product)
        if not og:
            og = re.search(r'content="([^"]+)"\s+property="og:image"', product)
        if og:
            urls.append(_abs_url('https://duga.jp/', og.group(1)))
        for raw in re.findall(r'(?:src|href)="(https?://[^"]+\.(?:jpe?g|png)[^"]*)"', product, re.I):
            low = raw.lower()
            if 'thumb' in low or 'icon' in low or 'logo' in low:
                continue
            if 'jacket' in low or 'package' in low or 'll.jpg' in low or 'l.jpg' in low:
                urls.append(raw)
        break
    return _unique_urls(urls)


def _fanza_package_urls(content_id):
    content_id = (content_id or '').strip().lower()
    if not content_id or len(content_id) < 5:
        return []
    return [
        f'https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/{content_id}/{content_id}pl.jpg',
        f'https://pics.dmm.co.jp/digital/video/{content_id}/{content_id}pl.jpg',
        f'https://pics.dmm.co.jp/digital/video/{content_id}/{content_id}ps.jpg',
    ]


def _hnt_covers(title):
    """HNT article art plus FANZA package URLs when a content id is present."""
    page = _catalog_text('https://anime.hnt.co.jp/?' + urllib.parse.urlencode({'s': title}))
    articles = []
    for href, label in re.findall(r'href="(https://anime\.hnt\.co\.jp/\d+/)"[^>]*>(.*?)</a>', page, re.S):
        label = html.unescape(re.sub(r'<[^>]+>|\s+', ' ', label)).strip()
        if href not in articles and _title_hit(title, label):
            articles.append(href)
        if len(articles) >= 2:
            break
    urls = []
    for href in articles:
        article = _catalog_text(href)
        article_id = re.search(r'hnt\.co\.jp/(\d+)/', href)
        aid = article_id.group(1) if article_id else ''
        # Prefer FANZA package art linked from the article; skip tiny site banners.
        for content_id in re.findall(r'cid%3D([0-9a-z]{5,})|cid=([0-9a-z]{5,})', article, re.I):
            cid = content_id[0] or content_id[1]
            urls.extend(_fanza_package_urls(cid))
            break
        for raw in re.findall(r'(?:src|href|content)="(https?://[^"]+\.(?:jpe?g|png|webp)[^"]*)"', article, re.I):
            low = raw.lower()
            if 'cropped' in low or 'logo' in low or 'ranking' in low:
                continue
            if 'pics.dmm.co.jp' in low or 'awsimgsrc.dmm' in low:
                urls.append(raw.split('.webp')[0] if raw.endswith('.webp') else raw)
        if urls:
            break
    return _unique_urls(urls)


def _mal_covers(show):
    """MyAnimeList cover via Jikan when reachable; soft-fail on timeout."""
    mal_id = show.get('mal_id')
    endpoints = []
    if mal_id:
        endpoints.append(f'https://api.jikan.moe/v4/anime/{int(mal_id)}')
    else:
        for title in _show_names(show)[:2]:
            endpoints.append(
                'https://api.jikan.moe/v4/anime?'
                + urllib.parse.urlencode({'q': title, 'limit': '5', 'sfw': 'false'})
            )
    wanted = _norm(show.get('original') or show.get('romaji') or show.get('title') or '')
    for endpoint in endpoints:
        try:
            status, payload = _ipv4_get(
                endpoint,
                {'User-Agent': 'wooscraper', 'Accept': 'application/json'},
                500_000,
                timeout=6,
            )
        except Exception as error:
            logging.warning('MAL cover lookup failed: %s', error)
            return []
        if status != 200:
            continue
        try:
            data = json.loads(payload.decode('utf-8', 'replace'))
        except Exception:
            continue
        if isinstance(data.get('data'), list):
            rows = data['data']
        elif isinstance(data.get('data'), dict):
            rows = [data['data']]
        else:
            rows = []
        for row in rows:
            row_id = int(row.get('mal_id') or 0)
            if mal_id and row_id and row_id != int(mal_id):
                continue
            if not mal_id and wanted:
                titles = [row.get('title'), row.get('title_english'), row.get('title_japanese')]
                for entry in row.get('titles') or []:
                    titles.append(entry.get('title'))
                if not any(_norm(name or '') == wanted or _title_hit(wanted, name or '') for name in titles if name):
                    continue
            images = ((row.get('images') or {}).get('jpg') or {})
            urls = [images[key] for key in ('large_image_url', 'image_url') if images.get(key)]
            if urls:
                return _unique_urls(urls)
    return []


def _anidb_covers(title):
    """AniDB main image when the HTML search is not behind a challenge page."""
    page = _catalog_text(
        'https://anidb.net/search/anime/?' + urllib.parse.urlencode({'adb.search': title, 'do.search': '1'})
    )
    if not page or 'Just a moment' in page or 'cf-browser-verification' in page:
        return []
    urls = []
    for href, name in re.findall(r'href="(/anime/\d+)[^"]*"[^>]*>([^<]+)<', page):
        if not _title_hit(title, html.unescape(name)):
            continue
        item = _catalog_text('https://anidb.net' + href)
        if not item or 'Just a moment' in item:
            continue
        for raw in re.findall(r'(?:src|href)="(https?://cdn\.anidb\.net/images/main/[^"]+)"', item):
            urls.append(raw)
        if urls:
            break
    return _unique_urls(urls)


def _cover_candidate_urls(show):
    """Ranked remote poster URLs: Getchu, DUGA, HNT/FANZA, MAL, AniDB, then AniList."""
    urls = []
    for finder in (_getchu_covers, _duga_covers, _hnt_covers):
        for title in _show_names(show)[:2]:
            try:
                found = finder(title)
            except Exception as error:
                logging.warning('Cover search failed for %s: %s', title, error)
                found = []
            for url in found:
                if url not in urls:
                    urls.append(url)
            if found:
                break
    try:
        for url in _mal_covers(show):
            if url not in urls:
                urls.append(url)
    except Exception as error:
        logging.warning('MAL cover search failed: %s', error)
    try:
        for title in _show_names(show)[:2]:
            found = _anidb_covers(title)
            for url in found:
                if url not in urls:
                    urls.append(url)
            if found:
                break
    except Exception as error:
        logging.warning('AniDB cover search failed: %s', error)
    for url in show.get('picture_urls') or []:
        if url and url not in urls:
            urls.append(url)
    if show.get('poster_url') and show['poster_url'] not in urls:
        urls.append(show['poster_url'])
    return urls


def _ensure_cover_candidates(show):
    if show.get('_covers_ready'):
        return list(show.get('cover_candidates') or [])
    show['cover_candidates'] = _cover_candidate_urls(show)
    show['_covers_ready'] = True
    return list(show['cover_candidates'])


def _artwork_remove_names(media_server):
    name = (media_server or 'plex').strip().lower()
    if name == 'all':
        return []
    profile = artwork_profile(name)
    keep = set(profile['posters']) | set(profile['backgrounds'])
    return [
        item for item in (
            'poster.jpg', 'folder.jpg', 'cover.jpg',
            'fanart.jpg', 'background.jpg', 'backdrop.jpg', 'art.jpg',
        )
        if item not in keep
    ]


def _local_images(*folders):
    """Non-standard JPGs already on disk (release covers, not poster/background names)."""
    reserved = {
        'poster.jpg', 'folder.jpg', 'cover.jpg', 'fanart.jpg',
        'background.jpg', 'backdrop.jpg', 'art.jpg',
    }
    found = []
    seen = set()
    for folder in folders:
        if not folder:
            continue
        root = Path(folder)
        if not root.is_dir():
            continue
        for path in root.iterdir():
            if not path.is_file():
                continue
            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            if path.name.startswith('.'):
                continue
            if path.name.lower() in reserved:
                continue
            if path.name.endswith('-thumb' + path.suffix):
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            found.append(path)
        season = root / 'Season 01'
        if season.is_dir() and season.resolve() != root.resolve():
            for path in season.iterdir():
                if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                if path.name.startswith('.') or '-thumb' in path.stem:
                    continue
                key = str(path.resolve())
                if key in seen:
                    continue
                seen.add(key)
                found.append(path)
    return found


def _pick_best_image(paths, prefer='portrait'):
    """Return the best path by pixel count. prefer: portrait, landscape, or any.

    portrait/landscape return (None, -1) when nothing matches that shape so callers
    can fall back to a larger overall image instead of a tiny AniList portrait.
    """
    best = None
    best_pixels = -1
    for path in paths:
        width, height = image_dimensions(path)
        pixels = width * height
        if pixels <= 0:
            continue
        if prefer == 'portrait' and height < width:
            continue
        if prefer == 'landscape' and width <= height:
            continue
        if pixels > best_pixels:
            best = path
            best_pixels = pixels
    return best, best_pixels


def _replace_if_larger_file(source, dest):
    """Copy source over dest when dest is missing or source has more pixels."""
    source = Path(source)
    dest = Path(dest)
    if not source.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or image_pixels(source) > image_pixels(dest):
        if source.resolve() != dest.resolve():
            dest.write_bytes(source.read_bytes())
        return True
    return False


def _poster_from_cover(cover_path, poster_path):
    """Crop the right ~47% of a landscape cover into a portrait poster (same as JAV)."""
    from PIL import ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    cover_path = Path(cover_path)
    poster_path = Path(poster_path)
    if not cover_path.is_file():
        return False
    try:
        with Image.open(cover_path) as img:
            img = img.convert('RGB')
            width, height = img.size
            if width <= 0 or height <= 0:
                return False
            if height >= width:
                # Already a portrait — cannot invent a landscape crop.
                return False
            crop_width = max(1, int(width * 0.47125))
            left = width - crop_width
            cropped = img.crop((left, 0, width, height))
            poster_path.parent.mkdir(parents=True, exist_ok=True)
            cropped.save(poster_path, 'JPEG', quality=95)
        return poster_path.is_file() and image_pixels(poster_path) > 0
    except Exception as error:
        logging.warning('Poster crop failed for %s: %s', cover_path, error)
        return False


def _images_same(left, right):
    left, right = Path(left), Path(right)
    if not left.is_file() or not right.is_file():
        return False
    if left.resolve() == right.resolve():
        return True
    try:
        if left.stat().st_size != right.stat().st_size:
            return False
        return left.read_bytes() == right.read_bytes()
    except OSError:
        return False


def _download(url, dest):
    if not url or not url.startswith('https://'):
        return False
    if not _art_host_ok(url):
        return False
    try:
        status, payload = _ipv4_get(url, image_request_headers(url), 8_000_000)
        if status not in (200, 206):
            # Some CDNs return a tiny JPEG with a surprising status; reject tiny bodies.
            if len(payload) < 5000 or payload[:2] != b'\xff\xd8':
                return False
        if len(payload) < 1000:
            return False
        if payload[:2] not in (b'\xff\xd8', b'\x89P') and payload[:4] != b'RIFF':
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
        return True
    except Exception as error:
        logging.warning('Image download failed for %s: %s', url, error)
        return False


def _save_artwork(show_dir, show, media_server, source_dirs=None):
    """Write poster/background using remote catalogs, local release art, then AniList.

    Poster must be a real portrait cover. Landscape screenshots / full covers are
    never used as poster as-is — if we only have a cover/background, crop the
    right side into a poster (same rule as JAV).
    """
    profile = artwork_profile(media_server)
    show_dir = Path(show_dir)
    poster_path = show_dir / profile['posters'][0]
    background_path = show_dir / profile['backgrounds'][0]
    show_dir.mkdir(parents=True, exist_ok=True)
    temps = []
    remote_paths = []
    candidates = _ensure_cover_candidates(show)
    for index, url in enumerate(candidates):
        target = show_dir / f'.picture-{index}.jpg'
        if _download(url, target):
            temps.append(target)
            width, height = image_dimensions(target)
            pixels = width * height
            if pixels < 40_000:
                continue
            remote_paths.append(target)
            if height >= width and pixels >= _GOOD_POSTER_PIXELS:
                break
    local_paths = _local_images(show_dir, *(source_dirs or []))
    # Background: prefer a real landscape cover (not a tiny banner).
    background_pool = list(local_paths) + list(remote_paths)
    if background_path.is_file():
        background_pool.append(background_path)
    background, background_pixels = _pick_best_image(background_pool, prefer='landscape')
    if background is None:
        background, background_pixels = _pick_best_image(background_pool, prefer='any')

    # Poster: portrait catalog art only. Never use a landscape image unchanged.
    poster_pool = list(remote_paths) + list(local_paths)
    if poster_path.is_file():
        width, height = image_dimensions(poster_path)
        if height > width:
            poster_pool.append(poster_path)
    portrait, portrait_pixels = _pick_best_image(poster_pool, prefer='portrait')

    notes = []
    if background is not None and _replace_if_larger_file(background, background_path):
        notes.append(f'background {background_pixels}px')
    elif background_path.is_file():
        notes.append('background kept')
    else:
        notes.append('no background')

    used_crop = False
    if portrait is not None and portrait_pixels >= 80_000:
        if _replace_if_larger_file(portrait, poster_path):
            notes.append(f'poster {portrait_pixels}px')
        elif poster_path.is_file():
            notes.append('poster kept')
    elif background_path.is_file() and _poster_from_cover(background_path, poster_path):
        used_crop = True
        notes.append('poster cropped from cover')
    else:
        cover, _ = _pick_best_image(list(remote_paths) + list(local_paths), prefer='landscape')
        if cover is None:
            cover, _ = _pick_best_image(list(remote_paths) + list(local_paths), prefer='any')
        if cover is not None and _poster_from_cover(cover, poster_path):
            used_crop = True
            notes.append('poster cropped from cover')
        elif poster_path.is_file():
            notes.append('poster kept')
        else:
            notes.append('no poster')

    # Landscape poster or poster identical to background → force crop / untangle.
    if poster_path.is_file() and background_path.is_file():
        pw, ph = image_dimensions(poster_path)
        bw, bh = image_dimensions(background_path)
        if pw >= ph or _images_same(poster_path, background_path):
            if bw > bh and _poster_from_cover(background_path, poster_path):
                used_crop = True
                notes = [item for item in notes if not item.startswith('poster ')]
                notes.append('poster cropped from cover')
            elif _images_same(poster_path, background_path):
                # Only one portrait image exists — keep it as poster, not as both.
                other_land, _ = _pick_best_image(
                    [path for path in (list(remote_paths) + list(local_paths))
                     if Path(path).resolve() != poster_path.resolve()],
                    prefer='landscape',
                )
                if other_land is not None and _replace_if_larger_file(other_land, background_path):
                    notes = [item for item in notes if not item.startswith('background ')]
                    notes.append('background replaced')
                    if _poster_from_cover(background_path, poster_path):
                        used_crop = True
                        notes = [item for item in notes if not item.startswith('poster ')]
                        notes.append('poster cropped from cover')
                else:
                    background_path.unlink(missing_ok=True)
                    notes = [item for item in notes if not item.startswith('background ')]
                    notes.append('background cleared (was duplicate poster)')

    if poster_path.is_file():
        copy_bytes_as(poster_path, profile['posters'])
    if background_path.is_file():
        copy_bytes_as(background_path, profile['backgrounds'])
    prune_other_artwork(show_dir, media_server)
    for path in temps:
        path.unlink(missing_ok=True)
    if used_crop and 'poster cropped from cover' not in notes:
        notes.append('poster cropped from cover')
    return ', '.join(notes)


def _stem_variants(stem):
    """Release stems with and without trailing (1) duplicate markers."""
    variants = [stem]
    stripped = re.sub(r'\s*\(\d+\)$', '', stem).strip()
    if stripped and stripped not in variants:
        variants.append(stripped)
    return variants


def _promote_episode_thumbs(video_path, search_dirs):
    """Move the best matching release JPG next to the episode as -thumb.jpg."""
    video_path = Path(video_path)
    if not video_path.is_file():
        return []
    thumb = video_path.with_name(video_path.stem + '-thumb.jpg')
    candidates = []
    stems = _stem_variants(video_path.stem)
    # Also match original release stems that may still be in search_dirs.
    for folder in search_dirs:
        root = Path(folder)
        if not root.is_dir():
            continue
        for path in root.iterdir():
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            if path.name.startswith('.') or path.name.lower() in {
                'poster.jpg', 'folder.jpg', 'cover.jpg', 'fanart.jpg',
                'background.jpg', 'backdrop.jpg', 'art.jpg',
            }:
                continue
            if path.name.endswith('-thumb' + path.suffix):
                continue
            image_stem = path.stem
            base = re.sub(r'\s*\(\d+\)$', '', image_stem).strip()
            if any(image_stem == stem or base == stem or image_stem.startswith(stem) for stem in stems):
                candidates.append(path)
            # When video was already renamed, match by original sibling naming is harder;
            # accept any leftover non-reserved JPG only when this video's folder has exactly one.
    if not candidates:
        return []
    best, _ = _pick_best_image(candidates, prefer='any')
    if best is None:
        return []
    removed = []
    _replace_if_larger_file(best, thumb)
    for path in candidates:
        if path.resolve() == thumb.resolve():
            continue
        if path.resolve() == best.resolve() or image_pixels(path) <= image_pixels(best):
            # Drop duplicates and the source once promoted (unless it is already the thumb).
            if path.resolve() != thumb.resolve():
                path.unlink(missing_ok=True)
                removed.append(path.name)
    return removed


def _cleanup_release_images(folders, keep_paths):
    """Remove leftover release-named images after poster/background/thumbs are set."""
    keep = {Path(path).resolve() for path in keep_paths if path}
    reserved = {
        'poster.jpg', 'folder.jpg', 'cover.jpg', 'fanart.jpg',
        'background.jpg', 'backdrop.jpg', 'art.jpg',
    }
    removed = []
    for folder in folders:
        root = Path(folder)
        if not root.is_dir():
            continue
        for path in list(root.iterdir()):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            if path.name.startswith('.'):
                continue
            if path.name.lower() in reserved:
                continue
            if path.stem.endswith('-thumb'):
                continue
            if path.resolve() in keep:
                continue
            path.unlink(missing_ok=True)
            removed.append(path.name)
    return removed


def _remove_numbered_duplicates(root):
    """Delete Windows-style 'name (1).ext' copies when the original (or video) exists."""
    root = Path(root)
    removed = []
    if not root.is_dir():
        return removed
    for path in list(root.rglob('*')):
        if not path.is_file():
            continue
        match = _NUMBERED_DUP.match(path.name)
        if not match:
            continue
        base = match.group('base').rstrip()
        ext = match.group('ext').lower()
        original = path.with_name(base + match.group('ext'))
        # Subtitle (1)/(2) next to the episode video — always junk duplicates.
        if ext in SUBTITLE_EXTENSIONS:
            video_here = any(
                (path.parent / (base + video_ext)).is_file()
                for video_ext in VIDEO_EXTENSIONS
            )
            if original.is_file() or video_here:
                path.unlink(missing_ok=True)
                removed.append(path.name)
                continue
        # Duplicate video or any sidecar when the un-numbered file already exists.
        if original.is_file() and original.resolve() != path.resolve():
            path.unlink(missing_ok=True)
            removed.append(path.name)
    return removed


def _remove_junk_files(root):
    """Drop release notes and OS junk that should not sit in a show folder."""
    root = Path(root)
    removed = []
    if not root.is_dir():
        return removed
    for path in list(root.rglob('*')):
        if not path.is_file():
            continue
        name = path.name.lower()
        if name in _JUNK_NAMES or name.endswith('重要申明.txt'):
            path.unlink(missing_ok=True)
            removed.append(path.name)
            continue
        # Hidden download leftovers / temp catalog pictures.
        if name.startswith('.picture-') or name.startswith('.audit-'):
            path.unlink(missing_ok=True)
            removed.append(path.name)
    return removed


def scrub_show_tree(show_dir):
    """Remove duplicate (1)/(2) files and other junk under a show folder."""
    show_dir = Path(show_dir)
    removed = []
    removed.extend(_remove_numbered_duplicates(show_dir))
    removed.extend(_remove_junk_files(show_dir))
    return removed


def _series_key(folder_path, library_root):
    """Group key for a video folder. Season 01 lives under the show folder."""
    folder = Path(folder_path)
    if re.fullmatch(r'Season \d+', folder.name, flags=re.I):
        return str(folder.parent)
    return str(folder)


def _series_label(folder_path):
    folder = Path(folder_path)
    if re.fullmatch(r'Season \d+', folder.name, flags=re.I):
        return folder.parent.name
    return folder.name



def _rename_only(source, dest):
    """Move a file by renaming it. A cross-device move would copy, so it is refused."""
    source = Path(source)
    dest = Path(dest)
    if source.resolve() == dest.resolve():
        return True, 'already in place'
    if dest.exists():
        return False, 'left in place because that name already exists'
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(source, dest)
    except OSError as error:
        if error.errno == errno.EXDEV:
            return False, 'left in place because moving it would copy the file'
        raise
    return True, 'renamed'


def _sidecar_dest(source, video_stem, new_stem):
    name = source.name
    for marker in (source.suffix, '(' , ' ('):
        if name.startswith(video_stem + marker):
            return new_stem + name[len(video_stem):]
    return ''


def _empty_dir(path):
    path = Path(path)
    if path.is_dir() and not any(path.iterdir()):
        path.rmdir()


def _purge_migrated_source(source_dir):
    """After videos moved out, drop leftover artwork/NFO so the folder can go away."""
    root = Path(source_dir)
    if not root.is_dir():
        return
    leftovers = {
        'poster.jpg', 'folder.jpg', 'cover.jpg', 'fanart.jpg',
        'background.jpg', 'backdrop.jpg', 'art.jpg', 'tvshow.nfo',
    }
    for path in list(root.iterdir()):
        if not path.is_file():
            continue
        name = path.name.lower()
        if name in leftovers or path.suffix.lower() == '.nfo':
            path.unlink(missing_ok=True)
            continue
        if path.suffix.lower() in IMAGE_EXTENSIONS and not path.stem.endswith('-thumb'):
            path.unlink(missing_ok=True)
    _empty_dir(root)


def process_library(folder_path, settings, update, should_continue):
    """Write show and episode metadata. Rename videos only when organize is on."""
    library = Path(folder_path)
    files = scan_videos(library)
    update(total_files=len(files), message=f'Found {len(files)} videos')
    if not files:
        update(error='No videos found in folder', running=False)
        return
    groups = {}
    for item in files:
        key = _series_key(item['folder'], library)
        groups.setdefault(key, []).append(item)
    auditing = bool(settings.get('audit'))
    organize = bool(settings.get('organize_files', True))
    download_cover = bool(settings.get('download_cover', True))
    create_nfo = bool(settings.get('create_nfo', True))
    media_server = settings.get('media_server') or 'plex'
    done = 0
    for folder, items in groups.items():
        if not should_continue():
            update(message='Stopped')
            return
        folder_path_obj = Path(folder)
        if settings.get('skip_complete') and not auditing:
            still = []
            for item in items:
                if Path(item['file_path']).with_suffix('.nfo').is_file():
                    done += 1
                else:
                    still.append(item)
            if not still:
                if settings.get('download_trailer', True):
                    series = parse_release(_series_label(folder_path_obj), _series_label(folder_path_obj))
                    show = lookup_show(series['title'], series['studio'])
                    show_dir = folder_path_obj
                    if re.fullmatch(r'Season \d+', folder_path_obj.name, flags=re.I):
                        show_dir = folder_path_obj.parent
                    note = _download_show_trailer(show_dir, show)
                    print(f'{show.get("title") or series["title"]}: {note}', flush=True)
                    if create_nfo and show.get('trailer_file'):
                        (show_dir / 'tvshow.nfo').write_text(tvshow_nfo(show), encoding='utf-8')
                update(
                    processed_files=done,
                    progress=int((done / len(files)) * 100) if files else 100,
                    message=f'Skipped finished folder {folder_path_obj.name}',
                )
                continue
            items = still
        series_name = _series_label(folder_path_obj)
        series = parse_release(series_name, series_name)
        parsed_rows = []
        for item in items:
            parsed = parse_release(series_name, item['filename'])
            parsed['title'] = series['title'] or parsed['title']
            parsed['studio'] = series['studio'] or parsed['studio']
            parsed['item'] = item
            parsed_rows.append(parsed)
        parsed_rows.sort(key=lambda row: (row['episode_start'] or 9999, row['item']['filename']))
        _assign_episodes(parsed_rows)
        show = lookup_show(parsed_rows[0]['title'], parsed_rows[0]['studio'])
        show_name = show_folder_name(show)
        source_dirs = []
        for item in items:
            parent = Path(item['folder'])
            if parent not in source_dirs:
                source_dirs.append(parent)
            if folder_path_obj not in source_dirs:
                source_dirs.append(folder_path_obj)
        if organize:
            show_dir = library / show_name
            season_dir = show_dir / 'Season 01'
        else:
            if re.fullmatch(r'Season \d+', folder_path_obj.name, flags=re.I):
                show_dir = folder_path_obj.parent
                season_dir = folder_path_obj
            else:
                show_dir = folder_path_obj
                season_dir = folder_path_obj
        show_dir.mkdir(parents=True, exist_ok=True)
        if organize:
            season_dir.mkdir(parents=True, exist_ok=True)
        label = show['title']
        line = ('Matched ' if show['matched'] else 'No catalog match for ') + label
        print(line, flush=True)
        update(
            current_file=label,
            processed_files=done,
            progress=int((done / len(files)) * 100),
            message=line,
        )
        if download_cover:
            note = _save_artwork(show_dir, show, media_server, source_dirs=source_dirs)
            print(f'{label}: {note}', flush=True)
            update(message=f'{label}: {note}')
        if settings.get('download_trailer', True):
            note = _download_show_trailer(show_dir, show)
            print(f'{label}: {note}', flush=True)
            update(message=f'{label}: {note}')
        if create_nfo:
            (show_dir / 'tvshow.nfo').write_text(tvshow_nfo(show), encoding='utf-8')
        kept_images = set()
        if (show_dir / artwork_profile(media_server)['posters'][0]).is_file():
            kept_images.add((show_dir / artwork_profile(media_server)['posters'][0]).resolve())
        if (show_dir / artwork_profile(media_server)['backgrounds'][0]).is_file():
            kept_images.add((show_dir / artwork_profile(media_server)['backgrounds'][0]).resolve())
        for parsed in parsed_rows:
            if not should_continue():
                update(message='Stopped')
                return
            item = parsed['item']
            source = Path(item['file_path'])
            if not source.is_file():
                done += 1
                continue
            suffix = source.suffix
            new_name = episode_filename(show_name, parsed['episode_start'], parsed['episode_end'], suffix)
            video_path = source
            original_stem = source.stem
            search_dirs = list(source_dirs)
            if organize:
                moved, note = _rename_only(source, season_dir / new_name)
                update(message=f'{new_name}: {note}')
                if not moved and create_nfo:
                    (source.parent / 'tvshow.nfo').write_text(tvshow_nfo(show), encoding='utf-8')
                if moved:
                    video_path = season_dir / new_name
                    image_hits = []
                    for sibling in list(source.parent.iterdir()) if source.parent.is_dir() else []:
                        if not sibling.is_file():
                            continue
                        suffix_l = sibling.suffix.lower()
                        if suffix_l in SUBTITLE_EXTENSIONS:
                            dest_name = _sidecar_dest(sibling, original_stem, video_path.stem)
                            if dest_name:
                                _rename_only(sibling, season_dir / dest_name)
                            continue
                        if suffix_l not in IMAGE_EXTENSIONS:
                            continue
                        if sibling.name.startswith('.') or sibling.name.lower() in {
                            'poster.jpg', 'folder.jpg', 'cover.jpg', 'fanart.jpg',
                            'background.jpg', 'backdrop.jpg', 'art.jpg',
                        }:
                            continue
                        base = re.sub(r'\s*\(\d+\)$', '', sibling.stem).strip()
                        orig_base = re.sub(r'\s*\(\d+\)$', '', original_stem).strip()
                        if sibling.stem == original_stem or base == orig_base or sibling.stem.startswith(orig_base):
                            image_hits.append(sibling)
                    if image_hits:
                        best, _ = _pick_best_image(image_hits, prefer='any')
                        thumb_dest = season_dir / (video_path.stem + '-thumb.jpg')
                        if best is not None:
                            _rename_only(best, thumb_dest)
                            for extra in image_hits:
                                if extra.exists() and extra.resolve() != thumb_dest.resolve():
                                    extra.unlink(missing_ok=True)
                    search_dirs.append(season_dir)
            # Promote thumbs even when organize is off or files were already moved.
            _promote_episode_thumbs(video_path, search_dirs + [video_path.parent])
            thumb = video_path.with_name(video_path.stem + '-thumb.jpg')
            if thumb.is_file():
                kept_images.add(thumb.resolve())
            if create_nfo:
                nfo_path = video_path.with_suffix('.nfo')
                nfo_path.write_text(episode_nfo(show, parsed), encoding='utf-8')
            done += 1
            update(processed_files=done, progress=int((done / len(files)) * 100))
        cleanup_dirs = list(source_dirs) + [show_dir, season_dir]
        _cleanup_release_images(cleanup_dirs, kept_images)
        scrubbed = scrub_show_tree(show_dir)
        if scrubbed:
            print(f'{label}: removed {len(scrubbed)} junk/duplicate files', flush=True)
        if organize:
            for source_dir in source_dirs:
                if source_dir.resolve() in {library.resolve(), show_dir.resolve(), season_dir.resolve()}:
                    continue
                _purge_migrated_source(source_dir)
                scrub_show_tree(source_dir)
                parent = source_dir.parent
                if parent.resolve() != library.resolve() and parent.is_dir():
                    _empty_dir(parent)
    # Final pass: scrub every show folder under the library for leftover (1)/(2) junk.
    if library.is_dir():
        for child in library.iterdir():
            if child.is_dir() and not child.name.startswith(('.', '@')):
                scrub_show_tree(child)
    update(progress=100, message=f'Saved metadata for {done} videos', processed_files=done)
