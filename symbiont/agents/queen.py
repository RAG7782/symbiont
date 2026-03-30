"""
Queen Agent — the spawner.

NOT a commander. The Queen's role is:
1. Read demand signals from the CasteRegistry
2. Spawn agents of the needed caste
3. Suppress other agents from spawning (by her presence alone)

Biological analogy: termite queen — a factory, not a general.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine, TYPE_CHECKING

from symbiont.agents.base import BaseAgent
from symbiont.types import AgentState, Caste, Message

if TYPE_CHECKING:
    from symbiont.core.castes import CasteRegistry

logger = logging.getLogger(__name__)

# Function that creates and wires a new agent, provided by the organism
SpawnFunction = Callable[[Caste], Coroutine[Any, Any, BaseAgent | None]]


class QueenAgent(BaseAgent):
    """
    The Queen spawns agents based on colony demand.

    She does NOT decide what work to do — she decides WHO is born.
    Demand signals come from the CasteRegistry (auto-regulation).
    """

    def __init__(self, agent_id: str | None = None) -> None:
        super().__init__(
            caste=Caste.QUEEN,
            capabilities={"spawn", "suppress", "lifecycle"},
            agent_id=agent_id,
        )
        self._caste_registry: CasteRegistry | None = None
        self._spawn_fn: SpawnFunction | None = None
        self._spawned: list[str] = []

    def wire_registry(self, registry: CasteRegistry) -> None:
        self._caste_registry = registry

    def set_spawn_function(self, fn: SpawnFunction) -> None:
        """Set the function that actually creates and wires new agents."""
        self._spawn_fn = fn

    async def execute(self, task: str, context: dict | None = None) -> Any:
        """
        Queen's execute: check demand and spawn if needed.
        Can also be called with explicit caste requests.
        """
        self.set_current_task("spawning")

        context = context or {}
        explicit_caste = context.get("caste")

        spawned = []

        if explicit_caste and isinstance(explicit_caste, Caste):
            # Explicit spawn request
            agent = await self._spawn_one(explicit_caste)
            if agent:
                spawned.append(agent.id)
        elif self._caste_registry:
            # Auto-regulation: consume demand signals
            while True:
                needed = self._caste_registry.consume_demand()
                if not needed:
                    break
                agent = await self._spawn_one(needed)
                if agent:
                    spawned.append(agent.id)

        self.clear_current_task()

        if spawned:
            logger.info("queen: spawned %d agents: %s", len(spawned), spawned)
        return {"spawned": spawned}

    async def _spawn_one(self, caste: Caste) -> BaseAgent | None:
        """Spawn a single agent of the given caste."""
        if not self._spawn_fn:
            logger.error("queen: no spawn function configured")
            return None

        if self._caste_registry and not self._caste_registry.can_spawn(caste):
            logger.warning("queen: cannot spawn %s — at capacity", caste.name)
            return None

        agent = await self._spawn_fn(caste)
        if agent:
            self._spawned.append(agent.id)
            if self._caste_registry:
                self._caste_registry.register_birth(caste)
        return agent

    async def on_message(self, msg: Message) -> None:
        """React to spawn-request messages."""
        payload = msg.payload
        if isinstance(payload, dict) and payload.get("action") == "spawn":
            caste_name = payload.get("caste", "")
            try:
                caste = Caste[caste_name.upper()]
                await self.execute("spawn", {"caste": caste})
            except KeyError:
                logger.warning("queen: unknown caste '%s'", caste_name)

    @property
    def spawn_count(self) -> int:
        return len(self._spawned)
