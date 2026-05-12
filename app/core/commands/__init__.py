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

Sub-modules group commands by the domain they mutate; this package
re-exports the full surface so existing callers can keep importing
from ``app.core.commands``.
"""

from app.core.commands.base import (
    COALESCE_WINDOW_SEC,
    Command,
    _add_subtree_recursive,
    _restore_widget,
    build_bulk_add_entries,
    paste_target_parent_id,
)
from app.core.commands.documents import (
    AddDocumentCommand,
    ArrangeDocumentsCommand,
    DeleteDocumentCommand,
    MoveDocumentCommand,
    _remove_document_by_id,
    _replay_children,
    _restore_document,
)
from app.core.commands.flags import (
    BulkToggleFlagCommand,
    SetGroupCommand,
    ToggleFlagCommand,
)
from app.core.commands.handlers import (
    BindHandlerCommand,
    ReorderHandlerCommand,
    UnbindHandlerCommand,
)
from app.core.commands.object_references import (
    AddObjectReferenceCommand,
    DeleteObjectReferenceCommand,
    RenameObjectReferenceCommand,
    SetObjectReferenceTargetCommand,
    _iter_all_refs,
    _ref_target_list,
)
from app.core.commands.properties import (
    ChangeDescriptionCommand,
    ChangePropertyCommand,
    MultiChangePropertyCommand,
)
from app.core.commands.tree import (
    AddWidgetCommand,
    BulkAddCommand,
    BulkMoveCommand,
    BulkReparentCommand,
    DeleteMultipleCommand,
    DeleteWidgetCommand,
    MoveCommand,
    RenameCommand,
    ReparentCommand,
    ResizeCommand,
    ZOrderCommand,
    push_zorder_history,
)
from app.core.commands.variables import (
    AddVariableCommand,
    ChangeVariableDefaultCommand,
    ChangeVariableTypeCommand,
    DeleteVariableCommand,
    RenameVariableCommand,
    _variable_target_list,
)

__all__ = [
    "COALESCE_WINDOW_SEC",
    "Command",
    # tree
    "AddWidgetCommand",
    "DeleteWidgetCommand",
    "DeleteMultipleCommand",
    "MoveCommand",
    "BulkMoveCommand",
    "ResizeCommand",
    "ReparentCommand",
    "BulkReparentCommand",
    "RenameCommand",
    "BulkAddCommand",
    "ZOrderCommand",
    "push_zorder_history",
    # properties
    "ChangePropertyCommand",
    "ChangeDescriptionCommand",
    "MultiChangePropertyCommand",
    # handlers
    "BindHandlerCommand",
    "ReorderHandlerCommand",
    "UnbindHandlerCommand",
    # documents
    "AddDocumentCommand",
    "DeleteDocumentCommand",
    "ArrangeDocumentsCommand",
    "MoveDocumentCommand",
    # flags
    "ToggleFlagCommand",
    "BulkToggleFlagCommand",
    "SetGroupCommand",
    # variables
    "AddVariableCommand",
    "DeleteVariableCommand",
    "RenameVariableCommand",
    "ChangeVariableTypeCommand",
    "ChangeVariableDefaultCommand",
    # object references
    "AddObjectReferenceCommand",
    "DeleteObjectReferenceCommand",
    "RenameObjectReferenceCommand",
    "SetObjectReferenceTargetCommand",
    # helpers
    "paste_target_parent_id",
    "build_bulk_add_entries",
]
