"""OpenAI provider implementation (also covers local OpenAI-compatible APIs)."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from opencode_agent.base_types import (
    AgentEvent,
    AgentEventType,
    Message,
    MessageRole,
    TextContent,
    TokenUsage,
    ToolCall,
    ToolCallContent,
)
from opencode_agent.provider.base import BaseProvider, ProviderMessage, ProviderTool

logger = logging.getLogger("opencode_agent.provider.openai")


class OpenAIProvider(BaseProvider):
    """OpenAI API provider (also works with Ollama, vLLM, and other compatible APIs)."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = AsyncOpenAI(
            api_key=self.api_key or "not-needed",  # local models don't need a key
            base_url=self.base_url or None,
        )

    async def chat(
        self,
        messages: list[ProviderMessage],
        tools: list[ProviderTool] | None = None,
        system_prompt: str = "",
        stream: bool = True,
    ) -> AsyncIterator[AgentEvent]:
        # Build OpenAI message format
        oai_messages: list[dict[str, Any]] = []

        if system_prompt:
            oai_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            if msg.role == "tool":
                oai_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                })
            elif msg.tool_calls:
                oai_messages.append({
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": msg.tool_calls,
                })
            else:
                oai_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        # Build tools schema
        oai_tools: list[dict[str, Any]] | None = None
        if tools:
            oai_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": oai_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": stream,
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
            kwargs["tool_choice"] = "auto"

        try:
            if stream:
                async for chunk in await self._client.chat.completions.create(**kwargs):
                    choice = chunk.choices[0] if chunk.choices else None
                    if not choice:
                        continue

                    # Text content
                    if choice.delta.content:
                        yield self._make_text_event(choice.delta.content)

                    # Tool calls
                    if choice.delta.tool_calls:
                        for tc in choice.delta.tool_calls:
                            if tc.function and tc.function.name:
                                yield self._make_tool_call_event(
                                    ToolCall(
                                        id=tc.id or f"call_{tc.index}",
                                        name=tc.function.name,
                                        input=tc.function.arguments or "{}",
                                    )
                                )

                    # Finish reason
                    if choice.finish_reason == "stop" or choice.finish_reason == "tool_calls":
                        usage = None
                        if chunk.usage:
                            usage = TokenUsage(
                                prompt_tokens=chunk.usage.prompt_tokens or 0,
                                completion_tokens=chunk.usage.completion_tokens or 0,
                                total_tokens=chunk.usage.total_tokens or 0,
                            )
                        yield self._make_done_event(
                            message=Message(role=MessageRole.ASSISTANT),
                            usage=usage,
                        )
            else:
                response = await self._client.chat.completions.create(**{**kwargs, "stream": False})
                choice = response.choices[0]
                if choice.message.content:
                    yield self._make_text_event(choice.message.content)
                if choice.message.tool_calls:
                    for tc in choice.message.tool_calls:
                        if tc.function:
                            yield self._make_tool_call_event(
                                ToolCall(
                                    id=tc.id,
                                    name=tc.function.name,
                                    input=tc.function.arguments,
                                )
                            )
                usage = TokenUsage(
                    prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                    completion_tokens=response.usage.completion_tokens if response.usage else 0,
                    total_tokens=response.usage.total_tokens if response.usage else 0,
                )
                yield self._make_done_event(
                    message=Message(role=MessageRole.ASSISTANT),
                    usage=usage,
                )

        except Exception as e:
            logger.error("OpenAI API error: %s", e)
            yield self._make_error_event(str(e))