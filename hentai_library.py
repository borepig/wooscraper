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

from scraper_engine import artwork_profile, copy_bytes_as, image_request_headers

VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.wmv', '.mov'}
SUBTITLE_EXTENSIONS = {'.ass', '.ssa', '.srt', '.sub', '.idx'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
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
    if not title:
        title = safe_name(folder_name)
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
        if '.audit-' in path.name:
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


def _ipv4_get(url, headers, limit):
    """GET over IPv4. Several of these hosts do not answer on IPv6 from this network."""
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
      title { romaji english native }
      synonyms
      description(asHtml: false)
      startDate { year }
      averageScore
      coverImage { extraLarge large }
      bannerImage
      studios { nodes { name } }
      trailer { site id }
      streamingEpisodes { title }
      characters(perPage: 8, sort: [ROLE, RELEVANCE]) {
        edges { role node { name { full } image { large } } }
      }
    }
  }
}
'''


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
    key = _norm(title) + '|' + _norm(studio)
    if key in _SHOW_CACHE:
        return _SHOW_CACHE[key]
    show = {
        'catalog_id': None,
        'title': title,
        'original': title,
        'year': None,
        'plot': '',
        'score': None,
        'votes': None,
        'studio': studio,
        'poster_url': '',
        'picture_urls': [],
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
        show['title'] = names.get('english') or names.get('romaji') or title
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
        trailer = best.get('trailer') or {}
        if (trailer.get('site') or '').lower() == 'youtube' and trailer.get('id'):
            show['trailer_url'] = 'https://www.youtube.com/watch?v=' + trailer['id']
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
    if show.get('trailer_url'):
        lines.append(f"    <trailer>{_xml(show['trailer_url'])}</trailer>")
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
    series = parse_release(folder_name, folder_name)
    parsed = parse_release(folder_name, filename)
    parsed['title'] = series['title'] or parsed['title']
    parsed['studio'] = series['studio'] or parsed['studio']
    if not parsed['episode_start']:
        parsed['episode_start'] = 1
        parsed['episode_end'] = 1
    show = lookup_show(parsed['title'], parsed['studio'])
    folder = show_folder_name(show)
    suffix = Path(filename).suffix or '.mkv'
    profile = artwork_profile(media_server)
    fanart = show['picture_urls'][0] if show['picture_urls'] else show['poster_url']
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
        'cover_url': show['poster_url'],
        'fanart_url': fanart,
        'trailer_url': show['trailer_url'],
        'jav_code': folder,
        'artwork': {
            'posters': list(profile['posters']),
            'backgrounds': list(profile['backgrounds']),
            'actor_local': False,
            'remove': [],
            'remove_actors': False,
        },
    }


def _download(url, dest):
    if not url or not url.startswith('https://'):
        return False
    host = (urllib.parse.urlparse(url).hostname or '').lower()
    if 'anilist.co' not in host:
        return False
    try:
        status, payload = _ipv4_get(url, image_request_headers(url), 8_000_000)
        if status != 200:
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


def _save_artwork(show_dir, show, media_server):
    profile = artwork_profile(media_server)
    poster_path = show_dir / profile['posters'][0]
    background_path = show_dir / profile['backgrounds'][0]
    urls = [show.get('poster_url') or '']
    urls.extend(show.get('picture_urls') or [])
    saved = []
    for url in urls:
        if not url or url in saved:
            continue
        target = show_dir / f'.picture-{len(saved)}.jpg'
        if _download(url, target):
            saved.append(target)
        if len(saved) >= 3:
            break
    if not saved:
        return 'no poster published'
    poster = saved[0]
    background = saved[0]
    try:
        from PIL import Image
        widest = -1
        tallest = -1
        for path in saved:
            with Image.open(path) as image:
                width, height = image.size
            if width > widest:
                widest = width
                background = path
            if height >= width and height > tallest:
                tallest = height
                poster = path
    except Exception:
        poster = saved[0]
        background = saved[0]
    poster_path.parent.mkdir(parents=True, exist_ok=True)
    if poster != poster_path:
        poster_path.write_bytes(poster.read_bytes())
    if background != background_path:
        background_path.write_bytes(background.read_bytes())
    copy_bytes_as(poster_path, profile['posters'])
    copy_bytes_as(background_path, profile['backgrounds'])
    for path in saved:
        if path.name.startswith('.picture-'):
            path.unlink(missing_ok=True)
    return 'poster and background saved'


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
        groups.setdefault(item['folder'], []).append(item)
    organize = bool(settings.get('organize_files', True)) and not settings.get('audit')
    download_cover = bool(settings.get('download_cover', True))
    create_nfo = bool(settings.get('create_nfo', True))
    media_server = settings.get('media_server') or 'plex'
    done = 0
    for folder, items in groups.items():
        if not should_continue():
            update(message='Stopped')
            return
        folder_path_obj = Path(folder)
        if settings.get('skip_complete'):
            still = []
            for item in items:
                if Path(item['file_path']).with_suffix('.nfo').is_file():
                    done += 1
                else:
                    still.append(item)
            if not still:
                update(
                    processed_files=done,
                    progress=int((done / len(files)) * 100) if files else 100,
                    message=f'Skipped finished folder {folder_path_obj.name}',
                )
                continue
            items = still
        series = parse_release(folder_path_obj.name, folder_path_obj.name)
        parsed_rows = []
        for item in items:
            parsed = parse_release(folder_path_obj.name, item['filename'])
            parsed['title'] = series['title'] or parsed['title']
            parsed['studio'] = series['studio'] or parsed['studio']
            parsed['item'] = item
            parsed_rows.append(parsed)
        parsed_rows.sort(key=lambda row: (row['episode_start'] or 9999, row['item']['filename']))
        _assign_episodes(parsed_rows)
        show = lookup_show(parsed_rows[0]['title'], parsed_rows[0]['studio'])
        show_name = show_folder_name(show)
        if organize:
            show_dir = library / show_name
            season_dir = show_dir / 'Season 01'
        else:
            show_dir = folder_path_obj
            season_dir = folder_path_obj
        show_dir.mkdir(parents=True, exist_ok=True)
        label = show['title']
        update(
            current_file=label,
            processed_files=done,
            progress=int((done / len(files)) * 100),
            message=('Matched ' if show['matched'] else 'No catalog match for ') + label,
        )
        if download_cover:
            note = _save_artwork(show_dir, show, media_server)
            update(message=f'{label}: {note}')
        if create_nfo:
            (show_dir / 'tvshow.nfo').write_text(tvshow_nfo(show), encoding='utf-8')
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
            if organize:
                moved, note = _rename_only(source, season_dir / new_name)
                update(message=f'{new_name}: {note}')
                if not moved and create_nfo:
                    (source.parent / 'tvshow.nfo').write_text(tvshow_nfo(show), encoding='utf-8')
                if moved:
                    video_path = season_dir / new_name
                    for sibling in list(folder_path_obj.iterdir()) if folder_path_obj.is_dir() else []:
                        if not sibling.is_file():
                            continue
                        if sibling.suffix.lower() not in SUBTITLE_EXTENSIONS | IMAGE_EXTENSIONS:
                            continue
                        dest_name = _sidecar_dest(sibling, source.stem, video_path.stem)
                        if not dest_name:
                            continue
                        if sibling.suffix.lower() in IMAGE_EXTENSIONS and dest_name == video_path.stem + sibling.suffix:
                            dest_name = video_path.stem + '-thumb' + sibling.suffix
                        _rename_only(sibling, season_dir / dest_name)
            if create_nfo:
                nfo_path = video_path.with_suffix('.nfo')
                nfo_path.write_text(episode_nfo(show, parsed), encoding='utf-8')
            done += 1
            update(processed_files=done, progress=int((done / len(files)) * 100))
        if organize and folder_path_obj.resolve() != library.resolve():
            _empty_dir(folder_path_obj)
    update(progress=100, message=f'Saved metadata for {done} videos', processed_files=done)
