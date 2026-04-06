"""
SYMBIONT Colony — remote execution via SSH over Tailscale.

Colonies are remote SYMBIONT instances running on VPS nodes.
They connect back to the local Mycelium via the HTTP bridge.

Commands:
    sym colony list              — show known colonies
    sym colony status            — ping all colonies
    sym colony deploy <name>     — deploy SYMBIONT to a colony
    sym colony run <name> <task> — execute task on a remote colony
    sym colony heartbeat         — check all colonies health
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

COLONY_CONFIG = Path.home() / ".symbiont" / "colonies.json"

# Known colonies — Tailscale IPs
DEFAULT_COLONIES = {
    "kai": {
        "host": "100.73.123.8",
        "user": "root",
        "description": "cloud-882 — Ubuntu 24.04, 144GB disk",
        "public_ip": "74.1.21.180",
    },
    "alan": {
        "host": "100.102.158.60",
        "user": "root",
        "description": "OpenClawHosteg — Ubuntu 24.04, 144GB disk",
        "public_ip": "74.1.21.220",
    },
}


@dataclass
class ColonyResult:
    name: str
    host: str
    success: bool
    output: str
    error: str = ""


def _load_colonies() -> dict:
    if COLONY_CONFIG.exists():
        return json.loads(COLONY_CONFIG.read_text())
    return dict(DEFAULT_COLONIES)


def _save_colonies(colonies: dict) -> None:
    COLONY_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    COLONY_CONFIG.write_text(json.dumps(colonies, indent=2))


def _ssh_cmd(host: str, user: str, cmd: str, timeout: int = 30) -> ColonyResult:
    """Execute a command on a remote colony via SSH."""
    ssh = [
        "ssh", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=no",
        f"{user}@{host}", cmd,
    ]
    try:
        result = subprocess.run(ssh, capture_output=True, text=True, timeout=timeout)
        return ColonyResult(
            name="", host=host,
            success=result.returncode == 0,
            output=result.stdout.strip(),
            error=result.stderr.strip(),
        )
    except subprocess.TimeoutExpired:
        return ColonyResult(name="", host=host, success=False, output="", error="timeout")
    except Exception as e:
        return ColonyResult(name="", host=host, success=False, output="", error=str(e))


async def colony_cmd(args: str, backend: str, verbose: bool):
    """Main colony command dispatcher."""
    if verbose:
        logging.basicConfig(level=logging.INFO)

    parts = args.strip().split(maxsplit=1) if args.strip() else ["list"]
    subcmd = parts[0] if parts else "list"
    rest = parts[1] if len(parts) > 1 else ""

    colonies = _load_colonies()

    if subcmd == "list":
        _colony_list(colonies)
    elif subcmd == "status":
        await _colony_status(colonies)
    elif subcmd == "deploy":
        await _colony_deploy(rest.strip() or "all", colonies, backend)
    elif subcmd == "run":
        run_parts = rest.strip().split(maxsplit=1)
        if len(run_parts) < 2:
            print("Usage: sym colony run <name> <task>")
            return
        await _colony_run(run_parts[0], run_parts[1], colonies, backend)
    elif subcmd == "heartbeat":
        await _colony_heartbeat(colonies)
    else:
        print(f"Unknown colony command: {subcmd}")
        print("Available: list, status, deploy, run, heartbeat")


def _colony_list(colonies: dict):
    print("🏗️  SYMBIONT Colonies")
    print("=" * 60)
    for name, info in colonies.items():
        print(f"  {name:10s} {info['host']:20s} {info.get('description', '')}")
    print()
    if not COLONY_CONFIG.exists():
        print(f"  (using defaults — save with: sym colony deploy all)")


async def _colony_status(colonies: dict):
    print("🏗️  Colony Status")
    print("=" * 60)

    tasks = []
    for name, info in colonies.items():
        tasks.append((name, info))

    for name, info in tasks:
        result = _ssh_cmd(info["host"], info["user"], "uptime", timeout=15)
        result.name = name
        status = "online" if result.success else "offline"
        icon = "🟢" if result.success else "🔴"
        detail = result.output.strip() if result.success else result.error
        print(f"  {icon} {name:10s} [{status}] {detail}")


async def _colony_heartbeat(colonies: dict):
    """Quick health check — just ping via SSH."""
    print("💓 Colony Heartbeat")
    for name, info in colonies.items():
        result = _ssh_cmd(info["host"], info["user"], "echo ok", timeout=10)
        icon = "💚" if result.success else "💔"
        print(f"  {icon} {name}")


async def _colony_deploy(target: str, colonies: dict, backend: str):
    """Deploy SYMBIONT to a remote colony."""
    targets = list(colonies.keys()) if target == "all" else [target]

    for name in targets:
        if name not in colonies:
            print(f"  Unknown colony: {name}")
            continue

        info = colonies[name]
        host, user = info["host"], info["user"]
        print(f"🚀 Deploying SYMBIONT to {name} ({host})...")

        # 1. Check Python
        r = _ssh_cmd(host, user, "python3 --version", timeout=15)
        if not r.success:
            print(f"  ❌ Python3 not found on {name}. Install first.")
            continue
        print(f"  ✅ {r.output}")

        # 2. Create directory
        _ssh_cmd(host, user, "mkdir -p /opt/symbiont", timeout=10)

        # 3. Rsync the symbiont package
        rsync = [
            "rsync", "-avz", "--delete",
            "--exclude", ".venv", "--exclude", "__pycache__",
            "--exclude", ".git", "--exclude", "*.pyc",
            str(Path.home() / "symbiont") + "/",
            f"{user}@{host}:/opt/symbiont/",
        ]
        print(f"  📦 Syncing code...")
        result = subprocess.run(rsync, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            print(f"  ❌ Rsync failed: {result.stderr[:200]}")
            continue
        print(f"  ✅ Code synced")

        # 4. Create venv and install
        setup_cmd = (
            "cd /opt/symbiont && "
            "python3 -m venv .venv 2>/dev/null; "
            ".venv/bin/pip install -e . -q 2>&1 | tail -1"
        )
        r = _ssh_cmd(host, user, setup_cmd, timeout=120)
        print(f"  ✅ Installed: {r.output}" if r.success else f"  ⚠️  Install: {r.error[:200]}")

        # 5. Create sym wrapper with PYTHONPATH
        wrapper = (
            "cat > /usr/local/bin/sym << 'WRAPPER'\n"
            "#!/bin/bash\n"
            "export PYTHONPATH=/opt/symbiont\n"
            "cd /opt/symbiont\n"
            '.venv/bin/python -m symbiont.cli "$@"\n'
            "WRAPPER\n"
            "chmod +x /usr/local/bin/sym"
        )
        _ssh_cmd(host, user, wrapper, timeout=10)
        print(f"  ✅ sym CLI installed at /usr/local/bin/sym")

        # 6. Test
        r = _ssh_cmd(host, user, "/usr/local/bin/sym status --backend echo", timeout=30)
        if r.success:
            print(f"  ✅ Colony {name} operational!")
        else:
            print(f"  ⚠️  Test run: {r.error[:200]}")

    # Save config
    _save_colonies(colonies)
    print(f"\n✅ Config saved to {COLONY_CONFIG}")


async def _colony_run(name: str, task: str, colonies: dict, backend: str):
    """Execute a task on a remote colony."""
    if name not in colonies:
        print(f"Unknown colony: {name}")
        return

    info = colonies[name]
    host, user = info["host"], info["user"]

    print(f"🏗️  Running on {name} ({host}):")
    print(f"   Task: {task}")
    print()

    # Escape task for shell
    escaped = task.replace("'", "'\\''")
    cmd = f"/usr/local/bin/sym '{escaped}' --backend {backend}"

    result = _ssh_cmd(host, user, cmd, timeout=300)
    if result.success:
        print(result.output)
    else:
        print(f"❌ Error: {result.error}")
        if result.output:
            print(result.output)
