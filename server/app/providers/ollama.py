import json
import urllib.request
from .base import BaseProvider, AIResponse

DEFAULT_MODEL = "llama3.2"


class OllamaProvider(BaseProvider):

    def complete(self, prompt: str, max_tokens: int = 1000) -> AIResponse:
        host = self.config.get("ollama_host", "http://localhost:11434")
        model = self.config.get("model") or DEFAULT_MODEL

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }

        req = urllib.request.Request(
            f"{host}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return AIResponse(text=result["response"].strip(), model=model)
