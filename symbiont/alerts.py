"""
SYMBIONT Alerts — monitors health and sends notifications.

Supports Telegram and webhook notifications.
Runs as a background task inside `sym serve` or standalone.

Configuration via environment variables:
    TELEGRAM_BOT_TOKEN  — Telegram bot token
    TELEGRAM_CHAT_ID    — Telegram chat ID to send alerts to
    SYMBIONT_ALERT_WEBHOOK — Optional HTTP webhook for alerts
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ALERT_WEBHOOK = os.environ.get("SYMBIONT_ALERT_WEBHOOK", "")

# Alert config
CHECK_INTERVAL = 60  # seconds between checks
COLONY_TIMEOUT = 15  # seconds SSH timeout
BRIDGE_TIMEOUT = 5   # seconds HTTP timeout


@dataclass
class AlertState:
    """Tracks what was already alerted to avoid spam."""
    colony_down: dict[str, float] = field(default_factory=dict)  # name → timestamp
    bridge_down: float = 0.0
    last_check: float = 0.0
    consecutive_failures: dict[str, int] = field(default_factory=dict)


_state = AlertState()


def _send_telegram(message: str) -> bool:
    """Send a message via Telegram bot API. Returns True on success."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.debug("alerts: telegram not configured (missing token or chat_id)")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        logger.warning("alerts: telegram send failed: %s", e)
        return False


def _send_webhook(event: dict) -> bool:
    """Send alert to a webhook URL."""
    if not ALERT_WEBHOOK:
        return False

    data = json.dumps(event).encode("utf-8")
    req = urllib.request.Request(
        ALERT_WEBHOOK, data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def send_alert(title: str, message: str, level: str = "warning", data: dict | None = None):
    """Send an alert via all configured channels."""
    emoji = {"critical": "🔴", "warning": "🟡", "info": "🟢", "recovery": "💚"}.get(level, "⚪")
    full_msg = f"{emoji} *SYMBIONT Alert*\n*{title}*\n{message}"

    _send_telegram(full_msg)
    _send_webhook({
        "title": title,
        "message": message,
        "level": level,
        "timestamp": time.time(),
        "data": data or {},
    })

    logger.info("alert [%s]: %s — %s", level, title, message)


def _check_colony(name: str, host: str, user: str) -> bool:
    """Check if a colony is reachable via SSH."""
    try:
        result = subprocess.run(
            ["ssh", "-o", f"ConnectTimeout={COLONY_TIMEOUT}", "-o", "StrictHostKeyChecking=no",
             f"{user}@{host}", "echo ok"],
            capture_output=True, text=True, timeout=COLONY_TIMEOUT + 5,
        )
        return result.returncode == 0 and "ok" in result.stdout
    except Exception:
        return False


def _check_bridge(port: int = 7777) -> bool:
    """Check if the HTTP bridge is responding."""
    try:
        req = urllib.request.Request(f"http://localhost:{port}/health")
        with urllib.request.urlopen(req, timeout=BRIDGE_TIMEOUT) as resp:
            data = json.loads(resp.read())
            return data.get("ok", False)
    except Exception:
        return False


async def check_health(colonies: dict | None = None, bridge_port: int = 7777):
    """Run one health check cycle. Call periodically."""
    now = time.time()
    _state.last_check = now

    # Check colonies
    if colonies:
        for name, info in colonies.items():
            host = info.get("host", "")
            user = info.get("user", "root")
            alive = _check_colony(name, host, user)

            if not alive:
                failures = _state.consecutive_failures.get(name, 0) + 1
                _state.consecutive_failures[name] = failures

                # Alert on 2nd consecutive failure (avoid flapping)
                if failures == 2 and name not in _state.colony_down:
                    _state.colony_down[name] = now
                    send_alert(
                        f"Colony {name} DOWN",
                        f"Colony `{name}` ({host}) is unreachable.\n"
                        f"Failed {failures} consecutive checks.",
                        level="critical",
                        data={"colony": name, "host": host},
                    )
            else:
                _state.consecutive_failures[name] = 0
                if name in _state.colony_down:
                    downtime = now - _state.colony_down[name]
                    del _state.colony_down[name]
                    send_alert(
                        f"Colony {name} RECOVERED",
                        f"Colony `{name}` ({host}) is back online.\n"
                        f"Was down for {downtime:.0f}s.",
                        level="recovery",
                        data={"colony": name, "host": host, "downtime_sec": downtime},
                    )

    # Check bridge (only if not running inside serve — avoid self-check)
    if bridge_port and not _check_bridge(bridge_port):
        failures = _state.consecutive_failures.get("bridge", 0) + 1
        _state.consecutive_failures["bridge"] = failures

        if failures == 2 and _state.bridge_down == 0:
            _state.bridge_down = now
            send_alert(
                "HTTP Bridge DOWN",
                f"SYMBIONT HTTP bridge on port {bridge_port} is not responding.",
                level="critical",
            )
    else:
        _state.consecutive_failures["bridge"] = 0
        if _state.bridge_down > 0:
            downtime = now - _state.bridge_down
            _state.bridge_down = 0
            send_alert(
                "HTTP Bridge RECOVERED",
                f"SYMBIONT HTTP bridge is back online.\nWas down for {downtime:.0f}s.",
                level="recovery",
            )


async def alert_loop(colonies: dict | None = None, bridge_port: int = 7777, interval: int = CHECK_INTERVAL):
    """Background loop that periodically checks health and sends alerts."""
    logger.info("alerts: starting monitor loop (interval=%ds)", interval)

    # Load colonies from config if not provided
    if colonies is None:
        from symbiont.colony import _load_colonies
        colonies = _load_colonies()

    while True:
        try:
            await check_health(colonies=colonies, bridge_port=bridge_port)
        except Exception:
            logger.exception("alerts: health check failed")
        await asyncio.sleep(interval)


def get_alert_state() -> dict:
    """Return current alert state for the dashboard."""
    return {
        "colonies_down": list(_state.colony_down.keys()),
        "bridge_down": _state.bridge_down > 0,
        "last_check": _state.last_check,
        "consecutive_failures": dict(_state.consecutive_failures),
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        "webhook_configured": bool(ALERT_WEBHOOK),
    }
