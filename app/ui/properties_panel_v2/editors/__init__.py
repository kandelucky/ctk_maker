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
from .segment_values import SegmentValuesEditor

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
    "stretch": _ENUM,
    "grid_sticky": _ENUM,
    "wrap": _ENUM,
    "text_position": _ENUM,
    "tab_bar_align": _ENUM,
    "tab_bar_position": _ENUM,
    "segment_initial": _ENUM,
    "segment_values": SegmentValuesEditor(),
}


def get_editor(ptype: str) -> Editor:
    return _EDITORS.get(ptype, _FALLBACK)


__all__ = ["Editor", "get_editor"]
