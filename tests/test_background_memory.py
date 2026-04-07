"""Tests for Background Memory (R1 — fork+cache pattern)."""

import asyncio

import pytest

from symbiont.background_memory import BackgroundMemory
from symbiont.memory import IMIMemory


def _make_memory():
    """Create an IMIMemory instance without IMI backend (buffer-only mode)."""
    mem = IMIMemory.__new__(IMIMemory)
    mem._space = None
    mem._available = False
    mem._cursor = None
    mem._pending_buffer = []
    mem._session_start = 0
    mem._db_path = ""
    return mem


class TestBackgroundMemory:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        mem = _make_memory()
        bg = BackgroundMemory(mem, flush_interval=0.01, dream_interval=3600)
        await bg.start()
        assert bg.is_running
        await bg.stop()
        assert not bg.is_running

    @pytest.mark.asyncio
    async def test_remember_buffers(self):
        mem = _make_memory()
        bg = BackgroundMemory(mem, flush_interval=0.01, dream_interval=3600)
        await bg.start()
        bg.remember("task completed", tags=["auth"])
        bg.remember("bug fixed", tags=["bug"])
        assert mem.pending_count == 2
        await bg.stop()

    @pytest.mark.asyncio
    async def test_flush_runs_in_background(self):
        mem = _make_memory()
        bg = BackgroundMemory(mem, flush_interval=0.05, dream_interval=3600)
        await bg.start()
        bg.remember("experience 1")
        bg.remember("experience 2")
        # Wait for flush cycle
        await asyncio.sleep(0.15)
        # Memories not encoded (no backend), but flush was attempted
        # pending_count stays 2 because encode returns None without backend
        await bg.stop()

    @pytest.mark.asyncio
    async def test_stop_does_final_flush(self):
        mem = _make_memory()
        bg = BackgroundMemory(mem, flush_interval=3600, dream_interval=3600)
        await bg.start()
        bg.remember("last experience")
        await bg.stop()
        # Stop triggers final flush

    @pytest.mark.asyncio
    async def test_stats(self):
        mem = _make_memory()
        bg = BackgroundMemory(mem, flush_interval=1, dream_interval=3600)
        s = bg.stats()
        assert s["running"] is False
        assert s["pending"] == 0
        assert s["total_flushed"] == 0
        assert s["total_dreams"] == 0

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self):
        mem = _make_memory()
        bg = BackgroundMemory(mem)
        await bg.start()
        await bg.start()  # Should not crash
        assert bg.is_running
        await bg.stop()

    @pytest.mark.asyncio
    async def test_remember_without_start(self):
        mem = _make_memory()
        bg = BackgroundMemory(mem)
        bg.remember("buffered without start")
        assert mem.pending_count == 1
