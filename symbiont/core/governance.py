"""
System 7 — COLONY GOVERNANCE (Heterocephalus glaber + Canis lupus)

The endocrine system of SYMBIONT. Governance by presence, not command.
Combines contextual leadership (wolf) with hormonal suppression and
leader election (naked mole-rat).

Key biological properties:
- Wolf: leadership rotates by context (who leads depends on the task phase)
- Mole-rat: queen suppresses certain behaviors by presence, not by orders
- Mole-rat: leader election via competition when queen fails
- Mole-rat: reserve agents (infrequent workers) for burst capacity
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from symbiont.config import GovernanceConfig
from symbiont.types import AgentState, Caste, Phase

logger = logging.getLogger(__name__)


@dataclass
class _AgentRecord:
    """Governance-level view of an agent."""
    agent_id: str
    caste: Caste
    state: AgentState = AgentState.ACTIVE
    trust_score: float = 0.5
    tasks_completed: int = 0
    errors: int = 0
    last_active: float = field(default_factory=time.time)

    @property
    def reliability(self) -> float:
        total = self.tasks_completed + self.errors
        if total == 0:
            return 0.5
        return self.tasks_completed / total


@dataclass
class _ElectionCandidate:
    agent_id: str
    score: float


class Governor:
    """
    Hybrid governance: Wolf contextual leadership + Mole-rat suppression.

    The Governor does NOT issue commands. It:
    1. Tracks the current phase and which caste leads
    2. Suppresses behaviors via presence (e.g., only Queen can spawn)
    3. Manages leader election when the Queen fails
    4. Maintains the reserve pool for burst capacity
    """

    def __init__(self, config: GovernanceConfig | None = None) -> None:
        self.config = config or GovernanceConfig()
        self._phase: Phase = Phase.EXPLORATION
        self._agents: dict[str, _AgentRecord] = {}
        self._queen_id: str | None = None
        self._reserve_pool: list[str] = []
        self._phase_leader: dict[Phase, Caste] = {
            Phase.EXPLORATION: Caste.SCOUT,
            Phase.DECISION: Caste.MAJOR,    # Waggle is collective, but Major breaks ties
            Phase.EXECUTION: Caste.MEDIA,
            Phase.VALIDATION: Caste.MAJOR,
            Phase.DELIVERY: Caste.MEDIA,
        }
        self._suppression_active: bool = False
        self._election_in_progress: bool = False
        self._human_present: bool = False
        self._phase_history: list[tuple[Phase, float]] = []

    # ------------------------------------------------------------------
    # Phase management (Wolf contextual leadership)
    # ------------------------------------------------------------------

    @property
    def current_phase(self) -> Phase:
        return self._phase

    @property
    def leading_caste(self) -> Caste:
        """The caste that currently has priority (not authority — priority)."""
        return self._phase_leader[self._phase]

    async def transition_to(self, phase: Phase) -> Phase:
        """
        Transition to a new governance phase.
        The leading caste changes with the phase (wolf model).
        """
        old_phase = self._phase
        self._phase = phase
        self._phase_history.append((phase, time.time()))

        logger.info(
            "governance: phase %s → %s (leader: %s)",
            old_phase.name,
            phase.name,
            self.leading_caste.name,
        )
        return phase

    async def auto_transition(self) -> Phase | None:
        """
        Automatically transition to the next phase if conditions are met.
        Returns the new phase or None if no transition occurred.
        """
        if not self.config.phase_auto_transition:
            return None

        transitions = {
            Phase.EXPLORATION: Phase.DECISION,
            Phase.DECISION: Phase.EXECUTION,
            Phase.EXECUTION: Phase.VALIDATION,
            Phase.VALIDATION: Phase.DELIVERY,
            Phase.DELIVERY: Phase.EXPLORATION,  # Cycle back
        }
        next_phase = transitions.get(self._phase)
        if next_phase:
            return await self.transition_to(next_phase)
        return None

    # ------------------------------------------------------------------
    # Agent registration
    # ------------------------------------------------------------------

    def register_agent(self, agent_id: str, caste: Caste) -> None:
        self._agents[agent_id] = _AgentRecord(agent_id=agent_id, caste=caste)
        if caste == Caste.QUEEN:
            self._queen_id = agent_id
            self._suppression_active = True
            logger.info("governance: queen registered '%s' — suppression active", agent_id)

    def unregister_agent(self, agent_id: str) -> None:
        record = self._agents.pop(agent_id, None)
        if record and agent_id == self._queen_id:
            self._queen_id = None
            self._suppression_active = False
            logger.warning("governance: queen lost — suppression deactivated")

    def record_task_complete(self, agent_id: str) -> None:
        rec = self._agents.get(agent_id)
        if rec:
            rec.tasks_completed += 1
            rec.trust_score = min(1.0, rec.trust_score + 0.05)
            rec.last_active = time.time()

    def record_error(self, agent_id: str) -> None:
        rec = self._agents.get(agent_id)
        if rec:
            rec.errors += 1
            rec.trust_score = max(0.0, rec.trust_score - 0.1)

    # ------------------------------------------------------------------
    # Suppression (Mole-rat hormonal governance)
    # ------------------------------------------------------------------

    def can_spawn(self, requester_id: str) -> bool:
        """
        Only the Queen can spawn new agents while she's active.
        This is suppression by presence — not a command.
        """
        if not self._suppression_active:
            return True  # No queen → anyone can spawn (chaotic period)
        return requester_id == self._queen_id

    def can_decide(self, agent_id: str) -> bool:
        """
        During a decision phase, only the leading caste has priority.
        Others can still suggest (via Waggle), but tie-breaking goes to the leader.
        """
        rec = self._agents.get(agent_id)
        if not rec:
            return False
        if self._human_present:
            return False  # Human override: system is consultive only
        return rec.caste == self.leading_caste

    def set_human_present(self, present: bool) -> None:
        """When human is present, system operates in consultive mode."""
        self._human_present = present
        logger.info("governance: human %s", "present" if present else "absent")

    @property
    def is_human_present(self) -> bool:
        return self._human_present

    # ------------------------------------------------------------------
    # Leader Election (Mole-rat competition)
    # ------------------------------------------------------------------

    async def elect_queen(self) -> str | None:
        """
        When the Queen fails, eligible Majors compete for the role.
        The winner transforms (gains Queen capabilities).
        """
        if self._queen_id and self._agents.get(self._queen_id):
            return self._queen_id  # Queen still alive

        self._election_in_progress = True
        logger.info("governance: queen election started")

        # Candidates: all active Majors
        candidates = [
            _ElectionCandidate(
                agent_id=rec.agent_id,
                score=rec.trust_score * rec.reliability * (rec.tasks_completed + 1),
            )
            for rec in self._agents.values()
            if rec.caste == Caste.MAJOR and rec.state == AgentState.ACTIVE
        ]

        if not candidates:
            logger.error("governance: no candidates for queen election")
            self._election_in_progress = False
            return None

        # Competition: highest composite score wins
        candidates.sort(key=lambda c: c.score, reverse=True)
        winner = candidates[0]

        # Transformation: the winner changes caste (gains Queen toolset)
        rec = self._agents[winner.agent_id]
        rec.caste = Caste.QUEEN
        self._queen_id = winner.agent_id
        self._suppression_active = True
        self._election_in_progress = False

        logger.info(
            "governance: '%s' elected as new queen (score=%.2f)",
            winner.agent_id,
            winner.score,
        )
        return winner.agent_id

    @property
    def election_in_progress(self) -> bool:
        return self._election_in_progress

    # ------------------------------------------------------------------
    # Reserve Pool (Mole-rat infrequent workers)
    # ------------------------------------------------------------------

    def hibernate_agent(self, agent_id: str) -> None:
        """Move an agent to reserve pool — warm start, zero active cost."""
        rec = self._agents.get(agent_id)
        if rec:
            rec.state = AgentState.HIBERNATING
            self._reserve_pool.append(agent_id)
            logger.debug("governance: '%s' hibernated", agent_id)

    def activate_reserve(self, caste: Caste | None = None) -> str | None:
        """
        Activate a hibernated agent from the reserve pool.
        Faster than spawning a new agent (warm start).
        """
        for agent_id in self._reserve_pool:
            rec = self._agents.get(agent_id)
            if rec and (caste is None or rec.caste == caste):
                rec.state = AgentState.ACTIVE
                self._reserve_pool.remove(agent_id)
                logger.info("governance: activated reserve '%s' (%s)", agent_id, rec.caste.name)
                return agent_id
        return None

    @property
    def reserve_count(self) -> int:
        return len(self._reserve_pool)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        active = sum(1 for r in self._agents.values() if r.state == AgentState.ACTIVE)
        return {
            "phase": self._phase.name,
            "leading_caste": self.leading_caste.name,
            "queen": self._queen_id,
            "suppression_active": self._suppression_active,
            "human_present": self._human_present,
            "total_agents": len(self._agents),
            "active_agents": active,
            "reserve_pool": self.reserve_count,
            "election_in_progress": self._election_in_progress,
        }
