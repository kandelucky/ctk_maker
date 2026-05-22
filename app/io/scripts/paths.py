"""Behavior-file lifecycle on disk — create / rename / recycle / save.

Each per-window ``.py`` lives at
``<project>/assets/scripts/<page>/<window>.py`` and is imported by the
exported code as
``from assets.scripts.<page>.<window> import <WindowName>Page``.
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

from app.core.script_paths import (
    behavior_class_name,
    behavior_file_path,
    ensure_scripts_root,
    page_scripts_dir,
    slugify_window_name,
)
from app.io.scripts.runtime import ensure_runtime_helpers

# Files that live in a page-scripts folder but aren't user-authored
# behavior code. Hidden from the page-delete picker and only swept
# when the page is cleared of every real ``.py``. ``_runtime.py`` is
# NOT listed because it lives in the parent scripts root (shared
# across pages), so it never appears in a per-page folder anyway.
_PLUMBING_NAMES = {"__init__.py"}


# Skeleton template written on first handler attach (or eager on
# document creation). Plain string — no f-string at module level so
# the literal ``{class_name}`` markers stay intact for ``.format``
# at call time.
_SKELETON_TEMPLATE = '''"""Behavior for the {window_label} window — fill in the method bodies below.

Each method maps to a widget event set in the Properties panel; CTkMaker
stubs new methods automatically. For an Inspector-bindable widget slot,
annotate ``name: ref[CTkLabel]`` (imported from ``_runtime``) and add a
matching Object Reference in the Properties panel.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import customtkinter as ctk
    import tkinter as tk


class {class_name}:
    def setup(self, window: "ctk.CTk | ctk.CTkToplevel") -> None:
        """Runs once after the UI is built and Object References are wired."""
        self.window = window
