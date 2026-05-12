"""Chrome icon-button click handlers extracted from ``ChromeManager``.

Each ``_on_*_click`` is the ``tag_bind`` target for one icon in the
title strip — Bring-to-Front / Send-to-Back / Preview / Export /
Settings / Description / Variables (Local) / Minimize / Close.

The helpers all run in two well-defined steps: activate the
clicked document (or operate on its id), then route the action
through ``project.event_bus`` (for cross-module flows: Preview,
Export, Description, Variables, Close-project) or directly mutate
the project (z-order, minimize). Returns ``"break"`` so the
``tag_bind`` chain doesn't fall through to the canvas-level
``<Button-1>`` handler and reset the selection.

Lives on ``ChromeManager.buttons``; ``ChromeManager._bind_for_document``
points the per-icon ``tag_bind`` callbacks at these methods directly
(no pass-throughs needed since the binding code is in the same
module).
"""
from __future__ import annotations

import tkinter as tk


class ChromeButtons:
    """Click handlers for every icon in the chrome strip.
    See module docstring.
    """

    def __init__(self, chrome) -> None:
        self.chrome = chrome

    def on_tofront_click(self, doc_id: str) -> str:
        self.chrome.project.bring_document_to_front(doc_id)
        return "break"

    def on_toback_click(self, doc_id: str) -> str:
        self.chrome.project.send_document_to_back(doc_id)
        return "break"

    def on_preview_click(self, doc_id: str) -> str:
        """Launch a dialog-only preview subprocess — hidden root host
        + this Toplevel on top. Routes through the workspace's event
        bus so main_window owns the subprocess lifecycle (same place
        Ctrl+R is handled).
        """
        self.chrome.project.event_bus.publish(
            "request_preview_dialog", doc_id,
        )
        return "break"

    def on_export_click(self, doc_id: str) -> str:
        """Export just this dialog as a standalone .py — routes
        through the event bus so main_window owns the file dialog
        + write flow (same handler as File → Export Active Document).
        """
        self.chrome.project.event_bus.publish(
            "request_export_document", doc_id,
        )
        return "break"

    # ------------------------------------------------------------------
    # Selection + settings
    # ------------------------------------------------------------------
    def select(self, doc_id: str | None = None) -> None:
        from app.core.project import WINDOW_ID
        if doc_id is not None:
            self.chrome.project.set_active_document(doc_id)
        self.chrome.project.select_widget(WINDOW_ID)

    def on_settings_click(
        self, _event=None, doc_id: str | None = None,
    ) -> str:
        self.select(doc_id)
        return "break"

    def on_desc_click(self, doc_id: str) -> str:
        """Open the AI-bridge description editor for the clicked
        document. Selects the document's window first so the
        properties panel is on the right context, then asks it to
        open the dialog via an event-bus request."""
        self.select(doc_id)
        self.chrome.project.event_bus.publish("request_edit_description")
        return "break"

    def on_vars_click(self, doc_id: str, scope: str) -> str:
        """Open the Variables window on the matching tab. Activates
        the clicked document first so the Local tab targets it."""
        self.chrome.project.set_active_document(doc_id)
        self.chrome.project.event_bus.publish(
            "request_open_variables_window", scope, doc_id,
        )
        return "break"

    def set_cursor(self, cursor: str) -> None:
        # Don't fight the current tool's cursor (Hand mode owns
        # the cursor for the whole canvas).
        chrome = self.chrome
        if not cursor:
            cursor = chrome.workspace.default_tool_cursor()
        try:
            chrome.canvas.configure(cursor=cursor)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Minimize → collapse to bottom workspace tab strip
    # ------------------------------------------------------------------
    def on_minimize_click(self, doc_id: str) -> str:
        self.chrome.project.set_document_collapsed(doc_id, True)
        return "break"

    # ------------------------------------------------------------------
    # Close → remove document
    # ------------------------------------------------------------------
    def on_close_click(
        self, _event=None, doc_id: str | None = None,
    ) -> str:
        # Dialog chrome close = remove that dialog from the project.
        # Main window chrome close = project-level close (File/Close).
        # Mirrors OS native behaviour.
        chrome = self.chrome
        if doc_id is not None:
            doc = chrome.project.get_document(doc_id)
            if doc is not None and doc.is_toplevel:
                chrome.removal.remove_document(doc_id)
                return "break"
        chrome.project.event_bus.publish("request_close_project")
        return "break"
