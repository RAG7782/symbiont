"""
Minima Agent — the context worker.

Minimas are small, cheap, high-cardinality agents that handle
maintenance tasks: context preparation, formatting, cleanup,
indexing, and knowledge base tending.

Biological analogy: minima leaf-cutter ants that tend the fungus garden.
"""

from __future__ import annotations

import logging
from typing import Any

from symbiont.agents.base import BaseAgent
from symbiont.types import Caste, Message

logger = logging.getLogger(__name__)


class MinimaAgent(BaseAgent):
    """
    Context and maintenance agent (Minima caste).

    Minimas are the most numerous and cheapest agents. They:
    - Prepare context for other agents
    - Format and clean data
    - Maintain the knowledge base (fungus garden)
    - Index artifacts for fast retrieval
    - Propagate decisions to affected artifacts
    """

    def __init__(self, agent_id: str | None = None) -> None:
        super().__init__(
            caste=Caste.MINIMA,
            capabilities={"context_prep", "formatting", "cleanup", "indexing"},
            agent_id=agent_id,
        )

    async def execute(self, task: str, context: dict | None = None) -> Any:
        """
        Minima's execute: perform maintenance/context work.
        """
        self.set_current_task(task)
        context = context or {}

        task_type = context.get("type", "context_prep")

        if task_type == "context_prep":
            result = await self._prepare_context(task, context)
        elif task_type == "cleanup":
            result = await self._cleanup(task, context)
        elif task_type == "index":
            result = await self._index_artifacts(task, context)
        elif task_type == "knowledge_update":
            result = await self._update_knowledge(task, context)
        elif task_type == "format":
            result = await self._format_data(task, context)
        else:
            result = await self._generic_maintenance(task, context)

        self.clear_current_task()
        return result

    async def _prepare_context(self, task: str, context: dict) -> dict:
        """Prepare context for another agent — gather relevant info."""
        if not self._mound:
            return {"context": context}

        # Search knowledge base for relevant info
        knowledge = self._mound.search_knowledge(task)

        # Find related artifacts
        related = self._mound.query(min_quality=0.5)[:10]

        prepared = {
            "original_task": task,
            "knowledge": dict(knowledge[:5]),
            "related_artifacts": [
                {"id": a.id, "kind": a.kind, "quality": a.quality}
                for a in related
            ],
            **context,
        }

        # Deposit prepared context as artifact
        await self.deposit_artifact(
            kind="context",
            content=prepared,
            quality=0.6,
            confidence=0.7,
            tags={"context", "prepared"},
        )

        return prepared

    async def _cleanup(self, task: str, context: dict) -> dict:
        """Clean up artifacts: archive old ones, remove drafts."""
        if not self._mound:
            return {"cleaned": 0}

        from symbiont.types import ArtifactStatus
        drafts = self._mound.query(status=ArtifactStatus.DRAFT)
        cleaned = 0
        for artifact in drafts:
            if artifact.age_seconds > 3600:  # Older than 1 hour
                await self._mound.update(artifact.id, status=ArtifactStatus.ARCHIVED)
                cleaned += 1

        return {"cleaned": cleaned}

    async def _index_artifacts(self, task: str, context: dict) -> dict:
        """Index artifacts in the knowledge base for fast retrieval."""
        if not self._mound:
            return {"indexed": 0}

        from symbiont.types import ArtifactStatus
        approved = self._mound.query(status=ArtifactStatus.APPROVED)
        indexed = 0
        for artifact in approved:
            key = f"artifact:{artifact.kind}:{artifact.id}"
            summary = str(artifact.content)[:200]
            self._mound.learn(key, summary)
            indexed += 1

        return {"indexed": indexed}

    async def _update_knowledge(self, task: str, context: dict) -> dict:
        """Update the knowledge base with new information."""
        if not self._mound:
            return {}

        key = context.get("key", task[:50])
        value = context.get("value", "")
        if value:
            self._mound.learn(key, value)
            return {"key": key, "updated": True}
        return {"key": key, "updated": False}

    async def _format_data(self, task: str, context: dict) -> dict:
        """Format data for consumption by other agents."""
        data = context.get("data", "")
        prompt = f"Format the following data cleanly and consistently:\n\n{data}"
        result = await self.think(prompt, context)
        return {"formatted": result}

    async def _generic_maintenance(self, task: str, context: dict) -> dict:
        prompt = f"Perform this maintenance task: {task}"
        result = await self.think(prompt, context)
        return {"result": result}

    async def on_message(self, msg: Message) -> None:
        """React to maintenance requests."""
        payload = msg.payload
        if isinstance(payload, dict):
            action = payload.get("action", "")
            if action in ("context_prep", "cleanup", "index", "knowledge_update", "format"):
                task = payload.get("task", "maintenance")
                await self.execute(task, {**payload, "type": action})
