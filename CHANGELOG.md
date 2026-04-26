# Changelog

All notable changes to SYMBIONT are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## 2026-04-25 — Ollama Model Expansion

- Added 7 new models: gemma4:latest (8B), qwen3.5:9b, qwen3.5:4b, deepseek-coder:6.7b, nemotron-mini:4b, phi4-mini, llama3.1:8b
- Added oxe-juris-base Modelfile (llama:8b with legal system prompt)
- New tiers in OllamaBackend: coding, juris, light
- LIGHT_MODEL changed to phi4-mini (2.5 GB vs 5.2 GB)

## [0.4.1] — 2026-04-16

### Security
- **Sandbox path confinement** (`sandbox.py`): all `_resolve()` calls now
  canonicalize via `.resolve()` and assert the result is `relative_to(host_base)`.
  Path traversal attacks (e.g. `/mnt/workspace/../../etc/passwd`) raise
  `PermissionError` instead of silently escaping the mount.
- **CWD pinned to workspace**: `execute_stream()` sets `cwd=workspace` so
  relative paths in shell commands are confined to the sandbox.

### Added
- **execute_stream()** (`sandbox.py`): async generator that yields output
  lines in real time as the subprocess produces them. Enables Workers to
  observe long-running commands (builds, tests, ingest) without blocking.
  `execute()` is now implemented on top of `execute_stream()`.
- **DockerSandbox** (`sandbox.py`): Sandbox ABC implementation backed by
  Docker `--rm` containers with `--memory=512m --cpus=1 --network=none`.
  `SandboxProvider(backend="docker")` selects it; no interface changes needed.
- **ResearchSquad: parallel wave execution** (`research_squad.py`):
  `_build_waves()` performs topological sort on `TodoItem.depends_on` to
  produce execution waves; independent todos in the same wave run via
  `asyncio.gather`, delivering up to N× speedup.
- **ResearchSquad: exponential-backoff retry** (`research_squad.py`):
  `_llm_call_with_retry()` retries up to `llm_max_retries` times (default 3)
  with backoff 1s→2s→4s. Transient LLM failures no longer crash pipelines.
- **ResearchSquad: SQLite checkpointing** (`research_squad.py`):
  when `persistence=PersistenceStore()` is provided, completed todos are
  written to the KV store under `rsquad:<run_id>:<task_id>`. Resuming with
  the same `run_id` skips already-done todos and restores the plan.
- **TodoItem.depends_on** (`research_squad.py`): explicit DAG edges parsed
  from planner output (`[depends: TASK-N]` annotation).
- **MCPRegistry: background config watcher** (`mcp_registry.py`):
  `await registry.start_watcher()` spawns an asyncio task that polls
  `mtime` every 60 s and reloads servers proactively. `stop_watcher()` for
  clean shutdown.
- **MCPRegistry: parallel server discovery** (`mcp_registry.py`):
  `asyncio.gather` probes all enabled servers concurrently; per-server
  errors are isolated and logged without blocking other discoveries.
- **MCPRegistry: 12-factor env var** (`mcp_registry.py`):
  `MCP_SERVERS_JSON` env var overrides the default config path at startup,
  enabling container/12-factor deployments without code changes.

## [0.4.0] — 2026-04-16

### Added
- **Sandbox** (`sandbox.py`): isolated code execution for agents (DeerFlow pattern)
  - `LocalSandbox`: virtual `/mnt/*` path mapping, host-path masking in output
  - Read-only mount enforcement, per-thread workspace isolation
  - `SandboxProvider` singleton with `acquire/release` lifecycle
  - Interface: `execute`, `read_file`, `write_file`, `list_dir`, `glob`, `grep`
- **MCP Registry** (`mcp_registry.py`): dynamic MCP server discovery with OAuth
  - Supports `stdio`, `sse`, `http` transports
  - OAuth2 `client_credentials` + `refresh_token` with proactive refresh (1h skew)
  - Config file staleness detection (mtime-based auto-reload)
  - `MCPRegistry` singleton with `get_tools()`, `reload()`, `summary()`
- **Research Squad** (`research_squad.py`): Planner→Researcher→Coder pipeline
  - `ResearchSquad`: Major (plan) → Scout (research) → Worker (code) sequencing
  - Loop detection via content fingerprinting (aborts after 3 identical outputs)
  - Sandbox auto-execution of `\`\`\`bash` blocks in LLM output
  - MCP tool awareness injected into researcher prompt
  - `PipelineResult`: artifacts, todos, elapsed_sec, loop_detected

