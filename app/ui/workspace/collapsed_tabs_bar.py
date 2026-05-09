"""Bottom-of-workspace strip listing minimised documents.

Lives outside the canvas so the tabs stay reachable regardless of
canvas scroll / zoom. Each entry shows the doc's accent colour as a
left bar, its name, a restore button, and an X. Click on the body or
restore icon to expand the doc back to the canvas; click the X to
remove the doc (Toplevel) or close the project (main window) — same
behaviour as the chrome ✕.

Auto-hides itself when no doc is collapsed so it doesn't reserve UI
space when there's nothing to show.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from app.ui.icons import load_tk_icon
from app.ui.system_fonts import ui_font

BAR_BG = "#252526"
TAB_BG = "#2d2d30"
TAB_BG_HOVER = "#3a3a3c"
TAB_FG = "#cccccc"
TAB_FG_DIM = "#888888"
TAB_HEIGHT = 22
TAB_LEFT_BAR_WIDTH = 3
CLOSE_HOVER_BG = "#c42b1c"


class CollapsedTabsBar(ctk.CTkFrame):
    """Horizontal strip of minimised-document chips, docked above the
    workspace status bar. Subscribes to the project event bus for the
    bus events that change the visible label set (collapse / rename /
    add / remove / reorder)."""

    def __init__(self, master, workspace) -> None:
        super().__init__(
            master, fg_color=BAR_BG, corner_radius=0, height=TAB_HEIGHT + 4,
        )
        self.workspace = workspace
        self._tab_frames: list[tk.Frame] = []
        self.pack_propagate(False)
        bus = self.project.event_bus
        bus.subscribe(
            "document_collapsed_changed",
            lambda *_a, **_k: self.refresh(),
        )
        bus.subscribe(
            "document_added", lambda *_a, **_k: self.refresh(),
        )
        bus.subscribe(
            "document_removed", lambda *_a, **_k: self.refresh(),
        )
        bus.subscribe(
            "document_renamed", lambda *_a, **_k: self.refresh(),
        )
        bus.subscribe(
            "documents_reordered", lambda *_a, **_k: self.refresh(),
        )
        # Window renames route through ``widget_renamed`` with the
        # WINDOW_ID sentinel — pick those up too so the tab title
        # tracks the chrome title.
        bus.subscribe(
            "widget_renamed", self._on_widget_renamed,
        )
        self.after(0, self.refresh)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------
    @property
    def project(self):
        return self.workspace.project

    # ------------------------------------------------------------------
    # Bus hooks
    # ------------------------------------------------------------------
    def _on_widget_renamed(self, widget_id: str, _new_name: str) -> None:
        from app.core.project import WINDOW_ID
        if widget_id == WINDOW_ID:
            self.refresh()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Rebuild the chip list from scratch. Cheap — at most a
        dozen frames in the worst case, only triggered on events that
        already hit the canvas redraw."""
        for frame in self._tab_frames:
            try:
                frame.destroy()
            except tk.TclError:
                pass
        self._tab_frames = []
        collapsed = [d for d in self.project.documents if d.collapsed]
        if not collapsed:
            try:
                self.pack_forget()
            except tk.TclError:
                pass
            return
        # Re-pack ourselves above the status bar — pack order: bar
        # first (side=bottom), tabs second (side=bottom) puts tabs
        # above the bar. The status bar is packed in
        # ``WorkspaceControls.build_status_bar`` before we get here.
        if not self.winfo_ismapped():
            try:
                self.pack(side="bottom", fill="x")
            except tk.TclError:
                pass
        for doc in collapsed:
            self._build_chip(doc)

    def _build_chip(self, doc) -> None:
        # Use raw tk widgets — CTkButton / CTkFrame have a minimum
        # canvas-rendered footprint that makes ``width=12`` etc. lie,
        # so the chip stayed wide despite my reductions. tk.Label /
        # tk.Frame honour pixel sizes exactly. The chip frame lets
        # its children dictate its size (no pack_propagate(False))
        # so it shrink-wraps the title + close button.
        chip = tk.Frame(self, bg=TAB_BG)
        chip.pack(side="left", padx=(2, 0), pady=2)
        accent = self.project.get_accent_color(doc.id)
        bar = tk.Frame(
            chip, bg=accent, width=TAB_LEFT_BAR_WIDTH,
        )
        bar.pack(side="left", fill="y")
        title = tk.Label(
            chip, text=str(doc.name or "Untitled"),
            fg=TAB_FG, bg=TAB_BG, font=ui_font(10),
            padx=5, pady=2, bd=0,
        )
        title.pack(side="left")
        close_icon = load_tk_icon("x", size=12, color=TAB_FG)
        close_btn = tk.Label(
            chip, image=close_icon if close_icon else None,
            text="" if close_icon else "✕",
            fg=TAB_FG, bg=TAB_BG, bd=0, padx=2, pady=0,
            cursor="hand2",
        )
        close_btn.image = close_icon  # keep ref so tk doesn't GC
        close_btn.pack(side="right", padx=(0, 3))
        close_btn.bind(
            "<Button-1>",
            lambda _e, d=doc.id: self._on_close(d),
        )
        close_btn.bind(
            "<Enter>",
            lambda _e: close_btn.configure(bg=CLOSE_HOVER_BG),
        )
        close_btn.bind(
            "<Leave>",
            lambda _e: close_btn.configure(bg=TAB_BG),
        )
        # Click anywhere on the body / title / accent bar restores.
        for clickable in (chip, bar, title):
            clickable.bind(
                "<Button-1>",
                lambda _e, d=doc.id: self._on_restore(d),
            )
            clickable.configure(cursor="hand2")
        # Hover only on chip body — close button has its own red
        # hover, swapping bg when the cursor is over title would fight
        # the close hover.
        chip.bind(
            "<Enter>",
            lambda _e: self._set_chip_bg(chip, title, bar, TAB_BG_HOVER),
        )
        chip.bind(
            "<Leave>",
            lambda _e: self._set_chip_bg(chip, title, bar, TAB_BG, accent),
        )
        self._tab_frames.append(chip)

    def _set_chip_bg(
        self, chip, title, bar, bg: str, accent: str | None = None,
    ) -> None:
        try:
            chip.configure(bg=bg)
            title.configure(bg=bg)
            # The accent bar keeps its colour on hover — only restore
            # the original accent on leave (when ``accent`` is passed).
            if accent is not None:
                bar.configure(bg=accent)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Click handlers
    # ------------------------------------------------------------------
    def _on_restore(self, doc_id: str) -> None:
        self.project.set_document_collapsed(doc_id, False)

    def _on_close(self, doc_id: str) -> None:
        doc = self.project.get_document(doc_id)
        if doc is None:
            return
        if doc.is_toplevel:
            # Same flow as chrome ✕ on a Toplevel — route through
            # ChromeManager.remove_document so the delete-flow dialog
            # surfaces and history records the deletion.
            chrome = self.workspace.chrome
            if chrome is not None:
                chrome.remove_document(doc_id)
        else:
            self.project.event_bus.publish("request_close_project")
