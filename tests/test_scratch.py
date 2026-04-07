"""Tests for the Shared Scratchpad (R4 — extended mind)."""

import time

import pytest

from symbiont.scratch import SharedScratchpad, ScratchEntry, SCORE_PRUNE_THRESHOLD


class TestSharedScratchpad:
    def test_write_and_read(self):
        pad = SharedScratchpad(session_id="test")
        entry_id = pad.write("agent:001", "intermediate result", tags=["auth"])
        entries = pad.read()
        assert len(entries) == 1
        assert entries[0].id == entry_id
        assert entries[0].content == "intermediate result"

    def test_read_filters_by_tags(self):
        pad = SharedScratchpad(session_id="test")
        pad.write("a", "auth stuff", tags=["auth"])
        pad.write("b", "db stuff", tags=["database"])
        entries = pad.read(tags=["auth"])
        assert len(entries) == 1
        assert entries[0].content == "auth stuff"

    def test_read_filters_by_min_score(self):
        pad = SharedScratchpad(session_id="test")
        pad.write("a", "good", score=0.9)
        pad.write("b", "bad", score=0.1)
        entries = pad.read(min_score=0.5)
        assert len(entries) == 1
        assert entries[0].content == "good"

    def test_score_entry(self):
        pad = SharedScratchpad(session_id="test")
        eid = pad.write("a", "content")
        assert pad.score_entry(eid, "agent:002", 0.8)
        assert pad.score_entry(eid, "agent:003", 0.6)
        entry = pad._entries[eid]
        assert abs(entry.aggregate_score - 0.7) < 0.01

    def test_score_clamps(self):
        pad = SharedScratchpad(session_id="test")
        eid = pad.write("a", "content")
        pad.score_entry(eid, "x", 1.5)
        assert pad._entries[eid].scores["x"] == 1.0
        pad.score_entry(eid, "y", -0.5)
        assert pad._entries[eid].scores["y"] == 0.0

    def test_score_nonexistent_returns_false(self):
        pad = SharedScratchpad(session_id="test")
        assert not pad.score_entry("fake", "agent", 0.5)

    def test_remove(self):
        pad = SharedScratchpad(session_id="test")
        eid = pad.write("a", "content")
        assert pad.entry_count == 1
        assert pad.remove(eid)
        assert pad.entry_count == 0

    def test_auto_prune_by_ttl(self):
        pad = SharedScratchpad(session_id="test", ttl=0.01)
        pad.write("a", "old content")
        time.sleep(0.02)
        entries = pad.read()  # triggers auto_prune
        assert len(entries) == 0

    def test_auto_prune_by_low_score(self):
        pad = SharedScratchpad(session_id="test", ttl=3600)
        eid = pad.write("a", "low quality")
        pad.score_entry(eid, "scorer1", 0.1)
        pad.score_entry(eid, "scorer2", 0.2)
        entries = pad.read()
        assert len(entries) == 0  # pruned because aggregate < SCORE_PRUNE_THRESHOLD

    def test_no_prune_without_scores(self):
        pad = SharedScratchpad(session_id="test", ttl=3600)
        pad.write("a", "unscored content")
        entries = pad.read()
        assert len(entries) == 1  # not pruned — no scores yet

    def test_read_increments_read_count(self):
        pad = SharedScratchpad(session_id="test")
        eid = pad.write("a", "content")
        pad.read()
        pad.read()
        assert pad._entries[eid].read_count == 2

    def test_clear(self):
        pad = SharedScratchpad(session_id="test")
        pad.write("a", "1")
        pad.write("b", "2")
        pad.clear()
        assert pad.entry_count == 0

    def test_summary(self):
        pad = SharedScratchpad(session_id="test-123")
        pad.write("a", "content")
        s = pad.summary()
        assert s["session_id"] == "test-123"
        assert s["entries"] == 1

    def test_sorted_newest_first(self):
        pad = SharedScratchpad(session_id="test")
        pad.write("a", "first")
        time.sleep(0.01)
        pad.write("b", "second")
        entries = pad.read()
        assert entries[0].content == "second"
        assert entries[1].content == "first"


class TestScratchEntry:
    def test_to_dict(self):
        e = ScratchEntry(id="x", author_id="a", content="data")
        d = e.to_dict()
        assert d["id"] == "x"
        assert d["author_id"] == "a"
        assert "aggregate_score" in d

    def test_age(self):
        e = ScratchEntry(id="x", author_id="a", content="data", created_at=time.time() - 10)
        assert e.age_seconds >= 10
