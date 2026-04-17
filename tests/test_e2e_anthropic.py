"""
E2E tests with AnthropicBackend (real API).

Skipped automatically if ANTHROPIC_API_KEY is not set.
Run explicitly: uv run pytest tests/test_e2e_anthropic.py -v -s
"""

from __future__ import annotations

import os
import pytest

_SKIP = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skipping E2E tests",
)


@pytest.fixture
def anthropic_backend():
    pytest.importorskip("anthropic", reason="anthropic package not installed")
    from symbiont.backends import AnthropicBackend
    return AnthropicBackend()


@pytest.fixture
def llm_callable(anthropic_backend):
    """Wrap AnthropicBackend.complete() as a simple async callable for ResearchSquad."""
    async def _llm(prompt: str) -> str:
        return await anthropic_backend.complete(prompt, context={}, model_tier="haiku")
    return _llm


class TestAnthropicBackendDirect:
    @_SKIP
    @pytest.mark.asyncio
    async def test_complete_returns_string(self, anthropic_backend):
        result = await anthropic_backend.complete(
            "Reply with exactly: PONG",
            context={},
            model_tier="haiku",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @_SKIP
    @pytest.mark.asyncio
    async def test_model_tier_haiku(self, anthropic_backend):
        result = await anthropic_backend.complete(
            "What is 2+2? Reply with just the number.",
            context={},
            model_tier="haiku",
        )
        assert "4" in result

    @_SKIP
    @pytest.mark.asyncio
    async def test_context_injected_in_system_prompt(self, anthropic_backend):
        result = await anthropic_backend.complete(
            "What project are you working on?",
            context={"project": "SYMBIONT-E2E-TEST"},
            model_tier="haiku",
        )
        assert isinstance(result, str)
        assert len(result) > 0


class TestResearchSquadWithAnthropic:
    @_SKIP
    @pytest.mark.asyncio
    async def test_research_pipeline_completes(self, llm_callable):
        from symbiont.research_squad import ResearchSquad
        squad = ResearchSquad(llm_backend=llm_callable)
        result = await squad.run("List 2 benefits of multi-agent systems")
        assert result is not None
        assert hasattr(result, "success")
        assert hasattr(result, "todos")
        assert hasattr(result, "elapsed_sec")
        assert result.elapsed_sec > 0

    @_SKIP
    @pytest.mark.asyncio
    async def test_pipeline_result_has_plan_artifact(self, llm_callable):
        from symbiont.research_squad import ResearchSquad
        squad = ResearchSquad(llm_backend=llm_callable)
        result = await squad.run("Explain what a neural network is")
        plan_arts = [a for a in result.artifacts if a.stage == "plan"]
        assert len(plan_arts) == 1

    @_SKIP
    @pytest.mark.asyncio
    async def test_organism_research_integration(self):
        """Full integration: Symbiont.boot() → organism.research() with real LLM."""
        pytest.importorskip("anthropic", reason="anthropic package not installed")
        from symbiont import Symbiont
        from symbiont.backends import AnthropicBackend

        sym = Symbiont(backend=AnthropicBackend(), num_agents=2)
        await sym.boot()
        try:
            result = await sym.research(
                "What are 2 key properties of swarm intelligence?",
                use_sandbox=False,
            )
            assert result is not None
            assert hasattr(result, "todos")
        finally:
            await sym.shutdown()
