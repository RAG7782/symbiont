"""
Memory Scoring — utility-based memory lifecycle management.

Neither Claude Code nor SYMBIONT has a system to evaluate whether
memories are USEFUL. Memories accumulate without pruning by utility.
This module tracks: was the memory accessed? Did it help?

Each memory gets a utility score based on:
- Access frequency (was it recalled?)
- Recency of last access
- Explicit feedback (thumbs up/down)

Memories with utility=0 after N sessions are candidates for pruning.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

SESSIONS_BEFORE_PRUNE = 5
UTILITY_DECAY_RATE = 0.1  # Per session


@dataclass
class MemoryScore:
    """Utility tracking for a single memory."""
    memory_id: str
    created_at: float = field(default_factory=time.time)
    access_count: int = 0
    last_accessed: float = 0.0
    positive_feedback: int = 0
    negative_feedback: int = 0
    sessions_since_access: int = 0

    @property
    def utility(self) -> float:
        """
        Calculate utility score (0.0 to 1.0).
        Based on access frequency, feedback, and decay.
        Accessed memories always score higher than unaccessed ones.
        """
        if self.access_count == 0:
            # Never accessed — utility decays per session, capped at 0.4
            return max(0.0, min(0.4, 0.4 - self.sessions_since_access * UTILITY_DECAY_RATE))

        # Base: access frequency normalized (0.5 to 1.0 range)
        freq_score = min(1.0, 0.5 + self.access_count / 20.0)

        # Feedback adjustment
        total_feedback = self.positive_feedback + self.negative_feedback
        if total_feedback > 0:
            feedback_ratio = self.positive_feedback / total_feedback
        else:
            feedback_ratio = 0.5  # Neutral if no feedback

        # Recency: decay based on sessions since last access
        recency = max(0.0, 1.0 - self.sessions_since_access * UTILITY_DECAY_RATE * 0.5)

        return (freq_score * 0.4 + feedback_ratio * 0.3 + recency * 0.3)

    @property
    def should_prune(self) -> bool:
        """Check if this memory should be pruned."""
        return (
            self.sessions_since_access >= SESSIONS_BEFORE_PRUNE
            and self.access_count == 0
        )


class MemoryScorer:
    """
    Tracks utility of all memories for pruning decisions.
    """

    def __init__(self) -> None:
        self._scores: dict[str, MemoryScore] = {}

    def register(self, memory_id: str) -> None:
        """Register a new memory for tracking."""
        if memory_id not in self._scores:
            self._scores[memory_id] = MemoryScore(memory_id=memory_id)

    def record_access(self, memory_id: str) -> None:
        """Record that a memory was accessed (recalled)."""
        score = self._scores.get(memory_id)
        if score:
            score.access_count += 1
            score.last_accessed = time.time()
            score.sessions_since_access = 0

    def record_feedback(self, memory_id: str, positive: bool) -> None:
        """Record explicit feedback on a memory's usefulness."""
        score = self._scores.get(memory_id)
        if score:
            if positive:
                score.positive_feedback += 1
            else:
                score.negative_feedback += 1

    def tick_session(self) -> None:
        """
        Called at the end of each session.
        Increments sessions_since_access for all memories.
        """
        for score in self._scores.values():
            score.sessions_since_access += 1

    def get_prune_candidates(self) -> list[str]:
        """Get memory IDs that should be pruned."""
        return [
            score.memory_id
            for score in self._scores.values()
            if score.should_prune
        ]

    def get_utility(self, memory_id: str) -> float:
        """Get the utility score for a memory."""
        score = self._scores.get(memory_id)
        return score.utility if score else 0.0

    def get_top_memories(self, n: int = 10) -> list[dict]:
        """Get top N most useful memories."""
        ranked = sorted(
            self._scores.values(),
            key=lambda s: s.utility,
            reverse=True,
        )
        return [
            {
                "id": s.memory_id,
                "utility": round(s.utility, 3),
                "accesses": s.access_count,
                "feedback": f"+{s.positive_feedback}/-{s.negative_feedback}",
            }
            for s in ranked[:n]
        ]

    def summary(self) -> dict:
        total = len(self._scores)
        prune_candidates = len(self.get_prune_candidates())
        avg_utility = (
            sum(s.utility for s in self._scores.values()) / total
            if total > 0 else 0.0
        )
        return {
            "total_tracked": total,
            "prune_candidates": prune_candidates,
            "avg_utility": round(avg_utility, 3),
        }
