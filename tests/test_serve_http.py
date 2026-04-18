"""Tests for the SYMBIONT HTTP bridge (_WebhookHandler routes)."""

from __future__ import annotations

import asyncio
import json
from io import BytesIO
from threading import Thread
from http.server import HTTPServer
from unittest.mock import AsyncMock, MagicMock, patch
import urllib.request
import urllib.error

import pytest

import symbiont.serve as serve_mod
from symbiont.serve import _WebhookHandler, _sanitize


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_handler(path: str, method: str = "GET", body: bytes = b"") -> _WebhookHandler:
    """
    Construct a _WebhookHandler without a real socket.
    Captures response in a BytesIO buffer.
    """
    handler = object.__new__(_WebhookHandler)
    handler.path = path
    handler.command = method
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = BytesIO(body)
    buf = BytesIO()
    handler.wfile = buf
    handler.server = MagicMock()
    handler._buf = buf
    return handler

def _response_json(handler: _WebhookHandler) -> tuple[int, dict]:
    """Parse status code + JSON from buffer written by handler."""
    raw = handler._buf.getvalue().decode("utf-8", errors="replace")
    # HTTP/1.0 200 OK\r\n...\r\n\r\n{json}
    lines = raw.split("\r\n")
    status_line = lines[0]
    status_code = int(status_line.split()[1])
    # body is after the blank line
    body_start = raw.find("\r\n\r\n") + 4
    body = raw[body_start:]
    return status_code, json.loads(body) if body.strip() else {}


class _FakeHTTP:
    """Minimal send_response/send_header/end_headers implementation."""
    def __init__(self, handler):
        self._handler = handler
        self._handler.wfile = BytesIO()

    def __enter__(self):
        h = self._handler
        h.send_response = lambda code, msg=None: h.wfile.write(f"HTTP/1.0 {code} OK\r\n".encode())
        h.send_header = lambda k, v: h.wfile.write(f"{k}: {v}\r\n".encode())
        h.end_headers = lambda: h.wfile.write(b"\r\n")
        return h

    def __exit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# _sanitize (already in test_serve.py but we cover extra branches here)
# ---------------------------------------------------------------------------

class TestSanitizeExtra:
    def test_tuple_becomes_list(self):
        assert _sanitize((1, 2, 3)) == [1, 2, 3]

    def test_nested_set_in_dict(self):
        result = _sanitize({"s": {1, 2}})
        assert isinstance(result["s"], list)

    def test_deeply_nested(self):
        result = _sanitize({"a": {"b": {"c": [1, 2, {3}]}}})
        assert isinstance(result["a"]["b"]["c"][2], list)


# ---------------------------------------------------------------------------
# Route tests via a real ephemeral HTTPServer
# ---------------------------------------------------------------------------

def _start_test_server(host="127.0.0.1", port=0):
    """Start an HTTPServer on a random port, return (server, thread, port)."""
    server = HTTPServer((host, port), _WebhookHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, port


def _get(port, path):
    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(port, path, data: dict):
    url = f"http://127.0.0.1:{port}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body,
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.fixture(scope="module")
def test_server():
    """Ephemeral server for the whole module."""
    # Reset global state
    serve_mod._organism = None
    serve_mod._event_loop = None
    serve_mod._federation = None
    serve_mod._store = None

    server, thread, port = _start_test_server()
    yield port
    server.shutdown()


class TestHealthRoute:
    def test_health_returns_200(self, test_server):
        status, body = _get(test_server, "/health")
        assert status == 200
        assert body["ok"] is True
        assert body["service"] == "symbiont"


class TestNotFound:
    def test_unknown_get_returns_404(self, test_server):
        status, body = _get(test_server, "/nonexistent")
        assert status == 404
        assert "error" in body

    def test_unknown_post_returns_404(self, test_server):
        status, body = _post(test_server, "/nonexistent", {})
        assert status == 404


class TestStatusWithoutOrganism:
    def test_status_503_no_organism(self, test_server):
        serve_mod._organism = None
        status, body = _get(test_server, "/status")
        assert status == 503
        assert "error" in body

    def test_channels_503_no_organism(self, test_server):
        serve_mod._organism = None
        status, body = _get(test_server, "/channels")
        assert status == 503

    def test_metrics_503_no_organism(self, test_server):
        serve_mod._organism = None
        status, body = _get(test_server, "/metrics")
        assert status == 503

    def test_webhook_503_no_organism(self, test_server):
        serve_mod._organism = None
        serve_mod._event_loop = None
        status, body = _post(test_server, "/webhook", {"channel": "test", "payload": {}})
        assert status == 503

    def test_task_503_no_organism(self, test_server):
        serve_mod._organism = None
        serve_mod._event_loop = None
        status, body = _post(test_server, "/task", {"task": "hello"})
        assert status == 503


class TestTaskValidation:
    def test_task_400_missing_task_field(self, test_server):
        # Provide a fake organism+loop so it passes the 503 check
        mock_org = MagicMock()
        mock_loop = MagicMock()
        serve_mod._organism = mock_org
        serve_mod._event_loop = mock_loop
        status, body = _post(test_server, "/task", {})
        assert status == 400
        assert "missing" in body.get("error", "").lower()
        serve_mod._organism = None
        serve_mod._event_loop = None


class TestFederationWithoutFederation:
    def test_heartbeat_503_no_federation(self, test_server):
        serve_mod._federation = None
        status, body = _post(test_server, "/federation/heartbeat", {})
        assert status == 503

    def test_register_503_no_federation(self, test_server):
        serve_mod._federation = None
        status, body = _post(test_server, "/federation/register", {})
        assert status == 503


class TestStatusWithOrganism:
    def test_status_200_with_mock_organism(self, test_server):
        mock_org = MagicMock()
        mock_org.status.return_value = {"agents": 3, "running": True}
        serve_mod._organism = mock_org

        status, body = _get(test_server, "/status")
        assert status == 200
        assert "agents" in body
        serve_mod._organism = None

    def test_channels_200_with_mock_organism(self, test_server):
        mock_org = MagicMock()
        mock_org.mycelium.get_active_channels.return_value = ["ch1", "ch2"]
        mock_org.mycelium.query_topology.return_value = {}
        serve_mod._organism = mock_org

        status, body = _get(test_server, "/channels")
        assert status == 200
        assert "channels" in body
        serve_mod._organism = None


class TestWebhookWithOrganism:
    def test_webhook_publishes_and_returns_message_id(self, test_server):
        loop = asyncio.new_event_loop()

        mock_msg = MagicMock()
        mock_msg.id = "msg-abc123"

        mock_org = MagicMock()
        mock_org.mycelium.publish = AsyncMock(return_value=mock_msg)

        future = loop.create_future()
        future.set_result(mock_msg)

        serve_mod._organism = mock_org
        serve_mod._event_loop = loop

        with patch("asyncio.run_coroutine_threadsafe") as mock_rct:
            mock_rct.return_value.result.return_value = mock_msg
            status, body = _post(test_server, "/webhook",
                                  {"channel": "test.ch", "payload": {"x": 1}})

        assert status == 200
        assert body["ok"] is True
        assert body["channel"] == "test.ch"

        serve_mod._organism = None
        serve_mod._event_loop = None
        loop.close()
