"""
System 2 — TOPOLOGY ENGINE (Physarum polycephalum)

Neural optimization of the SYMBIONT organism. Observes flow in the Mycelium
and continuously optimizes the network topology.

Key biological properties:
- Explore phase: spawn probe agents in new directions
- Reinforce phase: thicken paths that produced good results
- Prune phase: atrophy idle connections
- Never "done" — perpetually seeking a better topology
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from symbiont.config import TopologyConfig

logger = logging.getLogger(__name__)


@dataclass
class PathRecord:
    """Track the history of a path (channel) for optimization."""
    channel: str
    flow_score: float = 0.0       # Accumulated quality of messages
    usage_count: int = 0
    last_reinforced: float = field(default_factory=time.time)
    idle_cycles: int = 0
    is_probe: bool = False         # Was this path created by exploration?


class TopologyEngine:
    """
    Physarum-inspired topology optimizer.

    Runs periodic cycles of explore/reinforce/prune on the Mycelium,
    converging toward an optimal network topology while maintaining
    a fixed exploration budget to avoid local optima.
    """

    def __init__(self, config: TopologyConfig | None = None) -> None:
        self.config = config or TopologyConfig()
        self._paths: dict[str, PathRecord] = {}
        self._cycle_count: int = 0
        self._running = False
        self._task: asyncio.Task | None = None
        # Callbacks set by the organism during wiring
        self._mycelium = None  # Set by organism
        self._queen = None     # Set by organism (for probe spawning)

    def wire(self, mycelium, queen=None) -> None:
        """Connect the engine to the Mycelium and optionally a Queen for probing."""
        self._mycelium = mycelium
        self._queen = queen

    async def start(self) -> None:
        """Start the continuous optimization loop."""
        self._running = True
        self._task = asyncio.create_task(self._optimization_loop())
        logger.info("topology-engine: started (explore_ratio=%.0f%%)", self.config.explore_ratio * 100)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("topology-engine: stopped after %d cycles", self._cycle_count)

    async def _optimization_loop(self) -> None:
        while self._running:
            try:
                await self.run_cycle()
                await asyncio.sleep(self.config.probe_interval_sec)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("topology-engine: cycle error")
                await asyncio.sleep(5)

    async def run_cycle(self) -> dict:
        """
        Execute one full Physarum cycle: snapshot → reinforce → prune → explore.
        Returns a report of actions taken.
        """
        self._cycle_count += 1
        report = {"cycle": self._cycle_count, "reinforced": [], "pruned": [], "probes": []}

        if not self._mycelium:
            return report

        # 1. Snapshot current topology (channels with subscribers + channels with stats)
        topo = self._mycelium.query_topology()
        channels = topo.get("channels", {})
        # Also include channels that have stats but no subscribers yet
        for ch_name, stats in self._mycelium.get_channel_stats().items():
            if ch_name not in channels:
                channels[ch_name] = {
                    "subscribers": 0,
                    "message_count": stats.message_count,
                    "weight": stats.weight,
                    "idle_seconds": stats.idle_seconds,
                }

        # 2. Update path records from flow data
        for ch_name, ch_data in channels.items():
            if ch_name not in self._paths:
                self._paths[ch_name] = PathRecord(channel=ch_name)
            path = self._paths[ch_name]
            msg_count = ch_data.get("message_count", 0)
            if msg_count > path.usage_count:
                path.flow_score += (msg_count - path.usage_count) * ch_data.get("weight", 1.0)
                path.usage_count = msg_count
                path.idle_cycles = 0
            else:
                path.idle_cycles += 1

        # 3. Reinforce — thicken high-flow paths
        total_flow = sum(p.flow_score for p in self._paths.values()) or 1.0
        for path in self._paths.values():
            normalized = path.flow_score / total_flow
            if normalized >= self.config.reinforce_threshold / 10:  # Relative threshold
                self._mycelium.reinforce_channel(path.channel, factor=1.1 + normalized)
                path.last_reinforced = time.time()
                report["reinforced"].append(path.channel)

        # 4. Prune — atrophy idle paths
        to_prune = []
        for ch_name, path in self._paths.items():
            if path.idle_cycles >= self.config.prune_idle_cycles:
                self._mycelium.attenuate_channel(ch_name, factor=0.5)
                if path.idle_cycles >= self.config.prune_idle_cycles * 2:
                    to_prune.append(ch_name)
        for ch_name in to_prune:
            del self._paths[ch_name]
            report["pruned"].append(ch_name)

        # 5. Explore — spawn probes (fixed % of budget, never zero)
        probe_count = max(1, int(len(self._paths) * self.config.explore_ratio))
        if self._queen:
            for _ in range(probe_count):
                probe_channel = f"probe:{self._cycle_count}:{_}"
                self._paths[probe_channel] = PathRecord(channel=probe_channel, is_probe=True)
                report["probes"].append(probe_channel)

        if report["reinforced"] or report["pruned"] or report["probes"]:
            logger.info(
                "topology-engine: cycle %d — reinforced=%d, pruned=%d, probes=%d",
                self._cycle_count,
                len(report["reinforced"]),
                len(report["pruned"]),
                len(report["probes"]),
            )

        return report

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    def get_path_health(self) -> dict[str, dict]:
        """Return health status of all tracked paths."""
        return {
            ch: {
                "flow_score": p.flow_score,
                "usage_count": p.usage_count,
                "idle_cycles": p.idle_cycles,
                "is_probe": p.is_probe,
            }
            for ch, p in self._paths.items()
        }
