"""
Emergent Specialization — castes self-specialize through tool usage.

Combines deferred tool loading (R9) with agent tolerance (R12).
Instead of statically configuring which tools each caste can use,
agents earn access to new tools through successful usage.

A Scout that repeatedly succeeds at analysis tasks might earn access
to the "edit" tool — evolving from pure exploration toward assisted
implementation. This is NOT a bug; it's emergent specialization.

The tolerance system prevents abuse: failures with earned tools
revoke access (immune-tolerance demotion).

Biological analogy: phenotypic plasticity — organisms adapting
their expressed capabilities to environmental demands.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from symbiont.agent_tolerance import AgentToleranceManager, TrustLevel
from symbiont.deferred_tools import DeferredToolLoader, CASTE_TOOL_PROFILES
from symbiont.types import Caste

logger = logging.getLogger(__name__)

# Minimum successes with a requested tool before it's permanently earned
EARN_THRESHOLD = 3
# Maximum extra tools an agent can earn beyond its caste profile
MAX_EARNED_TOOLS = 5


@dataclass
class ToolUsageRecord:
    """Tracks an agent's usage of a specific tool."""
    tool_name: str
    successes: int = 0
    failures: int = 0
    last_used: float = 0.0

    @property
    def earned(self) -> bool:
        """Has the agent earned permanent access to this tool?"""
        return self.successes >= EARN_THRESHOLD and self.success_rate >= 0.8

    @property
    def success_rate(self) -> float:
        total = self.successes + self.failures
        return self.successes / total if total > 0 else 0.0


class EmergentSpecialization:
    """
    Manages emergent tool specialization for agents.

    Agents start with their caste's default tool set. Through
    successful usage, they can earn access to additional tools.
    Failures revoke earned access.
    """

    def __init__(
        self,
        tool_loader: DeferredToolLoader,
        tolerance: AgentToleranceManager,
    ):
        self._tool_loader = tool_loader
        self._tolerance = tolerance
        self._usage: dict[str, dict[str, ToolUsageRecord]] = {}  # agent_id → {tool → record}
        self._earned: dict[str, set[str]] = {}  # agent_id → earned tool names

    def request_tool(self, agent_id: str, caste: Caste, tool_name: str) -> bool:
        """
        Request access to a tool. Allowed if:
        1. Tool is in caste's default profile, OR
        2. Agent's trust level is TRUSTED+ and hasn't exceeded max earned tools
        """
        # Already visible to caste
        if self._tool_loader.is_visible(tool_name, caste):
            return True

        # Check trust level
        trust = self._tolerance.get_trust_level(agent_id)
        if trust in (TrustLevel.SUPPRESSED, TrustLevel.PROBATION):
            logger.info(
                "specialization: '%s' denied tool '%s' (trust=%s)",
                agent_id, tool_name, trust.value,
            )
            return False

        # Check max earned limit
        earned = self._earned.get(agent_id, set())
        if len(earned) >= MAX_EARNED_TOOLS:
            logger.info("specialization: '%s' at max earned tools (%d)", agent_id, MAX_EARNED_TOOLS)
            return False

        # Grant temporary access via tool loader
        return self._tool_loader.request_tool(agent_id, caste, tool_name)

    def record_tool_success(self, agent_id: str, tool_name: str) -> bool:
        """
        Record successful use of a tool.
        May earn permanent access if threshold reached.
        Returns True if tool was newly earned.
        """
        record = self._get_or_create_record(agent_id, tool_name)
        record.successes += 1
        record.last_used = time.time()

        if record.earned and tool_name not in self._earned.get(agent_id, set()):
            if agent_id not in self._earned:
                self._earned[agent_id] = set()
            self._earned[agent_id].add(tool_name)
            logger.info(
                "specialization: '%s' EARNED permanent access to '%s' (successes=%d)",
                agent_id, tool_name, record.successes,
            )
            return True

        return False

    def record_tool_failure(self, agent_id: str, tool_name: str) -> None:
        """Record failed use of a tool. May revoke earned access."""
        record = self._get_or_create_record(agent_id, tool_name)
        record.failures += 1
        record.last_used = time.time()

        # Revoke if success rate drops below threshold
        earned = self._earned.get(agent_id, set())
        if tool_name in earned and record.success_rate < 0.5:
            earned.discard(tool_name)
            logger.warning(
                "specialization: '%s' LOST access to '%s' (rate=%.2f)",
                agent_id, tool_name, record.success_rate,
            )

    def get_earned_tools(self, agent_id: str) -> set[str]:
        """Get tools earned by an agent beyond its caste profile."""
        return self._earned.get(agent_id, set()).copy()

    def get_specialization_profile(self, agent_id: str) -> dict:
        """Get the full specialization profile for an agent."""
        usage = self._usage.get(agent_id, {})
        return {
            "agent_id": agent_id,
            "earned_tools": list(self._earned.get(agent_id, set())),
            "tool_usage": {
                name: {
                    "successes": r.successes,
                    "failures": r.failures,
                    "success_rate": round(r.success_rate, 2),
                    "earned": r.earned,
                }
                for name, r in usage.items()
            },
        }

    def summary(self) -> dict:
        total_earned = sum(len(t) for t in self._earned.values())
        agents_with_specialization = len(self._earned)
        return {
            "agents_tracked": len(self._usage),
            "agents_with_earned_tools": agents_with_specialization,
            "total_earned_tools": total_earned,
        }

    def _get_or_create_record(self, agent_id: str, tool_name: str) -> ToolUsageRecord:
        if agent_id not in self._usage:
            self._usage[agent_id] = {}
        if tool_name not in self._usage[agent_id]:
            self._usage[agent_id][tool_name] = ToolUsageRecord(tool_name=tool_name)
        return self._usage[agent_id][tool_name]
