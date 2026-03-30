"""
Base Agent — the fundamental unit of the SYMBIONT organism.

Every agent, regardless of caste, shares the same lifecycle and
communication primitives. Specialization comes from capabilities
and the execute() method, not from different base classes.

Biological analogy: every cell has the same DNA — differentiation
comes from which genes are expressed (which capabilities are active).
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

from symbiont.types import (
    AgentState,
    Artifact,
    ArtifactStatus,
    Caste,
    Message,
    Signal,
    SignalType,
    WaggleReport,
    _uid,
)

if TYPE_CHECKING:
    from symbiont.core.mycelium import Mycelium
    from symbiont.core.mound import Mound
    from symbiont.core.murmuration import MurmurationBus
    from symbiont.core.governance import Governor

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    The fundamental SYMBIONT agent.

    Every agent:
    - Has an identity, caste, and set of capabilities
    - Communicates only through the Mycelium (never directly)
    - Deposits artifacts in the Mound (stigmergy)
    - Monitors neighbors via the Murmuration Bus
    - Reports heartbeats to maintain cohesion
    """

    def __init__(
        self,
        caste: Caste,
        capabilities: set[str] | None = None,
        agent_id: str | None = None,
    ) -> None:
        self.id = agent_id or f"{caste.name.lower()}:{_uid()}"
        self.caste = caste
        self.capabilities = capabilities or set()
        self.state = AgentState.SPAWNING
        self.trust_score: float = 0.5
        self.created_at: float = time.time()
        self._current_task: str = ""
        self._message_inbox: asyncio.Queue[Message] = asyncio.Queue()
        self._running = False
        self._loop_task: asyncio.Task | None = None

        # Systems — wired by the organism
        self._mycelium: Mycelium | None = None
        self._mound: Mound | None = None
        self._murmuration: MurmurationBus | None = None
        self._governor: Governor | None = None

        # LLM backend (pluggable)
        self._llm_backend: Any = None

    # ------------------------------------------------------------------
    # Wiring (called by the organism during boot)
    # ------------------------------------------------------------------

    def wire(
        self,
        mycelium: Mycelium,
        mound: Mound,
        murmuration: MurmurationBus,
        governor: Governor,
    ) -> None:
        """Connect this agent to all organism systems."""
        self._mycelium = mycelium
        self._mound = mound
        self._murmuration = murmuration
        self._governor = governor

    def set_llm_backend(self, backend: Any) -> None:
        """Set the LLM backend for this agent (model-agnostic interface)."""
        self._llm_backend = backend

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Boot the agent: register with systems and start the main loop."""
        self.state = AgentState.ACTIVE
        self._running = True

        # Register with governance
        if self._governor:
            self._governor.register_agent(self.id, self.caste)

        # Register with murmuration
        if self._murmuration:
            self._murmuration.register_agent(self.id)

        # Subscribe to caste-specific channel
        if self._mycelium:
            self._mycelium.subscribe(
                channel=f"caste:{self.caste.name.lower()}",
                subscriber_id=self.id,
                handler=self._handle_message,
            )
            # Subscribe to broadcast channel
            self._mycelium.subscribe(
                channel="broadcast",
                subscriber_id=self.id,
                handler=self._handle_message,
            )

        # Start main loop
        self._loop_task = asyncio.create_task(self._main_loop())

        logger.info("agent: '%s' (%s) started", self.id, self.caste.name)

    async def stop(self) -> None:
        """Gracefully shut down the agent."""
        self._running = False
        self.state = AgentState.TERMINATED

        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass

        if self._governor:
            self._governor.unregister_agent(self.id)
        if self._murmuration:
            self._murmuration.unregister_agent(self.id)

        logger.info("agent: '%s' stopped", self.id)

    async def hibernate(self) -> None:
        """Enter hibernation — warm state preserved, zero active cost."""
        self.state = AgentState.HIBERNATING
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        if self._governor:
            self._governor.hibernate_agent(self.id)
        logger.info("agent: '%s' hibernating", self.id)

    async def wake(self) -> None:
        """Wake from hibernation — warm start."""
        self.state = AgentState.ACTIVE
        self._running = True
        self._loop_task = asyncio.create_task(self._main_loop())
        logger.info("agent: '%s' woke from hibernation", self.id)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _main_loop(self) -> None:
        """The agent's heartbeat loop — process messages and report health."""
        while self._running:
            try:
                # Report heartbeat (murmuration cohesion)
                if self._murmuration:
                    self._murmuration.record_heartbeat(
                        self.id,
                        current_task=self._current_task,
                    )

                # Process queued messages
                while not self._message_inbox.empty():
                    try:
                        msg = self._message_inbox.get_nowait()
                        await self.on_message(msg)
                    except asyncio.QueueEmpty:
                        break

                await asyncio.sleep(1.0)  # Heartbeat interval

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("agent: '%s' loop error", self.id)
                if self._governor:
                    self._governor.record_error(self.id)
                await asyncio.sleep(2.0)

    # ------------------------------------------------------------------
    # Communication (through Mycelium only)
    # ------------------------------------------------------------------

    async def publish(self, channel: str, payload: Any, priority: int = 5) -> None:
        """Publish a message through the Mycelium."""
        if self._mycelium:
            await self._mycelium.publish(
                channel=channel,
                payload=payload,
                sender_id=self.id,
                priority=priority,
            )

    async def _handle_message(self, msg: Message) -> None:
        """Internal handler — queues messages for processing in main loop."""
        await self._message_inbox.put(msg)

    async def on_message(self, msg: Message) -> None:
        """
        Handle an incoming message. Override in subclasses for caste-specific behavior.
        Default: log and ignore.
        """
        logger.debug("agent: '%s' received message on '%s'", self.id, msg.channel)

    # ------------------------------------------------------------------
    # Stigmergy (deposit artifacts in the Mound)
    # ------------------------------------------------------------------

    async def deposit_artifact(
        self,
        kind: str,
        content: Any,
        quality: float = 0.5,
        confidence: float = 0.5,
        tags: set[str] | None = None,
        metadata: dict | None = None,
    ) -> Artifact | None:
        """Deposit a work artifact — this IS the communication to next agents."""
        if not self._mound:
            return None

        artifact = Artifact(
            kind=kind,
            content=content,
            status=ArtifactStatus.DRAFT,
            author_id=self.id,
            quality=quality,
            confidence=confidence,
            tags=tags or set(),
            metadata=metadata or {},
        )
        await self._mound.deposit(artifact)

        # Also announce via Mycelium so watchers can react
        await self.publish(
            channel=f"artifact:{kind}",
            payload={"artifact_id": artifact.id, "kind": kind, "quality": quality},
            priority=3,
        )

        return artifact

    # ------------------------------------------------------------------
    # Signal emission (Murmuration Bus)
    # ------------------------------------------------------------------

    async def emit_signal(self, signal_type: SignalType, payload: Any = None) -> None:
        """Emit a signal on the Murmuration Bus."""
        if self._murmuration:
            signal = Signal(
                signal_type=signal_type,
                source_id=self.id,
                payload=payload,
            )
            await self._murmuration.emit(signal)

    # ------------------------------------------------------------------
    # Core execution (to be implemented by each caste)
    # ------------------------------------------------------------------

    @abstractmethod
    async def execute(self, task: str, context: dict | None = None) -> Any:
        """
        Execute a task. This is the caste-specific behavior.
        - Minima: context preparation, cleanup
        - Media: core work (code, analysis)
        - Major: decisions, architecture
        - Scout: exploration, evaluation
        - Queen: spawning agents
        """
        ...

    # ------------------------------------------------------------------
    # LLM interaction (model-agnostic)
    # ------------------------------------------------------------------

    async def think(self, prompt: str, context: dict | None = None) -> str:
        """
        Use the LLM backend to reason about a prompt.
        Falls back to a simple echo if no backend is configured.
        """
        if self._llm_backend:
            return await self._llm_backend.complete(
                prompt=prompt,
                context=context or {},
                model_tier=self._get_model_tier(),
            )
        # Fallback: no LLM backend — return the prompt as a marker
        return f"[{self.caste.name}:{self.id}] would think about: {prompt[:100]}"

    def _get_model_tier(self) -> str:
        """Map caste to model tier."""
        tier_map = {
            Caste.MINIMA: "haiku",
            Caste.SCOUT: "haiku",
            Caste.MEDIA: "sonnet",
            Caste.MAJOR: "opus",
            Caste.QUEEN: "opus",
        }
        return tier_map.get(self.caste, "sonnet")

    # ------------------------------------------------------------------
    # Task tracking
    # ------------------------------------------------------------------

    def set_current_task(self, task: str) -> None:
        self._current_task = task
        self.state = AgentState.BUSY if task else AgentState.ACTIVE

    def clear_current_task(self) -> None:
        self._current_task = ""
        self.state = AgentState.ACTIVE
        if self._governor:
            self._governor.record_task_complete(self.id)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} caste={self.caste.name} state={self.state.name}>"
