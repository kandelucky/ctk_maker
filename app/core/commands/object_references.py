"""Object reference commands — v1.10.8 (replaces Behavior Fields)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.commands.base import Command

if TYPE_CHECKING:
    from app.core.object_references import RefScope
    from app.core.project import Project


def _ref_target_list(
    project: "Project", scope: str, document_id: str | None,
) -> list:
    """Pick the right backing list for an object-reference command's
    scope. Locals follow ``document_id`` first; if the document is
    gone (e.g. deleted between redo and undo), the entry is dropped.
    """
    if scope == "local":
        if document_id is None:
            return []
        doc = project.get_document(document_id)
        if doc is None:
            return []
        return doc.local_object_references
    return project.object_references


def _iter_all_refs(project):
    """Walk every ObjectReferenceEntry the project owns — globals
    + every document's locals. Used by rename / set-target commands
    that don't know the entry's scope up front.
    """
    for entry in project.object_references:
        yield entry
    for doc in project.documents:
        for entry in doc.local_object_references:
            yield entry


class AddObjectReferenceCommand(Command):
    """Append a new object reference. ``entry_dict`` carries the
    serialised ``ObjectReferenceEntry`` so undo / redo recreate it
    with the same UUID + name + target. ``scope`` + ``document_id``
    route the entry to the right list; locals require a document_id.
    """

    def __init__(
        self, entry_dict: dict, index: int,
        scope: "RefScope" = "local", document_id: str | None = None,
    ):
        self.entry_dict = dict(entry_dict)
        self.index = index
        self.scope: "RefScope" = scope
        self.document_id = document_id
        self.description = (
            f"Add reference: {entry_dict.get('name', '')}"
        )

    def undo(self, project: "Project") -> None:
        ref_id = self.entry_dict.get("id")
        if not ref_id:
            return
        target = _ref_target_list(project, self.scope, self.document_id)
        for i, e in enumerate(list(target)):
            if e.id == ref_id:
                target.pop(i)
                project.event_bus.publish(
                    "object_reference_removed", e,
                )
                break

    def redo(self, project: "Project") -> None:
        from app.core.object_references import ObjectReferenceEntry
        entry = ObjectReferenceEntry.from_dict(self.entry_dict)
        entry.scope = self.scope  # storage location is truth
        target = _ref_target_list(project, self.scope, self.document_id)
        if 0 <= self.index <= len(target):
            target.insert(self.index, entry)
        else:
            target.append(entry)
        project.event_bus.publish("object_reference_added", entry)


class DeleteObjectReferenceCommand(Command):
    """Remove an object reference. Captures the entry + index so undo
    restores it at the same position.
    """

    def __init__(
        self, entry_dict: dict, index: int,
        scope: "RefScope" = "local", document_id: str | None = None,
    ):
        self.entry_dict = dict(entry_dict)
        self.index = index
        self.scope: "RefScope" = scope
        self.document_id = document_id
        self.description = (
            f"Delete reference: {entry_dict.get('name', '')}"
        )

    def undo(self, project: "Project") -> None:
        from app.core.object_references import ObjectReferenceEntry
        entry = ObjectReferenceEntry.from_dict(self.entry_dict)
        entry.scope = self.scope
        target = _ref_target_list(project, self.scope, self.document_id)
        if 0 <= self.index <= len(target):
            target.insert(self.index, entry)
        else:
            target.append(entry)
        project.event_bus.publish("object_reference_added", entry)

    def redo(self, project: "Project") -> None:
        ref_id = self.entry_dict.get("id")
        if not ref_id:
            return
        target = _ref_target_list(project, self.scope, self.document_id)
        for i, e in enumerate(list(target)):
            if e.id == ref_id:
                target.pop(i)
                project.event_bus.publish(
                    "object_reference_removed", e,
                )
                break


class RenameObjectReferenceCommand(Command):
    def __init__(self, ref_id: str, before: str, after: str):
        self.ref_id = ref_id
        self.before = before
        self.after = after
        self.description = (
            f"Rename reference: {before} → {after}"
        )

    def _set_name(self, project: "Project", name: str) -> None:
        for entry in _iter_all_refs(project):
            if entry.id == self.ref_id:
                entry.name = name
                project.event_bus.publish(
                    "object_reference_renamed", entry,
                )
                return

    def undo(self, project: "Project") -> None:
        self._set_name(project, self.before)

    def redo(self, project: "Project") -> None:
        self._set_name(project, self.after)


class SetObjectReferenceTargetCommand(Command):
    """Re-bind an object reference to a different widget / document.
    Captures the previous target_id so undo restores the prior pick.
    Empty ``new_target_id`` clears the binding.
    """

    def __init__(self, ref_id: str, new_target_id: str):
        self.ref_id = ref_id
        self.new_target_id = new_target_id
        self._previous_target_id: str | None = None
        self.description = "Set reference target"

    def _entry(self, project: "Project"):
        for entry in _iter_all_refs(project):
            if entry.id == self.ref_id:
                return entry
        return None

    def redo(self, project: "Project") -> None:
        entry = self._entry(project)
        if entry is None:
            return
        if self._previous_target_id is None:
            self._previous_target_id = entry.target_id
        entry.target_id = self.new_target_id
        project.event_bus.publish(
            "object_reference_target_changed", entry,
        )

    def undo(self, project: "Project") -> None:
        entry = self._entry(project)
        if entry is None:
            return
        entry.target_id = self._previous_target_id or ""
        project.event_bus.publish(
            "object_reference_target_changed", entry,
        )
