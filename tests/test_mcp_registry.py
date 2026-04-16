"""Tests for the MCP Registry (v0.4.1)."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pytest

from symbiont.mcp_registry import (
    MCPOAuthConfig,
    MCPRegistry,
    MCPServerConfig,
    MCPTool,
    _OAuthTokenManager,
    _resolve_env,
    get_mcp_registry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cfg_file(tmp_path):
    """Write a minimal config file and return its path."""
    path = tmp_path / "mcp_servers.json"
    path.write_text(json.dumps({"servers": {}}))
    return path


@pytest.fixture
def registry(cfg_file):
    return MCPRegistry(config_path=str(cfg_file))


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------

class TestConfigParsing:
    def test_server_config_from_dict_minimal(self):
        cfg = MCPServerConfig.from_dict("test", {"transport": "http", "url": "http://localhost"})
        assert cfg.name == "test"
        assert cfg.transport == "http"
        assert cfg.url == "http://localhost"
        assert cfg.enabled is True

    def test_server_config_disabled(self):
        cfg = MCPServerConfig.from_dict("off", {"enabled": False})
        assert not cfg.enabled

    def test_server_config_with_oauth(self):
        cfg = MCPServerConfig.from_dict("api", {
            "transport": "http",
            "url": "http://api.example.com/mcp",
            "oauth": {
                "token_endpoint": "http://api.example.com/token",
                "client_id": "$CLIENT_ID",
                "client_secret": "$CLIENT_SECRET",
            }
        })
        assert cfg.oauth is not None
        assert cfg.oauth.token_endpoint == "http://api.example.com/token"

    def test_resolve_env_expands_dollar_var(self, monkeypatch):
        monkeypatch.setenv("MY_SECRET", "abc123")
        assert _resolve_env("$MY_SECRET") == "abc123"
        assert _resolve_env("${MY_SECRET}") == "abc123"

    def test_resolve_env_plain_value(self):
        assert _resolve_env("plaintext") == "plaintext"

    def test_resolve_env_missing_var_returns_empty(self):
        result = _resolve_env("$DEFINITELY_NOT_SET_XYZ_12345")
        assert result == ""


# ---------------------------------------------------------------------------
# Registry initialization
# ---------------------------------------------------------------------------

class TestRegistry:
    @pytest.mark.asyncio
    async def test_loads_empty_config(self, registry):
        tools = await registry.get_tools()
        assert tools == []
        assert registry._initialized

    @pytest.mark.asyncio
    async def test_disabled_servers_skipped(self, cfg_file):
        cfg_file.write_text(json.dumps({"servers": {
            "disabled": {"transport": "http", "url": "http://localhost:9999", "enabled": False},
        }}))
        reg = MCPRegistry(config_path=str(cfg_file))
        tools = await reg.get_tools()
        assert tools == []

    @pytest.mark.asyncio
    async def test_missing_config_returns_empty(self, tmp_path):
        reg = MCPRegistry(config_path=str(tmp_path / "nonexistent.json"))
        tools = await reg.get_tools()
        assert tools == []
        assert reg._initialized

    @pytest.mark.asyncio
    async def test_invalid_json_does_not_crash(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{invalid json}")
        reg = MCPRegistry(config_path=str(bad))
        tools = await reg.get_tools()
        assert tools == []

    @pytest.mark.asyncio
    async def test_needs_reload_on_mtime_change(self, registry):
        await registry.get_tools()  # initializes
        assert not registry._needs_reload()

        # Simulate config file modification
        time.sleep(0.01)
        registry._config_path.touch()
        assert registry._needs_reload()

    @pytest.mark.asyncio
    async def test_forced_reload(self, registry):
        await registry.get_tools()
        assert registry._initialized
        await registry.reload()
        assert registry._initialized

    def test_summary_structure(self, registry):
        s = registry.summary()
        assert "tools" in s
        assert "servers" in s
        assert "config_path" in s
        assert "initialized" in s
        assert "watcher_active" in s

    @pytest.mark.asyncio
    async def test_env_var_override(self, tmp_path, monkeypatch):
        cfg = tmp_path / "override.json"
        cfg.write_text(json.dumps({"servers": {}}))
        monkeypatch.setenv("MCP_SERVERS_JSON", str(cfg))
        reg = MCPRegistry()
        assert str(reg._config_path) == str(cfg.resolve())

    @pytest.mark.asyncio
    async def test_watcher_starts_and_stops(self, registry):
        await registry.start_watcher(interval_sec=60)
        assert registry._watcher_task is not None
        assert not registry._watcher_task.done()
        # Idempotent
        await registry.start_watcher(interval_sec=60)
        task_ref = registry._watcher_task
        await registry.stop_watcher()
        assert task_ref.done()

    @pytest.mark.asyncio
    async def test_get_tool_by_name(self, registry):
        # Inject a mock tool directly
        registry._tools = [
            MCPTool(name="echo", description="echo tool", server_name="test",
                    input_schema={}, _call=None)
        ]
        tool = registry.get_tool("echo")
        assert tool is not None
        assert tool.name == "echo"

        missing = registry.get_tool("nonexistent")
        assert missing is None


# ---------------------------------------------------------------------------
# MCPTool callable
# ---------------------------------------------------------------------------

class TestMCPTool:
    @pytest.mark.asyncio
    async def test_tool_call_dispatches(self):
        called_with = {}

        async def mock_call(**kwargs):
            called_with.update(kwargs)
            return {"result": "ok"}

        tool = MCPTool(
            name="search",
            description="search docs",
            server_name="docs",
            input_schema={},
            _call=mock_call,
        )
        result = await tool(query="SYMBIONT", limit=5)
        assert called_with == {"query": "SYMBIONT", "limit": 5}
        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_tool_without_callable_raises(self):
        tool = MCPTool(name="broken", description="", server_name="srv", input_schema={})
        with pytest.raises(RuntimeError, match="no callable"):
            await tool()
