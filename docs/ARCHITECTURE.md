# SYMBIONT Architecture Reference

> Version 0.2.0 | Updated 2026-04-06 (Fase 1 Complete)

## 1. Design Philosophy

SYMBIONT is a **multi-pattern bio-inspired coordination framework** for LLM agents.
Unlike single-pattern approaches (ACO, PSO, ABC), SYMBIONT integrates eight biological
mechanisms that address orthogonal coordination problems. No agent knows the global
plan — coordination emerges from local interactions mediated by shared infrastructure.

**Core principle**: Functional inspiration, not structural replication.
Each mechanism is imported only if the computational problem it solves exists in
LLM agent orchestration.

---

## 2. System Architecture

```
                         ┌──────────────────────────┐
                         │      Human / Client       │
                         └─────────┬────────────────┘
                                   │
                         ┌─────────▼────────────────┐
                         │   HTTP Bridge (:7777)     │
                         │  /webhook /task /status   │
                         └─────────┬────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────┐
│                        SYMBIONT ORGANISM                            │
│                                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐     │
│  │ System 1 │    │ System 2 │    │ System 3 │    │ System 4 │     │
│  │ MYCELIUM │◄──►│ TOPOLOGY │    │ CASTES   │    │ WAGGLE   │     │
│  │ (msgs)   │    │ (paths)  │    │ (pop)    │    │ (decide) │     │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘     │
│                                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐     │
│  │ System 5 │    │ System 6 │    │ System 7 │    │ System 8 │     │
│  │ MOUND    │    │ MURMUR.  │    │ GOVERNOR │    │ POD DYN. │     │
│  │ (store)  │    │ (reflex) │    │ (leader) │    │ (allied) │     │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘     │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │                     AGENT LAYER                           │      │
│  │   Queen(1)  Scout(2)  Major(1)  Worker(2)  Minima(3)    │      │
│  └──────────────────────────────────────────────────────────┘      │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │                     BACKEND LAYER                         │      │
│  │   EchoBackend | OllamaBackend | OpenRouterBackend |      │      │
│  │   AnthropicBackend | ModalBackend                        │      │
│  └──────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
           │                    │                    │
  ┌────────▼──────┐   ┌───────▼────────┐   ┌──────▼──────────┐
  │  Kestra        │   │  OpenClaw      │   │  VPS Colonies   │
  │  (3 flows)     │   │  (3 cron jobs) │   │  Kai + Alan     │
  └───────────────┘   └────────────────┘   └─────────────────┘
```

---

## 3. The Eight Systems — Detailed

### System 1: Mycelium (Mycorrhizal Fungus)
**File**: `symbiont/core/mycelium.py` (230 LOC)

The circulatory system. All inter-agent communication flows through Mycelium channels.
Channels are pub/sub topics that **adaptively thicken with use** (more traffic = higher
bandwidth weight) and **atrophy with disuse** (pruned when weight drops below 0.1).

| Feature | Implementation |
|---------|---------------|
| Publish/Subscribe | `async publish(channel, payload, sender_id)` |
| Adaptive bandwidth | `reinforce_channel()` / `attenuate_channel()` |
| Hub detection | `get_hub_nodes()` — emergent, not designated |
| Topology queries | `query_topology()` — snapshot for optimization |
| Fan-out | Parallel delivery via `asyncio.gather()` |

**Key insight**: Hub nodes emerge from communication patterns. The most-connected
agents become natural brokers without being appointed.

### System 2: Topology Engine (Physarum polycephalum)
**File**: `symbiont/core/topology.py`

Self-optimizing network topology inspired by slime mold's ability to find shortest
paths. Runs periodic optimization cycles:

1. **Explore**: Spawn probe messages on random channels (15% of resources)
2. **Reinforce**: Channels with flow score > 0.7 get thickened
3. **Prune**: Channels idle for 10+ cycles get removed

### System 3: Caste Registry (Atta — Leaf-cutter Ants)
**File**: `symbiont/core/castes.py`

