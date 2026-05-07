"""Segment values editor — single full-width button that opens the
SegmentValuesDialog table editor.

Used by CTkSegmentedButton for the ``values`` row. The whole value
column is one button labeled "Edit Segments..." — no first-line
preview, no separate pencil. The user goes through the dialog every
time, so a single big affordance is more honest than a faked-text
read-only preview.
"""

from __future__ import annotations

import tkinter as tk

from ..overlays import SLOT_TEXT_VALUE, place_text_value
from .base import Editor


# Slightly raised colours so the cell reads as a button, not a label.
BTN_BG = "#3c3c3c"
BTN_HOVER = "#4a4a4a"
BTN_FG = "#cccccc"
BTN_FG_DISABLED = "#666666"


class SegmentValuesEditor(Editor):
    @staticmethod
    def _label_for(panel, pname: str) -> str:
        if pname == "tab_names":
            return "Edit Tabs..."
        node = panel.project.get_widget(panel.current_id)
        if node is not None and node.widget_type == "CTkSegmentedButton":
            return "Edit Segments..."
        return "Edit Values..."

    def populate(self, panel, iid, pname, prop, value) -> None:
        label_text = self._label_for(panel, pname)
        btn = tk.Label(
            panel.tree, text=label_text,
            bg=BTN_BG, fg=BTN_FG,
            font=("Segoe UI", 10), anchor="center",
            relief="flat", bd=0, cursor="hand2",
        )
        btn.bind(
            "<Enter>",
            lambda _e: btn.configure(bg=BTN_HOVER) if str(
                btn.cget("cursor"),
            ) == "hand2" else None,
        )
        btn.bind("<Leave>", lambda _e: btn.configure(bg=BTN_BG))
        btn.bind(
            "<Button-1>",
            lambda _e, p=pname: panel._open_segment_values_editor(p),
        )
        panel.overlays.add(
            iid, SLOT_TEXT_VALUE, btn, place_text_value,
        )

    def refresh(self, panel, iid, pname, prop, value) -> None:
        # Static "Edit Segments..." label — nothing to refresh.
        return

    def set_disabled(self, panel, iid, pname, prop, disabled) -> None:
        btn = panel.overlays.get(iid, SLOT_TEXT_VALUE)
        if btn is None:
            return
        try:
            btn.configure(
                fg=BTN_FG_DISABLED if disabled else BTN_FG,
                cursor="arrow" if disabled else "hand2",
            )
        except tk.TclError:
            pass

    def on_double_click(self, panel, pname, prop, event) -> bool:
        panel._open_segment_values_editor(pname)
        return True
