"""
GPU Router — unified interface to multiple GPU cloud providers.

Routes tasks to the cheapest/fastest available provider automatically.
Free tiers are prioritized before paid compute.

Providers:
- Modal:       $30/mo free, serverless, T4/L4/A100
- Kaggle:      30h/week free T4, notebooks
- Lightning:   Free GPU Studios, T4/L4
- Together AI: Free credits, pre-hosted LLMs (API)
- Colab:       Free T4 (~4h sessions)

Usage:
    from symbiont.gpu_router import GPURouter

    router = GPURouter()
    print(router.status())  # Show available providers

    # Auto-route to best free provider
    result = await router.inference("What is 2+2?", model="qwen2.5-72b")

    # Force a specific provider
    result = await router.inference("prompt", provider="together")

    # Heavy tasks
    result = await router.embeddings(texts=[...])
    result = await router.finetune(base_model="...", dataset="...")
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


class GPURouter:
    """Routes GPU tasks to the cheapest available provider."""

    def __init__(self) -> None:
        self._providers: dict[str, dict] = {}
        self._detect_providers()

    def _detect_providers(self) -> None:
        """Detect which providers are available."""

        # Modal
        try:
            import modal
            self._providers["modal"] = {
                "name": "Modal",
                "free_tier": "$30/mo",
                "gpus": ["T4", "L4", "A100"],
                "style": "serverless",
                "priority": 1,
            }
        except ImportError:
            pass

        # Together AI
        if os.environ.get("TOGETHER_API_KEY"):
            self._providers["together"] = {
                "name": "Together AI",
                "free_tier": "initial credits",
                "gpus": ["hosted"],
                "style": "api",
                "priority": 0,  # Highest priority — pre-hosted, fastest
            }

        # Lightning AI
        if os.environ.get("LIGHTNING_API_KEY"):
            self._providers["lightning"] = {
                "name": "Lightning AI",
                "free_tier": "free GPU studios",
                "gpus": ["T4", "L4"],
                "style": "serverless",
                "priority": 2,
            }

        # NVIDIA Brev (persistent GPU VMs)
        import shutil
        if shutil.which("brev"):
            self._providers["brev"] = {
                "name": "NVIDIA Brev",
                "free_tier": "promo credits",
                "gpus": ["T4", "L4", "A100", "H100"],
                "style": "persistent",
                "priority": 4,  # Use for long-running tasks
            }

        # OpenRouter (already configured)
        if os.environ.get("OPENROUTER_API_KEY"):
            self._providers["openrouter"] = {
                "name": "OpenRouter",
                "free_tier": "pay-per-token",
                "gpus": ["hosted"],
                "style": "api",
                "priority": 3,
            }

        logger.info("gpu-router: %d providers detected: %s",
                     len(self._providers), list(self._providers.keys()))

    def status(self) -> dict:
        """Show available providers and their status."""
        return {
            "providers": self._providers,
            "count": len(self._providers),
            "recommended": self._best_provider(),
        }

    def _best_provider(self, task_type: str = "inference") -> str | None:
        """Select the best provider based on priority and task type."""
        if not self._providers:
            return None

        # For API-style inference, prefer pre-hosted (Together/OpenRouter)
        if task_type == "inference":
            api_providers = {k: v for k, v in self._providers.items() if v["style"] == "api"}
            if api_providers:
                return min(api_providers, key=lambda k: api_providers[k]["priority"])

        # For compute tasks, prefer serverless (Modal)
        serverless = {k: v for k, v in self._providers.items() if v["style"] == "serverless"}
        if serverless:
            return min(serverless, key=lambda k: serverless[k]["priority"])

        # Fallback to any
        return min(self._providers, key=lambda k: self._providers[k]["priority"])

    async def inference(self, prompt: str, model: str | None = None, provider: str | None = None) -> str:
        """Run LLM inference on the best available GPU provider."""
        provider = provider or self._best_provider("inference")

        if provider == "together":
            return await self._together_inference(prompt, model)
        elif provider == "openrouter":
            return await self._openrouter_inference(prompt, model)
        elif provider == "modal":
            from symbiont.modal_backend import ModalBackend
            mb = ModalBackend()
            return await mb.complete(prompt, {})
        else:
            raise ValueError(f"No provider available. Detected: {list(self._providers.keys())}")

    async def embeddings(self, texts: list[str], model: str = "BAAI/bge-large-en-v1.5", provider: str | None = None) -> dict:
        """Generate embeddings on the best GPU provider."""
        provider = provider or self._best_provider("compute")

        if provider == "modal":
            from symbiont.modal_backend import ModalBackend
            mb = ModalBackend()
            return await mb.run_gpu_task("embeddings", texts=texts, model=model)
        else:
            raise ValueError(f"Embeddings require serverless provider. Have: {list(self._providers.keys())}")

    async def finetune(self, base_model: str, dataset: str = "", output_name: str = "symbiont-ft",
                       provider: str | None = None) -> dict:
        """Fine-tune a model on the best GPU provider."""
        provider = provider or self._best_provider("compute")

        if provider == "modal":
            from symbiont.modal_backend import ModalBackend
            mb = ModalBackend()
            return await mb.run_gpu_task("finetune", base_model=base_model, dataset=dataset, output_name=output_name)
        else:
            raise ValueError(f"Fine-tuning requires serverless provider. Have: {list(self._providers.keys())}")

    # ------------------------------------------------------------------
    # Provider-specific implementations
    # ------------------------------------------------------------------

    async def _together_inference(self, prompt: str, model: str | None = None) -> str:
        """Inference via Together AI API (OpenAI-compatible)."""
        import httpx

        model = model or "Qwen/Qwen2.5-72B-Instruct"
        api_key = os.environ["TOGETHER_API_KEY"]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.together.xyz/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2048,
                },
                timeout=120.0,
            )
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def _openrouter_inference(self, prompt: str, model: str | None = None) -> str:
        """Inference via OpenRouter API."""
        import httpx

        model = model or "qwen/qwen-2.5-72b-instruct"
        api_key = os.environ["OPENROUTER_API_KEY"]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": "https://github.com/RAG7782/symbiont",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=120.0,
            )
            data = response.json()
            return data["choices"][0]["message"]["content"]
