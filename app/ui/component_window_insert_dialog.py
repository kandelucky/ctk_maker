"""Modal — confirmation gate before inserting a Window-type
component as a new Dialog document. Window components don't slot
into the current window the way fragments do; instead they create
their own Toplevel. The confirmation makes the side-effect explicit
since drag/double-click look the same as for fragments.

``result`` is True on Insert, False on Cancel.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk


class ComponentWindowInsertDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        component_name: str,
        target_doc_name: str,
    ):
        super().__init__(parent)
        self.title("Insert Window component")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color="#1a1a1a")

        self.result: bool = False

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(padx=22, pady=(20, 8), fill="x")

        ctk.CTkLabel(
            body, text="Insert as a new Dialog?",
            font=("Segoe UI", 14, "bold"),
            text_color="#e6e6e6", anchor="w",
        ).pack(anchor="w", pady=(0, 6))
        ctk.CTkLabel(
            body,
            text=(
                f"\"{component_name}\" is a Window component."
            ),
            font=("Segoe UI", 10),
            text_color="#bdbdbd", anchor="w",
            wraplength=380, justify="left",
        ).pack(anchor="w", pady=(0, 14))

        info = ctk.CTkFrame(body, fg_color="#2a2118", corner_radius=4)
        info.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            info,
            text=(
                "• A new Toplevel will be added to this project.\n"
                f"• Default name: {target_doc_name}\n"
                "• You can rename it from the Forms tab."
            ),
            font=("Segoe UI", 10),
            text_color="#cc7e1f",
            justify="left", anchor="w", wraplength=380,
        ).pack(anchor="w", padx=12, pady=10)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=22, pady=(10, 16))
        ctk.CTkButton(
            footer, text="Insert", width=120, height=32,
            corner_radius=4, command=self._on_insert,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel", width=90, height=32,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._on_insert())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.after(100, self._center_on_parent)

    def _on_insert(self) -> None:
        self.result = True
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = False
        self.destroy()

    def _center_on_parent(self) -> None:
        self.update_idletasks()
        parent = self.master
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
        except tk.TclError:
            return
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
