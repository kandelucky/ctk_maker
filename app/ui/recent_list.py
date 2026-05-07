"""Reusable Recent Projects list panel.

Renders a scrollable list of recent project files with:
- filename + parent-dir + relative modification time per row
- click to select (highlight), double-click to activate
- right-click → "Remove from Recent" (persists via recent_files)
- helper text when list is empty

Callbacks:
    on_select(path)   — fires on single-click
    on_activate(path) — fires on double-click or Open button
"""

from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from app.core.recent_files import load_recent, remove_recent
from app.ui.system_fonts import ui_font

PANEL_BG = "#252526"
HOVER_BG = "#2d2d30"
SELECTED_BG = "#094771"
SUBTITLE_FG = "#888888"
FILE_NAME_FG = "#cccccc"
FILE_PATH_FG = "#666666"
META_FG = "#6a6a6a"

# Missing (file moved / deleted) — dimmed so the user sees the row
# but can't open it. Right-click → Remove from Recent still works.
MISSING_NAME_FG = "#666666"
MISSING_PATH_FG = "#4a4a4a"
MISSING_META_FG = "#8b4a4a"

ROW_HEIGHT = 22
PATH_MAX_LEN = 28


def _relative_time(ts: float) -> str:
    """Format a unix timestamp as 'Xm ago' / 'Xh ago' / etc."""
    diff = time.time() - ts
    if diff < 60:
        return "just now"
    if diff < 3600:
        return f"{int(diff / 60)}m ago"
    if diff < 86400:
        return f"{int(diff / 3600)}h ago"
    if diff < 604800:
        return f"{int(diff / 86400)}d ago"
    if diff < 2592000:
        return f"{int(diff / 604800)}w ago"
    if diff < 31536000:
        return f"{int(diff / 2592000)}mo ago"
    return f"{int(diff / 31536000)}y ago"


