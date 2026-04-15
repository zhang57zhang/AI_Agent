"""Tool system: base interface, built-in tools, and MCP integration."""

from opencode_agent.tools.base import BaseTool, ToolContext, get_tool, register_tool
from opencode_agent.tools.file_tools import get_file_tools
from opencode_agent.tools.bash_tool import BashTool
from opencode_agent.tools.web_tools import get_web_tools
from opencode_agent.tools.git_tools import get_git_tools
from opencode_agent.tools.mcp_tools import discover_mcp_tools


def coder_agent_tools() -> list[BaseTool]:
    """Full tool set for the Coder agent (read + write + bash + git + web)."""
    return [
        *get_file_tools(),
        BashTool(),
        *get_git_tools(),
        *get_web_tools(),
    ]


def task_agent_tools() -> list[BaseTool]:
    """Read-only tool set for the Task agent (exploration/analysis only)."""
    # Only non-destructive file tools
    from opencode_agent.tools.file_tools import (
        ReadFileTool,
        GlobTool,
        GrepTool,
        ListDirectoryTool,
    )
    from opencode_agent.tools.web_tools import WebFetchTool, WebSearchTool

    return [
        ReadFileTool(),
        GlobTool(),
        GrepTool(),
        ListDirectoryTool(),
        WebFetchTool(),
        WebSearchTool(),
    ]


async def all_tools_with_mcp() -> list[BaseTool]:
    """Get all built-in tools plus dynamically discovered MCP tools."""
    from opencode_agent.tools.mcp_tools import MCPToolWrapper

    tools = coder_agent_tools()
    try:
        mcp_tools = await discover_mcp_tools()
        tools.extend(mcp_tools)
    except Exception:
        pass  # MCP is optional
    return tools


__all__ = [
    "BaseTool",
    "ToolContext",
    "coder_agent_tools",
    "task_agent_tools",
    "all_tools_with_mcp",
    "discover_mcp_tools",
    "get_file_tools",
    "get_web_tools",
    "get_git_tools",
]