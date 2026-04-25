"""Font editor: family-name preview + open / clear buttons.

Mirrors ``ImageEditor`` — same overlay slots, same picker-launch
shape — because the property is conceptually identical: a single
referenceable identifier with a heavyweight modal picker. The two
editors deliberately reuse ``SLOT_IMAGE_VALUE`` /
``SLOT_IMAGE_BUTTONS`` because those slots are keyed per
``(iid, slot)`` and font + image properties never share a row.

The displayed value is the family name (`"(default)"` when ``None``,
i.e. inherit from project / type defaults). Clearing sets the
property back to ``None`` so cascade resolution kicks in again.
"""

from __future__ import annotations

import tkinter as tk

from ..constants import TEXT_BG, TREE_BG
from ..overlays import (
    SLOT_IMAGE_BUTTONS,
    SLOT_IMAGE_VALUE,
    place_image_buttons,
    place_image_value,
)
from .base import Editor


def _display(value) -> str:
    if not value:
        return "(default)"
    return str(value)


class FontEditor(Editor):
    def populate(self, panel, iid, pname, prop, value) -> None:
        value_label = tk.Label(
            panel.tree, text=_display(value),
            bg=TEXT_BG, fg="#cccccc",
            font=("Segoe UI", 11), anchor="w",
            relief="flat", bd=0, padx=6,
        )
        panel.overlays.add(
            iid, SLOT_IMAGE_VALUE, value_label, place_image_value,
        )

        btn_frame = tk.Frame(panel.tree, bg=TREE_BG)
        open_btn = tk.Label(
            btn_frame, text="⋯", bg=TREE_BG, fg="#aaaaaa",
            font=("Segoe UI", 14, "bold"),
            padx=4, cursor="hand2",
        )
        open_btn.pack(side="left", padx=(0, 2))
        open_btn.bind(
            "<Button-1>",
            lambda _e, p=pname: panel._pick_font(p),
        )
        clear_btn = tk.Label(
            btn_frame, text="✕", bg=TREE_BG, fg="#aaaaaa",
            font=("Segoe UI", 11, "bold"),
            padx=4, cursor="hand2",
        )
        clear_btn.pack(side="left")
        clear_btn.bind(
            "<Button-1>",
            lambda _e, p=pname: panel._commit_prop(p, None),
        )
        panel.overlays.add(
            iid, SLOT_IMAGE_BUTTONS, btn_frame, place_image_buttons,
        )

    def refresh(self, panel, iid, pname, prop, value) -> None:
        overlay = panel.overlays.get(iid, SLOT_IMAGE_VALUE)
        if overlay is None:
            return
        try:
            overlay.configure(text=_display(value))
        except tk.TclError:
            pass

    def set_disabled(self, panel, iid, pname, prop, disabled) -> None:
        val = panel.overlays.get(iid, SLOT_IMAGE_VALUE)
        if val is not None:
            try:
                val.configure(fg="#555555" if disabled else "#cccccc")
            except tk.TclError:
                pass
        btns = panel.overlays.get(iid, SLOT_IMAGE_BUTTONS)
        if btns is not None:
            for child in btns.winfo_children():
                try:
                    child.configure(
                        fg="#555555" if disabled else "#cccccc",
                        cursor="arrow" if disabled else "hand2",
                    )
                except tk.TclError:
                    pass

    def on_double_click(self, panel, pname, prop, event) -> bool:
        panel._pick_font(pname)
        return True
