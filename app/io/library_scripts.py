"""Export-time package markers for the build's copied ``scripts/`` tree.

The builder keeps the source scripts tree free of ``__init__.py``
markers — CTkMaker only AST-parses user scripts, never imports them.
At export time, though, the runnable bundle wants explicit packages so
``from scripts.<module> import <Class>`` resolves on any Python.
``write_package_markers_in`` seeds those markers into the build
output. Pure I/O: no UI, no Tk.
"""

from __future__ import annotations

from pathlib import Path


def write_package_markers_in(scripts_dir: Path) -> None:
    """Write empty ``__init__.py`` markers into ``scripts_dir`` and every
    sub-folder beneath it (skipping ``__pycache__``).

    Called at EXPORT time against the build bundle's copied ``scripts/``
    folder so the runnable output is an explicit package tree — even
    though the source kept no markers. (Modern Python resolves the imports via PEP
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


__all__ = ["write_package_markers_in"]
