"""Editor registry for the Properties panel v2.

Maps a schema `type` string to the editor instance that handles it.
Unknown types resolve to a no-op base Editor, keeping the panel safe
against schema additions it doesn't yet know about.
"""

from __future__ import annotations

from .base import Editor
from .boolean import BooleanEditor
from .color import ColorEditor
from .enum import EnumEditor
from .image import ImageEditor
from .multiline import MultilineEditor
from .number import NumberEditor

_FALLBACK = Editor()
_ENUM = EnumEditor()

_EDITORS: dict[str, Editor] = {
    "color": ColorEditor(),
    "boolean": BooleanEditor(),
    "multiline": MultilineEditor(),
    "image": ImageEditor(),
    "number": NumberEditor(),
    "anchor": _ENUM,
    "compound": _ENUM,
    "justify": _ENUM,
    "orientation": _ENUM,
    "grid_style": _ENUM,
    "layout_type": _ENUM,
    "pack_side": _ENUM,
    "pack_fill": _ENUM,
    "grid_sticky": _ENUM,
}


def get_editor(ptype: str) -> Editor:
    return _EDITORS.get(ptype, _FALLBACK)


__all__ = ["Editor", "get_editor"]
