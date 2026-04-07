"""Tests for Emergent Specialization (R14 — evolved caste capabilities)."""

import pytest

from symbiont.agent_tolerance import AgentToleranceManager, TrustLevel, TASKS_TO_TRUSTED
from symbiont.deferred_tools import DeferredToolLoader
from symbiont.emergent_specialization import (
    EmergentSpecialization,
    EARN_THRESHOLD,
    MAX_EARNED_TOOLS,
)
from symbiont.types import Caste


def _setup():
    loader = DeferredToolLoader()
    loader.register_tool("edit", "Edit files", "write")
    loader.register_tool("bash", "Run commands", "write")
    loader.register_tool("special", "Special tool", "utility")
    tolerance = AgentToleranceManager()
    return EmergentSpecialization(loader, tolerance), tolerance


class TestEmergentSpecialization:
    def test_caste_default_tools_always_allowed(self):
        spec, tol = _setup()
        tol.register("scout:001", Caste.SCOUT)
        assert spec.request_tool("scout:001", Caste.SCOUT, "read")

    def test_probation_agents_denied_extra_tools(self):
        spec, tol = _setup()
        tol.register("scout:001", Caste.SCOUT)
        assert not spec.request_tool("scout:001", Caste.SCOUT, "edit")

    def test_trusted_agents_can_request_extra_tools(self):
        spec, tol = _setup()
        tol.register("scout:001", Caste.SCOUT)
        for _ in range(TASKS_TO_TRUSTED):
            tol.record_success("scout:001")
        assert spec.request_tool("scout:001", Caste.SCOUT, "edit")

    def test_earn_tool_after_threshold(self):
        spec, tol = _setup()
        tol.register("scout:001", Caste.SCOUT)
        for _ in range(TASKS_TO_TRUSTED):
            tol.record_success("scout:001")
        spec.request_tool("scout:001", Caste.SCOUT, "edit")

        for i in range(EARN_THRESHOLD):
            earned = spec.record_tool_success("scout:001", "edit")
        assert earned  # Should be earned on last call
        assert "edit" in spec.get_earned_tools("scout:001")

    def test_revoke_on_low_success_rate(self):
        spec, tol = _setup()
        tol.register("media:001", Caste.MEDIA)
        for _ in range(TASKS_TO_TRUSTED):
            tol.record_success("media:001")

        # Earn the tool
        for _ in range(EARN_THRESHOLD):
            spec.record_tool_success("media:001", "special")
        assert "special" in spec.get_earned_tools("media:001")

        # Fail enough to revoke
        for _ in range(EARN_THRESHOLD + 2):
            spec.record_tool_failure("media:001", "special")
        assert "special" not in spec.get_earned_tools("media:001")

    def test_max_earned_tools_limit(self):
        spec, tol = _setup()
        tol.register("a", Caste.SCOUT)
        for _ in range(TASKS_TO_TRUSTED):
            tol.record_success("a")

        # Register many tools
        for i in range(MAX_EARNED_TOOLS + 3):
            spec._tool_loader.register_tool(f"tool_{i}", f"Tool {i}", "utility")

        # Request up to limit
        for i in range(MAX_EARNED_TOOLS):
            assert spec.request_tool("a", Caste.SCOUT, f"tool_{i}")
            # Force-add to earned
            spec._earned.setdefault("a", set()).add(f"tool_{i}")

        # Next request should be denied
        assert not spec.request_tool("a", Caste.SCOUT, f"tool_{MAX_EARNED_TOOLS}")

    def test_specialization_profile(self):
        spec, tol = _setup()
        tol.register("a", Caste.MEDIA)
        spec.record_tool_success("a", "edit")
        spec.record_tool_failure("a", "edit")
        profile = spec.get_specialization_profile("a")
        assert profile["agent_id"] == "a"
        assert "edit" in profile["tool_usage"]
        assert profile["tool_usage"]["edit"]["successes"] == 1

    def test_summary(self):
        spec, tol = _setup()
        s = spec.summary()
        assert s["agents_tracked"] == 0
        assert s["total_earned_tools"] == 0
