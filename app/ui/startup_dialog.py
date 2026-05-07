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
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

from app import __version__
from app.core.screen import center_geometry
from app.ui.dialog_utils import safe_grab_set
from app.ui.new_project_form import NewProjectForm
from app.ui.recent_list import RecentList

DIALOG_W = 740
DIALOG_H = 510

BG = "#1e1e1e"
TITLE_FG = "#e0e0e0"
SUBTITLE_FG = "#888888"
VERSION_FG = "#666666"

LOGO_PATH = Path(__file__).resolve().parents[2] / "app" / "assets" / "icon.png"
LOGO_SIZE = 28


class StartupDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_ready=None):
        super().__init__(parent)
        # Hide before the WM maps the window; reveal at the end of
        # __init__ once geometry has been positioned. Otherwise the
        # window flashes at the WM-default location and jumps to the
        # centered position. Alpha=0 layered on top so even the
        # first map after deiconify doesn't show Windows' default
        # white background for one frame.
        self.withdraw()
        self.attributes("-alpha", 0.0)
        self.title("CTkMaker")
        self.resizable(False, False)
        self.transient(parent)
        self.configure(fg_color=BG)

        self.result: tuple | None = None

        self.geometry(f"{DIALOG_W}x{DIALOG_H}")
        self._center_on_screen()

        self._build_header()
        self._build_body()
        self._build_footer()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_close())
        self.bind("<Return>", lambda e: self._on_create())

        self.deiconify()
        self.update_idletasks()
        self.attributes("-alpha", 1.0)
        # Dismiss the splash AFTER this window is fully revealed, not
        # before — otherwise there's a visible gap with neither window
        # on screen while we paint.
        if on_ready is not None:
            try:
                on_ready()
            except Exception:
                pass
        safe_grab_set(self)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _center_on_screen(self) -> None:
        # Use the cached work-area helper — no Tk geometry queries,
        # no update_idletasks pump. Falls back to Tk's screen size
        # only when the Win32 work-area lookup fails. Pass our CTk
        # window scaling so center_geometry accounts for the scaling
        # CTk applies to width/height before placement.
        scale = float(self._get_window_scaling() or 1.0)
        geom = center_geometry(DIALOG_W, DIALOG_H, scale=scale)
        if geom is None:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            physical_w = int(DIALOG_W * scale)
            physical_h = int(DIALOG_H * scale)
            x = max(0, (sw - physical_w) // 2)
            y = max(0, (sh - physical_h) // 2)
            geom = f"{DIALOG_W}x{DIALOG_H}+{x}+{y}"
        self.geometry(geom)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(18, 8))

        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.pack(fill="x")

        if LOGO_PATH.exists():
            try:
                self._logo_image = ctk.CTkImage(
                    light_image=Image.open(LOGO_PATH),
                    dark_image=Image.open(LOGO_PATH),
                    size=(LOGO_SIZE, LOGO_SIZE),
                )
                ctk.CTkLabel(
                    title_row, image=self._logo_image, text="",
                ).pack(side="left", padx=(0, 8))
            except Exception:
                pass

        ctk.CTkLabel(
            title_row, text="CTkMaker",
            font=("Segoe UI", 18, "bold"),
            text_color=TITLE_FG, anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            title_row, text=f"v{__version__}",
            font=("Segoe UI", 10),
            text_color=VERSION_FG, anchor="sw",
        ).pack(side="left", padx=(6, 0), pady=(0, 2))

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
