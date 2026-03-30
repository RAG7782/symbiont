"""
Tests for the SYMBIONT organism.

Tests verify that all 8 biological systems work together correctly:
1. Mycelium — message routing
2. TopologyEngine — path optimization
3. CasteRegistry — population management
4. WaggleProtocol — collective decisions
5. Mound — artifact storage + homeostasis
6. MurmurationBus — neighbor coordination
7. Governor — contextual leadership + suppression
8. PodDynamics — coalition formation
"""

import asyncio
import pytest

from symbiont import Symbiont
from symbiont.backends import EchoBackend
from symbiont.core.mycelium import Mycelium
from symbiont.core.topology import TopologyEngine
from symbiont.core.castes import CasteRegistry
from symbiont.core.waggle import WaggleProtocol
from symbiont.core.mound import Mound
from symbiont.core.murmuration import MurmurationBus
from symbiont.core.governance import Governor
from symbiont.core.pod import PodDynamics
from symbiont.types import (
    AgentState,
    AllianceRequest,
    Artifact,
    ArtifactStatus,
    Caste,
    Message,
    Phase,
    QuorumLevel,
    Signal,
    SignalType,
    WaggleReport,
)


# ======================================================================
# System 1: Mycelium
# ======================================================================

class TestMycelium:

    @pytest.mark.asyncio
    async def test_publish_subscribe(self):
        mycelium = Mycelium()
        received = []

        async def handler(msg: Message):
            received.append(msg)

        mycelium.subscribe("test", "agent-1", handler)
        await mycelium.publish("test", payload="hello", sender_id="agent-0")

        assert len(received) == 1
        assert received[0].payload == "hello"
        assert received[0].sender_id == "agent-0"

    @pytest.mark.asyncio
    async def test_hub_nodes(self):
        mycelium = Mycelium()
        async def noop(msg): pass
        mycelium.subscribe("ch1", "agent-1", noop)
        for _ in range(10):
            await mycelium.publish("ch1", payload="x", sender_id="agent-hub")
        hubs = mycelium.get_hub_nodes(1)
        assert hubs[0][0] == "agent-hub"

    @pytest.mark.asyncio
    async def test_channel_stats(self):
        mycelium = Mycelium()
        await mycelium.publish("ch1", payload="a")
        await mycelium.publish("ch1", payload="b")
        stats = mycelium.get_channel_stats()
        assert stats["ch1"].message_count == 2

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        mycelium = Mycelium()
        received = []
        async def handler(msg): received.append(msg)
        mycelium.subscribe("ch", "a1", handler)
        assert mycelium.unsubscribe("ch", "a1")
        await mycelium.publish("ch", payload="x")
        assert len(received) == 0


# ======================================================================
# System 2: TopologyEngine
# ======================================================================

class TestTopologyEngine:

    @pytest.mark.asyncio
    async def test_cycle_runs(self):
        mycelium = Mycelium()
        engine = TopologyEngine()
        engine.wire(mycelium)
        await mycelium.publish("ch1", payload="x")
        report = await engine.run_cycle()
        assert report["cycle"] == 1

    @pytest.mark.asyncio
    async def test_path_health(self):
        mycelium = Mycelium()
        engine = TopologyEngine()
        engine.wire(mycelium)
        await mycelium.publish("active", payload="x")
        await engine.run_cycle()
        health = engine.get_path_health()
        assert "active" in health


# ======================================================================
# System 3: CasteRegistry
# ======================================================================

class TestCasteRegistry:

    def test_spawn_limits(self):
        registry = CasteRegistry()
        assert registry.can_spawn(Caste.QUEEN)
        registry.register_birth(Caste.QUEEN)
        assert not registry.can_spawn(Caste.QUEEN)  # Max 1 queen

    def test_demand_signals(self):
        registry = CasteRegistry()
        registry.signal_demand(Caste.SCOUT, 3)
        assert registry.consume_demand() == Caste.SCOUT

    def test_population_tracking(self):
        registry = CasteRegistry()
        registry.register_birth(Caste.MEDIA)
        registry.register_birth(Caste.MEDIA)
        assert registry.get_population()[Caste.MEDIA] == 2
        registry.register_death(Caste.MEDIA)
        assert registry.get_population()[Caste.MEDIA] == 1


# ======================================================================
# System 4: WaggleProtocol
# ======================================================================

