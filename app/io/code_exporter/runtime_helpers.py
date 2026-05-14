"""Runtime helper text for the exported `.py` file.

Each `*_lines()` function returns a list of source lines spliced into
the generated file's helper preamble. Two flavours:

- Inline runtime classes (``CircularProgress``) — read live source via
  ``inspect.getsource`` so a single edit in ``app/widgets/runtime/``
  propagates to every export.
- Hand-written helpers (``_register_project_fonts``) — string literals
  kept here because the runtime they target doesn't need a builder-side
  equivalent.
"""

from __future__ import annotations


def _circular_progress_class_lines() -> list[str]:
    """Inline the ``CircularProgress`` runtime class + its bg-resolver
    helper into generated `.py` files. The class lives in
    ``app/widgets/runtime/circular_progress.py`` for builder use; we
    read its source via ``inspect`` so a single edit propagates to
    every export. The runtime module's own ``tkinter as tk`` /
    ``customtkinter as ctk`` imports are already emitted by the
    standard import block; ``CTkScalingBaseClass`` is a deeper CTk
    internal path that the standard imports don't cover, so we emit
    it here as a sibling of the helper + class definitions.
    """
    import inspect

    from app.widgets.runtime.circular_progress import (
        CircularProgress,
        _circular_progress_resolve_bg,
    )

    lines: list[str] = [
        "from customtkinter.windows.widgets.scaling import "
        "CTkScalingBaseClass",
        "",
    ]
    lines.extend(
        inspect.getsource(_circular_progress_resolve_bg).splitlines(),
    )
    lines.append("")
    lines.append("")
    lines.extend(inspect.getsource(CircularProgress).splitlines())
    return lines


def _font_register_helper_lines() -> list[str]:
    """Emit a module-level helper that loads every ``.ttf`` / ``.otf``
    sitting in ``assets/fonts/`` next to the script via tkextrafont
    so ``CTkFont(family=...)`` resolves the bundled families. Soft
    dependency — if tkextrafont isn't installed, the helper logs and
    falls back to Tk defaults so the rest of the app still runs.
    """
    return [
        "def _register_project_fonts(root):",
        '    """Load every .ttf / .otf in assets/fonts/ next to this',
        "    script so widget CTkFont(family=...) lookups can find",
        '    families bundled with the project."""',
        "    from pathlib import Path",
        '    fonts_dir = Path(__file__).resolve().parent / "assets" / "fonts"',
        "    if not fonts_dir.exists():",
        "        return",
        "    try:",
        "        from tkextrafont import Font",
        "    except ImportError:",
        "        # tkextrafont missing — bundled fonts won't load, but",
        "        # system / Tk-default fonts still render.",
        "        return",
        '    for f in sorted(fonts_dir.iterdir()):',
        '        if f.suffix.lower() in (".ttf", ".otf", ".ttc"):',
        "            try:",
        "                Font(root, file=str(f))",
        "            except Exception:",
        "                pass",
    ]
