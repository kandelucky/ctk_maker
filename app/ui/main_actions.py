"""Misc action handlers extracted from the monolithic ``main_window.py``.

Covers three groupings that don't fit the file / document / window /
preview mixins:

* **Appearance + Help menu** — ``_on_appearance_change``, ``_open_url``,
  the Documentation / User Guide / Widget Catalog / Keyboard Shortcuts
  / Report Bug / About handlers.
* **Undo / Redo + Alignment** — toolbar-driven history operations and
  the multi-widget align / distribute resolver.
* **Theme + window state** — ``_on_theme_toggle``, geometry centring,
  saved-geometry restore, ``zoomed`` (Windows-maximized) helpers.

The mixin inherits ``_MainWindowHost`` so pyright resolves
``self.project`` / ``self.toolbar`` / ``self._appearance_var`` against
the host stub instead of flagging them per call site.
"""
from __future__ import annotations

import tkinter as tk
import webbrowser

import customtkinter as ctk

from app.core.logger import log_error
from app.core.settings import load_settings, save_setting
from app.ui._main_window_host import _MainWindowHost


WIKI_BASE_URL = "https://github.com/kandelucky/ctk_maker/wiki"
WIKI_USER_GUIDE_URL = f"{WIKI_BASE_URL}/User-Guide"
WIKI_WIDGETS_URL = f"{WIKI_BASE_URL}/Widgets"
WIKI_SHORTCUTS_URL = f"{WIKI_BASE_URL}/Keyboard-Shortcuts"


