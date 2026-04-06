"""
SYMBIONT Squads — project-based agent grouping.

Squads assign groups of agents to specific projects or domains.
Each squad has its own context, allowing specialized behavior.

Usage:
    from symbiont.squads import SquadManager

    mgr = SquadManager(store=persistence_store)
    mgr.create("legal", description="Legal analysis team",
               context={"domain": "law", "language": "pt-br"})
    mgr.assign("legal", ["scout:abc123", "worker:def456"])

CLI:
    sym squad list
    sym squad create <name> <description>
    sym squad assign <name> <agent_ids>
    sym squad run <name> <task>
    sym squad delete <name>
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class Squad:
    """A project-based group of agents."""

    def __init__(self, name: str, description: str = "",
                 agent_ids: list[str] | None = None,
                 context: dict | None = None,
                 created_at: float = 0):
        self.name = name
        self.description = description
        self.agent_ids: list[str] = agent_ids or []
        self.context: dict = context or {}
        self.created_at = created_at or time.time()
        self.updated_at = time.time()

    def add_agent(self, agent_id: str) -> None:
        if agent_id not in self.agent_ids:
            self.agent_ids.append(agent_id)
            self.updated_at = time.time()

    def remove_agent(self, agent_id: str) -> bool:
        if agent_id in self.agent_ids:
            self.agent_ids.remove(agent_id)
            self.updated_at = time.time()
            return True
        return False

    @property
    def size(self) -> int:
        return len(self.agent_ids)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "agent_ids": self.agent_ids,
            "context": self.context,
            "size": self.size,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SquadManager:
    """Manages squads with optional persistence."""

    def __init__(self, store=None):
        self._squads: dict[str, Squad] = {}
        self._store = store  # PersistenceStore (optional)

        if self._store:
            self._load_from_store()

    def _load_from_store(self):
        data = self._store.load_squads()
        for name, info in data.items():
            self._squads[name] = Squad(
                name=name,
                description=info.get("description", ""),
                agent_ids=info.get("agent_ids", []),
                context=info.get("context", {}),
                created_at=info.get("created_at", 0),
            )
        logger.info("squads: loaded %d squads from store", len(self._squads))

    def _persist(self, squad: Squad):
        if self._store:
            self._store.save_squad(squad.name, squad.description, squad.agent_ids, squad.context)

    def create(self, name: str, description: str = "", context: dict | None = None) -> Squad:
        squad = Squad(name=name, description=description, context=context)
        self._squads[name] = squad
        self._persist(squad)
        logger.info("squads: created '%s'", name)
        return squad

    def get(self, name: str) -> Squad | None:
        return self._squads.get(name)

    def delete(self, name: str) -> bool:
        if name in self._squads:
            del self._squads[name]
            if self._store:
                self._store.delete_squad(name)
            return True
        return False

    def assign(self, squad_name: str, agent_ids: list[str]) -> bool:
        squad = self._squads.get(squad_name)
        if not squad:
            return False
        for aid in agent_ids:
            squad.add_agent(aid)
        self._persist(squad)
        return True

    def unassign(self, squad_name: str, agent_id: str) -> bool:
        squad = self._squads.get(squad_name)
        if not squad:
            return False
        removed = squad.remove_agent(agent_id)
        if removed:
            self._persist(squad)
        return removed

    def get_agent_squad(self, agent_id: str) -> str | None:
        """Find which squad an agent belongs to."""
        for name, squad in self._squads.items():
            if agent_id in squad.agent_ids:
                return name
        return None

    def list_squads(self) -> dict[str, dict]:
        return {name: squad.to_dict() for name, squad in self._squads.items()}

    def auto_assign(self, organism) -> dict[str, list[str]]:
        """
        Auto-assign agents from a running organism to squads based on caste.

        Default mapping:
        - Scouts + Minima → exploration squad
        - Workers + Major → execution squad
        - Queen stays unassigned (global)
        """
        from symbiont.types import Caste

        assignments = {}
        for agent in organism._agents.values():
            if agent.caste == Caste.QUEEN:
                continue  # Queen is global
            elif agent.caste in (Caste.SCOUT, Caste.MINIMA):
                squad_name = "exploration"
            else:
                squad_name = "execution"

            if squad_name not in self._squads:
                self.create(squad_name, description=f"Auto-assigned {squad_name} squad")

            self._squads[squad_name].add_agent(agent.id)
            assignments.setdefault(squad_name, []).append(agent.id)

        # Persist all
        for squad in self._squads.values():
            self._persist(squad)

        return assignments

    @property
    def total_squads(self) -> int:
        return len(self._squads)

    @property
    def total_assigned(self) -> int:
        return sum(s.size for s in self._squads.values())
