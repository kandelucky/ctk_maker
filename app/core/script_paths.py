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

import os
import re
import shutil
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

    When a digit-start ``.ctkproj`` filename gains the underscore
    prefix from [[behavior_file_stem]], any pre-existing folder at the
    raw (digit-start) location is silently migrated to the new
    underscored name so older projects keep their hand-written
    behavior intact.
    """
    root = scripts_root(project_file_path)
    if root is None:
        return None
    new_stem = behavior_file_stem(project_file_path)
    _migrate_digit_prefix_dir(root, project_file_path, new_stem)
    page_dir = root / new_stem
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


def _migrate_digit_prefix_dir(
    root: Path,
    project_file_path: str | Path | None,
    new_stem: str,
) -> None:
    """Rename ``assets/scripts/<digit-start-stem>/`` to
    ``assets/scripts/_<digit-start-stem>/`` when the new naming rule
    would target the prefixed form. Silent no-op when:

    - the .ctkproj filename doesn't start with a digit
    - the source folder is missing (no behavior to migrate)
    - the destination already exists with content (refuse to clobber
      hand-written code; caller will see the destination and use it)

    Same for the archive folder so historic exports stay readable.
    """
    if not project_file_path:
        return
    raw_stem = (Path(project_file_path).stem.lower() or "page")
    if raw_stem == new_stem or not raw_stem[:1].isdigit():
        return
    # archive parent lives a sibling away from ``scripts_root`` —
    # reuse the existing migrator which already handles both sides.
    project_folder = root.parent.parent
    try:
        migrate_page_scripts_folders(project_folder, raw_stem, new_stem)
    except ScriptsMigrationConflict:
        # Destination already has real content — keep the old folder
        # in place; ``ensure_scripts_root`` will create the new one
        # next to it. User can merge manually.
        pass


def behavior_file_stem(project_file_path: str | Path | None) -> str:
    """Stem of the page filename (the ``.ctkproj`` basename),
    lowercased and made into a valid Python identifier.

    The stem becomes both the directory name (``assets/scripts/<stem>/``)
    and a path component in the exporter's ``from assets.scripts.<stem>
    .<window> import ...`` statement. Python rejects digit-start module
    names as a ``SyntaxError`` (``001.foo`` is the literal ``0.01``
    followed by ``.foo``), so a leading-underscore fix is applied — the
    same rule [[slugify_window_name]] already uses for window slugs.

    ``"login.ctkproj"`` → ``"login"``
    ``"Dashboard.ctkproj"`` → ``"dashboard"``
    ``"001.ctkproj"`` → ``"_001"``

    Falls back to ``"page"`` when no path is available.
    """
    if not project_file_path:
        return "page"
    stem = (Path(project_file_path).stem.lower() or "page")
    if stem[0].isdigit():
        stem = "_" + stem
    return stem


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
    ``"001Doc"`` → ``"_001docPage"``  (digit-start gets ``_`` prefix
    so the class is a valid Python identifier)

    Per-window (Decision #13) — every Document gets its own class.
    Empty / missing name falls back to ``"WindowPage"``.
    """
    if document is None:
        return "WindowPage"
    slug = slugify_window_name(getattr(document, "name", None))
    # Keep the leading-underscore guard from ``slugify_window_name``
    # (lstrip would discard the digit-start fix and produce an invalid
    # class name like ``001Page``).
    parts = [p for p in slug.split("_") if p]
    if not parts:
        return "WindowPage"
    joined = "".join(p.capitalize() for p in parts)
    if joined[0].isdigit():
        joined = "_" + joined
    return joined + "Page"


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


class ScriptsMigrationConflict(Exception):
    """Raised when ``migrate_page_scripts_folders`` cannot move a
    per-page subfolder because the destination already exists with
    non-stub content. Caller decides whether to surface as a fatal
    error or skip.
    """


def _is_disposable_target(target_dir: Path) -> bool:
    """True when ``target_dir`` either doesn't exist, is empty, or
    contains only a single ``__init__.py`` (stub-folder shape created
    eagerly by ``ensure_scripts_root``). Used by
    ``migrate_page_scripts_folders`` to decide whether the stub can
    be safely overwritten by the source dir's real contents.
    """
    if not target_dir.exists():
        return True
    try:
        entries = list(target_dir.iterdir())
    except OSError:
        return False
    if not entries:
        return True
    if len(entries) == 1 and entries[0].name == "__init__.py":
        # Empty __init__.py is the regen baseline — anything else
        # (real source files or other stubs) means user-authored
        # content that we mustn't silently overwrite.
        try:
            return entries[0].stat().st_size == 0
        except OSError:
            return False
    return False


def _migrate_one_subfolder(
    parent: Path, old_stem: str, new_stem: str,
) -> bool:
    """Move ``parent/<old_stem>/`` → ``parent/<new_stem>/``. Returns
    True when a real migration happened, False when the source didn't
    exist (no-op). Raises ``ScriptsMigrationConflict`` when the
    destination already holds non-stub content.
    """
    src = parent / old_stem
    dst = parent / new_stem
    if not src.exists():
        return False
    if not _is_disposable_target(dst):
        raise ScriptsMigrationConflict(
            f"Cannot migrate '{src}' → '{dst}': destination is not "
            f"empty (and contains more than just an empty __init__.py)."
        )
    if dst.exists():
        # Stub-shaped target: drop it so os.replace can land cleanly.
        # rmtree handles the single __init__.py case + any future
        # stub-only layouts without enumerating them.
        shutil.rmtree(dst)
    os.replace(src, dst)
    return True


def migrate_page_scripts_folders(
    project_folder: str | Path, old_stem: str, new_stem: str,
) -> None:
    """Rename per-page ``assets/scripts/<stem>/`` and
    ``assets/scripts_archive/<stem>/`` subfolders when a page's
    ``.ctkproj`` filename is renamed.

    No-op when both source folders are absent (page never had
    behavior code). Idempotent when ``old_stem == new_stem``. Raises
    ``ScriptsMigrationConflict`` when either destination already
    holds non-stub content — caller surfaces this as a user-facing
    error before the rest of the rename completes.
    """
    if old_stem == new_stem:
        return
    folder = Path(project_folder)
    scripts_parent = folder / ASSETS_DIR_NAME / SCRIPTS_DIR_NAME
    archive_parent = folder / ASSETS_DIR_NAME / ARCHIVE_DIR_NAME
    _migrate_one_subfolder(scripts_parent, old_stem, new_stem)
    _migrate_one_subfolder(archive_parent, old_stem, new_stem)
