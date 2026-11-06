from ympd.config import Settings
from ympd.models import Track
from ympd.search import build_candidates, words

CFG = Settings()
MB = 1_000_000


def resp(user, *files, free=True, queue=0, speed=1_000_000):
    return {"username": user, "hasFreeUploadSlot": free, "queueLength": queue,
            "uploadSpeed": speed,
            "files": [{"filename": f, "size": 30 * MB} for f in files]}


def test_words_normalizes_punctuation_and_yo():
    assert words("Ёлка, Artist_Name (feat. X)") == ["елка", "artist", "name", "feat", "x"]


def test_query_strips_feat():
    assert Track("Artist", "Title (feat. Someone)").query == "Artist Title"
    assert Track("Artist", "Title [ft. Someone]").query == "Artist Title"


def test_matches_whole_words_and_lossless_only():
    q = Track("Artist", "Title").query
    r = [resp("u1", "Music\\Artist\\01 Artist - Title.flac",
              "Music\\Artist\\01 Artist - Title.mp3",
              "Music\\Artist\\02 Artist - Other.flac")]
    got = build_candidates(q, r, CFG)
    assert [c.filename for c in got] == ["Music\\Artist\\01 Artist - Title.flac"]


def test_exclusions_use_whole_words():
    q = Track("Artist", "Title").query
    r = [resp("u1", "Artist - Title (Live).flac", "Artist - Title (Credits).flac")]
    got = build_candidates(q, r, CFG)
    assert [c.filename for c in got] == ["Artist - Title (Credits).flac"]  # credits != edit


def test_exclusion_skipped_when_word_is_in_query():
    q = Track("Artist", "Title (Remix)").query
    r = [resp("u1", "Artist - Title (Remix).flac")]
    assert len(build_candidates(q, r, CFG)) == 1


def test_filters_queue_and_small_files_and_duplicates():
    q = Track("Artist", "Title").query
    r = [
        resp("far", "Artist - Title.flac", queue=CFG.max_queue + 1),
        resp("u1", "Artist - Title.flac", "Artist - Title.flac"),
        {"username": "tiny", "files": [{"filename": "Artist - Title.flac", "size": 1000}]},
    ]
    got = build_candidates(q, r, CFG)
    assert [c.username for c in got] == ["u1"]


def test_sorted_by_score_then_free_slot_then_queue():
    q = Track("Artist", "Title").query
    r = [
        resp("busy", "Artist - Title.flac", free=False, queue=3),
        resp("free", "Artist - Title.flac", free=True),
        resp("hires", "Artist - Title [24bit].flac", free=False, queue=5),
    ]
    got = build_candidates(q, r, CFG)
    assert [c.username for c in got] == ["hires", "free", "busy"]


def test_max_candidates():
    q = Track("Artist", "Title").query
    r = [resp(f"u{i}", "Artist - Title.flac") for i in range(20)]
    assert len(build_candidates(q, r, Settings(max_candidates=3))) == 3
