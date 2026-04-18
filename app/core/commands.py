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


def paste_target_parent_id(
    project: "Project", widget_id: str | None,
) -> str | None:
    """Where should a paste land given ``widget_id`` as the anchor?

    - widget is a container → inside it
    - widget is a leaf      → as its sibling (same parent)
    - widget is None or missing → top level

    The three UI call sites (Edit menu paste, tree Ctrl+V, canvas
    right-click paste) were open-coding this three times — with the
    usual drift risk when a new widget kind shows up. Funnel through
    here so container semantics stay in one place.
    """
    if widget_id is None:
        return None
    from app.widgets.registry import get_descriptor
    node = project.get_widget(widget_id)
    if node is None:
        return None
    descriptor = get_descriptor(node.widget_type)
    if descriptor is not None and getattr(
        descriptor, "is_container", False,
    ):
        return widget_id
    return node.parent.id if node.parent is not None else None


def push_zorder_history(
    project: "Project", widget_id: str, direction: str,
) -> None:
    """Apply a z-order move (bring to front / send to back) AND push
    a ``ZOrderCommand`` to history in one shot.

    Shared by every UI entry point (Edit menu, canvas right-click,
    Object Tree right-click). Each had been capturing old_index /
    calling the project helper / capturing new_index / pushing the
    command in ~20 duplicated lines. One call site = one source of
    truth; a new direction (e.g. "one step up") only needs Project
    + a new branch here.
    """
    node = project.get_widget(widget_id)
    if node is None:
        return
    siblings = (
        node.parent.children if node.parent is not None
        else project.root_widgets
    )
    try:
        old_index = siblings.index(node)
    except ValueError:
        return
    if direction == "front":
        project.bring_to_front(widget_id)
    elif direction == "back":
        project.send_to_back(widget_id)
    else:
        return
    try:
        new_index = siblings.index(node)
    except ValueError:
        return
    if old_index == new_index:
        return
    parent_id = node.parent.id if node.parent is not None else None
    project.history.push(
        ZOrderCommand(widget_id, parent_id, old_index, new_index, direction),
    )


def build_bulk_add_entries(
    project: "Project", widget_ids,
) -> list[tuple[dict, str | None, int, str | None]]:
    """Snapshot a batch of already-added widgets into the 4-tuple
    shape ``BulkAddCommand`` expects. Used by every paste / duplicate
    path across the UI — the call site passes the fresh ids just
    returned by ``paste_from_clipboard`` / ``duplicate_widget``, and
    this helper walks each one to capture its parent, sibling index,
    and owning document so undo/redo can restore it in place.

    Entries for ids that don't resolve (a deleted widget mid-flight)
    are skipped rather than raising, matching the old per-site loops.
    """
    entries: list[tuple[dict, str | None, int, str | None]] = []
    for nid in widget_ids:
        node = project.get_widget(nid)
        if node is None:
            continue
        parent_id = node.parent.id if node.parent is not None else None
        siblings = (
            node.parent.children if node.parent is not None
            else project.root_widgets
        )
        try:
            index = siblings.index(node)
        except ValueError:
            index = len(siblings) - 1
        owning_doc = project.find_document_for_widget(nid)
        document_id = owning_doc.id if owning_doc is not None else None
        entries.append((node.to_dict(), parent_id, index, document_id))
    return entries


def _restore_widget(
    project: "Project",
    snapshot: dict,
    parent_id: str | None,
    index: int | None,
    document_id: str | None,
) -> WidgetNode:
    """Shared body for every command that recreates a widget from a
    snapshot (Add.redo, Delete.undo, DeleteMultiple.undo, BulkAdd.redo).

    Resolving the doc + re-inserting at the original index used to be
    open-coded in four places; any drift (a missing ``document_id``
    pass-through, for instance) breaks cross-document undo. Funnel
    through here so the contract stays one line wide.
    """
    node = WidgetNode.from_dict(snapshot)
    project.add_widget(node, parent_id=parent_id, document_id=document_id)
    if index is not None:
        project.reparent(node.id, parent_id, index=index)
    return node


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
        document_id: str | None = None,
    ):
        self._snapshot = snapshot
        self._parent_id = parent_id
        self._index = index
        self._document_id = document_id
        self.description = f"Add {snapshot.get('widget_type', 'widget')}"

    def undo(self, project: "Project") -> None:
        project.remove_widget(self._snapshot["id"])

    def redo(self, project: "Project") -> None:
        node = _restore_widget(
            project, self._snapshot, self._parent_id,
            self._index, self._document_id,
        )
        project.select_widget(node.id)


