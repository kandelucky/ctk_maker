"""Modal — resolve variable name/type conflicts when inserting a
component. One row per conflict; user picks Rename (with a new name)
or Skip (drops the binding entirely).

Returns ``True`` from ``run()`` when the user clicked OK; ``False``
on Cancel. The caller's list of ``VarConflict`` objects is mutated
in place — ``resolution`` and ``new_name`` carry the user's choices.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

import customtkinter as ctk

from app.ui.dialog_utils import prepare_dialog, reveal_dialog, safe_grab_set

if TYPE_CHECKING:
    from app.io.component_io import VarConflict

_FORBIDDEN = set('\\/:*?"<>|')


def _is_valid_name(name: str) -> bool:
    name = name.strip()
    if not name or name in (".", ".."):
        return False
    return not any(ch in _FORBIDDEN for ch in name)


class ComponentVarConflictDialog(ctk.CTkToplevel):
    def __init__(self, parent, conflicts: "list[VarConflict]"):
        super().__init__(parent)
        prepare_dialog(self)
        self.title("Resolve variable conflicts")
        self.transient(parent)
        safe_grab_set(self)

        self._conflicts = conflicts
        self._row_state: list[dict] = []
        self.result: bool = False

        self.geometry("460x420")
        self.minsize(400, 320)

        intro = ctk.CTkLabel(
            self,
            text=(
                "These variables already exist in the target window "
                "with a different type. Pick a resolution for each:"
            ),
            font=("Segoe UI", 10),
            text_color="#cccccc",
            wraplength=420,
            justify="left",
        )
        intro.pack(padx=16, pady=(14, 8), anchor="w")

        scroll = ctk.CTkScrollableFrame(
            self, fg_color="#1e1e1e", corner_radius=4,
        )
        scroll.pack(padx=12, pady=(0, 8), fill="both", expand=True)

        for conflict in conflicts:
            self._build_row(scroll, conflict)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=16, pady=(4, 14))
        ctk.CTkButton(
            footer, text="OK", width=100, height=30,
            corner_radius=4, command=self._on_ok,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel", width=80, height=30,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))

        self.bind("<Return>", lambda _e: self._on_ok())
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.after(100, self._center_on_parent)

    def _build_row(self, parent, conflict: "VarConflict") -> None:
        wrap = ctk.CTkFrame(
            parent, fg_color="#2a2a2a", corner_radius=4,
        )
        wrap.pack(fill="x", padx=4, pady=4)

        name = conflict.bundle.get("name", "?")
        comp_type = conflict.bundle.get("type", "?")
        existing_type = conflict.existing_type
        ctk.CTkLabel(
            wrap,
            text=f"{name}",
            font=("Segoe UI", 11, "bold"),
            text_color="#e6e6e6",
            anchor="w",
        ).pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(
            wrap,
            text=(
                f"component: {comp_type}    "
                f"existing: {existing_type}"
            ),
            font=("Segoe UI", 9),
            text_color="#888888",
            anchor="w",
        ).pack(fill="x", padx=10, pady=(0, 4))

        choice_var = tk.StringVar(value=conflict.resolution)
        name_var = tk.StringVar(value=conflict.new_name)

        row1 = ctk.CTkFrame(wrap, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(0, 2))
        ctk.CTkRadioButton(
            row1, text="Rename to", variable=choice_var, value="rename",
            font=("Segoe UI", 10),
        ).pack(side="left")
        name_entry = ctk.CTkEntry(
            row1, textvariable=name_var, width=200, height=24,
        )
        name_entry.pack(side="left", padx=(8, 0))

        row2 = ctk.CTkFrame(wrap, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkRadioButton(
            row2, text="Skip binding", variable=choice_var, value="skip",
            font=("Segoe UI", 10),
        ).pack(side="left")

        self._row_state.append({
            "conflict": conflict,
            "choice_var": choice_var,
            "name_var": name_var,
        })

    def _on_ok(self) -> None:
        from tkinter import messagebox
        for state in self._row_state:
            choice = state["choice_var"].get()
            new_name = state["name_var"].get().strip()
            if choice == "rename":
                if not _is_valid_name(new_name):
                    self.bell()
                    messagebox.showwarning(
                        "Invalid name",
                        f"'{new_name}' isn't a valid variable name.",
                        parent=self,
                    )
                    return
                state["conflict"].resolution = "rename"
                state["conflict"].new_name = new_name
            else:
                state["conflict"].resolution = "skip"
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
            reveal_dialog(self)
            return
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        reveal_dialog(self)
