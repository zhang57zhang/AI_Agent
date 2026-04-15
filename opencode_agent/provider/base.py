"""Abstract LLM provider interface.

All LLM providers implement this interface. The agent loop calls
the provider to get completions with streaming and tool-calling support.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from opencode_agent.base_types import (
    AgentEvent,
    AgentEventType,
    Message,
    MessageRole,
    TextContent,
    TokenUsage,
    ToolCall,
    ToolCallContent,
    ToolCallStatus,
)


@dataclass
class ProviderMessage:
    """Unified message format for all providers."""

    role: str  # "system", "user", "assistant", "tool"
    content: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_call_id: str | None = None  # for tool result messages
    name: str | None = None  # tool name for tool result messages


@dataclass
class ProviderTool:
    """Tool definition in provider format."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


class BaseProvider(ABC):
    """Abstract base for all LLM providers."""

    def __init__(
        self,
        model: str,
        api_key: str = "",
        base_url: str = "",
        max_tokens: int = 16384,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.extra = kwargs

    @abstractmethod
    async def chat(
        self,
        messages: list[ProviderMessage],
        tools: list[ProviderTool] | None = None,
        system_prompt: str = "",
        stream: bool = True,
    ) -> AsyncIterator[AgentEvent]:
        """Send messages to the LLM and stream back events.

        Yields AgentEvent objects:
        - RESPONSE: text content chunks
        - TOOL_CALL: when the model requests a tool invocation
        - THINKING: reasoning/thinking content (if supported)
        - DONE: final event with full message and token usage
        """
        ...

    def _make_text_event(self, text: str, session_id: str = "") -> AgentEvent:
        return AgentEvent(
            type=AgentEventType.RESPONSE,
            session_id=session_id,
            content=text,
        )

    def _make_tool_call_event(
        self, tool_call: ToolCall, session_id: str = ""
    ) -> AgentEvent:
        return AgentEvent(
            type=AgentEventType.TOOL_CALL,
            session_id=session_id,
            tool_name=tool_call.name,
            tool_call_id=tool_call.id,
            data={"input": tool_call.input},
        )

    def _make_done_event(
        self,
        message: Message,
        usage: TokenUsage | None = None,
        session_id: str = "",
    ) -> AgentEvent:
        return AgentEvent(
            type=AgentEventType.DONE,
            session_id=session_id,
            message=message,
            token_usage=usage,
        )

    def _make_error_event(self, error: str, session_id: str = "") -> AgentEvent:
        return AgentEvent(
            type=AgentEventType.ERROR,
            session_id=session_id,
            content=error,
        )