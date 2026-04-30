"""Per-project visual-scripting (Phase 2) behavior file location.

Each project owns a ``scripts/`` folder next to ``components/`` and
``assets/``::

    <project_folder>/scripts/
        __init__.py
        <page_slug>.py     # one file per page

Behavior files hold the user-written Python that backs widget event
handlers — generated method skeletons live here, the user writes the
bodies.

Sharing across projects happens via plain file copy (no Library / no
publish flow). Components strip handler bindings on save (see
``app/io/component_io.py``) so a dropped component never references a
method that doesn't exist in the target project.
"""

from __future__ import annotations

from pathlib import Path

SCRIPTS_DIR_NAME = "scripts"
BEHAVIOR_FILE_EXT = ".py"


def scripts_root(project_file_path: str | Path | None) -> Path | None:
    """``<project_folder>/scripts/`` for the given ``.ctkproj`` path.
    Returns ``None`` when no project is loaded — callers should fall
    back to a "save project first" hint.

    Two layouts (mirrors ``components_root``):
    - Multi-page (P1+): page lives at
      ``<root>/assets/pages/foo.ctkproj``. Walk up to find
      ``project.json``; scripts sit at ``<root>/scripts/``.
    - Legacy single-file: ``<folder>/foo.ctkproj`` with sibling
      ``<folder>/scripts/``.
    """
    if not project_file_path:
        return None
    # Local import keeps this module free of project_folder cycles.
    from app.core.project_folder import find_project_root
    root = find_project_root(project_file_path)
    if root is not None:
        return root / SCRIPTS_DIR_NAME
    return Path(project_file_path).parent / SCRIPTS_DIR_NAME


def ensure_scripts_root(
    project_file_path: str | Path | None,
) -> Path | None:
    """Create the ``scripts/`` folder + its ``__init__.py`` if missing.
    ``None`` for unsaved projects — caller decides whether to surface
    a "save first" hint. The ``__init__.py`` makes ``scripts`` an
    importable package so the exporter can emit
    ``from .scripts.<page> import <PageClass>``.
    """
    root = scripts_root(project_file_path)
    if root is None:
        return None
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    init_path = root / "__init__.py"
    if not init_path.exists():
        try:
            init_path.write_text("", encoding="utf-8")
        except OSError:
            pass
    return root


def behavior_file_stem(project_file_path: str | Path | None) -> str:
    """Stem of the page filename, lowercased.

    ``"login.ctkproj"`` → ``"login"``
    ``"Dashboard.ctkproj"`` → ``"dashboard"``

    Falls back to ``"page"`` when no path is available so callers
    always have something to work with.
    """
    if not project_file_path:
        return "page"
    stem = Path(project_file_path).stem
    return (stem.lower() or "page")


def behavior_file_path(
    project_file_path: str | Path | None,
) -> Path | None:
    """``<project>/scripts/<page>.py`` or ``None`` when unsaved.
    The file may not exist yet — call ``load_or_create_behavior_file``
    in ``app/io/scripts.py`` to materialise the skeleton.
    """
    root = scripts_root(project_file_path)
    if root is None:
        return None
    return root / f"{behavior_file_stem(project_file_path)}{BEHAVIOR_FILE_EXT}"


def behavior_class_name(project_file_path: str | Path | None) -> str:
    """PascalCase + ``Page`` suffix derived from the page filename.

    ``"login"`` → ``"LoginPage"``
    ``"user_settings"`` → ``"UserSettingsPage"``

    Used by the exporter for the ``from .scripts.<page> import …``
    line and by the skeleton-generation step.
    """
    if not project_file_path:
        return "Page"
    stem = behavior_file_stem(project_file_path)
    parts = [p for p in stem.split("_") if p]
    if not parts:
        return "Page"
    return "".join(p.capitalize() for p in parts) + "Page"
