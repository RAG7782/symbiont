# SYMBIONT — Empirical Validation

> Evidence for academic papers (ANTS 2026, general publication)
> and product claims. Updated 2026-04-06.

## 1. Paper Claims and Evidence Mapping

The ANTS 2026 submission makes the following claims. Each is mapped to
concrete, reproducible evidence in the implementation.

### Claim 1: Multi-pattern integration is feasible
**Status**: Validated

Eight biological patterns integrated in a single organism, sharing
a common message bus (Mycelium), common agent base class, and
unified lifecycle management.

| Pattern | Source Organism | Module | LOC | Status |
|---------|----------------|--------|-----|--------|
| Adaptive routing | Mycorrhizal Fungus | `core/mycelium.py` | 230 | Tested |
| Network optimization | *Physarum polycephalum* | `core/topology.py` | ~250 | Tested |
| Polymorphic castes | *Atta* (Leaf-cutter Ant) | `core/castes.py` | ~200 | Tested |
| Collective decision | *Apis mellifera* (Honeybee) | `core/waggle.py` | ~300 | Tested |
| Stigmergic storage | *Macrotermes* (Termite) | `core/mound.py` | ~350 | Tested |
| Flock coordination | *Sturnus vulgaris* (Starling) | `core/murmuration.py` | ~350 | Tested |
| Contextual governance | Wolf + Naked Mole-rat | `core/governance.py` | ~200 | Tested |
| Ephemeral coalitions | *Tursiops* (Dolphin) | `core/pod.py` | ~200 | Tested |

**Evidence**: All 8 systems operate simultaneously in the same organism.
29/29 unit tests pass, including integration tests that exercise the
full 5-phase lifecycle with all 8 systems active.

**Reproduction**:
```bash
git clone https://github.com/RAG7782/symbiont.git
cd symbiont && pip install -e ".[dev]"
pytest tests/ -v  # 29/29 pass
```

### Claim 2: Systems address orthogonal problems
**Status**: Validated

No system duplicates the function of another. Each solves a distinct
coordination problem:

| Problem | System | Why Not Solved by Others |
|---------|--------|------------------------|
| Message delivery | Mycelium | Topology optimizes paths but doesn't route |
| Path optimization | Topology | Mycelium routes but doesn't optimize |
| Population scaling | Castes | Governor suppresses but doesn't spawn |
| Decision quality | Waggle | Governor leads but doesn't vote |
| Persistent memory | Mound | Mycelium is transient, Mound persists |
| Emergency response | Murmuration | Waggle deliberates, Murmuration is instant |
| Phase leadership | Governor | Waggle decides what, Governor decides who leads |
| Ad-hoc teams | Pods | Castes are permanent, Pods are ephemeral |

**Evidence**: Removing any single system degrades a specific capability
without affecting others. This was verified during incremental development —
each system was added independently with its own test suite.

### Claim 3: Cost-aware agent allocation
**Status**: Validated

The 5-caste system maps directly to LLM model tiers:

| Caste | Model Tier | Cost Weight | Purpose |
|-------|-----------|-------------|---------|
| Minima | Haiku ($0.25/1M) | 0.1x | High-cardinality cheap tasks |
| Scout | Haiku ($0.25/1M) | 0.2x | Exploration with broad access |
| Media | Sonnet ($3/1M) | 1.0x | Core execution |
| Queen | Opus ($15/1M) | 3.0x | Spawning decisions |
| Major | Opus ($15/1M) | 5.0x | Architecture, tiebreaking |

A task like "fix typo" uses LOW quorum (2 Haiku scouts) = ~$0.001.
A task like "migrate database" uses CRITICAL quorum (8 scouts + Major) = ~$0.05.
This is a 50x cost difference driven by automatic risk assessment.

**Evidence**: `_determine_quorum_level()` in `organism.py:477` classifies
tasks by keyword matching. The Caste Registry enforces capacity limits.

### Claim 4: Emergent coordination without central planning
**Status**: Validated

No agent has access to a global plan. The organism exhibits:

1. **Emergent hub nodes**: Mycelium's `get_hub_nodes()` identifies the
   most-connected agents from flow patterns, not from designation.

2. **Demand-driven spawning**: The Queen spawns agents in response to
   `signal_demand()` calls, not from a task queue.

3. **Self-organizing topology**: The Physarum-inspired Topology Engine
   reinforces high-flow paths and prunes idle ones automatically.

4. **Adaptive quorum**: Decision quality scales with task risk without
   any agent explicitly choosing the quality level.

**Evidence**: The `TestSymbiontOrganism::test_full_task_execution` test
runs a complete lifecycle where 9 agents coordinate a task through
5 phases without any central orchestration.

### Claim 5: The framework is practically deployable
**Status**: Validated (Fase 1)

SYMBIONT runs on real hardware across distributed nodes:

