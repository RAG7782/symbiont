"""
System 8 — POD DYNAMICS (Tursiops truncatus)

The adaptive immune system of SYMBIONT. Forms specific responses to
novel tasks through dynamic coalition building.

Key biological properties:
- Level 1 (Pod): 2-4 agents cooperate for a sub-task
- Level 2 (Super-Pod): 2-3 pods with interdependent objectives
- Level 3 (Swarm): full mobilization for exceptional events
- Alliances are ephemeral — they dissolve when the task completes
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from symbiont.types import AllianceRequest, PodLevel, _uid

logger = logging.getLogger(__name__)


@dataclass
class Pod:
    """A temporary alliance of 2-4 agents."""
    id: str = field(default_factory=_uid)
    level: PodLevel = PodLevel.POD
    objective: str = ""
    members: list[str] = field(default_factory=list)
    leader_id: str = ""            # Contextual leader for this pod
    capabilities: set[str] = field(default_factory=set)
    shared_context: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    completed: bool = False
    result: str | None = None

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


@dataclass
class SuperPod:
    """An alliance of 2-3 pods with interdependent objectives."""
    id: str = field(default_factory=_uid)
    pod_ids: list[str] = field(default_factory=list)
    shared_objective: str = ""
    shared_context: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    completed: bool = False


class PodDynamics:
    """
    Dolphin-inspired dynamic coalition formation.

    Agents request alliances when they need capabilities they don't have.
    Pods form, execute, and dissolve automatically. Super-Pods form when
    the TopologyEngine detects interdependent pods.
    """

    def __init__(self) -> None:
        self._pods: dict[str, Pod] = {}
        self._super_pods: dict[str, SuperPod] = {}
        self._pending_requests: list[AllianceRequest] = []
        self._agent_capabilities: dict[str, set[str]] = {}
        self._agent_pod_map: dict[str, str] = {}  # agent_id → pod_id
        self._swarm_active: bool = False

    # ------------------------------------------------------------------
    # Agent capability registration
    # ------------------------------------------------------------------

    def register_capabilities(self, agent_id: str, capabilities: set[str]) -> None:
        self._agent_capabilities[agent_id] = capabilities

    def unregister_agent(self, agent_id: str) -> None:
        self._agent_capabilities.pop(agent_id, None)
        pod_id = self._agent_pod_map.pop(agent_id, None)
        if pod_id:
            pod = self._pods.get(pod_id)
            if pod and agent_id in pod.members:
                pod.members.remove(agent_id)

    # ------------------------------------------------------------------
    # Pod formation (Level 1)
    # ------------------------------------------------------------------

    async def request_alliance(self, request: AllianceRequest) -> Pod | None:
        """
        An agent publishes a "call for alliance" — agents with matching
        capabilities respond. First viable match forms the Pod.
        """
        # Find agents with the needed capabilities
        matches = []
        for agent_id, caps in self._agent_capabilities.items():
            if agent_id == request.requester_id:
                continue
            if agent_id in self._agent_pod_map:
                continue  # Already in a pod
            overlap = caps & request.needed_capabilities
            if overlap:
                matches.append((agent_id, len(overlap)))

        if not matches:
            self._pending_requests.append(request)
            logger.debug("pod: no matches for alliance request '%s' — queued", request.id)
            return None

        # Sort by most capability overlap
        matches.sort(key=lambda m: m[1], reverse=True)

        # Form the pod (up to max_members)
        members = [request.requester_id]
        combined_caps = set(self._agent_capabilities.get(request.requester_id, set()))

        for agent_id, _ in matches:
            if len(members) >= request.max_members:
                break
            members.append(agent_id)
            combined_caps |= self._agent_capabilities.get(agent_id, set())

        pod = Pod(
            objective=request.objective,
            members=members,
            leader_id=request.requester_id,  # Requester leads initially
            capabilities=combined_caps,
        )

        self._pods[pod.id] = pod
        for member_id in members:
            self._agent_pod_map[member_id] = pod.id

        logger.info(
            "pod: formed '%s' — %d members, objective='%s'",
            pod.id,
            pod.size,
            request.objective[:60],
        )
        return pod

    async def complete_pod(self, pod_id: str, result: str = "") -> None:
        """Dissolve a pod after its objective is complete."""
        pod = self._pods.get(pod_id)
        if not pod:
            return

        pod.completed = True
        pod.result = result

        # Free all members
        for member_id in pod.members:
            self._agent_pod_map.pop(member_id, None)

        logger.info("pod: dissolved '%s' (lived %.1fs)", pod_id, pod.age_seconds)

        # Check if this completes a super-pod
        for sp in self._super_pods.values():
            if pod_id in sp.pod_ids:
                all_done = all(
                    self._pods.get(pid, Pod()).completed
                    for pid in sp.pod_ids
                )
                if all_done:
                    sp.completed = True
                    logger.info("pod: super-pod '%s' completed", sp.id)

    # ------------------------------------------------------------------
    # Super-Pod formation (Level 2)
    # ------------------------------------------------------------------

    async def form_super_pod(self, pod_ids: list[str], shared_objective: str = "") -> SuperPod | None:
        """
        Form a Super-Pod when the TopologyEngine detects that
        pods have interdependent objectives.
        """
        valid_pods = [pid for pid in pod_ids if pid in self._pods and not self._pods[pid].completed]
        if len(valid_pods) < 2:
            return None

        sp = SuperPod(
            pod_ids=valid_pods,
            shared_objective=shared_objective,
            shared_context={},
        )

        self._super_pods[sp.id] = sp

        logger.info(
            "pod: super-pod '%s' formed — %d pods, objective='%s'",
            sp.id,
            len(valid_pods),
            shared_objective[:60],
        )
        return sp

    # ------------------------------------------------------------------
    # Swarm (Level 3 — full mobilization)
    # ------------------------------------------------------------------

    async def activate_swarm(self, reason: str) -> None:
        """
        Full mobilization — all agents align in one direction.
        Rare: equivalent to the entire flock fleeing a predator.
        """
        self._swarm_active = True
        logger.warning("pod: SWARM ACTIVATED — '%s'", reason)

    async def deactivate_swarm(self) -> None:
        self._swarm_active = False
        logger.info("pod: swarm deactivated")

    @property
    def is_swarm_active(self) -> bool:
        return self._swarm_active

    # ------------------------------------------------------------------
    # Pending request matching (called periodically)
    # ------------------------------------------------------------------

    async def match_pending(self) -> list[Pod]:
        """Try to match pending alliance requests with newly available agents."""
        formed = []
        still_pending = []

        for request in self._pending_requests:
            pod = await self.request_alliance(request)
            if pod:
                formed.append(pod)
            else:
                still_pending.append(request)

        self._pending_requests = still_pending
        return formed

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_pod(self, pod_id: str) -> Pod | None:
        return self._pods.get(pod_id)

    def get_agent_pod(self, agent_id: str) -> Pod | None:
        pod_id = self._agent_pod_map.get(agent_id)
        return self._pods.get(pod_id) if pod_id else None

    def get_active_pods(self) -> list[Pod]:
        return [p for p in self._pods.values() if not p.completed]

    def get_active_super_pods(self) -> list[SuperPod]:
        return [sp for sp in self._super_pods.values() if not sp.completed]

    def summary(self) -> dict:
        active_pods = self.get_active_pods()
        return {
            "active_pods": len(active_pods),
            "completed_pods": sum(1 for p in self._pods.values() if p.completed),
            "super_pods": len(self.get_active_super_pods()),
            "swarm_active": self._swarm_active,
            "pending_requests": len(self._pending_requests),
            "agents_in_pods": len(self._agent_pod_map),
        }
