"""Modal dialog with up to three custom-labelled buttons.

Used by cascade-edit flows that need a richer prompt than yes/no.
"""

from __future__ import annotations

import tkinter as tk

from app.ui.dialog_utils import prepare_dialog, reveal_dialog, safe_grab_set
from app.ui.dialogs._colors import _ABT_BG, _ABT_FG
from app.ui.system_fonts import ui_font


class ChoiceDialog(tk.Toplevel):
    """Modal dialog with up to three custom-labelled buttons. Used by
    cascade-edit flows that need a richer prompt than a yes/no — e.g.
    "the new font replaces the type default. Apply to all widgets too,
    or only those without a per-widget override?".

    ``self.result`` is the string key of the picked button or
    ``None`` on Cancel / Escape / window close.
    """

    def __init__(
        self, parent, title: str, message: str,
        primary: tuple[str, str],
        secondary: tuple[str, str] | None = None,
        cancel_text: str = "Cancel",
    ) -> None:
        super().__init__(parent)
        prepare_dialog(self)
        self.title(title)
        self.configure(bg=_ABT_BG)
        self.resizable(False, False)
        self.transient(parent)
        self.result: str | None = None
        self._build(message, primary, secondary, cancel_text)
        self.update_idletasks()
        W = max(440, self.winfo_reqwidth())
        H = self.winfo_reqheight()
        px = parent.winfo_rootx() + parent.winfo_width() // 2
        py = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"{W}x{H}+{px - W // 2}+{py - H // 2}")
        self.lift()
        self.focus_set()
        safe_grab_set(self)
        reveal_dialog(self)

    def _build(
        self, message: str,
        primary: tuple[str, str],
        secondary: tuple[str, str] | None,
        cancel_text: str,
    ) -> None:
        tk.Frame(self, bg=_ABT_BG, height=20).pack()
        tk.Label(
            self, text=message,
            bg=_ABT_BG, fg=_ABT_FG, font=ui_font(10),
            justify="left", wraplength=420,
        ).pack(padx=24, pady=(0, 16))
        btn_row = tk.Frame(self, bg=_ABT_BG)
        btn_row.pack(pady=(0, 20))
        tk.Button(
            btn_row, text=cancel_text, command=self._on_cancel,
            bg="#3a3a3a", fg=_ABT_FG, activebackground="#4a4a4a",
            activeforeground=_ABT_FG, relief="flat", bd=0,
            font=ui_font(10), padx=16, pady=4, cursor="hand2",
        ).pack(side="left", padx=(0, 8))
        if secondary is not None:
            sec_key, sec_text = secondary
            tk.Button(
                btn_row, text=sec_text,
                command=lambda: self._pick(sec_key),
                bg="#3a3a3a", fg=_ABT_FG, activebackground="#4a4a4a",
                activeforeground=_ABT_FG, relief="flat", bd=0,
                font=ui_font(10), padx=16, pady=4, cursor="hand2",
            ).pack(side="left", padx=(0, 8))
        prim_key, prim_text = primary
        tk.Button(
            btn_row, text=prim_text,
            command=lambda: self._pick(prim_key),
            bg="#6366f1", fg="#ffffff", activebackground="#4f46e5",
            activeforeground="#ffffff", relief="flat", bd=0,
            font=ui_font(10), padx=16, pady=4, cursor="hand2",
        ).pack(side="left")
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._pick(prim_key))

    def _pick(self, key: str) -> None:
        self.result = key
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()
