"""Tests for the Antibody Registry (R5 — error memory)."""

import pytest

from symbiont.antibodies import Antibody, AntibodyRegistry


class TestAntibody:
    def test_matches_case_insensitive(self):
        ab = Antibody(id="x", pattern="ImportError", response="pip install", source_agent="a")
        assert ab.matches("importerror: no module named foo")
        assert ab.matches("IMPORTERROR in module bar")

    def test_no_match(self):
        ab = Antibody(id="x", pattern="ImportError", response="pip install", source_agent="a")
        assert not ab.matches("TypeError: expected str")


class TestAntibodyRegistry:
    def test_generate_and_check(self):
        reg = AntibodyRegistry()
        reg.generate("ImportError: no module named 'foo'", "pip install foo", "media:001")
        ab = reg.check("ImportError: no module named 'foo'")
        assert ab is not None
        assert ab.response == "pip install foo"
        assert ab.match_count == 1

    def test_check_no_match(self):
        reg = AntibodyRegistry()
        assert reg.check("TypeError: something") is None

    def test_generate_updates_existing(self):
        reg = AntibodyRegistry()
        reg.generate("ImportError: missing foo", "install foo", "a")
        reg.generate("ImportError: missing foo", "pip install foo --upgrade", "b")
        assert reg.count == 1  # Same pattern, updated
        ab = reg.check("ImportError: missing foo")
        assert ab.response == "pip install foo --upgrade"

    def test_remove(self):
        reg = AntibodyRegistry()
        ab = reg.generate("error X", "fix X", "a")
        assert reg.remove(ab.id)
        assert reg.count == 0

    def test_remove_nonexistent(self):
        reg = AntibodyRegistry()
        assert not reg.remove("fake")

    def test_list_all(self):
        reg = AntibodyRegistry()
        reg.generate("error A", "fix A", "agent1")
        reg.generate("error B", "fix B", "agent2")
        items = reg.list_all()
        assert len(items) == 2

    def test_summary(self):
        reg = AntibodyRegistry()
        reg.generate("error", "fix", "a")
        reg.check("error in module")  # 1 match
        reg.check("error in function")  # 2 matches
        s = reg.summary()
        assert s["antibodies"] == 1
        assert s["total_matches"] == 2

    def test_match_count_increments(self):
        reg = AntibodyRegistry()
        reg.generate("timeout error", "increase timeout", "a")
        reg.check("timeout error occurred")
        reg.check("timeout error again")
        ab = reg.check("timeout error third")
        assert ab.match_count == 3

    def test_confidence_takes_max(self):
        reg = AntibodyRegistry()
        reg.generate("error", "fix1", "a", confidence=0.7)
        reg.generate("error", "fix2", "b", confidence=0.9)
        ab = list(reg._antibodies.values())[0]
        assert ab.confidence == 0.9
