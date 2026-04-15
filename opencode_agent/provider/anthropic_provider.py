"""Anthropic (Claude) provider implementation."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from opencode_agent.base_types import (
    AgentEvent,
    AgentEventType,
    Message,
    MessageRole,
    TokenUsage,
    ToolCall,
)
from opencode_agent.provider.base import BaseProvider, ProviderMessage, ProviderTool

logger = logging.getLogger("opencode_agent.provider.anthropic")


class AnthropicProvider(BaseProvider):
    """Anthropic Claude API provider."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = None
        self._import_client()

    def _import_client(self) -> None:
        try:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(api_key=self.api_key)
        except ImportError:
            logger.warning("anthropic package not installed")

    async def chat(
        self,
        messages: list[ProviderMessage],
        tools: list[ProviderTool] | None = None,
        system_prompt: str = "",
        stream: bool = True,
    ) -> AsyncIterator[AgentEvent]:
        if self._client is None:
            yield self._make_error_event("Anthropic client not initialized. Install: pip install anthropic")
            return

        # Convert to Anthropic format
        anthropic_messages: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "tool":
                anthropic_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content": msg.content,
                        }
                    ],
                })
            elif msg.role == "assistant" and msg.tool_calls:
                content_blocks: list[dict[str, Any]] = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    func = tc.get("function", {})
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": func.get("name", ""),
                        "input": json.loads(func.get("arguments", "{}")),
                    })
                anthropic_messages.append({"role": "assistant", "content": content_blocks})
            else:
                anthropic_messages.append({
                    "role": msg.role,
                    "content": msg.content or "",
                })

        # Build tools
        anthropic_tools: list[dict[str, Any]] | None = None
        if tools:
            anthropic_tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature if self.temperature > 0 else 0,
            "stream": stream,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        try:
            if stream:
                async with self._client.messages.stream(**kwargs) as stream_ctx:
                    async for event in stream_ctx:
                        if event.type == "content_block_delta":
                            if hasattr(event.delta, "text"):
                                yield self._make_text_event(event.delta.text)
                        elif event.type == "content_block_start":
                            if hasattr(event.content_block, "type") and event.content_block.type == "tool_use":
                                pass  # Tool use will be signaled via content_block_stop
                        elif event.type == "message_stop":
                            msg = stream_ctx.get_final_message()
                            usage = TokenUsage(
                                prompt_tokens=msg.usage.input_tokens if msg.usage else 0,
                                completion_tokens=msg.usage.output_tokens if msg.usage else 0,
                                total_tokens=(msg.usage.input_tokens + msg.usage.output_tokens) if msg.usage else 0,
                            )
                            # Extract tool calls from final message
                            for block in msg.content:
                                if block.type == "tool_use":
                                    yield self._make_tool_call_event(
                                        ToolCall(
                                            id=block.id,
                                            name=block.name,
                                            input=json.dumps(block.input, ensure_ascii=False),
                                        )
                                    )
                            yield self._make_done_event(
                                message=Message(role=MessageRole.ASSISTANT),
                                usage=usage,
                            )
            else:
                response = await self._client.messages.create(**{**kwargs, "stream": False})
                for block in response.content:
                    if block.type == "text":
                        yield self._make_text_event(block.text)
                    elif block.type == "tool_use":
                        yield self._make_tool_call_event(
                            ToolCall(
                                id=block.id,
                                name=block.name,
                                input=json.dumps(block.input, ensure_ascii=False),
                            )
                        )
                usage = TokenUsage(
                    prompt_tokens=response.usage.input_tokens if response.usage else 0,
                    completion_tokens=response.usage.output_tokens if response.usage else 0,
                    total_tokens=(response.usage.input_tokens + response.usage.output_tokens) if response.usage else 0,
                )
                yield self._make_done_event(
                    message=Message(role=MessageRole.ASSISTANT),
                    usage=usage,
                )

        except Exception as e:
            logger.error("Anthropic API error: %s", e)
            yield self._make_error_event(str(e))