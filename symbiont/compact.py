"""
Partial Compact — adaptive context compression for handoffs.

Inspired by Claude Code's partial compact pattern: preserve recent
messages verbatim and compact only the prefix. The receiving agent
gets full context for recent work + high-level summary of history.

This enables asymmetric handoffs where the next agent has:
- Complete detail for the last N interactions
- Compressed overview of everything before that

Biological analogy: working memory (recent, detailed) + episodic
memory (older, compressed to key events).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# Default: preserve last 5 messages verbatim
DEFAULT_PRESERVE_COUNT = 5

COMPACT_TEMPLATE = """\
Summarize the following interaction history into a concise context brief.
Preserve:
1. Key decisions made and their rationale
2. Errors encountered and how they were resolved
3. Important state changes or artifacts created
4. Constraints and requirements discovered

Do NOT include:
- Routine acknowledgements or status updates
- Duplicate information
- Low-priority details

History to summarize:
{history}

Provide a structured summary in under 500 words.
"""


class LLMBackend(Protocol):
    async def complete(self, prompt: str, context: dict, model_tier: str, images: list | None = None) -> str: ...


@dataclass
class CompactResult:
    """Result of a partial compaction."""
    summary: str  # Compressed prefix
    preserved: list[dict]  # Recent messages kept verbatim
    original_count: int  # Total messages before compact
    compacted_count: int  # Messages that were compressed
    preserved_count: int  # Messages kept verbatim


@dataclass
class HandoffContext:
    """
    Context package for inter-caste handoffs.
    Combines compact summary + preserved recent messages.
    """
    summary: str
    recent_messages: list[dict]
    source_caste: str
    target_caste: str
    task: str
    metadata: dict = field(default_factory=dict)

    def to_prompt(self) -> str:
        """Format the handoff context as a prompt for the receiving agent."""
        parts = [
            f"## Handoff from {self.source_caste} → {self.target_caste}",
            f"\n### Task: {self.task}",
            f"\n### History Summary:\n{self.summary}",
        ]
        if self.recent_messages:
            parts.append("\n### Recent Context (verbatim):")
            for msg in self.recent_messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                parts.append(f"  [{role}]: {content}")

        return "\n".join(parts)


async def partial_compact(
    messages: list[dict],
    preserve_count: int = DEFAULT_PRESERVE_COUNT,
    llm_backend: LLMBackend | None = None,
) -> CompactResult:
    """
    Partially compact a message history.

    Preserves the last `preserve_count` messages verbatim.
    Compacts everything before that into a summary.

    Args:
        messages: Full message history (list of dicts with role/content)
        preserve_count: Number of recent messages to preserve
        llm_backend: LLM backend for generating summary

    Returns:
        CompactResult with summary + preserved messages
    """
    if len(messages) <= preserve_count:
        # Nothing to compact — all messages fit in the preserve window
        return CompactResult(
            summary="(no history to summarize — all context preserved)",
            preserved=messages,
            original_count=len(messages),
            compacted_count=0,
            preserved_count=len(messages),
        )

    # Split: prefix (to compact) + suffix (to preserve)
    split_point = len(messages) - preserve_count
    to_compact = messages[:split_point]
    to_preserve = messages[split_point:]

    # Generate summary of the prefix
    if llm_backend:
        history_text = "\n".join(
            f"[{m.get('role', '?')}]: {m.get('content', '')}"
            for m in to_compact
        )
        prompt = COMPACT_TEMPLATE.format(history=history_text)
        try:
            summary = await llm_backend.complete(
                prompt=prompt,
                context={},
                model_tier="haiku",  # Use cheapest tier for compaction
            )
        except Exception as e:
            logger.warning("compact: LLM summary failed (%s), using fallback", e)
            summary = _fallback_summary(to_compact)
    else:
        summary = _fallback_summary(to_compact)

    logger.info(
        "compact: %d messages → summary (%d chars) + %d preserved",
        len(messages), len(summary), len(to_preserve),
    )

    return CompactResult(
        summary=summary,
        preserved=to_preserve,
        original_count=len(messages),
        compacted_count=len(to_compact),
        preserved_count=len(to_preserve),
    )


def build_handoff_context(
    compact_result: CompactResult,
    source_caste: str,
    target_caste: str,
    task: str,
    metadata: dict | None = None,
) -> HandoffContext:
    """Build a HandoffContext from a CompactResult."""
    return HandoffContext(
        summary=compact_result.summary,
        recent_messages=compact_result.preserved,
        source_caste=source_caste,
        target_caste=target_caste,
        task=task,
        metadata=metadata or {},
    )


def _fallback_summary(messages: list[dict]) -> str:
    """Generate a simple summary without LLM (fallback)."""
    if not messages:
        return "(empty history)"

    # Extract key events: first, last, and any with "error" or "decision"
    key_msgs = []
    key_msgs.append(f"Started with: {messages[0].get('content', '')[:100]}")

    for m in messages:
        content = m.get("content", "").lower()
        if any(w in content for w in ("error", "fail", "decision", "chose", "approved")):
            key_msgs.append(f"  - {m.get('content', '')[:150]}")

    key_msgs.append(f"Last action: {messages[-1].get('content', '')[:100]}")

    return f"History ({len(messages)} messages):\n" + "\n".join(key_msgs)
