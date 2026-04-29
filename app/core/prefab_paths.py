"""User-wide prefab library location.

Prefabs live OUTSIDE any project so the user can drag the same
saved widget / window into any project they open. Default root:

    Windows : %APPDATA%/CTkMaker/prefabs/
    macOS   : ~/Library/Application Support/CTkMaker/prefabs/
    Linux   : ~/.config/CTkMaker/prefabs/

Each ``.ctkprefab`` file is a zip archive (json + thumbnail +
optional bundled assets); folders under the root act as user-defined
categories.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PREFAB_DIR_NAME = "prefabs"
APP_DIR_NAME = "CTkMaker"
PREFAB_EXT = ".ctkprefab"


def _platform_appdata_root() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base)
        return Path.home() / "AppData" / "Roaming"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".config"


def prefabs_root() -> Path:
    """``<appdata>/CTkMaker/prefabs/`` — does not create."""
    return _platform_appdata_root() / APP_DIR_NAME / PREFAB_DIR_NAME


def ensure_prefabs_root() -> Path:
    """Create the prefabs root if missing. Idempotent. Falls back to
    ``~/CTkMaker/prefabs/`` if the platform appdata path can't be
    created (sandboxed env, read-only home).
    """
    root = prefabs_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        return root
    except OSError:
        fallback = Path.home() / APP_DIR_NAME / PREFAB_DIR_NAME
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
