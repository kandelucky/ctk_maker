"""Multiline editor: dark text preview overlay + pencil button.

- Inline edit on double-click of the value overlay.
- Pencil opens the full TextEditorDialog for multiline editing.
"""

from __future__ import annotations

import tkinter as tk

from ..constants import TEXT_BG, TREE_BG
from ..overlays import (
    SLOT_TEXT_EDIT,
    SLOT_TEXT_VALUE,
    place_text_edit_pencil,
    place_text_value,
)
from app.ui.system_fonts import ui_font
from .base import Editor


class MultilineEditor(Editor):
    def populate(self, panel, iid, pname, prop, value) -> None:
        text_val = str(value) if value is not None else ""
        first_line = text_val.partition("\n")[0] + (
            " …" if "\n" in text_val else ""
        )
        value_label = tk.Label(
            panel.tree, text=first_line,
            bg=TEXT_BG, fg="#cccccc",
            font=ui_font(11), anchor="w",
            relief="flat", bd=0, padx=6, cursor="xterm",
        )
        value_label.bind(
            "<Double-Button-1>",
            lambda _e, p=pname: panel._edit_text_inline(p),
        )
        panel.overlays.add(
            iid, SLOT_TEXT_VALUE, value_label, place_text_value,
        )

        edit_btn = tk.Label(
            panel.tree, text="✎",
            bg=TREE_BG, fg="#aaaaaa",
            font=("Segoe UI Symbol", 12),
            cursor="hand2", borderwidth=0,
        )
        edit_btn.bind(
            "<Button-1>",
            lambda _e, p=pname, pr=prop: panel._open_text_editor(p, pr),
        )
        panel.overlays.add(
            iid, SLOT_TEXT_EDIT, edit_btn, place_text_edit_pencil,
        )

    def refresh(self, panel, iid, pname, prop, value) -> None:
        overlay = panel.overlays.get(iid, SLOT_TEXT_VALUE)
        if overlay is None:
            return
        text_val = str(value) if value is not None else ""
        first_line = text_val.partition("\n")[0] + (
            " …" if "\n" in text_val else ""
        )
        try:
            overlay.configure(text=first_line)
        except tk.TclError:
            pass

    def set_disabled(self, panel, iid, pname, prop, disabled) -> None:
        pencil = panel.overlays.get(iid, SLOT_TEXT_EDIT)
        if pencil is not None:
            try:
                pencil.configure(
                    fg="#555555" if disabled else "#aaaaaa",
                    cursor="arrow" if disabled else "hand2",
                )
            except tk.TclError:
                pass
        text_val = panel.overlays.get(iid, SLOT_TEXT_VALUE)
        if text_val is not None:
            try:
                text_val.configure(
                    fg="#555555" if disabled else "#cccccc",
                )
            except tk.TclError:
                pass

    def on_double_click(self, panel, pname, prop, event) -> bool:
        panel._edit_text_inline(pname)
        return True
