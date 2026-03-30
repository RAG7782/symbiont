"""
System 1 — MYCELIUM (Mycorrhizal Fungus)

The circulatory system of SYMBIONT. Transports everything, connects everything,
decides nothing. Heterogeneous, fault-tolerant, with adaptive bandwidth.

Key biological properties:
- Hyphae (channels) connect agents of different "species"
- Hub nodes emerge naturally from topology (not designated)
- Channels thicken with use, atrophy with disuse
- The network IS intelligence — flow patterns carry information
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from symbiont.types import Message, MessageHandler, _uid

logger = logging.getLogger(__name__)


@dataclass
class _ChannelStats:
    """Tracks flow through a channel — basis for adaptive bandwidth."""
    message_count: int = 0
    total_bytes: int = 0
    last_active: float = field(default_factory=time.time)
    weight: float = 1.0  # Adaptive bandwidth: higher = more "thick"

    def record(self, size: int = 1) -> None:
        self.message_count += 1
        self.total_bytes += size
        self.last_active = time.time()

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_active


@dataclass
class _Subscription:
    """A subscriber on a channel."""
    subscriber_id: str
    handler: MessageHandler
    filter_fn: Any = None  # Optional predicate on Message


class Mycelium:
    """
    The connective substrate of the SYMBIONT organism.

    All agents communicate through the Mycelium — never directly.
    The Mycelium tracks flow patterns that the TopologyEngine uses
    to optimize the network.
    """

    def __init__(self) -> None:
        self._channels: dict[str, list[_Subscription]] = defaultdict(list)
        self._stats: dict[str, _ChannelStats] = defaultdict(_ChannelStats)
        self._message_log: list[Message] = []
        self._max_log_size = 10_000
        self._hub_scores: dict[str, float] = defaultdict(float)
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Publish / Subscribe
    # ------------------------------------------------------------------

    async def publish(
        self,
        channel: str,
        payload: Any,
        sender_id: str = "",
        priority: int = 5,
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        """Publish a message to a channel. All subscribers are notified."""
        msg = Message(
            channel=channel,
            sender_id=sender_id,
            payload=payload,
            priority=priority,
            metadata=metadata or {},
        )

        async with self._lock:
            self._stats[channel].record()
            self._hub_scores[sender_id] += 1.0
            self._log_message(msg)
            subs = list(self._channels.get(channel, []))

        # Fan-out to subscribers (parallel, non-blocking)
        tasks = []
        for sub in subs:
            if sub.filter_fn and not sub.filter_fn(msg):
                continue
            tasks.append(asyncio.create_task(self._safe_deliver(sub, msg)))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.debug("mycelium: published to '%s' (%d subs)", channel, len(tasks))
        return msg

    def subscribe(
        self,
        channel: str,
        subscriber_id: str,
        handler: MessageHandler,
        filter_fn: Any = None,
    ) -> str:
        """Subscribe to a channel. Returns subscription ID."""
        sub = _Subscription(
            subscriber_id=subscriber_id,
            handler=handler,
            filter_fn=filter_fn,
        )
        self._channels[channel].append(sub)
        self._hub_scores[subscriber_id] += 0.5  # Subscribing increases connectivity
        logger.debug("mycelium: '%s' subscribed to '%s'", subscriber_id, channel)
        return f"{channel}:{subscriber_id}"

    def unsubscribe(self, channel: str, subscriber_id: str) -> bool:
        """Remove a subscriber from a channel."""
        subs = self._channels.get(channel, [])
        before = len(subs)
        self._channels[channel] = [s for s in subs if s.subscriber_id != subscriber_id]
        return len(self._channels[channel]) < before

    # ------------------------------------------------------------------
    # Topology queries (used by TopologyEngine / Physarum)
    # ------------------------------------------------------------------

    def get_channel_stats(self) -> dict[str, _ChannelStats]:
        """Return flow statistics for all channels."""
        return dict(self._stats)

    def get_hub_nodes(self, top_n: int = 5) -> list[tuple[str, float]]:
        """
        Return the most connected nodes (hub trees in the mycorrhizal network).
        These are NOT leaders — they're topologically central brokers.
        """
        sorted_hubs = sorted(
            self._hub_scores.items(), key=lambda x: x[1], reverse=True
        )
        return sorted_hubs[:top_n]

    def get_active_channels(self) -> list[str]:
        """Return channels that have subscribers."""
        return [ch for ch, subs in self._channels.items() if subs]

    def get_subscriber_count(self, channel: str) -> int:
        return len(self._channels.get(channel, []))

    def query_topology(self) -> dict[str, Any]:
        """
        Return a snapshot of the network topology.
        Used by the TopologyEngine for optimization.
        """
        return {
            "channels": {
                ch: {
                    "subscribers": len(subs),
                    "message_count": self._stats[ch].message_count,
                    "weight": self._stats[ch].weight,
                    "idle_seconds": self._stats[ch].idle_seconds,
                }
                for ch, subs in self._channels.items()
            },
            "hub_nodes": self.get_hub_nodes(10),
            "total_messages": sum(s.message_count for s in self._stats.values()),
        }

    # ------------------------------------------------------------------
    # Adaptive bandwidth (called by TopologyEngine)
    # ------------------------------------------------------------------

    def reinforce_channel(self, channel: str, factor: float = 1.2) -> None:
        """Thicken a channel — it's being used productively (Physarum reinforce)."""
        self._stats[channel].weight *= factor
        logger.debug("mycelium: reinforced '%s' (weight=%.2f)", channel, self._stats[channel].weight)

    def attenuate_channel(self, channel: str, factor: float = 0.8) -> None:
        """Thin a channel — it's been idle (Physarum atrophy)."""
        stats = self._stats.get(channel)
        if stats:
            stats.weight *= factor
            if stats.weight < 0.1:
                self._prune_channel(channel)

    def _prune_channel(self, channel: str) -> None:
        """Remove a fully atrophied channel."""
        self._channels.pop(channel, None)
        self._stats.pop(channel, None)
        logger.info("mycelium: pruned dead channel '%s'", channel)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _log_message(self, msg: Message) -> None:
        self._message_log.append(msg)
        if len(self._message_log) > self._max_log_size:
            self._message_log = self._message_log[-self._max_log_size // 2:]

    @staticmethod
    async def _safe_deliver(sub: _Subscription, msg: Message) -> None:
        try:
            await sub.handler(msg)
        except Exception:
            logger.exception(
                "mycelium: delivery failed for '%s' on '%s'",
                sub.subscriber_id,
                msg.channel,
            )

    @property
    def recent_messages(self) -> list[Message]:
        return list(self._message_log[-100:])

    @property
    def total_channels(self) -> int:
        return len(self._channels)
