"""
SYMBIONT Persistence — SQLite-backed state for Mycelium and organism.

Stores:
- Channel statistics (message counts, weights, last active)
- Hub node scores
- Message log (recent N messages)
- Topology snapshots
- Squad definitions

Zero external dependencies — uses stdlib sqlite3.
Auto-saves on state changes, restores on boot.

Usage:
    store = PersistenceStore()  # ~/.symbiont/state.db
    store.save_channel_stats(mycelium.get_channel_stats())
    stats = store.load_channel_stats()
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path.home() / ".symbiont" / "state.db"
MAX_MESSAGE_LOG = 1000


class PersistenceStore:
    """SQLite persistence for SYMBIONT state."""

    def __init__(self, db_path: Path | str | None = None):
        self._path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False, timeout=10)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._write_lock = threading.Lock()
        self._init_schema()

    def _write(self, sql: str, params: tuple = ()) -> None:
        """Thread-safe write (execute + commit)."""
        with self._write_lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    def _write_many(self, operations: list[tuple[str, tuple]]) -> None:
        """Thread-safe batch write."""
        with self._write_lock:
            for sql, params in operations:
                self._conn.execute(sql, params)
            self._conn.commit()
        logger.info("persistence: opened %s", self._path)

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS channel_stats (
                channel TEXT PRIMARY KEY,
                message_count INTEGER DEFAULT 0,
                total_bytes INTEGER DEFAULT 0,
                last_active REAL DEFAULT 0,
                weight REAL DEFAULT 1.0
            );

            CREATE TABLE IF NOT EXISTS hub_scores (
                node_id TEXT PRIMARY KEY,
                score REAL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                channel TEXT,
                sender_id TEXT,
                payload TEXT,
                priority INTEGER DEFAULT 5,
                timestamp REAL,
                metadata TEXT
            );

            CREATE TABLE IF NOT EXISTS squads (
                name TEXT PRIMARY KEY,
                description TEXT DEFAULT '',
                agent_ids TEXT DEFAULT '[]',
                context TEXT DEFAULT '{}',
                created_at REAL,
                updated_at REAL
            );

            CREATE TABLE IF NOT EXISTS federation (
                organism_id TEXT PRIMARY KEY,
                name TEXT DEFAULT '',
                url TEXT DEFAULT '',
                last_heartbeat REAL DEFAULT 0,
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at REAL
            );
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Channel Stats
    # ------------------------------------------------------------------

    def save_channel_stats(self, stats: dict) -> None:
        """Save channel statistics from Mycelium."""
        ops = [
            ("""INSERT OR REPLACE INTO channel_stats
                (channel, message_count, total_bytes, last_active, weight)
                VALUES (?, ?, ?, ?, ?)""",
             (ch, cs.message_count, cs.total_bytes, cs.last_active, cs.weight))
            for ch, cs in stats.items()
        ]
        self._write_many(ops)

    def load_channel_stats(self) -> dict:
        """Load channel statistics."""
        rows = self._conn.execute("SELECT * FROM channel_stats").fetchall()
        return {
            row[0]: {
                "message_count": row[1], "total_bytes": row[2],
                "last_active": row[3], "weight": row[4],
            }
            for row in rows
        }

    # ------------------------------------------------------------------
    # Hub Scores
    # ------------------------------------------------------------------

    def save_hub_scores(self, scores: dict[str, float]) -> None:
        ops = [("INSERT OR REPLACE INTO hub_scores (node_id, score) VALUES (?, ?)",
                (nid, s)) for nid, s in scores.items()]
        self._write_many(ops)

    def load_hub_scores(self) -> dict[str, float]:
        rows = self._conn.execute("SELECT node_id, score FROM hub_scores").fetchall()
        return {row[0]: row[1] for row in rows}

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def save_message(self, msg) -> None:
        """Save a single message to the log."""
        self._write(
            """INSERT OR IGNORE INTO messages
               (id, channel, sender_id, payload, priority, timestamp, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (msg.id, msg.channel, msg.sender_id,
             json.dumps(msg.payload, default=str, ensure_ascii=False),
             msg.priority, msg.timestamp,
             json.dumps(msg.metadata, default=str, ensure_ascii=False)),
        )
        self._trim_messages()

    def load_recent_messages(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {"id": r[0], "channel": r[1], "sender_id": r[2],
             "payload": json.loads(r[3]), "priority": r[4],
             "timestamp": r[5], "metadata": json.loads(r[6])}
            for r in rows
        ]

    def _trim_messages(self):
        count = self._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        if count > MAX_MESSAGE_LOG:
            self._write(
                """DELETE FROM messages WHERE id IN
                   (SELECT id FROM messages ORDER BY timestamp ASC LIMIT ?)""",
                (count - MAX_MESSAGE_LOG,),
            )

    # ------------------------------------------------------------------
    # Squads
    # ------------------------------------------------------------------

    def save_squad(self, name: str, description: str, agent_ids: list[str], context: dict) -> None:
        now = time.time()
        self._write(
            """INSERT OR REPLACE INTO squads
               (name, description, agent_ids, context, created_at, updated_at)
               VALUES (?, ?, ?, ?, COALESCE((SELECT created_at FROM squads WHERE name=?), ?), ?)""",
            (name, description, json.dumps(agent_ids), json.dumps(context, ensure_ascii=False),
             name, now, now),
        )

    def load_squads(self) -> dict[str, dict]:
        rows = self._conn.execute("SELECT * FROM squads").fetchall()
        return {
            row[0]: {
                "name": row[0], "description": row[1],
                "agent_ids": json.loads(row[2]), "context": json.loads(row[3]),
                "created_at": row[4], "updated_at": row[5],
            }
            for row in rows
        }

    def delete_squad(self, name: str) -> bool:
        with self._write_lock:
            self._conn.execute("DELETE FROM squads WHERE name=?", (name,))
            self._conn.commit()
            return self._conn.total_changes > 0

    # ------------------------------------------------------------------
    # Federation
    # ------------------------------------------------------------------

    def save_peer(self, organism_id: str, name: str, url: str, metadata: dict | None = None) -> None:
        self._write(
            """INSERT OR REPLACE INTO federation
               (organism_id, name, url, last_heartbeat, metadata)
               VALUES (?, ?, ?, ?, ?)""",
            (organism_id, name, url, time.time(), json.dumps(metadata or {})),
        )

    def load_peers(self) -> dict[str, dict]:
        rows = self._conn.execute("SELECT * FROM federation").fetchall()
        return {
            row[0]: {"name": row[1], "url": row[2],
                     "last_heartbeat": row[3], "metadata": json.loads(row[4])}
            for row in rows
        }

    def remove_stale_peers(self, max_age_sec: float = 300) -> int:
        cutoff = time.time() - max_age_sec
        with self._write_lock:
            self._conn.execute("DELETE FROM federation WHERE last_heartbeat < ?", (cutoff,))
            self._conn.commit()
            return self._conn.total_changes

    # ------------------------------------------------------------------
    # Key-Value (generic)
    # ------------------------------------------------------------------

    def set(self, key: str, value: Any) -> None:
        self._write(
            "INSERT OR REPLACE INTO kv (key, value, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, default=str, ensure_ascii=False), time.time()),
        )

    def get(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def snapshot(self, mycelium) -> None:
        """Take a full snapshot of Mycelium state."""
        self.save_channel_stats(mycelium.get_channel_stats())
        self.save_hub_scores(dict(mycelium._hub_scores))
        for msg in mycelium.recent_messages[-50:]:
            self.save_message(msg)
        self.set("last_snapshot", time.time())

    def close(self) -> None:
        self._conn.close()

    @property
    def path(self) -> Path:
        return self._path

    def stats(self) -> dict:
        channels = self._conn.execute("SELECT COUNT(*) FROM channel_stats").fetchone()[0]
        messages = self._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        squads = self._conn.execute("SELECT COUNT(*) FROM squads").fetchone()[0]
        peers = self._conn.execute("SELECT COUNT(*) FROM federation").fetchone()[0]
        return {
            "db_path": str(self._path),
            "channels": channels, "messages": messages,
            "squads": squads, "peers": peers,
        }
