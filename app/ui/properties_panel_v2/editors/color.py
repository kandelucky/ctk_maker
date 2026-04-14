"""Color editor: persistent swatch overlay + color picker dialog."""

from __future__ import annotations

import tkinter as tk

from ..constants import VALUE_BG
from ..overlays import SLOT_COLOR, place_color_swatch
from .base import Editor


class ColorEditor(Editor):
    def populate(self, panel, iid, pname, prop, value) -> None:
        overlay = tk.Frame(
            panel.tree, bg=str(value) if value else VALUE_BG,
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
        if overlay is not None and value:
            try:
                overlay.configure(bg=str(value))
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
                bg="#444444" if disabled else (str(val) or VALUE_BG),
                cursor="arrow" if disabled else "hand2",
            )
        except tk.TclError:
            pass

    def on_double_click(self, panel, pname, prop, event) -> bool:
        panel._pick_color(pname)
        return True
