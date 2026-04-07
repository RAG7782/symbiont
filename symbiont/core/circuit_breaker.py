"""
Circuit Breaker — apoptose cognitiva para subsistemas SYMBIONT.

Inspired by Claude Code's MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3.
After N consecutive failures, the subsystem degrades gracefully
instead of retrying indefinitely.

Biological analogy: apoptosis — cells self-destruct when damaged
beyond repair, preventing the organism from wasting resources
on a broken component.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 3
COOLDOWN_SECONDS = 60.0  # Time before auto-reset attempt


class BreakerState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failures exceeded threshold — blocking calls
    HALF_OPEN = "half_open"  # Cooldown elapsed — allowing one probe call


@dataclass
class CircuitBreaker:
    """
    Universal circuit breaker for any SYMBIONT subsystem.

    Usage:
        breaker = CircuitBreaker(name="mycelium.publish")
        if breaker.allow():
            try:
                result = do_thing()
                breaker.record_success()
            except Exception:
                breaker.record_failure()
        else:
            # Degraded mode — skip or use fallback
            ...
    """
    name: str
    max_failures: int = MAX_CONSECUTIVE_FAILURES
    cooldown: float = COOLDOWN_SECONDS
    state: BreakerState = BreakerState.CLOSED
    consecutive_failures: int = 0
    total_failures: int = 0
    total_successes: int = 0
    last_failure_time: float = 0.0
    opened_at: float = 0.0
    _on_open: Callable[[str, int], Any] | None = None

    def allow(self) -> bool:
        """Check if a call should be allowed through."""
        if self.state == BreakerState.CLOSED:
            return True
        if self.state == BreakerState.OPEN:
            # Check if cooldown has elapsed
            if time.time() - self.opened_at >= self.cooldown:
                self.state = BreakerState.HALF_OPEN
                logger.info("circuit-breaker: '%s' → HALF_OPEN (probe allowed)", self.name)
                return True
            return False
        # HALF_OPEN: allow one probe
        return True

    def record_success(self) -> None:
        """Record a successful call — reset the breaker."""
        self.total_successes += 1
        if self.state != BreakerState.CLOSED:
            logger.info(
                "circuit-breaker: '%s' → CLOSED (recovered after %d failures)",
                self.name, self.consecutive_failures,
            )
        self.consecutive_failures = 0
        self.state = BreakerState.CLOSED

    def record_failure(self) -> None:
        """Record a failed call — potentially open the breaker."""
        self.consecutive_failures += 1
        self.total_failures += 1
        self.last_failure_time = time.time()

        if self.state == BreakerState.HALF_OPEN:
            # Probe failed — back to OPEN
            self.state = BreakerState.OPEN
            self.opened_at = time.time()
            logger.warning(
                "circuit-breaker: '%s' probe failed → OPEN (total failures: %d)",
                self.name, self.total_failures,
            )
            return

        if self.consecutive_failures >= self.max_failures:
            self.state = BreakerState.OPEN
            self.opened_at = time.time()
            logger.warning(
                "circuit-breaker: '%s' → OPEN after %d consecutive failures",
                self.name, self.consecutive_failures,
            )
            if self._on_open:
                self._on_open(self.name, self.consecutive_failures)

    def reset(self) -> None:
        """Manually reset the breaker to CLOSED."""
        self.consecutive_failures = 0
        self.state = BreakerState.CLOSED
        logger.info("circuit-breaker: '%s' manually reset → CLOSED", self.name)

    @property
    def is_open(self) -> bool:
        return self.state == BreakerState.OPEN

    def summary(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
        }


class CircuitBreakerRegistry:
    """
    Central registry for all circuit breakers in the organism.
    Provides a single point to check health and reset breakers.
    """

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        name: str,
        max_failures: int = MAX_CONSECUTIVE_FAILURES,
        cooldown: float = COOLDOWN_SECONDS,
        on_open: Callable[[str, int], Any] | None = None,
    ) -> CircuitBreaker:
        """Get an existing breaker or create a new one."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name=name,
                max_failures=max_failures,
                cooldown=cooldown,
                _on_open=on_open,
            )
        return self._breakers[name]

    def summary(self) -> dict[str, dict]:
        return {name: b.summary() for name, b in self._breakers.items()}

    @property
    def open_breakers(self) -> list[str]:
        return [name for name, b in self._breakers.items() if b.is_open]

    def reset_all(self) -> None:
        for b in self._breakers.values():
            b.reset()
