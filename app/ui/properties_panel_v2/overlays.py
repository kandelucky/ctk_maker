"""Overlay registry + placer functions for the Properties panel v2.

Phase C refactor: every persistent `.place()`-based widget that sits
on top of a tree row (color swatches, pencil buttons, enum dropdowns,
text value labels, image buttons, style preview) lives inside a
single `OverlayRegistry`.

Each registered entry is a `(widget, placer)` pair keyed by
`(iid, slot)`. The registry owns the lifetime (clear → destroy) and
fan-out repositioning after scroll / layout changes.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable


# =====================================================================
# Placer helpers — low-level bbox + place math
# =====================================================================
def _place_value_cell_left(
    tree: tk.Widget, widget: tk.Widget, iid: str,
    *, width: int, pad_y: int,
) -> None:
    try:
        bbox = tree.bbox(iid, "value")
    except tk.TclError:
        bbox = ()
    if not bbox:
        widget.place_forget()
        return
    x, y, _w, h = bbox
    widget.place(
        x=x + 4, y=y + pad_y,
        width=width, height=max(1, h - pad_y * 2),
    )
    widget.lift()


def _place_value_cell_right(
    tree: tk.Widget, widget: tk.Widget, iid: str,
    *, width: int, pad_y: int,
) -> None:
    try:
        bbox = tree.bbox(iid, "value")
    except tk.TclError:
        bbox = ()
    if not bbox:
        widget.place_forget()
        return
    x, y, w, h = bbox
    widget.place(
        x=x + w - width - 4, y=y + pad_y,
        width=width, height=max(1, h - pad_y * 2),
    )
    widget.lift()


_IMAGE_BTN_RESERVE = 50


# =====================================================================
# Named placers — one per overlay slot (stable callable identity)
# =====================================================================
def place_color_swatch(tree: tk.Widget, widget: tk.Widget, iid: str) -> None:
    _place_value_cell_left(tree, widget, iid, width=50, pad_y=4)


def place_enum_button(tree: tk.Widget, widget: tk.Widget, iid: str) -> None:
    _place_value_cell_right(tree, widget, iid, width=20, pad_y=4)


def place_text_edit_pencil(
    tree: tk.Widget, widget: tk.Widget, iid: str,
) -> None:
    _place_value_cell_right(tree, widget, iid, width=20, pad_y=4)


def place_text_value(tree: tk.Widget, widget: tk.Widget, iid: str) -> None:
    try:
        bbox = tree.bbox(iid, "value")
    except tk.TclError:
        bbox = ()
    if not bbox:
        widget.place_forget()
        return
    x, y, w, h = bbox
    widget.place(
        x=x + 4, y=y + 3,
        width=max(1, w - 32), height=max(1, h - 6),
    )
    widget.lift()


def place_image_value(tree: tk.Widget, widget: tk.Widget, iid: str) -> None:
    try:
        bbox = tree.bbox(iid, "value")
    except tk.TclError:
        bbox = ()
    if not bbox:
        widget.place_forget()
        return
    x, y, w, h = bbox
    widget.place(
        x=x + 4, y=y + 3,
        width=max(1, w - _IMAGE_BTN_RESERVE - 4),
        height=max(1, h - 6),
    )
    widget.lift()


def place_image_buttons(
    tree: tk.Widget, frame: tk.Widget, iid: str,
) -> None:
    try:
        bbox = tree.bbox(iid, "value")
    except tk.TclError:
        bbox = ()
    if not bbox:
        frame.place_forget()
        return
    x, y, w, h = bbox
    btn_width = _IMAGE_BTN_RESERVE - 4
    frame.place(
        x=x + w - btn_width - 4, y=y + 3,
        width=btn_width, height=max(1, h - 6),
    )
    frame.lift()


def place_style_preview(
    tree: tk.Widget, widget: tk.Widget, iid: str,
) -> None:
    _place_value_cell_left(tree, widget, iid, width=300, pad_y=3)


# =====================================================================
# Slot constants — one string per overlay kind
# =====================================================================
SLOT_COLOR = "color"
SLOT_ENUM_BUTTON = "enum_button"
SLOT_TEXT_VALUE = "text_value"
SLOT_TEXT_EDIT = "text_edit"
SLOT_IMAGE_VALUE = "image_value"
SLOT_IMAGE_BUTTONS = "image_buttons"
SLOT_STYLE_PREVIEW = "style_preview"


# =====================================================================
# Registry
# =====================================================================
PlacerFn = Callable[[tk.Widget, tk.Widget, str], None]


class OverlayRegistry:
    """Single source of truth for per-row overlay widgets.

    Each entry is keyed by `(iid, slot)` so a single row can own
    multiple overlays (e.g. `multiline` has both a value label and a
    pencil button). The registry owns destruction and repositioning.
    """

    def __init__(self, tree: tk.Widget):
        self._tree = tree
        self._entries: dict[
            tuple[str, str], tuple[tk.Widget, PlacerFn]
        ] = {}

    def add(
        self,
        iid: str,
        slot: str,
        widget: tk.Widget,
        placer: PlacerFn,
    ) -> None:
        self._entries[(iid, slot)] = (widget, placer)

    def get(self, iid: str, slot: str) -> tk.Widget | None:
        entry = self._entries.get((iid, slot))
        return entry[0] if entry else None

    def clear(self) -> None:
        for widget, _placer in self._entries.values():
            try:
                widget.destroy()
            except tk.TclError:
                pass
        self._entries.clear()

    def reposition_all(self) -> None:
        for (iid, _slot), (widget, placer) in self._entries.items():
            placer(self._tree, widget, iid)
