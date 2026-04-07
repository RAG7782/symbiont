"""Tests for the Circuit Breaker subsystem."""

import time

import pytest

from symbiont.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    BreakerState,
    MAX_CONSECUTIVE_FAILURES,
)


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(name="test")
        assert cb.state == BreakerState.CLOSED
        assert cb.allow()

    def test_stays_closed_on_success(self):
        cb = CircuitBreaker(name="test")
        cb.record_success()
        cb.record_success()
        assert cb.state == BreakerState.CLOSED
        assert cb.consecutive_failures == 0
        assert cb.total_successes == 2

    def test_opens_after_max_failures(self):
        cb = CircuitBreaker(name="test", max_failures=3)
        cb.record_failure()
        assert cb.state == BreakerState.CLOSED
        cb.record_failure()
        assert cb.state == BreakerState.CLOSED
        cb.record_failure()
        assert cb.state == BreakerState.OPEN
        assert not cb.allow()

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(name="test", max_failures=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.consecutive_failures == 0
        assert cb.state == BreakerState.CLOSED
        # Need 3 more consecutive failures to open
        cb.record_failure()
        cb.record_failure()
        assert cb.state == BreakerState.CLOSED

    def test_half_open_after_cooldown(self):
        cb = CircuitBreaker(name="test", max_failures=1, cooldown=0.01)
        cb.record_failure()
        assert cb.state == BreakerState.OPEN
        assert not cb.allow()
        time.sleep(0.02)
        assert cb.allow()  # Should transition to HALF_OPEN
        assert cb.state == BreakerState.HALF_OPEN

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(name="test", max_failures=1, cooldown=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.allow()  # HALF_OPEN
        cb.record_success()
        assert cb.state == BreakerState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(name="test", max_failures=1, cooldown=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.allow()  # HALF_OPEN
        cb.record_failure()
        assert cb.state == BreakerState.OPEN

    def test_manual_reset(self):
        cb = CircuitBreaker(name="test", max_failures=1)
        cb.record_failure()
        assert cb.state == BreakerState.OPEN
        cb.reset()
        assert cb.state == BreakerState.CLOSED
        assert cb.consecutive_failures == 0

    def test_on_open_callback(self):
        called_with = []
        cb = CircuitBreaker(
            name="test", max_failures=2,
            _on_open=lambda name, count: called_with.append((name, count)),
        )
        cb.record_failure()
        cb.record_failure()
        assert len(called_with) == 1
        assert called_with[0] == ("test", 2)

    def test_summary(self):
        cb = CircuitBreaker(name="test")
        cb.record_success()
        cb.record_failure()
        s = cb.summary()
        assert s["name"] == "test"
        assert s["state"] == "closed"
        assert s["total_successes"] == 1
        assert s["total_failures"] == 1

    def test_default_max_failures_is_3(self):
        cb = CircuitBreaker(name="test")
        assert cb.max_failures == MAX_CONSECUTIVE_FAILURES == 3


class TestCircuitBreakerRegistry:
    def test_get_or_create(self):
        reg = CircuitBreakerRegistry()
        cb1 = reg.get_or_create("foo")
        cb2 = reg.get_or_create("foo")
        assert cb1 is cb2

    def test_open_breakers(self):
        reg = CircuitBreakerRegistry()
        cb = reg.get_or_create("failing", max_failures=1)
        cb.record_failure()
        assert reg.open_breakers == ["failing"]

    def test_reset_all(self):
        reg = CircuitBreakerRegistry()
        cb = reg.get_or_create("failing", max_failures=1)
        cb.record_failure()
        reg.reset_all()
        assert reg.open_breakers == []

    def test_summary(self):
        reg = CircuitBreakerRegistry()
        reg.get_or_create("a")
        reg.get_or_create("b")
        s = reg.summary()
        assert "a" in s
        assert "b" in s
