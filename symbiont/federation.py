"""
SYMBIONT Federation — multi-organism communication.

Allows multiple SYMBIONT organisms (local + colonies) to:
- Discover each other via registration
- Exchange heartbeats to track liveness
- Relay messages between organisms via their HTTP bridges
- Route tasks to the best organism based on load/capabilities

Federation protocol:
1. Each organism registers with peers via POST /federation/register
2. Heartbeats every 60s via POST /federation/heartbeat
3. Message relay via POST /federation/relay
4. Task routing via POST /federation/route

Usage:
    fed = Federation(organism_id="local", bridge_url="http://localhost:7777")
    fed.register_peer("kai", "http://100.73.123.8:7777")
    await fed.relay("kai", channel="task.coding", payload={...})
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.request
import urllib.error
import uuid
from typing import Any

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 60  # seconds
PEER_TIMEOUT = 180       # seconds before peer considered dead


class Federation:
    """Multi-organism federation manager."""

    def __init__(self, organism_id: str | None = None, bridge_url: str = "http://localhost:7777",
                 store=None):
        self.organism_id = organism_id or f"org-{uuid.uuid4().hex[:8]}"
        self.bridge_url = bridge_url
        self._store = store  # PersistenceStore (optional)
        self._peers: dict[str, dict] = {}  # id → {name, url, last_heartbeat, metadata}

        # Load peers from persistence
        if self._store:
            self._peers = self._store.load_peers()
            logger.info("federation: loaded %d peers from store", len(self._peers))

    def register_peer(self, peer_id: str, url: str, name: str = "", metadata: dict | None = None):
        """Register a peer organism."""
        self._peers[peer_id] = {
            "name": name or peer_id,
            "url": url.rstrip("/"),
            "last_heartbeat": time.time(),
            "metadata": metadata or {},
        }
        if self._store:
            self._store.save_peer(peer_id, name or peer_id, url, metadata)
        logger.info("federation: registered peer %s at %s", peer_id, url)

    def remove_peer(self, peer_id: str) -> bool:
        if peer_id in self._peers:
            del self._peers[peer_id]
            return True
        return False

    @property
    def peers(self) -> dict[str, dict]:
        return dict(self._peers)

    @property
    def alive_peers(self) -> dict[str, dict]:
        cutoff = time.time() - PEER_TIMEOUT
        return {pid: p for pid, p in self._peers.items() if p["last_heartbeat"] > cutoff}

    def _http_post(self, url: str, data: dict, timeout: int = 10) -> dict | None:
        """Send a POST request to a peer."""
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.warning("federation: HTTP POST to %s failed: %s", url, e)
            return None

    def _http_get(self, url: str, timeout: int = 10) -> dict | None:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    async def send_heartbeat(self, peer_id: str) -> bool:
        """Send heartbeat to a specific peer."""
        if peer_id not in self._peers:
            return False
        peer = self._peers[peer_id]
        result = self._http_post(f"{peer['url']}/federation/heartbeat", {
            "organism_id": self.organism_id,
            "url": self.bridge_url,
            "timestamp": time.time(),
        })
        if result and result.get("ok"):
            peer["last_heartbeat"] = time.time()
            return True
        return False

    async def heartbeat_all(self) -> dict[str, bool]:
        """Send heartbeat to all peers."""
        results = {}
        for peer_id in list(self._peers.keys()):
            results[peer_id] = await self.send_heartbeat(peer_id)
        return results

    def receive_heartbeat(self, organism_id: str, url: str, **kwargs) -> dict:
        """Process incoming heartbeat from a peer."""
        if organism_id not in self._peers:
            self.register_peer(organism_id, url, metadata=kwargs)
        else:
            self._peers[organism_id]["last_heartbeat"] = time.time()
        return {"ok": True, "organism_id": self.organism_id}

    # ------------------------------------------------------------------
    # Message Relay
    # ------------------------------------------------------------------

    async def relay(self, peer_id: str, channel: str, payload: Any,
                    sender: str = "", priority: int = 5) -> dict | None:
        """Relay a message to a peer's Mycelium via their HTTP bridge."""
        if peer_id not in self._peers:
            logger.warning("federation: unknown peer %s", peer_id)
            return None

        peer = self._peers[peer_id]
        return self._http_post(f"{peer['url']}/webhook", {
            "channel": channel,
            "payload": payload,
            "sender": sender or f"federation:{self.organism_id}",
            "priority": priority,
        })

    async def broadcast(self, channel: str, payload: Any, sender: str = "", priority: int = 5) -> dict:
        """Broadcast a message to all alive peers."""
        results = {}
        for peer_id in self.alive_peers:
            results[peer_id] = await self.relay(peer_id, channel, payload, sender, priority)
        return results

    # ------------------------------------------------------------------
    # Task Routing
    # ------------------------------------------------------------------

    async def route_task(self, task: str, context: dict | None = None) -> dict | None:
        """Route a task to the least loaded peer."""
        best_peer = None
        best_load = float("inf")

        for peer_id, peer in self.alive_peers.items():
            status = self._http_get(f"{peer['url']}/status")
            if status:
                agents = status.get("agents", {})
                # Simple load metric: fewer busy agents = less loaded
                by_state = agents.get("by_state", {})
                busy = by_state.get("BUSY", 0)
                total = agents.get("total", 1)
                load = busy / max(total, 1)
                if load < best_load:
                    best_load = load
                    best_peer = peer_id

        if not best_peer:
            return None

        peer = self._peers[best_peer]
        result = self._http_post(f"{peer['url']}/task", {
            "task": task,
            "context": context or {},
        }, timeout=120)

        if result:
            result["routed_to"] = best_peer
        return result

    # ------------------------------------------------------------------
    # Background Loop
    # ------------------------------------------------------------------

    async def federation_loop(self, interval: int = HEARTBEAT_INTERVAL):
        """Background loop: heartbeat all peers, prune dead ones."""
        logger.info("federation: starting loop (interval=%ds)", interval)
        while True:
            try:
                await self.heartbeat_all()
                # Prune dead peers
                cutoff = time.time() - PEER_TIMEOUT
                dead = [pid for pid, p in self._peers.items() if p["last_heartbeat"] < cutoff]
                for pid in dead:
                    logger.warning("federation: peer %s is dead (no heartbeat), removing", pid)
                    self.remove_peer(pid)
            except Exception:
                logger.exception("federation: loop error")
            await asyncio.sleep(interval)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        alive = self.alive_peers
        return {
            "organism_id": self.organism_id,
            "bridge_url": self.bridge_url,
            "total_peers": len(self._peers),
            "alive_peers": len(alive),
            "peers": {
                pid: {"name": p["name"], "url": p["url"],
                      "alive": pid in alive,
                      "last_heartbeat": p["last_heartbeat"]}
                for pid, p in self._peers.items()
            },
        }
