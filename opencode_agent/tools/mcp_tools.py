"""MCP (Model Context Protocol) tool integration.

Dynamically discovers and wraps MCP server tools as BaseTool instances.
MCP tools are loaded from configuration at startup and cached.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from opencode_agent.base_types import ToolCall, ToolInfo, ToolResponse
from opencode_agent.config import MCPServer, MCPServer, get_config
from opencode_agent.tools.base import BaseTool, ToolContext

logger = logging.getLogger("opencode_agent.tools.mcp")


class MCPToolWrapper(BaseTool):
    """Wraps an MCP tool as a BaseTool."""

    def __init__(self, server_name: str, tool_name: str, description: str, input_schema: dict[str, Any]) -> None:
        self._server_name = server_name
        self._tool_name = tool_name
        self._description = description
        self._input_schema = input_schema
        self._full_name = f"mcp__{server_name}__{tool_name}"
        self._client: Any = None  # MCP client, set after connection

    def set_client(self, client: Any) -> None:
        self._client = client

    @property
    def server_name(self) -> str:
        return self._server_name

    def info(self) -> ToolInfo:
        return ToolInfo(
            name=self._full_name,
            description=f"[MCP:{self._server_name}] {self._description}",
            parameters=self._input_schema.get("properties", {}),
            required=self._input_schema.get("required", []),
        )

    async def run(self, ctx: ToolContext, params: ToolCall) -> ToolResponse:
        if self._client is None:
            return ToolResponse.error(f"MCP client not connected: {self._server_name}")

        try:
            data = json.loads(params.input) if isinstance(params.input, str) else params.input
        except (json.JSONDecodeError, TypeError):
            return ToolResponse.error(f"Invalid JSON parameters: {params.input}")

        try:
            result = await self._client.call_tool(self._tool_name, data)
            # MCP result format: list of content blocks
            if isinstance(result, dict):
                content = result.get("content", [])
                text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                is_error = result.get("isError", False)
                return ToolResponse(
                    content="\n".join(text_parts),
                    is_error=is_error,
                )
            elif isinstance(result, str):
                return ToolResponse.text(result)
            else:
                return ToolResponse.json_response({"result": str(result)})
        except Exception as e:
            return ToolResponse.error(f"MCP tool error ({self._full_name}): {e}")


async def discover_mcp_tools(configs: list[MCPServer] | None = None) -> list[MCPToolWrapper]:
    """Connect to MCP servers and discover their tools.

    Returns wrapped tools ready for use in the agent loop.
    """
    if configs is None:
        cfg = get_config()
        if not cfg.enable_mcp:
            return []
        configs = cfg.mcp_servers

    if not configs:
        return []

    tools: list[MCPToolWrapper] = []

    for server_config in configs:
        try:
            client = await _connect_mcp_server(server_config)
            if client is None:
                logger.warning("Failed to connect to MCP server: %s", server_config.name)
                continue

            # List available tools
            tool_list = await client.list_tools()
            for tool in tool_list:
                wrapper = MCPToolWrapper(
                    server_name=server_config.name,
                    tool_name=tool.get("name", ""),
                    description=tool.get("description", ""),
                    input_schema=tool.get("inputSchema", {}),
                )
                wrapper.set_client(client)
                tools.append(wrapper)
                logger.info("Discovered MCP tool: %s", wrapper._full_name)

        except Exception as e:
            logger.warning("Error discovering MCP tools from %s: %s", server_config.name, e)

    return tools


async def _connect_mcp_server(config: MCPServer) -> Any:
    """Connect to an MCP server (stdio or SSE).

    Returns the MCP client or None on failure.
    """
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        if config.type.value == "stdio":
            if not config.command:
                logger.error("MCP stdio server %s missing command", config.name)
                return None

            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env if config.env else None,
            )

            # Connect and initialize
            read_stream, write_stream = await stdio_client(server_params).__aenter__()
            session = ClientSession(read_stream, write_stream)
            await session.__aenter__()
            await session.initialize()

            # Wrap session to provide list_tools and call_tool
            return _MCPClientAdapter(session)

        elif config.type.value == "sse":
            # SSE transport (future: implement when needed)
            logger.warning("SSE MCP transport not yet implemented for %s", config.name)
            return None

    except ImportError:
        logger.warning("MCP SDK not installed. Install with: pip install mcp")
        return None
    except Exception as e:
        logger.warning("Failed to connect to MCP server %s: %s", config.name, e)
        return None


class _MCPClientAdapter:
    """Adapter to make MCP ClientSession look like a simple tool client."""

    def __init__(self, session: Any) -> None:
        self._session = session

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self._session.list_tools()
        return [
            {
                "name": t.name,
                "description": t.description or "",
                "inputSchema": t.inputSchema,
            }
            for t in result.tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await self._session.call_tool(name, arguments=arguments)
        return {
            "content": [
                {"type": "text", "text": c.text} if hasattr(c, "text") else {"type": "text", "text": str(c)}
                for c in result.content
            ],
            "isError": result.isError if hasattr(result, "isError") else False,
        }