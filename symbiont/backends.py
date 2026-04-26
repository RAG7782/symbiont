"""
LLM Backends — pluggable model interfaces for SYMBIONT agents.

Agents are model-agnostic. The backend translates agent requests
to specific LLM API calls. This allows SYMBIONT to work with
different providers or even run in demo mode without any LLM.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class EchoBackend:
    """
    Demo backend that echoes prompts — no LLM calls.
    Useful for testing the organism's coordination without API costs.
    """

    async def complete(self, prompt: str, context: dict, model_tier: str = "sonnet", images: list | None = None) -> str:
        logger.debug("echo-backend: [%s] prompt=%s...", model_tier, prompt[:60])
        # Return a structured response that agents can parse
        return (
            f"OPTION: Approach based on analysis\n"
            f"DESCRIPTION: After analyzing the task, the recommended approach is "
            f"to proceed with a systematic implementation.\n"
            f"EVIDENCE:\n"
            f"- The task requirements are clear\n"
            f"- Existing patterns support this approach\n"
            f"RISKS:\n"
            f"- Complexity may increase over time\n"
            f"CONFIDENCE: medium confidence\n"
            f"\n[Model: {model_tier}] [Context keys: {list(context.keys())}]"
        )


class OllamaBackend:
    """
    Local backend using Ollama — zero API cost, runs on-device.

    Maps model tiers to local Ollama models (updated 2026-04-25):
    - haiku  → qwen3:8b           (fast, lightweight)
    - sonnet → qwen3.5:9b         (coding, balanced speed/quality)
    - opus   → gemma4:26b         (all-rounder, #3 open model)
    - reason → nemotron-3-nano:30b (math 82.88%, 1M context)
    - coding → deepseek-coder:6.7b (code-specialized)
    - juris  → oxe-juris-base     (fine-tuned jurídico BR)
    - light  → phi4-mini          (ultra-fast, 2.5 GB)

    New models added 2026-04-25: gemma4:latest (9.6GB), nemotron-mini:4b,
    phi4-mini, deepseek-coder:6.7b, qwen3.5:4b, qwen3.5:9b,
    oxe-juris-base (fine-tune jurídico), llama3.1:8b.

    Also supports preset aliases: coding, general, reasoning.
    """

    MODEL_MAP = {
        "haiku": "qwen3:8b",
        "sonnet": "qwen3.5:9b",
        "opus": "gemma4:26b",
        "reason": "nemotron-3-nano:30b",
        "vision": "llama3.2-vision:11b",
        "ocr": "qwen3-vl:8b",
        "coding": "deepseek-coder:6.7b",
        "juris": "oxe-juris-base:latest",
        "light": "phi4-mini:latest",
        # Preset aliases
        "general": "general",
        "reasoning": "reasoning",
    }

    # Light mode: all tiers use the same model (avoids RAM thrashing)
    LIGHT_MODEL = "phi4-mini:latest"

    def __init__(self, host: str = "http://localhost:11434", light: bool = False, memory: bool = True) -> None:
        self._light = light
        self._memory = None
        try:
            import ollama as _ollama
            self._client = _ollama.Client(host=host)
        except ImportError:
            raise ImportError(
                "ollama package required. Install with: pip install ollama"
            )

        # Initialize IMI memory if requested
        if memory:
            try:
                from symbiont.memory import IMIMemory
                self._memory = IMIMemory()
                if self._memory.available:
                    logger.info("ollama-backend: IMI memory active (%d memories)", self._memory.memory_count)
                else:
                    self._memory = None
            except Exception as e:
                logger.debug("ollama-backend: IMI not available — %s", e)

    # Vision-capable models (auto-switch when images are provided)
    # Vision-capable models (auto-switch when images are provided)
    VISION_MODELS = {"llama3.2-vision:11b", "qwen3-vl:8b"}

    async def complete(self, prompt: str, context: dict, model_tier: str = "sonnet", images: list | None = None) -> str:
        if self._light and not images:
            model = self.LIGHT_MODEL
        elif images and model_tier not in ("vision", "ocr"):
            # Auto-route to vision model when images are provided
            model = self.MODEL_MAP["vision"]
        else:
            model = self.MODEL_MAP.get(model_tier, self.MODEL_MAP["sonnet"])

        system_prompt = (
            "You are a SYMBIONT agent — part of a bio-inspired multi-agent system. "
            "Be concise, structured, and action-oriented."
        )

        if context:
            system_prompt += f"\n\nContext: {context}"

        # Recall relevant memories before LLM call
        if self._memory:
            memories = self._memory.recall(prompt, top_k=3)
            if memories:
                mem_text = "\n".join(f"- {m['content']}" for m in memories)
                system_prompt += f"\n\nRelevant memories:\n{mem_text}"

        # Build user message (with optional images)
        user_message: dict = {"role": "user", "content": prompt}
        if images:
            user_message["images"] = images

        import asyncio
        response = await asyncio.to_thread(
            self._client.chat,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                user_message,
            ],
        )
        result = response["message"]["content"]

        # Encode the interaction into memory
        if self._memory:
            img_tag = f", {len(images)} image(s)" if images else ""
            self._memory.encode(
                f"Task: {prompt[:200]}{img_tag}\nResult: {result[:300]}",
                tags=["symbiont", model_tier, model],
                source="symbiont-ollama",
            )

        return result


class OpenRouterBackend:
    """
    Cloud backend via OpenRouter — access 200+ open source models.

    Uses the same tier system but routes to cloud models.
    Good for models too large to run locally (70B+, 400B+).

    Requires OPENROUTER_API_KEY environment variable.
    """

    MODEL_MAP = {
        "haiku": "qwen/qwen-2.5-7b-instruct",
        "sonnet": "qwen/qwen-2.5-72b-instruct",
        "opus": "google/gemma-2-27b-it",
        "reason": "deepseek/deepseek-r1",
        "vision": "qwen/qwen-2.5-vl-72b-instruct",
        # Large models only available in cloud
        "frontier": "qwen/qwen-3-235b-a22b",
    }

    def __init__(self, api_key: str | None = None) -> None:
        import os
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY not set")

        try:
            import httpx
            self._client = httpx.Client(
                base_url="https://openrouter.ai/api/v1",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "HTTP-Referer": "https://github.com/RAG7782/symbiont",
                },
                timeout=120.0,
            )
        except ImportError:
            raise ImportError("httpx required. Install with: pip install httpx")

    async def complete(self, prompt: str, context: dict, model_tier: str = "sonnet", images: list | None = None) -> str:
        model = self.MODEL_MAP.get(model_tier, self.MODEL_MAP["sonnet"])

        system_prompt = (
            "You are a SYMBIONT agent — part of a bio-inspired multi-agent system. "
            "Be concise, structured, and action-oriented."
        )
        if context:
            system_prompt += f"\n\nContext: {context}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        import asyncio
        response = await asyncio.to_thread(
            self._client.post,
            "/chat/completions",
            json={"model": model, "messages": messages},
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]


class AnthropicBackend:
    """
    Production backend using the Anthropic API.

    Maps model tiers to specific Claude models:
    - haiku → claude-haiku-4-5-20251001
    - sonnet → claude-sonnet-4-6
    - opus → claude-opus-4-6
    """

    MODEL_MAP = {
        "haiku": "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-6",
        "opus": "claude-opus-4-6",
    }

    def __init__(self, api_key: str | None = None) -> None:
        try:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
        except ImportError:
            raise ImportError(
                "anthropic package required. Install with: pip install 'symbiont[llm]'"
            )

    async def complete(self, prompt: str, context: dict, model_tier: str = "sonnet", images: list | None = None) -> str:
        model = self.MODEL_MAP.get(model_tier, self.MODEL_MAP["sonnet"])

        system_prompt = (
            "You are a SYMBIONT agent — part of a bio-inspired multi-agent system. "
            "Be concise, structured, and action-oriented."
        )

        if context:
            system_prompt += f"\n\nContext: {context}"

        response = await self._client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