class TestWaggleProtocol:

    @pytest.mark.asyncio
    async def test_session_with_reports(self):
        waggle = WaggleProtocol()

        counter = {"n": 0}
        async def mock_scout(session_id, question):
            counter["n"] += 1
            return WaggleReport(
                scout_id=f"scout-{counter['n']}",  # Unique scouts (quorum counts unique voters)
                option="approach-A",
                description="Good approach",
                quality=0.8,
                confidence=0.9,
            )

        waggle.set_scout_dispatcher(mock_scout)
        session = await waggle.initiate("s1", "What approach?", QuorumLevel.LOW)
        assert session.decision == "approach-A"
        assert session.decided

    @pytest.mark.asyncio
    async def test_no_quorum(self):
        waggle = WaggleProtocol()

        counter = {"n": 0}
        async def diverse_scout(session_id, question):
            counter["n"] += 1
            return WaggleReport(
                scout_id=f"scout-{counter['n']}",
                option=f"option-{counter['n']}",
                quality=0.5,
                confidence=0.5,
            )

        waggle.set_scout_dispatcher(diverse_scout)
        session = await waggle.initiate("s2", "Ambiguous?", QuorumLevel.HIGH)
        # With all different options, quorum shouldn't be reached cleanly
        assert session.decision is not None  # Falls back to highest scored


# ======================================================================
# System 5: Mound
# ======================================================================

class TestMound:

    @pytest.mark.asyncio
    async def test_deposit_and_query(self):
        mound = Mound()
        artifact = Artifact(kind="code", content="def hello(): pass", quality=0.8)
        await mound.deposit(artifact)
        results = mound.query(kind="code")
        assert len(results) == 1
        assert results[0].content == "def hello(): pass"

    @pytest.mark.asyncio
    async def test_knowledge_base(self):
        mound = Mound()
        mound.learn("auth", "Use JWT tokens for authentication")
        assert mound.recall("auth") == "Use JWT tokens for authentication"
        results = mound.search_knowledge("JWT")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_artifact_update(self):
        mound = Mound()
        artifact = Artifact(kind="code", content="v1", status=ArtifactStatus.DRAFT)
        await mound.deposit(artifact)
        await mound.update(artifact.id, status=ArtifactStatus.APPROVED, content="v2")
        updated = mound.get(artifact.id)
        assert updated.status == ArtifactStatus.APPROVED
        assert updated.content == "v2"

    @pytest.mark.asyncio
    async def test_health_metrics(self):
        mound = Mound()
        mound.update_health(latency_ms=100, error_rate=0.01)
        assert mound.health.is_healthy()
        mound.update_health(error_rate=0.5)
        assert not mound.health.is_healthy()


# ======================================================================
# System 6: MurmurationBus
# ======================================================================

class TestMurmurationBus:

    def test_neighbor_limit(self):
        bus = MurmurationBus()
        bus.register_agent("a1")
        for i in range(10):
            bus.add_neighbor("a1", f"n{i}")
        # Should cap at 7 (default max_neighbors)
        assert len(bus.get_neighbors("a1")) == 7

    @pytest.mark.asyncio
    async def test_signal_propagation(self):
        bus = MurmurationBus()
        bus.register_agent("a1")
        bus.register_agent("a2")
        bus.register_agent("a3")
        bus.add_neighbor("a1", "a2")
        bus.add_neighbor("a2", "a3")
        signal = Signal(signal_type=SignalType.ALERT, source_id="a1", payload="fire")
        reached = await bus.emit(signal)
        assert reached >= 2  # a2 and a3

    def test_auto_assign_neighbors(self):
        bus = MurmurationBus()
        agents = ["s1", "s2", "s3", "w1", "w2", "m1"]
        for a in agents:
            bus.register_agent(a)
        caste_map = {"s1": "SCOUT", "s2": "SCOUT", "s3": "SCOUT",
                     "w1": "MEDIA", "w2": "MEDIA", "m1": "MAJOR"}
        bus.auto_assign_neighbors("s1", agents, caste_map)
        neighbors = bus.get_neighbors("s1")
        assert len(neighbors) > 0
        assert len(neighbors) <= 7


# ======================================================================
# System 7: Governor
# ======================================================================

