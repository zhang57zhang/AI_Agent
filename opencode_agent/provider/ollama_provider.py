"""Ollama provider — connects to local or remote Ollama servers.

Extends OpenAI-compatible API with Ollama-specific features:
- Health check via /api/version
- Model listing via /api/tags
- Auto base_url from host:port
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

import httpx

from opencode_agent.base_types import (
    AgentEvent,
    AgentEventType,
    Message,
    MessageRole,
    TextContent,
    TokenUsage,
    ToolCall,
)
from opencode_agent.provider.base import BaseProvider, ProviderMessage, ProviderTool
from opencode_agent.provider.openai_provider import OpenAIProvider

logger = logging.getLogger("opencode_agent.provider.ollama")


class OllamaProvider(OpenAIProvider):
    """Ollama LLM provider with extra management APIs.

    Uses OpenAI-compatible /v1/chat/completions for chat,
    plus native /api/* endpoints for Ollama management.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 11434,
        **kwargs: Any,
    ) -> None:
        # Synthesize base_url from host:port if not explicitly provided
        if not kwargs.get("base_url"):
            # Strip protocol if user included it
            clean_host = host
            if clean_host.startswith("http://"):
                clean_host = clean_host[len("http://"):]
            elif clean_host.startswith("https://"):
                clean_host = clean_host[len("https://"):]
            # Strip trailing slash and port if embedded
            if "/" in clean_host:
                clean_host = clean_host.split("/")[0]
            kwargs["base_url"] = f"http://{clean_host}:{port}/v1"

        # Ollama does not require an API key
        if not kwargs.get("api_key"):
            kwargs["api_key"] = "ollama"

        # Store Ollama native endpoint (without /v1)
        self.ollama_base = kwargs["base_url"].rsplit("/v1", 1)[0]

        super().__init__(**kwargs)

    # ------------------------------------------------------------------
    # Ollama-native management APIs
    # ------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Check Ollama server health and version.

        Returns:
            Dict with version info, e.g. {"version": "0.5.4", ...}
        Raises:
            ConnectionError if server is unreachable.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.ollama_base}/api/version")
                resp.raise_for_status()
                return resp.json()
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.ollama_base}: {e}"
            ) from e
        except httpx.HTTPStatusError as e:
            raise ConnectionError(
                f"Ollama health check failed: {e.response.status_code}"
            ) from e

    async def list_models(self) -> list[dict[str, Any]]:
        """List locally available models on the Ollama server.

        Returns:
            List of model dicts with keys: name, model, modified_at, size, ...
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.ollama_base}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                return data.get("models", [])
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.ollama_base}: {e}"
            ) from e

    async def model_info(self, model_name: str) -> dict[str, Any]:
        """Get detailed information about a specific model.

        Args:
            model_name: Model identifier (e.g. "llama3", "qwen2:7b").

        Returns:
            Dict with model details, license, parameters, etc.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.ollama_base}/api/show",
                    json={"name": model_name},
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.ollama_base}: {e}"
            ) from e

    async def pull_model(self, model_name: str) -> AsyncIterator[str]:
        """Pull (download) a model from Ollama registry.

        Args:
            model_name: Model to pull (e.g. "llama3", "qwen2:7b").

        Yields:
            Status strings as the model downloads.
        """
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream(
                "POST",
                f"{self.ollama_base}/api/pull",
                json={"name": model_name, "stream": True},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.strip():
                        import json
                        data = json.loads(line)
                        status = data.get("status", "")
                        yield status
