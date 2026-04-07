"""Tests for IMI Memory incremental cursor (R2)."""

import pytest

from symbiont.memory import IMIMemory


class TestIMIMemoryCursor:
    """Test cursor and buffer functionality without requiring IMI backend."""

    def test_initial_cursor_is_none(self):
        mem = IMIMemory.__new__(IMIMemory)
        mem._space = None
        mem._available = False
        mem._cursor = None
        mem._pending_buffer = []
        mem._session_start = 0
        mem._db_path = ""
        assert mem.cursor is None

    def test_buffer_adds_to_pending(self):
        mem = IMIMemory.__new__(IMIMemory)
        mem._space = None
        mem._available = False
        mem._cursor = None
        mem._pending_buffer = []
        mem._session_start = 0
        mem._db_path = ""

        mem.buffer("test experience 1", tags=["test"])
        mem.buffer("test experience 2", tags=["test"])
        assert mem.pending_count == 2

    def test_flush_with_unavailable_backend(self):
        mem = IMIMemory.__new__(IMIMemory)
        mem._space = None
        mem._available = False
        mem._cursor = None
        mem._pending_buffer = []
        mem._session_start = 0
        mem._db_path = ""

        mem.buffer("experience 1")
        mem.buffer("experience 2")
        results = mem.flush()
        # All fail because backend unavailable — stay in buffer
        assert results == []
        assert mem.pending_count == 2

    def test_reset_cursor(self):
        mem = IMIMemory.__new__(IMIMemory)
        mem._space = None
        mem._available = False
        mem._cursor = "abc-123"
        mem._pending_buffer = []
        mem._session_start = 0
        mem._db_path = ""

        mem.reset_cursor()
        assert mem.cursor is None

    def test_stats_include_cursor_info(self):
        mem = IMIMemory.__new__(IMIMemory)
        mem._space = None
        mem._available = False
        mem._cursor = "xyz-789"
        mem._pending_buffer = [{"experience": "x"}]
        mem._session_start = 0
        mem._db_path = ""

        s = mem.stats()
        assert s["cursor"] == "xyz-789"
        assert s["pending"] == 1

    def test_buffer_preserves_tags_and_source(self):
        mem = IMIMemory.__new__(IMIMemory)
        mem._space = None
        mem._available = False
        mem._cursor = None
        mem._pending_buffer = []
        mem._session_start = 0
        mem._db_path = ""

        mem.buffer("experience", tags=["auth", "fix"], source="scout:001")
        item = mem._pending_buffer[0]
        assert item["tags"] == ["auth", "fix"]
        assert item["source"] == "scout:001"
        assert "buffered_at" in item
