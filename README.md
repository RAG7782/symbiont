# SYMBIONT

**Symbiotic Multi-pattern Bio-intelligent Organism for Networked Tasks**

A framework that integrates eight biological swarm patterns into a unified organism for LLM agent coordination.

## The Problem

LLM agent frameworks (LangChain, CrewAI, AutoGen) impose coordination **top-down**: a central planner assigns tasks, a fixed pipeline determines order. Agents cannot self-organize, form spontaneous coalitions, or adapt coordination patterns to changing demands.

Biological superorganisms solved this long ago. SYMBIONT imports their solutions — selectively.

## Design Principle

**Functional inspiration, not structural replication.** Each biological mechanism is imported only if the computational problem it solves exists in LLM agent orchestration.

## Eight Biological Systems

| # | Source | System | Role |
|---|--------|--------|------|
| 1 | Mycorrhizal Fungus | **Mycelium** | Adaptive message routing — channels thicken with use |
| 2 | Slime Mold (*Physarum*) | **Topology Engine** | Network self-optimization via explore-reinforce-prune |
| 3 | Leaf-cutter Ant (*Atta*) | **Caste Registry** | 5-caste agent polymorphism with demand signals |
| 4 | Honeybee (*Apis mellifera*) | **Waggle Protocol** | Collective decision-making with dynamic quorum |
| 5 | Termite (*Macrotermes*) | **Mound** | Stigmergic artifacts + homeostasis feedback |
| 6 | Starling (*Sturnus*) | **Murmuration Bus** | Real-time reflexes, O(log N) alert propagation |
| 7 | Wolf + Naked Mole-rat | **Governor** | Contextual leadership + suppression/reserves |
| 8 | Dolphin (*Tursiops*) | **Pod Dynamics** | Ephemeral coalitions: Pod → Super-Pod → Swarm |

## Five Agent Castes

Castes map directly to LLM model tiers:

| Caste | LLM Tier | Cost | Role | Max |
|-------|----------|------|------|-----|
| **Minima** | Haiku | 0.1x | Context prep, formatting, cleanup | 20 |
| **Media** | Sonnet | 1.0x | Core execution — code, analysis, review | 10 |
| **Major** | Opus | 5.0x | Architecture, disambiguation, tiebreaking | 3 |
| **Scout** | Haiku | 0.2x | Exploration with broad tool access | 8 |
| **Queen** | Opus | 3.0x | Spawner, not commander — responds to demand | 1 |

The Queen does not assign tasks. She spawns agents in response to demand signals from the Caste Registry — mirroring how biological queens lay eggs in response to pheromone signals.

## Nine Emergent Laws

1. No agent knows the global plan
2. The network is smarter than any node
3. Artifacts are communication (stigmergy)
4. Failure is information, not error
5. Leadership is contextual, not hierarchical
6. Diversity enables resilience
7. Local rules produce global order
8. Reserve is strategy, not waste
9. The organism adapts; no agent decides to adapt

## Five-Phase Lifecycle

```
Exploration → Decision → Execution → Validation → Delivery
  (Scouts)    (Waggle)   (Workers)    (Major)     (Queen)
```

Different castes lead in different phases. No single agent type dominates.

## Quickstart

```python
import asyncio
from symbiont import Symbiont
from symbiont.backends import EchoBackend

async def main():
    organism = Symbiont()
    organism.set_llm_backend(EchoBackend())  # No API key needed
    await organism.boot()

    result = await organism.execute(
        task="Implement user authentication",
        context={"language": "python"},
    )
    print(result)

    await organism.shutdown()

asyncio.run(main())
```

## Installation

```bash
pip install -e .

# With LLM support (Anthropic):
pip install -e ".[llm]"

# For development:
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v
```

## Project Structure

```
symbiont/
├── __init__.py          # Exports Symbiont
├── organism.py          # Main integration — the Bauplan (body plan)
├── types.py             # Enums + dataclasses (Caste, Phase, Signal, etc.)
├── config.py            # Configuration for all 8 systems
├── backends.py          # EchoBackend (test) + AnthropicBackend (production)
├── core/
│   ├── mycelium.py      # System 1: Message routing
│   ├── topology.py      # System 2: Path optimization
│   ├── castes.py        # System 3: Population management
│   ├── waggle.py        # System 4: Decision protocol
│   ├── mound.py         # System 5: Artifact storage + homeostasis
│   ├── murmuration.py   # System 6: Neighbor coordination
│   ├── governance.py    # System 7: Leadership + suppression
│   └── pod.py           # System 8: Coalition formation
├── agents/
│   ├── base.py          # Base agent
│   ├── queen.py         # QUEEN caste
│   ├── major.py         # MAJOR caste
│   ├── scout.py         # SCOUT caste
│   ├── worker.py        # MEDIA caste
│   └── minima.py        # MINIMA caste
tests/
│   └── test_organism.py # 40+ tests across all 8 systems + integration
examples/
    └── demo.py          # Full lifecycle demo with EchoBackend
```

## Dynamic Quorum

Decision quality scales with risk:

| Risk Level | Quorum | Example |
|------------|--------|---------|
| LOW | 2 scouts | Fix typo in readme |
| MEDIUM | 4 scouts | Refactor auth module |
| HIGH | 6 scouts | Change database schema |
| CRITICAL | 8 scouts + human | Deploy migration to production |

## Key Differentiators

- **Multi-pattern**: Integrates 8 biological systems (vs single-pattern ACO/PSO/ABC)
- **LLM-native**: Applies swarm intelligence to natural language reasoning, not scalar optimization
- **Cost-aware**: Caste system creates natural cost-performance gradient
- **Self-organizing**: No central planner — coordination emerges from local interactions
- **Composable**: Systems address orthogonal coordination problems and don't interfere

## Research

SYMBIONT is described in:

> R. A. Gomes, "SYMBIONT: Unifying Eight Biological Swarm Patterns for LLM Agent Coordination," submitted to ANTS 2026 (15th International Conference on Swarm Intelligence), Darmstadt, Germany.

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Author

Renato Aparecido Gomes — Independent Researcher, S\~ao Paulo, Brazil
