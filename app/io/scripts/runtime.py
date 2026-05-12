"""Auto-generated ``assets/scripts/_runtime.py`` — the ``ref`` marker
class that behavior-file annotations reference.

Lives at the package root (alongside per-page subfolders) so any
behavior file can import via ``from .._runtime import ref``.
"""

from __future__ import annotations

from pathlib import Path

from app.core.script_paths import ensure_scripts_root, scripts_root


_RUNTIME_MODULE_NAME = "_runtime.py"
_RUNTIME_TEMPLATE = '''"""CTkMaker behavior-runtime helpers — auto-generated.

The ``ref`` marker lets behavior files declare Inspector-bindable
attributes without forcing a CTkMaker package install. CTkMaker
detects ``<name>: ref[<WidgetType>]`` annotations at parse time and
exposes them as widget picker slots in the Properties panel; the
exported app then assigns the real widget to each slot at runtime.

Edits to this file are overwritten when CTkMaker regenerates it.
"""
from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class ref(Generic[T]):
    """Inspector-bindable widget reference marker.

    Has no runtime behavior on its own — annotations of the form
    ``target: ref[CTkLabel]`` are resolved by the exporter into
    ``self._behavior.target = self.<widget_var>`` assignments after
    the UI is built.

    Name match is verbatim: the annotation name must equal the
    Properties-panel Object Reference name exactly. ``counter_label``
    and ``counter_label_ref`` are two different slots — typoing one
    side means ``self.<annotation_name>`` stays unbound and the first
    access raises ``AttributeError``. CTkMaker keeps the two in sync
    when you create / rename / delete refs in the GUI; if you edit
    this file by hand, an export-time validator warns before runtime
    hits the mismatch.
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
    # Run ensure_scripts_root() for the side effect of creating the
    # __init__.py at both ``scripts/`` and ``scripts/<page>/`` so the
    # ``from assets.scripts.<page>.<window>`` import resolves; its
    # return value is the per-page subfolder, which is the wrong
    # level for ``_runtime.py``. Drop the helper at the parent root
    # so behavior files' ``from .._runtime import ref`` resolves.
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
