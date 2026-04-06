"""Tests for colony management."""

import json
import os
import tempfile

from symbiont.colony import DEFAULT_COLONIES, _load_colonies, _save_colonies, ColonyResult


class TestDefaultColonies:
    def test_has_kai_and_alan(self):
        assert "kai" in DEFAULT_COLONIES
        assert "alan" in DEFAULT_COLONIES

    def test_colony_structure(self):
        for name, info in DEFAULT_COLONIES.items():
            assert "host" in info
            assert "user" in info
            assert "description" in info


class TestColonyConfig:
    def test_save_and_load(self):
        path = tempfile.mktemp(suffix=".json")
        import symbiont.colony as colony_mod
        original = colony_mod.COLONY_CONFIG
        colony_mod.COLONY_CONFIG = type(original)(path)
        try:
            colonies = {"test": {"host": "1.2.3.4", "user": "root"}}
            _save_colonies(colonies)
            loaded = _load_colonies()
            assert "test" in loaded
            assert loaded["test"]["host"] == "1.2.3.4"
        finally:
            colony_mod.COLONY_CONFIG = original
            os.unlink(path)


class TestColonyResult:
    def test_create(self):
        r = ColonyResult(name="kai", host="1.2.3.4", success=True, output="ok")
        assert r.success is True
        assert r.name == "kai"

    def test_failure(self):
        r = ColonyResult(name="kai", host="1.2.3.4", success=False, output="", error="timeout")
        assert r.success is False
        assert r.error == "timeout"
