"""Agent Loop — the core execution engine.

Implements the agentic loop:
1. User sends message
2. LLM generates response (may include tool calls)
3. If tool calls: execute tools, feed results back to LLM
4. Repeat until LLM stops requesting tools (or max iterations)
5. Stream events to subscribers throughout
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncIterator

from opencode_agent.agent.prompt import get_agent_prompt, get_tools_description
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
    ToolResponse,
)
from opencode_agent.config import AgentName, get_config
from opencode_agent.permissions import PermissionService
from opencode_agent.provider.base import BaseProvider, ProviderMessage, ProviderTool
from opencode_agent.tools.base import BaseTool, ToolContext

logger = logging.getLogger("opencode_agent.agent.loop")

MAX_TOOL_ITERATIONS = 25  # Safety limit: max rounds of tool calling


class AgentLoop:
    """Core agent execution loop with streaming event support.

    The loop:
    1. Receives user message
    2. Builds prompt context (system prompt + history + tools)
    3. Calls LLM provider
    4. If LLM requests tools → execute them → feed results back
    5. Repeat until done or max iterations
    6. Publishes events throughout for UI updates
    """

    def __init__(
        self,
        provider: BaseProvider,
        tools: list[BaseTool],
        agent_name: AgentName = AgentName.CODER,
        permissions: PermissionService | None = None,
        session_id: str = "",
        message_history: list[Message] | None = None,
    ) -> None:
        self.provider = provider
        self.tools = tools
        self.agent_name = agent_name
        self.permissions = permissions
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.history: list[Message] = message_history or []

        # Build tool lookup
        self._tool_map: dict[str, BaseTool] = {t.info().name: t for t in tools}

        # Track current response state
        self._response_text = ""
        self._current_tool_calls: list[ToolCall] = []
        self._total_usage = TokenUsage()
        self._is_running = False
        self._cancelled = False

    @property
    def model_name(self) -> str:
        return self.provider.model

    @property
    def is_busy(self) -> bool:
        return self._is_running

    async def run(self, user_message: str) -> AsyncIterator[AgentEvent]:
        """Execute the full agent loop for a user message.

        Yields AgentEvent objects for streaming to the UI.
        """
        if self._is_running:
            yield AgentEvent(
                type=AgentEventType.ERROR,
                session_id=self.session_id,
                content="Session is busy processing another request",
            )
            return

        self._is_running = True
        self._cancelled = False
        self._response_text = ""
        self._current_tool_calls = []
        self._total_usage = TokenUsage()

        try:
            # Add user message to history
            user_msg = Message.user_text(user_message)
            self.history.append(user_msg)

            # Build provider messages from history
            provider_messages = self._history_to_provider_messages()

            # Build system prompt
            tools_summary = get_tools_description(self.tools)
            system_prompt = get_agent_prompt(
                agent_name=self.agent_name,
                model_name=self.model_name,
                tools_summary=tools_summary,
            )

            # Build provider tool schemas
            provider_tools = self._tools_to_provider_tools()

            # Execute the agentic loop
            iteration = 0
            while iteration < MAX_TOOL_ITERATIONS:
                if self._cancelled:
                    yield AgentEvent(
                        type=AgentEventType.ERROR,
                        session_id=self.session_id,
                        content="Request cancelled",
                    )
                    break

                iteration += 1
                tool_calls_in_round: list[ToolCall] = []
                round_text = ""

                # Call the LLM
                async for event in self.provider.chat(
                    messages=provider_messages,
                    tools=provider_tools,
                    system_prompt=system_prompt,
                    stream=True,
                ):
                    if self._cancelled:
                        break

                    event.session_id = self.session_id

                    if event.type == AgentEventType.RESPONSE:
                        round_text += event.content
                        self._response_text += event.content
                        yield event

                    elif event.type == AgentEventType.TOOL_CALL:
                        tool_calls_in_round.append(
                            ToolCall(
                                id=event.tool_call_id,
                                name=event.tool_name,
                                input=event.data.get("input", "{}"),
                            )
                        )

                    elif event.type == AgentEventType.DONE:
                        if event.token_usage:
                            self._total_usage.prompt_tokens += event.token_usage.prompt_tokens
                            self._total_usage.completion_tokens += event.token_usage.completion_tokens
                            self._total_usage.total_tokens += event.token_usage.total_tokens

                    elif event.type == AgentEventType.ERROR:
                        yield event

                if self._cancelled:
                    break

                # If no tool calls, we're done
                if not tool_calls_in_round:
                    break

                # Execute tool calls
                # Add assistant message with tool calls to history
                assistant_msg = Message(role=MessageRole.ASSISTANT, model=self.model_name)
                assistant_msg.parts.append(TextContent(text=round_text))
                for tc in tool_calls_in_round:
                    assistant_msg.parts.append(ToolCallContent(tool_call=tc))
                self.history.append(assistant_msg)
                provider_messages.append(self._message_to_provider(assistant_msg))

                # Execute each tool call
                for tc in tool_calls_in_round:
                    if self._cancelled:
                        break

                    # Notify UI
                    yield AgentEvent(
                        type=AgentEventType.PROGRESS,
                        session_id=self.session_id,
                        content=f"Executing tool: {tc.name}",
                        tool_name=tc.name,
                        tool_call_id=tc.id,
                    )

                    # Execute the tool
                    response = await self._execute_tool(tc)

                    # Notify UI of result
                    yield AgentEvent(
                        type=AgentEventType.TOOL_RESULT,
                        session_id=self.session_id,
                        tool_name=tc.name,
                        tool_call_id=tc.id,
                        content=response.content[:500] if response.content else "",
                        data={"is_error": response.is_error},
                    )

                    # Add tool result to provider messages
                    provider_messages.append(ProviderMessage(
                        role="tool",
                        content=response.content,
                        tool_call_id=tc.id,
                        name=tc.name,
                    ))

                    # Update assistant message with result
                    for part in assistant_msg.parts:
                        if isinstance(part, ToolCallContent) and part.tool_call.id == tc.id:
                            part.tool_response = response

            # Final done event
            final_message = Message.assistant_text(self._response_text, model=self.model_name)
            self.history.append(final_message)

            yield AgentEvent(
                type=AgentEventType.DONE,
                session_id=self.session_id,
                content=self._response_text,
                message=final_message,
                token_usage=self._total_usage,
            )

        except Exception as e:
            logger.exception("Agent loop error")
            yield AgentEvent(
                type=AgentEventType.ERROR,
                session_id=self.session_id,
                content=f"Agent error: {e}",
            )
        finally:
            self._is_running = False

    async def _execute_tool(self, tool_call: ToolCall) -> ToolResponse:
        """Execute a single tool call with error handling."""
        tool = self._tool_map.get(tool_call.name)
        if tool is None:
            return ToolResponse.error(f"Unknown tool: {tool_call.name}")

        cfg = get_config()
        ctx = ToolContext(
            session_id=self.session_id,
            working_dir=str(cfg.working_dir),
            permissions=self.permissions,
        )

        try:
            return await tool.run(ctx, tool_call)
        except asyncio.CancelledError:
            return ToolResponse.error("Tool execution cancelled")
        except Exception as e:
            logger.error("Tool %s error: %s", tool_call.name, e)
            return ToolResponse.error(f"Tool '{tool_call.name}' error: {e}")

    def cancel(self) -> None:
        """Cancel the current execution."""
        self._cancelled = True

    def _history_to_provider_messages(self) -> list[ProviderMessage]:
        """Convert Message history to ProviderMessage format."""
        result: list[ProviderMessage] = []
        for msg in self.history:
            pm = self._message_to_provider(msg)
            result.append(pm)
        return result

    def _message_to_provider(self, msg: Message) -> ProviderMessage:
        """Convert a single Message to ProviderMessage."""
        # Check for tool calls in parts
        tool_calls: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []

        for part in msg.parts:
            if isinstance(part, ToolCallContent):
                tool_calls.append({
                    "id": part.tool_call.id,
                    "type": "function",
                    "function": {
                        "name": part.tool_call.name,
                        "arguments": part.tool_call.input,
                    },
                })
                if part.tool_response:
                    tool_results.append({
                        "tool_call_id": part.tool_call.id,
                        "content": part.tool_response.content,
                    })

        if tool_results:
            # Return tool result messages (one per result)
            # We return the first one here; caller handles multi-result
            return ProviderMessage(
                role="tool",
                content=tool_results[0]["content"],
                tool_call_id=tool_results[0]["tool_call_id"],
                name="",
            )

        return ProviderMessage(
            role=msg.role.value,
            content=msg.text,
            tool_calls=tool_calls if tool_calls else None,  # type: ignore
        )

    def _tools_to_provider_tools(self) -> list[ProviderTool]:
        """Convert BaseTool list to ProviderTool list."""
        return [
            ProviderTool(
                name=t.info().name,
                description=t.info().description,
                parameters={
                    "type": "object",
                    "properties": t.info().parameters,
                    "required": t.info().required,
                },
            )
            for t in self.tools
        ]

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.history.clear()
        self._response_text = ""

    def get_history(self) -> list[Message]:
        """Return conversation history."""
        return list(self.history)