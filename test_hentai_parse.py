from hentai_library import parse_release


def test_plex_year_is_not_part_of_title():
    parsed = parse_release('Slave Nurses (2003)', 'Slave Nurses (2003)')
    assert parsed['title'] == 'Slave Nurses'


def test_release_name_still_keeps_real_title():
    parsed = parse_release(
        'folder',
        '(18禁アニメ) (無修正) [バニラ] 爆乳姉妹 (DVD 960x720 x264 AAC).mkv',
    )
    assert '爆乳姉妹' in parsed['title']
    assert parsed['studio'] == 'バニラ'