class RecentList(ctk.CTkFrame):
    def __init__(
        self,
        master,
        *,
        on_select: Callable[[str], None] | None = None,
        on_activate: Callable[[str], None] | None = None,
    ):
        super().__init__(master, fg_color=PANEL_BG, corner_radius=6)
        self._on_select = on_select
        self._on_activate = on_activate

        self._selected_path: str | None = None
        self._rows: list[tuple[ctk.CTkFrame, str]] = []

        ctk.CTkLabel(
            self, text="Recent",
            font=ui_font(11, "bold"),
            text_color=SUBTITLE_FG, anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 6))

        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
        )
        self._scroll.pack(fill="both", expand=True, padx=4, pady=(0, 8))

        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def selected_path(self) -> str | None:
        return self._selected_path

    def refresh(self) -> None:
        for child in list(self._scroll.winfo_children()):
            child.destroy()
        self._rows.clear()

        recent = load_recent()
        if not recent:
            ctk.CTkLabel(
                self._scroll, text="No recent projects",
                font=ui_font(10, "italic"),
                text_color=FILE_PATH_FG,
            ).pack(pady=20)
            return

        for path in recent:
            self._build_row(path)

    def clear_selection(self) -> None:
        self._selected_path = None
        for frame, _path in self._rows:
            frame.configure(fg_color="transparent")

    # ------------------------------------------------------------------
    # Row build
    # ------------------------------------------------------------------
    def _build_row(self, path: str) -> None:
        row = ctk.CTkFrame(
            self._scroll, fg_color="transparent",
            corner_radius=3, height=ROW_HEIGHT,
        )
        row.pack(fill="x", padx=2, pady=1)
        row.pack_propagate(False)

        # Multi-page project: show the project folder name + its
        # parent dir (the location the user picked when creating it),
        # not the deeply-nested .ctkproj filename + assets/pages/
        # path. Falls back to the page filename for legacy projects.
        from app.core.project_folder import find_project_root
        project_root = find_project_root(path)
        if project_root is not None:
            name = project_root.name
            display_parent = project_root.parent
        else:
            name = Path(path).stem
            display_parent = Path(path).parent

        missing = False
        try:
            mtime = Path(path).stat().st_mtime
            time_text = _relative_time(mtime)
        except OSError:
            time_text = "missing"
            missing = True

        parent_dir = str(display_parent)
        if len(parent_dir) > PATH_MAX_LEN:
            parent_dir = "…" + parent_dir[-(PATH_MAX_LEN - 1):]

        name_lbl = ctk.CTkLabel(
            row, text=name, font=ui_font(12, "bold"),
            text_color=MISSING_NAME_FG if missing else FILE_NAME_FG,
            anchor="w",
        )
        name_lbl.pack(side="left", padx=(8, 16))

        time_lbl = ctk.CTkLabel(
            row, text=time_text, font=ui_font(9),
            text_color=MISSING_META_FG if missing else META_FG, anchor="e",
        )
        time_lbl.pack(side="right", padx=(0, 8))

        path_lbl = ctk.CTkLabel(
            row, text=parent_dir, font=ui_font(9),
            text_color=MISSING_PATH_FG if missing else FILE_PATH_FG,
            anchor="w",
        )
        path_lbl.pack(side="left", fill="x", expand=True)

        self._rows.append((row, path))

        self._bind_row_events(
            row, path, (row, name_lbl, path_lbl, time_lbl), missing,
        )

    def _bind_row_events(
        self, row, path: str, widgets, missing: bool = False,
    ) -> None:
        def on_enter(_e):
            if self._selected_path != path and not missing:
                row.configure(fg_color=HOVER_BG)

        def on_leave(_e):
            if self._selected_path != path:
                row.configure(fg_color="transparent")

        def on_click(_e):
            if missing:
                return  # dimmed — clicks are a no-op; only right-click works
            self._select(path, row)
            if self._on_select is not None:
                self._on_select(path)

        def on_double(_e):
            if missing:
                return
            self._select(path, row)
            if self._on_activate is not None:
                self._on_activate(path)

        def on_right(event):
            self._show_row_menu(event, path)

        for w in widgets:
            w.bind("<Enter>", on_enter, add="+")
            w.bind("<Leave>", on_leave, add="+")
            w.bind("<Button-1>", on_click, add="+")
            w.bind("<Double-Button-1>", on_double, add="+")
            w.bind("<Button-3>", on_right, add="+")

    def _select(self, path: str, selected_row: ctk.CTkFrame) -> None:
        self._selected_path = path
        for r, _p in self._rows:
            r.configure(
                fg_color=SELECTED_BG if r is selected_row else "transparent",
            )

    def _show_row_menu(self, event, path: str) -> str:
        # Match the dark menu style used elsewhere (ProjectPanel, etc.)
        # so the welcome screen doesn't clash with the in-app surface.
        menu = tk.Menu(
            self, tearoff=0,
            bg="#2d2d30", fg=FILE_NAME_FG,
            activebackground="#094771", activeforeground="#ffffff",
            relief="flat", bd=0, font=ui_font(10),
        )
        missing = not Path(path).exists()
        menu.add_command(
            label="Open",
            state="normal" if not missing else "disabled",
            command=lambda p=path: self._activate(p),
        )
        menu.add_command(
            label="Open containing folder",
            state="normal" if not missing else "disabled",
            command=lambda p=path: self._reveal_in_explorer(p),
        )
        menu.add_separator()
        menu.add_command(
            label="Remove from Recent",
            command=lambda p=path: self._on_remove(p),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _activate(self, path: str) -> None:
        """Same as a double-click — fires the activate callback so
        the host (StartupDialog / similar) can open the project.
        """
        if self._on_activate is not None:
            self._on_activate(path)

    def _reveal_in_explorer(self, path: str) -> None:
        """Open the project folder (or the .ctkproj's parent for
        legacy projects) in the OS file manager.
        """
        import os
        import subprocess
        import sys
        from app.core.project_folder import find_project_root
        target = find_project_root(path) or Path(path).parent
        if not target.exists():
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(target))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except OSError:
            pass

    def _on_remove(self, path: str) -> None:
        remove_recent(path)
        if self._selected_path == path:
            self._selected_path = None
        self.refresh()
