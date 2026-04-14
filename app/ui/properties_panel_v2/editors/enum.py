"""Enum editor: ▾ button that opens a native tk.Menu popup.

Used for `anchor`, `compound`, and `justify` property types.
"""

from __future__ import annotations

import tkinter as tk

from ..constants import TREE_BG
from ..overlays import SLOT_ENUM_BUTTON, place_enum_button
from .base import Editor


class EnumEditor(Editor):
    def populate(self, panel, iid, pname, prop, value) -> None:
        ptype = prop["type"]
        btn = tk.Label(
            panel.tree, text="▾",
            bg=TREE_BG, fg="#aaaaaa",
            font=("Segoe UI", 12, "bold"),
            cursor="hand2", borderwidth=0,
        )
        btn.bind(
            "<Button-1>",
            lambda _e, p=pname, t=ptype, b=btn:
                panel._popup_enum_menu_at(
                    p, t,
                    b.winfo_rootx(),
                    b.winfo_rooty() + b.winfo_height(),
                ),
        )
        panel.overlays.add(iid, SLOT_ENUM_BUTTON, btn, place_enum_button)

    def set_disabled(self, panel, iid, pname, prop, disabled) -> None:
        btn = panel.overlays.get(iid, SLOT_ENUM_BUTTON)
        if btn is None:
            return
        try:
            btn.configure(
                fg="#555555" if disabled else "#aaaaaa",
                cursor="arrow" if disabled else "hand2",
            )
        except tk.TclError:
            pass

    def on_double_click(self, panel, pname, prop, event) -> bool:
        panel._popup_enum_menu_at(
            pname, prop["type"], event.x_root, event.y_root,
        )
        return True
