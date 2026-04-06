"""
Major Agent — the specialist and decision-maker.

Majors handle architecture, complex decisions, and disambiguation.
They are expensive (Opus-class) and used sparingly. They also serve
as candidates for Queen succession (leader election).

Biological analogy: soldier ants with specialized mandibles.
"""

from __future__ import annotations

import logging
from typing import Any

from symbiont.agents.base import BaseAgent
from symbiont.types import Caste, Message, QuorumLevel

logger = logging.getLogger(__name__)


class MajorAgent(BaseAgent):
    """
    Specialist agent (Major caste).

    Majors are invoked for:
    - Architectural decisions
    - Ambiguity resolution
    - Complex planning
    - Tie-breaking in the Waggle Protocol
    - Queen election candidacy
    """

    def __init__(self, agent_id: str | None = None) -> None:
        super().__init__(
            caste=Caste.MAJOR,
            capabilities={"architecture", "decision", "disambiguation", "planning"},
            agent_id=agent_id,
        )

    async def execute(self, task: str, context: dict | None = None) -> Any:
        """
        Major's execute: make a high-quality decision or plan.
        """
        self.set_current_task(task)
        context = context or {}

        task_type = context.get("type", "decision")

        if task_type == "architecture":
            result = await self._architectural_decision(task, context)
        elif task_type == "disambiguation":
            result = await self._disambiguate(task, context)
        elif task_type == "plan":
            result = await self._plan(task, context)
        elif task_type == "tiebreak":
            result = await self._tiebreak(task, context)
        else:
            result = await self._generic_decision(task, context)

        # Deposit as high-quality artifact
        artifact = await self.deposit_artifact(
            kind="decision",
            content=result,
            quality=0.9,  # Majors produce high-quality output
            confidence=0.85,
            tags={"decision", task_type},
            metadata={"task": task, "type": task_type, "major_id": self.id},
        )

        self.clear_current_task()
        return {
            "decision": result,
            "artifact_id": artifact.id if artifact else None,
            "type": task_type,
        }

    async def _architectural_decision(self, task: str, context: dict) -> str:
        prompt = (
            f"You are an Architecture Major agent. Make an architectural decision:\n\n"
            f"Question: {task}\n"
            f"Context: {context}\n\n"
            f"Structure your response as:\n"
            f"1. DECISION: Clear statement of the architectural choice\n"
            f"2. RATIONALE: Why this is the right choice\n"
            f"3. TRADE-OFFS: What we're giving up\n"
            f"4. IMPLEMENTATION NOTES: Key considerations for the Workers\n"
        )
        return await self.think_deep(prompt, context)

    async def _disambiguate(self, task: str, context: dict) -> str:
        options = context.get("options", [])
        prompt = (
            f"You are a Disambiguation Major agent. Resolve this ambiguity:\n\n"
            f"Question: {task}\n"
            f"Options: {options}\n\n"
            f"Choose the best option and explain why unambiguously.\n"
        )
        return await self.think(prompt, context)

    async def _plan(self, task: str, context: dict) -> str:
        prompt = (
            f"You are a Planning Major agent. Create a detailed plan:\n\n"
            f"Objective: {task}\n"
            f"Context: {context}\n\n"
            f"Provide a step-by-step plan with:\n"
            f"1. Steps in order\n"
            f"2. Dependencies between steps\n"
            f"3. Which caste should handle each step\n"
            f"4. Risk points and mitigations\n"
        )
        return await self.think(prompt, context)

    async def _tiebreak(self, task: str, context: dict) -> str:
        """Break a tie in the Waggle Protocol when no quorum was reached."""
        options = context.get("tally", {})
        reports = context.get("reports", [])
        prompt = (
            f"You are a Tiebreak Major agent. The Waggle Protocol failed to reach quorum.\n\n"
            f"Question: {task}\n"
            f"Option scores: {options}\n"
            f"Number of reports: {len(reports)}\n\n"
            f"Make the final call. Choose one option and justify.\n"
        )
        return await self.think_deep(prompt, context)

    async def _generic_decision(self, task: str, context: dict) -> str:
        prompt = (
            f"You are a Major agent. Handle this task with expert-level analysis:\n\n"
            f"{task}\n\n"
            f"Context: {context}\n"
        )
        return await self.think(prompt, context)

    async def on_message(self, msg: Message) -> None:
        """React to decision requests and escalations."""
        payload = msg.payload
        if isinstance(payload, dict):
            action = payload.get("action", "")
            if action in ("decide", "plan", "tiebreak", "disambiguate"):
                task = payload.get("task", "")
                if task:
                    await self.execute(task, {**payload, "type": action})
