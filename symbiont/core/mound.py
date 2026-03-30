"""
System 5 — MOUND ARCHITECTURE (Macrotermes bellicosus)

The skeletal system of SYMBIONT. Artifacts produced by agents are living
infrastructure that guides future behavior (stigmergy). The Mound also
maintains homeostasis — monitoring system health and triggering feedback loops.

Key biological properties:
- Artifact as signal: the work product IS the communication
- Homeostasis: monitoring "temperature" and auto-correcting
- Fungus garden: a collectively maintained knowledge base
- Ventilation: feedback loops that keep the system stable
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict

from symbiont.config import HomeostasisConfig
from symbiont.types import Artifact, ArtifactStatus, HealthMetrics

logger = logging.getLogger(__name__)


class Mound:
    """
    The artifact store and homeostasis monitor.

    Every piece of work is deposited here with metadata. Other agents
    react to artifacts — this IS the coordination mechanism (stigmergy).
    The homeostasis system monitors health and triggers corrective actions.
    """

    def __init__(self, homeostasis_config: HomeostasisConfig | None = None) -> None:
        self._artifacts: dict[str, Artifact] = {}
        self._by_kind: dict[str, list[str]] = defaultdict(list)
        self._by_tag: dict[str, list[str]] = defaultdict(list)
        self._by_status: dict[ArtifactStatus, list[str]] = defaultdict(list)
        self._knowledge_base: dict[str, str] = {}  # The "fungus garden"
        self._health = HealthMetrics()
        self._homeostasis_config = homeostasis_config or HomeostasisConfig()
        self._watchers: list[tuple[str, asyncio.Event]] = []
        self._feedback_handlers: dict[str, list] = defaultdict(list)
        self._running = False
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Artifact Store (Stigmergy)
    # ------------------------------------------------------------------

    async def deposit(self, artifact: Artifact) -> Artifact:
        """
        Deposit an artifact. This is the primary stigmergic action —
        an agent modifies the shared environment, and other agents react.
        """
        self._artifacts[artifact.id] = artifact
        self._by_kind[artifact.kind].append(artifact.id)
        self._by_status[artifact.status].append(artifact.id)
        for tag in artifact.tags:
            self._by_tag[tag].append(artifact.id)

        self._health.artifacts_total = len(self._artifacts)

        # Notify watchers
        for kind_filter, event in self._watchers:
            if kind_filter == "*" or kind_filter == artifact.kind:
                event.set()

        logger.debug(
            "mound: deposited artifact '%s' (kind=%s, status=%s)",
            artifact.id,
            artifact.kind,
            artifact.status.name,
        )
        return artifact

    async def update(self, artifact_id: str, **changes) -> Artifact | None:
        """Update an existing artifact. Triggers stigmergic reactions."""
        artifact = self._artifacts.get(artifact_id)
        if not artifact:
            return None

        old_status = artifact.status
        for key, value in changes.items():
            if hasattr(artifact, key):
                setattr(artifact, key, value)
        artifact.touch()

        # Re-index if status changed
        if "status" in changes and old_status != artifact.status:
            if artifact_id in self._by_status.get(old_status, []):
                self._by_status[old_status].remove(artifact_id)
            self._by_status[artifact.status].append(artifact_id)

        # Notify watchers
        for kind_filter, event in self._watchers:
            if kind_filter == "*" or kind_filter == artifact.kind:
                event.set()

        return artifact

    def get(self, artifact_id: str) -> Artifact | None:
        return self._artifacts.get(artifact_id)

    def query(
        self,
        kind: str | None = None,
        status: ArtifactStatus | None = None,
        tag: str | None = None,
        min_quality: float = 0.0,
    ) -> list[Artifact]:
        """Query artifacts by filters."""
        candidates = set(self._artifacts.keys())

        if kind:
            candidates &= set(self._by_kind.get(kind, []))
        if status:
            candidates &= set(self._by_status.get(status, []))
        if tag:
            candidates &= set(self._by_tag.get(tag, []))

        results = [self._artifacts[aid] for aid in candidates if self._artifacts[aid].quality >= min_quality]
        return sorted(results, key=lambda a: a.updated_at, reverse=True)

    async def wait_for_artifact(self, kind: str = "*", timeout: float = 60.0) -> bool:
        """Wait until an artifact of the given kind is deposited."""
        event = asyncio.Event()
        watcher = (kind, event)
        self._watchers.append(watcher)
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self._watchers.remove(watcher)

    # ------------------------------------------------------------------
    # Knowledge Base (Fungus Garden)
    # ------------------------------------------------------------------

    def learn(self, key: str, knowledge: str) -> None:
        """Add or update knowledge in the shared garden."""
        self._knowledge_base[key] = knowledge

    def recall(self, key: str) -> str | None:
        """Retrieve knowledge from the garden."""
        return self._knowledge_base.get(key)

    def search_knowledge(self, query: str) -> list[tuple[str, str]]:
        """Simple keyword search in the knowledge base."""
        query_lower = query.lower()
        results = []
        for key, value in self._knowledge_base.items():
            if query_lower in key.lower() or query_lower in value.lower():
                results.append((key, value))
        return results

    def forget(self, key: str) -> bool:
        """Remove stale knowledge (Physarum-style pruning of the garden)."""
        return self._knowledge_base.pop(key, None) is not None

    # ------------------------------------------------------------------
    # Homeostasis (Termite Ventilation)
    # ------------------------------------------------------------------

    def register_feedback_handler(self, metric: str, handler) -> None:
        """Register a handler that fires when a health metric goes out of range."""
        self._feedback_handlers[metric].append(handler)

    async def start_homeostasis(self) -> None:
        """Start the homeostasis monitoring loop."""
        self._running = True
        self._task = asyncio.create_task(self._homeostasis_loop())
        logger.info("mound: homeostasis started")

    async def stop_homeostasis(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _homeostasis_loop(self) -> None:
        while self._running:
            try:
                await self._check_vitals()
                await asyncio.sleep(self._homeostasis_config.check_interval_sec)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("mound: homeostasis check error")

    async def _check_vitals(self) -> None:
        """Run all health checks and trigger feedback loops if needed."""
        h = self._health
        config = self._homeostasis_config
        violations = []

        if h.latency_ms > config.max_latency_ms:
            violations.append(("latency", h.latency_ms))
        if h.error_rate > config.max_error_rate:
            violations.append(("error_rate", h.error_rate))
        if h.test_coverage < config.min_test_coverage:
            violations.append(("test_coverage", h.test_coverage))
        if h.context_drift > config.max_context_drift:
            violations.append(("context_drift", h.context_drift))

        for metric, value in violations:
            logger.warning("mound: homeostasis violation — %s=%.2f", metric, value)
            for handler in self._feedback_handlers.get(metric, []):
                try:
                    await handler(metric, value)
                except Exception:
                    logger.exception("mound: feedback handler error for %s", metric)

    def update_health(self, **metrics) -> None:
        """Update health metrics (called by monitoring agents)."""
        for key, value in metrics.items():
            if hasattr(self._health, key):
                setattr(self._health, key, value)
        self._health.timestamp = time.time()

    @property
    def health(self) -> HealthMetrics:
        return self._health

    @property
    def artifact_count(self) -> int:
        return len(self._artifacts)
