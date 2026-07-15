"""CTkScript model — read/scan user scripts + create new ones.

The user keeps ``CTkScript`` subclasses in the project's top-level
``scripts/`` folder. CTkMaker never imports them — it only AST-scans
them (for the attach + Function pickers) and the exporter copies the
folder into the build. This package re-exports the public surface so
callers can keep importing from ``app.io.scripts``.
"""

from app.io.scripts.ast_scan import (
    find_attachable_scripts,
    parse_ctkscript_classes,
    parse_exposed_variables,
    parse_handler_methods,
)
from app.io.scripts.components import (
    iter_script_call_targets,
    resolve_script_component,
)
from app.io.scripts.editor import (
    EDITOR_ORDER,
    editor_id_for_label,
    editor_id_from_command,
    editor_is_available,
    editor_label,
    launch_editor,
    launch_editor_from_settings,
    resolve_editor_path,
    resolve_project_root_for_editor,
)
from app.io.scripts.paths import (
    class_name_to_filename,
    create_user_script,
    normalize_class_name,
)
from app.io.scripts.variable_fields import build_variable_rows

__all__ = [
    # ast_scan
    "find_attachable_scripts",
    "parse_ctkscript_classes",
    "parse_exposed_variables",
    "parse_handler_methods",
    # components (CTkScript resolution)
    "iter_script_call_targets",
    "resolve_script_component",
    # variable_fields (Script Variables panel rows)
    "build_variable_rows",
    # editor
    "EDITOR_ORDER",
    "editor_id_for_label",
    "editor_id_from_command",
    "editor_is_available",
    "editor_label",
    "launch_editor",
    "launch_editor_from_settings",
    "resolve_editor_path",
    "resolve_project_root_for_editor",
    # paths
    "class_name_to_filename",
    "create_user_script",
    "normalize_class_name",
]
