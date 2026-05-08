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

from app.ui.managed_window import ManagedToplevel
from app.ui.system_fonts import ui_font

if TYPE_CHECKING:
    from app.io.component_io import VarConflict

_FORBIDDEN = set('\\/:*?"<>|')


def _is_valid_name(name: str) -> bool:
    name = name.strip()
    if not name or name in (".", ".."):
        return False
    return not any(ch in _FORBIDDEN for ch in name)


class ComponentVarConflictDialog(ManagedToplevel):
    window_title = "Resolve variable conflicts"
    default_size = (460, 420)
    min_size = (400, 320)
    panel_padding = (0, 0)
    modal = True

    def __init__(self, parent, conflicts: "list[VarConflict]"):
        self._conflicts = conflicts
        self._row_state: list[dict] = []
        self.result: bool = False
        super().__init__(parent)
        self.bind("<Return>", lambda _e: self._on_ok())

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

        intro = ctk.CTkLabel(
            container,
            text=(
                "These variables already exist in the target window "
                "with a different type. Pick a resolution for each:"
            ),
            font=ui_font(10),
            text_color="#cccccc",
            wraplength=420,
            justify="left",
        )
        intro.pack(padx=16, pady=(14, 8), anchor="w")

        scroll = ctk.CTkScrollableFrame(
            container, fg_color="#1e1e1e", corner_radius=4,
        )
        scroll.pack(padx=12, pady=(0, 8), fill="both", expand=True)

        for conflict in self._conflicts:
            self._build_row(scroll, conflict)

        footer = ctk.CTkFrame(container, fg_color="transparent")
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
        return container

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
            font=ui_font(11, "bold"),
            text_color="#e6e6e6",
            anchor="w",
        ).pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(
            wrap,
            text=(
                f"component: {comp_type}    "
                f"existing: {existing_type}"
            ),
            font=ui_font(9),
            text_color="#888888",
            anchor="w",
        ).pack(fill="x", padx=10, pady=(0, 4))

        choice_var = tk.StringVar(value=conflict.resolution)
        name_var = tk.StringVar(value=conflict.new_name)

        row1 = ctk.CTkFrame(wrap, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(0, 2))
        ctk.CTkRadioButton(
            row1, text="Rename to", variable=choice_var, value="rename",
            font=ui_font(10),
        ).pack(side="left")
        name_entry = ctk.CTkEntry(
            row1, textvariable=name_var, width=200, height=24,
        )
        name_entry.pack(side="left", padx=(8, 0))

        row2 = ctk.CTkFrame(wrap, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkRadioButton(
            row2, text="Skip binding", variable=choice_var, value="skip",
            font=ui_font(10),
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
