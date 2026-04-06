"""Tests for the dashboard."""

from symbiont.dashboard import get_dashboard_html


class TestDashboard:
    def test_returns_html(self):
        html = get_dashboard_html()
        assert "<!DOCTYPE html>" in html
        assert "SYMBIONT" in html

    def test_has_key_elements(self):
        html = get_dashboard_html()
        assert "agentCount" in html
        assert "channelCount" in html
        assert "colonyTable" in html
        assert "alertsCard" in html

    def test_has_auto_refresh(self):
        html = get_dashboard_html()
        assert "setInterval" in html
        assert "refresh" in html

    def test_minimum_size(self):
        html = get_dashboard_html()
        assert len(html) > 5000  # Should be substantial