class ActionsMixin(_MainWindowHost):
    """Help-menu links, appearance + theme toggles, undo/redo, align,
    window-state persistence. See module docstring.
    """

    # ------------------------------------------------------------------
    # Appearance + Help menu
    # ------------------------------------------------------------------
    def _on_appearance_change(self) -> None:
        mode = self._appearance_var.get()
        ctk.set_appearance_mode(mode.lower())
        save_setting("appearance_mode", mode)

    def _open_url(self, url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception:
            log_error(f"open url {url}")

    def _on_widget_docs(self) -> None:
        # Help → Documentation entry — points at the wiki landing page
        # so users can navigate to whichever section they need.
        self._open_url(WIKI_BASE_URL)

    def _on_user_guide(self) -> None:
        self._open_url(WIKI_USER_GUIDE_URL)

    def _on_widget_catalog(self) -> None:
        self._open_url(WIKI_WIDGETS_URL)

    def _on_keyboard_shortcuts(self) -> None:
        self._open_url(WIKI_SHORTCUTS_URL)

    def _on_report_bug(self) -> None:
        from app.ui.bug_reporter import BugReporterWindow
        BugReporterWindow(self)

    def _on_about(self) -> None:
        from app.ui.dialogs import AboutDialog
        from app import __version__ as app_version
        AboutDialog(self, app_version=f"v{app_version}")

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------
    def _on_undo(self) -> str | None:
        # Always route Ctrl+Z through the project history, even when
        # an Entry widget has focus — the name entry's edits are
        # already tracked as coalesced RenameCommands, so app-level
        # undo is the right behaviour everywhere.
        self.project.history.undo()
        return "break"

    def _on_redo(self) -> str | None:
        self.project.history.redo()
        return "break"

    def _refresh_undo_redo_buttons(self) -> None:
        if not hasattr(self, "toolbar"):
            return
        self.toolbar.set_undo_enabled(self.project.history.can_undo())
        self.toolbar.set_redo_enabled(self.project.history.can_redo())

    # ------------------------------------------------------------------
    # Alignment + distribution
    # ------------------------------------------------------------------
    def _resolve_align_targets(self) -> tuple[list, object | None, tuple[int, int] | None]:
        """Resolve which widgets (if any) the alignment buttons
        currently operate on, plus the container reference.

        Returns ``(units, parent_node, container_size)`` where:
          - ``units`` is a list of node-lists. Each unit moves as one
            block: a fully-selected group becomes one multi-widget
            unit, every other selected widget becomes a singleton.
            Empty disables all buttons; widgets in a layout-managed
            parent are dropped since the layout owns positioning.
          - ``parent_node`` is the shared parent (``None`` for
            top-level / mixed-parent selections)
          - ``container_size`` is ``(width, height)`` for the parent
            container, or ``None`` when aligning to selection bbox
        """
        from app.widgets.layout_schema import is_layout_container
        sel_ids = list(self.project.selected_ids or [])
        if not sel_ids:
            return [], None, None
        nodes = [
            self.project.get_widget(wid)
            for wid in sel_ids
        ]
        nodes = [n for n in nodes if n is not None and getattr(n, "id", None) is not None]
        if not nodes:
            return [], None, None
        # All selected nodes must share a parent — mixed-parent
        # selections don't have a coherent coordinate space.
        parents = {id(n.parent) for n in nodes}
        if len(parents) != 1:
            return [], None, None
        parent = nodes[0].parent
        # Layout-managed children: layout manager owns x/y, so
        # alignment is meaningless. Block the whole action.
        if parent is not None and is_layout_container(parent.properties):
            return [], parent, None
        # Container size: for top-level widgets use the document
        # bounds; for nested widgets use the parent's width/height.
        if parent is None:
            doc = self.project.find_document_for_widget(nodes[0].id)
            if doc is None:
                doc = self.project.active_document
            container_size = (doc.width, doc.height)
        else:
            container_size = (
                int(parent.properties.get("width", 0) or 0),
                int(parent.properties.get("height", 0) or 0),
            )
        # Bundle selected group members into one unit per group_id;
        # ungrouped widgets stay as singleton units. This is what
        # makes "align group to other widget" treat the group as one
        # block rather than aligning members against each other first.
        units: list[list] = []
        seen_gids: set = set()
        for n in nodes:
            gid = getattr(n, "group_id", None)
            if gid:
                if gid in seen_gids:
                    continue
                members = [
                    m for m in nodes
                    if getattr(m, "group_id", None) == gid
                ]
                seen_gids.add(gid)
                units.append(members)
            else:
                units.append([n])
        # When 2+ units, switch reference to selection bbox so the
        # buttons mean "align units to each other". A single unit
        # (one widget OR one whole selected group) aligns to its
        # container.
        use_container = len(units) == 1
        return units, parent, container_size if use_container else None

    def _refresh_align_buttons(self) -> None:
        if not hasattr(self, "toolbar"):
            return
        from app.core.alignment import (
            ALIGN_MODES, MODE_DISTRIBUTE_H, MODE_DISTRIBUTE_V,
        )
        units, _parent, _container = self._resolve_align_targets()
        # Align-to-selection needs 2+ units to be useful; align-to-
        # container works with 1. Distribute always needs 3+ units.
        align_on = bool(units)
        distribute_on = len(units) >= 3
        states: dict[str, bool] = {
            mode: align_on for mode in ALIGN_MODES
        }
        states[MODE_DISTRIBUTE_H] = distribute_on
        states[MODE_DISTRIBUTE_V] = distribute_on
        self.toolbar.set_align_enabled(states)

    def _on_align_action(self, mode: str) -> None:
        from app.core.alignment import (
            DISTRIBUTE_MODES,
            compute_align_units,
            compute_distribute_units,
        )
        units, _parent, container_size = self._resolve_align_targets()
        if not units:
            return
        if mode in DISTRIBUTE_MODES:
            moves = compute_distribute_units(units, mode)
        else:
            moves = compute_align_units(
                units, mode, container_size=container_size,
            )
        # Drop no-op tuples so the history entry doesn't show the
        # widgets that were already aligned. If everything was
        # already aligned, do nothing.
        moves = [(wid, b, a) for wid, b, a in moves if b != a]
        if not moves:
            return
        from app.core.commands import BulkMoveCommand
        cmd = BulkMoveCommand(moves)
        cmd.redo(self.project)
        self.project.history.push(cmd)

    # ------------------------------------------------------------------
    # Theme + window state
    # ------------------------------------------------------------------
    def _on_theme_toggle(self) -> None:
        current = self._appearance_var.get()
        nxt = "Light" if current == "Dark" else "Dark"
        self._appearance_var.set(nxt)
        self._on_appearance_change()

    def _set_centered_geometry(self, desired_w: int, desired_h: int) -> None:
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(desired_w, sw - 80)
        h = min(desired_h, sh - 120)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2 - 20)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _apply_saved_window_state(self) -> None:
        settings = load_settings()
        saved_geom = settings.get("window_geometry")
        applied = False
        if isinstance(saved_geom, str) and saved_geom:
            try:
                self.geometry(saved_geom)
                applied = True
            except tk.TclError:
                applied = False
        if not applied:
            self._set_centered_geometry(1280, 800)
        self._wants_maximized = bool(settings.get("window_maximized"))

    def _safe_zoom(self) -> None:
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

    def _save_window_state(self) -> None:
        try:
            is_max = self.state() == "zoomed"
        except tk.TclError:
            is_max = False
        save_setting("window_maximized", is_max)
        if not is_max:
            try:
                save_setting("window_geometry", self.geometry())
            except tk.TclError:
                pass
