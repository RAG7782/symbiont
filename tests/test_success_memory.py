"""Tests for Success Memory (R13 — positive pattern capture)."""

import pytest

from symbiont.success_memory import SuccessMemory, SuccessRecord


class TestSuccessRecord:
    def test_matches_keywords(self):
        rec = SuccessRecord(
            id="s1", approach="Used JWT refresh tokens for auth",
            outcome="Zero failures", tags=["auth"],
        )
        assert rec.matches("JWT auth tokens") > 0
        assert rec.matches("completely unrelated query") == 0

    def test_matches_tags(self):
        rec = SuccessRecord(
            id="s1", approach="approach", outcome="outcome",
            tags=["database", "optimization"],
        )
        assert rec.matches("database") > 0


class TestSuccessMemory:
    def test_record_and_recall(self):
        sm = SuccessMemory()
        sm.record("Used async batch processing", outcome="3x throughput", tags=["performance"])
        results = sm.recall("async processing performance")
        assert len(results) >= 1
        assert results[0].approach == "Used async batch processing"

    def test_recall_increments_reuse(self):
        sm = SuccessMemory()
        sm.record("pattern X", outcome="good", tags=["test"])
        sm.recall("pattern X")
        sm.recall("pattern X")
        assert sm.most_reused(1)[0].reuse_count == 2

    def test_recall_min_score_filters(self):
        sm = SuccessMemory()
        sm.record("very specific approach", outcome="ok")
        results = sm.recall("completely different topic", min_score=0.5)
        assert len(results) == 0

    def test_get_by_tags(self):
        sm = SuccessMemory()
        sm.record("a1", outcome="o1", tags=["auth", "jwt"])
        sm.record("a2", outcome="o2", tags=["database"])
        sm.record("a3", outcome="o3", tags=["auth", "oauth"])
        results = sm.get_by_tags(["auth"])
        assert len(results) == 2

    def test_most_reused(self):
        sm = SuccessMemory()
        sm.record("JWT auth tokens", outcome="o1", tags=["auth"])
        sm.record("batch database queries", outcome="o2", tags=["database"])
        # Reuse database pattern more
        sm.recall("database queries")
        sm.recall("database queries")
        top = sm.most_reused(1)
        assert top[0].approach == "batch database queries"

    def test_summary(self):
        sm = SuccessMemory()
        sm.record("a", outcome="o", confidence=0.9)
        sm.record("b", outcome="o", confidence=0.7)
        s = sm.summary()
        assert s["total_records"] == 2
        assert s["avg_confidence"] == 0.8

    def test_empty_summary(self):
        sm = SuccessMemory()
        s = sm.summary()
        assert s["total_records"] == 0
        assert s["avg_confidence"] == 0.0
