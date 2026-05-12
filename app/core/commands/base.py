"""Command base class + shared helpers used by every command file.

The ``Command`` base defines the undo / redo / merge_into contract.
Helpers (``paste_target_parent_id``, ``build_bulk_add_entries``,
``_restore_widget``, ``_add_subtree_recursive``) live here so each
sibling sub-module imports them from one place.
"""

from __future__ import annotations

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
        if not isinstance(node, WidgetNode):
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
