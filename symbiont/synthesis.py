"""
Synthesis — mandatory context synthesis before delegation.

Inspired by Claude Code's coordinator principle: "Never delegate understanding."
Before a Governor/Major hands off a complex task, the delegator MUST synthesize
context first. This ensures the receiving agent gets a precise, pre-digested
prompt instead of raw context.

Evidence: STEER per-query targeting (F1=0.91) vs generic targeting (F1≈0)
shows that specificity of instruction is the dominant variable in delegation quality.

R3 from the cross-pollination report — the 1/99 element.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from symbiont.types import Caste

logger = logging.getLogger(__name__)

# Complexity threshold: only synthesize for non-trivial tasks
COMPLEXITY_THRESHOLD = 1  # 1 = multi-file or multi-dependency


SYNTHESIS_TEMPLATE = """\
You are synthesizing context for a handoff to a {target_caste} agent.
Your job is NOT to solve the task — it is to PREPARE the next agent to solve it well.

## Task
{task}

## Context Available
{context}

## What the {target_caste} agent needs to know
Synthesize the above into a clear, actionable brief:
1. OBJECTIVE: What exactly needs to be done (1-2 sentences)
2. CONSTRAINTS: What must NOT be done or broken
3. KEY FILES/COMPONENTS: Specific files, functions, or systems involved
4. PRIOR ATTEMPTS: What has been tried and what happened (if any)
5. SUCCESS CRITERIA: How to know the task is complete

Be precise and specific. The quality of this synthesis determines the quality of execution.
"""


class LLMBackend(Protocol):
    """Protocol for LLM backends used in synthesis."""
    async def complete(self, prompt: str, context: dict, model_tier: str, images: list | None = None) -> str: ...


@dataclass
class SynthesisResult:
    """Result of a synthesis operation."""
    synthesized_prompt: str
    original_task: str
    target_caste: Caste
    complexity: int
    was_synthesized: bool  # False if bypassed (trivial task)

    @property
    def prompt(self) -> str:
        """The prompt to pass to the target agent."""
        return self.synthesized_prompt if self.was_synthesized else self.original_task


def estimate_complexity(task: str, context: dict | None = None) -> int:
    """
    Estimate task complexity for synthesis threshold.

    Returns:
        0 = trivial (single action, no dependencies)
        1 = moderate (multiple steps or files)
        2 = complex (cross-cutting, architectural)
    """
    context = context or {}
    score = 0

    task_lower = task.lower()

    # Multi-file indicators
    if any(w in task_lower for w in ("files", "modules", "across", "multiple", "refactor", "migrate")):
        score += 1

    # Dependency indicators
    if any(w in task_lower for w in ("depends", "requires", "integration", "coordinate", "sync")):
        score += 1

    # Architectural indicators
    if any(w in task_lower for w in ("architecture", "design", "redesign", "pattern", "system")):
        score += 1

    # Context richness as complexity signal
    if len(str(context)) > 500:
        score += 1

    # Explicit complexity hints from context
    if context.get("complexity"):
        score = max(score, int(context["complexity"]))

    return min(score, 2)


async def synthesize(
    task: str,
    target_caste: Caste,
    context: dict | None = None,
    llm_backend: LLMBackend | None = None,
    force: bool = False,
) -> SynthesisResult:
    """
    Synthesize context before delegating a task.

    If complexity is below threshold and force=False, bypasses synthesis
    and returns the original task (trivial tasks don't need synthesis overhead).

    Args:
        task: The task description
        target_caste: Which caste will receive the task
        context: Available context dict
        llm_backend: LLM backend for synthesis (uses Governor's tier)
        force: Force synthesis even for trivial tasks

    Returns:
        SynthesisResult with the synthesized (or original) prompt
    """
    context = context or {}
    complexity = estimate_complexity(task, context)

    # Bypass synthesis for trivial tasks (unless forced)
    if complexity < COMPLEXITY_THRESHOLD and not force:
        logger.debug("synthesis: bypassed for trivial task (complexity=%d)", complexity)
        return SynthesisResult(
            synthesized_prompt=task,
            original_task=task,
            target_caste=target_caste,
            complexity=complexity,
            was_synthesized=False,
        )

    # Build synthesis prompt
    prompt = SYNTHESIS_TEMPLATE.format(
        target_caste=target_caste.name,
        task=task,
        context=_format_context(context),
    )

    # Perform synthesis via LLM
    if llm_backend:
        try:
            synthesized = await llm_backend.complete(
                prompt=prompt,
                context={},
                model_tier="opus",  # Synthesis uses highest quality tier
            )
            logger.info(
                "synthesis: completed for %s handoff (complexity=%d, original=%d chars, synthesized=%d chars)",
                target_caste.name, complexity, len(task), len(synthesized),
            )
            return SynthesisResult(
                synthesized_prompt=synthesized,
                original_task=task,
                target_caste=target_caste,
                complexity=complexity,
                was_synthesized=True,
            )
        except Exception as e:
            logger.warning("synthesis: LLM call failed (%s), falling back to original task", e)
            return SynthesisResult(
                synthesized_prompt=task,
                original_task=task,
                target_caste=target_caste,
                complexity=complexity,
                was_synthesized=False,
            )

    # No LLM backend — return original task
    logger.debug("synthesis: no LLM backend, returning original task")
    return SynthesisResult(
        synthesized_prompt=task,
        original_task=task,
        target_caste=target_caste,
        complexity=complexity,
        was_synthesized=False,
    )


def _format_context(context: dict) -> str:
    """Format context dict into readable text for the synthesis prompt."""
    if not context:
        return "(no additional context)"

    parts = []
    for key, value in context.items():
        if key in ("images", "type"):  # Skip non-textual keys
            continue
        parts.append(f"- {key}: {value}")

    return "\n".join(parts) if parts else "(no additional context)"
