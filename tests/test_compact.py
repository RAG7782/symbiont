"""Tests for Partial Compact (R7 — adaptive context compression)."""

import pytest

from symbiont.compact import (
    partial_compact,
    build_handoff_context,
    HandoffContext,
    CompactResult,
    DEFAULT_PRESERVE_COUNT,
    _fallback_summary,
)


def _make_messages(n: int) -> list[dict]:
    return [{"role": "agent", "content": f"message {i}"} for i in range(n)]


class _MockLLM:
    def __init__(self, response="Summary of history."):
        self.response = response
        self.calls = []

    async def complete(self, prompt, context, model_tier, images=None):
        self.calls.append({"model_tier": model_tier})
        return self.response


class _FailingLLM:
    async def complete(self, prompt, context, model_tier, images=None):
        raise RuntimeError("LLM down")


@pytest.mark.asyncio
class TestPartialCompact:
    async def test_no_compact_needed(self):
        msgs = _make_messages(3)
        result = await partial_compact(msgs, preserve_count=5)
        assert result.compacted_count == 0
        assert result.preserved_count == 3
        assert len(result.preserved) == 3

    async def test_partial_compact_with_llm(self):
        msgs = _make_messages(10)
        llm = _MockLLM("Compressed history of 5 messages.")
        result = await partial_compact(msgs, preserve_count=5, llm_backend=llm)
        assert result.compacted_count == 5
        assert result.preserved_count == 5
        assert result.summary == "Compressed history of 5 messages."
        assert len(llm.calls) == 1
        assert llm.calls[0]["model_tier"] == "haiku"

    async def test_fallback_on_llm_failure(self):
        msgs = _make_messages(10)
        llm = _FailingLLM()
        result = await partial_compact(msgs, preserve_count=5, llm_backend=llm)
        assert result.compacted_count == 5
        assert "History" in result.summary

    async def test_no_llm_uses_fallback(self):
        msgs = _make_messages(8)
        result = await partial_compact(msgs, preserve_count=3, llm_backend=None)
        assert result.compacted_count == 5
        assert "History" in result.summary

    async def test_preserved_are_most_recent(self):
        msgs = _make_messages(10)
        result = await partial_compact(msgs, preserve_count=3)
        assert result.preserved[0]["content"] == "message 7"
        assert result.preserved[-1]["content"] == "message 9"

    async def test_empty_messages(self):
        result = await partial_compact([], preserve_count=5)
        assert result.preserved_count == 0
        assert result.compacted_count == 0


class TestHandoffContext:
    def test_to_prompt(self):
        ctx = HandoffContext(
            summary="History summary here",
            recent_messages=[{"role": "worker", "content": "did the thing"}],
            source_caste="MAJOR",
            target_caste="MEDIA",
            task="implement feature X",
        )
        prompt = ctx.to_prompt()
        assert "MAJOR" in prompt
        assert "MEDIA" in prompt
        assert "History summary here" in prompt
        assert "did the thing" in prompt

    def test_to_prompt_no_recent(self):
        ctx = HandoffContext(
            summary="summary",
            recent_messages=[],
            source_caste="SCOUT",
            target_caste="MEDIA",
            task="explore",
        )
        prompt = ctx.to_prompt()
        assert "Recent Context" not in prompt


class TestBuildHandoffContext:
    def test_builds_from_compact_result(self):
        cr = CompactResult(
            summary="compressed",
            preserved=[{"role": "a", "content": "recent"}],
            original_count=10,
            compacted_count=9,
            preserved_count=1,
        )
        ctx = build_handoff_context(cr, "MAJOR", "MEDIA", "task X")
        assert ctx.summary == "compressed"
        assert ctx.source_caste == "MAJOR"
        assert len(ctx.recent_messages) == 1


class TestFallbackSummary:
    def test_empty(self):
        assert _fallback_summary([]) == "(empty history)"

    def test_includes_key_events(self):
        msgs = [
            {"content": "started work"},
            {"content": "encountered error in auth"},
            {"content": "decision: use JWT"},
            {"content": "finished"},
        ]
        summary = _fallback_summary(msgs)
        assert "error" in summary.lower() or "auth" in summary
        assert "decision" in summary.lower() or "JWT" in summary
