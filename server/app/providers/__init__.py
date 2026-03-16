from .base import BaseProvider, AIResponse
from .claude import ClaudeProvider
from .openai import OpenAIProvider
from .ollama import OllamaProvider

__all__ = ["BaseProvider", "AIResponse", "ClaudeProvider", "OpenAIProvider", "OllamaProvider"]


def get_provider(config: dict) -> "BaseProvider":
    providers = {
        "claude": ClaudeProvider,
        "openai": OpenAIProvider,
        "ollama": OllamaProvider,
    }
    provider_type = config.get("provider", "claude")
    cls = providers.get(provider_type)
    if not cls:
        raise ValueError(f"Unknown AI provider: {provider_type}")
    return cls(config)