class TestGovernor:

    @pytest.mark.asyncio
    async def test_phase_transitions(self):
        gov = Governor()
        assert gov.current_phase == Phase.EXPLORATION
        await gov.transition_to(Phase.DECISION)
        assert gov.current_phase == Phase.DECISION
        assert gov.leading_caste == Caste.MAJOR

    def test_suppression(self):
        gov = Governor()
        gov.register_agent("queen-1", Caste.QUEEN)
        # Only queen can spawn
        assert gov.can_spawn("queen-1")
        assert not gov.can_spawn("worker-1")

    @pytest.mark.asyncio
    async def test_leader_election(self):
        gov = Governor()
        gov.register_agent("major-1", Caste.MAJOR)
        gov._agents["major-1"].trust_score = 0.9
        gov._agents["major-1"].tasks_completed = 10
        # No queen — election should work
        new_queen = await gov.elect_queen()
        assert new_queen == "major-1"
        assert gov._agents["major-1"].caste == Caste.QUEEN

    def test_reserve_pool(self):
        gov = Governor()
        gov.register_agent("w1", Caste.MEDIA)
        gov.hibernate_agent("w1")
        assert gov.reserve_count == 1
        activated = gov.activate_reserve(Caste.MEDIA)
        assert activated == "w1"
        assert gov.reserve_count == 0


# ======================================================================
# System 8: PodDynamics
# ======================================================================

class TestPodDynamics:

    @pytest.mark.asyncio
    async def test_pod_formation(self):
        pods = PodDynamics()
        pods.register_capabilities("a1", {"code", "test"})
        pods.register_capabilities("a2", {"review", "test"})
        request = AllianceRequest(
            requester_id="a1",
            needed_capabilities={"review"},
            objective="Review the auth module",
        )
        pod = await pods.request_alliance(request)
        assert pod is not None
        assert "a2" in pod.members
        assert pod.size == 2

    @pytest.mark.asyncio
    async def test_pod_dissolution(self):
        pods = PodDynamics()
        pods.register_capabilities("a1", {"code"})
        pods.register_capabilities("a2", {"review"})
        request = AllianceRequest(
            requester_id="a1",
            needed_capabilities={"review"},
            objective="test",
        )
        pod = await pods.request_alliance(request)
        await pods.complete_pod(pod.id, result="done")
        assert pod.completed
        assert pods.get_agent_pod("a1") is None

    @pytest.mark.asyncio
    async def test_swarm(self):
        pods = PodDynamics()
        await pods.activate_swarm("critical incident")
        assert pods.is_swarm_active
        await pods.deactivate_swarm()
        assert not pods.is_swarm_active


# ======================================================================
# Full Organism Integration
# ======================================================================

class TestSymbiontOrganism:

    @pytest.mark.asyncio
    async def test_boot_and_shutdown(self):
        org = Symbiont()
        org.set_llm_backend(EchoBackend())
        await org.boot()
        assert org.is_running
        assert org.agent_count >= 8  # Queen + 2 scouts + 2 workers + 1 major + 3 minima
        await org.shutdown()
        assert not org.is_running

    @pytest.mark.asyncio
    async def test_full_task_execution(self):
        org = Symbiont()
        org.set_llm_backend(EchoBackend())
        await org.boot()

        result = await org.execute(
            task="Implement a hello world function",
            context={"language": "python"},
        )

        assert result["task_id"]
        assert result["approach"]
        assert result["waggle_session"]["reports_count"] > 0
        assert result["execution"] is not None

        await org.shutdown()

    @pytest.mark.asyncio
    async def test_status_reporting(self):
        org = Symbiont()
        org.set_llm_backend(EchoBackend())
        await org.boot()

        status = org.status()
        assert status["running"]
        assert status["agents"]["total"] > 0
        assert status["governance"]["phase"] == "EXPLORATION"

        await org.shutdown()

    @pytest.mark.asyncio
    async def test_high_risk_task_uses_higher_quorum(self):
        org = Symbiont()
        org.set_llm_backend(EchoBackend())
        await org.boot()

        # A deploy task should use CRITICAL quorum
        level = org._determine_quorum_level("Deploy migration to production", {})
        assert level == QuorumLevel.CRITICAL

        # A simple task should use LOW quorum
        level = org._determine_quorum_level("Fix typo in readme", {})
        assert level == QuorumLevel.LOW

        await org.shutdown()
