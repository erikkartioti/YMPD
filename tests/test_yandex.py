from ympd.yandex import parse_playlist_id

UUID = "145932cb-b034-b3e7-8e3b-0af57fa46230"


def test_parse_plain_uuid():
    assert parse_playlist_id(UUID) == UUID


def test_parse_url():
    assert parse_playlist_id(f"https://music.yandex.ru/playlists/{UUID}?utm=x") == UUID
    assert parse_playlist_id(f" https://music.yandex.ru/playlists/{UUID}/ ") == UUID
