"""Configuration management using pydantic-settings.

Loads from environment variables, .env files, and config files.
All settings are typed and validated at startup.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelProvider(str, Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"  # OpenAI-compatible local endpoints (Ollama, vLLM, etc.)
    OPENROUTER = "openrouter"


class AgentName(str, Enum):
    """Named agent configurations."""

    CODER = "coder"
    TASK = "task"
    SUMMARIZER = "summarizer"
    TITLE = "title"


class MCPType(str, Enum):
    """MCP server transport type."""

    STDIO = "stdio"
    SSE = "sse"


class MCPServer(BaseSettings):
    """Configuration for a single MCP server."""

    model_config = SettingsConfigDict(extra="allow")

    name: str
    type: MCPType = MCPType.STDIO
    url: str | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)


class AgentConfig(BaseSettings):
    """Per-agent model configuration."""

    model_config = SettingsConfigDict(extra="allow")

    model: str = "gpt-4o"
    max_tokens: int = 16384
    reasoning_effort: str = ""  # e.g., "low", "medium", "high" for OpenAI


class ProviderConfig(BaseSettings):
    """Provider-specific API configuration."""

    model_config = SettingsConfigDict(extra="allow")

    api_key: str = ""
    base_url: str = ""  # Override default endpoint (useful for proxies/local models)


class Config(BaseSettings):
    """Top-level application configuration.

    Loads from environment variables prefixed with OPENCODE_.
    Example: OPENCODE_OPENAI_API_KEY=sk-...
    """

    model_config = SettingsConfigDict(
        env_prefix="OPENCODE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM Providers ---
    providers: dict[ModelProvider, ProviderConfig] = Field(
        default_factory=lambda: {
            ModelProvider.OPENAI: ProviderConfig(),
            ModelProvider.ANTHROPIC: ProviderConfig(),
            ModelProvider.LOCAL: ProviderConfig(base_url="http://localhost:11434/v1"),
            ModelProvider.OPENROUTER: ProviderConfig(),
        }
    )

    # --- Agent configs ---
    agents: dict[AgentName, AgentConfig] = Field(
        default_factory=lambda: {
            AgentName.CODER: AgentConfig(model="gpt-4o", max_tokens=16384),
            AgentName.TASK: AgentConfig(model="gpt-4o", max_tokens=8192),
            AgentName.SUMMARIZER: AgentConfig(model="gpt-4o-mini", max_tokens=4096),
            AgentName.TITLE: AgentConfig(model="gpt-4o-mini", max_tokens=256),
        }
    )

    # --- Default provider ---
    default_provider: ModelProvider = ModelProvider.OPENAI

    # --- MCP servers ---
    mcp_servers: list[MCPServer] = Field(default_factory=list)

    # --- Paths ---
    working_dir: Path = Field(default_factory=lambda: Path.cwd())
    data_dir: Path = Field(default_factory=lambda: Path.home() / ".opencode_agent")
    sessions_db: Path = Field(default=None)  # defaults to data_dir / "sessions.db"

    # --- System prompt path ---
    system_prompt_path: Path = Field(default_factory=lambda: Path("SYSTEM_PROMPT.md"))

    # --- Skills directory ---
    skills_dir: Path = Field(default_factory=lambda: Path("skills"))

    # --- Feature flags ---
    enable_lsp: bool = True
    enable_mcp: bool = True
    enable_git: bool = True

    # --- Security ---
    auto_approve_tools: set[str] = Field(default_factory=set)  # tools that skip permission check
    dangerous_commands: list[str] = Field(
        default_factory=lambda: [
            "rm -rf",
            "mkfs",
            "dd if=",
            ":(){ :|:& };:",
            "chmod 777 /",
            "shutdown",
            "reboot",
            "format",
            "del /s /q",
            "rmdir /s /q",
        ]
    )

    @field_validator("sessions_db", mode="before")
    @classmethod
    def _default_sessions_db(cls, v: Path | None, info) -> Path:
        if v is None or (isinstance(v, str) and not v):
            return info.data.get("data_dir", Path.home() / ".opencode_agent") / "sessions.db"
        return Path(v) if isinstance(v, str) else v

    @property
    def coder_agent(self) -> AgentConfig:
        return self.agents[AgentName.CODER]

    @property
    def task_agent(self) -> AgentConfig:
        return self.agents[AgentName.TASK]

    def get_provider_api_key(self, provider: ModelProvider) -> str:
        cfg = self.providers.get(provider)
        if cfg and cfg.api_key:
            return cfg.api_key
        # Fallback: try environment variable
        import os

        env_map = {
            ModelProvider.OPENAI: "OPENAI_API_KEY",
            ModelProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
            ModelProvider.LOCAL: "OPENAI_API_KEY",  # local often uses same key format
            ModelProvider.OPENROUTER: "OPENROUTER_API_KEY",
        }
        return os.environ.get(env_map.get(provider, ""), "")


# Global singleton — initialized once at startup
_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration singleton."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def init_config(**overrides: Any) -> Config:
    """Initialize config with optional overrides. Call once at app startup."""
    global _config
    _config = Config(**overrides)
    return _config