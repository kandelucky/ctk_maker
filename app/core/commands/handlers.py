"""Phase 2 visual scripting — event handler bind / unbind / reorder."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.commands.base import Command
from app.core.widget_node import WidgetNode

if TYPE_CHECKING:
    from app.core.project import Project


class BindHandlerCommand(Command):
    """Phase 2 visual scripting — append a method to a widget's
    event handler list. ``event_key`` is the storage key
    (``"command"`` or ``"bind:<seq>"``); ``method_name`` is the
    method on the window's behavior class that the runtime /
    exporter will resolve. Multi-method-per-event (Decision #10) —
    each invocation appends another row, undo pops the row that
    was added (matched by index, so duplicate names don't confuse
    the undo stack).

    The actual ``.py`` file mutation happens at the call site (the
    command only carries undo/redo for the model field).
    """

    def __init__(
        self, widget_id: str, event_key: str, method_name: str,
    ):
        self.widget_id = widget_id
        self.event_key = event_key
        self.method_name = method_name
        # Captured on first redo() (or set externally by the caller
        # right after the do-side append) so undo knows which row
        # to remove. Lets the undo path stay correct even when the
        # same method name appears more than once on the same event.
        self._appended_index: int | None = None
        self.description = "Bind handler"

    def _do(self, project: "Project") -> None:
        node = project.get_widget(self.widget_id)
        if not isinstance(node, WidgetNode):
            return
        methods = node.handlers.setdefault(self.event_key, [])
        methods.append(self.method_name)
        self._appended_index = len(methods) - 1
        project.event_bus.publish(
            "widget_handler_changed",
            self.widget_id, self.event_key, self.method_name,
        )
        project.select_widget(self.widget_id)

    def _undo(self, project: "Project") -> None:
        node = project.get_widget(self.widget_id)
        if not isinstance(node, WidgetNode):
            return
        methods = node.handlers.get(self.event_key)
        if not methods:
            return
        idx = self._appended_index
        # Defensive — if we never recorded the index (do() was
        # bypassed) fall back to popping the last matching name.
        if idx is None or idx >= len(methods) or methods[idx] != self.method_name:
            for i in range(len(methods) - 1, -1, -1):
                if methods[i] == self.method_name:
                    idx = i
                    break
        if idx is None:
            return
        methods.pop(idx)
        if not methods:
            node.handlers.pop(self.event_key, None)
        project.event_bus.publish(
            "widget_handler_changed",
            self.widget_id, self.event_key, "",
        )
        project.select_widget(self.widget_id)

    def undo(self, project: "Project") -> None:
        self._undo(project)

    def redo(self, project: "Project") -> None:
        self._do(project)


class ReorderHandlerCommand(Command):
    """Move a bound method up or down within its event handler list.
    Execution order matters — the exporter emits a lambda chain in
    list order — so reordering is a real undoable change, not just
    a visual tweak.
    """

    def __init__(
        self,
        widget_id: str,
        event_key: str,
        from_index: int,
        to_index: int,
    ):
        self.widget_id = widget_id
        self.event_key = event_key
        self.from_index = int(from_index)
        self.to_index = int(to_index)
        self.description = "Reorder handler"

    def _move(
        self, project: "Project", src: int, dst: int,
    ) -> None:
        node = project.get_widget(self.widget_id)
        if not isinstance(node, WidgetNode):
            return
        methods = node.handlers.get(self.event_key)
        if not methods or src == dst:
            return
        if not (0 <= src < len(methods) and 0 <= dst < len(methods)):
            return
        method = methods.pop(src)
        methods.insert(dst, method)
        project.event_bus.publish(
            "widget_handler_changed",
            self.widget_id, self.event_key, method,
        )
        project.select_widget(self.widget_id)

    def undo(self, project: "Project") -> None:
        self._move(project, self.to_index, self.from_index)

    def redo(self, project: "Project") -> None:
        self._move(project, self.from_index, self.to_index)


class UnbindHandlerCommand(Command):
    """Remove one method from a widget's event handler list. Captures
    the row's index at construction so undo restores it at the same
    position (sibling order matters for execution order).
    """

    def __init__(
        self,
        widget_id: str,
        event_key: str,
        previous_method: str,
        index: int,
    ):
        self.widget_id = widget_id
        self.event_key = event_key
        self.previous_method = previous_method
        self.index = int(index)
        self.description = "Unbind handler"

    def _do(self, project: "Project") -> None:
        node = project.get_widget(self.widget_id)
        if not isinstance(node, WidgetNode):
            return
        methods = node.handlers.get(self.event_key)
        if not methods or self.index >= len(methods):
            return
        if methods[self.index] != self.previous_method:
            return
        methods.pop(self.index)
        if not methods:
            node.handlers.pop(self.event_key, None)
        project.event_bus.publish(
            "widget_handler_changed",
            self.widget_id, self.event_key, "",
        )
        project.select_widget(self.widget_id)

    def _undo(self, project: "Project") -> None:
        node = project.get_widget(self.widget_id)
        if not isinstance(node, WidgetNode):
            return
        methods = node.handlers.setdefault(self.event_key, [])
        idx = max(0, min(self.index, len(methods)))
        methods.insert(idx, self.previous_method)
        project.event_bus.publish(
            "widget_handler_changed",
            self.widget_id, self.event_key, self.previous_method,
        )
        project.select_widget(self.widget_id)

    def undo(self, project: "Project") -> None:
        self._undo(project)

    def redo(self, project: "Project") -> None:
        self._do(project)
