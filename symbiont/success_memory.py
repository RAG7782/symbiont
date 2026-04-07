"""
Success Memory — explicit capture of what worked well.

Feedback systems have a negativity bias: they capture errors and
corrections but not approaches that worked exceptionally well.
STEER showed that confirmations are as valuable as corrections.

This module captures "memory of success" — approaches, patterns,
and decisions that produced good outcomes. It's the complement
to antibodies (error memory).

Usage:
    sm = SuccessMemory()
    sm.record("Used JWT with refresh tokens for auth", tags=["auth", "pattern"],
              outcome="Zero auth failures in 2 weeks", confidence=0.95)
    successes = sm.recall("authentication patterns")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SuccessRecord:
    """A recorded successful approach."""
    id: str
    approach: str  # What was done
    outcome: str  # What happened as a result
    tags: list[str] = field(default_factory=list)
    source_agent: str = ""
    confidence: float = 0.8
    created_at: float = field(default_factory=time.time)
    reuse_count: int = 0  # How many times this was reused

    def matches(self, query: str) -> float:
        """Simple keyword match score (0.0 to 1.0)."""
        query_words = set(query.lower().split())
        approach_words = set(self.approach.lower().split())
        tag_words = set(t.lower() for t in self.tags)
        all_words = approach_words | tag_words

        if not query_words:
            return 0.0

        overlap = query_words & all_words
        return len(overlap) / len(query_words)


class SuccessMemory:
    """
    Registry of successful approaches for bias correction.

    Complements antibodies (what went wrong) with what went right.
    Helps agents replicate successful patterns instead of only
    avoiding past failures.
    """

    def __init__(self) -> None:
        self._records: dict[str, SuccessRecord] = {}
        self._counter = 0

    def record(
        self,
        approach: str,
        outcome: str,
        tags: list[str] | None = None,
        source_agent: str = "",
        confidence: float = 0.8,
    ) -> SuccessRecord:
        """Record a successful approach."""
        self._counter += 1
        record_id = f"success:{self._counter}"

        rec = SuccessRecord(
            id=record_id,
            approach=approach,
            outcome=outcome,
            tags=tags or [],
            source_agent=source_agent,
            confidence=confidence,
        )
        self._records[record_id] = rec

        logger.info(
            "success-memory: recorded '%s' (outcome: '%s', confidence=%.2f)",
            approach[:50], outcome[:50], confidence,
        )
        return rec

    def recall(self, query: str, top_k: int = 5, min_score: float = 0.1) -> list[SuccessRecord]:
        """Find relevant successful approaches for a given query."""
        scored = []
        for rec in self._records.values():
            score = rec.matches(query)
            if score >= min_score:
                scored.append((score, rec))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for _, rec in scored[:top_k]:
            rec.reuse_count += 1
            results.append(rec)

        return results

    def get_by_tags(self, tags: list[str]) -> list[SuccessRecord]:
        """Get successes matching any of the given tags."""
        tag_set = set(t.lower() for t in tags)
        return [
            rec for rec in self._records.values()
            if set(t.lower() for t in rec.tags) & tag_set
        ]

    def most_reused(self, n: int = 5) -> list[SuccessRecord]:
        """Get the most frequently reused successful patterns."""
        sorted_recs = sorted(
            self._records.values(),
            key=lambda r: r.reuse_count,
            reverse=True,
        )
        return sorted_recs[:n]

    @property
    def count(self) -> int:
        return len(self._records)

    def summary(self) -> dict:
        total_reuses = sum(r.reuse_count for r in self._records.values())
        return {
            "total_records": self.count,
            "total_reuses": total_reuses,
            "avg_confidence": (
                round(sum(r.confidence for r in self._records.values()) / self.count, 3)
                if self.count > 0 else 0.0
            ),
        }
