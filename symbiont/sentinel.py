"""
@Sentinel — anti-hallucination auditor for compact summaries.

Inspired by AGORA Intelligence's @Sentinel pattern. Audits
compact summaries against original content to detect information
loss, hallucination, or distortion.

Classification levels:
- OK: Summary accurately represents the original
- NORMA_OK: Summary is directionally correct but lacks precision
- ALUCINACAO: Summary contains fabricated or contradictory information

When ALUCINACAO is detected, triggers re-compaction.
Uses the scratchpad pattern (R6) to keep audit reasoning out of final context.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from symbiont.scratchpad import with_scratchpad, strip_analysis

logger = logging.getLogger(__name__)


class AuditLevel(Enum):
    OK = "ok"
    NORMA_OK = "norma_ok"
    ALUCINACAO = "alucinacao"


@dataclass
class AuditResult:
    """Result of a Sentinel audit."""
    level: AuditLevel
    reasoning: str  # Audit reasoning (stripped from analysis)
    issues: list[str]  # Specific issues found
    recommendation: str  # "accept", "accept_with_caveats", "re_compact"


AUDIT_TEMPLATE = """\
You are @Sentinel, an anti-hallucination auditor. Your job is to verify
that a compact summary accurately represents the original content.

## Original Content ({original_length} chars):
{original}

## Summary to Audit ({summary_length} chars):
{summary}

## Audit Criteria:
1. COMPLETENESS: Are all key decisions, errors, and state changes preserved?
2. ACCURACY: Does the summary correctly represent what happened?
3. NO FABRICATION: Does the summary contain information NOT in the original?
4. NO CONTRADICTION: Does the summary contradict anything in the original?

## Classification:
- OK: Accurate and complete
- NORMA_OK: Directionally correct but missing some precision
- ALUCINACAO: Contains fabricated or contradictory information

Respond in this exact format:
LEVEL: [OK|NORMA_OK|ALUCINACAO]
ISSUES: [list each issue on its own line, or "none"]
RECOMMENDATION: [accept|accept_with_caveats|re_compact]
REASONING: [brief explanation]
"""


class LLMBackend(Protocol):
    async def complete(self, prompt: str, context: dict, model_tier: str, images: list | None = None) -> str: ...


async def audit_summary(
    original: str,
    summary: str,
    llm_backend: LLMBackend | None = None,
) -> AuditResult:
    """
    Audit a compact summary against the original content.

    Uses @Sentinel classification (OK / NORMA_OK / ALUCINACAO).
    If LLM is available, uses scratchpad pattern for reasoning.
    Falls back to heuristic checks without LLM.
    """
    if llm_backend:
        return await _llm_audit(original, summary, llm_backend)
    return _heuristic_audit(original, summary)


async def _llm_audit(
    original: str,
    summary: str,
    llm_backend: LLMBackend,
) -> AuditResult:
    """LLM-powered audit using scratchpad pattern."""
    prompt = AUDIT_TEMPLATE.format(
        original=original[:3000],  # Cap to avoid token explosion
        summary=summary,
        original_length=len(original),
        summary_length=len(summary),
    )

    try:
        response = await with_scratchpad(llm_backend, prompt, model_tier="sonnet")
        return _parse_audit_response(response)
    except Exception as e:
        logger.warning("sentinel: LLM audit failed (%s), using heuristics", e)
        return _heuristic_audit(original, summary)


def _heuristic_audit(original: str, summary: str) -> AuditResult:
    """
    Heuristic audit without LLM.
    Checks for obvious issues: empty summary, extreme compression, keyword loss.
    """
    issues = []

    # Empty or near-empty summary
    if len(summary.strip()) < 20:
        issues.append("Summary is too short (< 20 chars)")
        return AuditResult(
            level=AuditLevel.ALUCINACAO,
            reasoning="Summary is effectively empty",
            issues=issues,
            recommendation="re_compact",
        )

    # Extreme compression ratio
    if len(original) > 100 and len(summary) / len(original) < 0.02:
        issues.append(f"Extreme compression ratio ({len(summary)}/{len(original)} = {len(summary)/len(original):.3f})")

    # Check for key signal words in original that should appear in summary
    signal_words = ["error", "fail", "decision", "chose", "approved", "rejected", "blocked", "critical"]
    original_lower = original.lower()
    summary_lower = summary.lower()

    missing_signals = []
    for word in signal_words:
        if word in original_lower and word not in summary_lower:
            missing_signals.append(word)

    if missing_signals:
        issues.append(f"Key signals missing from summary: {missing_signals}")

    # Determine level
    if not issues:
        level = AuditLevel.OK
        recommendation = "accept"
    elif len(issues) == 1 and not missing_signals:
        level = AuditLevel.NORMA_OK
        recommendation = "accept_with_caveats"
    else:
        level = AuditLevel.ALUCINACAO if len(missing_signals) > 2 else AuditLevel.NORMA_OK
        recommendation = "re_compact" if level == AuditLevel.ALUCINACAO else "accept_with_caveats"

    return AuditResult(
        level=level,
        reasoning=f"Heuristic audit: {len(issues)} issue(s) found",
        issues=issues,
        recommendation=recommendation,
    )


def _parse_audit_response(response: str) -> AuditResult:
    """Parse the structured LLM audit response."""
    lines = response.strip().splitlines()

    level = AuditLevel.NORMA_OK
    issues = []
    recommendation = "accept_with_caveats"
    reasoning = ""

    for line in lines:
        line_stripped = line.strip()
        upper = line_stripped.upper()

        if upper.startswith("LEVEL:"):
            level_str = line_stripped.split(":", 1)[1].strip().upper()
            if "ALUCINACAO" in level_str or "ALUCINAÇÃO" in level_str:
                level = AuditLevel.ALUCINACAO
            elif "NORMA_OK" in level_str:
                level = AuditLevel.NORMA_OK
            elif level_str == "OK":
                level = AuditLevel.OK

        elif upper.startswith("ISSUES:"):
            issue_text = line_stripped.split(":", 1)[1].strip()
            if issue_text.lower() != "none":
                issues.append(issue_text)

        elif upper.startswith("RECOMMENDATION:"):
            recommendation = line_stripped.split(":", 1)[1].strip().lower()

        elif upper.startswith("REASONING:"):
            reasoning = line_stripped.split(":", 1)[1].strip()

        elif issues and line_stripped.startswith("-"):
            issues.append(line_stripped.lstrip("- "))

    return AuditResult(
        level=level,
        reasoning=reasoning,
        issues=issues,
        recommendation=recommendation,
    )
