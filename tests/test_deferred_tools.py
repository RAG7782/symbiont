"""Tests for Deferred Tool Loading (R9 — caste-specific tool visibility)."""

import pytest

from symbiont.deferred_tools import (
    DeferredToolLoader,
    CASTE_TOOL_PROFILES,
)
from symbiont.types import Caste


class TestDeferredToolLoader:
    def test_scout_only_sees_read_tools(self):
        loader = DeferredToolLoader()
        tools = loader.get_visible_tools(Caste.SCOUT)
        assert "read" in tools
        assert "grep" in tools
        assert "edit" not in tools
        assert "write" not in tools
        assert "bash" not in tools

    def test_media_sees_write_tools(self):
        tools = DeferredToolLoader().get_visible_tools(Caste.MEDIA)
        assert "edit" in tools
        assert "write" in tools
        assert "bash" in tools

    def test_major_sees_coordination_tools(self):
        tools = DeferredToolLoader().get_visible_tools(Caste.MAJOR)
        assert "plan" in tools
        assert "decide" in tools
        assert "bash" not in tools

    def test_queen_sees_lifecycle_tools(self):
        tools = DeferredToolLoader().get_visible_tools(Caste.QUEEN)
        assert "spawn" in tools
        assert "hibernate" in tools
        assert "edit" not in tools

    def test_minima_sees_utility_tools(self):
        tools = DeferredToolLoader().get_visible_tools(Caste.MINIMA)
        assert "format" in tools
        assert "edit" not in tools
        assert "plan" not in tools

    def test_request_tool_loads_for_agent(self):
        loader = DeferredToolLoader()
        loader.register_tool("special_tool", "A special tool", "utility")
        assert loader.request_tool("scout:001", Caste.SCOUT, "special_tool")
        assert "special_tool" in loader.get_loaded_tools("scout:001")

    def test_request_unknown_tool_fails(self):
        loader = DeferredToolLoader()
        assert not loader.request_tool("agent:001", Caste.MEDIA, "nonexistent")

    def test_build_tool_prompt(self):
        loader = DeferredToolLoader()
        loader.register_tool("read", "Read files", "read")
        loader.register_tool("grep", "Search content", "read")
        prompt = loader.build_tool_prompt(Caste.SCOUT)
        assert "read" in prompt.lower()
        assert "Available Tools" in prompt

    def test_build_tool_prompt_includes_loaded(self):
        loader = DeferredToolLoader()
        loader.register_tool("extra", "Extra tool", "utility")
        loader.request_tool("scout:001", Caste.SCOUT, "extra")
        prompt = loader.build_tool_prompt(Caste.SCOUT, agent_id="scout:001")
        assert "extra" in prompt.lower()

    def test_is_visible(self):
        loader = DeferredToolLoader()
        assert loader.is_visible("read", Caste.SCOUT)
        assert not loader.is_visible("edit", Caste.SCOUT)
        assert loader.is_visible("edit", Caste.MEDIA)

    def test_summary(self):
        loader = DeferredToolLoader()
        s = loader.summary()
        assert "profiles" in s
        assert s["profiles"]["SCOUT"] == len(CASTE_TOOL_PROFILES[Caste.SCOUT])

    def test_all_castes_have_profiles(self):
        for caste in Caste:
            assert caste in CASTE_TOOL_PROFILES, f"Missing profile for {caste.name}"

    def test_profiles_dont_overlap_excessively(self):
        scout = CASTE_TOOL_PROFILES[Caste.SCOUT]
        queen = CASTE_TOOL_PROFILES[Caste.QUEEN]
        # Scout and Queen should have minimal overlap
        overlap = scout & queen
        assert len(overlap) == 0, f"Unexpected overlap: {overlap}"
