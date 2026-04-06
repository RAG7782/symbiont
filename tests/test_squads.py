"""Tests for squad management."""

import os
import tempfile

import pytest

from symbiont.persistence import PersistenceStore
from symbiont.squads import Squad, SquadManager


@pytest.fixture
def store():
    db = tempfile.mktemp(suffix=".db")
    s = PersistenceStore(db)
    yield s
    s.close()
    os.unlink(db)


class TestSquad:
    def test_create(self):
        s = Squad("legal", description="Legal team")
        assert s.name == "legal"
        assert s.size == 0

    def test_add_agent(self):
        s = Squad("dev")
        s.add_agent("a1")
        s.add_agent("a2")
        assert s.size == 2
        # No duplicates
        s.add_agent("a1")
        assert s.size == 2

    def test_remove_agent(self):
        s = Squad("dev", agent_ids=["a1", "a2"])
        assert s.remove_agent("a1") is True
        assert s.size == 1
        assert s.remove_agent("nonexistent") is False

    def test_to_dict(self):
        s = Squad("legal", description="Law", agent_ids=["a1"], context={"domain": "law"})
        d = s.to_dict()
        assert d["name"] == "legal"
        assert d["size"] == 1
        assert d["context"]["domain"] == "law"


class TestSquadManager:
    def test_create_and_list(self, store):
        mgr = SquadManager(store=store)
        mgr.create("legal", description="Legal team")
        mgr.create("dev", description="Dev team")
        squads = mgr.list_squads()
        assert len(squads) == 2
        assert "legal" in squads

    def test_assign(self, store):
        mgr = SquadManager(store=store)
        mgr.create("dev")
        mgr.assign("dev", ["a1", "a2", "a3"])
        squad = mgr.get("dev")
        assert squad.size == 3

    def test_unassign(self, store):
        mgr = SquadManager(store=store)
        mgr.create("dev")
        mgr.assign("dev", ["a1", "a2"])
        assert mgr.unassign("dev", "a1") is True
        assert mgr.get("dev").size == 1

    def test_delete(self, store):
        mgr = SquadManager(store=store)
        mgr.create("temp")
        assert mgr.delete("temp") is True
        assert mgr.delete("nonexistent") is False
        assert mgr.total_squads == 0

    def test_get_agent_squad(self, store):
        mgr = SquadManager(store=store)
        mgr.create("legal")
        mgr.assign("legal", ["a1"])
        assert mgr.get_agent_squad("a1") == "legal"
        assert mgr.get_agent_squad("unknown") is None

    def test_persistence_reload(self, store):
        mgr1 = SquadManager(store=store)
        mgr1.create("legal", description="Law", context={"domain": "law"})
        mgr1.assign("legal", ["a1", "a2"])
        # Reload from same store
        mgr2 = SquadManager(store=store)
        squads = mgr2.list_squads()
        assert "legal" in squads
        assert squads["legal"]["size"] == 2

    def test_total_assigned(self, store):
        mgr = SquadManager(store=store)
        mgr.create("a")
        mgr.create("b")
        mgr.assign("a", ["a1", "a2"])
        mgr.assign("b", ["b1"])
        assert mgr.total_assigned == 3
