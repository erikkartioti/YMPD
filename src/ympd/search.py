"""Поиск в slskd и отбор вариантов раздач."""
from __future__ import annotations

import logging
import re
import time

from .config import Settings
from .models import Candidate

log = logging.getLogger(__name__)


def words(s: str) -> list[str]:
    """Нижний регистр, ё -> е, пунктуация -> пробелы."""
    return re.sub(r"[^\w\s]|_", " ", s.lower().replace("ё", "е")).split()


def file_score(f: dict) -> int:
    name = f["filename"].lower()
    toks = set(words(name))
    score = 0
    hires_words = ("24bit", "24 bit", "24-bit", "hi-res")
    if f.get("bitDepth", 16) >= 24 or any(k in name for k in hires_words):
        score += 100
    if toks & {"web", "qobuz", "tidal"}:
        score += 30
    if name.startswith("@@"):
        score -= 20
    if "[cd]" in name or "[flac]" in name:
        score += 10
    if name.endswith(".flac"):
        score += 5
    return score


def build_candidates(query: str, responses: list[dict], cfg: Settings) -> list[Candidate]:
    """Отбирает lossless-файлы, подходящие под запрос, и сортирует их по рейтингу."""
    q = set(words(query))
    banned = {w for w in cfg.exclusions if w not in q}   # «Remix» в названии трека не исключаем
    seen, out = set(), []
    for r in responses:
        if r.get("queueLength", 0) > cfg.max_queue:
            continue
        for f in r.get("files", []):
            name = f["filename"]
            if not name.lower().endswith(cfg.lossless) or f.get("size", 0) < cfg.min_size:
                continue
            toks = set(words(name))
            if toks & banned or not q <= toks:           # все слова запроса — целыми словами
                continue
            key = (r["username"], name)
            if key in seen:
                continue
            seen.add(key)
            out.append(Candidate(
                username=r["username"], filename=name, size=f["size"],
                score=file_score(f), free_slot=bool(r.get("hasFreeUploadSlot")),
                queue=r.get("queueLength", 0), speed=r.get("uploadSpeed", 0),
            ))
    out.sort(key=lambda c: c.sort_key)
    return out[:cfg.max_candidates]


def run_searches(slskd, queries: list[str], cfg: Settings) -> dict[str, str]:
    """Запускает поиски (уже существующие переиспользует) и ждёт их завершения."""
    existing = {s["searchText"]: s["id"] for s in slskd.searches.get_all()}
    ids: dict[str, str] = {}
    for q in queries:
        if q in existing:
            ids[q] = existing[q]
            continue
        ids[q] = slskd.searches.search_text(searchText=q)["id"]
        log.info("Поиск: %s", q)
        time.sleep(1.5)                                  # не заваливаем сеть Soulseek

    pending = set(ids.values())
    deadline = time.time() + cfg.search_wait
    while pending and time.time() < deadline:
        for sid in list(pending):
            if slskd.searches.state(sid).get("isComplete"):
                pending.discard(sid)
        if pending:
            time.sleep(3)
    if pending:
        log.warning("%d поисков не завершились за %s с, берём то, что есть",
                    len(pending), cfg.search_wait)
    return ids
