"""
Scout Agent — the explorer.

Scouts explore alternatives, evaluate options, and produce WaggleReports
for the collective decision protocol. They are cheap, fast, and disposable.

Biological analogy: scout bees + army ant explorers.
"""

from __future__ import annotations

import logging
from typing import Any

from symbiont.agents.base import BaseAgent
from symbiont.types import Caste, Message, WaggleReport

logger = logging.getLogger(__name__)


class ScoutAgent(BaseAgent):
    """
    Explorer agent with broad tool access.

    Scouts are dispatched to:
    - Discover resources, patterns, or alternatives
    - Evaluate options and produce WaggleReports
    - Test new paths (probe agents for the TopologyEngine)
    """

    def __init__(self, agent_id: str | None = None) -> None:
        super().__init__(
            caste=Caste.SCOUT,
            capabilities={"explore", "discover", "evaluate", "probe"},
            agent_id=agent_id,
        )

    async def execute(self, task: str, context: dict | None = None) -> Any:
        """
        Scout's execute: explore a question and produce a WaggleReport.
        """
        self.set_current_task(task)
        context = context or {}

        # Use LLM to explore the question
        exploration_prompt = self._build_exploration_prompt(task, context)
        result = await self.think(exploration_prompt, context)

        # Produce a WaggleReport
        report = WaggleReport(
            scout_id=self.id,
            option=self._extract_option(result),
            description=result,
            quality=self._assess_quality(result),
            confidence=self._assess_confidence(result),
            estimated_cost=context.get("estimated_cost", 0.0),
            evidence=self._extract_evidence(result),
            risks=self._extract_risks(result),
        )

        # Deposit as artifact for stigmergic visibility
        await self.deposit_artifact(
            kind="scout_report",
            content=report,
            quality=report.quality,
            confidence=report.confidence,
            tags={"exploration", task[:30]},
        )

        self.clear_current_task()
        return report

    async def on_message(self, msg: Message) -> None:
        """React to exploration requests."""
        payload = msg.payload
        if isinstance(payload, dict) and payload.get("action") == "explore":
            question = payload.get("question", "")
            if question:
                await self.execute(question, payload.get("context", {}))

    def _build_exploration_prompt(self, task: str, context: dict) -> str:
        parts = [
            f"You are a Scout agent exploring options for: {task}",
            "",
            "Analyze the situation and recommend an approach.",
            "Structure your response as:",
            "1. OPTION: A clear, concise name for your recommended approach",
            "2. DESCRIPTION: Why this approach works",
            "3. EVIDENCE: Concrete supporting facts",
            "4. RISKS: Potential downsides",
            "5. CONFIDENCE: How sure you are (low/medium/high)",
        ]
        if context:
            parts.insert(2, f"Context: {context}")
        return "\n".join(parts)

    def _extract_option(self, result: str) -> str:
        """Extract the option name from the LLM response."""
        for line in result.split("\n"):
            line = line.strip()
            if line.upper().startswith("OPTION:"):
                return line.split(":", 1)[1].strip()
            if line.startswith("1."):
                return line.split(".", 1)[1].strip()
        # Fallback: first line
        return result.split("\n")[0][:100] if result else "unknown"

    def _assess_quality(self, result: str) -> float:
        """Simple heuristic for quality assessment."""
        score = 0.3  # Base
        if len(result) > 100:
            score += 0.2
        if "evidence" in result.lower() or "because" in result.lower():
            score += 0.2
        if "risk" in result.lower():
            score += 0.1
        if "confidence" in result.lower():
            score += 0.1
        return min(1.0, score)

    def _assess_confidence(self, result: str) -> float:
        result_lower = result.lower()
        if "high confidence" in result_lower or "very confident" in result_lower:
            return 0.9
        if "medium confidence" in result_lower or "moderately confident" in result_lower:
            return 0.6
        if "low confidence" in result_lower or "uncertain" in result_lower:
            return 0.3
        return 0.5  # Default

    def _extract_evidence(self, result: str) -> list[str]:
        evidence = []
        capture = False
        for line in result.split("\n"):
            if "evidence" in line.lower() or "supporting" in line.lower():
                capture = True
                continue
            if capture and line.strip().startswith("-"):
                evidence.append(line.strip().lstrip("- "))
            elif capture and line.strip() == "":
                capture = False
        return evidence[:5]

    def _extract_risks(self, result: str) -> list[str]:
        risks = []
        capture = False
        for line in result.split("\n"):
            if "risk" in line.lower() or "downside" in line.lower():
                capture = True
                continue
            if capture and line.strip().startswith("-"):
                risks.append(line.strip().lstrip("- "))
            elif capture and line.strip() == "":
                capture = False
        return risks[:5]
