"""Create a new CTkScript file in the project's top-level ``scripts/``
folder. Pure I/O — no Tk, no behavior-file machinery.
"""

from __future__ import annotations

import re
from pathlib import Path

# Skeleton for a brand-new CTkScript file created from the attach
# picker's "New script…". Plain string (``{class_name}`` filled via
# ``.format`` at call time). Imports the base from ``ctkmaker`` — the
# exporter ships ``ctkmaker.py`` beside the build so this resolves
# self-contained.
_CTKSCRIPT_SKELETON = '''from ctkmaker import CTkScript


class {class_name}(CTkScript):
    def on_start(self):
        """Runs once after the object is built. self.widget / self.window
        give you the object this script is attached to."""
        pass
'''


def _class_name_to_filename(class_name: str) -> str:
    """``ClickCounter`` → ``click_counter``; non-identifier chars
    collapse to underscores. Falls back to ``script``."""
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s).strip("_")
    return s or "script"


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
    stem = _class_name_to_filename(class_name)
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
