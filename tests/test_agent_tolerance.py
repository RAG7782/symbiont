"""Tests for Agent Tolerance (R12 — internal trust zones)."""

import pytest

from symbiont.agent_tolerance import (
    AgentToleranceManager,
    TrustLevel,
    TASKS_TO_TRUSTED,
    TASKS_TO_AUTONOMOUS,
    ERRORS_TO_PROBATION,
    ERRORS_TO_SUPPRESSED,
)
from symbiont.types import Caste


class TestAgentToleranceManager:
    def test_new_agent_starts_on_probation(self):
        mgr = AgentToleranceManager()
        profile = mgr.register("scout:001", Caste.SCOUT)
        assert profile.trust_level == TrustLevel.PROBATION
        assert mgr.requires_validation("scout:001")

    def test_promote_to_trusted(self):
        mgr = AgentToleranceManager()
        mgr.register("media:001", Caste.MEDIA)
        for _ in range(TASKS_TO_TRUSTED):
            mgr.record_success("media:001")
        assert mgr.get_trust_level("media:001") == TrustLevel.TRUSTED

    def test_promote_to_autonomous(self):
        mgr = AgentToleranceManager()
        mgr.register("media:001", Caste.MEDIA)
        for _ in range(TASKS_TO_AUTONOMOUS):
            mgr.record_success("media:001")
        assert mgr.get_trust_level("media:001") == TrustLevel.AUTONOMOUS
        assert not mgr.requires_validation("media:001")

    def test_demote_on_failures(self):
        mgr = AgentToleranceManager()
        mgr.register("media:001", Caste.MEDIA)
        # Promote first
        for _ in range(TASKS_TO_AUTONOMOUS):
            mgr.record_success("media:001")
        assert mgr.get_trust_level("media:001") == TrustLevel.AUTONOMOUS
        # Demote
        for _ in range(ERRORS_TO_PROBATION):
            mgr.record_failure("media:001")
        assert mgr.get_trust_level("media:001") == TrustLevel.TRUSTED

    def test_suppress_on_many_failures(self):
        mgr = AgentToleranceManager()
        mgr.register("scout:001", Caste.SCOUT)
        for _ in range(ERRORS_TO_SUPPRESSED):
            mgr.record_failure("scout:001")
        assert mgr.get_trust_level("scout:001") == TrustLevel.SUPPRESSED
        assert "scout:001" in mgr.get_suppressed()

    def test_recover_from_suppression(self):
        mgr = AgentToleranceManager()
        mgr.register("scout:001", Caste.SCOUT)
        for _ in range(ERRORS_TO_SUPPRESSED):
            mgr.record_failure("scout:001")
        assert mgr.get_trust_level("scout:001") == TrustLevel.SUPPRESSED
        for _ in range(TASKS_TO_TRUSTED):
            mgr.record_success("scout:001")
        assert mgr.get_trust_level("scout:001") == TrustLevel.PROBATION

    def test_success_resets_consecutive_failures(self):
        mgr = AgentToleranceManager()
        mgr.register("a", Caste.MEDIA)
        mgr.record_failure("a")
        mgr.record_success("a")
        p = mgr.get_profile("a")
        assert p.consecutive_failures == 0
        assert p.consecutive_successes == 1

    def test_unknown_agent(self):
        mgr = AgentToleranceManager()
        assert mgr.get_trust_level("unknown") == TrustLevel.PROBATION
        assert mgr.requires_validation("unknown")
        assert mgr.record_success("unknown") is None

    def test_summary(self):
        mgr = AgentToleranceManager()
        mgr.register("a", Caste.SCOUT)
        mgr.register("b", Caste.MEDIA)
        for _ in range(TASKS_TO_TRUSTED):
            mgr.record_success("b")
        s = mgr.summary()
        assert s["total_agents"] == 2
        assert s["by_level"]["probation"] == 1
        assert s["by_level"]["trusted"] == 1

    def test_autonomous_requires_high_success_rate(self):
        mgr = AgentToleranceManager()
        mgr.register("a", Caste.MEDIA)
        # 8 successes + 2 failures = 80% rate (below 90% threshold)
        for _ in range(8):
            mgr.record_success("a")
        for _ in range(2):
            mgr.record_failure("a")
        # Even with 10+ tasks, shouldn't promote to AUTONOMOUS at 80%
        for _ in range(2):
            mgr.record_success("a")
        assert mgr.get_trust_level("a") != TrustLevel.AUTONOMOUS
