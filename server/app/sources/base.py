from abc import ABC, abstractmethod


class BaseSource(ABC):
    """Base class for all data sources (files, GitHub, Jira, etc.)"""

    @abstractmethod
    def fetch(self) -> str:
        """Fetch content and return as a single formatted string."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable source name for logging."""
        ...
