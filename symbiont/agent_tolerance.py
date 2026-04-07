"""
Agent Tolerance — immune-tolerance applied to internal agents.

Extends the immune-tolerance concept (designed for external integrations)
to internal SYMBIONT agents. Agents earn trust through successful task
completion and lose it through failures.

Trust levels:
- PROBATION: New agent, full validation on every action
- TRUSTED:   Proven agent, reduced oversight
- AUTONOMOUS: High-performing agent, minimal oversight
- SUPPRESSED: Failing agent, maximum oversight + limited actions

Transitions:
- Success → trust increases (PROBATION → TRUSTED → AUTONOMOUS)
- Failure → trust decreases (AUTONOMOUS → TRUSTED → PROBATION → SUPPRESSED)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum

from symbiont.types import Caste

logger = logging.getLogger(__name__)

# Thresholds for trust level transitions
TASKS_TO_TRUSTED = 3
TASKS_TO_AUTONOMOUS = 10
ERRORS_TO_PROBATION = 2
ERRORS_TO_SUPPRESSED = 5


class TrustLevel(Enum):
    SUPPRESSED = "suppressed"
    PROBATION = "probation"
    TRUSTED = "trusted"
    AUTONOMOUS = "autonomous"


@dataclass
class AgentTrustProfile:
    """Trust and performance profile for an agent."""
    agent_id: str
    caste: Caste
    trust_level: TrustLevel = TrustLevel.PROBATION
    tasks_completed: int = 0
    tasks_failed: int = 0
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    created_at: float = field(default_factory=time.time)
    last_action: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> float:
        total = self.tasks_completed + self.tasks_failed
        return self.tasks_completed / total if total > 0 else 0.0

    @property
    def requires_validation(self) -> bool:
        """Does this agent need validation before acting?"""
        return self.trust_level in (TrustLevel.PROBATION, TrustLevel.SUPPRESSED)

    @property
    def can_act_independently(self) -> bool:
        """Can this agent act without oversight?"""
        return self.trust_level == TrustLevel.AUTONOMOUS


class AgentToleranceManager:
    """
    Manages trust levels for all agents in the organism.
    """

    def __init__(self) -> None:
        self._profiles: dict[str, AgentTrustProfile] = {}

    def register(self, agent_id: str, caste: Caste) -> AgentTrustProfile:
        """Register a new agent. Starts on PROBATION."""
        profile = AgentTrustProfile(agent_id=agent_id, caste=caste)
        self._profiles[agent_id] = profile
        logger.info("tolerance: registered '%s' (%s) → PROBATION", agent_id, caste.name)
        return profile

    def record_success(self, agent_id: str) -> TrustLevel | None:
        """Record a successful task. May promote trust level."""
        profile = self._profiles.get(agent_id)
        if not profile:
            return None

        profile.tasks_completed += 1
        profile.consecutive_successes += 1
        profile.consecutive_failures = 0
        profile.last_action = time.time()

        old_level = profile.trust_level

        # Promotion logic
        if (profile.trust_level == TrustLevel.PROBATION
                and profile.tasks_completed >= TASKS_TO_TRUSTED):
            profile.trust_level = TrustLevel.TRUSTED
        elif (profile.trust_level == TrustLevel.TRUSTED
                and profile.tasks_completed >= TASKS_TO_AUTONOMOUS
                and profile.success_rate >= 0.9):
            profile.trust_level = TrustLevel.AUTONOMOUS
        elif (profile.trust_level == TrustLevel.SUPPRESSED
                and profile.consecutive_successes >= TASKS_TO_TRUSTED):
            profile.trust_level = TrustLevel.PROBATION

        if profile.trust_level != old_level:
            logger.info(
                "tolerance: '%s' promoted %s → %s",
                agent_id, old_level.value, profile.trust_level.value,
            )

        return profile.trust_level

    def record_failure(self, agent_id: str) -> TrustLevel | None:
        """Record a failed task. May demote trust level."""
        profile = self._profiles.get(agent_id)
        if not profile:
            return None

        profile.tasks_failed += 1
        profile.consecutive_failures += 1
        profile.consecutive_successes = 0
        profile.last_action = time.time()

        old_level = profile.trust_level

        # Demotion logic
        if (profile.trust_level == TrustLevel.AUTONOMOUS
                and profile.consecutive_failures >= ERRORS_TO_PROBATION):
            profile.trust_level = TrustLevel.TRUSTED
        elif (profile.trust_level == TrustLevel.TRUSTED
                and profile.consecutive_failures >= ERRORS_TO_PROBATION):
            profile.trust_level = TrustLevel.PROBATION
        elif (profile.trust_level == TrustLevel.PROBATION
                and profile.tasks_failed >= ERRORS_TO_SUPPRESSED):
            profile.trust_level = TrustLevel.SUPPRESSED

        if profile.trust_level != old_level:
            logger.warning(
                "tolerance: '%s' demoted %s → %s",
                agent_id, old_level.value, profile.trust_level.value,
            )

        return profile.trust_level

    def get_trust_level(self, agent_id: str) -> TrustLevel:
        profile = self._profiles.get(agent_id)
        return profile.trust_level if profile else TrustLevel.PROBATION

    def requires_validation(self, agent_id: str) -> bool:
        profile = self._profiles.get(agent_id)
        return profile.requires_validation if profile else True

    def get_profile(self, agent_id: str) -> AgentTrustProfile | None:
        return self._profiles.get(agent_id)

    def get_suppressed(self) -> list[str]:
        return [
            p.agent_id for p in self._profiles.values()
            if p.trust_level == TrustLevel.SUPPRESSED
        ]

    def summary(self) -> dict:
        by_level = {}
        for p in self._profiles.values():
            level = p.trust_level.value
            by_level[level] = by_level.get(level, 0) + 1
        return {
            "total_agents": len(self._profiles),
            "by_level": by_level,
            "suppressed": self.get_suppressed(),
        }
