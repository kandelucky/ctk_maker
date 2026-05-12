"""Property-mutation commands — single + multi + description."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.core.commands.base import COALESCE_WINDOW_SEC, Command
from app.core.logger import log_error
from app.core.widget_node import WidgetNode

if TYPE_CHECKING:
    from app.core.project import Project


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
            if isinstance(node, WidgetNode):
                node.description = value
        project.event_bus.publish(
            "widget_description_changed", self.widget_id, value,
        )
        project.select_widget(self.widget_id)

    def undo(self, project: "Project") -> None:
        self._apply(project, self.before)

    def redo(self, project: "Project") -> None:
        self._apply(project, self.after)


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
                    log_error("MultiChangePropertyCommand.undo: parent grid-dim revert")
        project.select_widget(self.widget_id)

    def redo(self, project: "Project") -> None:
        if self._parent_dim_changes is not None:
            parent_id, changes = self._parent_dim_changes
            for key, (_before, after) in changes.items():
                try:
                    project.update_property(parent_id, key, after)
                except Exception:
                    log_error("MultiChangePropertyCommand.redo: parent grid-dim apply")
        for name, (_before, after) in self.changes.items():
            project.update_property(self.widget_id, name, after)
        project.select_widget(self.widget_id)
