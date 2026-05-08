"""History inspector — shows the Undo/Redo stack as a scrollable list.

``HistoryPanel`` is an embeddable ``ctk.CTkFrame`` used in the docked
sidebar tab.  ``HistoryWindow`` is a thin ``CTkToplevel`` wrapper around
it for the floating (F9) use-case.

Entries above the current-state marker are past operations (undoable);
entries below are future operations (redoable, dimmed).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from app.ui.managed_window import ManagedToplevel
from app.ui.system_fonts import ui_font

if TYPE_CHECKING:
    from app.core.project import Project

BG = "#1e1e1e"
PANEL_BG = "#252526"
TREE_BG = "#1e1e1e"
TREE_FG = "#cccccc"
TREE_SELECTED_BG = "#094771"
TREE_HEADING_BG = "#2d2d30"
TREE_HEADING_FG = "#cccccc"
REDO_FG = "#666666"
CURRENT_BG = "#0c5a8c"
CURRENT_FG = "#ffffff"
EMPTY_FG = "#666666"

DIALOG_W = 300
DIALOG_H = 400
TREE_ROW_HEIGHT = 24
TREE_FONT_SIZE = 10

CURRENT_MARKER = "◉ Current state"
EMPTY_TEXT = "(no history yet)"


class HistoryPanel(ctk.CTkFrame):
    """Embeddable history list — use inside a sidebar tab or any frame."""

    def __init__(self, parent, project: "Project"):
        super().__init__(parent, fg_color=PANEL_BG, corner_radius=0, border_width=0)
        self.project = project
        self._bus_subs: list[tuple[str, Callable]] = []
        self._build_tree()
        bus = project.event_bus
        bus.subscribe("history_changed", self._on_history_changed)
        self._bus_subs.append(("history_changed", self._on_history_changed))
        self.after(0, self._refresh)

    # ------------------------------------------------------------------
    def _build_tree(self) -> None:
        style = ttk.Style(self)
        style_name = "History.Treeview"
        style.configure(
            style_name,
            background=TREE_BG,
            fieldbackground=TREE_BG,
            foreground=TREE_FG,
            rowheight=TREE_ROW_HEIGHT,
            borderwidth=0,
            font=ui_font(TREE_FONT_SIZE),
        )
        style.map(
            style_name,
            background=[("selected", TREE_SELECTED_BG)],
            foreground=[("selected", "#ffffff")],
        )

        self.tree = ttk.Treeview(
            self,
            columns=(),
            show="tree",
            style=style_name,
            selectmode="none",
        )
        self.tree.tag_configure("redo", foreground=REDO_FG)
        self.tree.tag_configure(
            "current", background=CURRENT_BG, foreground=CURRENT_FG,
        )
        self.tree.tag_configure("empty", foreground=EMPTY_FG)
        self.tree.bind("<Button-1>", self._on_click, add="+")

        vsb = ctk.CTkScrollbar(
            self, orientation="vertical",
            command=self.tree.yview,
            width=10, corner_radius=4,
            fg_color="transparent",
            button_color="#3a3a3a",
            button_hover_color="#4a4a4a",
        )
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    def _on_click(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid or iid in ("current", "") or iid.startswith("empty"):
            return
        history = self.project.history
        if iid.startswith("u:"):
            i = int(iid[2:])
            steps = len(history._undo) - 1 - i
            for _ in range(steps):
                history.undo()
        elif iid.startswith("r:"):
            i = int(iid[2:])
            for _ in range(i + 1):
                history.redo()

    def _on_history_changed(self, *_args, **_kwargs) -> None:
        self._refresh()

    def _refresh(self) -> None:
        for iid in self.tree.get_children(""):
            self.tree.delete(iid)
        history = self.project.history
        undo_stack = history._undo
        redo_stack = history._redo
        if not undo_stack and not redo_stack:
            self.tree.insert("", "end", text=EMPTY_TEXT, tags=("empty",))
            return
        for i, cmd in enumerate(undo_stack):
            desc = cmd.description or cmd.__class__.__name__
            self.tree.insert("", "end", iid=f"u:{i}", text=f"  {desc}")
        self.tree.insert(
            "", "end", iid="current",
            text=CURRENT_MARKER, tags=("current",),
        )
        for i, cmd in enumerate(reversed(redo_stack)):
            desc = cmd.description or cmd.__class__.__name__
            self.tree.insert(
                "", "end", iid=f"r:{i}", text=f"  {desc}", tags=("redo",),
            )
        try:
            self.tree.see("current")
        except tk.TclError:
            pass

    def destroy(self) -> None:
        self._unsubscribe_bus()
        super().destroy()

    def _unsubscribe_bus(self) -> None:
        try:
            bus = self.project.event_bus
            for event_name, handler in self._bus_subs:
                bus.unsubscribe(event_name, handler)
        except Exception:
            pass
        self._bus_subs = []


class HistoryWindow(ManagedToplevel):
    """Floating window wrapper around ``HistoryPanel`` (opened by F9)."""

    window_key = "history"
    window_title = "History"
    default_size = (DIALOG_W, DIALOG_H)
    min_size = (220, 200)
    fg_color = BG

    def __init__(
        self,
        parent,
        project: "Project",
        on_close: Callable[[], None] | None = None,
    ):
        self.project = project
        super().__init__(parent)
        self.set_on_close(on_close)

    def build_content(self) -> ctk.CTkFrame:
        return HistoryPanel(self, self.project)

    def default_offset(self, parent) -> tuple[int, int]:
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            return (px + pw - self.default_size[0] - 30, py + 340)
        except tk.TclError:
            return (100, 100)
