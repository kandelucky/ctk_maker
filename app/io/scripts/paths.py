"""Create a new CTkScript file in the project's top-level ``scripts/``
folder. Pure I/O — no Tk, no behavior-file machinery.
"""

from __future__ import annotations

import re
from pathlib import Path

# Skeleton for a brand-new CTkScript file created from the attach
# picker's "New script…". Plain string (``{class_name}`` filled via
# ``.format`` at call time). Imports the base from ``ctkmaker`` — the
# project scaffold writes ``ctkmaker.py`` at the project root and the
# exporter ships the same file beside the build, so this resolves
# self-contained both while editing and in exports.
_CTKSCRIPT_SKELETON = '''from __future__ import annotations

import tkinter as tk

from ctkmaker import CTkScript


class {class_name}(CTkScript):
    # Exposed fields — uncomment, then set the value in the Properties panel:
    # score: tk.IntVar

    def on_start(self):
        # Runs once after the object is built. self.widget / self.window
        # is the object this script is attached to.
        pass
'''


def class_name_to_filename(class_name: str) -> str:
    """``ClickCounter`` → ``click_counter``; non-identifier chars
    collapse to underscores. Falls back to ``script``."""
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s).strip("_")
    return s or "script"


def normalize_class_name(raw: str) -> str:
    """Normalize any input style to a PascalCase class name:
    ``foo_bar`` / ``foo bar`` / ``fooBar`` / ``FooBar`` → ``FooBar``;
    acronym runs survive (``HTTP server`` → ``HTTPServer``). Returns
    ``""`` when nothing identifier-like remains (e.g. digits/symbols
    only)."""
    words: list[str] = []
    for part in re.split(r"[^0-9a-zA-Z]+", raw.strip()):
        words.extend(re.findall(
            r"[A-Z]+(?=[A-Z][a-z])|[A-Z][a-z0-9]*|[a-z0-9]+", part,
        ))
    name = "".join(w[:1].upper() + w[1:] for w in words)
    name = re.sub(r"^[0-9]+", "", name)
    name = name[:1].upper() + name[1:]
    return name if name.isidentifier() else ""


def create_user_script(
    scripts_dir: str | Path | None, class_name: str,
) -> tuple[str, str] | None:
    """Create ``<scripts_dir>/<snake>.py`` with a CTkScript skeleton for
    ``class_name``. Returns ``(rel_filename, class_name)`` or ``None``
    (unsaved project / invalid name / write error). The filename
    auto-suffixes (``_2`` / ``_3``) so an existing file is never
    clobbered.
    """
    if not scripts_dir or not class_name or not class_name.isidentifier():
        return None
    root = Path(scripts_dir)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    stem = class_name_to_filename(class_name)
    fname = f"{stem}.py"
    n = 2
    while (root / fname).exists():
        fname = f"{stem}_{n}.py"
        n += 1
    try:
        (root / fname).write_text(
            _CTKSCRIPT_SKELETON.format(class_name=class_name),
            encoding="utf-8",
        )
    except OSError:
        return None
    return (fname, class_name)
