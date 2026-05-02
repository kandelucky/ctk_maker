"""Welcome / startup dialog shown when the builder launches.

Thin shell that composes two reusable components:
    - RecentList       (app/ui/recent_list.py)
    - NewProjectForm   (app/ui/new_project_form.py)

Result is exposed via `.result` as one of:
    ("open", "<absolute path>")     — user picked a recent file or browsed
    ("new",  name, w, h, path)      — user filled the New Project form
    None                            — user cancelled the dialog
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from app.ui.dialog_utils import safe_grab_set
from app.ui.new_project_form import NewProjectForm
from app.ui.recent_list import RecentList

DIALOG_W = 740
DIALOG_H = 510

BG = "#1e1e1e"
TITLE_FG = "#e0e0e0"
SUBTITLE_FG = "#888888"


class StartupDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("CTkMaker")
        self.resizable(False, False)
        self.transient(parent)
        safe_grab_set(self)
        self.configure(fg_color=BG)

        self.result: tuple | None = None

        self.geometry(f"{DIALOG_W}x{DIALOG_H}")
        self._center_on_parent()

        self._build_header()
        self._build_body()
        self._build_footer()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_close())
        self.bind("<Return>", lambda e: self._on_create())

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _center_on_parent(self) -> None:
        self.update_idletasks()
        try:
            px = self.master.winfo_rootx()
            py = self.master.winfo_rooty()
            pw = self.master.winfo_width()
            ph = self.master.winfo_height()
        except tk.TclError:
            return
        x = px + (pw - DIALOG_W) // 2
        y = py + (ph - DIALOG_H) // 2
        self.geometry(f"{DIALOG_W}x{DIALOG_H}+{max(0, x)}+{max(0, y)}")

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(18, 8))

        ctk.CTkLabel(
            header, text="CTkMaker",
            font=("Segoe UI", 18, "bold"),
            text_color=TITLE_FG, anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            header, text="Open a recent project or create a new one",
            font=("Segoe UI", 11),
            text_color=SUBTITLE_FG, anchor="w",
        ).pack(fill="x", pady=(2, 0))

    def _build_body(self) -> None:
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(0, 8))
        body.grid_columnconfigure(0, weight=1, minsize=200)
        body.grid_columnconfigure(1, weight=0, minsize=12)
        body.grid_columnconfigure(2, weight=2, minsize=380)
        body.grid_rowconfigure(0, weight=1)

        self._recent_list = RecentList(
            body,
            on_select=self._on_recent_select,
            on_activate=self._on_recent_activate,
        )
        self._recent_list.grid(row=0, column=0, sticky="nsew")

        self._build_recent_buttons()

        from app.ui.settings_dialog import get_default_project_size
        default_w, default_h = get_default_project_size()
        self._form = NewProjectForm(
            body, default_w=default_w, default_h=default_h,
        )
        self._form.grid(row=0, column=2, sticky="nsew")

    def _build_recent_buttons(self) -> None:
        # The RecentList is a self-contained CTkFrame; we layer a button
        # row inside its content area. Use an external wrapper so the
        # grid layout still works.
        btn_row = ctk.CTkFrame(self._recent_list, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=(0, 10), side="bottom")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            btn_row, text="Browse...", height=28, corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            font=("Segoe UI", 10),
            command=self._on_browse,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))

        self._open_btn = ctk.CTkButton(
            btn_row, text="Open", height=28, corner_radius=4,
            font=("Segoe UI", 10),
            state="disabled",
            command=self._on_open_selected,
        )
        self._open_btn.grid(row=0, column=1, sticky="ew", padx=(3, 0))

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(4, 16))
        ctk.CTkButton(
            footer, text="+ Create Project", width=160, height=32,
            corner_radius=4, command=self._on_create,
        ).pack(side="right")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def _on_recent_select(self, _path: str) -> None:
        self._open_btn.configure(state="normal")

    def _on_recent_activate(self, path: str) -> None:
        self.result = ("open", path)
        self.destroy()

    def _on_open_selected(self) -> None:
        selected = self._recent_list.selected_path
        if selected is None:
            return
        self.result = ("open", selected)
        self.destroy()

    def _on_browse(self) -> None:
        from app.core.paths import get_default_projects_dir
        from app.ui.dialogs import prompt_open_project_folder
        picked = prompt_open_project_folder(
            self, initial_dir=str(get_default_projects_dir()),
        )
        if picked is None:
            return
        self.result = ("open", str(picked))
        self.destroy()

    def _on_create(self) -> None:
        validated = self._form.validate_and_get()
        if validated is None:
            return
        name, path, w, h = validated
        self.result = ("new", name, w, h, path)
        self.destroy()

    def _on_close(self) -> None:
        # The X / Escape paths are now the only ways to dismiss the
        # startup dialog without picking a project. Without an
        # untitled fallback in the main window, dismissing here will
        # close the app — confirm first so a stray click on X doesn't
        # silently quit.
        confirm = messagebox.askyesno(
            "Quit CTkMaker?",
            "No project is open. Closing this dialog will quit "
            "CTkMaker.\n\nQuit now?",
            parent=self,
        )
        if not confirm:
            return
        self.result = None
        self.destroy()
