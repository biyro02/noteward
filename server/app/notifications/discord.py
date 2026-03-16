import json
import urllib.request
from .base import BaseNotifier


class DiscordNotifier(BaseNotifier):

    def send(self, message: str) -> None:
        webhook_url = self.config.get("webhook_url", "")
        if not webhook_url:
            raise ValueError("Discord webhook_url not configured.")
        # Discord uses "content" and supports basic markdown
        payload = {"content": message}
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)

    def parse_command(self, payload: dict) -> tuple[str, str] | None:
        # Discord interactions / webhook events
        author = payload.get("author", {})
        if author.get("bot"):
            return None
        user_id = author.get("id", "")
        text = payload.get("content", "").strip()
        if not text:
            return None
        return user_id, text

    def reply(self, user_id: str, message: str) -> None:
        self.send(message)
