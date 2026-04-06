"""Tests for the SQLite persistence layer."""

import os
import tempfile
import time

import pytest

from symbiont.persistence import PersistenceStore


@pytest.fixture
def store():
    db = tempfile.mktemp(suffix=".db")
    s = PersistenceStore(db)
    yield s
    s.close()
    os.unlink(db)


class TestChannelStats:
    def test_save_and_load(self, store):
        from symbiont.core.mycelium import _ChannelStats
        stats = {"ch1": _ChannelStats(message_count=10, total_bytes=500, weight=2.0)}
        store.save_channel_stats(stats)
        loaded = store.load_channel_stats()
        assert "ch1" in loaded
        assert loaded["ch1"]["message_count"] == 10
        assert loaded["ch1"]["weight"] == 2.0

    def test_overwrite(self, store):
        from symbiont.core.mycelium import _ChannelStats
        store.save_channel_stats({"ch1": _ChannelStats(message_count=5)})
        store.save_channel_stats({"ch1": _ChannelStats(message_count=15)})
        loaded = store.load_channel_stats()
        assert loaded["ch1"]["message_count"] == 15


class TestHubScores:
    def test_save_and_load(self, store):
        store.save_hub_scores({"agent1": 5.0, "agent2": 3.5})
        loaded = store.load_hub_scores()
        assert loaded["agent1"] == 5.0
        assert loaded["agent2"] == 3.5


class TestMessages:
    def test_save_and_load(self, store):
        from symbiont.types import Message
        msg = Message(id="m1", channel="test", sender_id="s1", payload={"data": 1})
        store.save_message(msg)
        loaded = store.load_recent_messages(10)
        assert len(loaded) == 1
        assert loaded[0]["id"] == "m1"
        assert loaded[0]["payload"]["data"] == 1

    def test_trim(self, store):
        from symbiont.types import Message
        for i in range(20):
            store.save_message(Message(id=f"m{i}", channel="test", payload=i))
        # Should not exceed MAX_MESSAGE_LOG (1000), but 20 is fine
        loaded = store.load_recent_messages(100)
        assert len(loaded) == 20


class TestSquads:
    def test_crud(self, store):
        store.save_squad("legal", "Legal team", ["a1", "a2"], {"domain": "law"})
        squads = store.load_squads()
        assert "legal" in squads
        assert squads["legal"]["agent_ids"] == ["a1", "a2"]
        assert store.delete_squad("legal")
        assert "legal" not in store.load_squads()

    def test_update(self, store):
        store.save_squad("dev", "Dev", ["a1"], {})
        store.save_squad("dev", "Dev team", ["a1", "a2"], {"lang": "py"})
        squads = store.load_squads()
        assert squads["dev"]["description"] == "Dev team"
        assert len(squads["dev"]["agent_ids"]) == 2


class TestFederation:
    def test_peer_lifecycle(self, store):
        store.save_peer("org1", "Kai", "http://kai:7777")
        peers = store.load_peers()
        assert "org1" in peers
        assert peers["org1"]["url"] == "http://kai:7777"

    def test_stale_removal(self, store):
        store.save_peer("old", "Old", "http://old:7777")
        # Manually set old timestamp
        store._conn.execute("UPDATE federation SET last_heartbeat=? WHERE organism_id='old'",
                            (time.time() - 600,))
        store._conn.commit()
        store.remove_stale_peers(max_age_sec=300)
        assert "old" not in store.load_peers()


class TestKV:
    def test_set_get(self, store):
        store.set("version", "0.3.0")
        assert store.get("version") == "0.3.0"

    def test_default(self, store):
        assert store.get("missing", "fallback") == "fallback"

    def test_overwrite(self, store):
        store.set("k", 1)
        store.set("k", 2)
        assert store.get("k") == 2


class TestSnapshot:
    def test_snapshot(self, store):
        from symbiont.core.mycelium import Mycelium
        m = Mycelium()
        store.snapshot(m)
        assert store.get("last_snapshot") is not None


class TestStats:
    def test_stats(self, store):
        s = store.stats()
        assert "db_path" in s
        assert s["channels"] == 0
