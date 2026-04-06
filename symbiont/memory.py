"""
IMI Memory integration for SYMBIONT.

Wraps the IMI cognitive memory system to provide persistent memory
for the SYMBIONT organism. Every task execution is encoded into IMI,
and past memories are retrieved to enrich context before LLM calls.

Usage:
    from symbiont.memory import IMIMemory

    mem = IMIMemory()
    mem.encode("Task completed: JWT auth module", tags=["auth", "coding"])
    results = mem.recall("authentication patterns")
    mem.dream()  # consolidation
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# IMI lives at ~/experimentos/tools/imi — add to path if needed
_IMI_DIR = Path.home() / "experimentos" / "tools" / "imi"


class IMIMemory:
    """Thin wrapper over IMI's IMISpace for SYMBIONT integration."""

    def __init__(self, db_path: str | None = None):
        self._space = None
        self._db_path = db_path or str(Path.home() / ".imi" / "symbiont.db")
        self._available = False
        self._init()

    def _init(self):
        try:
            if str(_IMI_DIR) not in sys.path:
                sys.path.insert(0, str(_IMI_DIR))
            from imi.space import IMISpace

            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._space = IMISpace.from_sqlite(self._db_path)
            self._available = True
            logger.info("imi-memory: connected (db=%s, memories=%d)", self._db_path, len(self._space.episodic))
        except Exception as e:
            logger.warning("imi-memory: not available (%s) — running without memory", e)
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    @property
    def memory_count(self) -> int:
        if not self._available:
            return 0
        return len(self._space.episodic)

    def encode(self, experience: str, tags: list[str] | None = None, source: str = "symbiont") -> dict | None:
        """Store a new memory. Returns node info or None if unavailable."""
        if not self._available:
            return None
        try:
            node = self._space.encode(experience, tags=tags, source=source)
            result = {
                "id": node.id,
                "summary": node.summary_medium,
                "tags": node.tags,
                "mass": round(node.mass, 3),
            }
            logger.debug("imi-memory: encoded '%s' (id=%s)", experience[:50], node.id)
            return result
        except Exception as e:
            logger.warning("imi-memory: encode failed — %s", e)
            return None

    def recall(self, query: str, top_k: int = 5, zoom: str = "medium") -> list[dict]:
        """Search memories. Returns list of hits or empty list."""
        if not self._available:
            return []
        try:
            nav = self._space.navigate(query, zoom=zoom, top_k=top_k)
            results = []
            for m in nav.memories[:top_k]:
                results.append({
                    "score": round(m["score"], 3),
                    "content": m["content"],
                    "tags": m.get("tags", []),
                })
            return results
        except Exception as e:
            logger.warning("imi-memory: recall failed — %s", e)
            return []

    def dream(self) -> dict | None:
        """Run consolidation cycle. Clusters and strengthens memories."""
        if not self._available:
            return None
        try:
            result = self._space.dream()
            logger.info("imi-memory: dream cycle complete")
            return {"status": "ok", "clusters": getattr(result, "clusters_formed", 0)}
        except Exception as e:
            logger.warning("imi-memory: dream failed — %s", e)
            return None

    def stats(self) -> dict:
        """Get memory statistics."""
        if not self._available:
            return {"available": False}
        try:
            return {
                "available": True,
                "memories": len(self._space.episodic),
                "db": self._db_path,
            }
        except Exception:
            return {"available": False}
