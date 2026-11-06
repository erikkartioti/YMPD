import itertools

import pytest

from ympd import downloads
from ympd.config import Settings
from ympd.models import Candidate, Job, Track

SIZE = 40_000_000


class Clock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def sleep(self, s):
        self.now += s


class FakeTransfers:
    """Поведение раздачи задаётся именем пользователя."""

    def __init__(self, clock):
        self.clock, self.t, self.ids = clock, {}, itertools.count(1)

    def enqueue(self, username, files):
        for f in files:
            self.t[(username, f["filename"])] = {
                "id": str(next(self.ids)), "filename": f["filename"],
                "t0": self.clock.now, "requestedAt": str(self.clock.now)}
        return True

    def cancel_download(self, username, id, remove=False):
        self.t = {k: v for k, v in self.t.items() if v["id"] != id}
        return True

    def get_all_downloads(self):
        users = {}
        for (u, _), v in self.t.items():
            age = self.clock.now - v["t0"]
            if u == "rejected":
                st, b = "Completed, Rejected", 0
            elif u == "aborted":
                st, b = "Completed, Aborted", 0
            elif u == "stuck":
                st, b = "Queued, Remotely", 0
            elif u == "slow":
                st, b = ("InProgress", 1000 * age) if age > 3 else ("Requested", 0)
            else:  # "ok": очередь 3 с, затем 2 МБ/с, через 20 с готово
                if age <= 3:
                    st, b = "Queued, Remotely", 0
                elif age < 20:
                    st, b = "InProgress", 2_000_000 * age
                else:
                    st, b = "Completed, Succeeded", SIZE
            f = dict(v, state=st, bytesTransferred=b, percentComplete=b / SIZE * 100)
            users.setdefault(u, {"username": u, "directories": [{"files": []}]})
            users[u]["directories"][0]["files"].append(f)
        return list(users.values())


class FakeSlskd:
    def __init__(self, clock):
        self.transfers = FakeTransfers(clock)


@pytest.fixture
def env(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(downloads.time, "time", clock.time)
    monkeypatch.setattr(downloads.time, "sleep", clock.sleep)
    return FakeSlskd(clock)


def cand(user, i=1):
    return Candidate(user, f"{user}\\song{i}.flac", SIZE, 0, True, 0, 0)


def job(title, *users):
    return Job(Track("A", title), [cand(u) for u in users])


def test_falls_through_rejected_aborted_and_slow_to_working_variant(env):
    j = job("One", "rejected", "aborted", "slow", "ok")
    downloads.monitor(env, [j], Settings())
    assert (j.status, j.idx) == ("done", 3)
    assert [x.split(":")[0] for x in j.log] == ["rejected", "aborted", "slow"]
    assert "медленно" in j.log[2]


def test_stuck_in_queue_switches_after_start_timeout(env):
    j = job("Two", "stuck", "ok")
    downloads.monitor(env, [j], Settings())
    assert (j.status, j.idx) == ("done", 1)
    assert "не началась" in j.log[0]


def test_exhausted_when_all_variants_fail(env):
    j = job("Three", "rejected", "stuck")
    downloads.monitor(env, [j], Settings())
    assert j.status == "exhausted"
    assert len(j.log) == 2


def test_already_downloaded_is_not_enqueued_again(env):
    j = job("Four", "ok")
    c = j.candidates[0]
    env.transfers.t[(c.username, c.filename)] = {
        "id": "x", "filename": c.filename, "t0": -100.0, "requestedAt": "0"}
    downloads.monitor(env, [j], Settings())
    assert j.status == "done" and not j.log


def test_enqueue_ok_handles_new_api_shape():
    assert downloads.enqueue_ok(True)
    assert downloads.enqueue_ok({"enqueued": [{}], "failed": []})
    assert not downloads.enqueue_ok({"enqueued": [], "failed": ["x"]})
    assert not downloads.enqueue_ok(False)