'''


def load_or_create_behavior_file(
    project_file_path: str | Path | None,
    document=None,
) -> Path | None:
    """Return the behavior-file path, creating the page subfolder and
    writing a class skeleton if the .py is missing. ``None`` for
    unsaved projects.

    ``document`` controls the filename + class name (per-window
    scope, Decision #13). When ``document`` is ``None`` the call is
    a no-op probe — useful for callers that just want to know
    whether the file would land in a writable location.
    """
    if not project_file_path:
        return None
    if ensure_scripts_root(project_file_path) is None:
        return None
    # Drop ``_runtime.py`` next to the per-page subfolders so Object
    # Reference annotations (``target: ref[CTkLabel]``) have an
    # importable ``ref`` marker. Idempotent: existing file is left
    # untouched. Runs on every behavior-file create so older projects
    # pick it up the first time the user adds any handler without a
    # separate migration step.
    ensure_runtime_helpers(project_file_path)
    file_path = behavior_file_path(project_file_path, document)
    if file_path is None:
        return None
    if file_path.exists():
        return file_path
    window_label = (
        getattr(document, "name", None) or "Window"
    )
    skeleton = _SKELETON_TEMPLATE.format(
        class_name=behavior_class_name(document),
        window_label=window_label,
    )
    try:
        file_path.write_text(skeleton, encoding="utf-8")
    except OSError:
        return None
    return file_path


def rename_behavior_file_and_class(
    project_file_path: str | Path | None,
    old_name: str,
    new_name: str,
) -> Path | None:
    """Phase 2 Step 3 — rename ``<page>/<old_slug>.py`` →
    ``<page>/<new_slug>.py`` and rewrite ``class <OldName>Page`` →
    ``class <NewName>Page`` inside the file. Returns the new path
    on success, ``None`` when the source file doesn't exist (legacy
    docs that never gained a behavior file) or the rename hit a
    collision / write error.

    The class rewrite uses a plain string replace against the
    expected ``class <Old>Page`` token rather than an AST round-trip
    so the user's blank lines + comments survive untouched.
    """

    class _Stub:
        def __init__(self, name: str):
            self.name = name

    old_path = behavior_file_path(project_file_path, _Stub(old_name))
    new_path = behavior_file_path(project_file_path, _Stub(new_name))
    if old_path is None or new_path is None:
        return None
    if not old_path.exists():
        return None
    if slugify_window_name(old_name) == slugify_window_name(new_name):
        # Display-name change that collapses to the same slug — no
        # rename needed, but still rewrite the class declaration so
        # the PascalCase identifier matches the user's intent.
        try:
            source = old_path.read_text(encoding="utf-8")
        except OSError:
            return None
        old_class = behavior_class_name(_Stub(old_name))
        new_class = behavior_class_name(_Stub(new_name))
        if old_class != new_class:
            updated = source.replace(
                f"class {old_class}", f"class {new_class}", 1,
            )
            try:
                old_path.write_text(updated, encoding="utf-8")
            except OSError:
                return None
        return old_path
    if new_path.exists():
        # Target slug already in use — refuse to clobber the
        # collision. The caller surfaces this as a no-op; the user
        # ends up with two files until they manually reconcile.
        return None
    try:
        source = old_path.read_text(encoding="utf-8")
    except OSError:
        return None
    old_class = behavior_class_name(_Stub(old_name))
    new_class = behavior_class_name(_Stub(new_name))
    updated = source.replace(
        f"class {old_class}", f"class {new_class}", 1,
    )
    try:
        new_path.write_text(updated, encoding="utf-8")
        old_path.unlink()
    except OSError:
        return None
    return new_path


def recycle_behavior_file(
    project_file_path: str | Path | None,
    doc_name: str,
) -> bool:
    """Send ``<page>/<window>.py`` to the OS recycle bin (Phase 2
    Step 3 default). Returns ``True`` on success, ``False`` when
    the file doesn't exist or send2trash fails — caller surfaces
    the failure as a toast so the window deletion can still
    proceed (orphan files clean up via "Save copy" path next time).
    """

    class _Stub:
        def __init__(self, name: str):
            self.name = name

    src = behavior_file_path(project_file_path, _Stub(doc_name))
    if src is None or not src.exists():
        return False
    try:
        # send2trash is a tiny pure-Python module — Windows uses
        # IFileOperation, macOS uses Foundation, Linux walks the
        # XDG trash spec. Cross-platform recovery without the user
        # opening a "Restore" dialog inside the builder.
        import send2trash
        send2trash.send2trash(str(src))
        return True
    except (OSError, ImportError):
        return False


def save_behavior_file_copy(
    project_file_path: str | Path | None,
    doc_name: str,
    target_path: str | Path,
) -> Path | None:
    """Move ``<page>/<window>.py`` to ``target_path`` (typically
    inside ``<project>/assets/scripts_archive/``), auto-suffixing
    ``_2`` / ``_3`` on filename collision. Returns the archived
    path or ``None`` when the source file doesn't exist or the
    move failed. The original file is removed — this is a "save
    + delete" round-trip, not a copy — so the active scripts
    folder stays clean.
    """

    class _Stub:
        def __init__(self, name: str):
            self.name = name

    src = behavior_file_path(project_file_path, _Stub(doc_name))
    if src is None or not src.exists():
        return None
    dst = Path(target_path)
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    final = dst
    if final.exists():
        base = dst.stem
        suffix = dst.suffix
        n = 2
        candidate = dst.with_name(f"{base}_{n}{suffix}")
        while candidate.exists():
            n += 1
            candidate = dst.with_name(f"{base}_{n}{suffix}")
        final = candidate
    try:
        shutil.move(str(src), str(final))
    except OSError:
        return None
    return final


def _count_script(path: Path) -> tuple[int, int]:
    """``(method_count, line_count)`` for a behavior file. Method count
    is every ``def`` / ``async def`` in the module (class methods +
    module functions) — a rough "how much is in here" figure for the
    delete picker, not a precise handler tally. Both degrade
    gracefully: an unreadable file is ``(0, 0)``; a syntactically
    broken one still reports its line count.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return (0, 0)
    line_count = len(source.splitlines())
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return (0, line_count)
    method_count = sum(
        1 for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    return (method_count, line_count)


def list_page_scripts(
    page_file_path: str | Path | None,
) -> list[tuple[str, int, int]]:
    """Return ``[(filename, method_count, line_count)]`` for every
    user-authored ``.py`` in the page's ``assets/scripts/<page>/``
    folder, sorted by name. Plumbing (``__init__.py``, ``__pycache__``)
    is skipped, and ``_runtime.py`` never appears (it lives in the
    parent scripts root, shared across pages). Empty list when the
    folder is absent or the project is unsaved.

    ``page_file_path`` is the page's ``.ctkproj`` path — its stem maps
    to the folder name via the same rule the exporter uses, so a page
    whose folder was renamed still resolves correctly.
    """
    page_dir = page_scripts_dir(page_file_path)
    if page_dir is None or not page_dir.is_dir():
        return []
    out: list[tuple[str, int, int]] = []
    for entry in sorted(page_dir.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_file() or entry.suffix != ".py":
            continue
        if entry.name in _PLUMBING_NAMES:
            continue
        methods, lines = _count_script(entry)
        out.append((entry.name, methods, lines))
    return out


def recycle_page_scripts(
    page_file_path: str | Path | None,
    selected_filenames,
) -> int:
    """Send the named ``.py`` files in the page's scripts folder to the
    OS recycle bin. After the selected files are gone, if no real
    ``.py`` remain the leftover plumbing (``__init__.py``,
    ``__pycache__``) and the now-empty page folder are recycled too, so
    a fully-cleared page leaves nothing behind. Files the user left
    unchecked stay put — the folder is kept for them.

    Never touches ``_runtime.py`` (parent scripts root, shared).
    Returns the count of user scripts recycled. Best-effort: a missing
    ``send2trash`` or per-file ``OSError`` is swallowed so the page
    deletion can still proceed.
    """
    page_dir = page_scripts_dir(page_file_path)
    if page_dir is None or not page_dir.is_dir():
        return 0
    try:
        import send2trash
    except ImportError:
        return 0

    recycled = 0
    for name in set(selected_filenames or ()):
        if name in _PLUMBING_NAMES:
            continue  # never offered in the picker; defensive
        target = page_dir / name
        # Only dispose direct children — guards against a crafted name
        # with separators / ".." escaping the page folder.
        if target.parent != page_dir or not target.is_file():
            continue
        try:
            send2trash.send2trash(str(target))
            recycled += 1
        except OSError:
            pass

    # Folder sweep — only when nothing user-authored is left.
    remaining = [
        p for p in page_dir.iterdir()
        if p.is_file()
        and p.suffix == ".py"
        and p.name not in _PLUMBING_NAMES
    ]
    if not remaining:
        try:
            send2trash.send2trash(str(page_dir))
        except OSError:
            pass
    return recycled
