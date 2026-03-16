from .base import BaseNotifier
from .slack import SlackNotifier
from .discord import DiscordNotifier

__all__ = ["BaseNotifier", "SlackNotifier", "DiscordNotifier"]


def get_notifier(config: dict) -> "BaseNotifier":
    notifiers = {
        "slack": SlackNotifier,
        "discord": DiscordNotifier,
    }
    notifier_type = config.get("type", "slack")
    cls = notifiers.get(notifier_type)
    if not cls:
        raise ValueError(f"Unknown notification type: {notifier_type}")
    return cls(config)
