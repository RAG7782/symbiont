"""SYMBIONT configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from symbiont.types import Caste


@dataclass
class CasteConfig:
    """Configuration for a single caste type."""
    model_tier: str = "sonnet"         # haiku / sonnet / opus
    max_instances: int = 10
    capabilities: set[str] = field(default_factory=set)
    cost_weight: float = 1.0           # Relative cost multiplier
    warm_pool_size: int = 0            # Pre-hibernated reserve agents


DEFAULT_CASTE_CONFIGS: dict[Caste, CasteConfig] = {
    Caste.MINIMA: CasteConfig(
        model_tier="haiku",
        max_instances=20,
        capabilities={"context_prep", "formatting", "cleanup", "indexing"},
        cost_weight=0.1,
        warm_pool_size=5,
    ),
    Caste.MEDIA: CasteConfig(
        model_tier="sonnet",
        max_instances=10,
        capabilities={"code", "analysis", "transform", "test", "review"},
        cost_weight=1.0,
        warm_pool_size=3,
    ),
    Caste.MAJOR: CasteConfig(
        model_tier="opus",
        max_instances=3,
        capabilities={"architecture", "decision", "disambiguation", "planning"},
        cost_weight=5.0,
        warm_pool_size=1,
    ),
    Caste.SCOUT: CasteConfig(
        model_tier="haiku",
        max_instances=8,
        capabilities={"explore", "discover", "evaluate", "probe"},
        cost_weight=0.2,
        warm_pool_size=2,
    ),
    Caste.QUEEN: CasteConfig(
        model_tier="opus",
        max_instances=1,
        capabilities={"spawn", "suppress", "lifecycle"},
        cost_weight=3.0,
        warm_pool_size=0,  # Queen has no reserve — leader election handles failover
    ),
}


@dataclass
class TopologyConfig:
    """Physarum-inspired topology engine settings."""
    explore_ratio: float = 0.15        # % of resources always exploring
    reinforce_threshold: float = 0.7   # Min flow score to reinforce a path
    prune_idle_cycles: int = 10        # Cycles with no flow before pruning
    probe_interval_sec: float = 30.0   # How often to spawn probes


@dataclass
class MurmurationConfig:
    """Starling-inspired coordination settings."""
    max_neighbors: int = 7
    heartbeat_interval_sec: float = 5.0
    reflex_timeout_sec: float = 2.0
    wave_ttl: int = 7                  # Max propagation hops


@dataclass
class WaggleConfig:
    """Bee-inspired decision protocol settings."""
    min_scouts: int = 3
    max_scouts: int = 7
    scout_timeout_sec: float = 60.0
    amplification_threshold: float = 0.6   # Min intensity to amplify
    recruitment_rounds: int = 2


@dataclass
class GovernanceConfig:
    """Mole-rat + Wolf governance settings."""
    election_timeout_sec: float = 30.0
    reserve_activation_sec: float = 5.0    # Warm start time
    phase_auto_transition: bool = True


@dataclass
class HomeostasisConfig:
    """Termite mound homeostasis thresholds."""
    max_latency_ms: float = 5000.0
    max_error_rate: float = 0.1
    min_test_coverage: float = 0.7
    max_context_drift: float = 0.5
    check_interval_sec: float = 10.0


@dataclass
class SymbiontConfig:
    """Root configuration for the SYMBIONT organism."""
    castes: dict[Caste, CasteConfig] = field(default_factory=lambda: dict(DEFAULT_CASTE_CONFIGS))
    topology: TopologyConfig = field(default_factory=TopologyConfig)
    murmuration: MurmurationConfig = field(default_factory=MurmurationConfig)
    waggle: WaggleConfig = field(default_factory=WaggleConfig)
    governance: GovernanceConfig = field(default_factory=GovernanceConfig)
    homeostasis: HomeostasisConfig = field(default_factory=HomeostasisConfig)
