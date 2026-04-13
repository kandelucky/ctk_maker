from pathlib import Path

import customtkinter as ctk
from PIL import Image

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
DEFAULT_SIZE = 16

_cache: dict[tuple[str, int], ctk.CTkImage] = {}


def load_icon(name: str, size: int = DEFAULT_SIZE) -> ctk.CTkImage | None:
    key = (name, size)
    if key in _cache:
        return _cache[key]
    path = ICON_DIR / f"{name}.png"
    if not path.exists():
        return None
    img = Image.open(path).convert("RGBA")
    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    _cache[key] = ctk_img
    return ctk_img
