"""Commands that mutate the widget tree — add / delete / move /
resize / reparent / rename / z-order.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.core.commands.base import (
    COALESCE_WINDOW_SEC,
    Command,
    _add_subtree_recursive,
    _restore_widget,
)
from app.core.logger import log_error
from app.core.widget_node import WidgetNode

if TYPE_CHECKING:
    from app.core.project import Project


class AddWidgetCommand(Command):
    def __init__(
        self,
        snapshot: dict,
        parent_id: str | None,
        index: int | None = None,
        document_id: str | None = None,
        parent_dim_changes: tuple[str, dict] | None = None,
    ):
        self._snapshot = snapshot
        self._parent_id = parent_id
        self._index = index
        self._document_id = document_id
        # (parent_id, {prop_name: (before, after)}) — set when the add
        # triggered an auto-grow of the target grid container. Undo
        # restores the before values; redo relies on the widget_added
        # event handler to regrow the grid naturally.
        self._parent_dim_changes = parent_dim_changes
        self.description = f"Add {snapshot.get('widget_type', 'widget')}"

    def undo(self, project: "Project") -> None:
        project.remove_widget(self._snapshot["id"])
        if self._parent_dim_changes is not None:
            parent_id, changes = self._parent_dim_changes
            for key, (before, _after) in changes.items():
                try:
                    project.update_property(parent_id, key, before)
                except Exception:
                    log_error("AddWidgetCommand.undo: parent grid-dim revert")

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

    ``coalesce_key`` lets repeated arrow-nudge volleys covering the
    same selection collapse into one undo entry — without it, every
    keystroke would push its own bulk command onto the stack.
    """

    def __init__(self, moves: list, coalesce_key: str | None = None):
        self.moves = list(moves)
        self.coalesce_key = coalesce_key
        self.timestamp = time.monotonic()
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

    def merge_into(self, other: "Command") -> bool:
        if self.coalesce_key is None:
            return False
        if not isinstance(other, BulkMoveCommand):
            return False
        if other.coalesce_key != self.coalesce_key:
            return False
        if self.timestamp - other.timestamp > COALESCE_WINDOW_SEC:
            return False
        # Tail's selection set must match ours exactly — if the user
        # changed the selection between volleys, we want a fresh undo
        # entry, not a silently-extended one.
        other_ids = {wid for wid, _b, _a in other.moves}
        self_ids = {wid for wid, _b, _a in self.moves}
        if other_ids != self_ids:
            return False
        # Extend tail: keep its 'before', adopt our 'after'.
        before_by_id = {wid: before for wid, before, _a in other.moves}
        merged: list = []
        for wid, _before, after in self.moves:
            merged.append((wid, before_by_id[wid], after))
        other.moves = merged
        other.timestamp = self.timestamp
        return True


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
        parent_dim_changes: tuple[str, dict] | None = None,
        old_parent_slot: str | None = None,
        new_parent_slot: str | None = None,
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
        # (container_id, {prop_name: (before, after)}) — set when the
        # drop triggered an auto-grow of the target grid container.
        # undo reverts the dims after moving the widget back; redo
        # re-applies them so the grid grows in step with the reparent.
        self._parent_dim_changes = parent_dim_changes
        # parent_slot is the tab name when reparenting into a Tabview —
        # captured so undo / redo restore the correct tab assignment.
        self.old_parent_slot = old_parent_slot
        self.new_parent_slot = new_parent_slot
        self.description = "Reparent widget"

    def _move(
        self,
        project: "Project",
        parent_id: str | None,
        index: int,
        x: int,
        y: int,
        document_id: str | None,
        parent_slot: str | None = None,
    ) -> None:
        node = project.get_widget(self.widget_id)
        if not isinstance(node, WidgetNode):
            return
        # Write coords + parent_slot before reparent so the destroy+
        # recreate that reparent triggers picks up the restored state.
        node.properties["x"] = x
        node.properties["y"] = y
        node.parent_slot = parent_slot
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
            parent_slot=self.old_parent_slot,
        )
        if self._parent_dim_changes is not None:
            parent_id, changes = self._parent_dim_changes
            for key, (before, _after) in changes.items():
                try:
                    project.update_property(parent_id, key, before)
                except Exception:
                    log_error("ReparentCommand.undo: parent grid-dim revert")

    def redo(self, project: "Project") -> None:
        if self._parent_dim_changes is not None:
            parent_id, changes = self._parent_dim_changes
            for key, (_before, after) in changes.items():
                try:
                    project.update_property(parent_id, key, after)
                except Exception:
                    log_error("ReparentCommand.redo: parent grid-dim apply")
        self._move(
            project, self.new_parent_id, self.new_index,
            self.new_x, self.new_y, self.new_document_id,
            parent_slot=self.new_parent_slot,
        )


class BulkReparentCommand(Command):
    """Wrap N ``ReparentCommand`` instances so a cross-doc group drag
    collapses into a single undo step. Undo walks the entries in
    reverse (each one undoes independently); redo walks them forward.
    Every member's full old / new snapshot is preserved so the group
    returns to its source document with all widgets intact.
    """

    def __init__(self, commands: list):
        self.commands = list(commands)
        n = len(self.commands)
        self.description = (
            f"Reparent {n} widgets" if n != 1 else "Reparent widget"
        )

    def undo(self, project: "Project") -> None:
        for cmd in reversed(self.commands):
            cmd.undo(project)

    def redo(self, project: "Project") -> None:
        for cmd in self.commands:
            cmd.redo(project)


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
    ``(snapshot, parent_id, index, document_id, parent_dim_changes)``
    so z-order, owning document, AND grid auto-grow side-effects all
    survive undo + redo. ``document_id`` only matters for top-level
    entries (``parent_id`` is None); nested entries inherit their doc
    from the parent that already exists. ``parent_dim_changes`` is
    ``(container_id, {prop: (before, after)})`` when the add grew the
    target grid, else None.
    """

    def __init__(
        self,
        entries: list,
        label: str = "Paste",
    ):
        # Back-compat: accept legacy 4-tuples by padding with None.
        normalised = []
        for entry in entries:
            if len(entry) == 4:
                entry = (*entry, None)
            normalised.append(entry)
        self._entries = normalised
        self.description = (
            f"{label} {len(normalised)} widgets" if len(normalised) > 1
            else label
        )

    def undo(self, project: "Project") -> None:
        # Reverse order so grid-dim reverts unwind in the opposite
        # order they were applied — otherwise two duplicates into the
        # same grid would restore dims out of sequence.
        for snapshot, _parent_id, _index, _doc_id, dim_changes in (
            reversed(self._entries)
        ):
            project.remove_widget(snapshot["id"])
            if dim_changes is not None:
                container_id, changes = dim_changes
                for key, (before, _after) in changes.items():
                    try:
                        project.update_property(container_id, key, before)
                    except Exception:
                        log_error("BulkAddCommand.undo: container grid-dim revert")

    def redo(self, project: "Project") -> None:
        restored_ids: list[str] = []
        for snapshot, parent_id, index, document_id, dim_changes in (
            self._entries
        ):
            if dim_changes is not None:
                container_id, changes = dim_changes
                for key, (_before, after) in changes.items():
                    try:
                        project.update_property(container_id, key, after)
                    except Exception:
                        log_error("BulkAddCommand.redo: container grid-dim apply")
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
    if not isinstance(node, WidgetNode):
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
