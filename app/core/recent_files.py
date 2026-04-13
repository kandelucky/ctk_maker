"""Track recently opened/saved project files.

Persists the list at `~/.ctk_visual_builder/recent.json` (max 10 entries,
newest first). Loader is tolerant — a missing or corrupt file is treated
as an empty list.
"""

from __future__ import annotations

import json
from pathlib import Path

RECENT_PATH = Path.home() / ".ctk_visual_builder" / "recent.json"
MAX_RECENT = 10


def load_recent() -> list[str]:
    if not RECENT_PATH.exists():
        return []
    try:
        data = json.loads(RECENT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(p) for p in data if isinstance(p, str)][:MAX_RECENT]


def save_recent(paths: list[str]) -> None:
    try:
        RECENT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RECENT_PATH.write_text(
            json.dumps(paths[:MAX_RECENT], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


def add_recent(path: str) -> list[str]:
    normalized = str(Path(path).resolve())
    paths = [p for p in load_recent() if p != normalized]
    paths.insert(0, normalized)
    paths = paths[:MAX_RECENT]
    save_recent(paths)
    return paths


def remove_recent(path: str) -> list[str]:
    normalized = str(Path(path).resolve())
    paths = [p for p in load_recent() if p != normalized]
    save_recent(paths)
    return paths


def clear_recent() -> None:
    save_recent([])
