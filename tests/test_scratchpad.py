"""Tests for the Scratchpad pattern (R6 — disposable reasoning)."""

import pytest

from symbiont.scratchpad import (
    wrap_prompt,
    strip_analysis,
    extract_analysis,
    with_scratchpad,
)


class TestStripAnalysis:
    def test_strips_single_block(self):
        text = "<analysis>thinking here</analysis>\nThe answer is 42."
        assert strip_analysis(text) == "The answer is 42."

    def test_strips_multiline_block(self):
        text = (
            "<analysis>\nStep 1: consider X\nStep 2: evaluate Y\n</analysis>\n"
            "Final answer: X is better."
        )
        assert strip_analysis(text) == "Final answer: X is better."

    def test_strips_multiple_blocks(self):
        text = (
            "<analysis>first thought</analysis>\n"
            "Partial answer.\n"
            "<analysis>second thought</analysis>\n"
            "Final answer."
        )
        result = strip_analysis(text)
        assert "first thought" not in result
        assert "second thought" not in result
        assert "Final answer." in result

    def test_no_analysis_returns_original(self):
        text = "Just a regular response."
        assert strip_analysis(text) == text

    def test_empty_analysis(self):
        text = "<analysis></analysis>Answer."
        assert strip_analysis(text) == "Answer."

    def test_preserves_non_analysis_tags(self):
        text = "<analysis>thinking</analysis>\n<code>print('hi')</code>"
        result = strip_analysis(text)
        assert "<code>print('hi')</code>" in result


class TestExtractAnalysis:
    def test_extracts_blocks(self):
        text = "<analysis>thought 1</analysis>\n<analysis>thought 2</analysis>"
        blocks = extract_analysis(text)
        assert len(blocks) == 2
        assert "thought 1" in blocks[0]
        assert "thought 2" in blocks[1]

    def test_no_blocks(self):
        assert extract_analysis("no analysis here") == []


class TestWrapPrompt:
    def test_adds_scratchpad_instruction(self):
        wrapped = wrap_prompt("What is 2+2?")
        assert "What is 2+2?" in wrapped
        assert "<analysis>" in wrapped
        assert "stripped" in wrapped.lower()


class _MockLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    async def complete(self, prompt, context, model_tier, images=None):
        self.calls.append({"prompt": prompt, "model_tier": model_tier})
        return self.response


@pytest.mark.asyncio
class TestWithScratchpad:
    async def test_strips_analysis_from_response(self):
        llm = _MockLLM(
            "<analysis>Let me think...\nStep 1...\nStep 2...</analysis>\n"
            "The answer is 42."
        )
        result = await with_scratchpad(llm, "What is the answer?")
        assert result == "The answer is 42."

    async def test_passes_model_tier(self):
        llm = _MockLLM("answer")
        await with_scratchpad(llm, "prompt", model_tier="opus")
        assert llm.calls[0]["model_tier"] == "opus"

    async def test_adds_scratchpad_instruction(self):
        llm = _MockLLM("answer")
        await with_scratchpad(llm, "What is 2+2?")
        assert "<analysis>" in llm.calls[0]["prompt"]

    async def test_no_analysis_in_response(self):
        llm = _MockLLM("Just a plain answer.")
        result = await with_scratchpad(llm, "prompt")
        assert result == "Just a plain answer."
