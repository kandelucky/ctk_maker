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

from app.ui.managed_window import ManagedToplevel
from app.ui.system_fonts import ui_font


class ComponentWindowInsertDialog(ManagedToplevel):
    window_title = "Insert Window component"
    default_size = (440, 280)
    min_size = (420, 260)
    fg_color = "#1a1a1a"
    panel_padding = (0, 0)
    modal = True
    window_resizable = (False, False)

    def __init__(
        self,
        parent,
        component_name: str,
        target_doc_name: str,
    ):
        self._component_name = component_name
        self._target_doc_name = target_doc_name
        self.result: bool = False
        super().__init__(parent)
        self.bind("<Return>", lambda _e: self._on_insert())

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

    def build_content(self) -> ctk.CTkFrame:
        container = ctk.CTkFrame(self, fg_color="transparent")

        body = ctk.CTkFrame(container, fg_color="transparent")
        body.pack(padx=22, pady=(20, 8), fill="x")

        ctk.CTkLabel(
            body, text="Insert as a new Dialog?",
            font=ui_font(14, "bold"),
            text_color="#e6e6e6", anchor="w",
        ).pack(anchor="w", pady=(0, 6))
        ctk.CTkLabel(
            body,
            text=(
                f"\"{self._component_name}\" is a Window component."
            ),
            font=ui_font(10),
            text_color="#bdbdbd", anchor="w",
            wraplength=380, justify="left",
        ).pack(anchor="w", pady=(0, 14))

        info = ctk.CTkFrame(body, fg_color="#2a2118", corner_radius=4)
        info.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            info,
            text=(
                "• A new Toplevel will be added to this project.\n"
                f"• Default name: {self._target_doc_name}\n"
                "• You can rename it from the Forms tab."
            ),
            font=ui_font(10),
            text_color="#cc7e1f",
            justify="left", anchor="w", wraplength=380,
        ).pack(anchor="w", padx=12, pady=10)

        footer = ctk.CTkFrame(container, fg_color="transparent")
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
        return container

    def _on_insert(self) -> None:
        self.result = True
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = False
        self.destroy()