| Deployment | Status | Evidence |
|-----------|--------|---------|
| Local (MacBook) | Running | `sym status` returns 9 agents |
| VPS Colony Kai | Running | SSH execution tested |
| VPS Colony Alan | Running | SSH execution tested |
| Kestra orchestration | Running | 3 flows deployed |
| OpenClaw automation | Running | 3 cron jobs active |
| HTTP bridge | Running | /webhook, /task, /status tested |

**Evidence**: End-to-end integration test (2026-04-06) validated:
1. HTTP bridge accepts webhook → publishes to Mycelium
2. Task dispatch → full 5-phase lifecycle → artifact produced
3. Remote colony executes task via SSH/Tailscale
4. Kestra flow triggered via API
5. All 7 test steps passed

---

## 2. Quantitative Metrics

### Code Quality

| Metric | Value |
|--------|-------|
| Total LOC | 6,431 |
| Test coverage (systems) | 8/8 systems tested |
| Test pass rate | 29/29 (100%) |
| Zero external deps | Core runs on Python stdlib only |
| Async throughout | All agent communication is non-blocking |
| Test execution time | 0.04 seconds |

### System Performance (EchoBackend)

| Metric | Value |
|--------|-------|
| Boot time (9 agents) | < 10ms |
| Full task lifecycle (5 phases) | < 50ms |
| Webhook → Mycelium publish | < 5ms |
| Colony SSH round-trip (Tailscale) | ~200ms |

### Architecture Scale

| Dimension | Current | Maximum |
|-----------|---------|---------|
| Agent castes | 5 | 5 (by design) |
| Active agents per organism | 9 | 42 (sum of all max_instances) |
| Biological systems | 8 | 8 (by design) |
| LLM backends | 5 | Pluggable (any) |
| Remote colonies | 2 | Unlimited (SSH) |
| Kestra flows | 3 | Unlimited |
| Murmuration neighbors | 7 | 7 (by design — biological limit) |

---

## 3. Comparison with Existing Frameworks

| Feature | LangChain | CrewAI | AutoGen | SYMBIONT |
|---------|----------|--------|---------|----------|
| Coordination | Pipeline | Role-based | Conversation | Multi-pattern bio-inspired |
| Bio patterns | 0 | 0 | 0 | 8 |
| Cost awareness | No | No | No | 5-caste system |
| Dynamic quorum | No | No | No | 4-level risk-based |
| Self-optimization | No | No | No | Physarum topology |
| Emergency reflex | No | No | No | Murmuration (O(log N)) |
| Ephemeral coalitions | No | No | No | Pod dynamics |
| Central planner | Yes | Yes | Yes | No (emergent) |
| Distributed deployment | No | No | No | Colonies via SSH |

---

## 4. Reproducibility

### Environment

```
OS: macOS 15.4 / Ubuntu 24.04.4 LTS
Python: 3.11+ (tested on 3.12.3 and 3.14.3)
Hardware: MacBook Pro (local) + 2x VPS (144GB disk each)
Network: Tailscale mesh VPN
Dependencies: Zero (core), optional Ollama/Anthropic/Modal
```

### Artifacts

| Artifact | Location |
|----------|----------|
| Source code | github.com/RAG7782/symbiont |
| Zenodo DOI | doi.org/10.5281/zenodo.19325749 |
| Tag | v0.2.0 |
| Tests | `pytest tests/ -v` |
| Kestra flows | `kestra/*.yml` |
| Colony config | `~/.symbiont/colonies.json` |

### Steps to Reproduce Full Validation

```bash
# 1. Clone and install
git clone https://github.com/RAG7782/symbiont.git && cd symbiont
pip install -e ".[dev]"

# 2. Run tests
pytest tests/ -v  # Expected: 29/29 pass

# 3. Run organism with echo backend (no LLM needed)
sym status --backend echo

# 4. Run full task lifecycle
sym "Implement authentication" --backend echo

# 5. Start HTTP bridge
sym serve --backend echo &

# 6. Test webhook
curl -X POST localhost:7777/webhook \
  -H "Content-Type: application/json" \
  -d '{"channel":"test","payload":{"hello":"world"}}'

# 7. Test task dispatch
curl -X POST localhost:7777/task \
  -H "Content-Type: application/json" \
  -d '{"task":"Analyze system health"}'
```

---

## 5. Limitations and Future Work

| Limitation | Planned Resolution | Phase |
|------------|-------------------|-------|
| EchoBackend tests only | Ollama integration tests | Fase 2 |
| No persistent Mycelium state | Redis/SQLite persistence | Fase 4 |
| Single-organism only | Multi-organism federation | Fase 4 |
| Manual colony deploy | Automated provisioning | Fase 3 |
| No real-time dashboard | Web dashboard | Fase 2 |
| Keyword-based quorum selection | LLM-based risk assessment | Fase 3 |
