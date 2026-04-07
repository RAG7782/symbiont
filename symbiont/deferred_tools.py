"""
Deferred Tool Loading — caste-specific tool visibility.

Inspired by Claude Code's ToolSearch deferred loading pattern:
instead of loading 200+ tools into every agent's prompt, each
caste only "knows" about tools relevant to its role.

This reduces system prompt tokens (~30% savings) and enforces
the principle that Scouts don't write, Minima don't decide,
and Majors don't do routine work.

Tool categories per caste:
- SCOUT:  read-only (grep, glob, read, git log)
- MEDIA:  read + write (edit, write, bash, tools)
- MAJOR:  coordination (agent, plan, decision)
- QUEEN:  lifecycle (spawn, hibernate, terminate)
- MINIMA: utility (format, transform, data prep)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from symbiont.types import Caste

logger = logging.getLogger(__name__)


# Default tool visibility per caste
CASTE_TOOL_PROFILES: dict[Caste, set[str]] = {
    Caste.SCOUT: {
        "read", "grep", "glob", "search",
        "git_log", "git_status", "git_diff",
        "analyze", "explore",
    },
    Caste.MEDIA: {
        "read", "grep", "glob", "search",
        "edit", "write", "bash", "test",
        "git_add", "git_commit",
        "tools",  # CLI Anything harnesses
    },
    Caste.MAJOR: {
        "read", "grep", "glob",
        "plan", "decide", "delegate",
        "review", "validate",
    },
    Caste.QUEEN: {
        "spawn", "hibernate", "terminate",
        "status", "health",
    },
    Caste.MINIMA: {
        "read", "format", "transform",
        "data_prep", "summarize",
    },
}


@dataclass
class DeferredTool:
    """A tool that can be loaded on demand."""
    name: str
    description: str
    category: str  # read, write, coordinate, lifecycle, utility
    loaded: bool = False


class DeferredToolLoader:
    """
    Manages tool visibility per caste with on-demand loading.

    Agents start with only their caste's default tools visible.
    Additional tools can be requested and loaded if governance approves.
    """

    def __init__(self) -> None:
        self._tools: dict[str, DeferredTool] = {}
        self._caste_tools: dict[Caste, set[str]] = {
            c: set(tools) for c, tools in CASTE_TOOL_PROFILES.items()
        }
        self._loaded_by_agent: dict[str, set[str]] = {}  # agent_id → loaded tools
        self._request_log: list[dict] = []

    def register_tool(self, name: str, description: str, category: str) -> None:
        """Register a tool in the system."""
        self._tools[name] = DeferredTool(name=name, description=description, category=category)

    def get_visible_tools(self, caste: Caste) -> set[str]:
        """Get the set of tools visible to a caste (default profile)."""
        return self._caste_tools.get(caste, set())

    def get_loaded_tools(self, agent_id: str) -> set[str]:
        """Get tools loaded for a specific agent."""
        return self._loaded_by_agent.get(agent_id, set())

    def is_visible(self, tool_name: str, caste: Caste) -> bool:
        """Check if a tool is visible to a caste."""
        return tool_name in self._caste_tools.get(caste, set())

    def request_tool(self, agent_id: str, caste: Caste, tool_name: str) -> bool:
        """
        Request a tool not in the default profile.
        Returns True if approved (tool exists and request is reasonable).
        """
        self._request_log.append({
            "agent_id": agent_id,
            "caste": caste.name,
            "tool": tool_name,
        })

        if tool_name not in self._tools:
            logger.warning("deferred-tools: '%s' requested unknown tool '%s'", agent_id, tool_name)
            return False

        # Load the tool for this agent
        if agent_id not in self._loaded_by_agent:
            self._loaded_by_agent[agent_id] = set()
        self._loaded_by_agent[agent_id].add(tool_name)

        logger.info("deferred-tools: loaded '%s' for agent '%s' (%s)", tool_name, agent_id, caste.name)
        return True

    def build_tool_prompt(self, caste: Caste, agent_id: str | None = None) -> str:
        """
        Build the tool section for an agent's system prompt.
        Only includes visible + loaded tools (not all tools).
        """
        visible = self.get_visible_tools(caste)
        loaded = self.get_loaded_tools(agent_id) if agent_id else set()
        all_tools = visible | loaded

        if not all_tools:
            return "No tools available."

        parts = [f"## Available Tools ({len(all_tools)})"]
        for tool_name in sorted(all_tools):
            tool = self._tools.get(tool_name)
            if tool:
                parts.append(f"- **{tool.name}**: {tool.description}")
            else:
                parts.append(f"- **{tool_name}**")

        return "\n".join(parts)

    def summary(self) -> dict:
        return {
            "registered_tools": len(self._tools),
            "profiles": {c.name: len(t) for c, t in self._caste_tools.items()},
            "agents_with_extra_tools": len(self._loaded_by_agent),
            "total_requests": len(self._request_log),
        }
