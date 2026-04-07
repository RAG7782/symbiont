"""Tests for the Synthesis module (R3 — never delegate understanding)."""

import asyncio

import pytest

from symbiont.synthesis import (
    SynthesisResult,
    estimate_complexity,
    synthesize,
    COMPLEXITY_THRESHOLD,
    SYNTHESIS_TEMPLATE,
)
from symbiont.types import Caste


class TestEstimateComplexity:
    def test_trivial_task(self):
        assert estimate_complexity("fix typo") == 0

    def test_multi_file_task(self):
        assert estimate_complexity("refactor authentication across files") >= 1

    def test_dependency_task(self):
        assert estimate_complexity("implement feature that depends on auth module") >= 1

    def test_architectural_task(self):
        assert estimate_complexity("redesign the system architecture") >= 1

    def test_rich_context_increases_complexity(self):
        big_context = {"details": "x" * 600}
        assert estimate_complexity("simple task", big_context) >= 1

    def test_explicit_complexity_override(self):
        assert estimate_complexity("simple task", {"complexity": 2}) == 2

    def test_capped_at_2(self):
        assert estimate_complexity(
            "refactor and redesign the architecture across multiple files with dependencies"
        ) <= 2


class TestSynthesisResult:
    def test_synthesized_prompt_when_synthesized(self):
        r = SynthesisResult(
            synthesized_prompt="synthesized version",
            original_task="original",
            target_caste=Caste.MEDIA,
            complexity=2,
            was_synthesized=True,
        )
        assert r.prompt == "synthesized version"

    def test_original_prompt_when_not_synthesized(self):
        r = SynthesisResult(
            synthesized_prompt="original",
            original_task="original",
            target_caste=Caste.MEDIA,
            complexity=0,
            was_synthesized=False,
        )
        assert r.prompt == "original"


class _MockLLM:
    """Mock LLM backend for testing."""
    def __init__(self, response: str = "synthesized brief"):
        self.response = response
        self.calls = []

    async def complete(self, prompt: str, context: dict, model_tier: str, images=None) -> str:
        self.calls.append({"prompt": prompt, "model_tier": model_tier})
        return self.response


class _FailingLLM:
    async def complete(self, prompt: str, context: dict, model_tier: str, images=None) -> str:
        raise RuntimeError("LLM unavailable")


@pytest.mark.asyncio
class TestSynthesize:
    async def test_bypasses_trivial_task(self):
        result = await synthesize(
            task="fix typo",
            target_caste=Caste.MEDIA,
        )
        assert not result.was_synthesized
        assert result.prompt == "fix typo"

    async def test_synthesizes_complex_task(self):
        llm = _MockLLM(response="## OBJECTIVE: Refactor auth module...")
        result = await synthesize(
            task="refactor authentication across multiple files",
            target_caste=Caste.MEDIA,
            llm_backend=llm,
        )
        assert result.was_synthesized
        assert result.prompt == "## OBJECTIVE: Refactor auth module..."
        assert len(llm.calls) == 1
        assert llm.calls[0]["model_tier"] == "opus"

    async def test_force_synthesis_on_trivial_task(self):
        llm = _MockLLM(response="forced synthesis")
        result = await synthesize(
            task="fix typo",
            target_caste=Caste.MEDIA,
            llm_backend=llm,
            force=True,
        )
        assert result.was_synthesized

    async def test_falls_back_on_llm_failure(self):
        llm = _FailingLLM()
        result = await synthesize(
            task="refactor multiple modules with dependencies",
            target_caste=Caste.MEDIA,
            llm_backend=llm,
        )
        assert not result.was_synthesized
        assert result.prompt == "refactor multiple modules with dependencies"

    async def test_no_llm_returns_original(self):
        result = await synthesize(
            task="refactor multiple modules with dependencies",
            target_caste=Caste.MEDIA,
            llm_backend=None,
        )
        assert not result.was_synthesized

    async def test_context_included_in_synthesis(self):
        llm = _MockLLM()
        await synthesize(
            task="refactor across files",
            target_caste=Caste.SCOUT,
            context={"files": ["a.py", "b.py"], "approach": "modular"},
            llm_backend=llm,
        )
        prompt = llm.calls[0]["prompt"]
        assert "SCOUT" in prompt
        assert "files" in prompt
        assert "approach" in prompt

    async def test_template_includes_target_caste(self):
        llm = _MockLLM()
        await synthesize(
            task="migrate database across modules",
            target_caste=Caste.MAJOR,
            llm_backend=llm,
        )
        prompt = llm.calls[0]["prompt"]
        assert "MAJOR" in prompt

    async def test_complexity_tracked_in_result(self):
        result = await synthesize(
            task="redesign the system architecture across multiple files",
            target_caste=Caste.MEDIA,
        )
        assert result.complexity >= 1
