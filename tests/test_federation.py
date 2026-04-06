"""Tests for multi-organism federation."""

import os
import tempfile
import time

import pytest

from symbiont.federation import Federation
from symbiont.persistence import PersistenceStore


@pytest.fixture
def store():
    db = tempfile.mktemp(suffix=".db")
    s = PersistenceStore(db)
    yield s
    s.close()
    os.unlink(db)


class TestFederation:
    def test_create(self):
        fed = Federation(organism_id="test-org")
        assert fed.organism_id == "test-org"
        assert len(fed.peers) == 0

    def test_register_peer(self):
        fed = Federation()
        fed.register_peer("kai", "http://kai:7777", name="Kai Colony")
        assert "kai" in fed.peers
        assert fed.peers["kai"]["url"] == "http://kai:7777"

    def test_remove_peer(self):
        fed = Federation()
        fed.register_peer("kai", "http://kai:7777")
        assert fed.remove_peer("kai") is True
        assert fed.remove_peer("nonexistent") is False
        assert len(fed.peers) == 0

    def test_alive_peers(self):
        fed = Federation()
        fed.register_peer("alive", "http://alive:7777")
        fed.register_peer("dead", "http://dead:7777")
        # Make "dead" stale
        fed._peers["dead"]["last_heartbeat"] = time.time() - 300
        alive = fed.alive_peers
        assert "alive" in alive
        assert "dead" not in alive

    def test_receive_heartbeat_new_peer(self):
        fed = Federation(organism_id="local")
        result = fed.receive_heartbeat("remote", "http://remote:7777")
        assert result["ok"] is True
        assert "remote" in fed.peers

    def test_receive_heartbeat_existing_peer(self):
        fed = Federation()
        fed.register_peer("kai", "http://kai:7777")
        old_ts = fed._peers["kai"]["last_heartbeat"]
        time.sleep(0.01)
        fed.receive_heartbeat("kai", "http://kai:7777")
        assert fed._peers["kai"]["last_heartbeat"] > old_ts

    def test_summary(self):
        fed = Federation(organism_id="test", bridge_url="http://localhost:7777")
        fed.register_peer("kai", "http://kai:7777")
        s = fed.summary()
        assert s["organism_id"] == "test"
        assert s["total_peers"] == 1
        assert s["alive_peers"] == 1
        assert "kai" in s["peers"]

    def test_persistence(self, store):
        fed1 = Federation(organism_id="org1", store=store)
        fed1.register_peer("kai", "http://kai:7777", name="Kai")
        # Reload from store
        fed2 = Federation(organism_id="org1", store=store)
        assert "kai" in fed2.peers
        assert fed2.peers["kai"]["name"] == "Kai"
