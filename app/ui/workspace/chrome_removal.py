"""Document removal helper for ``ChromeManager``.

* ``remove_document`` — the chrome × click + ``ChromeButtons.on_close_click``
  funnel here when a Toplevel chrome is closed. Surfaces the
  full Window-delete dialog (script + variable counts, where to
  route the .py — recycle bin or scripts_archive) before any
  geometry / model mutation, then auto-shifts right-of-deleted
  docs left to fill the gap and pushes a ``DeleteDocumentCommand``
  with the shift snapshot so undo replays both restore + un-shift.
* ``_compute_delete_shifts`` — surveys every non-collapsed doc
  to the right of the deleted one whose vertical span overlaps it
  and returns a per-doc shift snapshot for the auto-shift loop.

Lives on ``ChromeManager.removal``; ``ChromeButtons.on_close_click``
hands off here when the close target is a Toplevel.
"""
from __future__ import annotations


# Horizontal gap between docs after an auto-shift. Matches the
# 120 px gap MainWindow._add_document / Project._shift_if_position
# _occluded use when placing new docs to the right of existing
# ones — keeps the visual rhythm consistent.
_DOC_AUTO_SHIFT_GAP = 120


class ChromeRemoval:
    """Document remove + auto-shift helper. See module docstring."""

    def __init__(self, chrome) -> None:
        self.chrome = chrome

    def remove_document(self, doc_id: str) -> None:
        from app.core.commands import DeleteDocumentCommand
        from app.ui.handler_delete_dialogs import run_window_delete_flow
        chrome = self.chrome
        doc = chrome.project.get_document(doc_id)
        if doc is None or not doc.is_toplevel:
            return
        # Phase 2 Step 3 — the dialog surfaces script + variable
        # counts, lets the user route the .py to recycle bin or
        # ``assets/scripts_archive/<page>/`` before the document
        # itself goes (Decisions C=B, K=B, send2trash default).
        if not run_window_delete_flow(
            chrome.workspace.winfo_toplevel(), chrome.project, doc,
        ):
            return
        snapshot = doc.to_dict()
        doc_name = doc.name
        index = chrome.project.documents.index(doc)
        # Compute auto-shift: right neighbours that vertically overlap
        # the deleted doc slide left to fill the gap. Captured BEFORE
        # mutation so the undo path on DeleteDocumentCommand can
        # replay both restore + un-shift.
        shifts = self._compute_delete_shifts(doc)
        for node in list(doc.root_widgets):
            chrome.project.remove_widget(node.id)
        chrome.project.documents.remove(doc)
        # Apply the shifts now that the doc is gone.
        for sid, _bx, _by, ax, ay in shifts:
            sdoc = chrome.project.get_document(sid)
            if sdoc is None:
                continue
            sdoc.canvas_x, sdoc.canvas_y = int(ax), int(ay)
            chrome.project.event_bus.publish(
                "document_position_changed", sid,
            )
        if chrome.project.active_document_id == doc_id:
            chrome.project.active_document_id = (
                chrome.project.documents[0].id
            )
            chrome.project.event_bus.publish(
                "active_document_changed",
                chrome.project.active_document_id,
            )
        chrome.workspace._redraw_document()
        # Phase 2 Step 3 — fire ``document_removed`` so the auto-save
        # subscriber in MainWindow persists the .ctkproj (otherwise
        # the deleted dialog could come back after a reload) and the
        # asset panel refreshes its tree to drop the now-deleted
        # behavior file row.
        chrome.project.event_bus.publish(
            "document_removed", doc_id, doc_name,
        )
        chrome.project.history.push(
            DeleteDocumentCommand(snapshot, index, shifts=shifts),
        )

    def _compute_delete_shifts(self, deleted_doc) -> list:
        """Return ``[(doc_id, before_x, before_y, after_x, after_y)]``
        for every non-collapsed doc to the right of ``deleted_doc``
        whose vertical span overlaps it. Each gets shifted left by
        ``deleted.width + _DOC_AUTO_SHIFT_GAP``. Vertically separate
        docs aren't touched so a user-arranged second row stays put.
        """
        chrome = self.chrome
        d_top = deleted_doc.canvas_y
        d_bot = deleted_doc.canvas_y + deleted_doc.height
        d_left = deleted_doc.canvas_x
        shift_dx = deleted_doc.width + _DOC_AUTO_SHIFT_GAP
        shifts: list = []
        for other in chrome.project.documents:
            if other.id == deleted_doc.id or other.collapsed:
                continue
            if other.canvas_x <= d_left:
                continue
            # Vertical overlap test — non-overlapping rows stay put.
            if (
                other.canvas_y >= d_bot
                or other.canvas_y + other.height <= d_top
            ):
                continue
            bx, by = other.canvas_x, other.canvas_y
            ax = max(0, other.canvas_x - shift_dx)
            shifts.append((other.id, bx, by, ax, by))
        return shifts
