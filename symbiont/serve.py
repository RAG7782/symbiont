"""
SYMBIONT HTTP Bridge — connects external systems to the Mycelium.

Exposes a lightweight async HTTP server that:
- POST /webhook           → publishes event to a Mycelium channel
- POST /task              → executes a task through the organism
- GET  /status            → returns organism health
- GET  /channels          → lists active Mycelium channels

Zero external dependencies — uses stdlib aiohttp-like pattern with asyncio.

This is the bridge that lets Kestra, OpenClaw, and remote colonies
communicate with the SYMBIONT organism over HTTP.
"""

from __future__ import annotations

import asyncio
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any
from threading import Thread
from functools import partial

logger = logging.getLogger(__name__)

# Global reference to the running organism (set by serve())
_organism = None
_event_loop = None


class _WebhookHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the SYMBIONT bridge."""

    def log_message(self, format, *args):
        logger.info("http: %s", format % args)

    def _send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw)

    def _send_html(self, status: int, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # --- Routes ---

    def do_GET(self):
        if self.path == "/status":
            self._handle_status()
        elif self.path == "/channels":
            self._handle_channels()
        elif self.path == "/health":
            self._send_json(200, {"ok": True, "service": "symbiont"})
        elif self.path == "/dashboard" or self.path == "/":
            self._handle_dashboard()
        elif self.path == "/alerts":
            self._handle_alerts()
        elif self.path == "/metrics":
            self._handle_metrics()
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/webhook":
            self._handle_webhook()
        elif self.path == "/task":
            self._handle_task()
        else:
            self._send_json(404, {"error": "not found"})

    def _handle_status(self):
        if not _organism:
            self._send_json(503, {"error": "organism not running"})
            return
        status = _organism.status()
        self._send_json(200, _sanitize(status))

    def _handle_channels(self):
        if not _organism:
            self._send_json(503, {"error": "organism not running"})
            return
        channels = _organism.mycelium.get_active_channels()
        topology = _organism.mycelium.query_topology()
        self._send_json(200, {"channels": channels, "topology": _sanitize(topology)})

    def _handle_dashboard(self):
        from symbiont.dashboard import get_dashboard_html
        self._send_html(200, get_dashboard_html())

    def _handle_alerts(self):
        from symbiont.alerts import get_alert_state
        self._send_json(200, get_alert_state())

    def _handle_metrics(self):
        """Return enriched metrics: organism + colonies + mycelium."""
        if not _organism:
            self._send_json(503, {"error": "organism not running"})
            return

        # Colony status (cached from alert loop)
        from symbiont.alerts import _state as alert_state
        from symbiont.colony import _load_colonies
        colonies_config = _load_colonies()
        colony_metrics = {}
        for name, info in colonies_config.items():
            failures = alert_state.consecutive_failures.get(name, 0)
            colony_metrics[name] = {
                "host": info.get("host", ""),
                "alive": failures == 0,
                "consecutive_failures": failures,
                "description": info.get("description", ""),
            }

        # Mycelium metrics
        topology = _organism.mycelium.query_topology()
        recent = _organism.mycelium.recent_messages

        self._send_json(200, {
            "colonies": colony_metrics,
            "topology": _sanitize(topology),
            "recent_messages": len(recent),
            "organism": _sanitize(_organism.status()),
        })

    def _handle_webhook(self):
        """Receive an external event and publish to a Mycelium channel."""
        if not _organism or not _event_loop:
            self._send_json(503, {"error": "organism not running"})
            return

        body = self._read_body()
        channel = body.get("channel", "external.webhook")
        payload = body.get("payload", body)
        sender = body.get("sender", "kestra")
        priority = body.get("priority", 5)

        future = asyncio.run_coroutine_threadsafe(
            _organism.mycelium.publish(
                channel=channel,
                payload=payload,
                sender_id=sender,
                priority=priority,
                metadata={"source": "http-bridge", "sender": sender},
            ),
            _event_loop,
        )

        try:
            msg = future.result(timeout=10)
            self._send_json(200, {
                "ok": True,
                "message_id": msg.id,
                "channel": channel,
            })
        except Exception as e:
            logger.exception("webhook publish failed")
            self._send_json(500, {"error": str(e)})

    def _handle_task(self):
        """Execute a full task through the organism."""
        if not _organism or not _event_loop:
            self._send_json(503, {"error": "organism not running"})
            return

        body = self._read_body()
        task = body.get("task", "")
        context = body.get("context", {})

        if not task:
            self._send_json(400, {"error": "missing 'task' field"})
            return

        future = asyncio.run_coroutine_threadsafe(
            _organism.execute(task=task, context=context),
            _event_loop,
        )

        try:
            result = future.result(timeout=120)
            self._send_json(200, {"ok": True, "result": _sanitize(result)})
        except Exception as e:
            logger.exception("task execution failed")
            self._send_json(500, {"error": str(e)})


def _sanitize(obj: Any) -> Any:
    """Make an object JSON-serializable."""
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(i) for i in obj]
    if isinstance(obj, set):
        return list(obj)
    if hasattr(obj, "name") and isinstance(obj, type(obj)):
        return obj.name if hasattr(obj, "name") else str(obj)
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


async def serve(host: str = "0.0.0.0", port: int = 7777, backend_name: str = "ollama", light: bool = False, verbose: bool = False):
    """
    Start the SYMBIONT HTTP bridge.

    Boots the organism, starts the HTTP server in a thread,
    and keeps the event loop running for async operations.
    """
    global _organism, _event_loop

    from symbiont import Symbiont

    if verbose:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)-20s] %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        logging.basicConfig(level=logging.WARNING)

    _event_loop = asyncio.get_running_loop()

    # Boot organism
    from symbiont.cli import make_backend
    organism = Symbiont()
    organism.set_llm_backend(make_backend(backend_name, light=light))

    print(f"🧬 SYMBIONT serve — booting ({backend_name})...")
    await organism.boot()
    _organism = organism
    print(f"   {organism.agent_count} agents online")

    # Start HTTP server in a thread
    server = HTTPServer((host, port), _WebhookHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print(f"🌐 HTTP bridge listening on http://{host}:{port}")
    print(f"   GET  /          — dashboard (web UI)")
    print(f"   POST /webhook   — publish to Mycelium")
    print(f"   POST /task      — execute task")
    print(f"   GET  /status    — organism health")
    print(f"   GET  /channels  — active channels")
    print(f"   GET  /metrics   — enriched metrics")
    print(f"   GET  /alerts    — alert state")
    print(f"   GET  /health    — liveness probe")
    print()

    # Start alert monitoring loop
    from symbiont.alerts import alert_loop
    alert_task = asyncio.create_task(alert_loop(bridge_port=0))  # bridge_port=0 skips self-check
    print("🔔 Alert monitoring active")

    # Keep alive until interrupted
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        alert_task.cancel()
        print("\n🧬 Shutting down...")
        server.shutdown()
        await organism.shutdown()
        _organism = None
        print("🧬 SYMBIONT serve stopped.")
