"""
Background Memory — fork-inspired background encoding for IMI.

Inspired by Claude Code's runForkedAgent pattern: the main agent
continues working while a background process encodes memories.
In CC, forked agents share prompt cache for efficiency.

In Python, we use asyncio.create_task for non-blocking background
encoding. The main agent buffers experiences and a background loop
flushes them to IMI without blocking task execution.

This enables:
- Real-time memory encoding (not batch at end of session)
- Dream can run more frequently (every 4h vs 24h) since cost is lower
- Main agent is never blocked by memory operations
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from symbiont.memory import IMIMemory

logger = logging.getLogger(__name__)

# Background flush interval
FLUSH_INTERVAL_SECONDS = 30.0
# Dream interval (background consolidation)
DREAM_INTERVAL_SECONDS = 14400.0  # 4 hours (vs CC's 24h)
MIN_MEMORIES_FOR_DREAM = 5


class BackgroundMemory:
    """
    Background memory encoding — fork pattern adapted for Python.

    Wraps IMIMemory with a background asyncio task that:
    1. Periodically flushes buffered experiences (every 30s)
    2. Runs dream consolidation at intervals (every 4h)
    3. Never blocks the main agent loop

    Usage:
        bg = BackgroundMemory(memory)
        await bg.start()
        bg.remember("completed auth refactor", tags=["auth"])
        # ... memory is encoded in background ...
        await bg.stop()
    """

    def __init__(
        self,
        memory: IMIMemory,
        flush_interval: float = FLUSH_INTERVAL_SECONDS,
        dream_interval: float = DREAM_INTERVAL_SECONDS,
    ):
        self._memory = memory
        self._flush_interval = flush_interval
        self._dream_interval = dream_interval
        self._running = False
        self._flush_task: asyncio.Task | None = None
        self._dream_task: asyncio.Task | None = None
        self._last_dream: float = 0.0
        self._total_flushed: int = 0
        self._total_dreams: int = 0

    async def start(self) -> None:
        """Start background memory tasks."""
        if self._running:
            return
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        self._dream_task = asyncio.create_task(self._dream_loop())
        logger.info("background-memory: started (flush=%ds, dream=%ds)",
                     self._flush_interval, self._dream_interval)

    async def stop(self) -> None:
        """Stop background tasks and flush remaining buffer."""
        self._running = False

        # Final flush before stopping
        flushed = self._memory.flush()
        self._total_flushed += len(flushed)

        for task in (self._flush_task, self._dream_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        logger.info(
            "background-memory: stopped (total_flushed=%d, total_dreams=%d)",
            self._total_flushed, self._total_dreams,
        )

    def remember(self, experience: str, tags: list[str] | None = None, source: str = "symbiont") -> None:
        """
        Buffer an experience for background encoding.
        Non-blocking — returns immediately.
        """
        self._memory.buffer(experience, tags=tags, source=source)

    async def _flush_loop(self) -> None:
        """Background loop: periodically flush buffered memories."""
        while self._running:
            try:
                await asyncio.sleep(self._flush_interval)
                if self._memory.pending_count > 0:
                    results = self._memory.flush()
                    self._total_flushed += len(results)
                    if results:
                        logger.debug("background-memory: flushed %d memories", len(results))
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("background-memory: flush error")

    async def _dream_loop(self) -> None:
        """Background loop: periodically run dream consolidation."""
        while self._running:
            try:
                await asyncio.sleep(self._dream_interval)
                if self._memory.memory_count >= MIN_MEMORIES_FOR_DREAM:
                    result = self._memory.dream()
                    if result:
                        self._total_dreams += 1
                        self._last_dream = time.time()
                        logger.info("background-memory: dream cycle #%d complete", self._total_dreams)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("background-memory: dream error")

    @property
    def is_running(self) -> bool:
        return self._running

    def stats(self) -> dict:
        return {
            "running": self._running,
            "pending": self._memory.pending_count,
            "cursor": self._memory.cursor,
            "total_flushed": self._total_flushed,
            "total_dreams": self._total_dreams,
            "last_dream": self._last_dream,
            "flush_interval": self._flush_interval,
            "dream_interval": self._dream_interval,
        }
