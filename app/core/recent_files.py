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


def _project_key(path: str) -> str:
    """Canonicalise a path for dedup. Multi-page paths collapse to
    their project folder so switching between pages doesn't pile up
    one recent entry per page. Legacy single-file paths use the
    resolved absolute path as the key, matching the previous behaviour.
    """
    try:
        from app.core.project_folder import find_project_root
        root = find_project_root(path)
        if root is not None:
            return str(root.resolve())
    except Exception:
        pass
    try:
        return str(Path(path).resolve())
    except OSError:
        return str(path)


def add_recent(path: str) -> list[str]:
    """Promote a project to the top of the recents list. Multi-page
    projects dedup by project folder so opening a different page in
    the same project doesn't add a second entry.

    Also drops any recent entry whose file no longer exists on disk
    (test pages the user deleted left "missing" rows otherwise).
    """
    normalized = str(Path(path).resolve())
    new_key = _project_key(normalized)
    kept: list[str] = []
    for existing in load_recent():
        if not Path(existing).exists():
            continue  # garbage-collect stale entries
        if _project_key(existing) == new_key:
            continue  # same project (folder) — replaced by the new path below
        kept.append(existing)
    kept.insert(0, normalized)
    kept = kept[:MAX_RECENT]
    save_recent(kept)
    return kept


def remove_recent(path: str) -> list[str]:
    target_key = _project_key(path)
    paths = [
        p for p in load_recent()
        if _project_key(p) != target_key
    ]
    save_recent(paths)
    return paths


def clear_recent() -> None:
    save_recent([])