5-caste polymorphism with capacity limits and demand signals:

| Caste | Model Tier | Cost | Max | Role |
|-------|-----------|------|-----|------|
| Minima | Haiku | 0.1x | 20 | Context prep, formatting |
| Media | Sonnet | 1.0x | 10 | Core execution |
| Major | Opus | 5.0x | 3 | Architecture, tiebreaking |
| Scout | Haiku | 0.2x | 8 | Exploration |
| Queen | Opus | 3.0x | 1 | Spawning (not commanding) |

The Queen responds to **demand signals** — she does not assign tasks.
`signal_demand(caste, intensity)` triggers the Queen to spawn more agents
of that caste, just as biological queens lay eggs in response to pheromones.

### System 4: Waggle Protocol (Apis mellifera — Honeybee)
**File**: `symbiont/core/waggle.py`

Collective decision-making with **dynamic quorum**:

| Risk Level | Quorum | Example |
|-----------|--------|---------|
| LOW (2) | 2 scouts | Fix typo |
| MEDIUM (4) | 4 scouts | Implement feature |
| HIGH (6) | 6 scouts | Schema migration |
| CRITICAL (8) | 8 scouts + human | Production deploy |

Scouts submit `WaggleReport` with quality, confidence, cost, evidence, and risks.
Votes are weighted by `intensity = quality * confidence`. When no quorum is reached,
a Major agent performs tiebreaking.

### System 5: Mound (Macrotermes — Termites)
**File**: `symbiont/core/mound.py`

Stigmergic storage + homeostasis feedback. Artifacts are the shared memory:

- **Artifact lifecycle**: DRAFT → IN_PROGRESS → REVIEW → CONTESTED/APPROVED → ARCHIVED
- **Knowledge base**: Cross-references between artifacts
- **Homeostasis**: Monitors latency, error rate, test coverage, context drift.
  Triggers feedback handlers when thresholds are exceeded.

### System 6: Murmuration Bus (Sturnus vulgaris — Starlings)
**File**: `symbiont/core/murmuration.py`

Real-time reflexes with O(log N) propagation. Each agent has max 7 neighbors.
Signals propagate via wave: each node forwards to neighbors it hasn't seen yet.

| Signal Type | TTL | Purpose |
|-------------|-----|---------|
| HEARTBEAT | 7 | Liveness |
| ALERT | 7 | Warning propagation |
| HALT | 7 | Emergency stop (reflex) |
| HUMAN_OVERRIDE | 7 | Enter consultive mode |

**Reflexes** bypass deliberation entirely — a HALT signal stops all busy agents
in milliseconds, before any planning or discussion.

### System 7: Governor (Wolf + Naked Mole-rat)
**File**: `symbiont/core/governance.py`

Contextual leadership: **different castes lead in different phases**.
In Exploration, Scouts lead. In Execution, Workers lead. In Validation, Majors lead.

Also implements:
- **Suppression** (Mole-rat): Can suppress overactive agents
- **Reserve pool**: Pre-hibernated agents for instant warm-start
- **Leader election**: Automatic failover if the Queen is lost

### System 8: Pod Dynamics (Tursiops — Dolphins)
**File**: `symbiont/core/pod.py`

Ephemeral coalitions that form around objectives:

| Level | Size | When |
|-------|------|------|
| Pod | 2-4 agents | Focused sub-task |
| Super-Pod | 2-3 pods | Complex feature |
| Swarm | All agents | Emergency / deadline |

Pods dissolve after the objective is met. Trust accrues between collaborators.

---

## 4. Agent Architecture

All agents extend `BaseAgent` and are wired to all 8 systems at boot:

```python
agent.wire(mycelium, mound, murmuration, governor)
```

Agents are **model-agnostic**. The `set_llm_backend()` method injects any backend
that implements `async complete(prompt, context, model_tier) -> str`.

### Five-Phase Lifecycle

```
Exploration → Decision → Execution → Validation → Delivery
  (Scouts)    (Waggle)   (Workers)    (Major)     (Queen)
```

