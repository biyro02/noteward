from pathlib import Path
from .base import BaseSource

NOTES_DIR = Path("/app/data/notes")


class FilesSource(BaseSource):
    """Reads synced note files pushed by watcher.py via the /sync API."""

    @property
    def name(self) -> str:
        return "files"

    def fetch(self) -> str:
        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        parts = []
        for f in sorted(NOTES_DIR.iterdir()):
            if f.is_file() and not f.name.startswith("."):
                try:
                    parts.append(f"### {f.name}\n{f.read_text(encoding='utf-8')}")
                except Exception:
                    pass
        return "\n\n".join(parts)
