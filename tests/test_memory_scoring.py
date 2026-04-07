"""Tests for Memory Scoring (R11 — utility-based lifecycle)."""

import pytest

from symbiont.memory_scoring import (
    MemoryScore,
    MemoryScorer,
    SESSIONS_BEFORE_PRUNE,
)


class TestMemoryScore:
    def test_new_memory_has_utility(self):
        s = MemoryScore(memory_id="m1")
        assert s.utility > 0.0
        assert not s.should_prune

    def test_utility_decays_per_session(self):
        s = MemoryScore(memory_id="m1")
        u0 = s.utility
        s.sessions_since_access = 3
        assert s.utility < u0

    def test_accessed_memory_has_higher_utility(self):
        s1 = MemoryScore(memory_id="m1", access_count=0, sessions_since_access=2)
        s2 = MemoryScore(memory_id="m2", access_count=5, sessions_since_access=2)
        assert s2.utility > s1.utility

    def test_positive_feedback_boosts_utility(self):
        s = MemoryScore(memory_id="m1", access_count=3, positive_feedback=5, negative_feedback=0)
        u_positive = s.utility
        s2 = MemoryScore(memory_id="m2", access_count=3, positive_feedback=0, negative_feedback=5)
        assert u_positive > s2.utility

    def test_should_prune_after_n_sessions(self):
        s = MemoryScore(memory_id="m1", access_count=0, sessions_since_access=SESSIONS_BEFORE_PRUNE)
        assert s.should_prune

    def test_accessed_memory_never_prune_by_sessions(self):
        s = MemoryScore(memory_id="m1", access_count=1, sessions_since_access=SESSIONS_BEFORE_PRUNE + 10)
        assert not s.should_prune


class TestMemoryScorer:
    def test_register_and_access(self):
        scorer = MemoryScorer()
        scorer.register("m1")
        scorer.record_access("m1")
        assert scorer.get_utility("m1") > 0

    def test_tick_session_ages_all(self):
        scorer = MemoryScorer()
        scorer.register("m1")
        scorer.register("m2")
        for _ in range(SESSIONS_BEFORE_PRUNE):
            scorer.tick_session()
        candidates = scorer.get_prune_candidates()
        assert "m1" in candidates
        assert "m2" in candidates

    def test_accessed_memory_not_pruned(self):
        scorer = MemoryScorer()
        scorer.register("m1")
        scorer.record_access("m1")
        for _ in range(10):
            scorer.tick_session()
        assert "m1" not in scorer.get_prune_candidates()

    def test_feedback(self):
        scorer = MemoryScorer()
        scorer.register("m1")
        scorer.record_access("m1")
        scorer.record_feedback("m1", positive=True)
        scorer.record_feedback("m1", positive=True)
        scorer.record_feedback("m1", positive=False)
        assert scorer.get_utility("m1") > 0.5

    def test_get_top_memories(self):
        scorer = MemoryScorer()
        for i in range(5):
            scorer.register(f"m{i}")
            for _ in range(i):
                scorer.record_access(f"m{i}")
        top = scorer.get_top_memories(3)
        assert len(top) == 3
        assert top[0]["accesses"] >= top[1]["accesses"]

    def test_summary(self):
        scorer = MemoryScorer()
        scorer.register("m1")
        scorer.register("m2")
        s = scorer.summary()
        assert s["total_tracked"] == 2
        assert s["prune_candidates"] == 0

    def test_unknown_memory_utility(self):
        scorer = MemoryScorer()
        assert scorer.get_utility("nonexistent") == 0.0
