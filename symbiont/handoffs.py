"""
Handoff Matrix — formalized collaboration rules for SYMBIONT agents.

Inspired by AIOX Course Module 7 (3-Tier Architecture + Handoff Matrix).
Defines who routes to whom, who collaborates, and who escalates.

Tiers:
  Tier 0 (Routing):    Scout — explores, triages, routes
  Tier 1 (Execution):  Worker — core work, code, analysis
  Tier 2 (Strategic):  Major — architecture, tiebreak, validation
  Meta:                Queen — lifecycle, spawning (not in decision chain)
  Support:             Minima — context prep, formatting (no LLM decisions)

Rules:
  - Scouts NEVER execute work — they explore and recommend
  - Workers NEVER make architectural decisions — they escalate to Major
  - Majors NEVER do routine work — they decide and validate
  - Queen NEVER participates in task execution — only lifecycle
  - Minima NEVER use expensive models — haiku only
"""

from __future__ import annotations

from dataclasses import dataclass, field
from symbiont.types import Caste


@dataclass
class HandoffRule:
    """Defines how a caste collaborates with others."""
    caste: Caste
    tier: int
    routes_to: list[Caste] = field(default_factory=list)
    collaborates_with: list[Caste] = field(default_factory=list)
    escalates_to: list[Caste] = field(default_factory=list)
    receives_from: list[Caste] = field(default_factory=list)
    max_hops: int = 3  # Max delegation chain before forcing a decision


# The Handoff Matrix
HANDOFF_MATRIX: dict[Caste, HandoffRule] = {
    Caste.SCOUT: HandoffRule(
        caste=Caste.SCOUT,
        tier=0,
        routes_to=[Caste.MEDIA, Caste.MAJOR],
        collaborates_with=[Caste.SCOUT],  # Scouts can swarm-explore together
        escalates_to=[Caste.MAJOR],
        receives_from=[Caste.QUEEN],
        max_hops=2,
    ),
    Caste.MEDIA: HandoffRule(
        caste=Caste.MEDIA,
        tier=1,
        routes_to=[Caste.MINIMA],  # Can delegate prep work to Minima
        collaborates_with=[Caste.MEDIA, Caste.SCOUT],  # Pod formation
        escalates_to=[Caste.MAJOR],  # Architectural questions go up
        receives_from=[Caste.SCOUT, Caste.MAJOR, Caste.QUEEN],
        max_hops=3,
    ),
    Caste.MAJOR: HandoffRule(
        caste=Caste.MAJOR,
        tier=2,
        routes_to=[Caste.MEDIA, Caste.SCOUT],  # Can dispatch work down
        collaborates_with=[Caste.MAJOR],  # Multi-Major consensus
        escalates_to=[],  # Top of chain — escalates to human
        receives_from=[Caste.SCOUT, Caste.MEDIA, Caste.QUEEN],
        max_hops=1,  # Majors decide quickly
    ),
    Caste.QUEEN: HandoffRule(
        caste=Caste.QUEEN,
        tier=-1,  # Meta — outside the execution chain
        routes_to=[Caste.SCOUT, Caste.MEDIA, Caste.MAJOR, Caste.MINIMA],
        collaborates_with=[],  # Queen doesn't collaborate — she spawns
        escalates_to=[],  # Queen IS the escalation endpoint for lifecycle
        receives_from=[],  # Queen observes demand signals, not tasks
        max_hops=1,
    ),
    Caste.MINIMA: HandoffRule(
        caste=Caste.MINIMA,
        tier=-1,  # Support — no decision authority
        routes_to=[],  # Minima can't delegate
        collaborates_with=[Caste.MINIMA],  # Can batch-process together
        escalates_to=[Caste.MEDIA],  # If something's wrong, tell a Worker
        receives_from=[Caste.MEDIA, Caste.QUEEN],
        max_hops=1,
    ),
}


def can_handoff(from_caste: Caste, to_caste: Caste) -> bool:
    """Check if a handoff from one caste to another is allowed."""
    rule = HANDOFF_MATRIX.get(from_caste)
    if not rule:
        return False
    return to_caste in rule.routes_to or to_caste in rule.collaborates_with


def can_escalate(from_caste: Caste, to_caste: Caste) -> bool:
    """Check if escalation from one caste to another is allowed."""
    rule = HANDOFF_MATRIX.get(from_caste)
    if not rule:
        return False
    return to_caste in rule.escalates_to


def get_tier(caste: Caste) -> int:
    """Get the tier of a caste."""
    rule = HANDOFF_MATRIX.get(caste)
    return rule.tier if rule else -1


def get_collaborators(caste: Caste) -> list[Caste]:
    """Get the castes that can collaborate with this one."""
    rule = HANDOFF_MATRIX.get(caste)
    return rule.collaborates_with if rule else []


def summary() -> dict:
    """Return a summary of the handoff matrix for display."""
    result = {}
    for caste, rule in HANDOFF_MATRIX.items():
        result[caste.name] = {
            "tier": rule.tier,
            "routes_to": [c.name for c in rule.routes_to],
            "collaborates_with": [c.name for c in rule.collaborates_with],
            "escalates_to": [c.name for c in rule.escalates_to],
            "max_hops": rule.max_hops,
        }
    return result
