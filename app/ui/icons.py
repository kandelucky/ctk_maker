import tkinter as tk
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageTk

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
DEFAULT_SIZE = 16

_ctk_cache: dict[tuple[str, int], ctk.CTkImage] = {}
_tk_cache: dict[tuple[str, int], tk.PhotoImage] = {}


def load_icon(name: str, size: int = DEFAULT_SIZE) -> ctk.CTkImage | None:
    key = (name, size)
    if key in _ctk_cache:
        return _ctk_cache[key]
    path = ICON_DIR / f"{name}.png"
    if not path.exists():
        return None
    img = Image.open(path).convert("RGBA")
    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    _ctk_cache[key] = ctk_img
    return ctk_img


def load_tk_icon(name: str, size: int = DEFAULT_SIZE) -> tk.PhotoImage | None:
    """Load an icon as a tk.PhotoImage (for tk.Menu which doesn't accept CTkImage)."""
    key = (name, size)
    if key in _tk_cache:
        return _tk_cache[key]
    path = ICON_DIR / f"{name}.png"
    if not path.exists():
        return None
    img = Image.open(path).convert("RGBA")
    if img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)
    photo = ImageTk.PhotoImage(img)
    _tk_cache[key] = photo
    return photo
