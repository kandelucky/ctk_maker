"""Behavior-file lifecycle on disk — create / rename / recycle / save.

Each per-window ``.py`` lives at
``<project>/assets/scripts/<page>/<window>.py`` and is imported by the
exported code as
``from assets.scripts.<page>.<window> import <WindowName>Page``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.core.script_paths import (
    behavior_class_name,
    behavior_file_path,
    ensure_scripts_root,
    slugify_window_name,
)
from app.io.scripts.runtime import ensure_runtime_helpers


# Skeleton template written on first handler attach (or eager on
# document creation). Plain string — no f-string at module level so
# the literal ``{class_name}`` markers stay intact for ``.format``
# at call time.
_SKELETON_TEMPLATE = '''"""Behavior file for the {window_label} window.

Methods here run in response to widget events. CTkMaker stubs new
methods automatically — fill in the bodies here. Each method maps
to a handler binding configured in the Properties panel.

To bind a widget as an Inspector slot, declare a ``ref[<WidgetType>]``
annotation on the class (e.g. ``target_label: ref[CTkLabel]``) and
add an entry with the **same name verbatim** in the Properties
panel's Object References group. CTkMaker keeps the two ends in
sync when refs are created / renamed in the GUI; renaming the
annotation by hand without updating the GUI side (or vice versa)
leaves ``self.<name>`` unbound — the next export run surfaces a
warning before the runtime hits ``AttributeError``. Import ``ref``
from the auto-generated ``_runtime`` module and the widget class
from ``customtkinter``.
"""


class {class_name}:
    def setup(self, window):
        """Called once after the UI is built and Object References
        are wired. ``self.<field>`` slots and ``window.<widget>``
        attributes are both available at this point.
        """
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
