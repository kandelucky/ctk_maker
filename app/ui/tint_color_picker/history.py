"""Persistent saved-colors storage for ctk-color-picker.

`ColorHistory` keeps a list of recent / saved hex colors on disk as a
JSON array, with move-to-front deduplication and a configurable cap.
"""
import json
import os

DEFAULT_MAX = 20


def _default_path() -> str:
    home = os.path.expanduser("~")
    folder = os.path.join(home, ".ctk_color_picker")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "colors.json")


class ColorHistory:
    """Persistent list of hex colors with deduplication and a max cap.

    Colors are stored on disk as a JSON array at `path`. When omitted,
    the default path is `~/.ctk_color_picker/colors.json`. Adding a
    color that already exists moves it to the front of the list; the
    oldest entries are dropped when `max_entries` is exceeded.

    Args:
        path: JSON file path. Uses the default location if None.
        max_entries: Maximum number of colors to retain (default: 20).
    """

    def __init__(self, path: str | None = None, max_entries: int = DEFAULT_MAX):
        self._path = path or _default_path()
        self._max = max_entries
        self._colors: list[str] = []
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._colors = [c.lower() for c in data
                                if isinstance(c, str)][:self._max]
        except Exception:
            self._colors = []

    def _save(self) -> None:
        try:
            folder = os.path.dirname(self._path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._colors, f)
        except Exception:
            pass

    def add(self, color: str) -> None:
        """Add a color to history and persist to disk.

        If the color already exists (case-insensitive), moves it to the
        front of the list instead of adding a duplicate. Empty strings
        and None are silently ignored.

        Args:
            color: Hex color string like "#ff5733". Lowercased on save.
        """
        if not color:
            return
        self._load()
        color = color.lower()
        if color in self._colors:
            self._colors.remove(color)
        self._colors.insert(0, color)
        self._colors = self._colors[:self._max]
        self._save()

    def all(self) -> list[str]:
        """Return a copy of the current list, most recent first."""
        self._load()
        return list(self._colors)

    def clear(self) -> None:
        """Remove all saved colors and persist the empty list."""
        self._loaded = True
        self._colors = []
        self._save()
