"""
Antibodies — error memory for SYMBIONT agents.

Integrates with the Immune Resolution MCP server to provide
pattern-based error prevention. When a caste resolves an error,
an antibody is generated. Before each task, existing antibodies
are checked — known patterns are resolved at zero cost.

Biological analogy: adaptive immune system. First exposure costs
the organism; subsequent exposures are handled by memory cells
(antibodies) that recognize the pattern instantly.

Falls back gracefully when Immune MCP is unavailable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Antibody:
    """A learned pattern-response pair from a past error."""
    id: str
    pattern: str  # Error pattern signature
    response: str  # Known resolution
    source_agent: str  # Who generated this antibody
    created_at: float = field(default_factory=time.time)
    match_count: int = 0  # How many times this antibody has been used
    confidence: float = 0.8

    def matches(self, error_text: str) -> bool:
        """Check if this antibody matches a given error."""
        return self.pattern.lower() in error_text.lower()


class AntibodyRegistry:
    """
    Local antibody cache for SYMBIONT.

    Works standalone (in-memory) or backed by Immune Resolution MCP.
    When Immune is available, antibodies are also persisted there
    for cross-session reuse.
    """

    def __init__(self) -> None:
        self._antibodies: dict[str, Antibody] = {}
        self._immune_available = False
        self._check_immune()

    def _check_immune(self) -> None:
        """Check if Immune Resolution MCP is available."""
        # Will be wired by organism if MCP is present
        self._immune_available = False

    def check(self, error_text: str) -> Antibody | None:
        """
        Check if an antibody exists for this error pattern.
        Returns the matching antibody or None.
        """
        for ab in self._antibodies.values():
            if ab.matches(error_text):
                ab.match_count += 1
                logger.info(
                    "antibody: match found for '%s' → '%s' (matches=%d)",
                    error_text[:50], ab.id, ab.match_count,
                )
                return ab
        return None

    def generate(
        self,
        error_text: str,
        resolution: str,
        source_agent: str,
        confidence: float = 0.8,
    ) -> Antibody:
        """
        Generate an antibody from a resolved error.
        The error pattern is hashed for dedup.
        """
        pattern = self._extract_pattern(error_text)
        ab_id = self._hash_pattern(pattern)

        # Update existing if same pattern
        if ab_id in self._antibodies:
            existing = self._antibodies[ab_id]
            existing.response = resolution
            existing.confidence = max(existing.confidence, confidence)
            logger.info("antibody: updated existing '%s'", ab_id)
            return existing

        ab = Antibody(
            id=ab_id,
            pattern=pattern,
            response=resolution,
            source_agent=source_agent,
            confidence=confidence,
        )
        self._antibodies[ab_id] = ab
        logger.info(
            "antibody: generated '%s' from agent '%s' (pattern='%s')",
            ab_id, source_agent, pattern[:50],
        )
        return ab

    def remove(self, ab_id: str) -> bool:
        """Remove an antibody (false positive, obsolete)."""
        if ab_id in self._antibodies:
            del self._antibodies[ab_id]
            return True
        return False

    def list_all(self) -> list[dict]:
        """List all antibodies."""
        return [
            {
                "id": ab.id,
                "pattern": ab.pattern,
                "response": ab.response[:100],
                "source": ab.source_agent,
                "matches": ab.match_count,
                "confidence": ab.confidence,
            }
            for ab in self._antibodies.values()
        ]

    @property
    def count(self) -> int:
        return len(self._antibodies)

    def summary(self) -> dict:
        total_matches = sum(ab.match_count for ab in self._antibodies.values())
        return {
            "antibodies": self.count,
            "total_matches": total_matches,
            "immune_connected": self._immune_available,
        }

    @staticmethod
    def _extract_pattern(error_text: str) -> str:
        """Extract the core error pattern, stripping variable parts."""
        # Simple extraction: take first line or first 200 chars
        lines = error_text.strip().splitlines()
        return lines[0][:200] if lines else error_text[:200]

    @staticmethod
    def _hash_pattern(pattern: str) -> str:
        """Generate a stable ID for a pattern."""
        return hashlib.sha256(pattern.lower().encode()).hexdigest()[:12]
