"""Project model — the source of truth for widgets, tree structure,
document settings, and selection state.

Phase 6.1: WidgetNodes form a parent/child tree. Top-level widgets
live in `root_widgets`; children live under their parent's
`children` list and carry a back-reference via `parent`.

Tree operations:
    add_widget(node, parent_id=None)
    remove_widget(widget_id)            — also removes its subtree
    reparent(widget_id, new_parent_id)  — move between parents
    get_widget(widget_id)               — DFS lookup
    iter_all_widgets()                  — DFS (top-down) generator

Sibling operations (work within the current parent):
    duplicate_widget, bring_to_front, send_to_back

Events published on event_bus:
    widget_added(node)                  — any add (root or child)
    widget_removed(widget_id)           — any remove
    widget_reparented(widget_id, old_parent_id, new_parent_id)
    widget_z_changed(widget_id, direction)
    property_changed(widget_id, prop_name, value)
    selection_changed(widget_id | None)
    document_resized(width, height)
"""

from __future__ import annotations

from typing import Iterator

from app.core.event_bus import EventBus
from app.core.widget_node import WidgetNode

DEFAULT_DOCUMENT_WIDTH = 800
DEFAULT_DOCUMENT_HEIGHT = 600


class Project:
    def __init__(self):
        self.event_bus = EventBus()
        self.root_widgets: list[WidgetNode] = []
        # `selected_id` is the "primary" / most-recently-clicked
        # selected widget (what handles resize / property editing).
        # `selected_ids` is the full set — only relevant while the
        # Object Tree has a multi-selection active. Workspace and
        # properties panel stay single-select-aware; they see a
        # `selection_changed(None)` event when multi is active.
        self.selected_id: str | None = None
        self.selected_ids: set[str] = set()
        self.document_width: int = DEFAULT_DOCUMENT_WIDTH
        self.document_height: int = DEFAULT_DOCUMENT_HEIGHT
        self.name: str = "Untitled"
        # Monotonic per-widget-type counter used to auto-name new widgets
        # ("Button", "Button (1)", "Button (2)", …). Persisted with the
        # project so numbers never get reused across reloads.
        self._name_counters: dict[str, int] = {}
        # In-memory clipboard for Ctrl+C / Ctrl+V. Each entry is a
        # full WidgetNode.to_dict() snapshot of a copied subtree.
        # Not persisted — lost when the app quits.
        self.clipboard: list[dict] = []

    # ------------------------------------------------------------------
    # Document
    # ------------------------------------------------------------------
    def resize_document(self, width: int, height: int) -> None:
        width = max(100, int(width))
        height = max(100, int(height))
        if width == self.document_width and height == self.document_height:
            return
        self.document_width = width
        self.document_height = height
        self.event_bus.publish("document_resized", width, height)

    # ------------------------------------------------------------------
    # Tree traversal
    # ------------------------------------------------------------------
    def iter_all_widgets(self) -> Iterator[WidgetNode]:
        """Yield every widget in the project, depth-first top-down."""
        def walk(node: WidgetNode):
            yield node
            for child in node.children:
                yield from walk(child)

        for root in self.root_widgets:
            yield from walk(root)

    def get_widget(self, widget_id: str) -> WidgetNode | None:
        for node in self.iter_all_widgets():
            if node.id == widget_id:
                return node
        return None

    def _sibling_list(self, node: WidgetNode) -> list[WidgetNode]:
        """Return the list that contains `node` (its parent's children
        or root_widgets if top-level)."""
        if node.parent is None:
            return self.root_widgets
        return node.parent.children

    # ------------------------------------------------------------------
    # Naming
    # ------------------------------------------------------------------
    def _generate_unique_name(self, widget_type: str) -> str:
        """Monotonic name: 'Button' → 'Button (1)' → 'Button (2)' → ...

        The counter is per widget type and never reuses numbers, even
        after deletions — so renamed / removed widgets can't collide
        with freshly generated names.
        """
        from app.widgets.registry import get_descriptor
        descriptor = get_descriptor(widget_type)
        base = descriptor.display_name if descriptor else widget_type

        count = self._name_counters.get(widget_type, 0)
        self._name_counters[widget_type] = count + 1

        if count == 0:
            return base
        return f"{base} ({count})"

    def rename_widget(self, widget_id: str, new_name: str) -> None:
        node = self.get_widget(widget_id)
        if node is None:
            return
        if node.name == new_name:
            return
        node.name = new_name
        self.event_bus.publish("widget_renamed", widget_id, new_name)

    # ------------------------------------------------------------------
    # Add / remove / reparent
    # ------------------------------------------------------------------
    def add_widget(
        self, node: WidgetNode, parent_id: str | None = None,
    ) -> None:
        if not node.name:
            node.name = self._generate_unique_name(node.widget_type)
        if parent_id is None:
            node.parent = None
            self.root_widgets.append(node)
        else:
            parent = self.get_widget(parent_id)
            if parent is None:
                # unknown parent id: fall back to top-level to avoid
                # silently dropping the node
                node.parent = None
                self.root_widgets.append(node)
            else:
                node.parent = parent
                parent.children.append(node)
        self.event_bus.publish("widget_added", node)

    def remove_widget(self, widget_id: str) -> None:
        node = self.get_widget(widget_id)
        if node is None:
            return
        # Remove descendants first (depth-first) so listeners see
        # children disappear before their parent.
        for child in list(node.children):
            self.remove_widget(child.id)
        siblings = self._sibling_list(node)
        if node in siblings:
            siblings.remove(node)
        node.parent = None
        if self.selected_id == widget_id:
            self.select_widget(None)
        self.event_bus.publish("widget_removed", widget_id)

    def reparent(
        self,
        widget_id: str,
        new_parent_id: str | None,
        index: int | None = None,
    ) -> None:
        """Move a node between parents and/or to a new sibling position.

        - ``new_parent_id=None`` → top-level
        - ``index=None`` → append to the end of the target sibling list
        - ``index=N`` → insert at position N (clamped)

        Publishes ``widget_reparented`` when the parent actually changes,
        or ``widget_z_changed(direction="reorder")`` when only the
        sibling order changed.
        """
        node = self.get_widget(widget_id)
        if node is None:
            return
        new_parent = (
            self.get_widget(new_parent_id) if new_parent_id else None
        )
        # Refuse to make a node a descendant of itself.
        if new_parent is not None and self._is_descendant(new_parent, node):
            return

        old_parent = node.parent
        old_parent_id = old_parent.id if old_parent is not None else None
        parent_changed = old_parent_id != new_parent_id

        old_siblings = self._sibling_list(node)
        try:
            old_index = old_siblings.index(node)
        except ValueError:
            old_index = None

        # Early-out: same parent and either no index or same index.
        if not parent_changed and (index is None or index == old_index):
            return

        if old_index is not None:
            old_siblings.pop(old_index)

        target_siblings = (
            new_parent.children if new_parent is not None
            else self.root_widgets
        )

        # If staying in the same sibling list and the original slot
        # was before the target slot, removing the node shifted
        # everything after it left by one — compensate.
        if (not parent_changed
                and index is not None
                and old_index is not None
                and old_index < index):
            index -= 1

        node.parent = new_parent
        if index is None:
            target_siblings.append(node)
        else:
            clamped = max(0, min(index, len(target_siblings)))
            target_siblings.insert(clamped, node)

        if parent_changed:
            self.event_bus.publish(
                "widget_reparented", widget_id,
                old_parent_id, new_parent_id,
            )
        else:
            self.event_bus.publish(
                "widget_z_changed", widget_id, "reorder",
            )

    def _is_descendant(
        self, candidate: WidgetNode, ancestor: WidgetNode,
    ) -> bool:
        node: WidgetNode | None = candidate
        while node is not None:
            if node is ancestor:
                return True
            node = node.parent
        return False

    def clear(self) -> None:
        for node in list(self.root_widgets):
            self.remove_widget(node.id)

    # ------------------------------------------------------------------
    # Selection + properties
    # ------------------------------------------------------------------
    def select_widget(self, widget_id: str | None) -> None:
        """Single-selection entry point. Replaces `selected_ids` with
        {widget_id} or an empty set."""
        new_ids: set[str] = {widget_id} if widget_id else set()
        if widget_id == self.selected_id and new_ids == self.selected_ids:
            return
        self.selected_id = widget_id
        self.selected_ids = new_ids
        self.event_bus.publish("selection_changed", widget_id)

    def set_multi_selection(
        self, ids: set[str], primary: str | None = None,
    ) -> None:
        """Replace selection with a set. Emits `selection_changed`
        with the primary id when there's 0 or 1 selected, and with
        `None` when there are 2+ — this naturally clears the
        workspace handles + properties panel while the tree keeps
        its own multi-row highlight."""
        new_ids = {i for i in ids if i is not None}
        if primary is not None and primary not in new_ids:
            primary = None
        if primary is None and new_ids:
            primary = next(iter(new_ids))
        if new_ids == self.selected_ids and primary == self.selected_id:
            return
        self.selected_ids = new_ids
        self.selected_id = primary
        display = primary if len(new_ids) <= 1 else None
        self.event_bus.publish("selection_changed", display)

    def update_property(
        self, widget_id: str, prop_name: str, value,
    ) -> None:
        node = self.get_widget(widget_id)
        if node is None:
            return
        node.properties[prop_name] = value
        self.event_bus.publish(
            "property_changed", widget_id, prop_name, value,
        )

    def set_visibility(self, widget_id: str, visible: bool) -> None:
        """Toggle a node's builder-only visibility flag and notify
        listeners (workspace hides/shows, Object Tree dims the row).
        The model is unaffected beyond the boolean; save/load/export
        all continue to include the node."""
        node = self.get_widget(widget_id)
        if node is None:
            return
        visible = bool(visible)
        if node.visible == visible:
            return
        node.visible = visible
        self.event_bus.publish("widget_visibility_changed", widget_id, visible)

    def set_locked(self, widget_id: str, locked: bool) -> None:
        """Toggle a node's builder-only lock flag. Locked nodes still
        render and export as usual, but the workspace refuses to
        drag / resize / nudge / delete them. Cascades through
        descendants at check-time (see workspace._effective_locked).
        """
        node = self.get_widget(widget_id)
        if node is None:
            return
        locked = bool(locked)
        if node.locked == locked:
            return
        node.locked = locked
        self.event_bus.publish("widget_locked_changed", widget_id, locked)

    # ------------------------------------------------------------------
    # Sibling operations
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Clipboard (Ctrl+C / Ctrl+V)
    # ------------------------------------------------------------------
    def copy_to_clipboard(self, ids) -> int:
        """Snapshot the given widget subtrees into `self.clipboard`.

        Iterates the tree in DFS top-down order so the clipboard
        preserves sibling z-order. Descendants whose ancestor is also
        in `ids` are skipped — copying a container already covers its
        children.

        Returns the number of top-level snapshots stored.
        """
        if not ids:
            return 0
        ids_set = set(ids)
        top_level: list[WidgetNode] = []
        for node in self.iter_all_widgets():
            if node.id not in ids_set:
                continue
            ancestor = node.parent
            is_descendant = False
            while ancestor is not None:
                if ancestor.id in ids_set:
                    is_descendant = True
                    break
                ancestor = ancestor.parent
            if not is_descendant:
                top_level.append(node)
        self.clipboard = [node.to_dict() for node in top_level]
        return len(self.clipboard)

    def paste_from_clipboard(
        self, parent_id: str | None = None,
    ) -> list[str]:
        """Recreate the clipboard snapshots under `parent_id` with
        fresh UUIDs + auto-generated names. Each top-level paste is
        offset by (+20, +20) so it doesn't land exactly on top of the
        original. Pasted widgets become the new selection.

        Returns the list of new top-level widget ids.
        """
        if not self.clipboard:
            return []
        new_top_ids: list[str] = []
        for data in self.clipboard:
            root = self._clone_with_fresh_ids(data)
            try:
                root.properties["x"] = int(root.properties.get("x", 0)) + 20
                root.properties["y"] = int(root.properties.get("y", 0)) + 20
            except (TypeError, ValueError):
                pass
            self._paste_recursive(root, parent_id)
            new_top_ids.append(root.id)
        if new_top_ids:
            if len(new_top_ids) == 1:
                self.select_widget(new_top_ids[0])
            else:
                self.set_multi_selection(
                    set(new_top_ids), primary=new_top_ids[0],
                )
        return new_top_ids

    def _clone_with_fresh_ids(self, data: dict) -> WidgetNode:
        """Rebuild a WidgetNode from a `to_dict` snapshot, forcing a
        fresh UUID for every node in the subtree and clearing names
        so `add_widget` can auto-assign new ones."""
        node = WidgetNode(
            widget_type=data["widget_type"],
            properties=dict(data.get("properties", {})),
        )
        # node.id is already a fresh UUID from WidgetNode.__init__.
        node.name = ""  # let add_widget auto-name
        node.visible = bool(data.get("visible", True))
        node.locked = bool(data.get("locked", False))
        for child_data in data.get("children", []):
            child = self._clone_with_fresh_ids(child_data)
            child.parent = node
            node.children.append(child)
        return node

    def _paste_recursive(
        self, node: WidgetNode, parent_id: str | None,
    ) -> None:
        """Add `node` to the project under `parent_id`, then walk
        descendants. Mirrors `project_loader._add_recursive`: we
        temporarily detach children so `add_widget` only fires the
        event for `node`, then re-add each descendant explicitly so
        every subscriber sees them one by one."""
        children_copy = list(node.children)
        node.children = []
        node.parent = None
        self.add_widget(node, parent_id=parent_id)
        for child in children_copy:
            child.parent = None
            self._paste_recursive(child, parent_id=node.id)

    def duplicate_widget(self, widget_id: str) -> str | None:
        node = self.get_widget(widget_id)
        if node is None:
            return None
        new_props = dict(node.properties)
        try:
            new_props["x"] = int(new_props.get("x", 0)) + 20
            new_props["y"] = int(new_props.get("y", 0)) + 20
        except (ValueError, TypeError):
            pass
        clone = WidgetNode(
            widget_type=node.widget_type,
            properties=new_props,
        )
        # Clone gets a fresh auto-generated name via add_widget.
        parent_id = node.parent.id if node.parent else None
        self.add_widget(clone, parent_id=parent_id)
        self.select_widget(clone.id)
        return clone.id

    def bring_to_front(self, widget_id: str) -> None:
        node = self.get_widget(widget_id)
        if node is None:
            return
        siblings = self._sibling_list(node)
        if not siblings or siblings[-1] is node:
            return
        siblings.remove(node)
        siblings.append(node)
        self.event_bus.publish("widget_z_changed", widget_id, "front")

    def send_to_back(self, widget_id: str) -> None:
        node = self.get_widget(widget_id)
        if node is None:
            return
        siblings = self._sibling_list(node)
        if not siblings or siblings[0] is node:
            return
        siblings.remove(node)
        siblings.insert(0, node)
        self.event_bus.publish("widget_z_changed", widget_id, "back")
