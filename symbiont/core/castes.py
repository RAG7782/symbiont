"""
System 3 — CASTES (Ant — Atta / Eciton)

Cellular differentiation of the SYMBIONT organism. Defines agent types,
their specializations, and how they interact via stigmergy.

Key biological properties:
- Physical polymorphism: each caste has a distinct body/toolset
- Communication via artifacts (stigmergy), not direct messages
- Caste proportions self-regulate based on demand
- The queen spawns, she does not command
"""

from __future__ import annotations

import logging
from collections import Counter

from symbiont.config import CasteConfig, DEFAULT_CASTE_CONFIGS
from symbiont.types import Caste

logger = logging.getLogger(__name__)


class CasteRegistry:
    """
    Manages caste configurations and tracks the population of each caste.

    The registry enforces max instances per caste and provides the
    self-regulation mechanism (adjusting caste proportions based on demand).
    """

    def __init__(
        self, configs: dict[Caste, CasteConfig] | None = None
    ) -> None:
        self._configs = configs or dict(DEFAULT_CASTE_CONFIGS)
        self._population: Counter[Caste] = Counter()
        self._demand_signals: Counter[Caste] = Counter()

    def get_config(self, caste: Caste) -> CasteConfig:
        return self._configs[caste]

    def can_spawn(self, caste: Caste) -> bool:
        """Check if the population limit allows spawning another agent of this caste."""
        config = self._configs[caste]
        return self._population[caste] < config.max_instances

    def register_birth(self, caste: Caste) -> None:
        """Record that a new agent of this caste was spawned."""
        self._population[caste] += 1
        logger.debug("castes: +1 %s (total=%d)", caste.name, self._population[caste])

    def register_death(self, caste: Caste) -> None:
        """Record that an agent of this caste was terminated."""
        self._population[caste] = max(0, self._population[caste] - 1)
        logger.debug("castes: -1 %s (total=%d)", caste.name, self._population[caste])

    def register_hibernation(self, caste: Caste) -> None:
        """Agent hibernated — still counts toward population but is inactive."""
        pass  # Population count stays; governance tracks active vs hibernating

    def signal_demand(self, caste: Caste, intensity: float = 1.0) -> None:
        """
        Signal that more agents of this caste are needed.

        The self-regulation mechanism: when work requires more agents of a
        certain caste, demand signals accumulate. The Queen reads these to
        decide what to spawn next.
        """
        self._demand_signals[caste] += intensity

    def consume_demand(self) -> Caste | None:
        """
        Return the caste with highest unmet demand, consuming the signal.
        Used by the Queen to decide what to spawn.
        Returns None if no demand exists or all castes are at capacity.
        """
        # Sort by demand intensity, descending
        for caste, demand in self._demand_signals.most_common():
            if demand > 0 and self.can_spawn(caste):
                self._demand_signals[caste] = max(0, demand - 1)
                return caste
        return None

    def get_population(self) -> dict[Caste, int]:
        return dict(self._population)

    def get_demand(self) -> dict[Caste, float]:
        return dict(self._demand_signals)

    def get_recommended_spawns(self) -> list[Caste]:
        """
        Auto-regulation: compare current population ratios with demand
        and return which castes should be spawned.
        """
        recommendations = []
        for caste in Caste:
            demand = self._demand_signals.get(caste, 0)
            population = self._population.get(caste, 0)
            config = self._configs.get(caste)
            if config and demand > 0 and population < config.max_instances:
                recommendations.append(caste)
        return recommendations

    @property
    def total_population(self) -> int:
        return sum(self._population.values())

    def summary(self) -> dict[str, dict]:
        """Return a summary of all castes: population, demand, capacity."""
        result = {}
        for caste in Caste:
            config = self._configs.get(caste)
            if config:
                result[caste.name] = {
                    "population": self._population[caste],
                    "max": config.max_instances,
                    "demand": self._demand_signals[caste],
                    "model": config.model_tier,
                    "cost": config.cost_weight,
                }
        return result
