"""Document-level commands — add / delete / arrange / move on canvas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.commands.base import Command

if TYPE_CHECKING:
    from app.core.project import Project


def _restore_document(
    project: "Project", snapshot: dict, index: int,
) -> None:
    """Re-instantiate a Document from a saved snapshot at the
    original list position and replay every widget so workspace /
    inspectors rebuild their views in the new document.
    """
    from app.core.document import Document
    doc = Document.from_dict(snapshot)
    roots = list(doc.root_widgets)
    doc.root_widgets = []
    pos = max(0, min(int(index), len(project.documents)))
    project.documents.insert(pos, doc)
    project.active_document_id = doc.id
    # ``document_added`` fires before ``active_document_changed`` so
    # subscribers (Phase 2 eager behavior-file creation lives in
    # ``MainWindow``) can materialise side files / asset folders
    # before the workspace re-renders against the new doc.
    project.event_bus.publish("document_added", doc.id)
    project.event_bus.publish("active_document_changed", doc.id)
    for node in roots:
        children = list(node.children)
        node.children = []
        node.parent = None
        project.add_widget(node, parent_id=None)
        _replay_children(project, node, children)


def _replay_children(project, parent_node, children) -> None:
    for child in children:
        grand = list(child.children)
        child.children = []
        child.parent = None
        project.add_widget(child, parent_id=parent_node.id)
        _replay_children(project, child, grand)


def _remove_document_by_id(project: "Project", doc_id: str) -> None:
    doc = project.get_document(doc_id)
    if doc is None:
        return
    # Capture before we mutate so the document_removed publish
    # (Phase 2 Step 3) can pass the doc's display name to its
    # behavior-file archiver — by the time the archive subscriber
    # runs the doc is already gone from the project.
    doc_name = doc.name
    for node in list(doc.root_widgets):
        project.remove_widget(node.id)
    if doc in project.documents:
        project.documents.remove(doc)
    if project.active_document_id == doc_id and project.documents:
        project.active_document_id = project.documents[0].id
    project.event_bus.publish(
        "active_document_changed", project.active_document_id,
    )
    project.event_bus.publish("document_removed", doc_id, doc_name)


class AddDocumentCommand(Command):
    """Adding a brand-new Document (main window or dialog) to the
    project. Snapshot captures the full Document state so undo can
    recreate it at its original list position with its widgets intact.
    """

    def __init__(self, snapshot: dict, index: int):
        self._snapshot = snapshot
        self._index = index
        self.description = f"Add {snapshot.get('name', 'document')}"

    def undo(self, project: "Project") -> None:
        _remove_document_by_id(project, self._snapshot["id"])

    def redo(self, project: "Project") -> None:
        _restore_document(project, self._snapshot, self._index)


class DeleteDocumentCommand(Command):
    """Removing a Document (typically a dialog — the main window is
    protected). Snapshot + index mirror AddDocumentCommand; their
    undo / redo sides are the same mechanic in opposite directions.

    Optional ``shifts``: list of ``(doc_id, before_x, before_y,
    after_x, after_y)`` for sibling docs that auto-shifted left to
    fill the deleted slot. Undo restores their original positions
    after the doc is re-inserted; redo re-applies the shifts.
    """

    def __init__(
        self,
        snapshot: dict,
        index: int,
        shifts: list | None = None,
    ):
        self._snapshot = snapshot
        self._index = index
        self._shifts = list(shifts) if shifts else []
        self.description = f"Delete {snapshot.get('name', 'document')}"

    def undo(self, project: "Project") -> None:
        _restore_document(project, self._snapshot, self._index)
        # Restore siblings to their pre-delete positions in REVERSE
        # order — symmetric with redo so chains of shift values stay
        # consistent when commands interleave.
        for doc_id, bx, by, _ax, _ay in self._shifts:
            doc = project.get_document(doc_id)
            if doc is None:
                continue
            doc.canvas_x, doc.canvas_y = int(bx), int(by)
            project.event_bus.publish(
                "document_position_changed", doc_id,
            )

    def redo(self, project: "Project") -> None:
        _remove_document_by_id(project, self._snapshot["id"])
        for doc_id, _bx, _by, ax, ay in self._shifts:
            doc = project.get_document(doc_id)
            if doc is None:
                continue
            doc.canvas_x, doc.canvas_y = int(ax), int(ay)
            project.event_bus.publish(
                "document_position_changed", doc_id,
            )


class ArrangeDocumentsCommand(Command):
    """Repositions every visible (non-collapsed) document on the
    canvas in one undoable step. ``before`` / ``after`` are lists of
    ``(doc_id, x, y)`` for each doc that gets moved. Triggered by the
    Arrange Horizontally / Arrange Vertically entries on the All
    Windows dropdown.
    """

    def __init__(
        self,
        before: list,
        after: list,
        axis: str,
    ):
        self._before = list(before)
        self._after = list(after)
        self.description = f"Arrange documents ({axis})"

    def _apply(self, project: "Project", positions: list) -> None:
        for doc_id, x, y in positions:
            doc = project.get_document(doc_id)
            if doc is None:
                continue
            doc.canvas_x, doc.canvas_y = int(x), int(y)
            project.event_bus.publish(
                "document_position_changed", doc_id,
            )

    def undo(self, project: "Project") -> None:
        self._apply(project, self._before)

    def redo(self, project: "Project") -> None:
        self._apply(project, self._after)


class MoveDocumentCommand(Command):
    """Dragging a document's title bar to a new canvas position.
    Only the canvas_x / canvas_y change — widgets stay put relative
    to their document, so undo is just a coord swap.
    """

    def __init__(
        self,
        document_id: str,
        before: tuple[int, int],
        after: tuple[int, int],
    ):
        self.document_id = document_id
        self.before = before
        self.after = after
        self.description = "Move document"

    def _apply(self, project: "Project", xy: tuple[int, int]) -> None:
        doc = project.get_document(self.document_id)
        if doc is None:
            return
        doc.canvas_x, doc.canvas_y = int(xy[0]), int(xy[1])
        # Widgets are rendered via ``canvas.create_window`` at
        # ``logical_to_canvas(x, y, document=doc)`` — mutating the doc's
        # canvas_x/canvas_y alone doesn't move them. The live drag path
        # fires zoom.apply_all() + selection.update() alongside the
        # redraw; the undo/redo path publishes this event so the
        # workspace replays the same three steps.
        project.event_bus.publish(
            "document_position_changed", self.document_id,
        )

    def undo(self, project: "Project") -> None:
        self._apply(project, self.before)

    def redo(self, project: "Project") -> None:
        self._apply(project, self.after)
