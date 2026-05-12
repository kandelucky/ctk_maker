"""Blocking single-line rename modal — used by workspace right-click
menu and Object Tree right-click menu.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from app.ui import style
from app.ui.managed_window import ManagedToplevel


class RenameDialog(ManagedToplevel):
    """Blocking rename dialog. Rejects empty names: bells, restores the
    original value in the entry, keeps the dialog open. ``__init__``
    blocks until the user closes the dialog (mirrors the previous
    ``simpledialog.Dialog`` contract — callers don't need to call
    ``wait_window`` themselves).
    """

    window_title = "Rename Widget"
    default_size = (340, 170)
    min_size = (320, 170)
    fg_color = style.BG
    panel_padding = (0, 0)
    modal = True
    window_resizable = (False, False)

    def __init__(self, parent, initial_value: str):
        self._initial = initial_value
        self.result: str | None = None
        self._name_var = tk.StringVar(master=parent, value=initial_value)
        super().__init__(parent)
        self.bind("<Return>", lambda _e: self._on_ok())
        self.after(80, self._focus_entry)
        # Block the caller until the dialog closes — preserves the
        # synchronous contract the old simpledialog.Dialog gave us so
        # existing callers can still ``if dialog.result: ...`` straight
        # after construction.
        self.wait_window(self)

    def default_offset(self, parent) -> tuple[int, int]:
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            w, h = self.default_size
            return (
                max(0, px + (pw - w) // 2),
                max(0, py + (ph - h) // 2),
            )
        except tk.TclError:
            return (100, 100)

    def _focus_entry(self) -> None:
        try:
            self._entry.focus_set()
            self._entry.select_range(0, tk.END)
        except tk.TclError:
            pass

    def build_content(self) -> ctk.CTkFrame:
        container = ctk.CTkFrame(self, fg_color="transparent")

        body = ctk.CTkFrame(container, fg_color="transparent")
        body.pack(padx=20, pady=(18, 10), fill="x")

        style.styled_label(body, "New name:").pack(
            anchor="w", pady=(0, 4),
        )
        self._entry = style.styled_entry(
            body, textvariable=self._name_var,
        )
        self._entry.pack(fill="x")

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(4, 16))
        footer.grid_columnconfigure(0, weight=1, uniform="btn")
        footer.grid_columnconfigure(1, weight=1, uniform="btn")
        style.secondary_button(
            footer, "Cancel", command=self._on_cancel,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        style.primary_button(
            footer, "OK", command=self._on_ok,
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        return container

    def _on_ok(self) -> None:
        value = self._name_var.get().strip()
        if not value:
            self.bell()
            self._name_var.set(self._initial)
            self._focus_entry()
            return
        self.result = value
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()
