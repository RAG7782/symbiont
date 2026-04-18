"""SYMBIONT — Symbiotic Multi-pattern Bio-intelligent Organism for Networked Tasks."""

from symbiont.organism import Symbiont
from symbiont.backends import EchoBackend, OllamaBackend
from symbiont.memory import IMIMemory
from symbiont.voice import Voice
from symbiont.modal_backend import ModalBackend
from symbiont.gpu_router import GPURouter
from symbiont.finetune import FineTunePipeline
from symbiont.handoffs import HANDOFF_MATRIX, can_handoff, can_escalate
from symbiont.tools import ToolRegistry
from symbiont.sandbox import SandboxProvider, SandboxConfig, get_sandbox_provider
from symbiont.mcp_registry import MCPRegistry, MCPServerConfig, get_mcp_registry
from symbiont.research_squad import ResearchSquad, PipelineResult
from symbiont.oxe_bridge import OXEBridge, PremiumResult, create_premium_router
from symbiont.federation import Federation, HEARTBEAT_INTERVAL, PEER_TIMEOUT
from symbiont.persistence import PersistenceStore, DEFAULT_DB_PATH
from symbiont.translation import TranslationLayer, TRANSLATION_WAVES
from symbiont.legal_assembly import LegalAssembly, AssemblyResult, RateLimitTracker

__version__ = "0.5.0"
__all__ = [
    # Core
    "Symbiont",
    # Backends
    "EchoBackend", "OllamaBackend", "ModalBackend",
    # Memory & Voice
    "IMIMemory", "Voice",
    # Infrastructure
    "GPURouter", "FineTunePipeline",
    # Handoffs
    "HANDOFF_MATRIX", "can_handoff", "can_escalate",
    # Tools
    "ToolRegistry",
    # DeerFlow-extracted patterns
    "SandboxProvider", "SandboxConfig", "get_sandbox_provider",
    "MCPRegistry", "MCPServerConfig", "get_mcp_registry",
    "ResearchSquad", "PipelineResult",
    # OXÉ integration
    "OXEBridge", "PremiumResult", "create_premium_router",
    # Federation
    "Federation", "HEARTBEAT_INTERVAL", "PEER_TIMEOUT",
    # Persistence
    "PersistenceStore", "DEFAULT_DB_PATH",
    # Multi-model ensemble (v0.5.0)
    "TranslationLayer", "TRANSLATION_WAVES",
    "LegalAssembly", "AssemblyResult", "RateLimitTracker",
]
