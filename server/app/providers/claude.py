import json
import urllib.request
from .base import BaseProvider, AIResponse

DEFAULT_MODEL = "claude-sonnet-4-6"


class ClaudeProvider(BaseProvider):

    def complete(self, prompt: str, max_tokens: int = 1000) -> AIResponse:
        api_key = self._resolve_api_key(self.config.get("api_key", ""))
        model = self.config.get("model") or DEFAULT_MODEL

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode(),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return AIResponse(text=result["content"][0]["text"].strip(), model=model)