Each phase has a leading caste. The Governor manages transitions.

---

## 5. Backend Layer

| Backend | Module | Cost | Features |
|---------|--------|------|----------|
| EchoBackend | backends.py | $0 | Testing without LLM |
| OllamaBackend | backends.py | $0 | 7 local models, model tier mapping |
| OpenRouterBackend | backends.py | $/token | 200+ cloud models |
| AnthropicBackend | backends.py | $/token | Claude family |
| ModalBackend | modal_backend.py | $/GPU-hr | GPU cloud (L4/A100) |

**OllamaBackend model mapping**:
- haiku → qwen3:8b (fast)
- sonnet → qwen3.5:27b (coding)
- opus → gemma4:26b (all-rounder)
- reason → nemotron-3-nano:30b (math, 1M context)

---

## 6. Distributed Layer (Fase 1)

### HTTP Bridge (`symbiont/serve.py`, 221 LOC)

Bridges external systems to the Mycelium via HTTP:

```
External System  →  POST /webhook  →  Mycelium.publish()  →  Agents
Kestra Flow      →  POST /task     →  Organism.execute()  →  Result
Monitoring       →  GET /status    →  Organism.status()    →  JSON
```

Uses stdlib `http.server` + `asyncio.run_coroutine_threadsafe()` for
thread-safe async integration. Zero external dependencies.

### Remote Colonies (`symbiont/colony.py`, 246 LOC)

SSH over Tailscale mesh VPN. Each colony is a full SYMBIONT instance:

| Colony | Tailscale IP | Role |
|--------|-------------|------|
| Kai | 100.73.123.8 | Worker colony |
| Alan | 100.102.158.60 | Worker colony |

Deploy via `sym colony deploy <name>` (rsync + PYTHONPATH wrapper).
Execute via `sym colony run <name> "task"`.

### Kestra Orchestration (3 flows)

| Flow | Trigger | Purpose |
|------|---------|---------|
| `health_check` | Cron */15 min | Monitors bridge liveness |
| `memory_consolidation` | Cron 0 */6 * * * | Triggers IMI dream cycle |
| `task_dispatch` | Webhook (inputs) | Executes arbitrary tasks |

### OpenClaw Cron Jobs (3 jobs)

| Job | Schedule | Event |
|-----|----------|-------|
| symbiont-health | Every 15m | `symbiont:health-check` |
| symbiont-dream | Cron 0 */6 * * * | `symbiont:memory-dream` |
| symbiont-colony-heartbeat | Every 30m | `symbiont:colony-heartbeat` |

---

## 7. Supporting Systems

| Module | LOC | Purpose |
|--------|-----|---------|
| `memory.py` | 123 | IMI cognitive memory (encode, navigate, dream) |
| `voice.py` | 166 | Whisper STT for voice commands |
| `gpu_router.py` | 221 | Routes to cheapest GPU provider |
| `finetune.py` | 361 | Unsloth → Modal → GGUF → Ollama pipeline |
| `tools.py` | 165 | CLI Anything + 9 system tools |
| `handoffs.py` | 129 | Inter-caste routing rules matrix |

---

## 8. Configuration

All 8 systems are configurable via `SymbiontConfig` dataclasses:

```python
from symbiont.config import SymbiontConfig, TopologyConfig

config = SymbiontConfig(
    topology=TopologyConfig(explore_ratio=0.20),  # 20% always exploring
)
organism = Symbiont(config=config)
```

---

## 9. Code Metrics

| Metric | Value |
|--------|-------|
| Total Python files | 31 |
| Total lines of code | 6,431 |
| Core systems | 1,881 LOC |
| Agent layer | 1,123 LOC |
| Infrastructure | 3,427 LOC |
| Tests | 29/29 (420 LOC) |
| Kestra flows | 3 (152 LOC YAML) |
| Zero external dependencies | Core runs on stdlib only |
| Async throughout | All agent communication is async |
