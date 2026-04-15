"""Base tool interface and registry.

Every tool in the system implements BaseTool. The agent loop calls
Info() to build the function-calling schema for the LLM, then Run()
to execute when the LLM requests a tool call.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from opencode_agent.base_types import ToolCall, ToolCallStatus, ToolInfo, ToolResponse


class BaseTool(ABC):
    """Abstract base class for all tools.

    Every tool must implement:
    - Info(): returns metadata (name, description, parameter schema)
    - Run(): executes the tool given a ToolCall
    """

    @abstractmethod
    def info(self) -> ToolInfo:
        """Return tool metadata for schema generation."""
        ...

    @abstractmethod
    async def run(self, ctx: "ToolContext", params: ToolCall) -> ToolResponse:
        """Execute the tool. Must be async for I/O operations."""
        ...

    # --- Optional overrides ---

    def check_permission(self, ctx: "ToolContext", params: ToolCall) -> bool:
        """Override to add custom permission checks. Default: auto-approve read-only tools."""
        return True


class ToolContext:
    """Execution context passed to every tool run.

    Provides access to session state, working directory,
    permission service, and other runtime information.
    """

    def __init__(
        self,
        session_id: str = "",
        working_dir: str = "",
        permissions: Any = None,  # PermissionService — avoid circular import
    ) -> None:
        self.session_id = session_id
        self.working_dir = working_dir or "."
        self.permissions = permissions


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

_tool_registry: dict[str, type[BaseTool]] = {}


def register_tool(tool_class: type[BaseTool]) -> type[BaseTool]:
    """Decorator to register a tool class by name."""
    instance = tool_class()
    _tool_registry[instance.info().name] = tool_class
    return tool_class


def get_all_tools() -> dict[str, type[BaseTool]]:
    """Return all registered tool classes."""
    return dict(_tool_registry)


def get_tool(name: str) -> type[BaseTool] | None:
    """Get a registered tool by name."""
    return _tool_registry.get(name)