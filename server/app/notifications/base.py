from abc import ABC, abstractmethod


class BaseNotifier(ABC):

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def send(self, message: str) -> None:
        """Send a plain text / mrkdwn message."""
        ...

    @abstractmethod
    def parse_command(self, payload: dict) -> tuple[str, str] | None:
        """
        Parse an incoming webhook payload.
        Returns (user_id, message_text) or None if not a user command.
        """
        ...

    @abstractmethod
    def reply(self, user_id: str, message: str) -> None:
        """Send a direct reply to a user."""
        ...
