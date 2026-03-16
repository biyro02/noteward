import json
import urllib.request
from .base import BaseNotifier


class SlackNotifier(BaseNotifier):

    def send(self, message: str) -> None:
        webhook_url = self.config.get("webhook_url", "")
        if not webhook_url:
            raise ValueError("Slack webhook_url not configured.")
        payload = {"text": message}
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)

    def parse_command(self, payload: dict) -> tuple[str, str] | None:
        # Slack Events API payload
        event = payload.get("event", {})
        if event.get("type") != "message":
            return None
        if event.get("bot_id"):
            return None
        user = event.get("user", "")
        text = event.get("text", "").strip()
        if not text:
            return None
        return user, text

    def reply(self, user_id: str, message: str) -> None:
        # For bot replies we use the webhook (simplest approach).
        # Full per-user DM requires chat.postMessage with bot_token.
        bot_token = self.config.get("bot_token", "")
        channel = self.config.get("channel", "")
        if bot_token and channel:
            payload = {"channel": channel, "text": message}
            req = urllib.request.Request(
                "https://slack.com/api/chat.postMessage",
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {bot_token}",
                    "Content-Type": "application/json",
                },
            )
            urllib.request.urlopen(req, timeout=10)
        else:
            self.send(message)
