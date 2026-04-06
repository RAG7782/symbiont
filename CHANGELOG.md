# Changelog

All notable changes to SYMBIONT are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

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