class DeleteWidgetCommand(Command):
    def __init__(
        self,
        snapshot: dict,
        parent_id: str | None,
        index: int,
        document_id: str | None = None,
    ):
        self._snapshot = snapshot
        self._parent_id = parent_id
        self._index = index
        self._document_id = document_id
        label = snapshot.get("name") or snapshot.get("widget_type", "widget")
        self.description = f"Delete {label}"

    def undo(self, project: "Project") -> None:
        node = _restore_widget(
            project, self._snapshot, self._parent_id,
            self._index, self._document_id,
        )
        project.select_widget(node.id)

    def redo(self, project: "Project") -> None:
        project.remove_widget(self._snapshot["id"])


class DeleteMultipleCommand(Command):
    """Multi-delete bundled into one undo step. Snapshots are stored
    top-down in pre-deletion tree order; undo replays them in the
    same order so each sibling lands back at its original index.

    Each entry also carries the owning document id so cross-document
    deletes restore each widget into the doc it came from — without
    it, every top-level widget would pile back into whichever doc
    happened to be active at undo time.
    """

    def __init__(
        self,
        entries: list[tuple[dict, str | None, int, str | None]],
    ):
        self._entries = entries
        self.description = f"Delete {len(entries)} widgets"

    def undo(self, project: "Project") -> None:
        restored_ids: list[str] = []
        for snapshot, parent_id, index, document_id in self._entries:
            node = _restore_widget(
                project, snapshot, parent_id, index, document_id,
            )
            restored_ids.append(node.id)
        if restored_ids:
            project.set_multi_selection(
                set(restored_ids), primary=restored_ids[0],
            )

    def redo(self, project: "Project") -> None:
        for snapshot, _parent_id, _index, _doc_id in self._entries:
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
    new parent, sibling index, coordinates, AND owning document so
    undo puts the widget back exactly where it was — including cross-
    document moves, where the target doc isn't the active one.
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
        old_document_id: str | None = None,
        new_document_id: str | None = None,
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
        self.old_document_id = old_document_id
        self.new_document_id = new_document_id
        self.description = "Reparent widget"

    def _move(
        self,
        project: "Project",
        parent_id: str | None,
        index: int,
        x: int,
        y: int,
        document_id: str | None,
    ) -> None:
        node = project.get_widget(self.widget_id)
        if node is None:
            return
        # Write coords before reparent so the destroy+recreate that
        # reparent triggers picks up the restored x/y.
        node.properties["x"] = x
        node.properties["y"] = y
        # Same-parent + same-doc moves are sibling reorders. The
        # captured ``index`` is post-move (final slot), which doesn't
        # match ``project.reparent``'s pre-pop semantics — running
        # through ``reparent`` here applies the compensate arithmetic
        # and the redo lands at the wrong position. ``reorder_child_at``
        # uses final-index semantics, so route sibling reorders there.
        current_parent_id = (
            node.parent.id if node.parent is not None else None
        )
        same_parent = current_parent_id == parent_id
        if same_parent:
            if parent_id is not None:
                # Nested reorder — parent pins the doc, can't cross.
                project.reorder_child_at(self.widget_id, index)
                project.select_widget(self.widget_id)
                return
            # Top-level: only a reorder when the doc didn't change too.
            current_doc = project.find_document_for_widget(self.widget_id)
            current_doc_id = current_doc.id if current_doc else None
            if document_id in (None, current_doc_id):
                project.reorder_child_at(self.widget_id, index)
                project.select_widget(self.widget_id)
                return
        project.reparent(
            self.widget_id, parent_id,
            index=index, document_id=document_id,
        )
        project.select_widget(self.widget_id)

    def undo(self, project: "Project") -> None:
        self._move(
            project, self.old_parent_id, self.old_index,
            self.old_x, self.old_y, self.old_document_id,
        )

    def redo(self, project: "Project") -> None:
        self._move(
            project, self.new_parent_id, self.new_index,
            self.new_x, self.new_y, self.new_document_id,
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
    snapshots. Each entry carries its own
    ``(snapshot, parent_id, index, document_id)`` so z-order and the
    owning document both survive undo + redo round trips. ``document_id``
    only matters for top-level entries (``parent_id`` is None); nested
    entries inherit their doc from the parent that already exists.
    """

    def __init__(
        self,
        entries: list[tuple[dict, str | None, int, str | None]],
        label: str = "Paste",
    ):
        self._entries = entries
        self.description = (
            f"{label} {len(entries)} widgets" if len(entries) > 1
            else label
        )

    def undo(self, project: "Project") -> None:
        for snapshot, _parent_id, _index, _doc_id in self._entries:
            project.remove_widget(snapshot["id"])

    def redo(self, project: "Project") -> None:
        restored_ids: list[str] = []
        for snapshot, parent_id, index, document_id in self._entries:
            node = _restore_widget(
                project, snapshot, parent_id, index, document_id,
            )
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
