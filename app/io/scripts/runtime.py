"""Auto-generated ``assets/scripts/_runtime.py`` — the ``ref`` marker
class that behavior-file annotations reference.

Lives at the package root (alongside per-page subfolders) so any
behavior file can import via ``from .._runtime import ref``.
"""

from __future__ import annotations

from pathlib import Path

from app.core.script_paths import ensure_scripts_root, scripts_root


_RUNTIME_MODULE_NAME = "_runtime.py"
_RUNTIME_TEMPLATE = '''"""CTkMaker behavior-runtime helpers — auto-generated, do not edit.

The ``ref`` marker lets behavior files declare Inspector-bindable widget
slots (``name: ref[CTkLabel]``) without a CTkMaker install. CTkMaker turns
each annotation into a widget picker in the Properties panel; the exported
app assigns the real widget at runtime.
"""
from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class ref(Generic[T]):
    """Inspector-bindable widget reference marker (no runtime behavior).

    The annotation name must match its Object Reference name verbatim — a
    mismatch leaves ``self.<name>`` unbound and raises ``AttributeError`` on
    first access. CTkMaker keeps both sides in sync from the GUI; a hand-edit
    is caught by the export-time validator.
    """

    pass
'''


def ensure_runtime_helpers(
    project_file_path: str | Path | None,
) -> Path | None:
    """Write ``<project>/assets/scripts/_runtime.py`` if missing.
    Idempotent — does not overwrite an existing file (so user edits
    survive even though the docstring warns otherwise; a future
    "regenerate runtime" command can clobber explicitly). Returns
    the runtime-file path on success, ``None`` for unsaved projects
    or write failures.
    """
    if not project_file_path:
        return None
    # Run ensure_scripts_root() to create the ``scripts/<page>/`` folder
    # structure; its return value is the per-page subfolder, which is the
    # wrong level for ``_runtime.py`` — drop the helper at the parent
    # root so behavior files' ``from .._runtime import ref`` resolves.
    # Package ``__init__.py`` markers are NOT written to source; they're
    # generated into the build at export time (write_package_markers_in).
    if ensure_scripts_root(project_file_path) is None:
        return None
    root = scripts_root(project_file_path)
    if root is None:
        return None
    runtime_path = root / _RUNTIME_MODULE_NAME
    if runtime_path.exists():
        return runtime_path
    try:
        runtime_path.write_text(_RUNTIME_TEMPLATE, encoding="utf-8")
    except OSError:
        return None
    return runtime_path
