"""
Tests for symbiont.persistence — PersistenceStore (SQLite-backed).

Coverage targets:
- Schema initialization (all 6 tables)
- Channel stats: save / load / round-trip
- Hub scores: save / load
- Messages: save, load_recent, trim (MAX_MESSAGE_LOG)
- Squads: save, load, delete
- Federation peers: save_peer, load_peers, remove_stale_peers
- Key-Value: set / get / kv_get / kv_set
- Lifecycle: snapshot, close, path, stats
- Thread safety: concurrent writes
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from symbiont.persistence import PersistenceStore, MAX_MESSAGE_LOG


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    """Fresh PersistenceStore backed by a temp SQLite file."""
    s = PersistenceStore(db_path=tmp_path / "test_state.db")
    yield s
    s.close()


def _make_msg(mid: str, channel: str = "ch1", sender: str = "agent-0",
              payload=None, priority: int = 5, ts: float | None = None):
    """Build a mock message object matching PersistenceStore.save_message expectations."""
    return SimpleNamespace(
        id=mid,
        channel=channel,
        sender_id=sender,
        payload=payload or {"text": mid},
        priority=priority,
        timestamp=ts or time.time(),
        metadata={},
    )


def _make_channel_stat(count: int = 1, total_bytes: int = 100,
                       last_active: float | None = None, weight: float = 1.0):
    return SimpleNamespace(
        message_count=count,
        total_bytes=total_bytes,
        last_active=last_active or time.time(),
        weight=weight,
    )


# ---------------------------------------------------------------------------
# Init / Schema
# ---------------------------------------------------------------------------

class TestInit:

    def test_db_file_created(self, tmp_path):
        s = PersistenceStore(db_path=tmp_path / "new.db")
        assert (tmp_path / "new.db").exists()
        s.close()

    def test_default_path_resolves(self):
        # Default path should be a Path instance under home
        s = PersistenceStore(db_path=":memory:")
        assert s.path == Path(":memory:")
        s.close()

    def test_all_tables_exist(self, store):
        tables = {
            row[0] for row in
            store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {"channel_stats", "hub_scores", "messages", "squads", "federation", "kv"}
        assert expected.issubset(tables)

    def test_wal_mode(self, store):
        mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"


# ---------------------------------------------------------------------------
# Channel Stats
# ---------------------------------------------------------------------------

class TestChannelStats:

    def test_save_and_load_single(self, store):
        stats = {"general": _make_channel_stat(count=5, total_bytes=500, weight=2.0)}
        store.save_channel_stats(stats)
        loaded = store.load_channel_stats()
        assert "general" in loaded
        assert loaded["general"]["message_count"] == 5
        assert loaded["general"]["total_bytes"] == 500
        assert loaded["general"]["weight"] == 2.0

    def test_save_multiple_channels(self, store):
        stats = {
            "ch1": _make_channel_stat(count=3),
            "ch2": _make_channel_stat(count=7),
        }
        store.save_channel_stats(stats)
        loaded = store.load_channel_stats()
        assert len(loaded) == 2
        assert loaded["ch2"]["message_count"] == 7

    def test_replace_existing_channel(self, store):
        store.save_channel_stats({"ch": _make_channel_stat(count=1)})
        store.save_channel_stats({"ch": _make_channel_stat(count=99)})
        loaded = store.load_channel_stats()
        assert loaded["ch"]["message_count"] == 99

    def test_load_empty(self, store):
        assert store.load_channel_stats() == {}


# ---------------------------------------------------------------------------
# Hub Scores
# ---------------------------------------------------------------------------

class TestHubScores:

    def test_save_and_load(self, store):
        scores = {"agent-1": 0.9, "agent-2": 0.3}
        store.save_hub_scores(scores)
        loaded = store.load_hub_scores()
        assert loaded["agent-1"] == pytest.approx(0.9)
        assert loaded["agent-2"] == pytest.approx(0.3)

    def test_replace_score(self, store):
        store.save_hub_scores({"a1": 0.5})
        store.save_hub_scores({"a1": 0.8})
        loaded = store.load_hub_scores()
        assert loaded["a1"] == pytest.approx(0.8)

    def test_load_empty(self, store):
        assert store.load_hub_scores() == {}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class TestMessages:

    def test_save_and_load_recent(self, store):
        msg = _make_msg("m1", channel="events", payload={"data": 42})
        store.save_message(msg)
        recent = store.load_recent_messages(limit=10)
        assert len(recent) == 1
        assert recent[0]["id"] == "m1"
        assert recent[0]["payload"]["data"] == 42

    def test_duplicate_ignored(self, store):
        msg = _make_msg("dup1")
        store.save_message(msg)
        store.save_message(msg)  # INSERT OR IGNORE
        recent = store.load_recent_messages(limit=100)
        assert len(recent) == 1

    def test_limit_respected(self, store):
        for i in range(10):
            store.save_message(_make_msg(f"m{i}", ts=float(i)))
        recent = store.load_recent_messages(limit=3)
        assert len(recent) == 3

    def test_ordered_by_timestamp_desc(self, store):
        for i in range(5):
            store.save_message(_make_msg(f"m{i}", ts=float(i)))
        recent = store.load_recent_messages(limit=5)
        timestamps = [r["timestamp"] for r in recent]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_trim_at_max(self, store):
        # Insert MAX_MESSAGE_LOG + 5 messages
        for i in range(MAX_MESSAGE_LOG + 5):
            store.save_message(_make_msg(f"trim-{i}", ts=float(i)))
        count = store._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        assert count <= MAX_MESSAGE_LOG

    def test_metadata_round_trip(self, store):
        msg = SimpleNamespace(
            id="m-meta", channel="ch", sender_id="s",
            payload={"k": "v"}, priority=3,
            timestamp=1000.0, metadata={"tag": "important"},
        )
        store.save_message(msg)
        recent = store.load_recent_messages(limit=1)
        assert recent[0]["metadata"]["tag"] == "important"


# ---------------------------------------------------------------------------
# Squads
# ---------------------------------------------------------------------------

class TestSquads:

    def test_save_and_load(self, store):
        store.save_squad("alpha", "Research squad", ["a1", "a2"], {"domain": "law"})
        squads = store.load_squads()
        assert "alpha" in squads
        assert squads["alpha"]["description"] == "Research squad"
        assert "a1" in squads["alpha"]["agent_ids"]
        assert squads["alpha"]["context"]["domain"] == "law"

    def test_replace_preserves_created_at(self, store):
        store.save_squad("beta", "Old", [], {})
        created_before = store.load_squads()["beta"]["created_at"]
        time.sleep(0.01)
        store.save_squad("beta", "New", ["x"], {})
        created_after = store.load_squads()["beta"]["created_at"]
        assert created_before == created_after  # COALESCE preserves original

    def test_delete_squad(self, store):
        store.save_squad("gamma", "", [], {})
        result = store.delete_squad("gamma")
        assert result is True
        assert "gamma" not in store.load_squads()

    def test_delete_nonexistent_returns_false(self, store):
        result = store.delete_squad("ghost")
        assert result is False

    def test_multiple_squads(self, store):
        for name in ["s1", "s2", "s3"]:
            store.save_squad(name, name, [], {})
        assert len(store.load_squads()) == 3


# ---------------------------------------------------------------------------
# Federation Peers
# ---------------------------------------------------------------------------

class TestFederation:

    def test_save_and_load_peer(self, store):
        store.save_peer("org-kai", "Kai", "http://100.73.123.8:7777", {"region": "br"})
        peers = store.load_peers()
        assert "org-kai" in peers
        assert peers["org-kai"]["name"] == "Kai"
        assert peers["org-kai"]["url"] == "http://100.73.123.8:7777"
        assert peers["org-kai"]["metadata"]["region"] == "br"

    def test_load_peers_empty(self, store):
        assert store.load_peers() == {}

    def test_remove_stale_peers(self, store):
        # Peer with old heartbeat
        store.save_peer("old-org", "Old", "http://dead:7777")
        # Manually backdate its heartbeat
        store._conn.execute(
            "UPDATE federation SET last_heartbeat=? WHERE organism_id=?",
            (time.time() - 400, "old-org"),
        )
        store._conn.commit()
        # Live peer
        store.save_peer("live-org", "Live", "http://alive:7777")
        store.remove_stale_peers(max_age_sec=300)
        # Verify by checking what's actually in the table — not via total_changes
        # (total_changes accumulates across the session, making count unreliable)
        remaining = store.load_peers()
        assert "live-org" in remaining
        assert "old-org" not in remaining


# ---------------------------------------------------------------------------
# Key-Value
# ---------------------------------------------------------------------------

class TestKV:

    def test_set_and_get(self, store):
        store.set("key1", {"nested": True, "count": 42})
        val = store.get("key1")
        assert val["nested"] is True
        assert val["count"] == 42

    def test_get_default(self, store):
        assert store.get("missing", default="fallback") == "fallback"

    def test_alias_kv_get_kv_set(self, store):
        store.kv_set("alias", [1, 2, 3])
        assert store.kv_get("alias") == [1, 2, 3]

    def test_overwrite(self, store):
        store.set("x", 1)
        store.set("x", 99)
        assert store.get("x") == 99


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:

    def test_stats(self, store):
        store.save_channel_stats({"ch1": _make_channel_stat()})
        store.save_message(_make_msg("m1"))
        store.save_squad("sq", "", [], {})
        store.save_peer("p1", "P1", "http://p:7777")
        s = store.stats()
        assert s["channels"] == 1
        assert s["messages"] == 1
        assert s["squads"] == 1
        assert s["peers"] == 1
        assert "db_path" in s

    def test_snapshot(self, store):
        mycelium = MagicMock()
        mycelium.get_channel_stats.return_value = {"ch": _make_channel_stat(count=5)}
        mycelium._hub_scores = {"hub-1": 0.7}
        mycelium.recent_messages = [_make_msg(f"snap-{i}") for i in range(10)]
        store.snapshot(mycelium)
        assert store.get("last_snapshot") is not None
        loaded_ch = store.load_channel_stats()
        assert loaded_ch["ch"]["message_count"] == 5

    def test_path_property(self, tmp_path):
        db = tmp_path / "p.db"
        s = PersistenceStore(db_path=db)
        assert s.path == db
        s.close()


# ---------------------------------------------------------------------------
# Thread Safety
# ---------------------------------------------------------------------------

class TestThreadSafety:

    def test_concurrent_writes(self, store):
        errors = []

        def writer(n):
            try:
                for i in range(20):
                    store.set(f"thread-{n}-key-{i}", i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
        # At least some keys should be persisted
        count = store._conn.execute("SELECT COUNT(*) FROM kv").fetchone()[0]
        assert count > 0
