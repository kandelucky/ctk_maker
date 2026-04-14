"""Lucide icon loader with on-the-fly tinting.

Icons ship as white PNGs (produced by tools/download.mjs). At load
time we recolor every non-transparent pixel via PIL so each call site
can pick its own color without re-rendering the assets.

Two APIs:
    load_icon(name, size, color)    -> ctk.CTkImage (default widget image)
    load_tk_icon(name, size, color) -> tk.PhotoImage (tk.Menu wants this)
"""

import tkinter as tk
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageTk

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
DEFAULT_SIZE = 16
DEFAULT_COLOR = "#888888"

_ctk_cache: dict[tuple[str, int, str], ctk.CTkImage] = {}
_tk_cache: dict[tuple[str, int, str], tk.PhotoImage] = {}


def load_icon(
    name: str,
    size: int = DEFAULT_SIZE,
    color: str = DEFAULT_COLOR,
) -> ctk.CTkImage | None:
    key = (name, size, color)
    if key in _ctk_cache:
        return _ctk_cache[key]
    tinted = _load_tinted(name, size, color)
    if tinted is None:
        return None
    ctk_img = ctk.CTkImage(
        light_image=tinted, dark_image=tinted, size=(size, size),
    )
    _ctk_cache[key] = ctk_img
    return ctk_img


def load_tk_icon(
    name: str,
    size: int = DEFAULT_SIZE,
    color: str = DEFAULT_COLOR,
) -> tk.PhotoImage | None:
    """Load an icon as a tk.PhotoImage (for tk.Menu which doesn't accept CTkImage)."""
    key = (name, size, color)
    if key in _tk_cache:
        return _tk_cache[key]
    tinted = _load_tinted(name, size, color)
    if tinted is None:
        return None
    photo = ImageTk.PhotoImage(tinted)
    _tk_cache[key] = photo
    return photo


# ----------------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------------
def _load_tinted(name: str, size: int, color: str) -> Image.Image | None:
    path = ICON_DIR / f"{name}.png"
    if not path.exists():
        return None
    src = Image.open(path).convert("RGBA")
    r, g, b = _parse_hex_color(color)
    solid = Image.new("RGBA", src.size, (r, g, b, 255))
    empty = Image.new("RGBA", src.size, (0, 0, 0, 0))
    alpha = src.split()[3]
    tinted = Image.composite(solid, empty, alpha)
    if tinted.size != (size, size):
        tinted = tinted.resize((size, size), Image.LANCZOS)
    return tinted


def _parse_hex_color(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return (
        int(value[0:2], 16),
        int(value[2:4], 16),
        int(value[4:6], 16),
    )
