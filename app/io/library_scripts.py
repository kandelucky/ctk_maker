"""Library script management — per-page shared ``.py`` files.

Library scripts are user-authored Python modules that live alongside
per-window behavior files at
``<project>/assets/scripts/<page_slug>/``. They give the user a place
to put shared utilities (``helpers.py``, ``api.py``, sub-packages
like ``services/auth.py``) that behavior files can import via plain
relative imports.

Library scripts are page-scoped — mirrors the Variables Global scope
model. Each page exports as an independent ``.py``; cross-page
sharing would break the per-page export invariant, so this module
deliberately stops at the page boundary.

This module is pure I/O: no UI imports, no Tk. ``scripts_window.py``
drives the panel; this module owns the filesystem.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from app.core.script_paths import (
    behavior_file_stem,
    ensure_scripts_root,
    page_scripts_dir,
    scripts_root,
    slugify_window_name,
)

PY_EXT = ".py"


@dataclass
class LibraryEntry:
    """One row in the Scripts panel tree.

    ``rel_path`` is a POSIX-style path relative to the page folder
    (``"helpers.py"`` or ``"services/auth.py"``). ``is_folder`` flags
    sub-packages so the UI can render an expandable node.
    ``is_behavior`` flags per-window behavior files (auto-managed by
    the builder) — the panel renders these with a distinct icon so
    the user can tell them apart from manually-added library scripts.
    """

    rel_path: str
    is_folder: bool
    children: list["LibraryEntry"]
    is_behavior: bool = False

    @property
    def name(self) -> str:
        return self.rel_path.rsplit("/", 1)[-1]


def _window_slug_set(window_names: list[str] | None) -> set[str]:
    """Window-name list → set of slugs. Behavior files match these
    slugs and are excluded from the library listing.
    """
    if not window_names:
        return set()
    return {slugify_window_name(n) for n in window_names if n}


def _is_behavior_file(path: Path, window_slugs: set[str]) -> bool:
    """A ``.py`` file is a behavior file when its stem matches a
    window slug for the current page. ``__init__.py`` is never a
    behavior file — handled separately as a package marker.
    """
    if path.suffix != PY_EXT:
        return False
    if path.stem == "__init__":
        return False
    return path.stem in window_slugs


def list_library_scripts(
    project_file_path: str | Path | None,
    window_names: list[str] | None,
) -> list[LibraryEntry]:
    """Return the library script tree for the active page.

    Walks ``<project>/assets/scripts/<page>/`` and returns every
    ``.py`` file + sub-folder that is NOT a behavior file for one of
    the windows in ``window_names``. ``__init__.py`` is hidden — it's
    a package marker, not user content.

    Returns an empty list when the project is unsaved or the page
    folder doesn't exist yet.
    """
    page_dir = page_scripts_dir(project_file_path)
    if page_dir is None or not page_dir.exists():
        return []
    window_slugs = _window_slug_set(window_names)
    return _walk(page_dir, page_dir, window_slugs)


def _walk(
    page_root: Path, current: Path, window_slugs: set[str],
) -> list[LibraryEntry]:
    """Recursive directory walk producing ``LibraryEntry`` tree.

    Behavior files (page-root ``.py`` whose stem matches a window
    slug) come first, then sub-packages, then library files. All
    sorted alphabetically within their group. Anything that isn't
    ``.py`` or a folder is silently skipped.

    ``__init__.py`` and ``__pycache__`` are hidden — package
    plumbing, not user content.
    """
    behavior: list[LibraryEntry] = []
    folders: list[LibraryEntry] = []
    files: list[LibraryEntry] = []
    try:
        entries = sorted(current.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return []
    for entry in entries:
        if entry.is_dir():
            if entry.name == "__pycache__":
                continue
            rel = entry.relative_to(page_root).as_posix()
            children = _walk(page_root, entry, window_slugs)
            folders.append(
                LibraryEntry(rel_path=rel, is_folder=True, children=children),
            )
        elif entry.is_file() and entry.suffix == PY_EXT:
            if entry.name == "__init__.py":
                continue
            rel = entry.relative_to(page_root).as_posix()
            is_behavior = (
                current == page_root
                and _is_behavior_file(entry, window_slugs)
            )
            row = LibraryEntry(
                rel_path=rel, is_folder=False, children=[],
                is_behavior=is_behavior,
            )
            if is_behavior:
                behavior.append(row)
            else:
                files.append(row)
    return behavior + folders + files


def write_package_markers_in(scripts_dir: Path) -> None:
    """Write empty ``__init__.py`` markers into ``scripts_dir`` and every
    sub-folder beneath it (skipping ``__pycache__``).

    Called at EXPORT time against the build bundle's ``assets/scripts/``
    so the runnable output is an explicit package tree — even though the
    source kept no markers. (Modern Python resolves the imports via PEP
    420 namespace packages regardless, but explicit packages stay robust
    across odd runtime environments.) Idempotent; swallows write errors.
    """
    if not scripts_dir.is_dir():
        return
    folders = [scripts_dir]
    folders.extend(
        sub for sub in scripts_dir.rglob("*")
        if sub.is_dir() and "__pycache__" not in sub.parts
    )
    for folder in folders:
        init_path = folder / "__init__.py"
        if not init_path.exists():
            try:
                init_path.write_text("", encoding="utf-8")
            except OSError:
                pass


def purge_source_package_markers(
    project_file_path: str | Path | None,
) -> None:
    """Remove leftover package plumbing from the SOURCE scripts tree:
    empty (zero-byte) ``__init__.py`` files and ``__pycache__`` folders.

    The source tree no longer needs ``__init__.py`` — markers are an
    export-only concern (see ``write_package_markers_in``), and CTkMaker
    only ever AST-parses user scripts, never imports them. This cleans up
    projects created before that change so the user's OS file manager
    shows only their real scripts.

    Only zero-byte ``__init__.py`` are removed — a marker someone
    hand-edited into a real module is left untouched. ``_runtime.py``
    (the ``ref`` helper, real content) is never touched. Idempotent;
    swallows errors.
    """
    root = scripts_root(project_file_path)
    if root is None or not root.exists():
        return
    for path in list(root.rglob("*")):
        try:
            if path.is_dir() and path.name == "__pycache__":
                shutil.rmtree(path, ignore_errors=True)
            elif (
                path.is_file()
                and path.name == "__init__.py"
                and path.stat().st_size == 0
            ):
                path.unlink()
        except OSError:
            pass


def _validate_rel_path(rel_path: str) -> str | None:
    """Reject empty, absolute, or parent-escaping paths. Returns the
    normalised POSIX form on success, ``None`` on failure.
    """
    cleaned = (rel_path or "").strip().replace("\\", "/").strip("/")
    if not cleaned:
        return None
    if cleaned.startswith(".") or ".." in cleaned.split("/"):
        return None
    return cleaned


def create_library_script(
    project_file_path: str | Path | None,
    rel_path: str,
    window_names: list[str] | None = None,
) -> Path | None:
    """Create ``<page>/<rel_path>.py`` with a one-line docstring.

    ``rel_path`` is the user-typed path relative to the page folder,
    optionally including sub-folders (``"services/auth"``). The
    ``.py`` suffix is appended if missing.

    Returns the absolute path on success. Returns ``None`` when the
    project is unsaved, the path is invalid, would collide with a
    window slug at the page root, or the file already exists.
    """
    cleaned = _validate_rel_path(rel_path)
    if cleaned is None:
        return None
    if not cleaned.endswith(PY_EXT):
        cleaned = cleaned + PY_EXT
    page_dir = ensure_scripts_root(project_file_path)
    if page_dir is None:
        return None
    target = page_dir / cleaned
    if target.exists():
        return None
    # Disallow shadowing a window's behavior file at the page root.
    if "/" not in cleaned:
        window_slugs = _window_slug_set(window_names)
        if Path(cleaned).stem in window_slugs:
            return None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            (
                '"""Library script for this page.\n'
                "\n"
                "Functions defined here are imported by behaviour files via\n"
                "``from . import <module>`` or bound directly to widget events as\n"
                "``library_call`` entries from the Properties panel (public,\n"
                "top-level, sync ``def``s only).\n"
                '"""\n'
                "\n"
                "from __future__ import annotations\n"
                "\n"
                "\n"
                "def example() -> None:\n"
                '    """Replace with your own function."""\n'
                "    pass\n"
            ),
            encoding="utf-8",
        )
    except OSError:
        return None
    return target


