"""Per-window visual-scripting (Phase 2) behavior file location.

Each project owns an ``assets/scripts/`` folder beside ``components/``
and ``assets/images/``::

    <project_folder>/assets/scripts/
        __init__.py
        <page_slug>/
            __init__.py
            <window_slug>.py    # one file per Document (window/dialog)
            <other_window>.py

A page == one ``.ctkproj`` file. A window == one ``Document`` inside it
(main window or any dialog). Per-window class scoping means each
window owns its own ``<WindowName>Page`` class — no cross-window
namespace collisions, no fat per-page classes.

Behavior files hold the user-written Python that backs widget event
handlers — generated method skeletons live here, the user writes the
bodies.

Sharing across projects happens via plain file copy (no Library / no
publish flow). Components strip handler bindings on save (see
``app/io/component_io.py``) so a dropped component never references a
method that doesn't exist in the target project.
"""

from __future__ import annotations

import re
from pathlib import Path

ASSETS_DIR_NAME = "assets"
SCRIPTS_DIR_NAME = "scripts"
BEHAVIOR_FILE_EXT = ".py"

# Sibling under ``assets/`` that holds backup copies of behavior
# files when the user picks "Save copy" instead of "Move to recycle
# bin" in the window-delete dialog. Lives in the project so the
# user keeps everything in one place; auto-created on first save.
# Mirrors the live scripts/ layout (per-page subfolders) so the
# archived path stays self-explanatory.
ARCHIVE_DIR_NAME = "scripts_archive"


def scripts_root(project_file_path: str | Path | None) -> Path | None:
    """``<project_folder>/assets/scripts/`` for the given ``.ctkproj``
    path. ``None`` when no project is loaded.

    Two layouts (mirrors ``components_root``):
    - Multi-page (P1+): page lives at
      ``<root>/assets/pages/foo.ctkproj``. Walk up to find
      ``project.json``; scripts sit at ``<root>/assets/scripts/``.
    - Legacy single-file: ``<folder>/foo.ctkproj`` with sibling
      ``<folder>/assets/scripts/``.
    """
    if not project_file_path:
        return None
    # Local import keeps this module free of project_folder cycles.
    from app.core.project_folder import find_project_root
    root = find_project_root(project_file_path)
    if root is not None:
        return root / ASSETS_DIR_NAME / SCRIPTS_DIR_NAME
    return (
        Path(project_file_path).parent
        / ASSETS_DIR_NAME
        / SCRIPTS_DIR_NAME
    )


def page_scripts_dir(
    project_file_path: str | Path | None,
) -> Path | None:
    """``<project>/assets/scripts/<page_slug>/``. The per-page
    subfolder that holds every window's ``.py``. ``None`` when the
    project isn't saved.
    """
    root = scripts_root(project_file_path)
    if root is None:
        return None
    return root / behavior_file_stem(project_file_path)


def ensure_scripts_root(
    project_file_path: str | Path | None,
) -> Path | None:
    """Create ``assets/scripts/`` + the page subfolder + both
    ``__init__.py`` files. ``None`` for unsaved projects.

    The two ``__init__.py`` files make ``assets.scripts.<page>`` an
    importable package so the exporter can emit
    ``from assets.scripts.<page>.<window> import <Class>Page``.
    """
    root = scripts_root(project_file_path)
    if root is None:
        return None
    page_dir = root / behavior_file_stem(project_file_path)
    try:
        page_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    # Both levels need __init__.py — assets/scripts/ is the top
    # package; <page>/ is the subpackage. Both files stay empty
    # (Decision I=A) — the user can hand-edit if they want.
    for init_path in (root / "__init__.py", page_dir / "__init__.py"):
        if not init_path.exists():
            try:
                init_path.write_text("", encoding="utf-8")
            except OSError:
                pass
    return page_dir


def behavior_file_stem(project_file_path: str | Path | None) -> str:
    """Stem of the page filename (the ``.ctkproj`` basename),
    lowercased.

    ``"login.ctkproj"`` → ``"login"``
    ``"Dashboard.ctkproj"`` → ``"dashboard"``

    Falls back to ``"page"`` when no path is available.
    """
    if not project_file_path:
        return "page"
    stem = Path(project_file_path).stem
    return (stem.lower() or "page")


def slugify_window_name(name: str | None) -> str:
    """Window-name → file-stem slug.

    Strip non-``[A-Za-z0-9_]`` to underscores, collapse repeats,
    lowercase, prefix underscore when the result starts with a digit
    (Decision J=A — silent fix for invalid module names). Falls back
    to ``"window"`` for empty / all-symbol input.

    ``"Main Window"`` → ``"main_window"``
    ``"Confirm Dialog!"`` → ``"confirm_dialog"``
    ``"1Setup"`` → ``"_1setup"``
    """
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", name or "").strip("_").lower()
    if not cleaned:
        return "window"
    if cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned


def behavior_file_path(
    project_file_path: str | Path | None,
    document=None,
) -> Path | None:
    """``<project>/assets/scripts/<page>/<window>.py`` or ``None``
    when unsaved. ``document`` is a ``Document`` instance — its
    ``.name`` drives the filename via ``slugify_window_name``. Pass
    ``None`` to fall back to a ``page.py`` placeholder used by the
    main-window default before any document exists.
    """
    page_dir = page_scripts_dir(project_file_path)
    if page_dir is None:
        return None
    window_slug = (
        slugify_window_name(getattr(document, "name", None))
        if document is not None else "main"
    )
    return page_dir / f"{window_slug}{BEHAVIOR_FILE_EXT}"


def behavior_class_name(document=None) -> str:
    """PascalCase + ``Page`` suffix derived from the window name.

    ``"Main Window"`` → ``"MainWindowPage"``
    ``"confirm_dialog"`` → ``"ConfirmDialogPage"``

    Per-window (Decision #13) — every Document gets its own class.
    Empty / missing name falls back to ``"WindowPage"``.
    """
    if document is None:
        return "WindowPage"
    slug = slugify_window_name(getattr(document, "name", None))
    parts = [p for p in slug.lstrip("_").split("_") if p]
    if not parts:
        return "WindowPage"
    return "".join(p.capitalize() for p in parts) + "Page"


def archive_dir(
    project_file_path: str | Path | None,
) -> Path | None:
    """``<project>/assets/scripts_archive/<page>/`` — default
    destination for behavior files when the user picks "Save copy"
    in the window-delete dialog. Mkdir on demand so the folder
    appears only when the user has actually archived something;
    ``None`` for unsaved projects.

    Mirrors the live scripts/ layout (per-page subfolder) so the
    archived path stays self-explanatory and survives a future
    page rename via the same logic.
    """
    if not project_file_path:
        return None
    from app.core.project_folder import find_project_root
    root = find_project_root(project_file_path)
    if root is not None:
        target = root / ASSETS_DIR_NAME / ARCHIVE_DIR_NAME / behavior_file_stem(project_file_path)
    else:
        target = (
            Path(project_file_path).parent
            / ASSETS_DIR_NAME / ARCHIVE_DIR_NAME
            / behavior_file_stem(project_file_path)
        )
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return target
