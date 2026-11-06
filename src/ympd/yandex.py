"""Чтение плейлиста Яндекс Музыки."""
from __future__ import annotations

from .models import Track


def parse_playlist_id(value: str) -> str:
    """Принимает UUID или ссылку вида https://music.yandex.ru/playlists/<uuid>?..."""
    value = value.strip().split("?")[0].split("#")[0]
    return value.rstrip("/").rsplit("/", 1)[-1]


def load_tracks(token: str, playlist: str) -> list[Track]:
    from yandex_music import Client  # ленивый импорт: тестам не нужны сеть и библиотека

    client = Client(token).init()
    tracks, seen = [], set()
    for short in client.playlist(parse_playlist_id(playlist)).fetch_tracks():
        t = short.track
        if t is None or not t.artists:
            continue
        track = Track(t.artists[0].name, t.title)   # первый исполнитель: больше совпадений
        if track.query not in seen:
            seen.add(track.query)
            tracks.append(track)
    return tracks
