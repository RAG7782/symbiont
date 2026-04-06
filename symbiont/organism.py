"""
SYMBIONT Organism — the unified living system.

This is the integration layer that wires all 8 biological systems together
and manages the lifecycle of the organism. It is NOT an orchestrator —
it is the body in which the systems live and operate autonomously.

Think of it as the "body plan" (Bauplan) of the organism:
it defines the structure, but behavior emerges from the systems.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from symbiont.config import SymbiontConfig
from symbiont.handoffs import HANDOFF_MATRIX, can_handoff, can_escalate, summary as handoff_summary
from symbiont.core.mycelium import Mycelium
from symbiont.core.topology import TopologyEngine
from symbiont.core.castes import CasteRegistry
from symbiont.core.waggle import WaggleProtocol
from symbiont.core.mound import Mound
from symbiont.core.murmuration import MurmurationBus
from symbiont.core.governance import Governor
from symbiont.core.pod import PodDynamics
from symbiont.agents.base import BaseAgent
from symbiont.agents.queen import QueenAgent
from symbiont.agents.scout import ScoutAgent
from symbiont.agents.worker import WorkerAgent
from symbiont.agents.major import MajorAgent
from symbiont.agents.minima import MinimaAgent
from symbiont.types import (
    AgentState,
    AllianceRequest,
    Caste,
    Phase,
    QuorumLevel,
    Signal,
    SignalType,
    WaggleReport,
    _uid,
)

logger = logging.getLogger(__name__)

# Map caste to agent class
_CASTE_AGENT_MAP: dict[Caste, type[BaseAgent]] = {
    Caste.MINIMA: MinimaAgent,
    Caste.MEDIA: WorkerAgent,
    Caste.MAJOR: MajorAgent,
    Caste.SCOUT: ScoutAgent,
    Caste.QUEEN: QueenAgent,
}


class Symbiont:
    """
    The SYMBIONT organism.

    Integrates all 8 biological systems into a unified living system.
    The organism boots, runs, and can be gracefully shut down.

    Nine Laws of SYMBIONT:
    1. No agent knows the global plan
    2. The network is smarter than any node
    3. Artifacts are communication
    4. Exploration never stops
    5. Leadership is contextual, not hierarchical
    6. Governance by presence, not command
    7. 7 neighbors suffice
    8. Reserve is strategy, not waste
    9. Alliances are ephemeral
    """

    def __init__(self, config: SymbiontConfig | None = None) -> None:
        self.config = config or SymbiontConfig()

        # --- The 8 Systems ---
        self.mycelium = Mycelium()
        self.topology = TopologyEngine(self.config.topology)
        self.castes = CasteRegistry(self.config.castes)
        self.waggle = WaggleProtocol(self.config.waggle)
        self.mound = Mound(self.config.homeostasis)
        self.murmuration = MurmurationBus(self.config.murmuration)
        self.governor = Governor(self.config.governance)
        self.pods = PodDynamics()

        # --- Agent registry ---
        self._agents: dict[str, BaseAgent] = {}
        self._queen: QueenAgent | None = None

        # --- LLM backend (pluggable) ---
        self._llm_backend: Any = None
        self._tools: Any = None

        # --- State ---
        self._running = False
        self._boot_complete = False

        # --- Auto-detect tools ---
        try:
            from symbiont.tools import ToolRegistry
            self._tools = ToolRegistry()
        except Exception:
            pass

    # ==================================================================
    # LLM Backend
    # ==================================================================

    def set_llm_backend(self, backend: Any) -> None:
        """
        Set the LLM backend for all agents.

        The backend must implement:
            async def complete(self, prompt: str, context: dict, model_tier: str) -> str
        """
        self._llm_backend = backend
        for agent in self._agents.values():
            agent.set_llm_backend(backend)

    # ==================================================================
    # Boot Sequence
    # ==================================================================

    async def boot(self) -> None:
        """
        Boot the organism. Wires all systems together and spawns
        the initial population of agents.
        """
        logger.info("=== SYMBIONT: booting ===")

        # 1. Wire the TopologyEngine to the Mycelium
        self.topology.wire(self.mycelium)

        # 2. Wire the Waggle Protocol's scout dispatcher
        self.waggle.set_scout_dispatcher(self._dispatch_scout)

        # 3. Register homeostasis feedback handlers
        self.mound.register_feedback_handler("latency", self._on_high_latency)
        self.mound.register_feedback_handler("error_rate", self._on_high_errors)

        # 4. Register murmuration reflexes
        self.murmuration.register_reflex(SignalType.HALT, self._reflex_halt)
        self.murmuration.register_reflex(SignalType.HUMAN_OVERRIDE, self._reflex_human_override)

        # 5. Spawn the Queen first
        self._queen = await self._create_agent(Caste.QUEEN)
        if isinstance(self._queen, QueenAgent):
            self._queen.wire_registry(self.castes)
            self._queen.set_spawn_function(self._spawn_agent)

        # 6. Spawn initial population
        initial_population = {
            Caste.SCOUT: 2,
            Caste.MEDIA: 2,
            Caste.MAJOR: 1,
            Caste.MINIMA: 3,
        }
        for caste, count in initial_population.items():
            for _ in range(count):
                await self._spawn_agent(caste)

        # 7. Start background systems
        await self.topology.start()
        await self.murmuration.start()
        await self.mound.start_homeostasis()

        # 8. Auto-assign murmuration neighbors for all agents
        self._reassign_neighbors()

        self._running = True
        self._boot_complete = True
        logger.info(
            "=== SYMBIONT: booted — %d agents, %d systems online ===",
            len(self._agents),
            8,
        )

    async def shutdown(self) -> None:
        """Gracefully shut down the organism."""
        logger.info("=== SYMBIONT: shutting down ===")
        self._running = False

        # Stop background systems
        await self.topology.stop()
        await self.murmuration.stop()
        await self.mound.stop_homeostasis()

        # Stop all agents
        for agent in list(self._agents.values()):
            await agent.stop()

        self._agents.clear()
        logger.info("=== SYMBIONT: shutdown complete ===")

    # ==================================================================
    # Agent Lifecycle
    # ==================================================================

    async def _create_agent(self, caste: Caste) -> BaseAgent:
        """Create, wire, and start a new agent."""
        agent_cls = _CASTE_AGENT_MAP[caste]
        agent = agent_cls()

        # Wire to all systems
        agent.wire(self.mycelium, self.mound, self.murmuration, self.governor)

        if self._llm_backend:
            agent.set_llm_backend(self._llm_backend)

        # Wire tools to Workers
        if self._tools and hasattr(agent, 'set_tools'):
            agent.set_tools(self._tools)

        # Register capabilities with PodDynamics
        self.pods.register_capabilities(agent.id, agent.capabilities)

        # Start the agent
        await agent.start()

        self._agents[agent.id] = agent
        return agent

    async def _spawn_agent(self, caste: Caste) -> BaseAgent | None:
        """
        Spawn a new agent. Used by the Queen via spawn function.
        Checks governance suppression and caste capacity.
        """
        # Check if we can spawn (mole-rat suppression)
        requester = self._queen.id if self._queen else ""
        if not self.governor.can_spawn(requester):
            logger.warning("symbiont: spawn suppressed for caste %s", caste.name)
            return None

        if not self.castes.can_spawn(caste):
            # Try activating a reserve first (mole-rat reserve pool)
            reserve_id = self.governor.activate_reserve(caste)
            if reserve_id and reserve_id in self._agents:
                agent = self._agents[reserve_id]
                await agent.wake()
                logger.info("symbiont: activated reserve '%s' instead of spawning", reserve_id)
                return agent
            logger.warning("symbiont: cannot spawn %s — at capacity, no reserves", caste.name)
            return None

        agent = await self._create_agent(caste)
        self.castes.register_birth(caste)

        # Reassign neighbors to include the new agent
        self._reassign_neighbors()

        return agent

    def _reassign_neighbors(self) -> None:
        """Reassign murmuration neighbors for all agents."""
        all_ids = list(self._agents.keys())
        caste_map = {a.id: a.caste.name for a in self._agents.values()}
        for agent_id in all_ids:
            self.murmuration.auto_assign_neighbors(agent_id, all_ids, caste_map)

    # ==================================================================
    # Task Execution (the primary interface)
    # ==================================================================

    async def execute(self, task: str, context: dict | None = None, images: list | None = None) -> dict:
        """
        Execute a task through the SYMBIONT organism.

        This is the main entry point. The organism:
        1. EXPLORATION: Scouts explore the task
        2. DECISION: Waggle Protocol decides approach
        3. EXECUTION: Workers execute the chosen approach
        4. VALIDATION: Review the results
        5. DELIVERY: Return the final output

        Args:
            task: The task description
            context: Optional context dict
            images: Optional list of image paths/bytes for multimodal tasks

        The human calls this method — everything else is emergent.
        """
        if not self._running:
            raise RuntimeError("SYMBIONT is not running. Call boot() first.")

        context = context or {}
        task_id = _uid()

        logger.info("symbiont: executing task '%s' (id=%s)", task[:80], task_id)

        # --- Phase 1: EXPLORATION (Scouts lead) ---
        await self.governor.transition_to(Phase.EXPLORATION)

        # Signal demand for scouts if we don't have enough
        active_scouts = [
            a for a in self._agents.values()
            if a.caste == Caste.SCOUT and a.state == AgentState.ACTIVE
        ]
        if len(active_scouts) < 2:
            self.castes.signal_demand(Caste.SCOUT, intensity=2)
            if self._queen:
                await self._queen.execute("check_demand")

        # --- Phase 2: DECISION (Waggle Protocol) ---
        await self.governor.transition_to(Phase.DECISION)

        quorum_level = self._determine_quorum_level(task, context)
        session = await self.waggle.initiate(
            session_id=task_id,
            question=task,
            quorum_level=quorum_level,
        )

        chosen_approach = session.decision or task

        # If no decision and we have a Major, ask for tiebreak
        if not session.decided:
            majors = [
                a for a in self._agents.values()
                if a.caste == Caste.MAJOR and a.state == AgentState.ACTIVE
            ]
            if majors:
                major = majors[0]
                tiebreak_result = await major.execute(task, {
                    "type": "tiebreak",
                    "tally": session.tally(),
                    "reports": [r.__dict__ for r in session.reports],
                })
                chosen_approach = tiebreak_result.get("decision", task)

        # --- Phase 3: EXECUTION (Workers lead) ---
        await self.governor.transition_to(Phase.EXECUTION)

        # Find or form a Pod for execution
        workers = [
            a for a in self._agents.values()
            if a.caste == Caste.MEDIA and a.state == AgentState.ACTIVE
        ]
        if not workers:
            self.castes.signal_demand(Caste.MEDIA, intensity=2)
            if self._queen:
                await self._queen.execute("check_demand")
            workers = [
                a for a in self._agents.values()
                if a.caste == Caste.MEDIA and a.state == AgentState.ACTIVE
            ]

        execution_result = None
        if workers:
            worker = workers[0]
            exec_context = {**context, "session": session.id, "approach": chosen_approach}
            if images:
                exec_context["images"] = images
            execution_result = await worker.execute(
                chosen_approach,
                exec_context,
            )

        # --- Phase 4: VALIDATION (Major reviews) ---
        await self.governor.transition_to(Phase.VALIDATION)

        validation_result = None
        if execution_result and execution_result.get("artifact_id"):
            reviewers = [
                a for a in self._agents.values()
                if a.caste in (Caste.MAJOR, Caste.MEDIA)
                and a.state == AgentState.ACTIVE
                and a.id != (workers[0].id if workers else "")
            ]
            if reviewers:
                reviewer = reviewers[0]
                if hasattr(reviewer, '_review_artifact'):
                    validation_result = await reviewer._review_artifact(
                        execution_result["artifact_id"]
                    )

        # --- Phase 5: DELIVERY ---
        await self.governor.transition_to(Phase.DELIVERY)

        result = {
            "task_id": task_id,
            "task": task,
            "approach": chosen_approach,
            "waggle_session": {
                "decided": session.decided,
                "decision": session.decision,
                "reports_count": len(session.reports),
                "tally": session.tally(),
            },
            "execution": execution_result,
            "validation": validation_result,
            "phase_history": [
                (p.name, t) for p, t in self.governor._phase_history[-5:]
            ],
        }

        logger.info("symbiont: task '%s' complete", task_id)

        # Cycle back to exploration for next task
        await self.governor.transition_to(Phase.EXPLORATION)

        return result

    # ==================================================================
    # Waggle Scout Dispatcher
    # ==================================================================

    async def _dispatch_scout(self, session_id: str, question: str) -> WaggleReport | None:
        """Dispatch a scout to explore a question (used by Waggle Protocol)."""
        scouts = [
            a for a in self._agents.values()
            if a.caste == Caste.SCOUT and a.state == AgentState.ACTIVE
        ]
        if not scouts:
            return None

        # Round-robin: pick the least busy scout
        scout = min(scouts, key=lambda s: 1 if s.state == AgentState.BUSY else 0)
        result = await scout.execute(question, {"session_id": session_id})

        if isinstance(result, WaggleReport):
            return result
        return None

    # ==================================================================
    # Pod Formation (Dolphin dynamics)
    # ==================================================================

    async def form_pod(self, requester_id: str, objective: str, needed_capabilities: set[str]) -> Any:
        """Form a Pod for a collaborative task."""
        request = AllianceRequest(
            requester_id=requester_id,
            needed_capabilities=needed_capabilities,
            objective=objective,
        )
        return await self.pods.request_alliance(request)

    # ==================================================================
    # Homeostasis Feedback Handlers (Termite ventilation)
    # ==================================================================

    async def _on_high_latency(self, metric: str, value: float) -> None:
        """Feedback loop: high latency → rebalance topology."""
        logger.warning("symbiont: homeostasis — high latency (%.0fms), rebalancing", value)
        await self.topology.run_cycle()

    async def _on_high_errors(self, metric: str, value: float) -> None:
        """Feedback loop: high errors → spawn more Majors for oversight."""
        logger.warning("symbiont: homeostasis — high error rate (%.2f), adding oversight", value)
        self.castes.signal_demand(Caste.MAJOR, intensity=1)
        if self._queen:
            await self._queen.execute("check_demand")

    # ==================================================================
    # Reflexes (Murmuration — bypass deliberation)
    # ==================================================================

    async def _reflex_halt(self, signal: Signal) -> None:
        """REFLEX: halt all work immediately."""
        logger.warning("symbiont: REFLEX HALT — stopping all agents")
        for agent in self._agents.values():
            if agent.state == AgentState.BUSY:
                agent.clear_current_task()

    async def _reflex_human_override(self, signal: Signal) -> None:
        """REFLEX: human override — enter consultive mode."""
        logger.info("symbiont: REFLEX — human override, entering consultive mode")
        self.governor.set_human_present(True)

    # ==================================================================
    # Quorum Level Determination
    # ==================================================================

    def _determine_quorum_level(self, task: str, context: dict) -> QuorumLevel:
        """Determine how much quorum a decision needs based on task characteristics."""
        task_lower = task.lower()

        # Irreversible / high-risk
        if any(w in task_lower for w in ("deploy", "delete", "production", "migration")):
            return QuorumLevel.CRITICAL
        # Architecture / expensive
        if any(w in task_lower for w in ("architecture", "redesign", "refactor")):
            return QuorumLevel.HIGH
        # Moderate
        if any(w in task_lower for w in ("implement", "feature", "create")):
            return QuorumLevel.MEDIUM
        # Reversible / low risk
        return QuorumLevel.LOW

    # ==================================================================
    # Status & Introspection
    # ==================================================================

    def status(self) -> dict:
        """Return the full organism status — a health dashboard."""
        return {
            "running": self._running,
            "agents": {
                "total": len(self._agents),
                "by_caste": self.castes.get_population(),
                "by_state": self._count_by_state(),
            },
            "governance": self.governor.summary(),
            "handoffs": handoff_summary(),
            "pods": self.pods.summary(),
            "murmuration": self.murmuration.topology_summary(),
            "topology": {
                "channels": self.mycelium.total_channels,
                "optimization_cycles": self.topology.cycle_count,
            },
            "mound": {
                "artifacts": self.mound.artifact_count,
                "health": {
                    "is_healthy": self.mound.health.is_healthy(),
                    "latency_ms": self.mound.health.latency_ms,
                    "error_rate": self.mound.health.error_rate,
                },
            },
        }

    def _count_by_state(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for agent in self._agents.values():
            state_name = agent.state.name
            counts[state_name] = counts.get(state_name, 0) + 1
        return counts

    def get_agent(self, agent_id: str) -> BaseAgent | None:
        return self._agents.get(agent_id)

    def get_agents_by_caste(self, caste: Caste) -> list[BaseAgent]:
        return [a for a in self._agents.values() if a.caste == caste]

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def agent_count(self) -> int:
        return len(self._agents)
