import json
import urllib.request
from .base import BaseProvider, AIResponse

DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider(BaseProvider):

    def complete(self, prompt: str, max_tokens: int = 1000) -> AIResponse:
        api_key = self._resolve_api_key(self.config.get("api_key", ""))
        model = self.config.get("model") or DEFAULT_MODEL

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return AIResponse(
                text=result["choices"][0]["message"]["content"].strip(),
                model=model,
            )
