"""SYMBIONT — Symbiotic Multi-pattern Bio-intelligent Organism for Networked Tasks."""

from symbiont.organism import Symbiont
from symbiont.backends import EchoBackend, OllamaBackend
from symbiont.memory import IMIMemory
from symbiont.voice import Voice
from symbiont.modal_backend import ModalBackend
from symbiont.gpu_router import GPURouter
from symbiont.finetune import FineTunePipeline
from symbiont.handoffs import HANDOFF_MATRIX, can_handoff, can_escalate

__version__ = "0.2.0"
__all__ = [
    "Symbiont", "EchoBackend", "OllamaBackend", "ModalBackend",
    "IMIMemory", "Voice", "GPURouter", "FineTunePipeline",
    "HANDOFF_MATRIX", "can_handoff", "can_escalate",
]
