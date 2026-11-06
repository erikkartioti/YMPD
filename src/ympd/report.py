"""Отчёт о треках, которые не удалось скачать."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .models import Job

log = logging.getLogger(__name__)


def save_report(path: Path, not_found: list[dict], jobs: list[Job]) -> None:
    """Пишет JSON: not_found (с причиной) и done. Причины: no_response, no_match, all_failed."""
    items = list(not_found)
    for j in jobs:
        if j.status == "exhausted":
            items.append({"artist": j.track.artist, "title": j.track.title,
                          "query": j.track.query, "reason": "all_failed", "attempts": j.log})
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "not_found": items,
        "done": [j.track.query for j in jobs if j.status == "done"],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Скачано: %d, не найдено: %d -> %s", len(data["done"]), len(items), path)
