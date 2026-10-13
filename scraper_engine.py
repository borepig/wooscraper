"""
JAV Scraper Engine
==================

A module for scraping metadata from JAV (Japanese Adult Video) content.

This engine handles the core functionality of scanning folders for JAV files,
extracting metadata, and generating NFO files for media servers.
"""

import re
import os
import shutil
import asyncio
import aiohttp
import yaml
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Tuple
import logging
from pathlib import Path
import json
from datetime import datetime
from PIL import Image
import urllib.parse
import tempfile
from xml.sax.saxutils import escape as xml_escape

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

# A preview can be a long HD sample. Past this, treat the file as a full movie.
TRAILER_MAX_BYTES = 1_000_000_000


def image_request_headers(url: str) -> dict:
    """Headers that the cover CDNs accept. The referer has to match the host."""
    host = (urllib.parse.urlparse(url).hostname or '').lower()
    if host.endswith('dmm.co.jp'):
        referer = 'https://www.dmm.co.jp/'
    elif 'javtrailers.com' in host:
        referer = 'https://javtrailers.com/'
    elif 'javdatabase.com' in host:
        referer = 'https://www.javdatabase.com/'
    elif 'myanimelist.net' in host:
        referer = 'https://myanimelist.net/'
    elif 'anilist.co' in host:
        referer = 'https://anilist.co/'
    elif host.endswith('getchu.com'):
        referer = 'https://www.getchu.com/'
    elif host.endswith('duga.jp'):
        referer = 'https://duga.jp/'
    elif host.endswith('hnt.co.jp'):
        referer = 'https://anime.hnt.co.jp/'
    elif host.endswith('anidb.net'):
        referer = 'https://anidb.net/'
    else:
        referer = 'https://jav.guru/'
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
        'Referer': referer,
        'Sec-Fetch-Dest': 'image',
        'Sec-Fetch-Mode': 'no-cors',
        'Sec-Fetch-Site': 'cross-site',
    }


def dmm_portrait_from_name(name: str) -> str:
    """DMM headshot when the trailer site has the name but no portrait file.

    The filename is family name then given name, with a few romanization
    swaps (shi/si, tsu/tu). Either name order is tried, and only a real image counts.
    """
    tokens = re.findall(r'[A-Za-z]+', name or '')
    if not tokens:
        return ''
    orders = [list(reversed(tokens)), tokens] if len(tokens) > 1 else [tokens]
    urls = []
    for order in orders:
        raw = '_'.join(token.lower() for token in order)
        converted = raw
        for source, target in (('tsu', 'tu'), ('shi', 'si'), ('chi', 'ti'), ('fu', 'hu')):
            converted = converted.replace(source, target)
        for stem in (converted, raw):
            url = f'https://pics.dmm.co.jp/mono/actjpgs/{stem}.jpg'
            if url not in urls:
                urls.append(url)
    for url in urls:
        if remote_image_size(url) > 1000:
            return url
    return ''


def artwork_profile(server):
    """Filenames each media server looks for beside the video."""
    name = (server or 'plex').strip().lower()
    profiles = {
        'plex': {
            'posters': ('poster.jpg',),
            'backgrounds': ('background.jpg',),
            'actor': 'url',
        },
        'jellyfin': {
            'posters': ('poster.jpg', 'folder.jpg'),
            'backgrounds': ('fanart.jpg', 'backdrop.jpg'),
            'actor': 'local',
        },
        'emby': {
            'posters': ('folder.jpg',),
            'backgrounds': ('backdrop.jpg',),
            'actor': 'local',
        },
        'kodi': {
            'posters': ('poster.jpg', 'folder.jpg'),
            'backgrounds': ('fanart.jpg',),
            'actor': 'local',
        },
        'all': {
            'posters': ('poster.jpg', 'folder.jpg'),
            'backgrounds': ('fanart.jpg', 'background.jpg', 'backdrop.jpg'),
            'actor': 'both',
        },
    }
    return profiles.get(name, profiles['plex'])


def prune_other_artwork(folder, server):
    """Drop image names the chosen server does not use. All keeps every name."""
    name = (server or 'plex').strip().lower()
    if name == 'all':
        return []
    profile = artwork_profile(name)
    folder = Path(folder)
    removed = []
    keep = set(profile['posters']) | set(profile['backgrounds'])
    background_names = {'fanart.jpg', 'background.jpg', 'backdrop.jpg', 'art.jpg'}
    poster_names = {'poster.jpg', 'folder.jpg', 'cover.jpg'}
    background_ready = any((folder / item).is_file() for item in profile['backgrounds'])
    poster_ready = any((folder / item).is_file() for item in profile['posters'])
    for item in ('poster.jpg', 'folder.jpg', 'cover.jpg', 'fanart.jpg', 'background.jpg', 'backdrop.jpg', 'art.jpg'):
        if item in keep or not (folder / item).is_file():
            continue
        if item in background_names and not background_ready:
            continue
        if item in poster_names and not poster_ready:
            continue
        (folder / item).unlink()
        removed.append(item)
    if profile['actor'] == 'url':
        actors = folder / '.actors'
        if actors.is_dir():
            shutil.rmtree(actors)
            removed.append('.actors')
        for path in folder.glob('*_portrait.jpg'):
            if path.is_file():
                path.unlink()
                removed.append(path.name)
    return removed


def actor_image_rel(name):
    """Kodi, Jellyfin, and Emby read .actors/Name.jpg (spaces become underscores)."""
    cleaned = re.sub(r'[<>:"/\\|?*]', '', name or '').strip()
    cleaned = re.sub(r'\s+', '_', cleaned)
    return f'.actors/{cleaned}.jpg' if cleaned else ''


def copy_bytes_as(source_path, names):
    """Write the same image under every filename a chosen server expects."""
    source = Path(source_path)
    if not source.is_file():
        return
    data = source.read_bytes()
    for name in names:
        dest = source.parent / name
        if dest == source:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)


def portrait_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', '', name or '').strip()
    cleaned = re.sub(r'\s+', '_', cleaned)
    return f'{cleaned}_portrait.jpg' if cleaned else ''


def actress_name_key(name: str) -> str:
    """Same person even when the sites swap family name and given name."""
    return ' '.join(sorted(re.findall(r'[a-z]+', (name or '').lower())))


def actress_names_match(left: str, right: str) -> bool:
    """True when two spellings are the same person, including joined names."""
    def forms(value):
        tokens = re.findall(r'[a-z]+', (value or '').lower())
        if not tokens:
            return set()
        return {''.join(tokens), ''.join(reversed(tokens))}
    return bool(forms(left) & forms(right))


def _preview_host_ok(url: str, suffix: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return (
        parsed.scheme == 'https'
        and (parsed.hostname or '').lower() == 'media.javtrailers.com'
        and parsed.path.startswith('/hlsvideo/freepv/')
        and parsed.path.endswith(suffix)
    )


def _fetch_preview_text(url: str) -> str:
    request = urllib.request.Request(url, headers=image_request_headers(url))
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode('utf-8', 'replace')


def _pick_hls_variant(playlist: str, base: str) -> str:
    """Choose the 720p stream when the preview offers several sizes."""
    variants = []
    width = 0
    for line in playlist.splitlines():
        line = line.strip()
        if line.startswith('#EXT-X-STREAM-INF'):
            match = re.search(r'RESOLUTION=(\d+)x(\d+)', line)
            width = int(match.group(1)) if match else 0
        elif line and not line.startswith('#') and width:
            url = line if line.startswith('http') else urllib.parse.urljoin(base, line)
            variants.append((width, url))
            width = 0
    if not variants:
        return ''
    variants.sort(key=lambda item: (abs(item[0] - 1280), -item[0]))
    return variants[0][1]


def hls_preview_segments(playlist_url: str) -> List[str]:
    """Turn a preview playlist into the list of short video pieces it contains."""
    if not _preview_host_ok(playlist_url, '.m3u8'):
        return []
    try:
        playlist = _fetch_preview_text(playlist_url)
    except Exception as error:
        logging.warning(f"Preview playlist failed: {error}")
        return []
    base = playlist_url.rsplit('/', 1)[0] + '/'
    if '#EXT-X-STREAM-INF' in playlist:
        chosen = _pick_hls_variant(playlist, base)
        if not chosen or not _preview_host_ok(chosen, '.m3u8'):
            return []
        try:
            playlist = _fetch_preview_text(chosen)
        except Exception as error:
            logging.warning(f"Preview variant failed: {error}")
            return []
        base = chosen.rsplit('/', 1)[0] + '/'
    segments = []
    for line in playlist.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        url = line if line.startswith('http') else urllib.parse.urljoin(base, line)
        if not _preview_host_ok(url, '.ts'):
            continue
        segments.append(url)
        if len(segments) >= 500:
            break
    return segments


def preview_from_page(html: str) -> Dict:
    """An older preview is one MP4. A current one is a playlist of short pieces."""
    mp4 = re.search(
        r'https://media\.javtrailers\.com/litevideo/freepv/[A-Za-z0-9_./-]+\.mp4',
        html,
    )
    if mp4:
        return {'trailer_url': mp4.group(0), 'trailer_segments': []}
    playlist = re.search(
        r'https://media\.javtrailers\.com/hlsvideo/freepv/[A-Za-z0-9_./-]+\.m3u8',
        html,
    )
    if not playlist:
        return {'trailer_url': '', 'trailer_segments': []}
    url = playlist.group(0)
    return {'trailer_url': url, 'trailer_segments': hls_preview_segments(url)}


def remote_image_size(url: str) -> int:
    """Byte size of an image, used to pick the high-resolution package art."""
    headers = image_request_headers(url)
    headers['Range'] = 'bytes=0-0'
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if 'now_printing' in (response.geturl() or ''):
                return 0
            span = response.headers.get('Content-Range') or ''
            if '/' in span:
                return int(span.rsplit('/', 1)[-1] or 0)
            return int(response.headers.get('Content-Length') or 0)
    except Exception:
        return 0


def fetch_html_urllib(url: str) -> Optional[str]:
    """Plain HTTP fetch. Some sites answer this and refuse the async client."""
    request = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            html = response.read().decode('utf-8', 'replace')
    except Exception as error:
        logging.warning(f"Plain HTTP fetch failed for {url}: {error}")
        return None
    if html and len(html) > 500 and 'Just a moment' not in html:
        logging.info(f"Fetched {url} over plain HTTP ({len(html)} chars)")
        return html
    return None

def image_dimensions(path) -> Tuple[int, int]:
    """Width and height of a local image, or zeroes when the file cannot be read."""
    try:
        with Image.open(path) as img:
            return int(img.size[0]), int(img.size[1])
    except Exception:
        return (0, 0)


def image_pixels(path) -> int:
    width, height = image_dimensions(path)
    return width * height


def settle_sidecar_trailers(folder) -> str:
    """Move trailer.mp4 or trailer.ts into Trailers/. Return the preview path when one exists."""
    library = Path(folder)
    extras = library / 'Trailers'
    have = ''
    if (extras / 'Preview.mp4').is_file():
        have = 'Trailers/Preview.mp4'
    elif (extras / 'Preview.ts').is_file():
        have = 'Trailers/Preview.ts'
    for source_name, dest_name in (('trailer.mp4', 'Preview.mp4'), ('trailer.ts', 'Preview.ts')):
        sidecar = library / source_name
        if not sidecar.is_file():
            continue
        if have:
            sidecar.unlink()
            logging.info(f"Removed unused {sidecar}")
            continue
        extras.mkdir(parents=True, exist_ok=True)
        sidecar.replace(extras / dest_name)
        have = f'Trailers/{dest_name}'
        logging.info(f"Moved sidecar trailer to {have}")
    return have


def title_assets_ready(folder, create_nfo=True, download_cover=True, download_trailer=True, media_server='plex') -> bool:
    """True when this folder already has every file this run would write.

    A repeat batch uses this so trailers that are already on disk are not
    downloaded again.
    """
    library = Path(folder)
    if not (create_nfo or download_cover or download_trailer):
        return False
    if create_nfo and not (library / 'movie.nfo').is_file():
        return False
    if download_cover:
        profile = artwork_profile(media_server)
        poster = library / profile['posters'][0]
        background = library / profile['backgrounds'][0]
        if not poster.is_file() or not background.is_file():
            return False
    if download_trailer:
        extras = library / 'Trailers'
        has_trailer = (
            (extras / 'Preview.mp4').is_file()
            or (extras / 'Preview.ts').is_file()
            or (library / 'trailer.mp4').is_file()
            or (library / 'trailer.ts').is_file()
        )
        if not has_trailer:
            return False
    return True


def plot_repeats_title(plot: str, title: str) -> bool:
    """True when the text is empty or only a restatement of the title."""
    text = re.sub(r'\s+', ' ', plot or '').strip()
    name = re.sub(r'\s+', ' ', title or '').strip()
    if not text or text.lower().startswith('jav content:'):
        return True
    if not name:
        return False
    if text.casefold() == name.casefold():
        return True
    return name.casefold() in text.casefold() and len(text) <= len(name) + 24


def _text_needs_english(text: str) -> bool:
    letters = [ch for ch in text or '' if ch.isalpha()]
    if not letters:
        return False
    cjk = sum(1 for ch in letters if '\u3040' <= ch <= '\u30ff' or '\u4e00' <= ch <= '\u9fff')
    return cjk / len(letters) > 0.2


def _google_english(text: str) -> str:
    url = (
        'https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=ja&tl=en&q='
        + urllib.parse.quote(text)
    )
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode('utf-8', 'replace'))
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, list) and payload and isinstance(payload[0], str):
        return ''.join(part for part in payload if isinstance(part, str)).strip()
    return ''


def _mymemory_english(text: str) -> str:
    url = 'https://api.mymemory.translated.net/get?langpair=ja|en&q=' + urllib.parse.quote(text)
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode('utf-8', 'replace'))
    return ((payload.get('responseData') or {}).get('translatedText') or '').strip()


