"""
Scratchpad Pattern — disposable reasoning scaffold.

Inspired by Claude Code's `<analysis>` scratchpad + strip pattern.
The model reasons inside `<analysis>` tags, which are REMOVED from
the final output. Reasoning improves quality but doesn't occupy
permanent context space.

Analogy: solving an equation on scratch paper and copying only the answer.

Usage:
    result = await with_scratchpad(llm_backend, prompt, model_tier="sonnet")
    # result contains only the final answer, analysis stripped

    # Or manually:
    wrapped = wrap_prompt(prompt)
    raw = await llm.complete(wrapped, ...)
    clean = strip_analysis(raw)
"""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# Pattern to match <analysis>...</analysis> blocks (including multiline)
_ANALYSIS_PATTERN = re.compile(
    r"<analysis>.*?</analysis>",
    re.DOTALL,
)

SCRATCHPAD_INSTRUCTION = """
Before answering, reason step-by-step inside <analysis></analysis> tags.
This scratchpad will be stripped from the final output — use it freely
for working through the problem. Your final answer should appear AFTER
the closing </analysis> tag.
"""


class LLMBackend(Protocol):
    async def complete(self, prompt: str, context: dict, model_tier: str, images: list | None = None) -> str: ...


def wrap_prompt(prompt: str) -> str:
    """Wrap a prompt with scratchpad instructions."""
    return f"{prompt}\n\n{SCRATCHPAD_INSTRUCTION}"


def strip_analysis(text: str) -> str:
    """
    Remove all <analysis>...</analysis> blocks from text.
    Returns the cleaned text with leading/trailing whitespace removed.
    """
    cleaned = _ANALYSIS_PATTERN.sub("", text)
    return cleaned.strip()


def extract_analysis(text: str) -> list[str]:
    """Extract all analysis blocks from text (for debugging/auditing)."""
    return _ANALYSIS_PATTERN.findall(text)


async def with_scratchpad(
    llm_backend: LLMBackend,
    prompt: str,
    context: dict | None = None,
    model_tier: str = "sonnet",
    images: list | None = None,
) -> str:
    """
    Execute an LLM call with scratchpad reasoning.

    The prompt is augmented with scratchpad instructions.
    The response is cleaned to remove analysis blocks.
    Net effect: better quality answers with no context bloat.

    Args:
        llm_backend: The LLM backend to use
        prompt: The prompt to send
        context: Optional context dict
        model_tier: Model tier to use
        images: Optional images for multimodal

    Returns:
        The cleaned response (analysis stripped)
    """
    wrapped = wrap_prompt(prompt)
    raw = await llm_backend.complete(
        prompt=wrapped,
        context=context or {},
        model_tier=model_tier,
        images=images,
    )
    cleaned = strip_analysis(raw)
    analysis_blocks = extract_analysis(raw)

    if analysis_blocks:
        total_analysis_chars = sum(len(b) for b in analysis_blocks)
        logger.debug(
            "scratchpad: stripped %d analysis block(s) (%d chars) from response",
            len(analysis_blocks), total_analysis_chars,
        )

    return cleaned
