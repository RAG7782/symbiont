"""Shared types and data structures for the SYMBIONT organism."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Coroutine


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Caste(Enum):
    """Agent castes — modeled after ant polymorphism."""
    MINIMA = auto()   # Small, cheap, high-cardinality context workers
    MEDIA = auto()    # Core execution workers
    MAJOR = auto()    # Expensive specialists / decision makers
    SCOUT = auto()    # Explorers with broad tool access
    QUEEN = auto()    # Spawner — not a commander


class AgentState(Enum):
    """Lifecycle states for an agent."""
    SPAWNING = auto()
    ACTIVE = auto()
    BUSY = auto()
    HIBERNATING = auto()
    TERMINATED = auto()


class Phase(Enum):
    """Governance phases — contextual leadership (wolf model)."""
    EXPLORATION = auto()
    DECISION = auto()
    EXECUTION = auto()
    VALIDATION = auto()
    DELIVERY = auto()


class SignalType(Enum):
    """Murmuration bus signal types."""
    HEARTBEAT = auto()
    ALERT = auto()
    PRIORITY_SHIFT = auto()
    HALT = auto()
    REFLEX = auto()
    HUMAN_OVERRIDE = auto()


class Impulse(Enum):
    """Starling-inspired impulses for the murmuration bus."""
    REPEL = auto()    # Avoid duplicate work
    ALIGN = auto()    # Follow majority direction
    COHERE = auto()   # Stay connected to neighbors


class QuorumLevel(Enum):
    """Dynamic quorum thresholds (bee model)."""
    LOW = 2       # Reversible decisions
    MEDIUM = 4    # Moderate-cost decisions
    HIGH = 6      # Architecture / expensive decisions
    CRITICAL = 8  # Irreversible + requires human confirmation


class ArtifactStatus(Enum):
    """Status of a work artifact in the Mound."""
    DRAFT = auto()
    IN_PROGRESS = auto()
    REVIEW = auto()
    CONTESTED = auto()
    APPROVED = auto()
    ARCHIVED = auto()


class PodLevel(Enum):
    """Dolphin-inspired coalition levels."""
    POD = 1          # 2-4 agents
    SUPER_POD = 2    # 2-3 pods
    SWARM = 3        # Full mobilization


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> float:
    return time.time()


@dataclass
class Message:
    """A message flowing through the Mycelium."""
    id: str = field(default_factory=_uid)
    channel: str = ""
    sender_id: str = ""
    payload: Any = None
    priority: int = 5          # 1 (highest) to 10 (lowest)
    timestamp: float = field(default_factory=_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Signal:
    """A fast signal on the Murmuration Bus."""
    id: str = field(default_factory=_uid)
    signal_type: SignalType = SignalType.HEARTBEAT
    source_id: str = ""
    payload: Any = None
    ttl: int = 7               # Max hops (propagation depth)
    timestamp: float = field(default_factory=_now)
    seen_by: set[str] = field(default_factory=set)


@dataclass
class Artifact:
    """A work product in the Mound — stigmergic communication."""
    id: str = field(default_factory=_uid)
    kind: str = ""             # code, doc, config, decision, report...
    content: Any = None
    status: ArtifactStatus = ArtifactStatus.DRAFT
    author_id: str = ""
    quality: float = 0.0       # 0.0–1.0
    confidence: float = 0.0    # 0.0–1.0
    tags: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)

    def touch(self) -> None:
        self.updated_at = _now()


@dataclass
class WaggleReport:
    """Structured report from a scout (bee waggle dance)."""
    id: str = field(default_factory=_uid)
    scout_id: str = ""
    option: str = ""
    description: str = ""
    quality: float = 0.0       # 0.0–1.0
    confidence: float = 0.0    # 0.0–1.0
    estimated_cost: float = 0.0
    evidence: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=_now)

    @property
    def intensity(self) -> float:
        """Dance intensity — higher means more convincing."""
        return self.quality * self.confidence


@dataclass
class AllianceRequest:
    """A request to form a Pod (dolphin alliance)."""
    id: str = field(default_factory=_uid)
    requester_id: str = ""
    needed_capabilities: set[str] = field(default_factory=set)
    objective: str = ""
    max_members: int = 4
    timestamp: float = field(default_factory=_now)


@dataclass
class HealthMetrics:
    """Homeostasis metrics for the Mound (termite ventilation)."""
    latency_ms: float = 0.0
    error_rate: float = 0.0
    test_coverage: float = 1.0
    context_drift: float = 0.0
    active_agents: int = 0
    hibernating_agents: int = 0
    artifacts_total: int = 0
    messages_per_second: float = 0.0
    timestamp: float = field(default_factory=_now)

    def is_healthy(self) -> bool:
        return (
            self.error_rate < 0.1
            and self.latency_ms < 5000
            and self.context_drift < 0.5
        )


# ---------------------------------------------------------------------------
# Callback types
# ---------------------------------------------------------------------------

MessageHandler = Callable[[Message], Coroutine[Any, Any, None]]
SignalHandler = Callable[[Signal], Coroutine[Any, Any, None]]
