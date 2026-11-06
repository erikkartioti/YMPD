"""Командная строка: ympd --playlist <uuid|ссылка> [опции]."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import slskd_api

from . import __version__
from .config import Settings, load_credentials
from .downloads import monitor
from .models import Job
from .report import save_report
from .search import build_candidates, run_searches
from .yandex import load_tracks

log = logging.getLogger("ympd")


def build_parser() -> argparse.ArgumentParser:
    d = Settings()
    p = argparse.ArgumentParser(
        prog="ympd",
        description="Скачивает плейлист Яндекс Музыки в lossless через Soulseek (slskd).")
    p.add_argument("--playlist", help="UUID или ссылка на плейлист (или YANDEX_PLAYLIST в .env)")
    p.add_argument("--report", type=Path, default=Path("not_found.json"),
                   help="куда сохранить отчёт (по умолчанию: %(default)s)")
    p.add_argument("--dry-run", action="store_true",
                   help="только поиск и отбор вариантов, без загрузки")
    p.add_argument("--max-queue", type=int, default=d.max_queue,
                   help="максимальная очередь у раздающего (по умолчанию: %(default)s)")
    p.add_argument("--max-candidates", type=int, default=d.max_candidates,
                   help="запасных вариантов на трек (по умолчанию: %(default)s)")
    p.add_argument("--start-timeout", type=float, default=d.start_timeout,
                   help="сек до переключения, если не началась (по умолчанию: %(default)s)")
    p.add_argument("--min-speed", type=int, default=d.min_speed // 1024,
                   help="КБ/с: медленнее считается слишком медленной (по умолчанию: %(default)s)")
    p.add_argument("--slow-grace", type=float, default=d.slow_grace,
                   help="сек медленной загрузки до переключения (по умолчанию: %(default)s)")
    p.add_argument("-v", "--verbose", action="store_true", help="подробные логи")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    creds = load_credentials()
    playlist = args.playlist or creds.playlist
    if not playlist:
        raise SystemExit("Укажите плейлист: --playlist или YANDEX_PLAYLIST в .env")

    cfg = Settings(max_queue=args.max_queue, max_candidates=args.max_candidates,
                   start_timeout=args.start_timeout, min_speed=args.min_speed * 1024,
                   slow_grace=args.slow_grace)

    tracks = load_tracks(creds.yandex_token, playlist)
    log.info("Треков в плейлисте: %d", len(tracks))
    slskd = slskd_api.SlskdClient(host=creds.slskd_host, api_key=creds.slskd_api_key)
    ids = run_searches(slskd, [t.query for t in tracks], cfg)

    jobs: list[Job] = []
    not_found: list[dict] = []
    for t in tracks:
        sid = ids[t.query]
        if slskd.searches.state(sid).get("responseCount", 0) == 0:
            reason, cands = "no_response", []
        else:
            reason = "no_match"
            cands = build_candidates(t.query, slskd.searches.search_responses(sid), cfg)
        if cands:
            jobs.append(Job(track=t, candidates=cands))
        else:
            not_found.append({"artist": t.artist, "title": t.title,
                              "query": t.query, "reason": reason})
    log.info("К загрузке: %d, без результата: %d", len(jobs), len(not_found))

    if args.dry_run:
        for j in jobs:
            c = j.candidates[0]
            log.info("%s -> %s: %s (вариантов: %d)", j.track.query, c.username,
                     c.filename, len(j.candidates))
        return

    try:
        monitor(slskd, jobs, cfg)
    except KeyboardInterrupt:
        log.warning("Прервано, сохраняю отчёт")
    finally:
        save_report(args.report, not_found, jobs)


if __name__ == "__main__":
    main()
