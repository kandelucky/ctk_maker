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
) -> list[tuple[dict, str | None, int, str | None, tuple | None]]:
    """Snapshot a batch of already-added widgets into the 5-tuple
    shape ``BulkAddCommand`` expects. Used by every paste / duplicate
    path across the UI — the call site passes the fresh ids just
    returned by ``paste_from_clipboard`` / ``duplicate_widget``, and
    this helper walks each one to capture its parent, sibling index,
    owning document, and any grid auto-grow side-effect so undo/redo
    restore both the widget AND the parent's grid dims.

    Entries for ids that don't resolve (a deleted widget mid-flight)
    are skipped rather than raising, matching the old per-site loops.
    """
    entries: list[tuple[dict, str | None, int, str | None, tuple | None]] = []
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
        # Harvest the auto-grow stash left by _auto_assign_grid_cell so
        # undo can revert the parent's grid_rows / grid_cols. Clear the
        # attribute so re-reading doesn't double-count.
        dim_changes = getattr(node, "_pending_parent_dim_changes", None)
        if hasattr(node, "_pending_parent_dim_changes"):
            try:
                delattr(node, "_pending_parent_dim_changes")
            except AttributeError:
                pass
        entries.append(
            (node.to_dict(), parent_id, index, document_id, dim_changes),
        )
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
    through here so the contract stays one line wide. Walks the
    snapshot subtree and adds each node individually so the
    ``widget_added`` event fires per node — without that, only the
    root's view gets created and a Frame's children never re-render
    on undo.
    """
    node = WidgetNode.from_dict(snapshot)
    _add_subtree_recursive(project, node, parent_id, document_id)
    if index is not None:
        project.reparent(node.id, parent_id, index=index)
    return node


def _add_subtree_recursive(
    project: "Project",
    node: WidgetNode,
    parent_id: str | None,
    document_id: str | None = None,
) -> None:
    """Detach children + add root + recurse — mirrors paste's
    ``_paste_recursive`` so every node gets its own ``widget_added``
    event and the workspace can build a tk widget for it. Without
    this, restoring a Frame from a Delete snapshot left every
    descendant invisible (in the model but never rendered)."""
    children_copy = list(node.children)
    node.children = []
    node.parent = None
    project.add_widget(node, parent_id=parent_id, document_id=document_id)
    for child in children_copy:
        child.parent = None
        _add_subtree_recursive(project, child, parent_id=node.id)


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
                    pass

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


class ChangeDescriptionCommand(Command):
    """Change a widget's ``description`` meta-property. Stored on the
    node directly (not in ``properties``) so it never leaks into the
    CTk constructor — only into the export-time comment pass.

    For Window selections (``widget_id == WINDOW_ID``) the description
    actually lives on the ``Document`` — captured by ``document_id``
    at command time so undo/redo target the right document even after
    the user switches the active form.
    """

    def __init__(
        self,
        widget_id: str,
        before: str,
        after: str,
        document_id: str | None = None,
    ):
        self.widget_id = widget_id
        self.document_id = document_id
        self.before = before
        self.after = after
        self.description = "Edit description"

    def _apply(self, project: "Project", value: str) -> None:
        from app.core.project import WINDOW_ID
        if self.widget_id == WINDOW_ID and self.document_id is not None:
            doc = next(
                (d for d in project.documents if d.id == self.document_id),
                None,
            )
            if doc is not None:
                project.set_active_document(doc.id)
                doc.description = value
        else:
            node = project.get_widget(self.widget_id)
            if node is not None:
                node.description = value
        project.event_bus.publish(
            "widget_description_changed", self.widget_id, value,
        )
        project.select_widget(self.widget_id)

    def undo(self, project: "Project") -> None:
        self._apply(project, self.before)

    def redo(self, project: "Project") -> None:
        self._apply(project, self.after)


class BindHandlerCommand(Command):
    """Phase 2 visual scripting — attach an event handler binding to
    a widget. ``event_key`` is the storage key (``"command"`` or
    ``"bind:<seq>"``); ``method_name`` is the method on the page's
    behavior class that the runtime / exporter will resolve. The
    actual ``.py`` file mutation happens at the call site (the
    command only carries undo/redo for the model field).
    """

    def __init__(
        self, widget_id: str, event_key: str, method_name: str,
    ):
        self.widget_id = widget_id
        self.event_key = event_key
        self.method_name = method_name
        self.description = "Bind handler"

    def _apply(self, project: "Project", method_name: str | None) -> None:
        node = project.get_widget(self.widget_id)
        if node is None:
            return
        if method_name:
            node.handlers[self.event_key] = method_name
        else:
            node.handlers.pop(self.event_key, None)
        project.event_bus.publish(
            "widget_handler_changed",
            self.widget_id, self.event_key, method_name or "",
        )
        project.select_widget(self.widget_id)

    def undo(self, project: "Project") -> None:
        self._apply(project, None)

    def redo(self, project: "Project") -> None:
        self._apply(project, self.method_name)


class UnbindHandlerCommand(Command):
    """Reverse of ``BindHandlerCommand`` — clear an event binding
    from a widget. Captures the previous method name at construction
    so undo can restore it. Doesn't touch the ``.py`` file: the user
    owns the script, we only manage the binding pointer.
    """

    def __init__(
        self, widget_id: str, event_key: str, previous_method: str,
    ):
        self.widget_id = widget_id
        self.event_key = event_key
        self.previous_method = previous_method
        self.description = "Unbind handler"

    def _apply(self, project: "Project", method_name: str | None) -> None:
        node = project.get_widget(self.widget_id)
        if node is None:
            return
        if method_name:
            node.handlers[self.event_key] = method_name
        else:
            node.handlers.pop(self.event_key, None)
        project.event_bus.publish(
            "widget_handler_changed",
            self.widget_id, self.event_key, method_name or "",
        )
        project.select_widget(self.widget_id)

    def undo(self, project: "Project") -> None:
        self._apply(project, self.previous_method)

    def redo(self, project: "Project") -> None:
        self._apply(project, None)


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
        parent_dim_changes: tuple[str, dict] | None = None,
    ):
        # changes: {prop_name: (before, after)}
        self.widget_id = widget_id
        self.changes = dict(changes)
        # (container_id, {prop_name: (before, after)}) — grid auto-grow
        # side-effect on same-parent grid drops. Same pattern as
        # AddWidgetCommand / ReparentCommand.
        self._parent_dim_changes = parent_dim_changes
        self.description = f"Change {len(changes)} properties"

    def undo(self, project: "Project") -> None:
        for name, (before, _after) in self.changes.items():
            project.update_property(self.widget_id, name, before)
        if self._parent_dim_changes is not None:
            parent_id, changes = self._parent_dim_changes
            for key, (before, _after) in changes.items():
                try:
                    project.update_property(parent_id, key, before)
                except Exception:
                    pass
        project.select_widget(self.widget_id)

    def redo(self, project: "Project") -> None:
        if self._parent_dim_changes is not None:
            parent_id, changes = self._parent_dim_changes
            for key, (_before, after) in changes.items():
                try:
                    project.update_property(parent_id, key, after)
                except Exception:
                    pass
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
        if node is None:
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
                    pass

    def redo(self, project: "Project") -> None:
        if self._parent_dim_changes is not None:
            parent_id, changes = self._parent_dim_changes
            for key, (_before, after) in changes.items():
                try:
                    project.update_property(parent_id, key, after)
                except Exception:
                    pass
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
                        pass

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
                        pass
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


class BulkToggleFlagCommand(Command):
    """Batch visibility / lock toggle for a set of widgets — used by
    Object Tree's virtual Group row so toggling the group is one undo
    step rather than N. Each entry remembers its own before-state so
    undo restores the exact mix even if some members were already ON.
    """

    def __init__(
        self,
        flag: str,
        entries: list[tuple[str, bool, bool]],
        label: str | None = None,
    ):
        self.flag = flag
        self._entries = list(entries)
        if label is None:
            verb = {
                ("visible", True): "Show",
                ("visible", False): "Hide",
                ("locked", True): "Lock",
                ("locked", False): "Unlock",
            }
            after_state = entries[0][2] if entries else True
            label = verb.get(
                (flag, after_state), f"Toggle {flag}",
            )
        self.description = f"{label} group ({len(entries)})"

    def _apply_one(
        self, project: "Project", widget_id: str, value: bool,
    ) -> None:
        if self.flag == "visible":
            project.set_visibility(widget_id, value)
        elif self.flag == "locked":
            project.set_locked(widget_id, value)

    def undo(self, project: "Project") -> None:
        for widget_id, before, _after in self._entries:
            self._apply_one(project, widget_id, before)

    def redo(self, project: "Project") -> None:
        for widget_id, _before, after in self._entries:
            self._apply_one(project, widget_id, after)


class SetGroupCommand(Command):
    """Group / ungroup tag mutation — records before/after group_id
    per widget so undo restores prior group memberships exactly,
    even for widgets that were already in a (possibly different)
    group before the change.
    """

    def __init__(
        self,
        before: dict,
        after: dict,
        description: str = "Group widgets",
    ):
        self.before = dict(before)
        self.after = dict(after)
        self.description = description

    def _apply(self, project: "Project", values: dict) -> None:
        for widget_id, group_id in values.items():
            project.set_group_id(widget_id, group_id)

    def undo(self, project: "Project") -> None:
        self._apply(project, self.before)

    def redo(self, project: "Project") -> None:
        self._apply(project, self.after)


# ======================================================================
# Variables (Phase 1 visual scripting)
# ======================================================================
def _variable_target_list(
    project: "Project", scope: str, document_id: str | None,
) -> list:
    """Pick the right backing list for a variable command's scope.

    Locals follow ``document_id`` first; if the document is gone (e.g.
    deleted between redo and undo), the entry is dropped — we'd rather
    silently lose a stale undo entry than insert the variable into the
    wrong document.
    """
    if scope == "local":
        if document_id is None:
            return []
        doc = project.get_document(document_id)
        if doc is None:
            return []
        return doc.local_variables
    return project.variables


class AddVariableCommand(Command):
    """Append a new variable to the project. Stores the entry's
    serialised form so undo / redo can recreate it with the same UUID
    + name + type + default — bindings written in the same session
    keep resolving across undo/redo. ``scope`` + ``document_id`` route
    the entry to the right list; locals require a document_id.
    """

    def __init__(
        self, entry_dict: dict, index: int,
        scope: str = "global", document_id: str | None = None,
    ):
        self.entry_dict = dict(entry_dict)
        self.index = index
        self.scope = scope
        self.document_id = document_id
        self.description = f"Add variable: {entry_dict.get('name', '')}"

    def undo(self, project: "Project") -> None:
        var_id = self.entry_dict.get("id")
        if var_id:
            project.remove_variable(var_id)

    def redo(self, project: "Project") -> None:
        from app.core.variables import VariableEntry
        entry = VariableEntry.from_dict(self.entry_dict)
        target = _variable_target_list(
            project, self.scope, self.document_id,
        )
        # Insert at the recorded index so position survives undo/redo.
        if 0 <= self.index <= len(target):
            target.insert(self.index, entry)
        else:
            target.append(entry)
        project.event_bus.publish("variable_added", entry)


class DeleteVariableCommand(Command):
    """Remove a variable + cascade-unbind every property that
    references it. Captures the per-binding snapshot so undo can
    re-bind every widget that was using the variable before delete.
    Scope + document_id route the restored entry back to the right
    list on undo.
    """

    def __init__(
        self, entry_dict: dict, index: int,
        bindings: list[tuple[str, str, str]],
        scope: str = "global", document_id: str | None = None,
    ):
        # ``bindings`` items: (widget_id, prop_name, previous_value).
        # ``previous_value`` is the var token at delete time so undo
        # rewrites the same string back into the property.
        self.entry_dict = dict(entry_dict)
        self.index = index
        self.bindings = list(bindings)
        self.scope = scope
        self.document_id = document_id
        self.description = (
            f"Delete variable: {entry_dict.get('name', '')}"
        )

    def undo(self, project: "Project") -> None:
        from app.core.variables import VariableEntry
        entry = VariableEntry.from_dict(self.entry_dict)
        target = _variable_target_list(
            project, self.scope, self.document_id,
        )
        if 0 <= self.index <= len(target):
            target.insert(self.index, entry)
        else:
            target.append(entry)
        project.event_bus.publish("variable_added", entry)
        # Restore every binding that was cleared on delete.
        for widget_id, pname, prev_value in self.bindings:
            project.update_property(widget_id, pname, prev_value)

    def redo(self, project: "Project") -> None:
        var_id = self.entry_dict.get("id")
        if var_id:
            project.remove_variable(var_id)


class RenameVariableCommand(Command):
    def __init__(self, var_id: str, before: str, after: str):
        self.var_id = var_id
        self.before = before
        self.after = after
        self.description = f"Rename variable: {before} → {after}"

    def undo(self, project: "Project") -> None:
        project.rename_variable(self.var_id, self.before)

    def redo(self, project: "Project") -> None:
        project.rename_variable(self.var_id, self.after)


class ChangeVariableTypeCommand(Command):
    """Type change cascades into the default (the project coerces
    the old default into the new type) so undo must restore both.
    """

    def __init__(
        self, var_id: str,
        before_type: str, after_type: str,
        before_default: str, after_default: str,
    ):
        self.var_id = var_id
        self.before_type = before_type
        self.after_type = after_type
        self.before_default = before_default
        self.after_default = after_default
        self.description = (
            f"Change variable type: {before_type} → {after_type}"
        )

    def undo(self, project: "Project") -> None:
        project.change_variable_type(self.var_id, self.before_type)
        project.change_variable_default(self.var_id, self.before_default)

    def redo(self, project: "Project") -> None:
        project.change_variable_type(self.var_id, self.after_type)
        project.change_variable_default(self.var_id, self.after_default)


class ChangeVariableDefaultCommand(Command):
    def __init__(self, var_id: str, before: str, after: str):
        self.var_id = var_id
        self.before = before
        self.after = after
        self.description = "Change variable default"

    def undo(self, project: "Project") -> None:
        project.change_variable_default(self.var_id, self.before)

    def redo(self, project: "Project") -> None:
        project.change_variable_default(self.var_id, self.after)