def create_library_subpackage(
    project_file_path: str | Path | None,
    rel_path: str,
) -> Path | None:
    """Create ``<page>/<rel_path>/`` and seed it with an empty
    ``__init__.py``. ``rel_path`` may be a multi-segment path
    (``"data/models"``).
    """
    cleaned = _validate_rel_path(rel_path)
    if cleaned is None:
        return None
    page_dir = ensure_scripts_root(project_file_path)
    if page_dir is None:
        return None
    target = page_dir / cleaned
    if target.exists():
        return None
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return target


def rename_library_script(
    project_file_path: str | Path | None,
    old_rel_path: str,
    new_rel_path: str,
    window_names: list[str] | None = None,
) -> Path | None:
    """Rename a library file or folder under the active page.

    Both arguments are POSIX-style relative paths. The new path may
    move the entry across sub-folders. Sub-folder parents are created
    + seeded with ``__init__.py`` as needed.

    Returns the new absolute path on success. Returns ``None`` for
    invalid inputs, missing source, collision with a window slug, or
    write failure.
    """
    page_dir = page_scripts_dir(project_file_path)
    if page_dir is None or not page_dir.exists():
        return None
    cleaned_old = _validate_rel_path(old_rel_path)
    cleaned_new = _validate_rel_path(new_rel_path)
    if cleaned_old is None or cleaned_new is None:
        return None
    src = page_dir / cleaned_old
    if not src.exists():
        return None
    # Files get the .py suffix auto-appended; folders do not.
    if src.is_file() and not cleaned_new.endswith(PY_EXT):
        cleaned_new = cleaned_new + PY_EXT
    dst = page_dir / cleaned_new
    if dst.exists():
        return None
    if src.is_file() and "/" not in cleaned_new:
        window_slugs = _window_slug_set(window_names)
        if Path(cleaned_new).stem in window_slugs:
            return None
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    except OSError:
        return None
    return dst


