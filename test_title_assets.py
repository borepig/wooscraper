"""Titles that already have their sidecars are left alone on a repeat batch."""

from pathlib import Path

from scraper_engine import title_assets_ready


def test_missing_trailer_is_not_finished(tmp_path):
    (tmp_path / 'movie.nfo').write_text('<movie/>', encoding='utf-8')
    (tmp_path / 'poster.jpg').write_bytes(b'x')
    (tmp_path / 'background.jpg').write_bytes(b'x')
    assert title_assets_ready(tmp_path) is False


def test_finished_plex_folder_is_skipped(tmp_path):
    (tmp_path / 'movie.nfo').write_text('<movie/>', encoding='utf-8')
    (tmp_path / 'poster.jpg').write_bytes(b'x')
    (tmp_path / 'background.jpg').write_bytes(b'x')
    extras = tmp_path / 'Trailers'
    extras.mkdir()
    (extras / 'Preview.mp4').write_bytes(b'x')
    assert title_assets_ready(tmp_path, media_server='plex') is True


def test_loose_sidecar_counts_as_a_trailer(tmp_path):
    (tmp_path / 'movie.nfo').write_text('<movie/>', encoding='utf-8')
    (tmp_path / 'poster.jpg').write_bytes(b'x')
    (tmp_path / 'background.jpg').write_bytes(b'x')
    (tmp_path / 'trailer.mp4').write_bytes(b'x')
    assert title_assets_ready(tmp_path) is True


def test_cover_off_ignores_missing_artwork(tmp_path):
    (tmp_path / 'movie.nfo').write_text('<movie/>', encoding='utf-8')
    (tmp_path / 'Trailers').mkdir()
    (tmp_path / 'Trailers' / 'Preview.mp4').write_bytes(b'x')
    assert title_assets_ready(tmp_path, download_cover=False) is True
    assert title_assets_ready(Path(tmp_path), download_trailer=False) is False