## [0.3.0] — 2026-04-06

### Added
- **Persistence** (`persistence.py`): SQLite-backed state with WAL mode
  - Channel stats, hub scores, message log, squads, federation, KV store
  - Auto-snapshot on shutdown, cross-thread safe
- **Federation** (`federation.py`): multi-organism communication protocol
  - Peer registration, heartbeat (60s), message relay, load-based task routing
  - HTTP endpoints: `/federation/heartbeat`, `/federation/register`
- **Squads** (`squads.py`): project-based agent grouping
  - Create, assign, unassign, auto-assign by caste, delete
  - CLI: `sym squad [list|create|delete|auto]`
  - Persistent via SQLite
- **HTTP Bridge** (`serve.py`): connects Mycelium to external systems
  - Endpoints: `/webhook`, `/task`, `/status`, `/channels`, `/health`
  - Dashboard web UI at `/` (dark theme, auto-refresh 5s)
  - Alerts endpoint at `/alerts`, metrics at `/metrics`
  - Federation endpoints for peer communication
- **Alerts** (`alerts.py`): Telegram + webhook notifications
  - Colony/bridge health monitoring with recovery detection
  - Consecutive failure thresholds, anti-spam
- **Dashboard** (`dashboard.py`): single-page web UI
  - Shows agents, castes, channels, hubs, colonies, health, alerts
  - Auto-refresh every 5 seconds via JavaScript polling
- **Colonies** (`colony.py`): remote execution via SSH over Tailscale
  - Deploy, status, heartbeat, run tasks on remote VPS
  - CLI: `sym colony [list|status|deploy|run|heartbeat]`
- **Datasets** (`datasets.py`): fine-tune dataset generators
  - Presets: `legal-br` (11 examples), `coding-python` (5), `general` (2)
  - Alpaca JSONL format with system prompts
  - CLI: `sym finetune [list|prepare|validate|run]`
- **Kestra Flows**: 4 workflow orchestration flows
  - `health_check` (cron */15 min), `memory_consolidation` (cron */6h)
  - `task_dispatch` (webhook), `alert_check` (cron */5 min)
- **Documentation**
  - `ARCHITECTURE.md`: full technical reference
  - `VALIDATION.md`: empirical evidence for academic papers
  - `SOCIAL-CONTENT.md`: marketing pack (LinkedIn, Twitter, blog)
  - `CONSULTORIA.md`: 3 service tiers (R$2K/R$5K/R$15K)
  - `docs/curso/`: "IA para Advogados" course (5 modules, 20 lessons)
  - `docs/landing/`: self-contained landing page
- **Tests**: 62 new tests (91 total, all passing)

### Changed
- `cli.py`: added `serve`, `colony`, `squad`, `federation`, `finetune` subcommands
- `serve.py`: integrated alerts loop, federation loop, persistence snapshot
- README: updated with distributed architecture, project structure, metrics

## [0.2.0] — 2026-04-05

### Added
- **Multimodal**: image analysis via llama3.2-vision, voice via Whisper
- **Multi-backend**: OllamaBackend, OpenRouterBackend, AnthropicBackend, ModalBackend
- **IMI Memory** (`memory.py`): cognitive memory integration (encode, navigate, dream)
- **Voice** (`voice.py`): Whisper STT for voice commands
- **GPU Router** (`gpu_router.py`): routes to cheapest GPU provider
- **Fine-Tune Pipeline** (`finetune.py`): Unsloth on Modal → GGUF → Ollama
- **Handoff Matrix** (`handoffs.py`): inter-caste task routing rules
- **Tool Registry** (`tools.py`): CLI Anything + 9 system tools
- CLI `sym` with 12+ commands
- 29 tests (all passing)

## [0.1.0] — 2026-04-04

### Added
- Initial release: 8 biological systems integrated
- Core: Mycelium, TopologyEngine, CasteRegistry, WaggleProtocol, Mound, MurmurationBus, Governor, PodDynamics
- 5 agent castes: Minima, Media, Major, Scout, Queen
- EchoBackend for testing without LLM
- 5-phase lifecycle: Exploration → Decision → Execution → Validation → Delivery
- 9 emergent laws
- Dynamic quorum (4 levels)
- Apache 2.0 license
