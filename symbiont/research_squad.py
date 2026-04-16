"""
SYMBIONT Research Squad — Planner→Researcher→Coder pipeline.

Coordinates three caste roles to complete complex research + implementation
tasks autonomously, with full production hardening.

Post v0.4.1 hardening:
  1. Retry with exponential backoff — transient LLM failures no longer crash
     the pipeline; each stage retries up to 3 times with 1s/2s/4s waits.
  2. Parallel todo execution — todos without declared dependencies run
     concurrently via asyncio.gather, delivering up to N× speedup.
  3. Checkpointing via PersistenceStore — completed artifacts are persisted
     to SQLite so a pipeline resumed after failure skips already-done todos.
  4. TodoItem.depends_on — explicit DAG: downstream todos wait for upstream;
     independent todos are gathered in parallel waves.

Pipeline stages:
  PLANNER  (Major caste)  — decomposes task → ordered TodoList with deps
  RESEARCHER (Scout caste) — gathers evidence per todo using sandbox + MCP
  CODER    (Worker caste) — produces executable code per todo

Loop detection: aborts if the same artifact content fingerprint appears 3×.

Usage:
    from symbiont.research_squad import ResearchSquad
    from symbiont.persistence import PersistenceStore

    store = PersistenceStore()
    squad = ResearchSquad(
        llm_backend=my_backend,
        sandbox_provider=provider,
        persistence=store,
    )
    result = await squad.run(
        "Implement JWT auth middleware for FastAPI",
        run_id="jwt-auth-v1",   # for checkpoint resume
    )
    for art in result.code_artifacts():
        print(art.content[:400])
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline data structures
# ---------------------------------------------------------------------------

@dataclass
class TodoItem:
    id: str
    description: str
    completed: bool = False
    notes: str = ""
    depends_on: list[str] = field(default_factory=list)  # DAG edges


@dataclass
class ResearchArtifact:
    stage: str          # "plan" | "research" | "code"
    task_id: str
    content: str
    kind: str = "text"  # text | code | file
    file_path: str | None = None
    created_at: float = field(default_factory=time.time)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]


@dataclass
class PipelineResult:
    success: bool
    summary: str
    todos: list[TodoItem]
    artifacts: list[ResearchArtifact]
    loop_detected: bool = False
    elapsed_sec: float = 0.0

    def code_artifacts(self) -> list[ResearchArtifact]:
        return [a for a in self.artifacts if a.stage == "code"]

    def research_artifacts(self) -> list[ResearchArtifact]:
        return [a for a in self.artifacts if a.stage == "research"]


# ---------------------------------------------------------------------------
# Research Squad
# ---------------------------------------------------------------------------

class ResearchSquad:
    """
    Orchestrates Planner→Researcher→Coder with:
      - Exponential-backoff retry on LLM failures
      - Parallel wave execution for independent todos
      - SQLite checkpointing via PersistenceStore (optional)
      - Explicit DAG via TodoItem.depends_on
    """

    MAX_TODOS = 10
    MAX_LOOP_FINGERPRINTS = 3

    def __init__(
        self,
        llm_backend: Any = None,
        sandbox_provider: Any = None,
        mcp_registry: Any = None,
        persistence: Any = None,
        max_todos: int = MAX_TODOS,
        llm_max_retries: int = 3,
    ) -> None:
        self._llm = llm_backend
        self._sandbox_provider = sandbox_provider
        self._mcp = mcp_registry
        self._store = persistence
        self._max_todos = max_todos
        self._llm_max_retries = llm_max_retries

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        task: str,
        context: dict | None = None,
        run_id: str | None = None,
    ) -> PipelineResult:
        """
        Execute full pipeline for task.

        run_id: stable identifier for checkpoint resume. If None, a hash
                of the task string is used. Pass the same run_id to resume
                a previously interrupted pipeline.
        """
        start = time.time()
        ctx = context or {}
        run_id = run_id or hashlib.sha256(task.encode()).hexdigest()[:12]
        seen_fingerprints: dict[str, int] = {}
        all_artifacts: list[ResearchArtifact] = []

        logger.info("research_squad[%s]: starting — %s", run_id, task[:80])

        # ---- Stage 1: PLAN ------------------------------------------------
        todos = await self._plan(task, ctx, run_id)
        if not todos:
            return PipelineResult(
                success=False,
                summary="Planner produced no sub-tasks.",
                todos=[],
                artifacts=[],
                elapsed_sec=time.time() - start,
            )

        all_artifacts.append(ResearchArtifact(
            stage="plan",
            task_id="root",
            content="\n".join(f"[{i+1}] {t.description}" for i, t in enumerate(todos)),
        ))
        logger.info("research_squad[%s]: plan=%d todos", run_id, len(todos))

        # ---- Stages 2+3: parallel waves via dependency DAG ---------------
        waves = _build_waves(todos)
        logger.info("research_squad[%s]: %d execution waves", run_id, len(waves))

        for wave_idx, wave in enumerate(waves):
            logger.info(
                "research_squad[%s]: wave %d/%d — %d todos",
                run_id, wave_idx + 1, len(waves), len(wave),
            )

            wave_results = await asyncio.gather(
                *[
                    self._execute_todo(
                        todo, task, all_artifacts, ctx, run_id, seen_fingerprints
                    )
                    for todo in wave
                ],
                return_exceptions=True,
            )

            for todo, result in zip(wave, wave_results):
                if isinstance(result, _LoopError):
                    return PipelineResult(
                        success=False,
                        summary=f"Loop detected: {result}",
                        todos=todos,
                        artifacts=all_artifacts,
                        loop_detected=True,
                        elapsed_sec=time.time() - start,
                    )
                if isinstance(result, Exception):
                    logger.error(
                        "research_squad[%s]: todo %s failed: %s",
                        run_id, todo.id, result,
                    )
                    # Non-loop failures: mark incomplete but continue
                else:
                    new_arts, completed = result
                    all_artifacts.extend(new_arts)
                    todo.completed = completed

        completed_count = sum(1 for t in todos if t.completed)
        return PipelineResult(
            success=completed_count == len(todos),
            summary=f"Completed {completed_count}/{len(todos)} sub-tasks.",
            todos=todos,
            artifacts=all_artifacts,
            elapsed_sec=time.time() - start,
        )

    # ------------------------------------------------------------------
    # Per-todo execution (runs in parallel within a wave)
    # ------------------------------------------------------------------

    async def _execute_todo(
        self,
        todo: TodoItem,
        root_task: str,
        shared_artifacts: list[ResearchArtifact],
        ctx: dict,
        run_id: str,
        seen_fingerprints: dict[str, int],
    ) -> tuple[list[ResearchArtifact], bool]:
        """
        Returns (new_artifacts, completed).
        Raises _LoopError on loop detection.
        """
        # Checkpoint resume: skip if already done
        if self._store and self._ckpt_get(run_id, todo.id) == "done":
            logger.info("research_squad[%s]: [%s] skipping (checkpointed)", run_id, todo.id)
            return [], True

        logger.info("research_squad[%s]: [%s] %s", run_id, todo.id, todo.description[:60])
        new_artifacts: list[ResearchArtifact] = []

        # Research stage
        research = await self._research(todo, root_task, shared_artifacts, ctx)
        if research:
            fp = research.fingerprint
            seen_fingerprints[fp] = seen_fingerprints.get(fp, 0) + 1
            if seen_fingerprints[fp] >= self.MAX_LOOP_FINGERPRINTS:
                raise _LoopError(f"research stage for todo {todo.id}")
            new_artifacts.append(research)

        # Code stage
        combined = shared_artifacts + new_artifacts
        code = await self._code(todo, research, root_task, combined, ctx)
        if code:
            fp = code.fingerprint
            seen_fingerprints[fp] = seen_fingerprints.get(fp, 0) + 1
            if seen_fingerprints[fp] >= self.MAX_LOOP_FINGERPRINTS:
                raise _LoopError(f"code stage for todo {todo.id}")
            new_artifacts.append(code)

        # Checkpoint
        if self._store:
            self._ckpt_set(run_id, todo.id, "done")

        return new_artifacts, bool(code or research)

    # ------------------------------------------------------------------
    # Stage implementations
    # ------------------------------------------------------------------

    async def _plan(self, task: str, ctx: dict, run_id: str) -> list[TodoItem]:
        # Checkpoint: reuse plan if pipeline is being resumed
        if self._store:
            cached = self._ckpt_get(run_id, "plan")
            if cached:
                try:
                    data = json.loads(cached)
                    todos = [TodoItem(**t) for t in data]
                    logger.info("research_squad[%s]: plan restored from checkpoint", run_id)
                    return todos
                except Exception:
                    pass

        prompt = self._build_plan_prompt(task, ctx)
        raw = await self._llm_call_with_retry(prompt, role="planner")
        todos = self._parse_todos(raw)

        if self._store and todos:
            self._ckpt_set(run_id, "plan", json.dumps([
                {"id": t.id, "description": t.description, "depends_on": t.depends_on}
                for t in todos
            ]))
        return todos

    async def _research(
        self,
        todo: TodoItem,
        root_task: str,
        artifacts: list[ResearchArtifact],
        ctx: dict,
    ) -> ResearchArtifact | None:
        mcp_tools: list[str] = []
        if self._mcp:
            try:
                tools = await self._mcp.get_tools()
                mcp_tools = [t.name for t in tools]
            except Exception as exc:
                logger.warning("research_squad: mcp unavailable: %s", exc)

        sandbox_context = "\n\n".join(
            f"[{a.task_id}]\n{a.content[:500]}"
            for a in artifacts[-3:]
            if a.stage in ("plan", "code")
        )

        prompt = self._build_research_prompt(todo, root_task, sandbox_context, mcp_tools)
        raw = await self._llm_call_with_retry(prompt, role="researcher")
        if not raw or raw.strip() == "[SKIP]":
            return None

        if self._sandbox_provider and "```bash" in raw:
            raw = await self._execute_sandbox_blocks(raw, todo.id)

        return ResearchArtifact(stage="research", task_id=todo.id, content=raw, kind="text")

    async def _code(
        self,
        todo: TodoItem,
        research: ResearchArtifact | None,
        root_task: str,
        artifacts: list[ResearchArtifact],
        ctx: dict,
    ) -> ResearchArtifact | None:
        research_context = research.content[:2000] if research else "(no prior research)"
        prior_code = "\n\n".join(
            f"// [{a.task_id}]\n{a.content[:600]}"
            for a in artifacts
            if a.stage == "code"
        )[-2000:]

        prompt = self._build_code_prompt(todo, root_task, research_context, prior_code)
        raw = await self._llm_call_with_retry(prompt, role="coder")
        if not raw or raw.strip() == "[SKIP]":
            return None

        if self._sandbox_provider:
            raw = await self._execute_sandbox_blocks(raw, todo.id)

        return ResearchArtifact(stage="code", task_id=todo.id, content=raw, kind="code")

    # ------------------------------------------------------------------
    # LLM call with exponential-backoff retry — increment #5
    # ------------------------------------------------------------------

    async def _llm_call_with_retry(self, prompt: str, role: str) -> str:
        """
        Call LLM backend with exponential backoff retry.

        Retries on any exception (timeout, rate-limit, transient error).
        Raises the last exception after max_retries exhausted.

        Backoff: 1s → 2s → 4s (doubles each attempt).
        """
        last_exc: Exception | None = None
        for attempt in range(self._llm_max_retries):
            try:
                return await self._dispatch_llm(prompt, role)
            except Exception as exc:
                last_exc = exc
                if attempt < self._llm_max_retries - 1:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(
                        "research_squad: LLM %s retry %d/%d after %.1fs — %s",
                        role, attempt + 1, self._llm_max_retries, wait, exc,
                    )
                    await asyncio.sleep(wait)
        raise last_exc  # type: ignore[misc]

    async def _dispatch_llm(self, prompt: str, role: str) -> str:
        if self._llm is None:
            return self._stub_response(role, prompt)
        if hasattr(self._llm, "complete"):
            return await self._llm.complete(prompt)
        if hasattr(self._llm, "chat"):
            return await self._llm.chat([{"role": "user", "content": prompt}])
        if callable(self._llm):
            result = self._llm(prompt)
            if asyncio.iscoroutine(result):
                return await result
            return result
        logger.warning("research_squad: llm_backend has no known interface")
        return self._stub_response(role, prompt)

    # ------------------------------------------------------------------
    # Sandbox: execute ```bash blocks from LLM output
    # ------------------------------------------------------------------

    async def _execute_sandbox_blocks(self, text: str, thread_id: str) -> str:
        import re
        if not self._sandbox_provider:
            return text

        sandbox_id = self._sandbox_provider.acquire(thread_id)
        sandbox = self._sandbox_provider.get(sandbox_id)
        if not sandbox:
            return text

        parts: list[str] = []
        last_end = 0
        for match in re.finditer(r"```bash\n(.*?)```", text, re.DOTALL):
            parts.append(text[last_end:match.start()])
            command = match.group(1).strip()
            try:
                output, code = await sandbox.execute(command, timeout=30)
                parts.append(
                    f"```bash\n{command}\n```\n**Output (exit {code}):**\n```\n{output}\n```"
                )
            except Exception as exc:
                parts.append(f"```bash\n{command}\n```\n**Error:** {exc}")
            last_end = match.end()
        parts.append(text[last_end:])
        return "".join(parts)

    # ------------------------------------------------------------------
    # Checkpoint helpers (thin KV over PersistenceStore)
    # ------------------------------------------------------------------

    def _ckpt_key(self, run_id: str, task_id: str) -> str:
        return f"rsquad:{run_id}:{task_id}"

    def _ckpt_get(self, run_id: str, task_id: str) -> str | None:
        try:
            return self._store.kv_get(self._ckpt_key(run_id, task_id))
        except Exception:
            return None

    def _ckpt_set(self, run_id: str, task_id: str, value: str) -> None:
        try:
            self._store.kv_set(self._ckpt_key(run_id, task_id), value)
        except Exception as exc:
            logger.warning("research_squad: checkpoint write failed: %s", exc)

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_plan_prompt(self, task: str, ctx: dict) -> str:
        ctx_str = f"\n\nContext:\n{_json_safe(ctx)}" if ctx else ""
        return (
            f"You are a technical planner. Decompose the task into at most "
            f"{self._max_todos} ordered, concrete sub-tasks. Each sub-task must be "
            f"independently actionable.\n\n"
            f"Output format — one per line:\n"
            f"[TASK-1] <description>\n"
            f"[TASK-2] <description> [depends: TASK-1]\n"
            f"...\n\n"
            f"Use '[depends: TASK-N]' only when a task strictly requires a prior one.\n\n"
            f"Task: {task}{ctx_str}"
        )

    def _build_research_prompt(
        self, todo: TodoItem, root_task: str, sandbox_context: str, mcp_tools: list[str]
    ) -> str:
        tools_str = ", ".join(mcp_tools) if mcp_tools else "none"
        return (
            f"You are a technical researcher. Gather context for the sub-task below.\n\n"
            f"Root task: {root_task}\n"
            f"Sub-task [{todo.id}]: {todo.description}\n\n"
            f"Available MCP tools: {tools_str}\n"
            f"Prior artifacts:\n{sandbox_context}\n\n"
            f"Instructions:\n"
            f"- Wrap shell commands in ```bash ... ``` blocks.\n"
            f"- If no research is needed, output exactly: [SKIP]\n"
            f"- Otherwise, output concise findings (max 800 words)."
        )

    def _build_code_prompt(
        self,
        todo: TodoItem,
        root_task: str,
        research_context: str,
        prior_code: str,
    ) -> str:
        return (
            f"You are a senior software engineer. Implement the sub-task below.\n\n"
            f"Root task: {root_task}\n"
            f"Sub-task [{todo.id}]: {todo.description}\n\n"
            f"Research findings:\n{research_context}\n\n"
            f"Prior code artifacts:\n{prior_code if prior_code else '(none yet)'}\n\n"
            f"Instructions:\n"
            f"- Produce complete, runnable code.\n"
            f"- Wrap shell commands in ```bash ... ``` blocks (auto-executed).\n"
            f"- If no code is needed, output exactly: [SKIP]"
        )

    # ------------------------------------------------------------------
    # Todo parser — supports depends_on annotations
    # ------------------------------------------------------------------

    def _parse_todos(self, raw: str) -> list[TodoItem]:
        import re
        todos: list[TodoItem] = []
        for match in re.finditer(
            r"\[TASK-(\d+)\]\s+(.+?)(?:\s+\[depends:\s*([^\]]+)\])?$",
            raw,
            re.MULTILINE,
        ):
            task_id = f"T{match.group(1)}"
            description = match.group(2).strip()
            deps_raw = match.group(3) or ""
            depends_on = [
                f"T{d.strip().removeprefix('TASK-')}"
                for d in deps_raw.split(",")
                if d.strip()
            ]
            todos.append(TodoItem(
                id=task_id,
                description=description,
                depends_on=depends_on,
            ))
        return todos[: self._max_todos]

    # ------------------------------------------------------------------
    # Stub (no LLM configured)
    # ------------------------------------------------------------------

    @staticmethod
    def _stub_response(role: str, prompt: str) -> str:
        if role == "planner":
            return (
                "[TASK-1] Implement the requested feature\n"
                "[TASK-2] Write tests [depends: TASK-1]\n"
                "[TASK-3] Update documentation [depends: TASK-2]"
            )
        if role == "researcher":
            return f"[stub] Research context for: {prompt[:60]}"
        return f"[stub] # Code for: {prompt[:60]}"


# ---------------------------------------------------------------------------
# DAG wave builder — increment #2 (parallel execution)
# ---------------------------------------------------------------------------

def _build_waves(todos: list[TodoItem]) -> list[list[TodoItem]]:
    """
    Topological sort → execution waves.

    Todos in the same wave have no inter-dependencies and run concurrently.
    Example:
        T1 (no deps) → wave 0
        T2 (no deps) → wave 0
        T3 (depends T1) → wave 1
        T4 (depends T1, T2) → wave 1
        T5 (depends T3) → wave 2
    """
    id_to_todo = {t.id: t for t in todos}
    assigned: dict[str, int] = {}

    def _wave_of(todo_id: str, depth: int = 0) -> int:
        if depth > len(todos):
            return 0  # cycle guard
        if todo_id in assigned:
            return assigned[todo_id]
        todo = id_to_todo.get(todo_id)
        if not todo or not todo.depends_on:
            assigned[todo_id] = 0
            return 0
        w = max(_wave_of(dep, depth + 1) for dep in todo.depends_on) + 1
        assigned[todo_id] = w
        return w

    for todo in todos:
        _wave_of(todo.id)

    max_wave = max(assigned.values(), default=0)
    waves: list[list[TodoItem]] = [[] for _ in range(max_wave + 1)]
    for todo in todos:
        waves[assigned[todo.id]].append(todo)
    return [w for w in waves if w]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _LoopError(Exception):
    pass


def _json_safe(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)
