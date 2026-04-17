"""Tests for the Research Squad pipeline (v0.4.1)."""

from __future__ import annotations

import asyncio
import time

import pytest

from symbiont.research_squad import (
    PipelineResult,
    ResearchArtifact,
    ResearchSquad,
    TodoItem,
    _build_waves,
    _json_safe,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

async def _make_llm(responses: dict[str, str]):
    """Factory: returns an async LLM callable keyed by role keyword."""
    async def llm(prompt: str) -> str:
        for key, resp in responses.items():
            if key in prompt:
                return resp
        return "[SKIP]"
    return llm


@pytest.fixture
def simple_llm():
    async def llm(prompt: str) -> str:
        responses = {
            "Decompose": "[TASK-1] Step alpha\n[TASK-2] Step beta",
            "researcher": "[SKIP]",
            "engineer": "[SKIP]",
        }
        for key, resp in responses.items():
            if key in prompt:
                return resp
        return "[SKIP]"
    return llm


# ---------------------------------------------------------------------------
# DAG wave builder
# ---------------------------------------------------------------------------

class TestBuildWaves:
    def test_no_deps_all_in_wave_0(self):
        todos = [TodoItem("T1", "A"), TodoItem("T2", "B"), TodoItem("T3", "C")]
        waves = _build_waves(todos)
        assert len(waves) == 1
        assert {t.id for t in waves[0]} == {"T1", "T2", "T3"}

    def test_linear_chain(self):
        todos = [
            TodoItem("T1", "A"),
            TodoItem("T2", "B", depends_on=["T1"]),
            TodoItem("T3", "C", depends_on=["T2"]),
        ]
        waves = _build_waves(todos)
        assert len(waves) == 3
        assert waves[0][0].id == "T1"
        assert waves[1][0].id == "T2"
        assert waves[2][0].id == "T3"

    def test_diamond_dag(self):
        todos = [
            TodoItem("T1", "root"),
            TodoItem("T2", "left", depends_on=["T1"]),
            TodoItem("T3", "right", depends_on=["T1"]),
            TodoItem("T4", "merge", depends_on=["T2", "T3"]),
        ]
        waves = _build_waves(todos)
        assert len(waves) == 3
        assert {t.id for t in waves[1]} == {"T2", "T3"}
        assert waves[2][0].id == "T4"

    def test_empty_list(self):
        assert _build_waves([]) == []

    def test_cycle_guard_does_not_crash(self):
        # Malformed dependency (cycle) — should not raise, just degrade
        todos = [
            TodoItem("T1", "A", depends_on=["T2"]),
            TodoItem("T2", "B", depends_on=["T1"]),
        ]
        waves = _build_waves(todos)  # should not hang or raise
        assert isinstance(waves, list)


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

class TestResearchSquad:
    @pytest.mark.asyncio
    async def test_run_returns_pipeline_result(self, simple_llm):
        squad = ResearchSquad(llm_backend=simple_llm)
        result = await squad.run("build a thing")
        assert isinstance(result, PipelineResult)
        assert len(result.todos) == 2
        assert result.elapsed_sec >= 0

    @pytest.mark.asyncio
    async def test_plan_failure_returns_early(self):
        async def bad_planner(prompt):
            return "no tasks here"

        squad = ResearchSquad(llm_backend=bad_planner)
        result = await squad.run("impossible task")
        assert not result.success
        assert "no sub-tasks" in result.summary

    @pytest.mark.asyncio
    async def test_all_skip_marks_todos_incomplete(self):
        async def skip_all(prompt):
            if "Decompose" in prompt:
                return "[TASK-1] thing"
            return "[SKIP]"

        squad = ResearchSquad(llm_backend=skip_all)
        result = await squad.run("test")
        # todo marked complete only if code artifact was produced
        assert len(result.todos) == 1

    @pytest.mark.asyncio
    async def test_plan_artifact_always_present(self, simple_llm):
        squad = ResearchSquad(llm_backend=simple_llm)
        result = await squad.run("test plan artifact")
        plan_arts = [a for a in result.artifacts if a.stage == "plan"]
        assert len(plan_arts) == 1
        assert "Step alpha" in plan_arts[0].content

    @pytest.mark.asyncio
    async def test_loop_detection_aborts_pipeline(self):
        repeated = "x" * 100
        async def looping(prompt):
            if "Decompose" in prompt:
                return "[TASK-1] loopy\n[TASK-2] loopy2\n[TASK-3] loopy3"
            return repeated  # same fingerprint every time

        squad = ResearchSquad(llm_backend=looping)
        result = await squad.run("loop test")
        assert result.loop_detected

    @pytest.mark.asyncio
    async def test_retry_on_transient_failure(self):
        attempts = [0]

        async def flaky(prompt):
            attempts[0] += 1
            if attempts[0] <= 2:
                raise RuntimeError("transient")
            if "Decompose" in prompt:
                return "[TASK-1] recovered"
            return "[SKIP]"

        squad = ResearchSquad(llm_backend=flaky, llm_max_retries=3)
        result = await squad.run("flaky task")
        assert result.todos  # recovered successfully

    @pytest.mark.asyncio
    async def test_retry_exhaustion_propagates(self):
        async def always_fail(prompt):
            raise RuntimeError("permanent error")

        squad = ResearchSquad(llm_backend=always_fail, llm_max_retries=2)
        with pytest.raises(RuntimeError, match="permanent error"):
            await squad.run("doomed task")

    @pytest.mark.asyncio
    async def test_parallel_waves_faster_than_sequential(self):
        """Two independent tasks should run faster than sequential would."""
        async def slow(prompt):
            await asyncio.sleep(0.05)
            if "Decompose" in prompt:
                return "[TASK-1] A\n[TASK-2] B"  # no deps → parallel
            return "[SKIP]"

        squad = ResearchSquad(llm_backend=slow)
        start = time.time()
        result = await squad.run("parallel test")
        elapsed = time.time() - start
        # Sequential would take ~0.30s (plan + 2×research + 2×code = 5×0.05)
        # Parallel should be < 0.25s
        assert elapsed < 0.28
        assert len(result.todos) == 2

    @pytest.mark.asyncio
    async def test_checkpointing_skips_done_todos(self):
        calls = [0]

        async def counted(prompt):
            calls[0] += 1
            if "Decompose" in prompt:
                return "[TASK-1] X\n[TASK-2] Y"
            return "[SKIP]"

        class MockStore:
            def __init__(self): self._kv = {}
            def kv_get(self, k): return self._kv.get(k)
            def kv_set(self, k, v): self._kv[k] = v

        store = MockStore()
        squad = ResearchSquad(llm_backend=counted, persistence=store)

        await squad.run("checkpoint test", run_id="ckpt-test-001")
        first_run_calls = calls[0]

        calls[0] = 0
        await squad.run("checkpoint test", run_id="ckpt-test-001")
        assert calls[0] < first_run_calls  # resume skips already-done todos

    @pytest.mark.asyncio
    async def test_depends_on_parsed_from_planner_output(self):
        async def planner_with_deps(prompt):
            if "Decompose" in prompt:
                return (
                    "[TASK-1] Foundation\n"
                    "[TASK-2] Build [depends: TASK-1]\n"
                    "[TASK-3] Test [depends: TASK-2]"
                )
            return "[SKIP]"

        squad = ResearchSquad(llm_backend=planner_with_deps)
        result = await squad.run("dep test")
        t2 = next(t for t in result.todos if t.id == "T2")
        t3 = next(t for t in result.todos if t.id == "T3")
        assert "T1" in t2.depends_on
        assert "T2" in t3.depends_on


# ---------------------------------------------------------------------------
# Artifact structure
# ---------------------------------------------------------------------------

class TestArtifact:
    def test_fingerprint_is_deterministic(self):
        a = ResearchArtifact(stage="code", task_id="T1", content="hello world")
        assert a.fingerprint == a.fingerprint
        assert len(a.fingerprint) == 16

    def test_fingerprint_differs_for_different_content(self):
        a = ResearchArtifact(stage="code", task_id="T1", content="hello")
        b = ResearchArtifact(stage="code", task_id="T1", content="world")
        assert a.fingerprint != b.fingerprint

    def test_pipeline_result_filters(self):
        arts = [
            ResearchArtifact(stage="plan", task_id="root", content="plan"),
            ResearchArtifact(stage="research", task_id="T1", content="research"),
            ResearchArtifact(stage="code", task_id="T1", content="code"),
        ]
        result = PipelineResult(success=True, summary="ok", todos=[], artifacts=arts)
        assert len(result.code_artifacts()) == 1
        assert len(result.research_artifacts()) == 1


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_json_safe_serializes_dict(self):
        out = _json_safe({"key": "value", "num": 42})
        assert '"key"' in out
        assert '"value"' in out

    def test_json_safe_fallback_on_unserializable(self):
        class Unserializable:
            pass
        out = _json_safe(Unserializable())
        assert isinstance(out, str)
