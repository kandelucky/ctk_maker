"""Image editor: filename preview + open/clear buttons."""

from __future__ import annotations

import os
import tkinter as tk

from ..constants import TEXT_BG, TREE_BG, VALUE_BG
from ..overlays import (
    SLOT_IMAGE_BUTTONS,
    SLOT_IMAGE_VALUE,
    place_image_buttons,
    place_image_value,
)
from .base import Editor


class ImageEditor(Editor):
    def populate(self, panel, iid, pname, prop, value) -> None:
        display_name = (
            os.path.basename(str(value)) if value else "(no image)"
        )
        value_label = tk.Label(
            panel.tree, text=display_name,
            bg=TEXT_BG, fg="#cccccc",
            font=("Segoe UI", 11), anchor="w",
            relief="flat", bd=0, padx=6,
        )
        panel.overlays.add(
            iid, SLOT_IMAGE_VALUE, value_label, place_image_value,
        )

        btn_frame = tk.Frame(panel.tree, bg=TREE_BG)
        open_btn = tk.Label(
            btn_frame, text="open", bg=VALUE_BG, fg="#cccccc",
            font=("Segoe UI", 10), padx=8, cursor="hand2",
        )
        open_btn.pack(side="left", padx=(0, 2))
        open_btn.bind(
            "<Button-1>",
            lambda _e, p=pname: panel._pick_image(p),
        )
        clear_btn = tk.Label(
            btn_frame, text="clear", bg=VALUE_BG, fg="#cccccc",
            font=("Segoe UI", 10), padx=8, cursor="hand2",
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
        display_name = (
            os.path.basename(str(value)) if value else "(no image)"
        )
        try:
            overlay.configure(text=display_name)
        except tk.TclError:
            pass

    def set_disabled(self, panel, iid, pname, prop, disabled) -> None:
        img_val = panel.overlays.get(iid, SLOT_IMAGE_VALUE)
        if img_val is not None:
            try:
                img_val.configure(
                    fg="#555555" if disabled else "#cccccc",
                )
            except tk.TclError:
                pass
        img_btns = panel.overlays.get(iid, SLOT_IMAGE_BUTTONS)
        if img_btns is not None:
            for child in img_btns.winfo_children():
                try:
                    child.configure(
                        fg="#555555" if disabled else "#cccccc",
                        cursor="arrow" if disabled else "hand2",
                    )
                except tk.TclError:
                    pass

    def on_double_click(self, panel, pname, prop, event) -> bool:
        panel._pick_image(pname)
        return True
