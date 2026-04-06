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

## Distributed Architecture

SYMBIONT is not limited to a single machine. It can operate as a distributed organism across multiple nodes.

```
┌─────────────────────────────────────────────────────────┐
│                    SYMBIONT Organism                      │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐  │
│  │ Mycelium│──│ Waggle   │──│ Governor │──│ Mound   │  │
│  │ (msgs)  │  │ (decide) │  │ (phases) │  │ (store) │  │
│  └────┬────┘  └──────────┘  └──────────┘  └─────────┘  │
│       │                                                  │
│  ┌────┴──────────────────────────────────────────────┐  │
│  │              HTTP Bridge (port 7777)               │  │
│  │  POST /webhook  POST /task  GET /status            │  │
│  └──────────┬────────────────────┬───────────────────┘  │
└─────────────┼────────────────────┼───────────────────────┘
              │                    │
    ┌─────────┴───────┐  ┌────────┴────────┐
    │  Kestra (flows)  │  │  VPS Colonies   │
    │  - health 15m    │  │  - Kai (SSH)    │
    │  - dream  6h     │  │  - Alan (SSH)   │
    │  - dispatch      │  │  via Tailscale  │
    └─────────────────┘  └─────────────────┘
```

### HTTP Bridge (`sym serve`)

Exposes the Mycelium to external systems via HTTP:

```bash
sym serve --backend ollama --port 7777
```

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/webhook` | POST | Publish event to a Mycelium channel |
| `/task` | POST | Execute a full task through the organism |
| `/status` | GET | Organism health dashboard |
| `/channels` | GET | Active Mycelium channels |
| `/health` | GET | Liveness probe |

### Remote Colonies (`sym colony`)

Deploy and manage SYMBIONT instances on remote VPS nodes via SSH over Tailscale:

```bash
sym colony list                    # Show known colonies
sym colony status                  # Ping all colonies
sym colony deploy kai              # Deploy SYMBIONT to a colony
sym colony run kai "Analyze logs"  # Execute task remotely
sym colony heartbeat               # Quick health check
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
pytest tests/ -v   # 91 tests across all modules
```

## Project Structure

```
symbiont/
├── organism.py          # Main integration — the Bauplan (body plan)
├── types.py             # Enums + dataclasses (Caste, Phase, Signal, etc.)
├── config.py            # Configuration for all 8 systems
├── backends.py          # 4 backends: Echo, Ollama, OpenRouter, Anthropic
├── cli.py               # CLI: sym <task>, sym serve, sym colony, sym status
├── serve.py             # HTTP bridge — connects Mycelium to external systems
├── colony.py            # Remote colony management via SSH/Tailscale
├── memory.py            # IMI cognitive memory integration
├── voice.py             # Voice input/output (Whisper STT)
├── gpu_router.py        # GPU cloud provider routing
├── finetune.py          # Fine-tune pipeline (Unsloth → Modal → GGUF → Ollama)
├── modal_backend.py     # Modal.com GPU backend
├── handoffs.py          # Handoff Matrix — inter-caste task routing rules
├── tools.py             # ToolRegistry — CLI Anything + system tools
├── core/
│   ├── mycelium.py      # System 1: Adaptive message routing
│   ├── topology.py      # System 2: Path optimization (Physarum)
│   ├── castes.py        # System 3: Population management (Atta)
│   ├── waggle.py        # System 4: Collective decision (Apis)
│   ├── mound.py         # System 5: Artifact storage + homeostasis (Macrotermes)
│   ├── murmuration.py   # System 6: Real-time reflexes (Sturnus)
│   ├── governance.py    # System 7: Leadership + suppression (Wolf/Mole-rat)
│   └── pod.py           # System 8: Coalition formation (Tursiops)
├── agents/
│   ├── base.py          # Base agent with LLM integration
│   ├── queen.py         # QUEEN — spawner caste
│   ├── major.py         # MAJOR — specialist caste
│   ├── scout.py         # SCOUT — explorer caste
│   ├── worker.py        # MEDIA — execution caste
│   └── minima.py        # MINIMA — lightweight caste
kestra/                  # Workflow orchestration flows
│   ├── health-check.yml       # Periodic health monitoring
│   ├── memory-consolidation.yml  # IMI dream cycle
│   └── task-dispatch.yml      # Webhook-triggered task execution
tests/
│   └── test_organism.py # 29 tests across all 8 systems + integration
docs/
│   ├── ARCHITECTURE.md  # Full technical architecture reference
│   ├── VALIDATION.md    # Empirical evidence and benchmarks
│   ├── PRODUTO.md       # Commercial product documentation
│   └── INSTALACAO.md    # Installation guide
```

## Metrics

| Metric | Value |
|--------|-------|
| Python modules | 48 |
| Lines of code | 9,316 |
| Tests | 91/91 passing |
| Biological systems | 8 |
| Agent castes | 5 |
| LLM backends | 4 (Echo, Ollama, OpenRouter, Anthropic) |
| CLI commands | 12+ |
| Kestra flows | 3 |
| Remote colonies | 2 (expandable) |

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
