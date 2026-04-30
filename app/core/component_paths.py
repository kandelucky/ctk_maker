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
# Local on-disk extension. Used for Save and Personal export — clean
# and short. GitHub Discussions blocks .ctkcomp uploads (extension
# not on its allow-list), which is the desired behaviour: local
# components stay local, sharing requires going through the Publish
# flow (License accept) which writes the upload-friendly variant.
COMPONENT_EXT = ".ctkcomp"
# Hub-upload variant. Same zip on disk, different filename, so
# GitHub recognises the trailing .zip and accepts the attachment.
PUBLISH_COMPONENT_EXT = ".ctkcomp.zip"


def is_component_file(path) -> bool:
    """True if ``path`` ends in either the local or the Hub-upload
    extension. Pass either a Path or a string.
    """
    name = str(path).lower()
    return (
        name.endswith(PUBLISH_COMPONENT_EXT)
        or name.endswith(COMPONENT_EXT)
    )


def component_display_stem(path) -> str:
    """User-facing stem with **either** extension stripped, so
    ``LoginForm.ctkcomp.zip``, ``LoginForm.ctkcomp`` and a
    non-component file all yield ``LoginForm`` consistently.
    Strips the longer suffix first so a ``.ctkcomp.zip`` filename
    doesn't collapse to ``LoginForm.ctkcomp``.
    """
    from pathlib import Path
    p = Path(path)
    name = p.name
    lower = name.lower()
    if lower.endswith(PUBLISH_COMPONENT_EXT):
        return name[: -len(PUBLISH_COMPONENT_EXT)]
    if lower.endswith(COMPONENT_EXT):
        return name[: -len(COMPONENT_EXT)]
    return p.stem


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
