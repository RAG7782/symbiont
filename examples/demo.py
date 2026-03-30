"""
SYMBIONT Demo — Full organism lifecycle.

This example boots the organism, executes a task through all 5 phases,
and shows the organism's status at each step.

Run with: python -m examples.demo
"""

import asyncio
import logging
import json

# Configure logging to see the organism's activity
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-20s] %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)

from symbiont import Symbiont
from symbiont.backends import EchoBackend


def pretty(data: dict, indent: int = 2) -> str:
    """Pretty-print a dict, handling non-serializable values."""
    def default(obj):
        if isinstance(obj, set):
            return list(obj)
        if hasattr(obj, 'name'):  # Enums
            return obj.name
        if hasattr(obj, '__dict__'):
            return str(obj)
        return str(obj)

    def convert_keys(obj):
        if isinstance(obj, dict):
            return {(k.name if hasattr(k, 'name') else str(k)): convert_keys(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [convert_keys(i) for i in obj]
        return obj

    return json.dumps(convert_keys(data), indent=indent, default=default)


async def main():
    print("=" * 70)
    print("  SYMBIONT — Bio-Inspired Multi-Agent Organism")
    print("  Demo with EchoBackend (no LLM calls)")
    print("=" * 70)
    print()

    # 1. Create and configure the organism
    organism = Symbiont()
    organism.set_llm_backend(EchoBackend())

    # 2. Boot — this wires all 8 systems and spawns initial agents
    print("[1] Booting organism...")
    await organism.boot()
    print(f"    Booted with {organism.agent_count} agents")
    print()

    # 3. Show initial status
    print("[2] Organism status:")
    status = organism.status()
    print(pretty(status))
    print()

    # 4. Execute a task — this flows through all 5 phases
    print("[3] Executing task: 'Implement a user authentication module'")
    print("    (This triggers: Exploration → Decision → Execution → Validation → Delivery)")
    print()

    result = await organism.execute(
        task="Implement a user authentication module",
        context={"language": "python", "framework": "fastapi"},
    )

    print("[4] Task result:")
    print(pretty(result))
    print()

    # 5. Show status after task
    print("[5] Organism status after task:")
    status = organism.status()
    print(pretty(status))
    print()

    # 6. Execute a second task (high-risk — requires higher quorum)
    print("[6] Executing high-risk task: 'Deploy migration to production database'")
    print()

    result2 = await organism.execute(
        task="Deploy migration to production database",
        context={"environment": "production", "irreversible": True},
    )

    print("[7] High-risk task result:")
    print(pretty(result2))
    print()

    # 7. Show the Mound's knowledge base
    print("[8] Knowledge base (Fungus Garden):")
    for key, value in list(organism.mound._knowledge_base.items())[:5]:
        print(f"    {key}: {value[:80]}...")
    print()

    # 8. Show topology
    print("[9] Mycelium topology:")
    topo = organism.mycelium.query_topology()
    print(f"    Channels: {len(topo['channels'])}")
    print(f"    Hub nodes: {topo['hub_nodes'][:3]}")
    print(f"    Total messages: {topo['total_messages']}")
    print()

    # 9. Graceful shutdown
    print("[10] Shutting down...")
    await organism.shutdown()
    print("     Done.")


if __name__ == "__main__":
    asyncio.run(main())
