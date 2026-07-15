"""Modal dialogs used by the builder.

Each dialog lives in its own sub-module; this package re-exports the
public surface so existing callers can keep importing from
``app.ui.dialogs``.
"""

from app.ui.dialogs.about import AboutDialog
from app.ui.dialogs.add_dialog_size import AddDialogSizeDialog
from app.ui.dialogs.message import (
    MessageDialog,
    ask_ok_cancel,
    ask_string,
    ask_yes_no,
    ask_yes_no_cancel,
    set_default_parent,
    show_error,
    show_info,
    show_warning,
)
from app.ui.dialogs.new_project_size import NewProjectSizeDialog
from app.ui.dialogs.open_project import prompt_open_project_folder
from app.ui.dialogs.rename import RenameDialog
from app.ui.dialogs.rename_page import RenamePageDialog, prompt_rename_page

__all__ = [
    "AboutDialog",
    "AddDialogSizeDialog",
    "MessageDialog",
    "NewProjectSizeDialog",
    "RenameDialog",
    "RenamePageDialog",
    "ask_ok_cancel",
    "ask_string",
    "ask_yes_no",
    "ask_yes_no_cancel",
    "prompt_open_project_folder",
    "prompt_rename_page",
    "set_default_parent",
    "show_error",
    "show_info",
    "show_warning",
]
