"""
Tests for symbiont.federation — Federation (multi-organism communication).

Coverage targets:
- Constructor: default organism_id, custom id, peer loading from store
- register_peer: in-memory + persistence
- remove_peer: existing / nonexistent
- peers / alive_peers properties
- _http_post / _http_get: success and failure paths
- receive_heartbeat: known and unknown peer
- send_heartbeat: success / failure (mocked HTTP)
- heartbeat_all: multiple peers
- relay: happy path, unknown peer
- broadcast: multiple alive peers
- route_task: selects least loaded peer
- federation_loop: runs one iteration (mocked asyncio.sleep)
- summary: structure and counts
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from symbiont.federation import Federation, HEARTBEAT_INTERVAL, PEER_TIMEOUT


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fed():
    return Federation(organism_id="local-org", bridge_url="http://localhost:7777")


@pytest.fixture
def fed_with_peer(fed):
    fed.register_peer("remote-1", "http://10.0.0.2:7777", name="RemoteOne")
    return fed


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

class TestConstructor:

    def test_default_organism_id(self):
        f = Federation()
        assert f.organism_id.startswith("org-")
        assert len(f.organism_id) > 4

    def test_custom_organism_id(self):
        f = Federation(organism_id="my-org")
        assert f.organism_id == "my-org"

    def test_bridge_url(self):
        f = Federation(bridge_url="http://custom:8888")
        assert f.bridge_url == "http://custom:8888"

    def test_loads_peers_from_store(self):
        store = MagicMock()
        store.load_peers.return_value = {
            "peer-1": {"name": "P1", "url": "http://p1:7777",
                       "last_heartbeat": time.time(), "metadata": {}}
        }
        f = Federation(store=store)
        assert "peer-1" in f.peers
        store.load_peers.assert_called_once()

    def test_no_store_starts_empty(self, fed):
        assert fed.peers == {}


# ---------------------------------------------------------------------------
# register_peer / remove_peer
# ---------------------------------------------------------------------------

class TestPeerManagement:

    def test_register_peer_in_memory(self, fed):
        fed.register_peer("p1", "http://p1:7777", name="P1")
        assert "p1" in fed.peers
        assert fed.peers["p1"]["url"] == "http://p1:7777"
        assert fed.peers["p1"]["name"] == "P1"

    def test_register_peer_persists(self):
        store = MagicMock()
        store.load_peers.return_value = {}
        f = Federation(store=store)
        f.register_peer("p2", "http://p2:7777", name="P2", metadata={"k": "v"})
        store.save_peer.assert_called_once_with("p2", "P2", "http://p2:7777", {"k": "v"})

    def test_register_peer_strips_trailing_slash(self, fed):
        fed.register_peer("p3", "http://p3:7777/", name="P3")
        assert fed.peers["p3"]["url"] == "http://p3:7777"

    def test_register_uses_id_as_name_when_empty(self, fed):
        fed.register_peer("lonely", "http://lonely:7777")
        assert fed.peers["lonely"]["name"] == "lonely"

    def test_remove_existing_peer(self, fed_with_peer):
        result = fed_with_peer.remove_peer("remote-1")
        assert result is True
        assert "remote-1" not in fed_with_peer.peers

    def test_remove_nonexistent_peer(self, fed):
        result = fed.remove_peer("ghost")
        assert result is False


# ---------------------------------------------------------------------------
# peers / alive_peers properties
# ---------------------------------------------------------------------------

class TestProperties:

    def test_peers_returns_copy(self, fed_with_peer):
        peers = fed_with_peer.peers
        peers["injected"] = {}
        assert "injected" not in fed_with_peer.peers

    def test_alive_peers_includes_recent(self, fed):
        fed.register_peer("fresh", "http://fresh:7777")
        # heartbeat just set by register_peer
        assert "fresh" in fed.alive_peers

    def test_alive_peers_excludes_stale(self, fed):
        fed.register_peer("stale", "http://stale:7777")
        fed._peers["stale"]["last_heartbeat"] = time.time() - (PEER_TIMEOUT + 10)
        assert "stale" not in fed.alive_peers


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

class TestHTTPHelpers:

    def test_http_post_success(self, fed):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fed._http_post("http://peer:7777/webhook", {"msg": "hello"})
        assert result == {"ok": True}

    def test_http_post_failure_returns_none(self, fed):
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = fed._http_post("http://dead:7777/webhook", {})
        assert result is None

    def test_http_get_success(self, fed):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"status": "ok"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fed._http_get("http://peer:7777/status")
        assert result == {"status": "ok"}

    def test_http_get_failure_returns_none(self, fed):
        with patch("urllib.request.urlopen", side_effect=Exception("refused")):
            result = fed._http_get("http://dead:7777/status")
        assert result is None


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

class TestHeartbeat:

    @pytest.mark.asyncio
    async def test_send_heartbeat_success(self, fed_with_peer):
        with patch.object(fed_with_peer, "_http_post", return_value={"ok": True}) as mock_post:
            result = await fed_with_peer.send_heartbeat("remote-1")
        assert result is True
        mock_post.assert_called_once()
        args = mock_post.call_args[0]
        assert "/federation/heartbeat" in args[0]

    @pytest.mark.asyncio
    async def test_send_heartbeat_failure(self, fed_with_peer):
        with patch.object(fed_with_peer, "_http_post", return_value=None):
            result = await fed_with_peer.send_heartbeat("remote-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_heartbeat_unknown_peer(self, fed):
        result = await fed.send_heartbeat("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_heartbeat_updates_timestamp(self, fed_with_peer):
        old_ts = fed_with_peer._peers["remote-1"]["last_heartbeat"]
        await asyncio.sleep(0.01)
        with patch.object(fed_with_peer, "_http_post", return_value={"ok": True}):
            await fed_with_peer.send_heartbeat("remote-1")
        new_ts = fed_with_peer._peers["remote-1"]["last_heartbeat"]
        assert new_ts >= old_ts

    @pytest.mark.asyncio
    async def test_heartbeat_all(self, fed):
        fed.register_peer("p1", "http://p1:7777")
        fed.register_peer("p2", "http://p2:7777")
        with patch.object(fed, "_http_post", return_value={"ok": True}):
            results = await fed.heartbeat_all()
        assert set(results.keys()) == {"p1", "p2"}
        assert all(results.values())

    def test_receive_heartbeat_known_peer(self, fed_with_peer):
        old_ts = fed_with_peer._peers["remote-1"]["last_heartbeat"]
        time.sleep(0.01)
        resp = fed_with_peer.receive_heartbeat("remote-1", "http://10.0.0.2:7777")
        assert resp["ok"] is True
        assert fed_with_peer._peers["remote-1"]["last_heartbeat"] > old_ts

    def test_receive_heartbeat_unknown_peer(self, fed):
        resp = fed.receive_heartbeat("new-peer", "http://new:7777")
        assert resp["ok"] is True
        assert "new-peer" in fed.peers

    def test_receive_heartbeat_returns_own_id(self, fed):
        resp = fed.receive_heartbeat("x", "http://x:7777")
        assert resp["organism_id"] == fed.organism_id


# ---------------------------------------------------------------------------
# Message Relay
# ---------------------------------------------------------------------------

class TestRelay:

    @pytest.mark.asyncio
    async def test_relay_to_known_peer(self, fed_with_peer):
        with patch.object(fed_with_peer, "_http_post", return_value={"status": "queued"}) as mock_post:
            result = await fed_with_peer.relay(
                "remote-1", channel="task.coding", payload={"task": "hello"}
            )
        assert result == {"status": "queued"}
        args = mock_post.call_args[0]
        assert "/webhook" in args[0]
        assert args[1]["channel"] == "task.coding"

    @pytest.mark.asyncio
    async def test_relay_to_unknown_peer_returns_none(self, fed):
        result = await fed.relay("ghost", channel="x", payload={})
        assert result is None

    @pytest.mark.asyncio
    async def test_relay_sets_sender_prefix(self, fed_with_peer):
        with patch.object(fed_with_peer, "_http_post", return_value={}) as mock_post:
            await fed_with_peer.relay("remote-1", channel="ch", payload={})
        body = mock_post.call_args[0][1]
        assert body["sender"].startswith("federation:")

    @pytest.mark.asyncio
    async def test_relay_custom_sender(self, fed_with_peer):
        with patch.object(fed_with_peer, "_http_post", return_value={}) as mock_post:
            await fed_with_peer.relay("remote-1", "ch", {}, sender="custom-agent")
        body = mock_post.call_args[0][1]
        assert body["sender"] == "custom-agent"


# ---------------------------------------------------------------------------
# Broadcast
# ---------------------------------------------------------------------------

class TestBroadcast:

    @pytest.mark.asyncio
    async def test_broadcast_reaches_all_alive(self, fed):
        fed.register_peer("p1", "http://p1:7777")
        fed.register_peer("p2", "http://p2:7777")
        with patch.object(fed, "_http_post", return_value={"ok": True}):
            results = await fed.broadcast("announcements", {"msg": "hello"})
        assert set(results.keys()) == {"p1", "p2"}

    @pytest.mark.asyncio
    async def test_broadcast_skips_stale_peers(self, fed):
        fed.register_peer("alive", "http://alive:7777")
        fed.register_peer("dead", "http://dead:7777")
        fed._peers["dead"]["last_heartbeat"] = time.time() - (PEER_TIMEOUT + 10)
        with patch.object(fed, "_http_post", return_value={"ok": True}):
            results = await fed.broadcast("ch", {})
        assert "alive" in results
        assert "dead" not in results

    @pytest.mark.asyncio
    async def test_broadcast_empty_when_no_peers(self, fed):
        results = await fed.broadcast("ch", {})
        assert results == {}


# ---------------------------------------------------------------------------
# Task Routing
# ---------------------------------------------------------------------------

class TestRouteTask:

    @pytest.mark.asyncio
    async def test_route_to_least_loaded(self, fed):
        fed.register_peer("busy-org", "http://busy:7777")
        fed.register_peer("free-org", "http://free:7777")

        def mock_get(url, timeout=10):
            if "busy" in url:
                return {"agents": {"by_state": {"BUSY": 8}, "total": 10}}
            if "free" in url:
                return {"agents": {"by_state": {"BUSY": 1}, "total": 10}}
            return None

        with patch.object(fed, "_http_get", side_effect=mock_get), \
             patch.object(fed, "_http_post", return_value={"result": "done"}) as mock_post:
            result = await fed.route_task("Analyze contract", context={"priority": "high"})

        assert result is not None
        assert result["routed_to"] == "free-org"

    @pytest.mark.asyncio
    async def test_route_returns_none_when_no_alive_peers(self, fed):
        result = await fed.route_task("any task")
        assert result is None

    @pytest.mark.asyncio
    async def test_route_task_includes_routed_to_field(self, fed):
        fed.register_peer("solo", "http://solo:7777")
        with patch.object(fed, "_http_get", return_value={"agents": {"by_state": {}, "total": 1}}), \
             patch.object(fed, "_http_post", return_value={"status": "ok"}):
            result = await fed.route_task("do something")
        assert result["routed_to"] == "solo"


# ---------------------------------------------------------------------------
# Federation Loop
# ---------------------------------------------------------------------------

class TestFederationLoop:

    @pytest.mark.asyncio
    async def test_loop_runs_one_iteration(self, fed):
        fed.register_peer("p1", "http://p1:7777")
        call_count = {"n": 0}

        async def fake_sleep(interval):
            call_count["n"] += 1
            if call_count["n"] >= 1:
                raise asyncio.CancelledError

        with patch.object(fed, "_http_post", return_value={"ok": True}), \
             patch("asyncio.sleep", side_effect=fake_sleep):
            with pytest.raises(asyncio.CancelledError):
                await fed.federation_loop(interval=0)

        assert call_count["n"] >= 1

    @pytest.mark.asyncio
    async def test_loop_prunes_dead_peers(self, fed):
        fed.register_peer("dead-peer", "http://dead:7777")
        fed._peers["dead-peer"]["last_heartbeat"] = time.time() - (PEER_TIMEOUT + 10)

        call_count = {"n": 0}

        async def fake_sleep(interval):
            call_count["n"] += 1
            raise asyncio.CancelledError

        with patch.object(fed, "_http_post", return_value={"ok": False}), \
             patch("asyncio.sleep", side_effect=fake_sleep):
            with pytest.raises(asyncio.CancelledError):
                await fed.federation_loop(interval=0)

        assert "dead-peer" not in fed.peers


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class TestSummary:

    def test_summary_structure(self, fed):
        fed.register_peer("p1", "http://p1:7777", name="Peer1")
        s = fed.summary()
        assert s["organism_id"] == "local-org"
        assert s["bridge_url"] == "http://localhost:7777"
        assert s["total_peers"] == 1
        assert "p1" in s["peers"]
        assert "name" in s["peers"]["p1"]
        assert "url" in s["peers"]["p1"]
        assert "alive" in s["peers"]["p1"]
        assert "last_heartbeat" in s["peers"]["p1"]

    def test_summary_alive_count(self, fed):
        fed.register_peer("alive", "http://alive:7777")
        fed.register_peer("dead", "http://dead:7777")
        fed._peers["dead"]["last_heartbeat"] = time.time() - (PEER_TIMEOUT + 10)
        s = fed.summary()
        assert s["alive_peers"] == 1
        assert s["total_peers"] == 2

    def test_summary_empty(self, fed):
        s = fed.summary()
        assert s["total_peers"] == 0
        assert s["alive_peers"] == 0
        assert s["peers"] == {}
