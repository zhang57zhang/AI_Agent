"""LLM Provider layer — unified interface for multiple AI providers."""

from opencode_agent.provider.base import (
    BaseProvider,
    ProviderMessage,
    ProviderTool,
)
from opencode_agent.provider.openai_provider import OpenAIProvider
from opencode_agent.provider.anthropic_provider import AnthropicProvider

from opencode_agent.config import AgentConfig, ModelProvider, get_config


def create_provider(
    agent_name: str = "coder",
    provider_override: ModelProvider | None = None,
) -> BaseProvider:
    """Factory: create a provider instance based on agent configuration.

    Args:
        agent_name: Which agent config to use (coder, task, summarizer, title).
        provider_override: Override the default provider.

    Returns:
        Configured BaseProvider instance ready for use.
    """
    cfg = get_config()

    # Determine provider
    provider = provider_override or cfg.default_provider

    # Get agent config
    from opencode_agent.config import AgentName
    try:
        agent_enum = AgentName(agent_name)
    except ValueError:
        agent_enum = AgentName.CODER
    agent_cfg = cfg.agents[agent_enum]

    # Get provider API config
    provider_cfg = cfg.providers.get(provider)

    # Build kwargs
    kwargs: dict = {
        "model": agent_cfg.model,
        "max_tokens": agent_cfg.max_tokens,
        "temperature": 0.0,
    }
    if provider_cfg:
        kwargs["api_key"] = provider_cfg.api_key
        kwargs["base_url"] = provider_cfg.base_url

    # Ensure we have an API key from environment if not in config
    if not kwargs.get("api_key"):
        kwargs["api_key"] = cfg.get_provider_api_key(provider)

    # Create provider instance
    if provider == ModelProvider.OPENAI:
        return OpenAIProvider(**kwargs)
    elif provider == ModelProvider.ANTHROPIC:
        return AnthropicProvider(**kwargs)
    elif provider == ModelProvider.LOCAL:
        # Local uses OpenAI-compatible API
        if not kwargs.get("base_url"):
            kwargs["base_url"] = "http://localhost:11434/v1"
        if not kwargs.get("model"):
            kwargs["model"] = "llama3"
        return OpenAIProvider(**kwargs)
    elif provider == ModelProvider.OPENROUTER:
        if not kwargs.get("base_url"):
            kwargs["base_url"] = "https://openrouter.ai/api/v1"
        return OpenAIProvider(**kwargs)
    else:
        # Default fallback
        return OpenAIProvider(**kwargs)


__all__ = [
    "BaseProvider",
    "ProviderMessage",
    "ProviderTool",
    "OpenAIProvider",
    "AnthropicProvider",
    "create_provider",
]