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


def place_color_clear(tree: tk.Widget, widget: tk.Widget, iid: str) -> None:
    """Small ✕ button sits at the right edge of the value cell — away
    from the swatch + hex readout on the left so the button never
    blends visually into the ``#ffffff`` text. Only drawn for schema
    props marked ``clearable`` — see ColorEditor.populate.
    """
    _place_value_cell_right(tree, widget, iid, width=14, pad_y=4)


def place_enum_button(tree: tk.Widget, widget: tk.Widget, iid: str) -> None:
    _place_value_cell_right(tree, widget, iid, width=20, pad_y=4)


def place_number_spin(tree: tk.Widget, widget: tk.Widget, iid: str) -> None:
    _place_value_cell_right(tree, widget, iid, width=14, pad_y=2)


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


def place_bind_button(
    tree: tk.Widget, widget: tk.Widget, iid: str,
) -> None:
    """Pinned to the leftmost gutter of the tree, OUTSIDE the indent
    area, so every row's icon aligns in the same vertical column
    regardless of indent depth. Tk's ``bbox(iid, "#0")`` returns the
    cell's content bbox (after indent), which would push the icon
    next to the row text — using a fixed x ignores that.
    """
    try:
        bbox = tree.bbox(iid, "#0")
    except tk.TclError:
        bbox = ()
    if not bbox:
        widget.place_forget()
        return
    _x, y, _w, h = bbox
    widget.place(
        x=4, y=y + 4,
        width=12, height=max(1, h - 8),
    )
    widget.lift()


# =====================================================================
# Slot constants — one string per overlay kind
# =====================================================================
SLOT_COLOR = "color"
SLOT_COLOR_CLEAR = "color_clear"
SLOT_ENUM_BUTTON = "enum_button"
SLOT_NUMBER_SPIN = "number_spin"
SLOT_TEXT_VALUE = "text_value"
SLOT_TEXT_EDIT = "text_edit"
SLOT_IMAGE_VALUE = "image_value"
SLOT_IMAGE_BUTTONS = "image_buttons"
SLOT_STYLE_PREVIEW = "style_preview"
SLOT_BIND_BUTTON = "bind_button"
SLOT_BIND_CLEAR = "bind_clear"
# Phase 2 visual scripting — inline buttons on Events group rows.
SLOT_EVENT_ADD = "event_add"
SLOT_EVENT_UNBIND = "event_unbind"


def place_bind_clear(
    tree: tk.Widget, widget: tk.Widget, iid: str,
) -> None:
    """Right-edge ✕ button for unbinding a bound property. Sits at the
    far right of the value cell — when a row is bound the literal
    editor is skipped (no swatch / pencil / spinner there), so this
    spot is always free.
    """
    _place_value_cell_right(tree, widget, iid, width=14, pad_y=4)


def place_event_add(
    tree: tk.Widget, widget: tk.Widget, iid: str,
) -> None:
    """``[+]`` button on event header rows in the Events group.
    Sits at the right edge of the value cell — the header preview
    text ("(2 actions)") sits on the left, the button on the right.
    Wider than the bind ✕ to make a primary action discoverable.
    """
    _place_value_cell_right(tree, widget, iid, width=20, pad_y=3)


def place_event_unbind(
    tree: tk.Widget, widget: tk.Widget, iid: str,
) -> None:
    """``[✕]`` button on bound-method rows. Mirrors place_bind_clear
    geometry so the visual rhythm matches existing unbind buttons
    elsewhere in the panel.
    """
    _place_value_cell_right(tree, widget, iid, width=14, pad_y=4)


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
