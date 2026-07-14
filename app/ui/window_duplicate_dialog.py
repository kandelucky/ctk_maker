"""Modal — name + confirmation gate before duplicating a Window /
Dialog document. Makes the side-effect explicit: what travels with
the copy (widgets, local variables, event bindings), where the new
window lands, and — for a main-window source — that the copy becomes
a Dialog. The name field is pre-filled with a unique suggestion.

``result`` is the chosen document name on Duplicate, ``None`` on
Cancel.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from app.ui.managed_window import ManagedToplevel
from app.ui.system_fonts import ui_font


class WindowDuplicateDialog(ManagedToplevel):
    window_title = "Duplicate Window"
    default_size = (440, 350)
    min_size = (420, 320)
    fg_color = "#1a1a1a"
    panel_padding = (0, 0)
    modal = True
    window_resizable = (False, False)

    def __init__(
        self,
        parent,
        source_name: str,
        default_name: str,
        taken_names: set[str],
        source_is_main: bool,
    ):
        self._source_name = source_name
        self._default_name = default_name
        self._taken_names = set(taken_names)
        self._source_is_main = source_is_main
        self.result: str | None = None
        if not source_is_main:
            self.window_title = "Duplicate Dialog"
        super().__init__(parent)
        self.bind("<Return>", lambda _e: self._on_duplicate())
        # Focus the name entry with the suggestion pre-selected so a
        # typed name replaces it in one go. Scheduled — the modal grab
        # is itself deferred, focus before it would be lost.
        self.after(80, self._focus_name_entry)

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
            body, text=f"Duplicate \"{self._source_name}\"?",
            font=ui_font(14, "bold"),
            text_color="#e6e6e6", anchor="w",
        ).pack(anchor="w", pady=(0, 6))
        ctk.CTkLabel(
            body,
            text=(
                "The copy is a fully independent window:\n"
                "•  every widget with its properties\n"
                "•  local variables — as separate copies\n"
                "•  event and script bindings stay attached"
            ),
            font=ui_font(10),
            text_color="#bdbdbd", anchor="w",
            wraplength=380, justify="left",
        ).pack(anchor="w", pady=(0, 14))

        name_row = ctk.CTkFrame(body, fg_color="transparent")
        name_row.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            name_row, text="Name", font=ui_font(10),
            text_color="#e6e6e6", width=44, anchor="w",
        ).pack(side="left")
        self._name_entry = ctk.CTkEntry(
            name_row, font=ui_font(10), height=30, corner_radius=4,
        )
        self._name_entry.pack(side="left", fill="x", expand=True)
        self._name_entry.insert(0, self._default_name)

        info_lines = [
            "• The copy is placed to the right of the existing windows.",
        ]
        if self._source_is_main:
            info_lines.append(
                "• The copy becomes a Dialog window — a project has "
                "only one main window.",
            )
        info = ctk.CTkFrame(body, fg_color="#2a2118", corner_radius=4)
        info.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            info,
            text="\n".join(info_lines),
            font=ui_font(10),
            text_color="#cc7e1f",
            justify="left", anchor="w", wraplength=380,
        ).pack(anchor="w", padx=12, pady=10)

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(fill="x", padx=22, pady=(10, 16))
        ctk.CTkButton(
            footer, text="Duplicate", width=120, height=32,
            corner_radius=4, command=self._on_duplicate,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel", width=90, height=32,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))
        return container

    def _focus_name_entry(self) -> None:
        try:
            self._name_entry.focus_set()
            self._name_entry.select_range(0, "end")
            self._name_entry.icursor("end")
        except tk.TclError:
            pass

    def _on_duplicate(self) -> None:
        name = self._name_entry.get().strip()
        # Empty or already-taken names can't proceed — flag the entry
        # instead of silently auto-suffixing a name the user typed.
        if not name or name in self._taken_names:
            self._name_entry.configure(border_color="#c0504d")
            return
        self.result = name
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()
