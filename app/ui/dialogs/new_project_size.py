"""File → New modal — standalone wrapper around ``NewProjectForm``.

Returns ``(name, path, w, h)`` on Create, ``None`` on Cancel.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from app.ui.managed_window import ManagedToplevel
from app.ui.new_project_form import NewProjectForm


class NewProjectSizeDialog(ManagedToplevel):
    window_title = "New project"
    default_size = (520, 560)
    min_size = (480, 520)
    panel_padding = (0, 0)
    modal = True
    window_resizable = (False, False)

    def __init__(
        self,
        parent,
        default_w: int = 800,
        default_h: int = 600,
        default_name: str = "Untitled",
        default_save_dir: str | None = None,
    ):
        self.result: tuple[str, str, int, int] | None = None
        self._form_default_w = default_w
        self._form_default_h = default_h
        self._form_default_name = default_name
        self._form_default_save_dir = default_save_dir
        super().__init__(parent)
        self.bind("<Return>", lambda e: self._on_ok())

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

        self._form = NewProjectForm(
            container,
            default_w=self._form_default_w,
            default_h=self._form_default_h,
            default_name=self._form_default_name,
            default_save_dir=self._form_default_save_dir,
        )
        self._form.pack(padx=20, pady=(20, 10), fill="both", expand=True)

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(
            footer, text="+ Create Project", width=160, height=32,
            corner_radius=4, command=self._on_ok,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel", width=90, height=32,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))
        return container

    def _on_ok(self) -> None:
        validated = self._form.validate_and_get()
        if validated is None:
            return
        self.result = validated
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()
