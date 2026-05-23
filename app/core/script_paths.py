"""CTkScript model — the top-level user-scripts folder.

A project keeps its ``CTkScript`` subclasses in a ``scripts/`` folder
at the project root, decoupled from ``assets/`` (which holds media
only). The exporter copies it into the build and the attach picker
AST-scans it.
"""

from __future__ import annotations

from pathlib import Path

# CTkScript model — the top-level user-scripts folder, at the project
# root and decoupled from ``assets/``. Holds the user's ``CTkScript``
# subclasses; the exporter copies it into the build and the attach
# picker AST-scans it.
USER_SCRIPTS_DIR_NAME = "scripts"


def user_scripts_dir(
    project_file_path: str | Path | None,
) -> Path | None:
    """``<project_root>/scripts/`` — the CTkScript model's top-level
    user-scripts folder (outside ``assets/``). ``None`` for unsaved
    projects. Mirrors the layout the exporter copies into the build.
    """
    if not project_file_path:
        return None
    from app.core.project_folder import find_project_root
    root = find_project_root(project_file_path)
    if root is not None:
        return root / USER_SCRIPTS_DIR_NAME
    return Path(project_file_path).parent / USER_SCRIPTS_DIR_NAME