def translate_plot_to_english(text: str) -> str:
    """English plot when the only real synopsis is Japanese. Already-English text stays."""
    original = re.sub(r'\s+', ' ', text or '').strip()
    if not original or not _text_needs_english(original):
        return original
    pieces = []
    start = 0
    while start < len(original):
        pieces.append(original[start:start + 400])
        start += 400
    translated = []
    for piece in pieces:
        english = ''
        for converter in (_google_english, _mymemory_english):
            try:
                english = converter(piece)
            except Exception as error:
                logging.info(f"Description translation failed: {error}")
                english = ''
            if english and not _text_needs_english(english):
                break
            english = ''
        if not english:
            return original
        translated.append(english)
    english_plot = re.sub(r'\s+', ' ', ' '.join(translated)).strip()
    return english_plot.replace('``', '"').replace("''", '"')


def plot_from_fanza(content_id: str) -> str:
    """Official catalog blurb. The trailer page id is the FANZA content id."""
    content_id = (content_id or '').strip()
    if not content_id:
        return ''
    query = 'query($id:ID!){ ppvContent(id:$id){ title description(format:PLAIN) } }'
    body = json.dumps({'query': query, 'variables': {'id': content_id}}).encode()
    request = urllib.request.Request(
        'https://api.video.dmm.co.jp/graphql',
        data=body,
        headers={
            'User-Agent': 'Mozilla/5.0',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Origin': 'https://video.dmm.co.jp',
            'Referer': 'https://video.dmm.co.jp/',
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode('utf-8', 'replace'))
    except Exception as error:
        logging.info(f"Catalog description unavailable for {content_id}: {error}")
        return ''
    item = ((payload.get('data') or {}).get('ppvContent')) or {}
    description = re.sub(r'\s+', ' ', item.get('description') or '').strip()
    if plot_repeats_title(description, item.get('title') or ''):
        return ''
    return description


def rating_from_javdb(code: str):
    """Community score for one code. The site uses 5 stars; Plex uses 10."""
    cleaned = (code or '').strip().upper()
    if not cleaned:
        return None
    url = 'https://javdb.com/search?q=' + urllib.parse.quote(cleaned) + '&f=all'
    html = fetch_html_urllib(url)
    if not html:
        return None
    for part in html.split('<a href="/v/')[1:]:
        strong = re.search(r'<strong>\s*([^<]+?)\s*</strong>', part)
        if not strong or strong.group(1).strip().upper() != cleaned:
            continue
        start = part.find('class="score"')
        if start < 0:
            return None
        window = part[start:start + 700]
        score = re.search(r'(\d+(?:\.\d+)?)\s*(?:分|,)', window)
        if not score:
            return None
        five = float(score.group(1))
        if five <= 0 or five > 5:
            return None
        votes = re.search(r'(?:by|由)\s*([\d,]+)', window)
        vote_count = int(votes.group(1).replace(',', '')) if votes else 0
        cover = re.search(r'https://c\d\.jdbstatic\.com/covers/[^"\'\s]+', part)
        return round(five * 2, 1), vote_count, cover.group(0) if cover else ''
    return None


def remove_stray_audit_copies(video_path) -> str:
    """Delete a leftover full copy beside the movie. The movie file is not opened or renamed."""
    path = Path(video_path)
    if not path.is_file():
        return ''
    parent = path.parent
    extras = [item for item in parent.glob(path.name + '.audit-*') if item.is_file() and item != path]
    for extra in extras:
        extra.unlink()
    return 'removed a leftover copy of the video' if extras else ''


class JAVScraperEngine:
    """
    Main class for the JAV Scraper Engine.

    This class provides all the functionality for scanning folders for JAV files,
    extracting metadata from various sources, and generating NFO files for media servers.
    """

    def __init__(self, config_path: str = "config.yml"):
        """
        Initialize the JAV scraper engine.

        Args:
            config_path (str): Path to the configuration file. Defaults to "config.yml"
        """
        self.config = self._load_config(config_path)
        self.setup_logging()
        self.session = None

    def _load_config(self, config_path: str) -> Dict:
        """
        Load configuration from YAML file.

        Args:
            config_path (str): Path to the configuration file

        Returns:
            Dict: Configuration dictionary or empty dict if file not found
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logging.error(f"Config file {config_path} not found")
            return {}

    def setup_logging(self):
        """
        Setup logging configuration.

        Configures the logging system based on the application's configuration.
        This includes setting log level, format, and output handlers (file and console).
        """
        log_config = self.config.get('logging', {})
        handlers = [logging.StreamHandler()]
        # Vercel's filesystem is read-only outside /tmp, so a log file is optional.
        if not os.environ.get('VERCEL'):
            try:
                handlers.insert(0, logging.FileHandler(log_config.get('file', 'scraper.log')))
            except OSError:
                pass
        logging.basicConfig(
            level=getattr(logging, log_config.get('level', 'INFO')),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=handlers
        )

    async def __aenter__(self):
        """
        Async context manager entry.

        Sets up the HTTP client session for making web requests during scraping operations.

        Returns:
            JAVScraperEngine: The instance of the scraper engine
        """
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.get('scraper', {}).get('timeout', 30))
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit.

        Closes the HTTP client session and performs cleanup operations.

        Args:
            exc_type: Exception type (if any)
            exc_val: Exception value (if any)
            exc_tb: Exception traceback (if any)
        """
        if self.session:
            await self.session.close()

    def extract_jav_code(self, filename: str) -> Optional[str]:
        """
        Extract JAV code from filename.
        Pattern: XXXX-NNNN where XXXX is letters and NNNN is numbers
        """
        # Remove file extension
        name_without_ext = os.path.splitext(filename)[0]

        # Special handling for FC2PPV codes first (since they contain numbers in the prefix)
        # Match: FC2PPV-123456, FC2-PPV-123456, FC2PPV123456, FC2-123456, etc.
        fc2ppv_match = re.search(r'FC2[-_]?PPV[-_-]?(\d{4,7})', name_without_ext.upper())
        if fc2ppv_match:
            number = fc2ppv_match.group(1)
            return f"FC2PPV-{number}"
        # Match FC2-123456 format (without PPV)
        fc2_match = re.search(r'FC2[-_-](\d{4,7})', name_without_ext.upper())
        if fc2_match:
            number = fc2_match.group(1)
            return f"FC2PPV-{number}"

        # Pattern for JAV codes: letters-numbers (e.g., ABC-1234, ABC1234, ABC-123)
        patterns = [
            r'([A-Z]{2,7})-?(\d{2,5})',  # ABC-1234, etc.
            r'([A-Z]{2,7})[-_](\d{2,5})',  # ABC_1234
            r'([A-Z]{2,7})(\d{2,5})',  # ABC1234
        ]

        for pattern in patterns:
            match = re.search(pattern, name_without_ext.upper())
            if match:
                prefix, number = match.groups()
                return f"{prefix}-{number}"

        return None

    def clean_actress_name(self, actress_name: str) -> str:
        """
        Clean actress name by removing Japanese characters and keeping only English/Romanized names.
        Examples:
        - "Miku Abeno 阿部乃みく" -> "Miku Abeno"
        - "Yui Hatano 波多野結衣" -> "Yui Hatano"
        - "Asahi Mizuno 水野朝陽" -> "Asahi Mizuno"
        """
        if not actress_name:
            return ""

        # Remove Japanese characters (Hiragana, Katakana, Kanji)
        # Japanese Unicode ranges:
        # Hiragana: 3040-309F
        # Katakana: 30A0-30FF
        # Kanji: 4E00-9FAF
        # Full-width characters: FF00-FFEF
        cleaned_name = re.sub(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF\uFF00-\uFFEF]', '', actress_name)

        # Remove any remaining parentheses and their contents
        cleaned_name = re.sub(r'\s*\([^)]*\)', '', cleaned_name)

        # Remove extra whitespace and normalize
        cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()

        # Remove any remaining special characters that might be left
        # Keep commas so "Aoi Tsukasa, Otoshiro Sayaka" stays two names.
        cleaned_name = re.sub(r'[^\w\s\-\.,]', '', cleaned_name)

        # Final cleanup of extra spaces
        cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()

        return cleaned_name

    def scan_folder(self, folder_path: str) -> List[Dict]:
        """Scan folder for video files and extract JAV codes."""
        video_extensions = self.config.get('scraper', {}).get('video_extensions', ['.mp4', '.avi', '.mkv'])
        results = []

        folder = Path(folder_path)
        if not folder.exists():
            logging.error(f"Folder {folder_path} does not exist")
            return results

        for file_path in folder.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                jav_code = self.extract_jav_code(file_path.name)
                if jav_code:
                    results.append({
                        'file_path': str(file_path),
                        'filename': file_path.name,
                        'jav_code': jav_code,
                        'folder': str(file_path.parent)
                    })

        return results

    async def fetch_html(self, url: str) -> Optional[str]:
        """Fetch a page with a normal HTTP client, then a local browser if needed.

        Hosted runs cannot launch Chromium, and jav.guru currently returns the
        search page to a plain request. Playwright stays a local fallback.
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        try:
            if self.session is None:
                timeout = self.config.get('scraper', {}).get('timeout', 30)
                self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout))
            async with self.session.get(url, headers=headers, allow_redirects=True) as response:
                if response.status == 200:
                    html = await response.text()
                    if html and len(html) > 500 and 'Just a moment' not in html:
                        logging.info(f"Fetched {url} over HTTP ({len(html)} chars)")
                        return html
                logging.warning(f"HTTP fetch for {url} was not usable (status {response.status})")
        except Exception as e:
            logging.warning(f"HTTP fetch failed for {url}: {e}")

        plain = fetch_html_urllib(url)
        if plain:
            return plain

        if async_playwright is not None and not os.environ.get('VERCEL'):
            return await self.fetch_html_with_playwright(url)
        return None

    async def fetch_html_with_playwright(self, url: str) -> Optional[str]:
        """Fetch HTML content using Playwright to bypass bot detection."""
        try:
            logging.info(f"🌐 Using Playwright to fetch: {url}")
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                # Set user agent to look like a real browser
                await page.set_extra_http_headers({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                })

                # Navigate to the page
                await page.goto(url, wait_until='networkidle', timeout=30000)
                logging.info(f"✅ Page loaded successfully")

                # Get the HTML content
                html = await page.content()
                logging.info(f"📄 Retrieved HTML length: {len(html)} characters")

                await browser.close()
                return html
        except Exception as e:
            logging.error(f"❌ Error fetching HTML with Playwright: {e}")
            return None

    async def scrape_javguru(self, jav_code: str) -> Optional[Dict]:
        """Scrape metadata from JavGuru using Playwright to bypass bot detection."""
        try:
            logging.info(f"🔍 Starting JavGuru scrape for {jav_code}")
            url = f"https://jav.guru/?s={jav_code}"

            logging.info(f"📡 Requesting URL with Playwright: {url}")
            html = await self.fetch_html(url)
            if not html:
                logging.warning(f"❌ Failed to fetch HTML with Playwright for {jav_code}")
                return None
            soup = BeautifulSoup(html, 'html.parser')
            # Find the first result
            article = soup.select_one('div.inside-article')
            if not article:
                logging.warning(f"⚠️ No search results found for {jav_code}")
                return None
            # Detail page link
            link_tag = article.select_one('div.imgg a')
            detail_url = link_tag['href'] if link_tag and link_tag.has_attr('href') else None
            # Cover image
            img_tag = link_tag.find('img') if link_tag else None
            cover_url = img_tag['src'] if img_tag and img_tag.has_attr('src') else None
            # Title
            title_tag = article.select_one('div.grid1 h2 a')
            title = title_tag['title'] if title_tag and title_tag.has_attr('title') else (title_tag.text.strip() if title_tag else None)
            # Tags
            tags = [a.text for a in article.select('div.grid3 p.tags a')]
            # Stats
            stats = article.select_one('div.javstats')
            stats_text = stats.text.strip() if stats else ""
            # Date
            date_tag = article.select_one('div.date')
            date = date_tag.text.strip() if date_tag else ""
            # Now fetch the detail page for comprehensive metadata
            if detail_url:
                logging.info(f"🔗 Fetching detail page: {detail_url}")
                detail_html = await self.fetch_html(detail_url)

                if detail_html:
                    logging.info(f"📄 Detail page HTML length: {len(detail_html)} characters")

                    # Parse detail page for comprehensive metadata
                    detail_soup = BeautifulSoup(detail_html, 'html.parser')

                    # Extract detailed metadata
                    detailed_metadata = self._extract_detailed_metadata(detail_soup, jav_code)

                    # Merge search result with detailed metadata
                    # Use fanart URL as the primary image source
                    fanart_url = detailed_metadata.get('fanart_url', cover_url)

                    result = {
                        'title': title,
                        'cover_url': cover_url,  # Keep original cover for fallback
                        'fanart_url': fanart_url,  # Use large image as fanart
                        'detail_url': detail_url,
                        'tags': tags,
                        'stats': stats_text,
                        'date': date,
                        'detailed_metadata': detailed_metadata,  # Add comprehensive metadata
                        'source': 'javguru'
                    }
                    logging.info(f"✅ JavGuru scrape completed for {jav_code}")
                    return result
                else:
                    logging.warning(f"❌ Failed to fetch detail page for {jav_code}")

            # Return search result only if detail page failed
            result = {
                'title': title,
                'cover_url': cover_url,
                'detail_url': detail_url,
                'tags': tags,
                'stats': stats_text,
                'date': date,
                'source': 'javguru'
            }
            logging.info(f"✅ JavGuru scrape completed for {jav_code} (search results only)")
            return result
        except Exception as e:
            logging.error(f"❌ Error scraping JavGuru for {jav_code}: {e}")
            return None

    def _extract_detailed_metadata(self, soup, jav_code):
        """Extract comprehensive metadata from detail page."""
        try:
            metadata = {}

            # Find the infoleft section containing movie information
            infoleft = soup.find('div', class_='infoleft')
            if not infoleft:
                logging.warning(f"⚠️ Could not find infoleft section for {jav_code}")
                return metadata

            # Extract all list items from the movie information section
            info_items = infoleft.find_all('li')

            for item in info_items:
                # Get the strong tag which contains the field name
                strong_tag = item.find('strong')
                if not strong_tag:
                    continue

                # Extract field name (remove any span tags and get clean text)
                field_name = strong_tag.get_text(strip=True).replace(':', '').lower()

                # Extract field value (everything after the strong tag)
                field_value = item.get_text()
                # Remove the field name from the value
                if ':' in field_value:
                    field_value = field_value.split(':', 1)[1].strip()

                # Clean up the field name
                field_name = field_name.replace(' ', '_').replace('-', '_')

                # Each linked name is one person. Flattened text can glue them together.
                if field_name in ['actress', 'actresses', 'cast', 'star', 'stars', 'actor', 'actors']:
                    original_value = field_value
                    linked = []
                    for anchor in item.find_all('a'):
                        cleaned = self.clean_actress_name(anchor.get_text(' ', strip=True))
                        if cleaned and cleaned not in linked:
                            linked.append(cleaned)
                    field_value = ', '.join(linked) if linked else self.clean_actress_name(field_value)
                    logging.info(f"📋 Extracted {field_name}: {original_value} -> {field_value}")
                else:
                    logging.info(f"📋 Extracted {field_name}: {field_value}")

                # Store the metadata
                metadata[field_name] = field_value

            # Also extract the main title from the page
            title_tag = soup.find('h1', class_='titl')
            if title_tag:
                metadata['full_title'] = title_tag.get_text(strip=True)
                logging.info(f"📋 Extracted full_title: {metadata['full_title']}")

            # Extract cover image from the large screenshot (this will be used as fanart)
            large_screenshot = soup.find('div', class_='large-screenshot')
            if large_screenshot:
                img_tag = large_screenshot.find('img')
                if img_tag and img_tag.get('src'):
                    metadata['fanart_url'] = img_tag['src']  # Use as fanart
                    metadata['large_cover_url'] = img_tag['src']  # Keep for compatibility
                    logging.info(f"📋 Extracted fanart_url: {metadata['fanart_url']}")

            # Extract plot/synopsis from wp-content
            wp_content = soup.find('div', class_='wp-content')
            if wp_content:
                paragraphs = wp_content.find_all('p')
                plot_text = []
                for p in paragraphs:
                    text = p.get_text(strip=True)
                    if text and not text.startswith('http'):  # Skip image URLs
                        plot_text.append(text)

                if plot_text:
                    metadata['plot'] = ' '.join(plot_text)
                    logging.info(f"📋 Extracted plot: {metadata['plot'][:100]}...")

            logging.info(f"✅ Extracted {len(metadata)} detailed metadata fields for {jav_code}")
            return metadata

        except Exception as e:
            logging.error(f"❌ Error extracting detailed metadata for {jav_code}: {e}")
            return {}

    async def scrape_fallback(self, jav_code: str) -> Optional[Dict]:
        """Return nothing rather than invented metadata.

        A random cover and a made-up release date used to be written into NFO
        files when every source failed. A miss is more useful than a lie.
        """
        logging.info(f"No metadata source returned a result for {jav_code}")
        return None

    async def scrape_all_sites(self, jav_code: str, enhance: bool = True) -> Dict:
        """Scrape metadata from all enabled sites."""
        logging.info(f"🔍 ==== METADATA SCRAPING START ====")
        logging.info(f"🔍 JAV Code: {jav_code}")
        logging.info(f"🔍 Config: {self.config.get('scraper', {})}")
        
        enabled_sites = [site for site in self.config.get('scraper', {}).get('sites', []) if site.get('enabled', True)]
        logging.info(f"🔍 Enabled sites: {[site['name'] for site in enabled_sites]}")
        
        tasks = []
        for site in enabled_sites:
            site_name = site['name']
            if site_name == 'javguru':
                logging.info(f"🌐 Adding JavGuru task for {jav_code}")
                tasks.append(self.scrape_javguru(jav_code))
            elif site_name == 'javtrailers':
                logging.info(f"🌐 Adding JAV Trailers task for {jav_code}")
                tasks.append(self.scrape_javtrailers(jav_code))
                
        logging.info(f"📡 Starting {len(tasks)} scraping tasks")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        logging.info(f"📊 Scraping results: {results}")
        
        # Check if all sites failed or returned empty results
        all_failed = True
        for i, result in enumerate(results):
            logging.info(f"📊 Analyzing result {i+1}: {type(result)}")
            if isinstance(result, dict) and result:
                # Check if the result has meaningful data
                has_title = result.get('title') and result.get('title') != 'None'
                has_cover = result.get('cover_url')
                has_actress = result.get('details', {}).get('Actress') or result.get('details', {}).get('Actor')
                
                logging.info(f"📊 Result {i+1} analysis:")
                logging.info(f"   📊 Has title: {has_title} ({result.get('title', 'N/A')})")
                logging.info(f"   📊 Has cover: {has_cover} ({result.get('cover_url', 'N/A')})")
                logging.info(f"   📊 Has actress: {has_actress}")
                
                if has_title or has_cover or has_actress:
                    all_failed = False
                    logging.info(f"✅ Result {i+1} has meaningful data")
                    break
            else:
                logging.warning(f"⚠️ Result {i+1} is not valid: {result}")
        
        # If all sites failed, try fallback sites in order: JAVmost -> JAV Trailers -> Basic
        if all_failed:
            logging.warning(f"⚠️ ==== ALL ENABLED SITES FAILED, TRYING FALLBACK SITES ====")
            logging.warning(f"⚠️ All scraping sites failed for {jav_code}, trying fallback sites")
            
            # Try JAVmost first
            logging.info(f"🔍 Trying JAVmost for {jav_code}")
            javmost_result = None
            try:
                javmost_result = await self.scrape_javmost(jav_code)
                if javmost_result:
                    # Check if JAVmost result has meaningful data
                    has_meaningful_data = (javmost_result.get('title') and 
                                          javmost_result.get('title') != jav_code and
                                          javmost_result.get('title') != f"{jav_code} - JAV Content" and
                                          javmost_result.get('title') != "JAV MOST") or \
                                         (javmost_result.get('cover_url') and javmost_result.get('cover_url').strip() != '') or \
                                         (javmost_result.get('details', {}).get('Actress') and 
                                          javmost_result.get('details', {}).get('Actress').strip() != '') or \
                                         (javmost_result.get('details', {}).get('Studio') and 
                                          javmost_result.get('details', {}).get('Studio').strip() != '') or \
                                         (javmost_result.get('detailed_metadata', {}).get('actress') and 
                                          javmost_result.get('detailed_metadata', {}).get('actress').strip() != '') or \
                                         (javmost_result.get('detailed_metadata', {}).get('studio') and 
                                          javmost_result.get('detailed_metadata', {}).get('studio').strip() != '')
                    
                    # Log the meaningful data check for debugging
                    logging.info(f"🔍 JAVmost meaningful data check:")
                    logging.info(f"   🔍 Title: {javmost_result.get('title', 'N/A')}")
                    logging.info(f"   🔍 Cover URL: {javmost_result.get('cover_url', 'N/A')}")
                    logging.info(f"   🔍 Details Actress: {javmost_result.get('details', {}).get('Actress', 'N/A')}")
                    logging.info(f"   🔍 Details Studio: {javmost_result.get('details', {}).get('Studio', 'N/A')}")
                    logging.info(f"   🔍 Detailed Metadata Actress: {javmost_result.get('detailed_metadata', {}).get('actress', 'N/A')}")
                    logging.info(f"   🔍 Detailed Metadata Studio: {javmost_result.get('detailed_metadata', {}).get('studio', 'N/A')}")
                    logging.info(f"   🔍 Has meaningful data: {has_meaningful_data}")
                    
                    if has_meaningful_data:
                        logging.info(f"✅ JAVmost fallback successful with meaningful data")
                        results = [javmost_result]
                        enabled_sites.append({'name': 'javmost', 'enabled': True})
                    else:
                        logging.warning(f"⚠️ JAVmost returned data but no meaningful content for {jav_code}")
                        logging.warning(f"⚠️ No actress information found, will try next fallback site")
                        javmost_result = None  # Mark as failed for next fallback
                else:
                    logging.warning(f"⚠️ JAVmost fallback failed for {jav_code}")
            except Exception as e:
                logging.error(f"❌ Error in JAVmost fallback: {e}")
                javmost_result = None
            
            # If JAVmost failed or had no meaningful data, try JAV Trailers
            if not javmost_result:
                logging.info(f"🔍 Trying JAV Trailers for {jav_code}")
                javtrailers_result = None
                try:
                    javtrailers_result = await self.scrape_javtrailers(jav_code)
                    if javtrailers_result:
                        # Check if JAV Trailers result has meaningful data
                        has_meaningful_data = (javtrailers_result.get('title') and 
                                              javtrailers_result.get('title') != jav_code and
                                              javtrailers_result.get('title') != f"{jav_code} - JAV Content") or \
                                             javtrailers_result.get('cover_url') or \
                                             (javtrailers_result.get('detailed_metadata', {}).get('actress') and 
                                              javtrailers_result.get('detailed_metadata', {}).get('actress').strip() != '') or \
                                             (javtrailers_result.get('detailed_metadata', {}).get('studio') and 
                                              javtrailers_result.get('detailed_metadata', {}).get('studio').strip() != '')
                        
                        if has_meaningful_data:
                            logging.info(f"✅ JAV Trailers fallback successful with meaningful data")
                            results = [javtrailers_result]
                            enabled_sites.append({'name': 'javtrailers', 'enabled': True})
                        else:
                            logging.warning(f"⚠️ JAV Trailers returned data but no meaningful content for {jav_code}")
                            logging.warning(f"⚠️ No actress information found, will try next fallback site")
                            javtrailers_result = None  # Mark as failed for next fallback
                    else:
                        logging.warning(f"⚠️ JAV Trailers fallback failed for {jav_code}")
                except Exception as e:
                    logging.error(f"❌ Error in JAV Trailers fallback: {e}")
                    javtrailers_result = None
                
                # If JAV Trailers also failed, try basic fallback
                if not javtrailers_result:
                    logging.info(f"🔍 Trying basic fallback for {jav_code}")
                    try:
                        fallback_result = await self.scrape_fallback(jav_code)
                        if fallback_result:
                            logging.info(f"✅ Basic fallback successful")
                            results = [fallback_result]
                            enabled_sites.append({'name': 'fallback', 'enabled': True})
                        else:
                            logging.warning(f"⚠️ Basic fallback failed for {jav_code}")
                            # Create basic result as last resort
                            results = [{
                                'title': f"{jav_code} - JAV Content",
                                'cover_url': None,
                                'details': {'Actor': 'Unknown', 'Studio': 'Unknown'},
                                'source': 'basic'
                            }]
                            enabled_sites.append({'name': 'basic', 'enabled': True})
                    except Exception as e:
                        logging.error(f"❌ Error in basic fallback: {e}")
                        # Create basic result as last resort
                        results = [{
                            'title': f"{jav_code} - JAV Content",
                            'cover_url': None,
                            'details': {'Actor': 'Unknown', 'Studio': 'Unknown'},
                            'source': 'basic'
                        }]
                        enabled_sites.append({'name': 'basic', 'enabled': True})
        

        
        # Combine results
        combined_data = {
            'jav_code': jav_code,
            'sources': {},
            'best_title': '',
            'best_cover': '',
            'all_details': {},
            'detailed_metadata': {}  # Add detailed metadata section
        }
        
        for i, result in enumerate(results):
            if isinstance(result, dict) and result:
                site_name = enabled_sites[i]['name']
                combined_data['sources'][site_name] = result
                
                # Use the first available title and cover
                if not combined_data['best_title'] and result.get('title'):
                    combined_data['best_title'] = result['title']
                if not combined_data['best_cover'] and result.get('cover_url'):
                    combined_data['best_cover'] = result['cover_url']
                    
                # Merge details
                combined_data['all_details'].update(result.get('details', {}))
                
                # Include detailed metadata if available
                if result.get('detailed_metadata'):
                    combined_data['detailed_metadata'] = result['detailed_metadata']
        
        # Portrait search hits extra sites. Callers that need a fast lookup can skip it.
        if enhance:
            combined_data = await self.enhance_actress_metadata(combined_data)

        for site_result in combined_data.get('sources', {}).values():
            if isinstance(site_result, dict) and site_result.get('source') and not combined_data.get('source'):
                combined_data['source'] = site_result['source']
        if combined_data.get('best_cover') and not combined_data['detailed_metadata'].get('fanart_url'):
            combined_data['detailed_metadata']['fanart_url'] = combined_data['best_cover']

        for site_result in combined_data.get('sources', {}).values():
            if isinstance(site_result, dict):
                site_result.pop('detail_html', None)

        return combined_data
        
    def create_nfo_file(self, metadata: Dict, output_path: Optional[str] = None, media_server: Optional[str] = None):
        """Create comprehensive NFO file for media servers using metadata.json structure."""
        # Get JAV code from various possible locations
        jav_code = (metadata.get('jav_code') or 
                   metadata.get('detailed_metadata', {}).get('code') or 
                   metadata.get('code', ''))
        
        # Get the best title from various sources
        title = (metadata.get('detailed_metadata', {}).get('full_title') or 
                metadata.get('best_title') or 
                metadata.get('title') or 
                jav_code)
        
        # Get plot from detailed metadata
        plot = (
            metadata.get('detailed_metadata', {}).get('plot')
            or metadata.get('all_details', {}).get('Plot')
            or ''
        )
        if plot_repeats_title(plot, title):
            plot = ''
        
        # Get release date from detailed metadata
        release_date = (metadata.get('detailed_metadata', {}).get('release_date') or 
                       metadata.get('all_details', {}).get('Release Date', ''))
        if not release_date:
            release_date = datetime.now().strftime('%Y-%m-%d')
        
        # Extract year from release date
        year = ''
        if release_date:
            try:
                year = release_date.split('-')[0]
            except:
                year = str(datetime.now().year)
        else:
            year = str(datetime.now().year)
        
        # Get director from detailed metadata
        director = (metadata.get('detailed_metadata', {}).get('director') or 
                   metadata.get('all_details', {}).get('Director', ''))
        
        # Get studio from detailed metadata
        studio = (metadata.get('detailed_metadata', {}).get('studio') or 
                 metadata.get('all_details', {}).get('Studio', ''))
        
        # Get label from detailed metadata
        label = metadata.get('detailed_metadata', {}).get('label', '')
        
        # Get category from detailed metadata
        category = metadata.get('detailed_metadata', {}).get('category', '')
        
        # Get actors (male performers) from detailed metadata
        actors = []
        actor_text = (metadata.get('detailed_metadata', {}).get('actor') or 
                     metadata.get('all_details', {}).get('Actor', ''))
        if actor_text:
            actors = [actor.strip() for actor in actor_text.split(',') if actor.strip()]
        
        # Get actresses (female performers) from detailed metadata
        actresses = []
        actress_text = (metadata.get('detailed_metadata', {}).get('actress') or
                       metadata.get('all_details', {}).get('Actress', ''))
        if actress_text:
            actresses = [actress.strip() for actress in actress_text.split(',') if actress.strip()]

        # Remove duplicates from actresses list while preserving order
        seen_actresses = set()
        unique_actresses = []
        for actress in actresses:
            # Normalize the actress name for duplicate detection (lowercase, strip whitespace)
            normalized_actress = actress.strip().lower()
            if normalized_actress not in seen_actresses:
                seen_actresses.add(normalized_actress)
                unique_actresses.append(actress)  # Keep original case
        actresses = unique_actresses
        
        # Get tags from detailed metadata
        tags = []
        tags_text = metadata.get('detailed_metadata', {}).get('tags', '')
        if tags_text:
            tags = [tag.strip() for tag in tags_text.split(',') if tag.strip()]
        
        # Get genres (combine category and tags)
        genres = []
        if category:
            genres.extend([cat.strip() for cat in category.split(',') if cat.strip()])
        if tags:
            genres.extend(tags)
        if not genres:
            genres = ['Adult', 'JAV']
        
        # Duration lives on the detailed record for jav.guru; older paths used Runtime.
        runtime = str(
            metadata.get('detailed_metadata', {}).get('runtime')
            or metadata.get('detailed_metadata', {}).get('duration')
            or metadata.get('all_details', {}).get('Runtime')
            or '0'
        )
        runtime = ''.join(ch for ch in runtime if ch.isdigit()) or '0'
        
        # A saved trailer.mp4 wins. Otherwise keep the remote preview address.
        detailed_for_art = metadata.get('detailed_metadata') or {}
        trailer = (
            detailed_for_art.get('trailer_file')
            or detailed_for_art.get('trailer_url')
            or metadata.get('all_details', {}).get('Trailer', '')
        )
        profile = artwork_profile(media_server or metadata.get('media_server'))
        actor_mode = profile['actor']
        portrait_thumbs = {}
        for item in detailed_for_art.get('portraits') or []:
            url = item.get('url') or ''
            local_thumb = actor_image_rel(item.get('name', ''))
            # Plex only downloads an actress photo from an https address.
            # Kodi, Jellyfin, and Emby use the file in .actors/.
            if actor_mode in ('url', 'both') and url.startswith('http'):
                portrait_thumbs[actress_name_key(item.get('name', ''))] = url
            elif actor_mode == 'local' and local_thumb:
                portrait_thumbs[actress_name_key(item.get('name', ''))] = local_thumb
            elif item.get('file') and item.get('saved') is not False:
                portrait_thumbs[actress_name_key(item.get('name', ''))] = item['file']
        
        # Get actor thumb URL
        actor_thumb = metadata.get('all_details', {}).get('Actor Thumb', '')
        
        # Get series/set information
        series = (
            metadata.get('detailed_metadata', {}).get('series')
            or metadata.get('all_details', {}).get('Series')
            or ''
        )
        
        # Get source information
        source = metadata.get('source', '')

        def _xml(value):
            return xml_escape(str(value or ''))

        title = _xml(title)
        plot = _xml(plot)
        release_date = _xml(release_date)
        year = _xml(year)
        director = _xml(director)
        studio = _xml(studio)
        label = _xml(label)
        category = _xml(category)
        jav_code = _xml(jav_code)
        runtime = _xml(runtime)
        source = _xml(source)
        series = _xml(series)
        trailer = _xml(trailer)
        actor_thumb = _xml(actor_thumb)
        actors = [_xml(actor) for actor in actors]
        actress_names = list(actresses)
        actresses = [_xml(actress) for actress in actress_names]
        tags = [_xml(tag) for tag in tags]
        genres = [_xml(genre) for genre in genres]

        has_fanart = bool((metadata.get('detailed_metadata') or {}).get('fanart_url'))
        has_poster = has_fanart or bool((metadata.get('detailed_metadata') or {}).get('poster_url'))
        
        nfo_content = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<movie>
    <title>{title}</title>
    <originaltitle>{title}</originaltitle>
    <plot>{plot}</plot>
    <runtime>{runtime}</runtime>
    <mpaa>NC-17</mpaa>
    <uniqueid type="num" default="true">{jav_code}</uniqueid>
    <uniqueid type="jav" default="false">{jav_code}</uniqueid>
    <year>{year}</year>
    <releasedate>{release_date}</releasedate>
    <country>Japan</country>
    <language>Japanese</language>
    <studio>{studio}</studio>
    <label>{label}</label>
    <director>{director}</director>
    <category>{category}</category>
    <tags>{', '.join(tags)}</tags>
    <source>{source}</source>"""
        
        # Add genres
        for genre in genres:
            nfo_content += f"\n    <genre>{genre}</genre>"
        
        # Each actress points at her own portrait file sitting next to movie.nfo.
        for index, (raw_name, actress) in enumerate(zip(actress_names, actresses)):
            nfo_content += f"\n    <actor>"
            nfo_content += f"\n        <name>{actress}</name>"
            nfo_content += f"\n        <role>Female Performer</role>"
            nfo_content += f"\n        <order>{index}</order>"
            portrait_file = portrait_thumbs.get(actress_name_key(raw_name), '')
            if portrait_file:
                nfo_content += f"\n        <thumb>{_xml(portrait_file)}</thumb>"
            nfo_content += f"\n    </actor>"
        
        # Add additional metadata
        if series:
            nfo_content += f"\n    <set>{series}</set>"
        
        if trailer:
            nfo_content += f"\n    <trailer>{trailer}</trailer>"
        
        if actor_thumb:
            nfo_content += f"\n    <actorthumb>{actor_thumb}</actorthumb>"

        rating = (metadata.get('detailed_metadata') or {}).get('rating')
        votes = (metadata.get('detailed_metadata') or {}).get('votes') or 0
        if rating:
            # The plain tag is what Kodi and the old XBMC importer read.
            # Current Plex only draws a star from a named entry in <ratings>.
            nfo_content += f"\n    <rating>{rating}</rating>"
            nfo_content += f"\n    <votes>{int(votes)}</votes>"
            nfo_content += "\n    <ratings>"
            nfo_content += '\n        <rating name="imdb" max="10" default="true">'
            nfo_content += f"\n            <value>{rating}</value>"
            nfo_content += f"\n            <votes>{int(votes)}</votes>"
            nfo_content += "\n        </rating>"
            nfo_content += "\n    </ratings>"

        if has_poster:
            nfo_content += f"\n    <thumb aspect=\"poster\">{profile['posters'][0]}</thumb>"

        if has_fanart:
            nfo_content += f"\n    <fanart>\n        <thumb>{profile['backgrounds'][0]}</thumb>\n    </fanart>"
        
        # Add custom fields for additional metadata
        nfo_content += f"""
    <custominfo>
        <info name="JAV Code">{jav_code}</info>
        <info name="Release Date">{release_date}</info>
        <info name="Category">{category}</info>
        <info name="Director">{director}</info>
        <info name="Studio">{studio}</info>
        <info name="Label">{label}</info>
        <info name="Tags">{', '.join(tags)}</info>
        <info name="Female Performers">{', '.join(actresses)}</info>
        <info name="Source">{source}</info>
        <info name="Plot">{plot}</info>
    </custominfo>
</movie>"""
        
        if not output_path:
            return nfo_content

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(nfo_content)
            logging.info(f"✅ NFO file created: {output_path}")
            return nfo_content
        except Exception as e:
            logging.error(f"❌ Error creating NFO file {output_path}: {e}")
            return False
    

            
    async def download_image(self, url: str, save_path: str):
        """Download image from URL using Playwright to bypass 403 errors and get the actual image file."""
        try:
            logging.info(f"🖼️ Starting image download with Playwright: {url}")
            logging.info(f"💾 Save path: {save_path}")

            # Ensure parent directory exists
            from pathlib import Path
            save_path_obj = Path(save_path)
            save_path_obj.parent.mkdir(parents=True, exist_ok=True)

            image_headers = image_request_headers(url)
            try:
                if self.session is None:
                    self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
                async with self.session.get(url, headers=image_headers) as response:
                    if response.status == 200:
                        image_bytes = await response.read()
                        if image_bytes and len(image_bytes) > 1000:
                            with open(save_path, 'wb') as f:
                                f.write(image_bytes)
                            logging.info(f"Downloaded image over HTTP: {save_path} ({len(image_bytes)} bytes)")
                            return True
            except Exception as http_error:
                logging.warning(f"HTTP image download failed: {http_error}")

            if async_playwright is None or os.environ.get('VERCEL'):
                logging.error(f"Could not download image without a browser: {url}")
                return False

            # The referer should be the detail page where the image is shown
            # Try to guess the referer from the image URL if not provided
            referer = None
            if 'cdn.javsts.com' in url:
                import re
                m = re.search(r'/([a-z0-9]+)pl', url)
                if m:
                    code = m.group(1).upper()
                    referer = f"https://jav.guru/?s={code}"
                else:
                    referer = "https://jav.guru/"
            else:
                referer = "https://jav.guru/"

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                # Set headers to look like a real browser
                await page.set_extra_http_headers({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Referer': referer,
                    'Connection': 'keep-alive',
                })

                logging.info(f"🌐 Navigating to image URL: {url}")
                response = await page.goto(url, wait_until='networkidle', timeout=30000)
                if response and response.status == 200:
                    image_bytes = await response.body()
                    if image_bytes and len(image_bytes) > 1000:
                        with open(save_path, 'wb') as f:
                            f.write(image_bytes)
                        logging.info(f"✅ Successfully downloaded actual image: {save_path} ({len(image_bytes)} bytes)")
                        await browser.close()
                        return True
                    else:
                        logging.error(f"❌ Image data is empty or too small")
                        await browser.close()
                        return False
                else:
                    logging.error(f"❌ Failed to download image: HTTP {response.status if response else 'no response'}")
                    await browser.close()
                    return False
        except Exception as e:
            logging.error(f"❌ Error downloading image with Playwright: {e}")
            return False
            
    def create_poster_from_fanart(self, fanart_path: str, poster_path: str):
        """Create poster.jpg by cropping the right 47.125% of fanart.jpg."""
        try:
            with Image.open(fanart_path) as img:
                width, height = img.size
                
                # Calculate the crop area (right 47.125%)
                crop_width = int(width * 0.47125)
                left = width - crop_width
                
                # Crop the right portion
                cropped_img = img.crop((left, 0, width, height))
                
                # Save as poster
                cropped_img.save(poster_path, 'JPEG', quality=95)
                logging.info(f"Created poster from fanart: {poster_path} ({cropped_img.size[0]}x{cropped_img.size[1]})")
                return True
        except Exception as e:
            logging.error(f"Error creating poster from fanart: {e}")
            return False
            
    async def process_folder(self, folder_path: str) -> List[Dict]:
        """Process all files in a folder and scrape metadata."""
        # Scan for JAV files
        files = self.scan_folder(folder_path)
        logging.info(f"Found {len(files)} JAV files in {folder_path}")
        
        results = []
        for file_info in files:
            jav_code = file_info['jav_code']
            logging.info(f"Processing {jav_code}")
            
            # Scrape metadata
            metadata = await self.scrape_all_sites(jav_code)
            metadata.update(file_info)
            
            # Enhance metadata with actress portraits
            metadata = await self.enhance_actress_metadata(metadata)
            
            # Note: File creation (NFO, fanart, poster) is handled in app.py
            # This method only scrapes metadata and enhances it with actress portraits
            logging.info(f"✅ Metadata processing completed for {jav_code}")
            
            # Save metadata JSON in the original folder for reference
            original_folder = Path(file_info['folder'])
            json_path = original_folder / f"{jav_code}-metadata.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
                
            results.append(metadata)
            
        return results 

    async def search_actress_portrait(self, actress_name: str) -> Optional[str]:
        """
        Search for actress portrait using multiple sources:
        1. javtiful.com (primary)
        2. javmost.com (fallback)
        3. javdatabase.com (final fallback)
        Returns the portrait URL if found.
        """
        try:
            if not actress_name or actress_name.strip() == "":
                logging.info(f"⚠️ No actress name provided for portrait search")
                return None
            
            # Clean actress name for search
            clean_name = actress_name.strip()
            logging.info(f"🎭 ==== ACTRESS PORTRAIT SEARCH START ====")
            logging.info(f"🎭 Actress name: {clean_name}")
            logging.info(f"🎭 Search strategy: javtiful.com → javmost.com → javdatabase.com")
            
            # Try javtiful.com first
            logging.info(f"🎭 ==== TRYING JAVTIFUL.COM ====")
            portrait_url = await self._search_javtiful_portrait(clean_name)
            if portrait_url:
                logging.info(f"✅ Found portrait on javtiful.com: {portrait_url}")
                logging.info(f"🎭 Portrait search completed successfully")
                return portrait_url
            else:
                logging.warning(f"⚠️ No portrait found on javtiful.com")
            
            # Try javmost.com as fallback
            logging.info(f"🎭 ==== TRYING JAVMOST.COM ====")
            portrait_url = await self._search_javmost_portrait(clean_name)
            if portrait_url:
                logging.info(f"✅ Found portrait on javmost.com: {portrait_url}")
                logging.info(f"🎭 Portrait search completed successfully")
                return portrait_url
            else:
                logging.warning(f"⚠️ No portrait found on javmost.com")
            
            # Try javdatabase.com as final fallback
            logging.info(f"🎭 ==== TRYING JAVDATABASE.COM (FINAL FALLBACK) ====")
            portrait_url = await self._search_javdatabase_portrait(clean_name)
            if portrait_url:
                logging.info(f"✅ Found portrait on javdatabase.com: {portrait_url}")
                logging.info(f"🎭 Portrait search completed successfully")
                return portrait_url
            else:
                logging.warning(f"⚠️ No portrait found on javdatabase.com")
            
            logging.warning(f"⚠️ ==== PORTRAIT SEARCH FAILED ====")
            logging.warning(f"⚠️ No actress portrait found for {clean_name} on any source")
            logging.warning(f"⚠️ Tried: javtiful.com, javmost.com, javdatabase.com")
            return None
                
        except Exception as e:
            logging.error(f"❌ ==== PORTRAIT SEARCH ERROR ====")
            logging.error(f"❌ Error searching for actress portrait {actress_name}: {e}")
            logging.error(f"❌ Exception type: {type(e).__name__}")
            return None
    
    async def _search_javtiful_portrait(self, clean_name: str) -> Optional[str]:
        """Search for actress portrait on javtiful.com."""
        try:
            logging.info(f"🔍 Searching javtiful.com for: {clean_name}")
            
            # Construct search URL for javtiful.com
            search_url = f"https://javtiful.com/actresses?q={clean_name.replace(' ', '+')}"
            
            # Fetch search results using Playwright
            html = await self.fetch_html(search_url)
            if not html:
                logging.warning(f"❌ Failed to fetch javtiful search results for {clean_name}")
                return None
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for actress profile links in search results
            actress_links = []
            
            # Pattern 1: Look for links with actress names and extract portrait from profile page
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Check if this looks like an actress profile link
                if ('/actress/' in href or '/actresses/' in href) and clean_name.lower() in text.lower():
                    logging.info(f"🎯 Found potential actress link: {href} ({text})")
                    
                    # Fetch the actress profile page to get the portrait
                    profile_url = href if href.startswith('http') else f"https://javtiful.com{href}"
                    profile_html = await self.fetch_html(profile_url)
                    
                    if profile_html:
                        profile_soup = BeautifulSoup(profile_html, 'html.parser')
                        
                        # Look for portrait image in the profile page
                        portrait_img = profile_soup.find('img', {
                            'src': lambda x: x and any(term in x.lower() for term in ['portrait', 'profile', 'actress', 'avatar', 'thumb'])
                        })
                        
                        if portrait_img and portrait_img.get('src'):
                            portrait_url = portrait_img['src']
                            if not portrait_url.startswith('http'):
                                portrait_url = f"https://javtiful.com{portrait_url}"
                            
                            # Remove query parameters (everything after ?)
                            if '?' in portrait_url:
                                portrait_url = portrait_url.split('?')[0]
                            
                            logging.info(f"🖼️ Found javtiful portrait: {portrait_url}")
                            return portrait_url
            
            # Pattern 2: Look for any image that might be a portrait
            all_images = soup.find_all('img')
            for img in all_images:
                src = img.get('src', '')
                alt = img.get('alt', '')
                
                # Check if this image looks like an actress portrait
                if (clean_name.lower() in alt.lower() or 
                    any(term in src.lower() for term in ['portrait', 'profile', 'actress', 'avatar'])):
                    
                    # Make sure it's a full URL
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = 'https://javtiful.com' + src
                    
                    logging.info(f"🖼️ Found javtiful actress image: {src} ({alt})")
                    return src
            
            logging.warning(f"⚠️ No javtiful portrait found for {clean_name}")
            return None
                
        except Exception as e:
            logging.error(f"❌ Error searching javtiful for {clean_name}: {e}")
            return None
    
    async def _search_javmost_portrait(self, clean_name: str) -> Optional[str]:
        """Search for actress portrait on javmost.com."""
        try:
            logging.info(f"🔍 Searching javmost.com for: {clean_name}")
            
            # Ensure session is available
            if not hasattr(self, 'session') or self.session is None:
                self.session = aiohttp.ClientSession()
            
            # Construct search URL for javmost.com
            search_url = f"https://www5.javmost.com/star/{clean_name.replace(' ', '+')}/"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with self.session.get(search_url, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Look for actress profile links in search results
                    for link in soup.find_all('a', href=True):
                        href = link.get('href', '')
                        text = link.get_text(strip=True)
                        
                        # Check if this looks like an actress profile link
                        if '/star/' in href and clean_name.lower() in text.lower():
                            logging.info(f"🎯 Found potential javmost actress link: {href} ({text})")
                            
                            # Fetch the actress profile page to get the portrait
                            profile_url = href if href.startswith('http') else f"https://www5.javmost.com{href}"
                            profile_html = await self._fetch_profile_page(profile_url, headers)
                            
                            if profile_html:
                                profile_soup = BeautifulSoup(profile_html, 'html.parser')
                                
                                # Look for portrait image in the profile page
                                portrait_img = profile_soup.find('img', {
                                    'src': lambda x: x and any(term in x.lower() for term in ['portrait', 'profile', 'actress', 'avatar', 'thumb'])
                                })
                                
                                if portrait_img and portrait_img.get('src'):
                                    portrait_url = portrait_img['src']
                                    if not portrait_url.startswith('http'):
                                        portrait_url = f"https://www5.javmost.com{portrait_url}"
                                    
                                    # Remove query parameters (everything after ?)
                                    if '?' in portrait_url:
                                        portrait_url = portrait_url.split('?')[0]
                                    
                                    logging.info(f"🖼️ Found javmost portrait: {portrait_url}")
                                    return portrait_url
                                else:
                                    # If no specific portrait found, look for any image
                                    for img in profile_soup.find_all('img', src=True)[:5]:
                                        src = img.get('src', '')
                                        if src and not src.endswith('.webp'):  # Avoid webp for now
                                            if not src.startswith('http'):
                                                src = f"https://www5.javmost.com{src}"
                                            
                                            # Remove query parameters
                                            if '?' in src:
                                                src = src.split('?')[0]
                                            
                                            logging.info(f"🖼️ Found javmost image: {src}")
                                            return src
                else:
                    logging.warning(f"❌ Failed to fetch javmost search results for {clean_name}: {response.status}")
            
            logging.warning(f"⚠️ No javmost portrait found for {clean_name}")
            return None
                
        except Exception as e:
            logging.error(f"❌ Error searching javmost for {clean_name}: {e}")
            return None
    
    async def _search_javdatabase_portrait(self, clean_name: str) -> Optional[str]:
        """Search for actress portrait on javdatabase.com as final fallback."""
        try:
            logging.info(f"🔍 ==== JAVDATABASE PORTRAIT SEARCH ====")
            logging.info(f"🔍 Actress name: {clean_name}")
            
            # Convert actress name to URL slug format
            # Example: "Kana Yume" -> "kana-yume"
            actress_slug = clean_name.lower().replace(' ', '-')
            logging.info(f"🔍 Actress slug: {actress_slug}")
            
            # Construct direct portrait URL using the known pattern
            portrait_url = f"https://www.javdatabase.com/idolimages/thumb/{actress_slug}.webp"
            logging.info(f"🔍 Direct portrait URL: {portrait_url}")
            
            # Check if the portrait exists by making a HEAD request
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'image/webp,image/*,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
            
            # Ensure session is available
            if not hasattr(self, 'session') or self.session is None:
                self.session = aiohttp.ClientSession()
                logging.info(f"🔍 Created new aiohttp session for JAV Database check")
            
            logging.info(f"📡 Checking if portrait exists...")

            async def _real_image(check_url: str) -> bool:
                async with self.session.get(check_url, headers=headers) as response:
                    if response.status != 200:
                        return False
                    kind = (response.headers.get('Content-Type') or '').lower()
                    sample = await response.content.read(16)
                    return kind.startswith('image/') or sample[:3] == b'\xff\xd8\xff' or sample[:4] == b'RIFF'

            if await _real_image(portrait_url):
                logging.info(f"✅ Portrait found at: {portrait_url}")
                return portrait_url
            else:
                    logging.warning(f"⚠️ Portrait not found at: {portrait_url}")
                    
                    # Try alternative slug formats if the first one doesn't work
                    alternative_slugs = [
                        actress_slug.replace('-', ''),  # "kana-yume" -> "kanayume"
                        actress_slug.replace('-', '_'),  # "kana-yume" -> "kana_yume"
                        clean_name.lower().replace(' ', ''),  # "Kana Yume" -> "kanayume"
                    ]
                    
                    for alt_slug in alternative_slugs:
                        alt_portrait_url = f"https://www.javdatabase.com/idolimages/thumb/{alt_slug}.webp"
                        logging.info(f"🔍 Trying alternative URL: {alt_portrait_url}")
                        
                        if await _real_image(alt_portrait_url):
                            logging.info(f"✅ Portrait found at alternative URL: {alt_portrait_url}")
                            return alt_portrait_url
                    
                    logging.warning(f"⚠️ No portrait found for {clean_name} with any slug format")
                    return None
                
        except Exception as e:
            logging.error(f"❌ ==== JAVDATABASE SEARCH ERROR ====")
            logging.error(f"❌ Error searching JAV Database for {clean_name}: {e}")
            logging.error(f"❌ Exception type: {type(e).__name__}")
            return None
    
    async def _fetch_profile_page(self, url: str, headers: dict) -> Optional[str]:
        """Fetch actress profile page."""
        try:
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logging.warning(f"❌ Failed to fetch profile page: {response.status}")
                    return None
        except Exception as e:
            logging.error(f"❌ Error fetching profile page: {e}")
            return None

    def content_id_candidates(self, jav_code: str) -> List[str]:
        """DMM ids pad the number to five digits: SSIS-001 becomes ssis00001."""
        match = re.match(r'^([A-Za-z]+)-?(\d+)$', (jav_code or '').strip())
        if not match:
            return []
        prefix, number = match.group(1).lower(), match.group(2)
        ordered = []
        for item in (f'{prefix}{number.zfill(5)}', f'{prefix}{number.zfill(3)}', f'{prefix}{number}'):
            if item not in ordered:
                ordered.append(item)
        return ordered

    def trailer_slug_from_search(self, html: str, jav_code: str) -> str:
        """Pick the trailer-page id. Some labels prefix it, so FNS-242 is 1fns00242."""
        match = re.match(r'^([A-Za-z]+)-?(\d+)$', (jav_code or '').strip())
        if not html or not match:
            return ''
        prefix, number = match.group(1).lower(), match.group(2)
        exact = {f'{prefix}{number.zfill(5)}', f'{prefix}{number.zfill(3)}', f'{prefix}{number}'}
        slugs = re.findall(r'/video/([a-z0-9]+)', html)
        for slug in slugs:
            if slug in exact:
                return slug
        padded = f'{prefix}{number.zfill(5)}'
        prefixed = [
            slug for slug in slugs
            if slug.endswith(padded) and slug[:-len(padded)].isdigit()
        ]
        if not prefixed:
            return ''
        prefixed.sort(key=len)
        return prefixed[0]

    def portraits_from_trailer_page(self, html: str) -> List[Dict]:
        """Read actress name and portrait URL pairs out of a javtrailers video page."""
        patterns = (
            # Name, then a short run of ids and profile fields, then the portrait.
            # JUR-265 puts the Japanese name before the number; older pages do the reverse.
            re.compile(
                r'"[0-9a-f]{24}","[a-z0-9-]+","\d+","([^"]+)"'
                r'(?:,(?:"[^"]*"|\d+)){0,16},"(https://pics\.dmm\.co\.jp/mono/actjpgs/[^"]+\.jpg)"'
            ),
            re.compile(
                r'"[0-9a-f]{24}","[a-z0-9-]+","\d+","([^"]+)",\d+,"[^"]*"'
                r'(?:,"[^"]*"){0,4},"[0-9a-f]{24}","(https://pics\.dmm\.co\.jp/mono/actjpgs/[^"]+\.jpg)"'
            ),
            re.compile(
                r'"[0-9a-f]{24}","[a-z0-9-]+","\d+","([^"]+)","[^"]*",(?:\d+,)?'
                r'"(https://pics\.dmm\.co\.jp/mono/actjpgs/[^"]+\.jpg)"'
            ),
        )
        found = []
        seen = set()
        for pattern in patterns:
            for name, url in pattern.findall(html):
                cleaned = name.strip()
                if not cleaned or url in seen or 'Jav' in cleaned or 'http' in cleaned:
                    continue
                seen.add(url)
                found.append({
                    'name': cleaned,
                    'url': url,
                    'file': portrait_filename(cleaned),
                })
        return found

    def cast_refs_from_page(self, html: str) -> List[Tuple[str, str]]:
        """Actress slug and English name pairs from a javtrailers video page."""
        found = []
        seen = set()

        def add(slug, name):
            cleaned = re.sub(r'\s+', ' ', re.sub(r'[^\x00-\x7F]+', ' ', name or '')).strip()
            if not slug or slug in seen or 'http' in cleaned or not re.search(r'[A-Za-z]', cleaned):
                return
            seen.add(slug)
            found.append((slug, cleaned))

        record = re.compile(
            r'"([a-z0-9]+(?:-[a-z0-9]+)+)",(?:(?:"[^"]{1,40}",)?"(\d+)","([^"]{2,80})")'
        )
        for slug, _digits, name in record.findall(html or ''):
            add(slug, name)
        cast_line = re.search(r'Cast\(s\):(.{0,2500}?)</p>', html or '', re.S)
        if cast_line:
            for slug, label in re.findall(
                r'href="/casts/([a-z0-9-]+)"[^>]*>\s*([^<]+)',
                cast_line.group(1),
            ):
                add(slug, label)
        return found

    def portrait_url_from_cast_html(self, html: str) -> str:
        """The cast profile names a small webp. Prefer the original DMM jpeg."""
        match = re.search(r'actjpgs/([a-z0-9_]+)\.(?:jpg|w\d+\.webp)', html or '')
        if not match:
            return ''
        jpg = f'https://pics.dmm.co.jp/mono/actjpgs/{match.group(1)}.jpg'
        if remote_image_size(jpg) > 1000:
            return jpg
        webp = re.search(r'https://images\.javtrailers\.com/mono/actjpgs/[^"\\]+\.webp', html or '')
        return webp.group(0) if webp else ''

    async def fill_cast_portraits(self, html: str, aligned: List[Dict], existing: List[str]) -> List[Dict]:
        """Give every named actress her own portrait address."""
        refs = self.cast_refs_from_page(html)
        known = {actress_name_key(item.get('name', '')) for item in aligned}
        for name in existing:
            if actress_name_key(name) not in known:
                aligned.append({
                    'name': name,
                    'url': '',
                    'file': portrait_filename(name),
                })
                known.add(actress_name_key(name))
        for item in aligned:
            if item.get('url'):
                continue
            name = item.get('name') or ''
            slug = next((item_slug for item_slug, item_name in refs if actress_names_match(name, item_name)), '')
            url = ''
            if slug:
                page = await self.fetch_html(f'https://javtrailers.com/casts/{slug}')
                url = self.portrait_url_from_cast_html(page or '')
            if not url:
                url = dmm_portrait_from_name(name)
            if not url:
                logging.info(f"No cast portrait for {name}" + (f" at {slug}" if slug else ''))
                continue
            item['url'] = url
            logging.info(f"Cast portrait for {name}: {url}")
        return aligned

    async def _javtrailers_video_html(self, jav_code: str) -> Optional[Tuple[str, str]]:
        candidates = self.content_id_candidates(jav_code)
        if not candidates:
            return None
        search_html = await self.fetch_html(
            f"https://javtrailers.com/search/{urllib.parse.quote(jav_code)}"
        )
        slug = self.trailer_slug_from_search(search_html or '', jav_code)
        if not slug:
            for candidate in candidates:
                if search_html and f'/video/{candidate}' in search_html:
                    slug = candidate
                    break
        if not slug:
            slug = candidates[0]
        html = await self.fetch_html(f'https://javtrailers.com/video/{slug}')
        useful = ('litevideo', 'm3u8', 'actjpgs', '/casts/', 'pl.w')
        if not html or not any(token in html for token in useful):
            return None
        return html, slug

    async def attach_library_artwork(self, metadata: Dict) -> Dict:
        """Add a downloadable cover, one portrait per actress, and a trailer URL.

        jav.guru's cover CDN refuses server downloads. The trailer site publishes
        the same title's package image, actress portraits, and preview file.
        """
        code = (
            metadata.get('jav_code')
            or (metadata.get('detailed_metadata') or {}).get('code')
            or ''
        )
        detailed = metadata.setdefault('detailed_metadata', {})
        try:
            found_rating = rating_from_javdb(code)
        except Exception as error:
            logging.warning(f"Rating lookup failed for {code}: {error}")
            found_rating = None
        if found_rating:
            score, vote_count, catalog_cover = found_rating
            if score:
                detailed['rating'] = score
                detailed['votes'] = vote_count
                logging.info(f"Rating for {code}: {score} from {vote_count} votes")
            if catalog_cover:
                detailed['catalog_cover'] = catalog_cover

        def use_english_plot():
            scraper = self.config.get('scraper') or {}
            if not scraper.get('translate_description', True):
                return
            if not str(scraper.get('language') or 'en').lower().startswith('en'):
                return
            translated = translate_plot_to_english(detailed.get('plot') or '')
            if not translated or translated == (detailed.get('plot') or ''):
                return
            detailed['plot'] = translated
            metadata.setdefault('all_details', {})['Plot'] = translated
            logging.info(f"English description for {code}: {len(translated)} chars")

        def keep_catalog_cover():
            if detailed.get('fanart_url') or not detailed.get('catalog_cover'):
                return
            detailed['fanart_url'] = detailed['catalog_cover']
            detailed['large_cover_url'] = detailed['catalog_cover']
            metadata['best_cover'] = detailed['catalog_cover']
            logging.info(f"Using catalog cover for {code}")
        try:
            located = await self._javtrailers_video_html(code)
        except Exception as error:
            logging.warning(f"Trailer-page artwork lookup failed for {code}: {error}")
            keep_catalog_cover()
            use_english_plot()
            return metadata
        if not located:
            logging.info(f"No trailer page for {code}")
            keep_catalog_cover()
            use_english_plot()
            return metadata

        html, content_id = located
        current_title = (
            detailed.get('full_title')
            or metadata.get('best_title')
            or metadata.get('title')
            or ''
        )
        if plot_repeats_title(detailed.get('plot') or '', current_title):
            blurb = plot_from_fanza(content_id)
            if blurb:
                detailed['plot'] = blurb
                metadata.setdefault('all_details', {})['Plot'] = blurb
                logging.info(f"Catalog description for {code}: {len(blurb)} chars")
        use_english_plot()
        standard = f'https://pics.dmm.co.jp/digital/video/{content_id}/{content_id}pl.jpg'
        large = f'https://awsimgsrc.dmm.co.jp/pics_dig/digital/video/{content_id}/{content_id}pl.jpg'
        if f'{content_id}pl' in html:
            standard_size = remote_image_size(standard)
            large_size = remote_image_size(large)
            fanart = large if large_size > standard_size else standard
            chosen_size = max(large_size, standard_size)
            if chosen_size <= 1000:
                webp = re.search(
                    rf'https://images\.javtrailers\.com/digital/video/{re.escape(content_id)}/{re.escape(content_id)}pl[^"\'\s]+',
                    html,
                )
                if webp:
                    fanart = webp.group(0)
                    chosen_size = remote_image_size(fanart)
            if chosen_size > 1000:
                detailed['fanart_url'] = fanart
                detailed['large_cover_url'] = fanart
                metadata['best_cover'] = fanart
                # poster.jpg is cropped from this image. The separate ps.jpg is only 147px tall.
                detailed.pop('poster_url', None)
                logging.info(f"Using fanart for {code}: {fanart} ({chosen_size} bytes)")

        preview = preview_from_page(html)
        if preview.get('trailer_url'):
            detailed['trailer_url'] = preview['trailer_url']
            detailed['trailer_segments'] = preview.get('trailer_segments') or []
            metadata.setdefault('all_details', {})['Trailer'] = detailed['trailer_url']
            logging.info(
                f"Found trailer for {code}: {len(detailed['trailer_segments'])} pieces"
                if detailed['trailer_segments'] else f"Found trailer for {code}"
            )

        page_portraits = self.portraits_from_trailer_page(html)
        actress_text = detailed.get('actress') or metadata.get('all_details', {}).get('Actress') or ''
        people = [name.strip() for name in actress_text.split(',') if name.strip()]
        for _slug, ref_name in self.cast_refs_from_page(html):
            if not any(actress_names_match(ref_name, name) for name in people):
                people.append(ref_name)
        unused = list(page_portraits)
        aligned = []
        for name in people:
            hit = next((item for item in unused if actress_names_match(name, item['name'])), None)
            if hit:
                unused.remove(hit)
                aligned.append({
                    'name': name,
                    'url': hit['url'],
                    'file': portrait_filename(name),
                })
            else:
                aligned.append({
                    'name': name,
                    'url': '',
                    'file': portrait_filename(name),
                })
        if len(people) == 1 and len(page_portraits) == 1 and not aligned[0].get('url'):
            aligned[0]['url'] = page_portraits[0]['url']
        elif not people and page_portraits:
            aligned = page_portraits
        aligned = await self.fill_cast_portraits(html, aligned, [item['name'] for item in aligned])
        aligned = [item for item in aligned if item.get('name')]
        detailed['portraits'] = aligned
        if aligned:
            detailed['actress'] = ', '.join(item['name'] for item in aligned)
            metadata.setdefault('all_details', {})['Actress'] = detailed['actress']
        linked = [item for item in aligned if item.get('url')]
        if linked:
            detailed['thumb_url'] = linked[0]['url']
            metadata.setdefault('all_details', {})['Actress Portrait'] = linked[0]['url']
        logging.info(f"Portraits for {code}: {[(item['name'], bool(item.get('url'))) for item in aligned]}")
        keep_catalog_cover()
        return metadata

    async def replace_if_larger(self, url: str, dest: Path, webp: bool = False) -> str:
        """Save url over dest only when dest is missing or the download has more pixels."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        temp = dest.with_name(dest.name + '.audit')
        try:
            if webp:
                saved = await self.download_and_convert_webp_to_jpg(url, str(temp))
            else:
                saved = await self.download_image(url, str(temp))
            if not saved or not temp.exists():
                return 'kept' if dest.exists() else 'failed'
            if not dest.exists() or image_pixels(temp) > image_pixels(dest):
                os.replace(temp, dest)
                return 'replaced'
            return 'kept'
        finally:
            temp.unlink(missing_ok=True)

    async def audit_folder(self, metadata: Dict, output_folder, video_path, download_cover: bool, download_trailer: bool, media_server: str = 'plex') -> List[str]:
        """Refresh artwork and the trailer beside a video. The video file is not opened."""
        notes = []
        stray = remove_stray_audit_copies(video_path)
        if stray:
            notes.append(stray)
        folder = Path(output_folder)
        folder.mkdir(parents=True, exist_ok=True)
        detailed = metadata.setdefault('detailed_metadata', {})
        profile = artwork_profile(media_server)
        if download_cover:
            fanart_url = detailed.get('fanart_url') or metadata.get('best_cover') or ''
            webp = bool(detailed.get('needs_webp_conversion') and detailed.get('webp_url'))
            if webp:
                fanart_url = detailed.get('webp_url')
            backgrounds = profile['backgrounds']
            posters = profile['posters']
            known_backgrounds = ('fanart.jpg', 'background.jpg', 'backdrop.jpg', 'art.jpg')
            known_posters = ('poster.jpg', 'folder.jpg', 'cover.jpg')
            existing = None
            existing_pixels = -1
            for name in known_backgrounds:
                candidate = folder / name
                if not candidate.is_file():
                    continue
                pixels = image_pixels(candidate)
                if pixels > existing_pixels:
                    existing = candidate
                    existing_pixels = pixels
            fanart_path = existing or (folder / backgrounds[0])
            poster_path = next((folder / name for name in posters if (folder / name).is_file()), None)
            if poster_path is None:
                poster_path = next((folder / name for name in known_posters if (folder / name).is_file()), None)
            if poster_path is None:
                poster_path = folder / posters[0]
            fanart_replaced = False
            if fanart_url:
                outcome = await self.replace_if_larger(fanart_url, fanart_path, webp=webp)
                fanart_replaced = outcome == 'replaced'
                if outcome == 'replaced':
                    notes.append('fanart replaced with a higher-resolution image')
                elif outcome == 'kept':
                    notes.append('fanart kept; the current file is already as large')
                else:
                    notes.append('fanart could not be downloaded')
            if fanart_path.exists():
                copy_bytes_as(fanart_path, backgrounds)
                notes.append('background names written for ' + (media_server or 'all'))
            poster_width = image_dimensions(poster_path)[0]
            poster_missing = any(not (folder / name).is_file() for name in posters)
            if fanart_path.exists() and (fanart_replaced or poster_missing or poster_width <= 200):
                if self.create_poster_from_fanart(str(fanart_path), str(poster_path)):
                    copy_bytes_as(poster_path, posters)
                    notes.append('poster rebuilt from fanart')
            if profile['actor'] in ('local', 'both'):
                for item in detailed.get('portraits') or []:
                    portrait_url = item.get('url') or ''
                    portrait_name = actor_image_rel(item.get('name', ''))
                    if not portrait_url or not portrait_name:
                        item['saved'] = False
                        continue
                    portrait_path = folder / portrait_name
                    portrait_path.parent.mkdir(parents=True, exist_ok=True)
                    outcome = await self.replace_if_larger(
                        portrait_url,
                        portrait_path,
                        webp=portrait_url.endswith('.webp'),
                    )
                    item['saved'] = portrait_path.exists()
                    item['file'] = portrait_name
                    if not item['saved']:
                        item['url'] = ''
                        notes.append(f"portrait missing for {item.get('name', '')}")
                    elif outcome == 'replaced':
                        notes.append(f"portrait updated for {item.get('name', '')}")
                    else:
                        notes.append(f"portrait kept for {item.get('name', '')}")
        else:
            for item in detailed.get('portraits') or []:
                item['saved'] = False

        removed = prune_other_artwork(folder, media_server)
        if removed:
            notes.append('removed ' + ', '.join(removed))

        trailer_name = settle_sidecar_trailers(folder)
        if trailer_name:
            detailed['trailer_file'] = trailer_name
            notes.append('trailer is in Trailers/')
        elif download_trailer:
            segments = detailed.get('trailer_segments') or []
            trailer_url = detailed.get('trailer_url') or ''
            saved_name = ''
            if segments:
                saved_name = self.save_hls_preview(segments, folder)
            elif trailer_url:
                trailer_path = folder / 'Trailers' / 'Preview.mp4'
                if await self.download_trailer(trailer_url, str(trailer_path)):
                    saved_name = 'Trailers/Preview.mp4'
            if saved_name:
                detailed['trailer_file'] = saved_name
                notes.append('trailer downloaded')
            else:
                notes.append('no trailer published')
        else:
            notes.append('trailer download is off')

        return notes

    async def download_trailer(self, url: str, save_path: str) -> bool:
        """Save a preview MP4. Refuse anything larger than 1GB."""
        try:
            headers = image_request_headers(url)
            headers['Range'] = 'bytes=0-0'
            if self.session is None:
                self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
            async with self.session.get(url, headers=headers) as probe:
                if probe.status not in (200, 206):
                    logging.warning(f"Trailer probe failed: HTTP {probe.status}")
                    return False
                span = probe.headers.get('Content-Range', '')
                total = 0
                if '/' in span:
                    total = int(span.rsplit('/', 1)[-1] or 0)
                elif probe.headers.get('Content-Length'):
                    total = int(probe.headers['Content-Length'])
                await probe.read()
            if total > TRAILER_MAX_BYTES:
                logging.warning(f"Trailer size {total} is over 1GB for {url}")
                return False
            headers.pop('Range', None)
            dest = Path(save_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            header = b''
            # The shared session timeout is for web pages. A long preview needs longer.
            timeout = aiohttp.ClientTimeout(total=None, sock_read=120)
            async with self.session.get(url, headers=headers, timeout=timeout) as response:
                if response.status != 200:
                    logging.warning(f"Trailer download failed: HTTP {response.status}")
                    return False
                with open(dest, 'wb') as handle:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        if len(header) < 8:
                            header += chunk
                        written += len(chunk)
                        if written > TRAILER_MAX_BYTES:
                            logging.warning(f"Trailer grew past 1GB for {url}")
                            break
                        handle.write(chunk)
            if written > TRAILER_MAX_BYTES or written < 100_000 or header[4:8] != b'ftyp':
                dest.unlink(missing_ok=True)
                logging.warning(f"Trailer payload is not a usable MP4 ({written} bytes)")
                return False
            logging.info(f"Saved trailer {save_path} ({written} bytes)")
            return True
        except Exception as error:
            logging.error(f"Trailer download failed: {error}")
            Path(save_path).unlink(missing_ok=True)
            return False

    def save_hls_preview(self, segments: List[str], output_folder) -> str:
        """Join a streamed preview into one file. ffmpeg wraps it as trailer.mp4."""
        import shutil
        import subprocess
        folder = Path(output_folder) / 'Trailers'
        folder.mkdir(parents=True, exist_ok=True)
        ts_path = folder / 'Preview.ts'
        total = 0
        try:
            with open(ts_path, 'wb') as handle:
                for url in segments:
                    if not _preview_host_ok(url, '.ts'):
                        continue
                    request = urllib.request.Request(url, headers=image_request_headers(url))
                    with urllib.request.urlopen(request, timeout=30) as response:
                        piece = response.read()
                    if not piece or piece[0] != 0x47:
                        logging.warning(f"Preview piece was not video data: {url}")
                        ts_path.unlink(missing_ok=True)
                        return ''
                    handle.write(piece)
                    total += len(piece)
                    if total > TRAILER_MAX_BYTES:
                        logging.warning(f'Preview is larger than 1GB ({total} bytes)')
                        ts_path.unlink(missing_ok=True)
                        return ''
        except Exception as error:
            logging.error(f"Preview download failed: {error}")
            ts_path.unlink(missing_ok=True)
            return ''
        if total < 100_000:
            ts_path.unlink(missing_ok=True)
            return ''
        mp4_path = folder / 'Preview.mp4'
        ffmpeg = shutil.which('ffmpeg')
        if ffmpeg:
            try:
                result = subprocess.run(
                    [ffmpeg, '-y', '-i', str(ts_path), '-c', 'copy', '-movflags', '+faststart', str(mp4_path)],
                    capture_output=True,
                    timeout=600,
                )
                if result.returncode == 0 and mp4_path.exists() and mp4_path.stat().st_size > 100_000:
                    ts_path.unlink(missing_ok=True)
                    logging.info(f"Saved trailer {mp4_path} ({mp4_path.stat().st_size} bytes)")
                    return 'Trailers/Preview.mp4'
            except Exception as error:
                logging.warning(f"Could not wrap the preview as mp4: {error}")
        logging.info(f"Saved trailer {ts_path} ({ts_path.stat().st_size} bytes)")
        return 'Trailers/Preview.ts'

    async def enhance_actress_metadata(self, metadata: Dict) -> Dict:
        """
        Enhance metadata by searching for actress portraits.
        Only attempts portrait search if actress information is found in metadata.
        """
        try:
            # Get actress information from metadata
            actress_name = None
            actress_source = None
            
            # Check different possible fields for actress name
            if metadata.get('detailed_metadata', {}).get('actress'):
                actress_name = metadata['detailed_metadata']['actress'].split(',')[0].strip()
                actress_source = 'detailed_metadata.actress'
            elif metadata.get('detailed_metadata', {}).get('actresses'):
                actress_name = metadata['detailed_metadata']['actresses'].split(',')[0].strip()
                actress_source = 'detailed_metadata.actresses'
            elif metadata.get('all_details', {}).get('Actress'):
                actress_name = metadata['all_details']['Actress'].split(',')[0].strip()
                actress_source = 'all_details.Actress'
            
            if not actress_name:
                logging.info(f"ℹ️ No actress name found in metadata, skipping portrait search")
                logging.info(f"ℹ️ Metadata source: {metadata.get('source', 'unknown')}")
                return metadata
            
            # Clean the actress name to remove Japanese characters
            original_actress_name = actress_name
            actress_name = self.clean_actress_name(actress_name)
            
            if not actress_name:
                logging.warning(f"⚠️ Actress name cleaned to empty: {original_actress_name}")
                return metadata
            
            logging.info(f"🎭 ==== ACTRESS PORTRAIT SEARCH START ====")
            logging.info(f"🎭 Original actress name: {original_actress_name}")
            logging.info(f"🎭 Cleaned actress name: {actress_name}")
            logging.info(f"🎭 Actress source: {actress_source}")
            logging.info(f"🎭 Metadata source: {metadata.get('source', 'unknown')}")
            logging.info(f"🎭 Enhancing metadata for actress: {actress_name}")
            
            # Search for actress portrait
            portrait_url = await self.search_actress_portrait(actress_name)
            
            if portrait_url:
                # Add portrait URL to metadata
                if 'detailed_metadata' not in metadata:
                    metadata['detailed_metadata'] = {}
                
                metadata['detailed_metadata']['thumb_url'] = portrait_url
                logging.info(f"✅ Added actress portrait URL: {portrait_url}")
                
                # Also add to all_details for compatibility
                if 'all_details' not in metadata:
                    metadata['all_details'] = {}
                metadata['all_details']['Actress Portrait'] = portrait_url
            else:
                logging.info(f"ℹ️ No portrait found for {actress_name}")
            
            return metadata
            
        except Exception as e:
            logging.error(f"❌ Error enhancing actress metadata: {e}")
            return metadata 

    async def search_google_for_title(self, jav_code: str) -> Optional[str]:
        """Search Google for the actual title of the JAV."""
        try:
            logging.info(f"🔍 Searching Google for title of {jav_code}")
            
            # Search query
            search_query = f"{jav_code} title"
            encoded_query = urllib.parse.quote(search_query)
            url = f"https://www.google.com/search?q={encoded_query}"
            
            # Headers to avoid blocking
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # Ensure session is initialized
            if not hasattr(self, 'session') or self.session is None:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Look for search results that might contain the actual title
                    # Google search results are typically in h3 tags
                    search_results = soup.find_all('h3')
                    
                    for result in search_results:
                        result_text = result.get_text().strip()
                        # Look for results that contain the JAV code and might have a title
                        if jav_code in result_text and len(result_text) > len(jav_code):
                            # Extract potential title (remove the JAV code and clean up)
                            potential_title = result_text.replace(jav_code, '').strip()
                            if potential_title and len(potential_title) > 3:
                                # Clean up common prefixes/suffixes
                                potential_title = re.sub(r'^[-_\s]+', '', potential_title)
                                potential_title = re.sub(r'[-_\s]+$', '', potential_title)
                                if potential_title:
                                    logging.info(f"✅ Found potential title: {potential_title}")
                                    return potential_title
                    
                    logging.warning(f"⚠️ No suitable title found for {jav_code}")
                    return None
                else:
                    logging.warning(f"⚠️ Google search failed with status {response.status}")
                    return None
                    
        except Exception as e:
            logging.error(f"❌ Error searching Google for {jav_code}: {e}")
            return None

    async def download_and_convert_webp_to_jpg(self, webp_url: str, output_path: str) -> bool:
        """Download webp image and convert to jpg."""
        try:
            logging.info(f"📥 Downloading webp image: {webp_url}")
            
            # Ensure session is initialized
            if not hasattr(self, 'session') or self.session is None:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(webp_url) as response:
                if response.status == 200:
                    # Download the webp image
                    webp_data = await response.read()
                    
                    # Create a temporary file for the webp
                    with tempfile.NamedTemporaryFile(suffix='.webp', delete=False) as temp_webp:
                        temp_webp.write(webp_data)
                        temp_webp_path = temp_webp.name
                    
                    try:
                        # Open and convert to jpg
                        with Image.open(temp_webp_path) as img:
                            # Convert to RGB if necessary
                            if img.mode in ('RGBA', 'LA', 'P'):
                                img = img.convert('RGB')
                            
                            # Save as jpg
                            img.save(output_path, 'JPEG', quality=95)
                        
                        logging.info(f"✅ Successfully converted webp to jpg: {output_path}")
                        return True
                        
                    finally:
                        # Clean up temporary file
                        if os.path.exists(temp_webp_path):
                            os.unlink(temp_webp_path)
                else:
                    logging.error(f"❌ Failed to download webp image: {response.status}")
                    return False
                    
        except Exception as e:
            logging.error(f"❌ Error converting webp to jpg: {e}")
            return False

    async def scrape_javmost(self, jav_code: str) -> Optional[Dict]:
        """Scrape metadata from JAVmost."""
        try:
            logging.info(f"🌐 ==== JAVMOST SCRAPING START ====")
            logging.info(f"🌐 JAV Code: {jav_code}")
            url = f"https://www5.javmost.com/search/{jav_code}/"
            logging.info(f"🌐 Search URL: {url}")
            
            # Ensure session is initialized
            if not hasattr(self, 'session') or self.session is None:
                import aiohttp
                self.session = aiohttp.ClientSession()
                logging.info(f"🌐 Created new aiohttp session")
            
            # Add headers to avoid blocking
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            logging.info(f"🌐 Using headers: {list(headers.keys())}")
            
            logging.info(f"📡 Requesting URL: {url}")
            async with self.session.get(url, headers=headers) as response:
                logging.info(f"📊 Response status: {response.status}")
                logging.info(f"📊 Response headers: {dict(response.headers)}")
                
                if response.status == 200:
                    html = await response.text()
                    logging.info(f"📄 Received HTML length: {len(html)} characters")
                    
                    # Check if HTML contains the JAV code
                    if jav_code in html:
                        logging.info(f"✅ HTML contains JAV code: {jav_code}")
                    else:
                        logging.warning(f"⚠️ HTML does not contain JAV code: {jav_code}")
                    
                    soup = BeautifulSoup(html, 'html.parser')
                    logging.info(f"🔍 Parsed HTML with BeautifulSoup")
                    
                    # Look for search results - JAVmost has specific structure
                    logging.info(f"🔍 ==== SEARCHING FOR RESULTS ====")
                    # Find cards that contain the JAV code
                    results = soup.find_all('div', class_='card')
                    logging.info(f"🔍 Found {len(results)} divs with class 'card'")
                    
                    if not results:
                        logging.info(f"🔍 No 'card' divs found, trying 'result' class")
                        # Try alternative selectors
                        results = soup.find_all('div', class_=lambda x: x and 'result' in x.lower())
                        logging.info(f"🔍 Found {len(results)} divs with 'result' in class")
                    
                    if not results:
                        logging.info(f"🔍 No 'result' divs found, searching for JAV code in text")
                        # Try finding any div that contains the JAV code
                        results = soup.find_all('div', string=lambda text: text and jav_code in text)
                        logging.info(f"🔍 Found {len(results)} divs containing JAV code in text")
                    
                    if not results:
                        logging.info(f"🔍 No specific results found, using entire page")
                        # Last resort: look for any content containing the JAV code
                        results = [soup]  # Use the entire page if no specific results found
                        logging.info(f"🔍 Using entire page as result")
                    
                    if results:
                        logging.info(f"✅ Found {len(results)} results for {jav_code}")
                        
                        # Find the result that matches the exact JAV code
                        exact_match = None
                        logging.info(f"🔍 ==== SEARCHING FOR EXACT MATCH ====")
                        for i, result in enumerate(results):
                            logging.info(f"🔍 Checking result {i+1}/{len(results)}")
                            # Check if this result contains the exact JAV code
                            result_text = result.get_text()
                            if jav_code in result_text:
                                logging.info(f"✅ Result {i+1} contains JAV code")
                                # Check if it's the exact match (not a variant)
                                title_elem = result.find('h1', class_='card-title')
                                if title_elem:
                                    title_text = title_elem.get_text().strip()
                                    logging.info(f"🔍 Found title: '{title_text}'")
                                    if title_text == jav_code:
                                        exact_match = result
                                        logging.info(f"✅ Found exact match in result {i+1}")
                                        break
                                    else:
                                        logging.info(f"⚠️ Title doesn't match JAV code: '{title_text}' != '{jav_code}'")
                                else:
                                    logging.info(f"⚠️ No title element found in result {i+1}")
                            else:
                                logging.info(f"⚠️ Result {i+1} doesn't contain JAV code")
                        
                        # Use exact match if found, otherwise use first result
                        first_result = exact_match if exact_match else results[0]
                        
                        # Extract title from the card title
                        title = f"{jav_code} - JAV Content"
                        title_elem = first_result.find('h1', class_='card-title')
                        if title_elem:
                            title = title_elem.get_text().strip()
                        else:
                            # Fallback to finding any title element
                            title_elem = first_result.find('h2') or first_result.find('h3') or \
                                       first_result.find('a', href=True)
                            if title_elem:
                                title = title_elem.get_text().strip()
                        
                        # If title is same as JAV code, try to get better title from Google
                        if title == jav_code:
                            logging.info(f"🔍 Title is same as JAV code, searching Google for better title")
                            google_title = await self.search_google_for_title(jav_code)
                            if google_title:
                                title = f"{jav_code} - {google_title}"
                                logging.info(f"✅ Enhanced title: {title}")
                        
                        # Extract metadata from the result
                        metadata = {
                            'code': jav_code,
                            'full_title': title,
                            'actress': '',
                            'director': '',
                            'studio': '',
                            'label': '',
                            'release_date': '',
                            'runtime': '',
                            'category': '',
                            'tags': '',
                            'plot': '',
                            'fanart_url': '',
                            'large_cover_url': '',
                            'thumb_url': ''
                        }
                        
                        # Extract actress/star information from the card-text section
                        actress_text = ""
                        card_text = first_result.find('p', class_='card-text')
                        if card_text:
                            # Look for star/actress information
                            star_section = card_text.find('i', class_='fa-female')
                            if star_section:
                                # Get the next sibling that contains the actress name
                                star_parent = star_section.find_parent()
                                if star_parent:
                                    # Find the actress link
                                    actress_link = star_parent.find('a', href=lambda x: x and 'star' in x)
                                    if actress_link:
                                        original_actress_text = actress_link.get_text().strip()
                                        # Clean the actress name to remove Japanese characters
                                        actress_text = self.clean_actress_name(original_actress_text)
                                        logging.info(f"🎭 JAVmost original actress: {original_actress_text}")
                                        logging.info(f"🎭 JAVmost cleaned actress: {actress_text}")
                        
                        metadata['actress'] = actress_text
                        
                        # Extract director from the card-text section
                        director_text = ""
                        if card_text:
                            # Look for director information
                            director_section = card_text.find('i', class_='fa-bullhorn')
                            if director_section:
                                # Get the next sibling that contains the director name
                                director_parent = director_section.find_parent()
                                if director_parent:
                                    # Find the director link
                                    director_link = director_parent.find('a', href=lambda x: x and 'director' in x)
                                    if director_link:
                                        director_text = director_link.get_text().strip()
                        
                        metadata['director'] = director_text
                        
                        # Extract maker/studio from the card-text section
                        studio_text = ""
                        if card_text:
                            # Look for maker information
                            maker_section = card_text.find('i', class_='fa-group')
                            if maker_section:
                                # Get the next sibling that contains the maker name
                                maker_parent = maker_section.find_parent()
                                if maker_parent:
                                    # Find the maker link
                                    maker_link = maker_parent.find('a', href=lambda x: x and 'maker' in x)
                                    if maker_link:
                                        studio_text = maker_link.get_text().strip()
                        
                        metadata['studio'] = studio_text
                        
                        # Extract release date from the card-text section
                        release_date = ""
                        if card_text:
                            # Look for release date
                            release_text = card_text.get_text()
                            import re
                            release_match = re.search(r'Release\s+(\d{4}-\d{2}-\d{2})', release_text)
                            if release_match:
                                release_date = release_match.group(1)
                        
                        metadata['release_date'] = release_date
                        
                        # Extract runtime from the card-text section
                        runtime = ""
                        if card_text:
                            # Look for runtime
                            runtime_text = card_text.get_text()
                            import re
                            runtime_match = re.search(r'Time\s+(\d+)', runtime_text)
                            if runtime_match:
                                runtime = runtime_match.group(1)
                        
                        metadata['runtime'] = runtime
                        
                        # Extract genre/category from the card-text section
                        category_text = ""
                        if card_text:
                            # Look for genre information
                            genre_section = card_text.find('i', class_='ion-ios-videocam')
                            if genre_section:
                                # Get the next sibling that contains the genre names
                                genre_parent = genre_section.find_parent()
                                if genre_parent:
                                    # Find all genre links
                                    genre_links = genre_parent.find_all('a', href=lambda x: x and 'category' in x)
                                    if genre_links:
                                        categories = [link.get_text().strip() for link in genre_links]
                                        category_text = ", ".join(categories)
                        
                        metadata['category'] = category_text
                        
                        # Try to find cover image from the source elements
                        cover_url = ""
                        # Look for source elements with the JAV code in the data-srcset
                        sources = first_result.find_all('source', attrs={'data-srcset': True})
                        for source in sources:
                            srcset = source.get('data-srcset', '')
                            if jav_code in srcset and '.webp' in srcset:
                                # Prefer the exact JAV code match, not variants
                                if jav_code == srcset.split('/')[-1].replace('.webp', ''):
                                    cover_url = srcset
                                    break
                                elif cover_url == "":  # Fallback to any match
                                    cover_url = srcset
                        
                        if cover_url:
                            if cover_url.startswith('//'):
                                cover_url = 'https:' + cover_url
                            elif cover_url.startswith('/'):
                                cover_url = 'https://www5.javmost.com' + cover_url
                            metadata['fanart_url'] = cover_url
                            metadata['large_cover_url'] = cover_url
                            
                            # If it's a webp image, we'll need to download and convert it
                            if cover_url.endswith('.webp'):
                                metadata['needs_webp_conversion'] = True
                                metadata['webp_url'] = cover_url
                        
                        # Try to find detail page link
                        detail_link = first_result.find('a', href=True)
                        if detail_link:
                            detail_url = detail_link.get('href')
                            if detail_url.startswith('/'):
                                detail_url = 'https://www5.javmost.com' + detail_url
                            elif not detail_url.startswith('http'):
                                detail_url = 'https://www5.javmost.com/' + detail_url
                            
                            # Only proceed if this is the exact JAV code detail page
                            if jav_code in detail_url and jav_code == detail_url.split('/')[-2]:
                                logging.info(f"🔗 Detail URL: {detail_url}")
                            
                            # Scrape detail page for more information
                            async with self.session.get(detail_url, headers=headers) as detail_response:
                                if detail_response.status == 200:
                                    detail_html = await detail_response.text()
                                    detail_soup = BeautifulSoup(detail_html, 'html.parser')
                                    
                                    # Extract plot/synopsis
                                    plot_elem = detail_soup.find('div', class_=lambda x: x and 'plot' in x.lower()) or \
                                              detail_soup.find('div', class_=lambda x: x and 'synopsis' in x.lower())
                                    if plot_elem:
                                        plot_text = plot_elem.get_text().strip()
                                        if plot_text:
                                            metadata['plot'] = plot_text
                                    
                                    # Try to find better cover image on detail page
                                    detail_cover = detail_soup.find('img', src=lambda x: x and ('cover' in x.lower() or 'poster' in x.lower()))
                                    if detail_cover:
                                        detail_cover_url = detail_cover.get('src')
                                        if detail_cover_url:
                                            if detail_cover_url.startswith('//'):
                                                detail_cover_url = 'https:' + detail_cover_url
                                            elif detail_cover_url.startswith('/'):
                                                detail_cover_url = 'https://www5.javmost.com' + detail_cover_url
                                            metadata['fanart_url'] = detail_cover_url
                                            metadata['large_cover_url'] = detail_cover_url
                        
                        result = {
                            'title': title,
                            'cover_url': metadata['fanart_url'],
                            'details': {
                                'Actor': metadata['actress'],
                                'Actress': metadata['actress'],
                                'Director': metadata['director'],
                                'Studio': metadata['studio'],
                                'Maker': metadata['studio'],
                                'Release Date': metadata['release_date'],
                                'Runtime': metadata['runtime'],
                                'Genre': metadata['category'],
                                'Category': metadata['category'],
                                'Plot': metadata['plot']
                            },
                            'detailed_metadata': metadata,
                            'source': 'javmost'
                        }
                        
                        logging.info(f"✅ JAVmost scrape completed for {jav_code}")
                        return result
                    else:
                        logging.warning(f"⚠️ No results found on JAVmost for {jav_code}")
                        return None
                else:
                    logging.warning(f"⚠️ JAVmost returned status {response.status} for {jav_code}")
                    return None

        except Exception as e:
            logging.error(f"❌ Error in JAVmost scraper for {jav_code}: {e}")
            return None

    async def scrape_javtrailers(self, jav_code: str) -> Optional[Dict]:
        """Scrape metadata from JavTrailers.com."""
        try:
            logging.info(f"🎬 ==== JAVTRAILERS SCRAPING START ====")
            logging.info(f"🎬 JAV Code: {jav_code}")
            
            # Step 1: Search for the JAV code
            search_url = f"https://javtrailers.com/search/{jav_code}"
            logging.info(f"🔍 Search URL: {search_url}")
            
            search_html = await self.fetch_html(search_url)
            if not search_html:
                logging.warning(f"⚠️ Failed to fetch search page for {jav_code}")
                return None
            
            search_soup = BeautifulSoup(search_html, 'html.parser')
            
            # Look for the first video result that matches our JAV code
            video_links = search_soup.find_all('a', href=True)
            detail_url = None
            
            for link in video_links:
                href = link.get('href', '')
                # Look for video links that contain the JAV code
                if '/video/' in href:
                    # Check if this link contains our JAV code
                    link_text = link.get_text(strip=True)
                    if jav_code.lower() in link_text.lower():
                        detail_url = href if href.startswith('http') else f"https://javtrailers.com{href}"
                        logging.info(f"🎯 Found detail URL: {detail_url}")
                        logging.info(f"🎯 Link text: {link_text}")
                        break
            
            # If not found by text, try to find by URL pattern
            if not detail_url:
                for link in video_links:
                    href = link.get('href', '')
                    if '/video/' in href and jav_code.lower() in href.lower():
                        detail_url = href if href.startswith('http') else f"https://javtrailers.com{href}"
                        logging.info(f"🎯 Found detail URL by URL pattern: {detail_url}")
                        break
            
            if not detail_url:
                logging.warning(f"⚠️ No detail page found for {jav_code}")
                return None
            
            # Step 2: Fetch the detail page
            logging.info(f"📄 Fetching detail page: {detail_url}")
            detail_html = await self.fetch_html(detail_url)
            
            if not detail_html:
                logging.warning(f"⚠️ Failed to fetch detail page for {jav_code}")
                return None
            
            detail_soup = BeautifulSoup(detail_html, 'html.parser')
            
            # Extract metadata from detail page
            metadata = {}
            
            # Extract title
            title_tag = detail_soup.find('h1')
            if title_tag:
                title = title_tag.get_text(strip=True)
                metadata['title'] = title
                logging.info(f"📋 Title: {title}")
            else:
                # Fallback: use JAV code as title
                title = f"{jav_code} - JAV Content"
                metadata['title'] = title
                logging.info(f"📋 Title (fallback): {title}")
            
            # Extract DVD ID and Content ID
            dvd_id = jav_code
            content_id = None
            
            # Look for content ID in the page - try multiple patterns
            content_patterns = [
                r'Content ID:\s*([^\s<]+)',
                r'DVD ID:\s*([^\s<]+)',
                r'ID:\s*([^\s<]+)'
            ]
            for pattern in content_patterns:
                content_match = re.search(pattern, detail_html)
                if content_match:
                    content_id = content_match.group(1)
                    logging.info(f"📋 Content ID: {content_id}")
                    break
            
            # Extract release date - try multiple patterns
            release_date = None
            date_patterns = [
                r'Release Date:\s*(\d+\s+\w+\s+\d+)',
                r'(\d+\s+\w+\s+\d+)\s*$',  # Date at end of line
                r'(\d{1,2}\s+\w+\s+\d{4})'  # General date pattern
            ]
            for pattern in date_patterns:
                date_match = re.search(pattern, detail_html)
                if date_match:
                    release_date = date_match.group(1)
                    logging.info(f"📋 Release Date: {release_date}")
                    break
            
            # Extract duration - try multiple patterns
            duration = None
            duration_patterns = [
                r'Duration:\s*(\d+)\s*mins',
                r'(\d+)\s*mins',
                r'(\d+):(\d+)'  # HH:MM format
            ]
            for pattern in duration_patterns:
                duration_match = re.search(pattern, detail_html)
                if duration_match:
                    if ':' in pattern:
                        hours, minutes = duration_match.groups()
                        duration = str(int(hours) * 60 + int(minutes))
                    else:
                        duration = duration_match.group(1)
                    logging.info(f"📋 Duration: {duration} mins")
                    break
            
            # Extract studio using BeautifulSoup
            studio = None
            studio_span = detail_soup.find('span', string=lambda text: text and 'Studio:' in text)
            if studio_span:
                studio_link = studio_span.find_next('a')
                if studio_link:
                    studio = studio_link.get_text(strip=True)
                    logging.info(f"📋 Studio: {studio}")
            
            # Extract categories using BeautifulSoup
            categories = []
            categories_span = detail_soup.find('span', string=lambda text: text and 'Categories:' in text)
            if categories_span:
                category_links = categories_span.find_next_siblings('a')
                for link in category_links:
                    category_text = link.get_text(strip=True)
                    if category_text:
                        categories.append(category_text)
                logging.info(f"📋 Categories: {categories}")
            
            # Extract cast using BeautifulSoup
            cast = []
            cast_span = detail_soup.find('span', string=lambda text: text and 'Cast(s):' in text)
            if cast_span:
                cast_link = cast_span.find_next('a')
                if cast_link:
                    cast_text = cast_link.get_text(strip=True)
                    # Clean up the cast text using the new cleaning function
                    cleaned_cast_text = self.clean_actress_name(cast_text)
                    if cleaned_cast_text:
                        cast = [cleaned_cast_text]
                        logging.info(f"📋 Original cast text: {cast_text}")
                        logging.info(f"📋 Cleaned cast: {cleaned_cast_text}")
                    else:
                        logging.warning(f"⚠️ Cast text cleaned to empty: {cast_text}")
            
            # Extract series using BeautifulSoup
            series = None
            series_span = detail_soup.find('span', string=lambda text: text and 'Series:' in text)
            if series_span:
                series_link = series_span.find_next('a')
                if series_link:
                    series = series_link.get_text(strip=True)
                    logging.info(f"📋 Series: {series}")
            
            # Extract images from JavTrailers
            fanart_url = None
            poster_url = None
            
            # Look for image URLs in the page
            img_tags = detail_soup.find_all('img')
            for img in img_tags:
                src = img.get('src', '')
                data_src = img.get('data-src', '')
                img_url = data_src if data_src else src
                
                if img_url and 'pics.dmm.co.jp' in img_url:
                    # This is likely a cover/poster image
                    if not poster_url:
                        poster_url = img_url
                        logging.info(f"📋 Poster URL: {poster_url}")
                    elif not fanart_url:
                        fanart_url = img_url
                        logging.info(f"📋 Fanart URL: {fanart_url}")
            
            # If we found a poster but no fanart, use poster as fanart too
            if poster_url and not fanart_url:
                fanart_url = poster_url
                logging.info(f"📋 Using poster as fanart: {fanart_url}")
            
            # Create detailed metadata structure
            detailed_metadata = {
                'dvd_id': dvd_id,
                'content_id': content_id,
                'release_date': release_date,
                'duration': duration,
                'studio': studio,
                'categories': categories,
                'cast': cast,
                'series': series,
                'source': 'javtrailers'
            }
            
            # Add image URLs to detailed metadata
            if poster_url:
                detailed_metadata['poster_url'] = poster_url
            if fanart_url:
                detailed_metadata['fanart_url'] = fanart_url
            
            # Extract actress information
            if cast:
                # Look for female performers (typically Japanese names)
                actresses = []
                for person in cast:
                    # Use the new cleaning function for consistent actress name cleaning
                    clean_name = self.clean_actress_name(person)
                    if clean_name:
                        actresses.append(clean_name)
                        logging.info(f"🎭 Original actress: {person}")
                        logging.info(f"🎭 Cleaned actress: {clean_name}")
                    else:
                        logging.warning(f"⚠️ Actress name cleaned to empty: {person}")
                
                if actresses:
                    detailed_metadata['actress'] = ', '.join(actresses)
                    logging.info(f"🎭 Final actresses list: {actresses}")
                else:
                    logging.warning(f"⚠️ No valid actresses found after cleaning")
            
            # Create result structure
            result = {
                'title': metadata.get('title', f"{jav_code} - JAV Content"),
                'cover_url': poster_url,  # Use poster URL as cover URL
                'detail_url': detail_url,
                'detailed_metadata': detailed_metadata,
                'source': 'javtrailers'
            }
            
            logging.info(f"✅ JavTrailers scrape completed for {jav_code}")
            return result
            
        except Exception as e:
            logging.error(f"❌ Error scraping JavTrailers for {jav_code}: {e}")
            return None