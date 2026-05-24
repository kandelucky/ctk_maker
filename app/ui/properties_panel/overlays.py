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
from tkinter import font as tkfont
from typing import Callable


# =====================================================================
# Placer helpers — low-level bbox + place math
# =====================================================================
_MEASURE_FONT_CACHE: dict[str, "tkfont.Font"] = {}


def _measure_text(widget: tk.Widget, text: str) -> int:
    """Pixel width of ``text`` in ``widget``'s font. Caches one Font per
    font spec — a fresh ``tkfont.Font`` per call would leak Tcl named
    fonts, and these placers run on every scroll / reposition."""
    spec = str(widget.cget("font"))
    font = _MEASURE_FONT_CACHE.get(spec)
    if font is None:
        font = tkfont.Font(font=widget.cget("font"))
        _MEASURE_FONT_CACHE[spec] = font
    return font.measure(text)
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
    # Reserve an extra 4px beyond the button band so the value box reads as
    # its own box with a gap before the buttons (the [ value ] … [ btns ]
    # rhythm), not a continuous block.
    widget.place(
        x=x + 4, y=y + 3,
        width=max(1, w - _IMAGE_BTN_RESERVE - 8),
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
SLOT_BOUND_COLOR_SWATCH = "bound_color_swatch"
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
SLOT_EVENT_DROPDOWN = "event_dropdown"


def place_bind_clear(
    tree: tk.Widget, widget: tk.Widget, iid: str,
) -> None:
    """Right-edge ✕ button for unbinding a bound property. Sits at the
    far right of the value cell — when a row is bound the literal
    editor is skipped (no swatch / pencil / spinner there), so this
    spot is always free.
    """
    _place_value_cell_right(tree, widget, iid, width=14, pad_y=4)


def place_bound_color_swatch(
    tree: tk.Widget, widget: tk.Widget, iid: str,
) -> None:
    """Small clickable swatch for a variable-bound color row. Sits at
    the right edge with a 22 px offset so it doesn't collide with the
    ✕ unbind button (which lives at the far right via place_bind_clear,
    14 px wide + 4 px right margin = 18 px reserved + 4 px gap).
    """
    try:
        bbox = tree.bbox(iid, "value")
    except tk.TclError:
        bbox = ()
    if not bbox:
        widget.place_forget()
        return
    x, y, w, h = bbox
    SWATCH_W = 22
    RIGHT_OFFSET = 22  # leaves room for the 14-px ✕ + gap
    pad_y = 4
    widget.place(
        x=x + w - SWATCH_W - RIGHT_OFFSET, y=y + pad_y,
        width=SWATCH_W, height=max(1, h - pad_y * 2),
    )
    widget.lift()


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


def place_event_dropdown(
    tree: tk.Widget, widget: tk.Widget, iid: str,
) -> None:
    """``▾`` dropdown button on a target / function row. Sits left
    of the ``[✕]`` unbind button (when one is present on the same
    row) so both fit at the right edge — 20px wide + 4px gap from
    the 14px ✕ + 4px right margin = 22px offset reserved.
    """
    try:
        bbox = tree.bbox(iid, "value")
    except tk.TclError:
        bbox = ()
    if not bbox:
        widget.place_forget()
        return
    x, y, w, h = bbox
    BTN_W = 20
    RIGHT_OFFSET = 22
    pad_y = 4
    widget.place(
        x=x + w - BTN_W - RIGHT_OFFSET, y=y + pad_y,
        width=BTN_W, height=max(1, h - pad_y * 2),
    )
    widget.lift()


# v1.38 — Variable type chip slot. Used by the Local Variables read-
# only list in the Window properties panel to surface the 3-letter
# type abbreviation (``str`` / ``flt`` / ``bol`` / ``col``…) at the
# left edge of the value cell, dimmed so it reads as a label not a
# value. The actual value text in the cell is padded with leading
# spaces so it lands clear of this chip.
SLOT_VAR_TYPE_CHIP = "var_type_chip"


def place_var_type_chip(
    tree: tk.Widget, widget: tk.Widget, iid: str,
) -> None:
    """Right-edge dim chip on a Variables-list row — sits at the
    right side of the tree column (``#0``), directly next to the
    variable name. Fixed ~30 px so every chip column-aligns
    regardless of the row's name length.
    """
    try:
        bbox = tree.bbox(iid, "#0")
    except tk.TclError:
        bbox = ()
    if not bbox:
        widget.place_forget()
        return
    x, y, w, h = bbox
    WIDTH = 30
    pad_y = 3
    widget.place(
        x=x + w - WIDTH - 4, y=y + pad_y,
        width=WIDTH, height=max(1, h - pad_y * 2),
    )
    widget.lift()


# v1.38 — Color swatch slot on the Variables list. Color rows wear
# the ``col`` chip in the name column same as the other types AND a
# real-hue swatch at the left of the value column, followed by the
# hex code text. ``values`` is padded with leading spaces so the hex
# lands clear of the swatch.
SLOT_VAR_COLOR_SWATCH = "var_color_swatch"


def place_var_color_swatch(
    tree: tk.Widget, widget: tk.Widget, iid: str,
) -> None:
    _place_value_cell_left(tree, widget, iid, width=24, pad_y=3)


# CTkScript model — the Scripts group rows. The value cell holds an
# action chip ("Edit Script" / "Add Script"); the name column (#0)
# holds the file location, left-elided so the tail stays visible.
SLOT_SCRIPT_NAME_CHIP = "script_name_chip"
SLOT_SCRIPT_PATH = "script_path"

# Events group — one-line handler row. The target (script) is boxed in the
# name column (#0) with a ✕ remove button; the method box + ▾ picker live in
# the value column via the shared SLOT_TEXT_VALUE / SLOT_EVENT_DROPDOWN slots.
SLOT_NAME_BOX = "name_box"
SLOT_NAME_BOX_CLEAR = "name_box_clear"
SLOT_NAME_BOX_BUTTON = "name_box_button"


def place_script_name_chip(
    tree: tk.Widget, widget: tk.Widget, iid: str,
) -> None:
    """Action label on an attached-script row — bounded to the left part
    of the value cell (mirrors place_text_value) so its lighter tint
    frees the right edge for the +/× icon, which then reads as a
    separate box rather than merging into the action block."""
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


def place_script_path(
    tree: tk.Widget, widget: tk.Widget, iid: str,
) -> None:
    """Path label in the name column (#0) of an attached-script row.
    Left-elides the stored full path (``widget._full_text``) so the
    tail — the file name — stays visible when the column is too narrow;
    a hover tooltip carries the complete path."""
    try:
        bbox = tree.bbox(iid, "#0")
    except tk.TclError:
        bbox = ()
    if not bbox:
        widget.place_forget()
        return
    x, y, w, h = bbox
    full = getattr(widget, "_full_text", "") or widget.cget("text")
    avail = max(1, w - 6)

    def measure(s: str) -> int:
        return _measure_text(widget, s)
    text = full
    if measure(full) > avail and len(full) > 1:
        i = 0
        while i < len(full) - 1 and measure("…" + full[i:]) > avail:
            i += 1
        text = "…" + full[i:]
    if widget.cget("text") != text:
        widget.configure(text=text)
    widget.place(x=x, y=y, width=w, height=max(1, h))
    widget.lift()


def place_script_open_label(
    tree: tk.Widget, widget: tk.Widget, iid: str,
) -> None:
    """"Open <name>" action label in a script row's value cell. Keeps
    the leading "Open " (``widget._prefix_len`` chars); elides the
    trailing name with "…" when the cell is too narrow. Width leaves
    room for the × detach icon at the right edge."""
    try:
        bbox = tree.bbox(iid, "value")
    except tk.TclError:
        bbox = ()
    if not bbox:
        widget.place_forget()
        return
    x, y, w, h = bbox
    # Bounded value box (mirrors place_text_value): the lighter tint
    # covers only the left part of the cell, freeing the right edge so
    # the × detach button reads as a separate box — the same two-box
    # rhythm as a variable row's [value] … [🔗]. The leading prefix
    # ("Edit [") and trailing suffix ("]") are preserved — only the name
    # between them elides.
    avail = max(1, w - 40)
    full = getattr(widget, "_full_text", "") or widget.cget("text")
    prefix_len = getattr(widget, "_prefix_len", 0)
    suffix = getattr(widget, "_suffix", "")

    def measure(s: str) -> int:
        return _measure_text(widget, s)
    text = full
    if measure(full) > avail:
        end = len(full) - len(suffix)
        j = end
        while j > prefix_len and measure(full[:j] + "…" + suffix) > avail:
            j -= 1
        if j < end:
            text = full[:j] + "…" + suffix
    if widget.cget("text") != text:
        widget.configure(text=text)
    widget.place(
        x=x + 4, y=y + 3,
        width=max(1, w - 32), height=max(1, h - 6),
    )
    widget.lift()


def place_name_box(tree: tk.Widget, widget: tk.Widget, iid: str) -> None:
    """Boxed value in the name column (#0) — the middle slot, reserving the
    left edge for the ✕ button and the right edge for the ▾ picker, so the
    row reads ``✕ [ value ] ▾``. Elides ``widget._full_text`` from the end
    when the cell is too narrow."""
    try:
        bbox = tree.bbox(iid, "#0")
    except tk.TclError:
        bbox = ()
    if not bbox:
        widget.place_forget()
        return
    x, y, w, h = bbox
    avail = max(1, w - 60)
    full = getattr(widget, "_full_text", "") or widget.cget("text")

    def measure(s: str) -> int:
        return _measure_text(widget, s)
    text = full
    if measure(full) > avail and len(full) > 1:
        i = len(full)
        while i > 1 and measure(full[:i] + "…") > avail:
            i -= 1
        text = full[:i] + "…"
    if widget.cget("text") != text:
        widget.configure(text=text)
    widget.place(
        x=x + 24, y=y + 3,
        width=max(1, w - 52), height=max(1, h - 6),
    )
    widget.lift()


def place_name_box_button(tree: tk.Widget, widget: tk.Widget, iid: str) -> None:
    """Right-edge button in the name column (#0) — the target picker ▾.
    Mirrors place_enum_button's geometry so it lines up with the value-
    column ▾."""
    try:
        bbox = tree.bbox(iid, "#0")
    except tk.TclError:
        bbox = ()
    if not bbox:
        widget.place_forget()
        return
    x, y, w, h = bbox
    widget.place(
        x=x + w - 20 - 4, y=y + 4,
        width=20, height=max(1, h - 8),
    )
    widget.lift()


def place_name_clear_left(tree: tk.Widget, widget: tk.Widget, iid: str) -> None:
    """✕ at the LEFT edge of the name column (#0) — the two-stage delete
    button, sitting before the boxed value."""
    try:
        bbox = tree.bbox(iid, "#0")
    except tk.TclError:
        bbox = ()
    if not bbox:
        widget.place_forget()
        return
    x, y, w, h = bbox
    widget.place(
        x=x + 4, y=y + 4,
        width=16, height=max(1, h - 8),
    )
    widget.lift()


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
