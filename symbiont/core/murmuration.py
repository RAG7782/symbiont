"""
System 6 — MURMURATION BUS (Sturnus vulgaris)

The autonomic nervous system of SYMBIONT. Real-time coordination for events
that cannot wait for deliberation. Each agent monitors 6-7 neighbors and
follows three impulses: repel, align, cohere.

Key biological properties:
- Each bird follows only 6-7 nearest neighbors (not all)
- Three rules: separation, alignment, cohesion
- Information propagates as a wave in O(log N)
- Reflexes bypass higher-level decision-making
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict

from symbiont.config import MurmurationConfig
from symbiont.types import Impulse, Signal, SignalType, SignalHandler

logger = logging.getLogger(__name__)


class _NeighborRecord:
    """Tracks the state of a neighbor."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.last_heartbeat: float = time.time()
        self.current_task: str = ""
        self.direction: str = ""  # Current work direction / priority

    @property
    def is_alive(self) -> bool:
        return (time.time() - self.last_heartbeat) < 30.0


class MurmurationBus:
    """
    Starling-inspired real-time coordination.

    Each agent monitors at most 7 neighbors. Signals propagate as waves
    through the neighbor graph. Reflexes trigger immediate action without
    consulting the Waggle Protocol or Governance.
    """

    def __init__(self, config: MurmurationConfig | None = None) -> None:
        self.config = config or MurmurationConfig()
        # agent_id → set of neighbor agent_ids
        self._neighbors: dict[str, dict[str, _NeighborRecord]] = defaultdict(dict)
        # Reflex handlers: signal_type → list of handlers
        self._reflexes: dict[SignalType, list[SignalHandler]] = defaultdict(list)
        # Signal log for debugging
        self._signal_log: list[Signal] = []
        self._max_log_size = 5_000
        self._running = False
        self._heartbeat_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Neighbor management (the "7 neighbors" rule)
    # ------------------------------------------------------------------

    def register_agent(self, agent_id: str) -> None:
        """Register an agent in the murmuration."""
        if agent_id not in self._neighbors:
            self._neighbors[agent_id] = {}

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent and clean up neighbor references."""
        self._neighbors.pop(agent_id, None)
        for neighbors in self._neighbors.values():
            neighbors.pop(agent_id, None)

    def add_neighbor(self, agent_id: str, neighbor_id: str) -> bool:
        """
        Add a neighbor link. Enforces the 7-neighbor maximum.
        Returns False if the agent already has max neighbors.
        """
        neighbors = self._neighbors.get(agent_id, {})
        if len(neighbors) >= self.config.max_neighbors:
            return False
        neighbors[neighbor_id] = _NeighborRecord(neighbor_id)
        self._neighbors[agent_id] = neighbors
        return True

    def remove_neighbor(self, agent_id: str, neighbor_id: str) -> None:
        neighbors = self._neighbors.get(agent_id, {})
        neighbors.pop(neighbor_id, None)

    def get_neighbors(self, agent_id: str) -> list[str]:
        return list(self._neighbors.get(agent_id, {}).keys())

    def auto_assign_neighbors(self, agent_id: str, all_agents: list[str], caste_map: dict[str, str] | None = None) -> None:
        """
        Automatically assign neighbors: 4-5 same caste + 2-3 different caste.
        This mirrors the biological observation: mostly same-type neighbors
        with some diversity for information cross-pollination.
        """
        caste_map = caste_map or {}
        my_caste = caste_map.get(agent_id, "")
        same_caste = [a for a in all_agents if a != agent_id and caste_map.get(a, "") == my_caste]
        diff_caste = [a for a in all_agents if a != agent_id and caste_map.get(a, "") != my_caste]

        # 4-5 same caste, 2-3 different caste (up to max_neighbors)
        max_same = min(5, len(same_caste))
        max_diff = min(self.config.max_neighbors - max_same, len(diff_caste))

        for neighbor_id in same_caste[:max_same]:
            self.add_neighbor(agent_id, neighbor_id)
        for neighbor_id in diff_caste[:max_diff]:
            self.add_neighbor(agent_id, neighbor_id)

    # ------------------------------------------------------------------
    # Signal propagation (wave)
    # ------------------------------------------------------------------

    async def emit(self, signal: Signal) -> int:
        """
        Emit a signal. It propagates through the neighbor graph as a wave.
        Returns the number of agents reached.
        """
        signal.seen_by.add(signal.source_id)
        self._log_signal(signal)

        # Check for reflexes first (bypass normal processing)
        if signal.signal_type in (SignalType.HALT, SignalType.REFLEX, SignalType.HUMAN_OVERRIDE):
            await self._trigger_reflex(signal)

        reached = await self._propagate(signal, signal.source_id)
        logger.debug(
            "murmuration: signal %s from '%s' reached %d agents (ttl=%d)",
            signal.signal_type.name,
            signal.source_id,
            reached,
            signal.ttl,
        )
        return reached

    async def _propagate(self, signal: Signal, from_id: str) -> int:
        """Recursive wave propagation through neighbor graph."""
        if signal.ttl <= 0:
            return 0

        neighbors = self._neighbors.get(from_id, {})
        reached = 0
        next_signals = []

        for neighbor_id, record in neighbors.items():
            if neighbor_id in signal.seen_by:
                continue
            signal.seen_by.add(neighbor_id)
            reached += 1

            # Apply impulses
            await self._apply_impulses(from_id, neighbor_id, signal)

            # Propagate further (with decremented TTL)
            child = Signal(
                signal_type=signal.signal_type,
                source_id=signal.source_id,
                payload=signal.payload,
                ttl=signal.ttl - 1,
                seen_by=signal.seen_by,
            )
            next_signals.append((child, neighbor_id))

        # Parallel propagation to all neighbors
        tasks = [
            asyncio.create_task(self._propagate(sig, nid))
            for sig, nid in next_signals
        ]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, int):
                    reached += r

        return reached

    # ------------------------------------------------------------------
    # Three Impulses (separation / alignment / cohesion)
    # ------------------------------------------------------------------

    async def _apply_impulses(self, from_id: str, to_id: str, signal: Signal) -> None:
        """Apply the three starling impulses based on signal content."""

        # REPEL: if neighbor is doing the same task, one should stop
        if signal.signal_type == SignalType.HEARTBEAT:
            from_record = self._get_record(to_id, from_id)
            to_neighbors = self._neighbors.get(to_id, {})
            if from_record and from_record.current_task:
                for other_id, other_record in to_neighbors.items():
                    if other_id != from_id and other_record.current_task == from_record.current_task:
                        logger.info(
                            "murmuration: REPEL — '%s' and '%s' duplicating task '%s'",
                            from_id, other_id, from_record.current_task,
                        )
                        # Emit a repel signal to the duplicate
                        await self.emit(Signal(
                            signal_type=SignalType.ALERT,
                            source_id=to_id,
                            payload={"impulse": Impulse.REPEL, "duplicate_task": from_record.current_task},
                            ttl=1,
                        ))

        # ALIGN: if majority of neighbors shifted priority, propagate
        if signal.signal_type == SignalType.PRIORITY_SHIFT:
            pass  # Alignment is implicit in wave propagation

        # COHERE: handled by heartbeat monitoring (see start_heartbeat_monitor)

    def _get_record(self, agent_id: str, neighbor_id: str) -> _NeighborRecord | None:
        return self._neighbors.get(agent_id, {}).get(neighbor_id)

    # ------------------------------------------------------------------
    # Reflexes (bypass Waggle Protocol)
    # ------------------------------------------------------------------

    def register_reflex(self, signal_type: SignalType, handler: SignalHandler) -> None:
        """Register a reflex handler — fires immediately, no deliberation."""
        self._reflexes[signal_type].append(handler)

    async def _trigger_reflex(self, signal: Signal) -> None:
        """Fire all reflex handlers for this signal type."""
        handlers = self._reflexes.get(signal.signal_type, [])
        for handler in handlers:
            try:
                await handler(signal)
            except Exception:
                logger.exception("murmuration: reflex handler error for %s", signal.signal_type.name)

    # ------------------------------------------------------------------
    # Heartbeat monitoring (COHERE impulse)
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("murmuration: bus started (max_neighbors=%d)", self.config.max_neighbors)

    async def stop(self) -> None:
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat_loop(self) -> None:
        while self._running:
            try:
                await self._check_cohesion()
                await asyncio.sleep(self.config.heartbeat_interval_sec)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("murmuration: heartbeat error")

    async def _check_cohesion(self) -> None:
        """COHERE: detect agents that lost contact with neighbors."""
        now = time.time()
        for agent_id, neighbors in list(self._neighbors.items()):
            dead_neighbors = [
                nid for nid, rec in neighbors.items()
                if (now - rec.last_heartbeat) > self.config.heartbeat_interval_sec * 3
            ]
            for dead_id in dead_neighbors:
                logger.warning(
                    "murmuration: COHERE — '%s' lost contact with '%s'",
                    agent_id, dead_id,
                )
                self.remove_neighbor(agent_id, dead_id)

    def record_heartbeat(self, agent_id: str, current_task: str = "", direction: str = "") -> None:
        """Record a heartbeat from an agent (updates all neighbor records)."""
        for neighbors in self._neighbors.values():
            if agent_id in neighbors:
                neighbors[agent_id].last_heartbeat = time.time()
                neighbors[agent_id].current_task = current_task
                neighbors[agent_id].direction = direction

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _log_signal(self, signal: Signal) -> None:
        self._signal_log.append(signal)
        if len(self._signal_log) > self._max_log_size:
            self._signal_log = self._signal_log[-self._max_log_size // 2:]

    @property
    def total_agents(self) -> int:
        return len(self._neighbors)

    def topology_summary(self) -> dict:
        return {
            "agents": len(self._neighbors),
            "connections": sum(len(n) for n in self._neighbors.values()),
            "avg_neighbors": (
                sum(len(n) for n in self._neighbors.values()) / max(1, len(self._neighbors))
            ),
        }
