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
    launch_editor,
    resolve_project_root_for_editor,
)
from app.io.scripts.paths import create_user_script

__all__ = [
    # ast_scan
    "find_attachable_scripts",
    "parse_ctkscript_classes",
    "parse_exposed_variables",
    "parse_handler_methods",
    # components (CTkScript resolution)
    "iter_script_call_targets",
    "resolve_script_component",
    # editor
    "launch_editor",
    "resolve_project_root_for_editor",
    # paths
    "create_user_script",
]
