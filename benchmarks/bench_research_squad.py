"""
SYMBIONT Performance Benchmark — ResearchSquad pipeline

Usage:
    uv run python benchmarks/bench_research_squad.py
    uv run python benchmarks/bench_research_squad.py --runs 20 --tasks 3

Metrics:
    - Latency p50/p95/p99 (seconds)
    - Throughput (pipelines/sec)
    - Parallel speedup vs sequential estimate
    - Loop detection rate
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

TASKS = [
    "List 3 advantages of microservices architecture",
    "Explain the difference between supervised and unsupervised learning",
    "What are the key principles of clean code?",
    "Describe the CAP theorem in distributed systems",
    "What is the actor model for concurrent computation?",
]

MOCK_LLM_DELAY = 0.01  # seconds per call (simulates fast LLM)


async def _mock_llm(prompt: str) -> str:
    await asyncio.sleep(MOCK_LLM_DELAY)
    if "Decompose" in prompt:
        return "[TASK-1] Research phase\n[TASK-2] Synthesis phase [depends: TASK-1]"
    return f"Result for: {prompt[:40]}"


async def run_single(task: str) -> tuple[float, bool]:
    """Run one pipeline, return (elapsed_sec, success)."""
    from symbiont.research_squad import ResearchSquad

    squad = ResearchSquad(llm_backend=_mock_llm)
    t0 = time.perf_counter()
    result = await squad.run(task)
    elapsed = time.perf_counter() - t0
    return elapsed, result.success


async def run_parallel_batch(tasks: list[str]) -> tuple[float, list[float]]:
    """Run multiple pipelines concurrently, return (total_elapsed, per_task_times)."""
    t0 = time.perf_counter()
    results = await asyncio.gather(*[run_single(t) for t in tasks])
    total = time.perf_counter() - t0
    times = [r[0] for r in results]
    return total, times


def percentile(data: list[float], p: int) -> float:
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * p / 100)
    return sorted_data[min(idx, len(sorted_data) - 1)]


async def main(runs: int, num_tasks: int) -> None:
    tasks = (TASKS * ((num_tasks // len(TASKS)) + 1))[:num_tasks]

    print(f"\n{'='*60}")
    print(f"SYMBIONT ResearchSquad Benchmark")
    print(f"  Runs: {runs} | Tasks/run: {num_tasks} | LLM delay: {MOCK_LLM_DELAY*1000:.0f}ms")
    print(f"{'='*60}\n")

    # --- Warmup ---
    print("Warming up (2 runs)...")
    for _ in range(2):
        await run_single(tasks[0])

    # --- Sequential baseline ---
    print(f"Running {runs} sequential pipelines...")
    seq_times: list[float] = []
    for _ in range(runs):
        t, _ = await run_single(tasks[0])
        seq_times.append(t)

    # --- Parallel batch ---
    print(f"Running {runs} parallel batches ({num_tasks} concurrent)...")
    par_totals: list[float] = []
    par_per_task: list[float] = []
    for _ in range(runs):
        total, per_task = await run_parallel_batch(tasks)
        par_totals.append(total)
        par_per_task.extend(per_task)

    # --- Report ---
    print(f"\n{'─'*60}")
    print("SEQUENTIAL (single pipeline)")
    print(f"  p50:  {percentile(seq_times, 50)*1000:.1f}ms")
    print(f"  p95:  {percentile(seq_times, 95)*1000:.1f}ms")
    print(f"  p99:  {percentile(seq_times, 99)*1000:.1f}ms")
    print(f"  mean: {statistics.mean(seq_times)*1000:.1f}ms")
    print(f"  throughput: {1/statistics.mean(seq_times):.1f} pipelines/sec")

    print(f"\nPARALLEL BATCH ({num_tasks} concurrent)")
    print(f"  p50 (total batch):  {percentile(par_totals, 50)*1000:.1f}ms")
    print(f"  p95 (total batch):  {percentile(par_totals, 95)*1000:.1f}ms")
    print(f"  p50 (per-task):     {percentile(par_per_task, 50)*1000:.1f}ms")
    speedup = statistics.mean(seq_times) * num_tasks / statistics.mean(par_totals)
    print(f"  parallel speedup:   {speedup:.2f}x vs sequential")
    print(f"  throughput: {num_tasks/statistics.mean(par_totals):.1f} pipelines/sec")

    print(f"\n{'─'*60}")
    print(f"STATUS: {'PASS' if speedup > 1.5 else 'WARN — check parallelism'}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--tasks", type=int, default=3)
    args = parser.parse_args()
    asyncio.run(main(args.runs, args.tasks))
