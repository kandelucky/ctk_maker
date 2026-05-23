"""Phase 2 visual scripting — event handler bind / unbind / reorder."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.commands.base import Command
from app.core.widget_node import WidgetNode

if TYPE_CHECKING:
    from app.core.project import Project


class BindHandlerCommand(Command):
    """Phase 2 visual scripting — append a handler entry to a
    widget's event list. ``event_key`` is the storage key
    (``"command"`` or ``"bind:<seq>"``); ``method_name`` is the
    handler entry — either a string (page method name on the
    window's behavior class) or a handler dict (e.g. a
    ``script_call`` binding to a CTkScript method).
    Both shapes share the multi-method-per-event semantics —
    invocation appends a row, undo pops the row that was added
    (matched by index so duplicates don't confuse the undo stack).

    The actual ``.py`` file mutation (stub creation for string
    entries) happens at the call site; the command only carries
    undo/redo for the model field.
    """

    def __init__(
        self, widget_id: str, event_key: str,
        method_name: "str | dict",
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


class AttachComponentCommand(Command):
    """CTkScript model — attach a component (``{"script", "class"}``) to
    a widget or the window (``attached_components``). ``widget_id`` is
    the WidgetNode id, or ``WINDOW_ID`` for the active document. Undo
    removes the entry it added (recorded index, class-name fallback).
    """

    def __init__(self, widget_id: str, component: dict):
        self.widget_id = widget_id
        self.component = dict(component)
        self._index: int | None = None
        self.description = "Attach script"

    def _target(self, project: "Project"):
        from app.core.project import WINDOW_ID
        if self.widget_id == WINDOW_ID:
            return project.active_document
        return project.get_widget(self.widget_id)

    def _refresh(self, project: "Project") -> None:
        project.event_bus.publish(
            "widget_handler_changed", self.widget_id, "", "",
        )
        project.select_widget(self.widget_id)

    def redo(self, project: "Project") -> None:
        target = self._target(project)
        if target is None:
            return
        comps = getattr(target, "attached_components", None)
        if comps is None:
            target.attached_components = comps = []
        comps.append(dict(self.component))
        self._index = len(comps) - 1
        self._refresh(project)

    def undo(self, project: "Project") -> None:
        target = self._target(project)
        if target is None:
            return
        comps = getattr(target, "attached_components", None) or []
        idx = self._index
        cls = self.component.get("class")
        if (
            idx is None or idx >= len(comps)
            or comps[idx].get("class") != cls
        ):
            idx = next(
                (
                    i for i in range(len(comps) - 1, -1, -1)
                    if comps[i].get("class") == cls
                ),
                None,
            )
        if idx is not None and 0 <= idx < len(comps):
            comps.pop(idx)
        self._refresh(project)


class DetachComponentCommand(Command):
    """CTkScript model — remove a component (by class name) from a widget
    or the window. Undo re-inserts it at its original index."""

    def __init__(self, widget_id: str, class_name: str):
        self.widget_id = widget_id
        self.class_name = class_name
        self._removed: dict | None = None
        self._index: int | None = None
        self.description = "Detach script"

    def _target(self, project: "Project"):
        from app.core.project import WINDOW_ID
        if self.widget_id == WINDOW_ID:
            return project.active_document
        return project.get_widget(self.widget_id)

    def _refresh(self, project: "Project") -> None:
        project.event_bus.publish(
            "widget_handler_changed", self.widget_id, "", "",
        )
        project.select_widget(self.widget_id)

    def redo(self, project: "Project") -> None:
        target = self._target(project)
        if target is None:
            return
        comps = getattr(target, "attached_components", None) or []
        idx = next(
            (
                i for i, c in enumerate(comps)
                if c.get("class") == self.class_name
            ),
            None,
        )
        if idx is None:
            return
        self._index = idx
        self._removed = dict(comps[idx])
        comps.pop(idx)
        self._refresh(project)

    def undo(self, project: "Project") -> None:
        target = self._target(project)
        if target is None or self._removed is None:
            return
        comps = getattr(target, "attached_components", None)
        if comps is None:
            target.attached_components = comps = []
        idx = self._index if self._index is not None else len(comps)
        idx = max(0, min(idx, len(comps)))
        comps.insert(idx, dict(self._removed))
        self._refresh(project)


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
    """Remove one handler entry from a widget's event list. Captures
    the row's index at construction so undo restores it at the same
    position (sibling order matters for execution order). The
    ``previous_method`` is the removed entry — a ``script_call``
    dict in the current model (a bare string only for legacy data).
    List comparison stays correct for both (Python equality is
    per-element / per-key).
    """

    def __init__(
        self,
        widget_id: str,
        event_key: str,
        previous_method: "str | dict",
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
