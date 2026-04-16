"""
SYMBIONT MCP Registry — dynamic MCP server discovery with OAuth support.

Agents discover tools from external MCP servers at runtime. Config file
changes are detected automatically (mtime-based staleness), and OAuth
tokens are refreshed transparently before they expire.

Post v0.4.1 additions:
  - Background config watcher: asyncio task polls mtime every 60 s and
    invalidates the cache proactively, so live servers appear without
    waiting for the next get_tools() call.
  - 12-factor env var override: MCP_SERVERS_JSON env var overrides the
    default config path at startup.
  - Parallel server discovery: all enabled servers are probed concurrently
    via asyncio.gather, with per-server error isolation.

Supported transports: stdio (local subprocess) | sse | http (remote)
Supported auth:       none | bearer header | OAuth2 client_credentials / refresh_token

Usage:
    from symbiont.mcp_registry import MCPRegistry, MCPServerConfig

    registry = MCPRegistry()               # respects MCP_SERVERS_JSON env var
    tools = await registry.get_tools()     # list[MCPTool]
    result = await tools[0](arg="value")   # direct call

    await registry.start_watcher()         # background auto-reload (optional)
    await registry.stop_watcher()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = "~/.symbiont/mcp_servers.json"


# ---------------------------------------------------------------------------
# Config schemas
# ---------------------------------------------------------------------------

@dataclass
class MCPOAuthConfig:
    """OAuth2 config for a single MCP server."""
    token_endpoint: str
    client_id: str
    client_secret: str
    grant_type: str = "client_credentials"
    scopes: list[str] = field(default_factory=list)
    access_token_field: str = "access_token"
    expires_in_field: str = "expires_in"
    refresh_token_field: str = "refresh_token"
    token_type_field: str = "token_type"

    @classmethod
    def from_dict(cls, d: dict) -> MCPOAuthConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""
    name: str
    enabled: bool = True
    transport: str = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    oauth: MCPOAuthConfig | None = None

    @classmethod
    def from_dict(cls, name: str, d: dict) -> MCPServerConfig:
        d = dict(d)
        oauth_raw = d.pop("oauth", None)
        obj = cls(name=name, **{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        if oauth_raw:
            obj.oauth = MCPOAuthConfig.from_dict(oauth_raw)
        return obj


# ---------------------------------------------------------------------------
# OAuth token manager
# ---------------------------------------------------------------------------

@dataclass
class _OAuthToken:
    access_token: str
    token_type: str
    expires_at: float
    refresh_token: str | None = None


class _OAuthTokenManager:
    """
    Manages OAuth2 token lifecycle for one MCP server.

    Proactively refreshes 1 hour before expiry.
    Double-checked locking prevents concurrent refresh storms.
    """

    _REFRESH_SKEW_SEC = 3600

    def __init__(self, config: MCPOAuthConfig) -> None:
        self._cfg = config
        self._token: _OAuthToken | None = None
        self._lock = asyncio.Lock()

    async def get_auth_headers(self) -> dict[str, str]:
        if not self._is_fresh():
            async with self._lock:
                if not self._is_fresh():
                    self._token = await self._fetch()
        return {"Authorization": f"{self._token.token_type} {self._token.access_token}"}

    def _is_fresh(self) -> bool:
        return bool(self._token and time.time() + self._REFRESH_SKEW_SEC < self._token.expires_at)

    async def _fetch(self) -> _OAuthToken:
        try:
            import aiohttp
        except ImportError as exc:
            raise RuntimeError("aiohttp required for MCP OAuth: pip install aiohttp") from exc

        data: dict[str, Any] = {
            "grant_type": self._cfg.grant_type,
            "client_id": _resolve_env(self._cfg.client_id),
            "client_secret": _resolve_env(self._cfg.client_secret),
        }
        if self._cfg.grant_type == "refresh_token" and self._token:
            data["refresh_token"] = self._token.refresh_token or ""
        if self._cfg.scopes:
            data["scope"] = " ".join(self._cfg.scopes)

        async with aiohttp.ClientSession() as session:
            async with session.post(self._cfg.token_endpoint, data=data) as resp:
                resp.raise_for_status()
                body = await resp.json()

        return _OAuthToken(
            access_token=body[self._cfg.access_token_field],
            token_type=body.get(self._cfg.token_type_field, "Bearer"),
            expires_at=time.time() + body.get(self._cfg.expires_in_field, 3600),
            refresh_token=body.get(self._cfg.refresh_token_field),
        )


# ---------------------------------------------------------------------------
# Tool descriptor
# ---------------------------------------------------------------------------

@dataclass
class MCPTool:
    """A discovered tool from an MCP server."""
    name: str
    description: str
    server_name: str
    input_schema: dict
    _call: Callable[..., Coroutine[Any, Any, Any]] = field(repr=False, default=None)

    async def __call__(self, **kwargs: Any) -> Any:
        if self._call is None:
            raise RuntimeError(f"MCPTool '{self.name}' has no callable attached")
        return await self._call(**kwargs)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class MCPRegistry:
    """
    Discovers tools from multiple MCP servers, with:
      - Lazy initialization on first get_tools()
      - mtime-based staleness detection on every call
      - Background watcher task for proactive cache invalidation
      - Parallel server discovery (asyncio.gather, per-server error isolation)
      - 12-factor env var override (MCP_SERVERS_JSON)

    Config file format (~/.symbiont/mcp_servers.json):
    {
      "servers": {
        "oxe_tools": {
          "transport": "http",
          "url": "http://localhost:8500/mcp",
          "enabled": true
        },
        "github": {
          "transport": "stdio",
          "command": "npx",
          "args": ["@modelcontextprotocol/server-github"],
          "env": {"GITHUB_TOKEN": "$GITHUB_TOKEN"},
          "enabled": true
        }
      }
    }
    """

    _WATCHER_INTERVAL_SEC = 60

    def __init__(self, config_path: str | None = None) -> None:
        raw_path = config_path or os.environ.get("MCP_SERVERS_JSON", _DEFAULT_CONFIG)
        self._config_path = Path(raw_path).expanduser().resolve()
        self._tools: list[MCPTool] = []
        self._initialized = False
        self._config_mtime: float = 0.0
        self._token_managers: dict[str, _OAuthTokenManager] = {}
        self._lock = asyncio.Lock()
        self._watcher_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_tools(self) -> list[MCPTool]:
        """Return all enabled tools, re-loading from disk if config changed."""
        async with self._lock:
            if self._needs_reload():
                await self._load()
        return list(self._tools)

    async def reload(self) -> None:
        """Force a full reload regardless of mtime."""
        async with self._lock:
            self._initialized = False
            await self._load()

    def get_tool(self, name: str) -> MCPTool | None:
        return next((t for t in self._tools if t.name == name), None)

    def summary(self) -> dict:
        return {
            "tools": len(self._tools),
            "servers": list({t.server_name for t in self._tools}),
            "config_path": str(self._config_path),
            "initialized": self._initialized,
            "watcher_active": self._watcher_task is not None and not self._watcher_task.done(),
        }

    # ------------------------------------------------------------------
    # Background config watcher — increment #4
    # ------------------------------------------------------------------

    async def start_watcher(self, interval_sec: int = _WATCHER_INTERVAL_SEC) -> None:
        """
        Start a background asyncio task that polls the config file for
        changes every `interval_sec` seconds and reloads proactively.

        Idempotent: calling multiple times is safe.
        """
        if self._watcher_task and not self._watcher_task.done():
            return
        self._watcher_task = asyncio.create_task(
            self._watch_loop(interval_sec), name="mcp_registry_watcher"
        )
        logger.info("mcp_registry: watcher started (interval=%ds)", interval_sec)

    async def stop_watcher(self) -> None:
        if self._watcher_task and not self._watcher_task.done():
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass
        self._watcher_task = None
        logger.info("mcp_registry: watcher stopped")

    async def _watch_loop(self, interval_sec: int) -> None:
        while True:
            await asyncio.sleep(interval_sec)
            try:
                async with self._lock:
                    if self._needs_reload():
                        logger.info("mcp_registry: config changed on disk — reloading")
                        await self._load()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("mcp_registry: watcher error: %s", exc)

    # ------------------------------------------------------------------
    # Internal load + parallel discovery
    # ------------------------------------------------------------------

    def _needs_reload(self) -> bool:
        if not self._initialized:
            return True
        if not self._config_path.exists():
            return False
        return self._config_path.stat().st_mtime != self._config_mtime

    async def _load(self) -> None:
        if not self._config_path.exists():
            logger.warning("mcp_registry: config not found at %s", self._config_path)
            self._initialized = True
            return

        try:
            raw = json.loads(self._config_path.read_text())
        except json.JSONDecodeError as exc:
            logger.error("mcp_registry: invalid JSON in %s: %s", self._config_path, exc)
            return

        self._config_mtime = self._config_path.stat().st_mtime
        servers_raw = raw.get("servers", {})

        # Build list of enabled server configs
        cfgs = [
            MCPServerConfig.from_dict(name, dict(srv))
            for name, srv in servers_raw.items()
        ]
        enabled = [c for c in cfgs if c.enabled]
        skipped = len(cfgs) - len(enabled)
        if skipped:
            logger.debug("mcp_registry: skipping %d disabled servers", skipped)

        # Discover all enabled servers in parallel
        results = await asyncio.gather(
            *[self._discover_server(cfg) for cfg in enabled],
            return_exceptions=True,
        )

        all_tools: list[MCPTool] = []
        for cfg, result in zip(enabled, results):
            if isinstance(result, Exception):
                logger.warning("mcp_registry: '%s' discovery failed: %s", cfg.name, result)
            else:
                all_tools.extend(result)
                logger.info("mcp_registry: %s → %d tools", cfg.name, len(result))

        self._tools = all_tools
        self._initialized = True
        logger.info(
            "mcp_registry: loaded %d tools from %d/%d servers",
            len(all_tools), len(enabled), len(cfgs),
        )

    async def _discover_server(self, cfg: MCPServerConfig) -> list[MCPTool]:
        headers = dict(cfg.headers)
        if cfg.oauth:
            if cfg.name not in self._token_managers:
                self._token_managers[cfg.name] = _OAuthTokenManager(cfg.oauth)
            headers.update(await self._token_managers[cfg.name].get_auth_headers())

        if cfg.transport == "stdio":
            return await self._discover_stdio(cfg)
        elif cfg.transport in ("sse", "http"):
            return await self._discover_http(cfg, headers)
        logger.warning("mcp_registry: unknown transport '%s' for '%s'", cfg.transport, cfg.name)
        return []

    async def _discover_http(self, cfg: MCPServerConfig, headers: dict) -> list[MCPTool]:
        try:
            import aiohttp
        except ImportError as exc:
            raise RuntimeError("aiohttp required: pip install aiohttp") from exc

        list_url = cfg.url.rstrip("/") + "/tools/list"
        async with aiohttp.ClientSession() as session:
            async with session.post(list_url, headers=headers, json={}) as resp:
                resp.raise_for_status()
                body = await resp.json()

        tools = []
        for t in body.get("tools", []):
            tool_name = t["name"]

            async def _call(server_cfg=cfg, name=tool_name, hdrs=headers, **kwargs: Any) -> Any:
                return await self._invoke_http(server_cfg, name, hdrs, kwargs)

            tools.append(MCPTool(
                name=tool_name,
                description=t.get("description", ""),
                server_name=cfg.name,
                input_schema=t.get("inputSchema", {}),
                _call=_call,
            ))
        return tools

    async def _invoke_http(
        self, cfg: MCPServerConfig, tool_name: str, headers: dict, arguments: dict
    ) -> Any:
        try:
            import aiohttp
        except ImportError as exc:
            raise RuntimeError("aiohttp required: pip install aiohttp") from exc

        if cfg.oauth and cfg.name in self._token_managers:
            headers = {**headers, **await self._token_managers[cfg.name].get_auth_headers()}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                cfg.url.rstrip("/") + "/tools/call",
                headers=headers,
                json={"name": tool_name, "arguments": arguments},
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def _discover_stdio(self, cfg: MCPServerConfig) -> list[MCPTool]:
        if not cfg.command:
            logger.warning("mcp_registry: stdio server '%s' has no command", cfg.name)
            return []

        env = {**os.environ, **{k: _resolve_env(v) for k, v in cfg.env.items()}}
        cmd = [cfg.command] + cfg.args

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError:
            logger.warning("mcp_registry: command not found for '%s': %s", cfg.name, cfg.command)
            return []

        init_req = _jsonrpc("initialize", 1, {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "symbiont", "version": "0.4.0"},
        })
        list_req = _jsonrpc("tools/list", 2, {})

        try:
            proc.stdin.write(init_req.encode())
            proc.stdin.write(list_req.encode())
            await proc.stdin.drain()
            proc.stdin.close()
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        except asyncio.TimeoutError:
            proc.kill()
            logger.warning("mcp_registry: timeout discovering stdio server '%s'", cfg.name)
            return []

        tools = []
        for line in stdout.decode().splitlines():
            try:
                msg = json.loads(line)
                if msg.get("id") == 2:
                    for t in msg.get("result", {}).get("tools", []):
                        tool_name = t["name"]

                        async def _call(
                            server_cfg=cfg, name=tool_name, env_=env, **kwargs: Any
                        ) -> Any:
                            return await self._invoke_stdio(server_cfg, name, env_, kwargs)

                        tools.append(MCPTool(
                            name=tool_name,
                            description=t.get("description", ""),
                            server_name=cfg.name,
                            input_schema=t.get("inputSchema", {}),
                            _call=_call,
                        ))
            except (json.JSONDecodeError, KeyError):
                continue
        return tools

    async def _invoke_stdio(
        self, cfg: MCPServerConfig, tool_name: str, env: dict, arguments: dict
    ) -> Any:
        cmd = [cfg.command] + cfg.args
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
        )
        proc.stdin.write(_jsonrpc("initialize", 0, {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "symbiont", "version": "0.4.0"},
        }).encode())
        proc.stdin.write(_jsonrpc("tools/call", 1, {
            "name": tool_name, "arguments": arguments,
        }).encode())
        await proc.stdin.drain()
        proc.stdin.close()

        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            return {"error": f"timeout calling {tool_name}"}

        for line in stdout.decode().splitlines():
            try:
                msg = json.loads(line)
                if msg.get("id") == 1:
                    return msg.get("result", {})
            except json.JSONDecodeError:
                continue
        return {"error": "no response"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_env(value: str) -> str:
    if value.startswith("$"):
        key = value.lstrip("$").strip("{}")
        return os.environ.get(key, "")
    return value


def _jsonrpc(method: str, id_: int, params: dict) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": id_, "method": method, "params": params}) + "\n"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: MCPRegistry | None = None


def get_mcp_registry(config_path: str | None = None) -> MCPRegistry:
    """Return (or create) the module-level MCPRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = MCPRegistry(config_path=config_path)
    return _registry
