"""Undo / redo history stack.

Stores ``Command`` objects whose ``do`` has already happened at the
call site; the History can replay them backward and forward.

Publishes ``history_changed`` on the project event bus whenever the
stacks change so toolbar buttons, menus, and any other observer can
refresh their enabled state.

The ``_suspended`` flag is set while undo/redo is replaying a
command so re-entrant calls to ``push`` (from the same UI flow that
originally produced the command) don't pollute the stack.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.commands import Command
    from app.core.project import Project

MAX_DEPTH = 200


class History:
    def __init__(self, project: "Project"):
        self._project = project
        self._undo: list["Command"] = []
        self._redo: list["Command"] = []
        self._suspended: bool = False

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------
    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def is_suspended(self) -> bool:
        return self._suspended

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------
    def push(self, command: "Command") -> None:
        """Record an already-applied command. Drops the redo stack.

        If the incoming command can merge into the undo-stack tail
        (e.g. a rapid-fire sequence of nudges), the tail is mutated
        in place instead of growing the stack.
        """
        if self._suspended:
            return
        if self._undo and command.merge_into(self._undo[-1]):
            if self._redo:
                self._redo.clear()
            self._publish()
            return
        self._undo.append(command)
        if len(self._undo) > MAX_DEPTH:
            del self._undo[0 : len(self._undo) - MAX_DEPTH]
        if self._redo:
            self._redo.clear()
        self._publish()

    def undo(self) -> None:
        if not self._undo:
            return
        command = self._undo.pop()
        self._suspended = True
        try:
            command.undo(self._project)
        finally:
            self._suspended = False
        self._redo.append(command)
        self._publish()

    def redo(self) -> None:
        if not self._redo:
            return
        command = self._redo.pop()
        self._suspended = True
        try:
            command.redo(self._project)
        finally:
            self._suspended = False
        self._undo.append(command)
        self._publish()

    def clear(self) -> None:
        if not self._undo and not self._redo:
            return
        self._undo.clear()
        self._redo.clear()
        self._publish()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _publish(self) -> None:
        try:
            self._project.event_bus.publish("history_changed")
        except Exception:
            pass
