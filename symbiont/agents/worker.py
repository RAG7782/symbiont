"""
Worker Agent (Media caste) — the core executor.

Workers do the main work: code, analysis, transformation, testing.
They follow artifacts deposited by scouts and majors, and deposit
their own work products for downstream agents.

Biological analogy: media-sized leaf-cutter ants that cut and transport.
"""

from __future__ import annotations

import logging
from typing import Any

from symbiont.agents.base import BaseAgent
from symbiont.types import ArtifactStatus, Caste, Message

logger = logging.getLogger(__name__)


class WorkerAgent(BaseAgent):
    """
    Core execution agent (Media caste).

    Workers are the backbone of the colony. They:
    - Pick up tasks from artifacts in the Mound
    - Execute work using their LLM backend + tools
    - Deposit results as new artifacts (stigmergy)
    - Can form Pods with other workers for complex tasks
    """

    def __init__(self, agent_id: str | None = None) -> None:
        super().__init__(
            caste=Caste.MEDIA,
            capabilities={"code", "analysis", "transform", "test", "review"},
            agent_id=agent_id,
        )

    async def execute(self, task: str, context: dict | None = None) -> Any:
        """
        Worker's execute: perform the core work and deposit results.
        """
        self.set_current_task(task)
        context = context or {}

        # Use LLM to perform the task
        work_prompt = self._build_work_prompt(task, context)
        result = await self.think(work_prompt, context)

        # Determine artifact kind from task type
        kind = self._infer_artifact_kind(task)

        # Deposit result as artifact
        artifact = await self.deposit_artifact(
            kind=kind,
            content=result,
            quality=0.7,  # Workers produce solid but not final quality
            confidence=0.8,
            tags={kind, "worker_output"},
            metadata={
                "task": task,
                "worker_id": self.id,
            },
        )

        self.clear_current_task()

        return {
            "result": result,
            "artifact_id": artifact.id if artifact else None,
            "kind": kind,
        }

    async def on_message(self, msg: Message) -> None:
        """React to work requests and artifact notifications."""
        payload = msg.payload
        if isinstance(payload, dict):
            action = payload.get("action", "")
            if action == "work":
                task = payload.get("task", "")
                if task:
                    await self.execute(task, payload.get("context", {}))
            elif action == "review":
                await self._review_artifact(payload.get("artifact_id", ""))

    async def _review_artifact(self, artifact_id: str) -> dict | None:
        """Review an artifact and update its status."""
        if not self._mound:
            return None

        artifact = self._mound.get(artifact_id)
        if not artifact:
            return None

        self.set_current_task(f"reviewing:{artifact_id}")

        review_prompt = (
            f"Review this work artifact and assess quality:\n\n"
            f"Kind: {artifact.kind}\n"
            f"Content: {artifact.content}\n\n"
            f"Provide: quality score (0-1), issues found, and recommendation (approve/revise)."
        )
        result = await self.think(review_prompt)

        # Update artifact based on review
        new_status = ArtifactStatus.APPROVED if "approve" in result.lower() else ArtifactStatus.REVIEW
        await self._mound.update(
            artifact_id,
            status=new_status,
            metadata={**artifact.metadata, "review": result, "reviewer": self.id},
        )

        self.clear_current_task()
        return {"review": result, "new_status": new_status.name}

    def _build_work_prompt(self, task: str, context: dict) -> str:
        parts = [
            f"You are a Worker agent. Execute this task: {task}",
            "",
            "Produce a clear, complete result.",
            "Focus on correctness and completeness.",
        ]
        if context:
            parts.insert(2, f"Context: {context}")
        return "\n".join(parts)

    def _infer_artifact_kind(self, task: str) -> str:
        task_lower = task.lower()
        if any(w in task_lower for w in ("code", "implement", "function", "class")):
            return "code"
        if any(w in task_lower for w in ("test", "spec", "assert")):
            return "test"
        if any(w in task_lower for w in ("review", "audit", "check")):
            return "review"
        if any(w in task_lower for w in ("doc", "document", "explain")):
            return "documentation"
        if any(w in task_lower for w in ("analyze", "analysis", "investigate")):
            return "analysis"
        return "work"
