"""Persistent user settings (theme, future preferences).

Stored at `~/.ctk_visual_builder/settings.json`. Loader is tolerant —
a missing or corrupt file is treated as an empty dict.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SETTINGS_PATH = Path.home() / ".ctk_visual_builder" / "settings.json"


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_setting(key: str, value: Any) -> None:
    data = load_settings()
    data[key] = value
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


def load_description_hints() -> list[str]:
    raw = load_settings().get("description_hints", [])
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if isinstance(x, str) and x.strip()]


def save_description_hints(hints: list[str]) -> None:
    cleaned = [h for h in hints if isinstance(h, str) and h.strip()]
    save_setting("description_hints", cleaned)
