"""Настройки и загрузка учётных данных из окружения / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import NamedTuple, Optional

from dotenv import find_dotenv, load_dotenv


@dataclass
class Settings:
    """Пороги отбора и мониторинга загрузок. Часть значений переопределяется флагами CLI."""

    lossless: tuple = (".flac", ".wav")
    exclusions: tuple = (
        "mix", "remix", "live", "feat", "mashup", "version", "versions",
        "edition", "edit", "radio",
    )
    min_size: int = 1_000_000        # байт; файлы меньше — скорее всего мусор
    max_queue: int = 5               # раздачи с очередью длиннее отбрасываем
    max_candidates: int = 10         # сколько запасных вариантов держим на трек

    search_wait: float = 90          # сек: сколько ждём завершения всех поисков
    poll_interval: float = 5         # сек между опросами статусов загрузок
    appear_timeout: float = 20       # сек: запись о загрузке должна появиться после enqueue
    start_timeout: float = 150       # сек: не перешла в InProgress — берём следующий вариант
    min_speed: int = 50 * 1024       # байт/с: медленнее считается «очень медленно»
    slow_grace: float = 40           # сек подряд медленнее min_speed -> переключаемся
    near_done: float = 90            # %: выше этого медленную загрузку не обрываем


class Credentials(NamedTuple):
    yandex_token: str
    slskd_host: str
    slskd_api_key: str
    playlist: Optional[str]


def load_credentials() -> Credentials:
    """Читает .env из текущей папки (или выше) и переменные окружения."""
    load_dotenv(find_dotenv(usecwd=True))
    token = os.getenv("YANDEX_TOKEN") or os.getenv("yandex_token")
    api_key = os.getenv("SLSKD_API_KEY")
    if not token:
        raise SystemExit("Не задан YANDEX_TOKEN (см. .env.example)")
    if not api_key:
        raise SystemExit("Не задан SLSKD_API_KEY (см. .env.example)")
    host = os.getenv("SLSKD_HOST", "http://localhost:5030").rstrip("/")
    return Credentials(token, host, api_key, os.getenv("YANDEX_PLAYLIST"))