def recycle_library_script(
    project_file_path: str | Path | None,
    rel_path: str,
) -> bool:
    """Send ``<page>/<rel_path>`` to the OS recycle bin via
    Send2Trash. Returns ``True`` on success, ``False`` otherwise
    (missing file, send2trash failure, unsaved project).
    """
    page_dir = page_scripts_dir(project_file_path)
    if page_dir is None or not page_dir.exists():
        return False
    cleaned = _validate_rel_path(rel_path)
    if cleaned is None:
        return False
    target = page_dir / cleaned
    if not target.exists():
        return False
    try:
        import send2trash
        send2trash.send2trash(str(target))
        return True
    except (OSError, ImportError):
        return False


def script_absolute_path(
    project_file_path: str | Path | None,
    rel_path: str,
) -> Path | None:
    """Resolve a panel-row relative path to an absolute path on disk.
    Returns ``None`` when the project is unsaved, the path is
    invalid, or the file doesn't exist.
    """
    page_dir = page_scripts_dir(project_file_path)
    if page_dir is None:
        return None
    cleaned = _validate_rel_path(rel_path)
    if cleaned is None:
        return None
    target = page_dir / cleaned
    if not target.exists():
        return None
    return target


__all__ = [
    "LibraryEntry",
    "list_library_scripts",
    "create_library_script",
    "create_library_subpackage",
    "rename_library_script",
    "recycle_library_script",
    "script_absolute_path",
]
