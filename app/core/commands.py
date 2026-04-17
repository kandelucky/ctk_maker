"""Undo / redo command objects.

Each command wraps a mutation and knows how to reverse + re-apply
itself. Commands are pushed to ``project.history`` AFTER the
mutation has already been applied — the ``do`` side happens at the
call site (drop, delete, drag-release, etc.), the command only
stores the before/after state needed to replay it both ways.

Widget IDs stay stable across undo/redo because ``WidgetNode.from_dict``
restores the original UUID. That lets properties panel, object tree,
and selection keep their references live even after a delete+undo
round trip.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.core.widget_node import WidgetNode

if TYPE_CHECKING:
    from app.core.project import Project

COALESCE_WINDOW_SEC = 0.6


class Command:
    description: str = ""

    def undo(self, project: "Project") -> None:
        raise NotImplementedError

    def redo(self, project: "Project") -> None:
        raise NotImplementedError

    def merge_into(self, other: "Command") -> bool:
        """If ``other`` (the tail of the undo stack) can absorb this
        command, mutate it in place and return True. Used for
        rapid-fire sequences like arrow-key nudges so they collapse
        into a single undo step.

        Default implementation: never merge.
        """
        return False


class AddWidgetCommand(Command):
    def __init__(
        self,
        snapshot: dict,
        parent_id: str | None,
        index: int | None = None,
    ):
        self._snapshot = snapshot
        self._parent_id = parent_id
        self._index = index
        self.description = f"Add {snapshot.get('widget_type', 'widget')}"

    def undo(self, project: "Project") -> None:
        project.remove_widget(self._snapshot["id"])

    def redo(self, project: "Project") -> None:
        node = WidgetNode.from_dict(self._snapshot)
        project.add_widget(node, parent_id=self._parent_id)
        if self._index is not None:
            project.reparent(node.id, self._parent_id, index=self._index)
        project.select_widget(node.id)


class DeleteWidgetCommand(Command):
    def __init__(
        self,
        snapshot: dict,
        parent_id: str | None,
        index: int,
    ):
        self._snapshot = snapshot
        self._parent_id = parent_id
        self._index = index
        label = snapshot.get("name") or snapshot.get("widget_type", "widget")
        self.description = f"Delete {label}"

    def undo(self, project: "Project") -> None:
        node = WidgetNode.from_dict(self._snapshot)
        project.add_widget(node, parent_id=self._parent_id)
        project.reparent(node.id, self._parent_id, index=self._index)
        project.select_widget(node.id)

    def redo(self, project: "Project") -> None:
        project.remove_widget(self._snapshot["id"])


class DeleteMultipleCommand(Command):
    """Multi-delete bundled into one undo step. Snapshots are stored
    top-down in pre-deletion tree order; undo replays them in the
    same order so each sibling lands back at its original index.
    """

    def __init__(self, entries: list[tuple[dict, str | None, int]]):
        self._entries = entries
        self.description = f"Delete {len(entries)} widgets"

    def undo(self, project: "Project") -> None:
        restored_ids: list[str] = []
        for snapshot, parent_id, index in self._entries:
            node = WidgetNode.from_dict(snapshot)
            project.add_widget(node, parent_id=parent_id)
            project.reparent(node.id, parent_id, index=index)
            restored_ids.append(node.id)
        if restored_ids:
            project.set_multi_selection(
                set(restored_ids), primary=restored_ids[0],
            )

    def redo(self, project: "Project") -> None:
        for snapshot, _parent_id, _index in self._entries:
            project.remove_widget(snapshot["id"])


class ChangePropertyCommand(Command):
    def __init__(
        self,
        widget_id: str,
        prop_name: str,
        before,
        after,
        coalesce_key: str | None = None,
    ):
        self.widget_id = widget_id
        self.prop_name = prop_name
        self.before = before
        self.after = after
        self.coalesce_key = coalesce_key
        self.timestamp = time.monotonic()
        self.description = f"Change {prop_name}"

    def undo(self, project: "Project") -> None:
        project.update_property(self.widget_id, self.prop_name, self.before)
        project.select_widget(self.widget_id)

    def redo(self, project: "Project") -> None:
        project.update_property(self.widget_id, self.prop_name, self.after)
        project.select_widget(self.widget_id)

    def merge_into(self, other: "Command") -> bool:
        if self.coalesce_key is None:
            return False
        if not isinstance(other, ChangePropertyCommand):
            return False
        if other.coalesce_key != self.coalesce_key:
            return False
        if other.widget_id != self.widget_id:
            return False
        if other.prop_name != self.prop_name:
            return False
        if self.timestamp - other.timestamp > COALESCE_WINDOW_SEC:
            return False
        # Extend tail: keep its 'before', adopt our 'after', slide
        # the timestamp forward so rapid sequences keep coalescing.
        other.after = self.after
        other.timestamp = self.timestamp
        return True


class MultiChangePropertyCommand(Command):
    """Bundle multiple property changes for a single widget into
    one undo step. Used when a single UI action triggers derived
    side-effects via the descriptor's ``compute_derived`` hook —
    e.g. setting an image on an Image widget also recomputes its
    height when ``preserve_aspect`` is on. Without bundling, the
    derived change would be lost on undo because only the primary
    commit path pushes history entries.
    """

    def __init__(
        self,
        widget_id: str,
        changes: dict,
    ):
        # changes: {prop_name: (before, after)}
        self.widget_id = widget_id
        self.changes = dict(changes)
        self.description = f"Change {len(changes)} properties"

    def undo(self, project: "Project") -> None:
        for name, (before, _after) in self.changes.items():
            project.update_property(self.widget_id, name, before)
        project.select_widget(self.widget_id)

    def redo(self, project: "Project") -> None:
        for name, (_before, after) in self.changes.items():
            project.update_property(self.widget_id, name, after)
        project.select_widget(self.widget_id)


class MoveCommand(Command):
    """Workspace drag — one entry per press→release. ``before`` and
    ``after`` are dicts like {"x": …, "y": …}.
    """

    def __init__(self, widget_id: str, before: dict, after: dict):
        self.widget_id = widget_id
        self.before = dict(before)
        self.after = dict(after)
        self.description = "Move widget"

    def _apply(self, project: "Project", values: dict) -> None:
        for key, val in values.items():
            project.update_property(self.widget_id, key, val)
        project.select_widget(self.widget_id)

    def undo(self, project: "Project") -> None:
        self._apply(project, self.before)

    def redo(self, project: "Project") -> None:
        self._apply(project, self.after)


class BulkMoveCommand(Command):
    """Multi-widget drag — apply the same delta to every selected
    widget so undo / redo rewinds the whole group as a single step.
    ``moves`` is a list of ``(widget_id, before, after)`` tuples.
    """

    def __init__(self, moves: list):
        self.moves = list(moves)
        label = (
            f"Move {len(self.moves)} widgets" if len(self.moves) != 1
            else "Move widget"
        )
        self.description = label

    def _apply(self, project: "Project", take_before: bool) -> None:
        for widget_id, before, after in self.moves:
            values = before if take_before else after
            for key, val in values.items():
                project.update_property(widget_id, key, val)

    def undo(self, project: "Project") -> None:
        self._apply(project, take_before=True)

    def redo(self, project: "Project") -> None:
        self._apply(project, take_before=False)


class ResizeCommand(MoveCommand):
    """Resize covers x, y, width, height. Shape-identical to Move."""

    def __init__(self, widget_id: str, before: dict, after: dict):
        super().__init__(widget_id, before, after)
        self.description = "Resize widget"


class ReparentCommand(Command):
    """Move a widget between containers via drag. Captures old and
    new parent, sibling index, and coordinates so undo puts the
    widget back exactly where it was.
    """

    def __init__(
        self,
        widget_id: str,
        old_parent_id: str | None,
        old_index: int,
        old_x: int,
        old_y: int,
        new_parent_id: str | None,
        new_index: int,
        new_x: int,
        new_y: int,
    ):
        self.widget_id = widget_id
        self.old_parent_id = old_parent_id
        self.old_index = old_index
        self.old_x = old_x
        self.old_y = old_y
        self.new_parent_id = new_parent_id
        self.new_index = new_index
        self.new_x = new_x
        self.new_y = new_y
        self.description = "Reparent widget"

    def _move(
        self,
        project: "Project",
        parent_id: str | None,
        index: int,
        x: int,
        y: int,
    ) -> None:
        node = project.get_widget(self.widget_id)
        if node is None:
            return
        # Write coords before reparent so the destroy+recreate that
        # reparent triggers picks up the restored x/y.
        node.properties["x"] = x
        node.properties["y"] = y
        project.reparent(self.widget_id, parent_id, index=index)
        project.select_widget(self.widget_id)

    def undo(self, project: "Project") -> None:
        self._move(
            project, self.old_parent_id, self.old_index,
            self.old_x, self.old_y,
        )

    def redo(self, project: "Project") -> None:
        self._move(
            project, self.new_parent_id, self.new_index,
            self.new_x, self.new_y,
        )


class RenameCommand(Command):
    def __init__(
        self,
        widget_id: str,
        before: str,
        after: str,
        coalesce_key: str | None = None,
    ):
        self.widget_id = widget_id
        self.before = before
        self.after = after
        self.coalesce_key = coalesce_key
        self.timestamp = time.monotonic()
        self.description = f"Rename to '{after}'"

    def undo(self, project: "Project") -> None:
        project.rename_widget(self.widget_id, self.before)

    def redo(self, project: "Project") -> None:
        project.rename_widget(self.widget_id, self.after)

    def merge_into(self, other: "Command") -> bool:
        if self.coalesce_key is None:
            return False
        if not isinstance(other, RenameCommand):
            return False
        if other.coalesce_key != self.coalesce_key:
            return False
        if other.widget_id != self.widget_id:
            return False
        if self.timestamp - other.timestamp > COALESCE_WINDOW_SEC:
            return False
        other.after = self.after
        other.timestamp = self.timestamp
        other.description = f"Rename to '{self.after}'"
        return True


class BulkAddCommand(Command):
    """Paste / duplicate — restores multiple widget subtrees from
    snapshots. Each entry carries its own (snapshot, parent_id, index)
    so z-order survives undo + redo round trips.
    """

    def __init__(
        self,
        entries: list[tuple[dict, str | None, int]],
        label: str = "Paste",
    ):
        self._entries = entries
        self.description = (
            f"{label} {len(entries)} widgets" if len(entries) > 1
            else label
        )

    def undo(self, project: "Project") -> None:
        for snapshot, _parent_id, _index in self._entries:
            project.remove_widget(snapshot["id"])

    def redo(self, project: "Project") -> None:
        restored_ids: list[str] = []
        for snapshot, parent_id, index in self._entries:
            node = WidgetNode.from_dict(snapshot)
            project.add_widget(node, parent_id=parent_id)
            project.reparent(node.id, parent_id, index=index)
            restored_ids.append(node.id)
        if len(restored_ids) == 1:
            project.select_widget(restored_ids[0])
        elif restored_ids:
            project.set_multi_selection(
                set(restored_ids), primary=restored_ids[0],
            )


class ZOrderCommand(Command):
    """Bring-to-Front / Send-to-Back reorder within a parent's
    children list. Captured as old / new sibling indices so undo is
    a single reparent call with the restored index.
    """

    def __init__(
        self,
        widget_id: str,
        parent_id: str | None,
        old_index: int,
        new_index: int,
        direction: str,
    ):
        self.widget_id = widget_id
        self.parent_id = parent_id
        self.old_index = old_index
        self.new_index = new_index
        self.description = {
            "front": "Bring to Front",
            "back": "Send to Back",
        }.get(direction, "Reorder")

    def undo(self, project: "Project") -> None:
        project.reorder_child_at(self.widget_id, self.old_index)
        project.select_widget(self.widget_id)

    def redo(self, project: "Project") -> None:
        project.reorder_child_at(self.widget_id, self.new_index)
        project.select_widget(self.widget_id)


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
    """

    def __init__(self, snapshot: dict, index: int):
        self._snapshot = snapshot
        self._index = index
        self.description = f"Delete {snapshot.get('name', 'document')}"

    def undo(self, project: "Project") -> None:
        _restore_document(project, self._snapshot, self._index)

    def redo(self, project: "Project") -> None:
        _remove_document_by_id(project, self._snapshot["id"])


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
        project.event_bus.publish(
            "active_document_changed", project.active_document_id,
        )

    def undo(self, project: "Project") -> None:
        self._apply(project, self.before)

    def redo(self, project: "Project") -> None:
        self._apply(project, self.after)


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
    for node in list(doc.root_widgets):
        project.remove_widget(node.id)
    if doc in project.documents:
        project.documents.remove(doc)
    if project.active_document_id == doc_id and project.documents:
        project.active_document_id = project.documents[0].id
    project.event_bus.publish(
        "active_document_changed", project.active_document_id,
    )


class ToggleFlagCommand(Command):
    """Visibility or lock toggle — both flags live on WidgetNode
    outside the normal ``properties`` dict, so they need their own
    setter routing rather than ChangePropertyCommand.
    """

    def __init__(
        self,
        widget_id: str,
        flag: str,
        before: bool,
        after: bool,
    ):
        self.widget_id = widget_id
        self.flag = flag
        self.before = before
        self.after = after
        self.description = {
            "visible": (
                "Hide widget" if not after else "Show widget"
            ),
            "locked": (
                "Lock widget" if after else "Unlock widget"
            ),
        }.get(flag, f"Toggle {flag}")

    def _apply(self, project: "Project", value: bool) -> None:
        if self.flag == "visible":
            project.set_visibility(self.widget_id, value)
        elif self.flag == "locked":
            project.set_locked(self.widget_id, value)

    def undo(self, project: "Project") -> None:
        self._apply(project, self.before)

    def redo(self, project: "Project") -> None:
        self._apply(project, self.after)
