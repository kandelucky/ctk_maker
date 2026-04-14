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

PANEL_BG = "#252526"
HOVER_BG = "#2d2d30"
SELECTED_BG = "#094771"
SUBTITLE_FG = "#888888"
FILE_NAME_FG = "#cccccc"
FILE_PATH_FG = "#666666"
META_FG = "#6a6a6a"

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
            font=("Segoe UI", 11, "bold"),
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
                font=("Segoe UI", 10, "italic"),
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

        name = Path(path).stem

        try:
            mtime = Path(path).stat().st_mtime
            time_text = _relative_time(mtime)
        except OSError:
            time_text = "missing"

        parent_dir = str(Path(path).parent)
        if len(parent_dir) > PATH_MAX_LEN:
            parent_dir = "…" + parent_dir[-(PATH_MAX_LEN - 1):]

        name_lbl = ctk.CTkLabel(
            row, text=name, font=("Segoe UI", 12, "bold"),
            text_color=FILE_NAME_FG, anchor="w",
        )
        name_lbl.pack(side="left", padx=(8, 16))

        time_lbl = ctk.CTkLabel(
            row, text=time_text, font=("Segoe UI", 9),
            text_color=META_FG, anchor="e",
        )
        time_lbl.pack(side="right", padx=(0, 8))

        path_lbl = ctk.CTkLabel(
            row, text=parent_dir, font=("Segoe UI", 9),
            text_color=FILE_PATH_FG, anchor="w",
        )
        path_lbl.pack(side="left", fill="x", expand=True)

        self._rows.append((row, path))

        self._bind_row_events(row, path, (row, name_lbl, path_lbl, time_lbl))

    def _bind_row_events(self, row, path: str, widgets) -> None:
        def on_enter(_e):
            if self._selected_path != path:
                row.configure(fg_color=HOVER_BG)

        def on_leave(_e):
            if self._selected_path != path:
                row.configure(fg_color="transparent")

        def on_click(_e):
            self._select(path, row)
            if self._on_select is not None:
                self._on_select(path)

        def on_double(_e):
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
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="Remove from Recent",
            command=lambda p=path: self._on_remove(p),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _on_remove(self, path: str) -> None:
        remove_recent(path)
        if self._selected_path == path:
            self._selected_path = None
        self.refresh()
