"""Core data types for the agent system.

Defines the fundamental data structures that flow through the entire system:
- ToolCall / ToolResponse: tool execution contract
- Message / ContentPart: conversation messages
- AgentEvent: streaming events from the agent loop
- Session: conversation session state
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Tool System Types
# ---------------------------------------------------------------------------


class ToolCallStatus(str, Enum):
    """Status of a tool call within an execution cycle."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ToolInfo:
    """Metadata describing a tool's interface.

    This is what gets sent to the LLM as part of the system prompt /
    function-calling schema.
    """

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for parameters
    required: list[str] = field(default_factory=list)


@dataclass
class ToolCall:
    """A request to execute a tool."""

    id: str  # unique identifier for this call
    name: str  # tool name (matches ToolInfo.name)
    input: str  # JSON-encoded parameters
    status: ToolCallStatus = ToolCallStatus.PENDING


@dataclass
class ToolResponse:
    """Result of a tool execution."""

    content: str  # text output (may be large — file contents, command output, etc.)
    is_error: bool = False
    attachments: list[Attachment] = field(default_factory=list)

    @classmethod
    def text(cls, content: str) -> ToolResponse:
        """Create a successful text response."""
        return cls(content=content, is_error=False)

    @classmethod
    def error(cls, message: str) -> ToolResponse:
        """Create an error response."""
        return cls(content=message, is_error=True)

    @classmethod
    def json_response(cls, data: dict[str, Any]) -> ToolResponse:
        """Create a response from a dict (auto-serialized to JSON)."""
        import json

        return cls(content=json.dumps(data, ensure_ascii=False, indent=2), is_error=False)


# ---------------------------------------------------------------------------
# Content Parts (Message building blocks)
# ---------------------------------------------------------------------------


@dataclass
class Attachment:
    """Binary or rich attachment (image, PDF, etc.)."""

    content_type: str  # MIME type, e.g., "image/png"
    data: bytes | None = None
    url: str | None = None  # alternative: reference by URL
    filename: str | None = None


@dataclass
class TextContent:
    """Plain-text content block."""

    text: str


@dataclass
class ToolCallContent:
    """A tool invocation embedded in a message."""

    tool_call: ToolCall
    tool_response: ToolResponse | None = None  # filled after execution


ContentPart = TextContent | ToolCallContent


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass
class Message:
    """A single message in the conversation history."""

    role: MessageRole
    parts: list[ContentPart] = field(default_factory=list)
    model: str = ""  # which model generated this (for assistant messages)
    timestamp: float = field(default_factory=lambda: time.time())
    token_usage: TokenUsage | None = None

    # --- Convenience constructors ---

    @classmethod
    def user_text(cls, text: str) -> Message:
        return cls(role=MessageRole.USER, parts=[TextContent(text=text)])

    @classmethod
    def assistant_text(cls, text: str, model: str = "") -> Message:
        return cls(role=MessageRole.ASSISTANT, parts=[TextContent(text=text)], model=model)

    @classmethod
    def system_text(cls, text: str) -> Message:
        return cls(role=MessageRole.SYSTEM, parts=[TextContent(text=text)])

    @property
    def text(self) -> str:
        """Extract plain text from this message."""
        parts: list[str] = []
        for p in self.parts:
            if isinstance(p, TextContent):
                parts.append(p.text)
            elif isinstance(p, ToolCallContent) and p.tool_response:
                parts.append(f"[{p.tool_call.name}] {p.tool_response.content}")
        return "\n".join(parts)


@dataclass
class TokenUsage:
    """Token usage statistics for a single LLM call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        """Rough cost estimate (override per-model for accuracy)."""
        return self.total_tokens * 0.000002  # $2 per 1M tokens as fallback


# ---------------------------------------------------------------------------
# Agent Events (Streaming)
# ---------------------------------------------------------------------------


class AgentEventType(str, Enum):
    ERROR = "error"
    RESPONSE = "response"  # streaming text chunk
    TOOL_CALL = "tool_call"  # tool about to be invoked
    TOOL_RESULT = "tool_result"  # tool finished
    SUMMARIZE = "summarize"  # summarization requested
    THINKING = "thinking"  # reasoning/thinking block (if supported)
    DONE = "done"  # full turn complete
    PROGRESS = "progress"  # progress update (e.g., "Step 2/5")


@dataclass
class AgentEvent:
    """Event emitted by the agent during processing."""

    type: AgentEventType
    session_id: str = ""
    content: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: time.time())

    # For tool events
    tool_name: str = ""
    tool_call_id: str = ""

    # For done event
    message: Message | None = None
    token_usage: TokenUsage | None = None


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


@dataclass
class Session:
    """A conversation session."""

    id: str = ""
    title: str = ""
    parent_id: str = ""  # for sub-sessions (task/summarizer sessions)
    created_at: float = field(default_factory=lambda: time.time())
    updated_at: float = field(default_factory=lambda: time.time())
    total_cost: float = 0.0
    message_count: int = 0

    @property
    def created_at_dt(self) -> datetime:
        return datetime.fromtimestamp(self.created_at, tz=timezone.utc)

    @property
    def updated_at_dt(self) -> datetime:
        return datetime.fromtimestamp(self.updated_at, tz=timezone.utc)


# ---------------------------------------------------------------------------
# Permission
# ---------------------------------------------------------------------------


class PermissionAction(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    BASH = "bash"
    NETWORK = "network"


@dataclass
class PermissionRequest:
    """A request for user approval before executing a sensitive action."""

    tool_name: str
    action: PermissionAction
    params: dict[str, Any] = field(default_factory=dict)
    path: str = ""  # relevant file path if any
    description: str = ""  # human-readable explanation


class PermissionDecision(str, Enum):
    GRANT = "grant"
    DENY = "deny"
    GRANT_PERSISTENT = "grant_persistent"  # remember for session


# ---------------------------------------------------------------------------
# Notepad (cross-turn memory)
# ---------------------------------------------------------------------------

NOTEPAD_CATEGORIES = ("learnings", "issues", "decisions", "problems")