"""History inspector — shows the Undo/Redo stack as a floating list.

Mirrors ``ObjectTreeWindow``'s shape (CTkToplevel + ttk.Treeview) but
much simpler: one column, no drag/drop, no context menu. Entries above
the current position are past operations (undoable); entries below are
future operations (redoable, dimmed).

Refreshes on the project event bus's ``history_changed`` event so it
stays in sync with toolbar buttons and keyboard shortcuts.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

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


class HistoryWindow(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        project: "Project",
        on_close: Callable[[], None] | None = None,
    ):
        super().__init__(parent)
        self.title("History")
        self.configure(fg_color=BG)
        self.geometry(f"{DIALOG_W}x{DIALOG_H}")
        self.minsize(220, 200)

        try:
            self.transient(parent)
        except tk.TclError:
            pass

        self.project = project
        self._on_close_callback = on_close

        self._build_tree()
        self._place_relative_to(parent)

        bus = project.event_bus
        self._bus_subs: list[tuple[str, Callable]] = []
        for evt in ("history_changed",):
            bus.subscribe(evt, self._on_history_changed)
            self._bus_subs.append((evt, self._on_history_changed))

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(0, self._refresh)

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------
    def _build_tree(self) -> None:
        container = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0)
        container.pack(fill="both", expand=True, padx=6, pady=6)

        style = ttk.Style(self)
        style_name = "History.Treeview"
        style.configure(
            style_name,
            background=TREE_BG,
            fieldbackground=TREE_BG,
            foreground=TREE_FG,
            rowheight=TREE_ROW_HEIGHT,
            borderwidth=0,
            font=("Segoe UI", TREE_FONT_SIZE),
        )
        style.map(
            style_name,
            background=[("selected", TREE_SELECTED_BG)],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            f"{style_name}.Heading",
            background=TREE_HEADING_BG,
            foreground=TREE_HEADING_FG,
            font=("Segoe UI", TREE_FONT_SIZE, "bold"),
            borderwidth=0,
        )

        self.tree = ttk.Treeview(
            container,
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

        vsb = ttk.Scrollbar(
            container, orient="vertical", command=self.tree.yview,
        )
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    def _place_relative_to(self, parent) -> None:
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            x = px + pw - DIALOG_W - 30
            y = py + 340
            self.geometry(f"{DIALOG_W}x{DIALOG_H}+{x}+{y}")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    def _on_history_changed(self, *_args, **_kwargs) -> None:
        self._refresh()

    def _refresh(self) -> None:
        for iid in self.tree.get_children(""):
            self.tree.delete(iid)
        history = self.project.history
        undo_stack = history._undo  # oldest → newest
        redo_stack = history._redo  # top of stack = next redo
        if not undo_stack and not redo_stack:
            self.tree.insert(
                "", "end", text=EMPTY_TEXT, tags=("empty",),
            )
            return
        for i, cmd in enumerate(undo_stack):
            desc = cmd.description or cmd.__class__.__name__
            self.tree.insert(
                "", "end", iid=f"u:{i}", text=f"  {desc}",
            )
        self.tree.insert(
            "", "end", iid="current",
            text=CURRENT_MARKER, tags=("current",),
        )
        # Redo stack: the LAST entry in self._redo is the next command
        # to run on Ctrl+Y. Display chronologically so the list reads
        # naturally top-to-bottom.
        for i, cmd in enumerate(reversed(redo_stack)):
            desc = cmd.description or cmd.__class__.__name__
            self.tree.insert(
                "", "end", iid=f"r:{i}", text=f"  {desc}", tags=("redo",),
            )
        # Keep the current marker visible without stealing focus.
        try:
            self.tree.see("current")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def _on_close(self) -> None:
        self._unsubscribe_bus()
        if self._on_close_callback is not None:
            try:
                self._on_close_callback()
            except Exception:
                pass
        self.destroy()

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
