from pathlib import Path

from PIL import Image

from hentai_library import (
    _poster_from_cover,
    _save_artwork,
    scrub_show_tree,
)


def _write_rgb(path, size, color):
    Image.new('RGB', size, color).save(path, 'JPEG', quality=95)


def test_poster_is_cropped_from_landscape_cover(tmp_path):
    show = {
        'title': 'Demo',
        'original': 'Demo',
        'romaji': 'Demo',
        'poster_url': '',
        'picture_urls': [],
        'cover_candidates': [],
        '_covers_ready': True,
        'matched': False,
    }
    cover = tmp_path / 'box.jpg'
    _write_rgb(cover, (1600, 900), (20, 40, 60))
    note = _save_artwork(tmp_path, show, 'plex', source_dirs=[tmp_path])
    poster = tmp_path / 'poster.jpg'
    background = tmp_path / 'background.jpg'
    assert background.is_file()
    assert poster.is_file()
    with Image.open(poster) as img:
        width, height = img.size
    assert height > width, (width, height)
    assert poster.read_bytes() != background.read_bytes()
    assert 'cropped' in note


def test_portrait_cover_preferred_over_landscape(tmp_path):
    show = {
        'title': 'Demo',
        'original': 'Demo',
        'romaji': 'Demo',
        'poster_url': '',
        'picture_urls': [],
        'cover_candidates': [],
        '_covers_ready': True,
        'matched': False,
    }
    land = tmp_path / 'wide.jpg'
    port = tmp_path / 'tall.jpg'
    _write_rgb(land, (1600, 900), (10, 10, 10))
    _write_rgb(port, (600, 900), (200, 10, 10))
    _save_artwork(tmp_path, show, 'plex', source_dirs=[tmp_path])
    poster = tmp_path / 'poster.jpg'
    with Image.open(poster) as img:
        width, height = img.size
    assert height > width
    # Portrait bytes should match the tall source, not a crop of the wide one.
    assert poster.read_bytes() == port.read_bytes()


def test_numbered_subtitle_duplicates_removed(tmp_path):
    season = tmp_path / 'Season 01'
    season.mkdir()
    (season / 'Show - s01e01.mkv').write_bytes(b'video')
    (season / 'Show - s01e01.ass').write_text('primary')
    dup = season / 'Show - s01e01(1).ass'
    dup.write_text('copy')
    (tmp_path / '重要申明.txt').write_text('junk')
    removed = scrub_show_tree(tmp_path)
    assert not dup.exists()
    assert not (tmp_path / '重要申明.txt').exists()
    assert (season / 'Show - s01e01.ass').exists()
    assert removed


def test_poster_from_cover_helper(tmp_path):
    cover = tmp_path / 'cover.jpg'
    poster = tmp_path / 'poster.jpg'
    _write_rgb(cover, (2000, 1000), (1, 2, 3))
    assert _poster_from_cover(cover, poster)
    with Image.open(poster) as img:
        width, height = img.size
    assert height == 1000
    assert width == int(2000 * 0.47125)
