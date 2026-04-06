"""Tests for the alert system."""

import pytest

from symbiont.alerts import _state, get_alert_state, AlertState


class TestAlertState:
    def test_initial_state(self):
        state = AlertState()
        assert len(state.colony_down) == 0
        assert state.bridge_down == 0.0
        assert len(state.consecutive_failures) == 0

    def test_get_alert_state(self):
        state = get_alert_state()
        assert "colonies_down" in state
        assert "bridge_down" in state
        assert "telegram_configured" in state
        assert "webhook_configured" in state
        assert isinstance(state["colonies_down"], list)

    def test_consecutive_failures_tracking(self):
        state = AlertState()
        state.consecutive_failures["kai"] = 3
        assert state.consecutive_failures["kai"] == 3
