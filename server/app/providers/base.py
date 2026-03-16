from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AIResponse:
    text: str
    model: str


class BaseProvider(ABC):
    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def complete(self, prompt: str, max_tokens: int = 1000) -> AIResponse:
        """Send prompt, return response."""
        ...

    def _resolve_api_key(self, key_value: str) -> str:
        """Resolve [secret:name] references."""
        if key_value.startswith("[secret:") and key_value.endswith("]"):
            from app import crypto
            secret_name = key_value[8:-1]
            return crypto.get_secret(secret_name)
        return key_value
