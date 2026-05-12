"""Variable commands — Phase 1 visual scripting."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.commands.base import Command

if TYPE_CHECKING:
    from app.core.project import Project


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
