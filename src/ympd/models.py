from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

_FEAT_RE = re.compile(r"[(\[]\s*(?:feat|ft)\.?[^)\]]*[)\]]", re.IGNORECASE)


@dataclass
class Track:
    artist: str
    title: str

    @property
    def query(self) -> str:
        """Поисковый запрос: «(feat. X)» убираем — он мешает, а исполнитель уже в запросе."""
        title = _FEAT_RE.sub("", self.title)
        return f"{self.artist} {title}".strip()


@dataclass
class Candidate:
    username: str
    filename: str
    size: int
    score: int
    free_slot: bool
    queue: int
    speed: int

    @property
    def sort_key(self):
        # лучший рейтинг файла -> свободный слот -> короче очередь -> быстрее аплоад
        return (-self.score, not self.free_slot, self.queue, -self.speed)


@dataclass
class Job:
    """Состояние загрузки одного трека: список вариантов и текущий из них."""

    track: Track
    candidates: list[Candidate]
    idx: int = -1
    status: str = "active"           # active | done | exhausted
    enqueued_at: float = 0.0
    started: bool = False            # видели ли InProgress для текущего кандидата
    last_bytes: int = 0
    last_ts: float = 0.0
    slow_since: Optional[float] = None
    log: list[str] = field(default_factory=list)

    @property
    def current(self) -> Candidate:
        return self.candidates[self.idx]
