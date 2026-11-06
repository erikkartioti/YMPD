"""Постановка в очередь и мониторинг загрузок с переключением на запасные варианты."""
from __future__ import annotations

import logging
import time

from .config import Settings
from .models import Job

log = logging.getLogger(__name__)

Snapshot = dict  # (username, filename) -> запись о загрузке из slskd


def snapshot(slskd) -> Snapshot:
    """Самая свежая запись о загрузке по каждому (username, filename). Один API-вызов."""
    snap: Snapshot = {}
    for user in slskd.transfers.get_all_downloads():
        for d in user.get("directories", []):
            for f in d.get("files", []):
                key = (user["username"], f["filename"])
                if key not in snap or f.get("requestedAt", "") > snap[key].get("requestedAt", ""):
                    snap[key] = f
    return snap


def enqueue_ok(res) -> bool:
    if res is False or res is None:
        return False
    if isinstance(res, dict) and res.get("failed"):     # новые версии slskd: {enqueued, failed}
        return False
    return True


def start_next(slskd, job: Job, snap: Snapshot) -> bool:
    """Ставит в очередь следующего кандидата. False — варианты закончились или трек уже скачан."""
    while True:
        job.idx += 1
        if job.idx >= len(job.candidates):
            job.status = "exhausted"
            log.warning("%s: варианты закончились", job.track.query)
            return False
        c = job.current
        job.started, job.slow_since, job.last_bytes = False, None, 0
        job.enqueued_at = job.last_ts = time.time()

        old = snap.get((c.username, c.filename))
        if old:
            state = old["state"]
            if state == "Completed, Succeeded":         # файл уже скачан в прошлый запуск
                job.status = "done"
                log.info("%s: уже скачан (%s)", job.track.query, c.username)
                return False
            if not state.startswith("Completed"):       # уже в очереди или качается: следим
                return True
            try:                                        # старая неудачная запись мешала бы статусам
                slskd.transfers.cancel_download(c.username, old["id"], remove=True)
            except Exception:
                log.debug("не удалось удалить старую запись", exc_info=True)
        try:
            res = slskd.transfers.enqueue(
                username=c.username, files=[{"filename": c.filename, "size": c.size}])
        except Exception as e:
            job.log.append(f"{c.username}: enqueue: {e}")
            continue
        if not enqueue_ok(res):
            job.log.append(f"{c.username}: enqueue отклонён")
            continue
        log.info("%s: вариант %d/%d (%s)", job.track.query, job.idx + 1,
                 len(job.candidates), c.username)
        return True


def fail_current(slskd, job: Job, snap: Snapshot, reason: str) -> None:
    c = job.current
    job.log.append(f"{c.username}: {reason}")
    log.info("%s: %s, %s; следующий вариант", job.track.query, c.username, reason)
    tr = snap.get((c.username, c.filename))
    if tr:
        try:
            slskd.transfers.cancel_download(c.username, tr["id"], remove=True)
        except Exception as e:
            log.warning("не удалось отменить загрузку: %s", e)
    start_next(slskd, job, snap)


def step(slskd, job: Job, snap: Snapshot, now: float, cfg: Settings) -> None:
    """Один шаг для трека: проверяет статус текущего варианта и при необходимости меняет его."""
    c = job.current
    tr = snap.get((c.username, c.filename))
    if tr is None:
        if now - job.enqueued_at > cfg.appear_timeout:
            fail_current(slskd, job, snap, "загрузка не появилась в slskd")
        return

    state = tr["state"]
    if state == "Completed, Succeeded":
        job.status = "done"
        log.info("%s: скачан (%s)", job.track.query, c.username)
        return
    if state.startswith("Completed"):
        # Rejected / Aborted / Errored / TimedOut / Cancelled
        fail_current(slskd, job, snap, state.split(", ", 1)[-1])
        return

    if "InProgress" in state:
        done = tr.get("bytesTransferred", 0)
        if not job.started:                             # первый замер: скорость пока не считаем
            job.started, job.last_bytes, job.last_ts, job.slow_since = True, done, now, None
            return
        speed = (done - job.last_bytes) / max(now - job.last_ts, 1e-6)
        job.last_bytes, job.last_ts = done, now
        if speed < cfg.min_speed and tr.get("percentComplete", 0) < cfg.near_done:
            if job.slow_since is None:
                job.slow_since = now
            elif now - job.slow_since >= cfg.slow_grace:
                fail_current(slskd, job, snap, f"медленно ({speed / 1024:.0f} КБ/с)")
        else:
            job.slow_since = None
        return

    # Requested / Queued, Remotely / Queued, Locally / Initializing
    if now - job.enqueued_at > cfg.start_timeout:
        fail_current(slskd, job, snap, f"не началась за {cfg.start_timeout:g} с ({state})")


def monitor(slskd, jobs: list[Job], cfg: Settings) -> None:
    """Запускает первые варианты и следит за всеми загрузками, пока они не закончатся."""
    snap = snapshot(slskd)
    for job in jobs:
        start_next(slskd, job, snap)
    active = [j for j in jobs if j.status == "active"]
    while active:
        time.sleep(cfg.poll_interval)
        try:
            snap = snapshot(slskd)
        except Exception as e:                          # временный сбой API: пробуем ещё раз
            log.warning("slskd не ответил: %s", e)
            continue
        now = time.time()
        for job in active:
            step(slskd, job, snap, now, cfg)
        active = [j for j in active if j.status == "active"]
