"""Color editor: persistent swatch overlay + color picker dialog."""

from __future__ import annotations

import tkinter as tk

from ..constants import VALUE_BG
from ..overlays import SLOT_COLOR, place_color_swatch
from .base import Editor

# CTk-only sentinel values that Tk's colour parser rejects. Map them
# to a readable swatch background so editors can render without
# tripping `_tkinter.TclError: unknown color name "transparent"`.
_CTK_SENTINEL_BG = {
    "transparent": "#2b2b2b",
}


def _swatch_bg(value) -> str:
    if not value:
        return VALUE_BG
    text = str(value)
    if text in _CTK_SENTINEL_BG:
        return _CTK_SENTINEL_BG[text]
    return text


class ColorEditor(Editor):
    def populate(self, panel, iid, pname, prop, value) -> None:
        try:
            overlay = tk.Frame(
                panel.tree, bg=_swatch_bg(value),
                highlightthickness=1, highlightbackground="#3a3a3a",
                cursor="hand2",
            )
        except tk.TclError:
            # Any other unrecognised colour — fall back to the neutral
            # value-bg so the editor still renders.
            overlay = tk.Frame(
                panel.tree, bg=VALUE_BG,
                highlightthickness=1, highlightbackground="#3a3a3a",
                cursor="hand2",
            )
        overlay.bind(
            "<Button-1>",
            lambda _e, p=pname: panel._pick_color(p),
        )
        panel.overlays.add(iid, SLOT_COLOR, overlay, place_color_swatch)

    def refresh(self, panel, iid, pname, prop, value) -> None:
        overlay = panel.overlays.get(iid, SLOT_COLOR)
        if overlay is None or not value:
            return
        try:
            overlay.configure(bg=_swatch_bg(value))
        except tk.TclError:
            pass

    def set_disabled(self, panel, iid, pname, prop, disabled) -> None:
        overlay = panel.overlays.get(iid, SLOT_COLOR)
        if overlay is None:
            return
        node = panel.project.get_widget(panel.current_id)
        val = node.properties.get(pname) if node else None
        try:
            overlay.configure(
                bg="#444444" if disabled else _swatch_bg(val),
                cursor="arrow" if disabled else "hand2",
            )
        except tk.TclError:
            pass

    def on_double_click(self, panel, pname, prop, event) -> bool:
        panel._pick_color(pname)
        return True
