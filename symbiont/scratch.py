"""
Shared Scratchpad — externalized working memory for agents.

Inspired by Claude Code's worker scratch directory pattern and
Clark & Chalmers' Extended Mind thesis: the scratch IS part of
the cognitive process, not just storage.

Each session gets its own scratch directory. All agents can read
and write freely. Contributions are scored — low-score entries
are auto-pruned after a configurable TTL.

Integration with immune-scoring: contributions can be marked
by multiple agents, and only collectively-scored items persist.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from symbiont.types import _uid

logger = logging.getLogger(__name__)

DEFAULT_SCRATCH_DIR = Path.home() / ".symbiont" / "scratch"
DEFAULT_TTL_SECONDS = 1800  # 30 minutes
SCORE_PRUNE_THRESHOLD = 0.3  # Below this score, entries are pruned


@dataclass
class ScratchEntry:
    """A single entry in the shared scratchpad."""
    id: str
    author_id: str
    content: Any
    tags: list[str] = field(default_factory=list)
    score: float = 0.5
    created_at: float = field(default_factory=time.time)
    read_count: int = 0
    scores: dict[str, float] = field(default_factory=dict)  # agent_id → score

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    @property
    def aggregate_score(self) -> float:
        """Average score from all scoring agents, or default."""
        if not self.scores:
            return self.score
        return sum(self.scores.values()) / len(self.scores)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "author_id": self.author_id,
            "content": self.content,
            "tags": self.tags,
            "score": self.score,
            "aggregate_score": self.aggregate_score,
            "created_at": self.created_at,
            "read_count": self.read_count,
            "scores": self.scores,
        }


class SharedScratchpad:
    """
    Shared working memory for all agents in a session.

    Features:
    - Write: any agent can deposit reasoning, intermediate results, or notes
    - Read: any agent can read all entries (or filter by tags)
    - Score: agents can score entries for quality/relevance
    - Prune: old or low-scored entries are automatically removed
    """

    def __init__(
        self,
        session_id: str | None = None,
        scratch_dir: Path | None = None,
        ttl: float = DEFAULT_TTL_SECONDS,
        persist: bool = False,
    ):
        self.session_id = session_id or _uid()
        self._entries: dict[str, ScratchEntry] = {}
        self._ttl = ttl
        self._persist = persist
        self._scratch_dir = (scratch_dir or DEFAULT_SCRATCH_DIR) / self.session_id

        if persist:
            self._scratch_dir.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        author_id: str,
        content: Any,
        tags: list[str] | None = None,
        score: float = 0.5,
    ) -> str:
        """Write an entry to the scratchpad. Returns entry ID."""
        entry_id = _uid()
        entry = ScratchEntry(
            id=entry_id,
            author_id=author_id,
            content=content,
            tags=tags or [],
            score=score,
        )
        self._entries[entry_id] = entry

        if self._persist:
            self._persist_entry(entry)

        logger.debug(
            "scratch: '%s' wrote entry %s (tags=%s)",
            author_id, entry_id, tags,
        )
        return entry_id

    def read(self, tags: list[str] | None = None, min_score: float = 0.0) -> list[ScratchEntry]:
        """Read entries, optionally filtered by tags and minimum score."""
        self._auto_prune()

        results = []
        for entry in self._entries.values():
            if min_score > 0 and entry.aggregate_score < min_score:
                continue
            if tags and not any(t in entry.tags for t in tags):
                continue
            entry.read_count += 1
            results.append(entry)

        return sorted(results, key=lambda e: e.created_at, reverse=True)

    def score_entry(self, entry_id: str, scorer_id: str, score: float) -> bool:
        """Score an entry (immune-scoring pattern: multi-agent consensus)."""
        entry = self._entries.get(entry_id)
        if not entry:
            return False
        entry.scores[scorer_id] = max(0.0, min(1.0, score))
        logger.debug(
            "scratch: '%s' scored entry %s = %.2f (aggregate=%.2f)",
            scorer_id, entry_id, score, entry.aggregate_score,
        )
        return True

    def remove(self, entry_id: str) -> bool:
        """Manually remove an entry."""
        if entry_id in self._entries:
            del self._entries[entry_id]
            if self._persist:
                path = self._scratch_dir / f"{entry_id}.json"
                path.unlink(missing_ok=True)
            return True
        return False

    def _auto_prune(self) -> int:
        """Remove expired or low-scored entries. Returns count of pruned."""
        now = time.time()
        to_prune = []

        for entry_id, entry in self._entries.items():
            # TTL expiration
            if entry.age_seconds > self._ttl:
                to_prune.append(entry_id)
                continue
            # Low aggregate score (only if scored by at least one agent)
            if entry.scores and entry.aggregate_score < SCORE_PRUNE_THRESHOLD:
                to_prune.append(entry_id)

        for entry_id in to_prune:
            self.remove(entry_id)

        if to_prune:
            logger.info("scratch: auto-pruned %d entries", len(to_prune))

        return len(to_prune)

    def _persist_entry(self, entry: ScratchEntry) -> None:
        """Persist an entry to disk."""
        path = self._scratch_dir / f"{entry.id}.json"
        path.write_text(json.dumps(entry.to_dict(), default=str))

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def summary(self) -> dict:
        return {
            "session_id": self.session_id,
            "entries": self.entry_count,
            "persist": self._persist,
            "ttl_seconds": self._ttl,
        }

    def clear(self) -> None:
        """Clear all entries."""
        self._entries.clear()
        if self._persist and self._scratch_dir.exists():
            for f in self._scratch_dir.glob("*.json"):
                f.unlink()
