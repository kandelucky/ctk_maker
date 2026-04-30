"""Per-project component library location.

Each project owns its components — they live next to ``assets/``
inside the project folder:

    <project_folder>/components/

Sharing across projects happens via explicit Export / Import (file
picker → ``.ctkcomp`` zip on disk). No user-wide library.
"""

from __future__ import annotations

from pathlib import Path

COMPONENT_DIR_NAME = "components"
COMPONENT_EXT = ".ctkcomp"


def components_root(project_file_path: str | Path | None) -> Path | None:
    """``<project_folder>/components/`` for the given project file
    path (a ``.ctkproj`` path). Returns ``None`` when no project is
    loaded — callers should fall back to a "save project first" hint.

    Two layouts (mirrors ``project_assets_dir``):
    - Multi-page (P1+): page lives at
      ``<root>/assets/pages/foo.ctkproj``. Walk up to find
      ``project.json``; components sit at ``<root>/components/``.
    - Legacy single-file: ``<folder>/foo.ctkproj`` with sibling
      ``<folder>/components/``.
    """
    if not project_file_path:
        return None
    # Local import keeps this module free of project_folder cycles.
    from app.core.project_folder import find_project_root
    root = find_project_root(project_file_path)
    if root is not None:
        return root / COMPONENT_DIR_NAME
    return Path(project_file_path).parent / COMPONENT_DIR_NAME


def ensure_components_root(
    project_file_path: str | Path | None,
) -> Path | None:
    """Create the components folder if missing. ``None`` for unsaved
    projects — caller decides whether to surface a "save first" hint.
    """
    root = components_root(project_file_path)
    if root is None:
        return None
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return root
