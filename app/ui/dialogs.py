"""Modal dialogs used by the builder.

NewProjectSizeDialog (File → New): standalone modal wrapping
NewProjectForm. Returns (name, path, w, h) on Create or None if
the user cancels.

RenameDialog: blocking single-line rename modal used by the workspace
right-click menu and the Object Tree right-click menu.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import simpledialog

import customtkinter as ctk

from app.ui.new_project_form import NewProjectForm


class RenameDialog(simpledialog.Dialog):
    """Blocking rename dialog. Rejects empty names: bells, restores the
    original value in the entry, and keeps the dialog open.
    """

    def __init__(self, parent, initial_value: str):
        self._initial = initial_value
        self.result: str | None = None
        super().__init__(parent, "Rename Widget")

    def body(self, master):
        tk.Label(master, text="New name:").pack(padx=16, pady=(12, 4))
        self.entry = tk.Entry(master, width=30)
        self.entry.insert(0, self._initial)
        self.entry.select_range(0, tk.END)
        self.entry.pack(padx=16, pady=(0, 12))
        return self.entry

    def validate(self) -> bool:
        value = self.entry.get().strip()
        if not value:
            self.bell()
            self.entry.delete(0, tk.END)
            self.entry.insert(0, self._initial)
            self.entry.select_range(0, tk.END)
            self.entry.focus_set()
            return False
        self.result = value
        return True

    def apply(self):
        # result is already set inside validate()
        pass


class NewProjectSizeDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        default_w: int = 800,
        default_h: int = 600,
        default_name: str = "Untitled",
        default_save_dir: str | None = None,
    ):
        super().__init__(parent)
        self.title("New project")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result: tuple[str, str, int, int] | None = None

        self._form = NewProjectForm(
            self,
            default_w=default_w,
            default_h=default_h,
            default_name=default_name,
            default_save_dir=default_save_dir,
        )
        self._form.pack(padx=20, pady=(20, 10), fill="both", expand=True)

        self._build_footer()

        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.after(100, self._center_on_parent)

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent")
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

    def _on_ok(self) -> None:
        validated = self._form.validate_and_get()
        if validated is None:
            return
        self.result = validated
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()
