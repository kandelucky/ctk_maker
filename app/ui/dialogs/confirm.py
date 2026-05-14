"""Modal yes/no dialog with custom OK / Cancel labels."""

from __future__ import annotations

import tkinter as tk

from app.ui.dialog_utils import safe_grab_set
from app.ui.dialogs._base import DarkDialog
from app.ui.dialogs._colors import _ABT_BG, _ABT_FG
from app.ui.system_fonts import ui_font


class ConfirmDialog(DarkDialog):
    """Modal yes/no dialog with customisable button labels. Built as a
    ``CTkToplevel`` (via ``DarkDialog``) with raw-tk content so the
    confirm/cancel button text can be any language — native
    ``messagebox.askokcancel`` hardcodes OS-locale "OK" / "Cancel"
    which doesn't fit the in-app copy.
    """

    def __init__(
        self, parent, title: str, message: str,
        ok_text: str = "OK", cancel_text: str = "Cancel",
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.result: bool = False
        self._build(message, ok_text, cancel_text)
        self.update_idletasks()
        W = max(360, self.winfo_reqwidth())
        H = self.winfo_reqheight()
        self.place_centered(W, H, parent)
        self.lift()
        self.focus_set()
        safe_grab_set(self)
        self.reveal()

    def _build(
        self, message: str, ok_text: str, cancel_text: str,
    ) -> None:
        tk.Frame(self, bg=_ABT_BG, height=20).pack()
        tk.Label(
            self, text=message,
            bg=_ABT_BG, fg=_ABT_FG, font=ui_font(10),
            justify="left", wraplength=380,
        ).pack(padx=24, pady=(0, 16))
        btn_row = tk.Frame(self, bg=_ABT_BG)
        btn_row.pack(pady=(0, 20))
        tk.Button(
            btn_row, text=cancel_text, command=self._on_cancel,
            bg="#3a3a3a", fg=_ABT_FG, activebackground="#4a4a4a",
            activeforeground=_ABT_FG, relief="flat", bd=0,
            font=ui_font(10), padx=20, pady=4, cursor="hand2",
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            btn_row, text=ok_text, command=self._on_ok,
            bg="#6366f1", fg="#ffffff", activebackground="#4f46e5",
            activeforeground="#ffffff", relief="flat", bd=0,
            font=ui_font(10), padx=20, pady=4, cursor="hand2",
        ).pack(side="left")
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._on_ok())

    def _on_ok(self) -> None:
        self.result = True
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = False
        self.destroy()
