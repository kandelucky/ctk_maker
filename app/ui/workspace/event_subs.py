"""Event-bus subscriber sidecar for ``Workspace``.

Wraps every ``project.event_bus`` handler that translates a model
change into a canvas update — document add / remove / rename /
active-switch / reorder / position / collapse / ghost, project
rename, dirty toggle, widget rename, variable type / default
changes. The actual ``subscribe`` calls still live in
``Workspace._subscribe_events`` so the wiring stays visible in one
place; this class only owns the callback bodies.

Callbacks lean on ``self.workspace.<attr>`` for everything they
touch (``project``, ``ghost_manager``, ``selection``, ``zoom``, the
``_redraw_document`` / ``_draw_window_chrome`` helpers that stay in
core). Mirrors the delegation pattern used by ``ChromeManager`` and
the other sibling sidecars.
"""
from __future__ import annotations


class EventSubscriberRouter:
    """Callback bodies for ``project.event_bus`` subscriptions.
    See module docstring.
    """

    def __init__(self, workspace) -> None:
        self.workspace = workspace

    def on_document_removed_ghost_cleanup(
        self, doc_id: str, _doc_name: str,
    ) -> None:
        """A ghosted doc that gets deleted otherwise leaves its image
        item on the canvas — ``_redraw_document`` only clears DOC /
        GRID / CHROME / LAYOUT_OVERLAY tags, never the per-doc
        ``ghost:<id>`` tag. Purge here so the canvas doesn't keep a
        screenshot for a doc that no longer exists."""
        if self.workspace.ghost_manager is not None:
            self.workspace.ghost_manager.purge(doc_id)

    def on_document_ghost_changed(
        self, doc_id: str, ghost: bool,
    ) -> None:
        # Lifecycle has no separate handler for ghost — the GhostManager
        # owns the freeze/unfreeze. The redraw afterwards repaints the
        # ghost statusbar in its new colour / label so the user sees
        # the state flip immediately.
        ws = self.workspace
        doc = ws.project.get_document(doc_id)
        if doc is None:
            return
        if ghost:
            ws.ghost_manager.freeze(doc)
        else:
            ws.ghost_manager.unfreeze(doc)
        ws._redraw_document()
        ws._redraw_document()

    def on_document_collapsed_changed(
        self, _doc_id: str, _collapsed: bool,
    ) -> None:
        # Lifecycle subscriber tears down or rebuilds widget views.
        # The canvas redraw afterwards repaints chrome (or hides it,
        # for a collapse) and refreshes the bottom-left tab strip.
        self.workspace._redraw_document()

    def on_active_document_changed(self, *_args, **_kwargs) -> None:
        # Add / remove / active-switch of a document changes which
        # chrome strip is highlighted and, on add/remove, the total
        # scroll region. A full redraw covers both cheaply.
        ws = self.workspace
        ws._redraw_document()
        # Center viewport on the now-active document so the user
        # never ends up looking at the wrong canvas region after a
        # cross-document switch (project load, Object Tree click on
        # a widget in another document, programmatic switch, …).
        ws.focus_document(ws.project.active_document_id)

    def on_documents_reordered(self, *_args, **_kwargs) -> None:
        # Send-to-Back / Bring-to-Front swap the drawing order; a
        # full redraw rebuilds the canvas stack in the new order.
        self.workspace._redraw_document()

    def on_document_position_changed(self, *_args, **_kwargs) -> None:
        # MoveDocumentCommand undo/redo path — mirror the live drag:
        # redraw background/chrome, re-place every widget against the
        # new canvas offset, refresh selection chrome if any.
        ws = self.workspace
        ws._redraw_document()
        ws.zoom.apply_all()
        # Ghost images need an explicit move — they're not in
        # widget_views and aren't touched by apply_all.
        if getattr(ws, "ghost_manager", None) is not None:
            for doc in ws.project.documents:
                if doc.ghosted:
                    ws.ghost_manager.reposition_doc(doc)
        if ws.project.selected_id:
            ws.selection.update()

    def on_any_widget_renamed(
        self, widget_id: str, _new_name: str,
    ) -> None:
        # Window renames retarget the active document's title —
        # repaint the canvas chrome so the new title shows up.
        from app.core.project import WINDOW_ID
        if widget_id == WINDOW_ID:
            self.workspace._draw_window_chrome()

    def on_project_renamed(self, *_args, **_kwargs) -> None:
        # The canvas title strip mirrors `project.name`; New / Open /
        # Save As all publish this event so the chrome repaints
        # without needing a full document rebuild.
        self.workspace._draw_window_chrome()

    def on_dirty_changed(self, dirty, *_args, **_kwargs) -> None:
        ws = self.workspace
        new_dirty = bool(dirty)
        if new_dirty == ws._dirty:
            return
        ws._dirty = new_dirty
        ws._draw_window_chrome()
