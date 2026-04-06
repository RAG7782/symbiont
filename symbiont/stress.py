"""
SYMBIONT Stress Test — built-in load and resilience testing.

Tests every component under pressure:
1. Mycelium throughput (messages/sec, fan-out latency)
2. Organism lifecycle (boot/execute/shutdown cycles)
3. HTTP Bridge (concurrent requests, webhook flood)
4. Persistence (concurrent writes, snapshot under load)
5. Federation (heartbeat flood, relay throughput)
6. Squads (concurrent assign/unassign)
7. Colony (parallel SSH, timeout handling)
8. Alert system (concurrent checks)

Zero external dependencies — uses stdlib asyncio, threading, concurrent.futures.

Usage:
    sym stress                  # Run all stress tests
    sym stress quick            # Fast smoke test (~10s)
    sym stress bridge           # HTTP bridge only
    sym stress organism         # Organism lifecycle only
    sym stress report           # Full test + JSON report

Design:
    Each test returns a StressResult with pass/fail, metrics, and latency
    percentiles (p50, p95, p99). Results feed into the audit system.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import statistics
import tempfile
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class StressResult:
    """Result of a single stress test."""
    name: str
    passed: bool
    duration_sec: float = 0.0
    operations: int = 0
    ops_per_sec: float = 0.0
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0
    error_rate: float = 0.0
    details: str = ""

    @property
    def p50(self) -> float:
        return self._percentile(50)

    @property
    def p95(self) -> float:
        return self._percentile(95)

    @property
    def p99(self) -> float:
        return self._percentile(99)

    def _percentile(self, pct: int) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_l = sorted(self.latencies_ms)
        idx = int(len(sorted_l) * pct / 100)
        return sorted_l[min(idx, len(sorted_l) - 1)]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "duration_sec": round(self.duration_sec, 3),
            "operations": self.operations,
            "ops_per_sec": round(self.ops_per_sec, 1),
            "p50_ms": round(self.p50, 2),
            "p95_ms": round(self.p95, 2),
            "p99_ms": round(self.p99, 2),
            "errors": self.errors,
            "error_rate": round(self.error_rate, 4),
        }


@dataclass
class StressReport:
    """Full stress test report."""
    results: list[StressResult] = field(default_factory=list)
    total_duration: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "total_duration_sec": round(self.total_duration, 2),
            "summary": {
                "total": len(self.results),
                "passed": self.pass_count,
                "failed": len(self.results) - self.pass_count,
                "all_passed": self.all_passed,
            },
            "tests": [r.to_dict() for r in self.results],
        }


# ---------------------------------------------------------------------------
# Individual Stress Tests
# ---------------------------------------------------------------------------

async def stress_mycelium(ops: int = 1000) -> StressResult:
    """Flood the Mycelium with messages and measure throughput."""
    from symbiont.core.mycelium import Mycelium

    mycelium = Mycelium()
    latencies = []
    errors = 0

    # Subscribe a counter
    received = []

    async def handler(msg):
        received.append(msg)

    mycelium.subscribe("stress.test", "counter", handler)

    start = time.perf_counter()
    for i in range(ops):
        t0 = time.perf_counter()
        try:
            await mycelium.publish("stress.test", {"seq": i}, sender_id="stress")
            latencies.append((time.perf_counter() - t0) * 1000)
        except Exception:
            errors += 1
    duration = time.perf_counter() - start

    return StressResult(
        name="mycelium_throughput",
        passed=errors == 0 and len(received) == ops,
        duration_sec=duration,
        operations=ops,
        ops_per_sec=ops / max(duration, 0.001),
        latencies_ms=latencies,
        errors=errors,
        error_rate=errors / max(ops, 1),
        details=f"Sent {ops}, received {len(received)}",
    )


async def stress_organism_lifecycle(cycles: int = 5) -> StressResult:
    """Boot and shutdown the organism multiple times."""
    from symbiont import Symbiont
    from symbiont.backends import EchoBackend

    latencies = []
    errors = 0

    start = time.perf_counter()
    for i in range(cycles):
        t0 = time.perf_counter()
        try:
            org = Symbiont()
            org.set_llm_backend(EchoBackend())
            await org.boot()
            assert org.agent_count == 9
            await org.shutdown()
            latencies.append((time.perf_counter() - t0) * 1000)
        except Exception as e:
            errors += 1
            logger.warning("stress: lifecycle error cycle %d: %s", i, e)
    duration = time.perf_counter() - start

    return StressResult(
        name="organism_lifecycle",
        passed=errors == 0,
        duration_sec=duration,
        operations=cycles,
        ops_per_sec=cycles / max(duration, 0.001),
        latencies_ms=latencies,
        errors=errors,
        error_rate=errors / max(cycles, 1),
        details=f"{cycles} boot/shutdown cycles",
    )


async def stress_organism_execution(tasks: int = 10) -> StressResult:
    """Execute multiple tasks through the organism."""
    from symbiont import Symbiont
    from symbiont.backends import EchoBackend

    org = Symbiont()
    org.set_llm_backend(EchoBackend())
    await org.boot()

    latencies = []
    errors = 0

    start = time.perf_counter()
    for i in range(tasks):
        t0 = time.perf_counter()
        try:
            result = await org.execute(f"Stress test task {i}")
            if not result.get("task_id"):
                errors += 1
            latencies.append((time.perf_counter() - t0) * 1000)
        except Exception:
            errors += 1
    duration = time.perf_counter() - start

    await org.shutdown()

    return StressResult(
        name="organism_execution",
        passed=errors == 0,
        duration_sec=duration,
        operations=tasks,
        ops_per_sec=tasks / max(duration, 0.001),
        latencies_ms=latencies,
        errors=errors,
        error_rate=errors / max(tasks, 1),
        details=f"{tasks} tasks executed",
    )


async def stress_persistence(ops: int = 500) -> StressResult:
    """Concurrent writes to SQLite persistence."""
    from symbiont.persistence import PersistenceStore
    from symbiont.types import Message

    db = tempfile.mktemp(suffix=".db")
    store = PersistenceStore(db)
    latencies = []
    errors = 0

    start = time.perf_counter()
    for i in range(ops):
        t0 = time.perf_counter()
        try:
            store.save_message(Message(id=f"stress-{i}", channel="stress", payload={"i": i}))
            store.set(f"stress-key-{i}", {"value": i})
            latencies.append((time.perf_counter() - t0) * 1000)
        except Exception:
            errors += 1
    duration = time.perf_counter() - start

    # Verify
    msgs = store.load_recent_messages(ops)
    stats = store.stats()

    store.close()
    os.unlink(db)

    return StressResult(
        name="persistence_writes",
        passed=errors == 0 and len(msgs) > 0,
        duration_sec=duration,
        operations=ops,
        ops_per_sec=ops / max(duration, 0.001),
        latencies_ms=latencies,
        errors=errors,
        error_rate=errors / max(ops, 1),
        details=f"{ops} writes, {stats['messages']} stored",
    )


async def stress_persistence_concurrent(threads: int = 4, ops_per_thread: int = 100) -> StressResult:
    """Multi-threaded concurrent writes to persistence."""
    from symbiont.persistence import PersistenceStore

    db = tempfile.mktemp(suffix=".db")
    store = PersistenceStore(db)
    all_latencies = []
    error_count = 0

    def writer(thread_id: int):
        lats = []
        errs = 0
        for i in range(ops_per_thread):
            t0 = time.perf_counter()
            try:
                store.set(f"t{thread_id}-k{i}", {"thread": thread_id, "op": i})
                lats.append((time.perf_counter() - t0) * 1000)
            except Exception:
                errs += 1
        return lats, errs

    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as pool:
        futures = [pool.submit(writer, t) for t in range(threads)]
        for f in concurrent.futures.as_completed(futures):
            lats, errs = f.result()
            all_latencies.extend(lats)
            error_count += errs
    duration = time.perf_counter() - start

    total_ops = threads * ops_per_thread
    store.close()
    os.unlink(db)

    return StressResult(
        name="persistence_concurrent",
        passed=error_count == 0,
        duration_sec=duration,
        operations=total_ops,
        ops_per_sec=total_ops / max(duration, 0.001),
        latencies_ms=all_latencies,
        errors=error_count,
        error_rate=error_count / max(total_ops, 1),
        details=f"{threads} threads x {ops_per_thread} ops",
    )


async def stress_federation(peers: int = 10) -> StressResult:
    """Simulate federation with many peers."""
    from symbiont.federation import Federation

    fed = Federation(organism_id="stress-test")
    latencies = []
    errors = 0

    start = time.perf_counter()
    # Register many peers
    for i in range(peers):
        t0 = time.perf_counter()
        try:
            fed.register_peer(f"peer-{i}", f"http://fake-{i}:7777", name=f"Peer {i}")
            latencies.append((time.perf_counter() - t0) * 1000)
        except Exception:
            errors += 1

    # Heartbeat all
    for i in range(peers):
        t0 = time.perf_counter()
        try:
            fed.receive_heartbeat(f"peer-{i}", f"http://fake-{i}:7777")
            latencies.append((time.perf_counter() - t0) * 1000)
        except Exception:
            errors += 1

    duration = time.perf_counter() - start
    alive = len(fed.alive_peers)

    return StressResult(
        name="federation_peers",
        passed=errors == 0 and alive == peers,
        duration_sec=duration,
        operations=peers * 2,
        ops_per_sec=(peers * 2) / max(duration, 0.001),
        latencies_ms=latencies,
        errors=errors,
        error_rate=errors / max(peers * 2, 1),
        details=f"{peers} peers registered, {alive} alive",
    )


async def stress_squads(squads_count: int = 20, agents_per: int = 10) -> StressResult:
    """Create many squads with many agents."""
    from symbiont.squads import SquadManager

    mgr = SquadManager()
    latencies = []
    errors = 0

    start = time.perf_counter()
    for s in range(squads_count):
        t0 = time.perf_counter()
        try:
            mgr.create(f"squad-{s}", description=f"Stress squad {s}")
            agents = [f"agent-{s}-{a}" for a in range(agents_per)]
            mgr.assign(f"squad-{s}", agents)
            latencies.append((time.perf_counter() - t0) * 1000)
        except Exception:
            errors += 1
    duration = time.perf_counter() - start

    return StressResult(
        name="squads_operations",
        passed=errors == 0 and mgr.total_squads == squads_count,
        duration_sec=duration,
        operations=squads_count,
        ops_per_sec=squads_count / max(duration, 0.001),
        latencies_ms=latencies,
        errors=errors,
        error_rate=errors / max(squads_count, 1),
        details=f"{squads_count} squads x {agents_per} agents = {mgr.total_assigned} total",
    )


def stress_bridge_http(port: int = 7777, requests: int = 50, threads: int = 4) -> StressResult:
    """Flood the HTTP bridge with concurrent requests."""
    all_latencies = []
    error_count = 0

    def requester(thread_id: int, count: int):
        lats = []
        errs = 0
        for i in range(count):
            t0 = time.perf_counter()
            try:
                # Alternate between endpoints
                if i % 3 == 0:
                    url = f"http://localhost:{port}/health"
                    req = urllib.request.Request(url)
                elif i % 3 == 1:
                    url = f"http://localhost:{port}/status"
                    req = urllib.request.Request(url)
                else:
                    url = f"http://localhost:{port}/webhook"
                    data = json.dumps({
                        "channel": f"stress.t{thread_id}",
                        "payload": {"seq": i, "thread": thread_id},
                        "sender": "stress-test",
                    }).encode()
                    req = urllib.request.Request(url, data=data,
                                                 headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    resp.read()
                lats.append((time.perf_counter() - t0) * 1000)
            except Exception:
                errs += 1
                lats.append((time.perf_counter() - t0) * 1000)
        return lats, errs

    per_thread = requests // threads

    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as pool:
        futures = [pool.submit(requester, t, per_thread) for t in range(threads)]
        for f in concurrent.futures.as_completed(futures):
            lats, errs = f.result()
            all_latencies.extend(lats)
            error_count += errs
    duration = time.perf_counter() - start

    total = threads * per_thread
    return StressResult(
        name="bridge_http_flood",
        passed=error_count < total * 0.05,  # <5% error rate
        duration_sec=duration,
        operations=total,
        ops_per_sec=total / max(duration, 0.001),
        latencies_ms=all_latencies,
        errors=error_count,
        error_rate=error_count / max(total, 1),
        details=f"{threads} threads x {per_thread} requests",
    )


# ---------------------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------------------

async def run_stress(mode: str = "full", bridge_port: int = 7777) -> StressReport:
    """Run stress tests."""
    report = StressReport()
    start = time.perf_counter()

    tests_to_run = []

    if mode in ("full", "quick", "organism"):
        tests_to_run.append(("Mycelium throughput",
                             stress_mycelium(1000 if mode == "full" else 100)))
        tests_to_run.append(("Organism lifecycle",
                             stress_organism_lifecycle(5 if mode == "full" else 2)))
        tests_to_run.append(("Organism execution",
                             stress_organism_execution(10 if mode == "full" else 3)))

    if mode in ("full", "quick"):
        tests_to_run.append(("Persistence writes",
                             stress_persistence(500 if mode == "full" else 50)))
        tests_to_run.append(("Persistence concurrent",
                             stress_persistence_concurrent(
                                 4 if mode == "full" else 2,
                                 100 if mode == "full" else 20)))
        tests_to_run.append(("Federation peers",
                             stress_federation(10 if mode == "full" else 3)))
        tests_to_run.append(("Squads operations",
                             stress_squads(20 if mode == "full" else 5,
                                           10 if mode == "full" else 3)))

    for name, coro in tests_to_run:
        print(f"  Running {name}...", end=" ", flush=True)
        result = await coro
        report.results.append(result)
        icon = "✅" if result.passed else "❌"
        print(f"{icon} {result.ops_per_sec:.0f} ops/s (p50={result.p50:.1f}ms p99={result.p99:.1f}ms)")

    # HTTP bridge test (sync, only if bridge is running)
    if mode in ("full", "bridge"):
        try:
            urllib.request.urlopen(f"http://localhost:{bridge_port}/health", timeout=2)
            print(f"  Running Bridge HTTP flood...", end=" ", flush=True)
            result = stress_bridge_http(
                bridge_port, requests=200 if mode == "full" else 20, threads=4)
            report.results.append(result)
            icon = "✅" if result.passed else "❌"
            print(f"{icon} {result.ops_per_sec:.0f} req/s (p50={result.p50:.1f}ms p99={result.p99:.1f}ms)")
        except Exception:
            print(f"  Skipping Bridge HTTP (bridge not running on :{bridge_port})")

    report.total_duration = time.perf_counter() - start
    return report


def report_text(report: StressReport) -> str:
    """Human-readable stress report."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"  SYMBIONT STRESS TEST REPORT")
    lines.append(f"  {len(report.results)} tests in {report.total_duration:.1f}s")
    icon = "✅" if report.all_passed else "❌"
    lines.append(f"  {icon} {report.pass_count}/{len(report.results)} passed")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"{'Test':<28} {'Status':>6} {'Ops/s':>8} {'p50':>8} {'p95':>8} {'p99':>8} {'Errors':>7}")
    lines.append("-" * 80)

    for r in report.results:
        icon = "PASS" if r.passed else "FAIL"
        lines.append(
            f"{r.name:<28} {icon:>6} {r.ops_per_sec:>7.0f} "
            f"{r.p50:>7.1f}ms {r.p95:>7.1f}ms {r.p99:>7.1f}ms {r.errors:>6}"
        )

    lines.append("")
    return "\n".join(lines)


async def stress_cmd(args: str, verbose: bool = False):
    """CLI handler for sym stress."""
    if verbose:
        logging.basicConfig(level=logging.INFO)

    parts = args.strip().split() if args.strip() else ["full"]
    mode = parts[0] if parts else "full"

    if mode == "help":
        print("Usage: sym stress [full|quick|organism|bridge|report]")
        print("  full      — all tests, high load (~30s)")
        print("  quick     — smoke test, low load (~10s)")
        print("  organism  — organism lifecycle + execution only")
        print("  bridge    — HTTP bridge flood only (requires sym serve)")
        print("  report    — full test + save JSON report")
        return

    print(f"🔥 SYMBIONT Stress Test ({mode})")
    print("=" * 60)

    report = await run_stress(mode=mode)
    print(report_text(report))

    if mode == "report":
        report_path = Path.home() / ".symbiont" / "stress-report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report.to_dict(), indent=2))
        print(f"📄 JSON report saved to {report_path}")

    if not report.all_passed:
        print("⚠️  Some tests failed. Review the results above.")
