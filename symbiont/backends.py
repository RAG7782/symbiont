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

    async def complete(self, prompt: str, context: dict, model_tier: str = "sonnet") -> str:
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

    async def complete(self, prompt: str, context: dict, model_tier: str = "sonnet") -> str:
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
