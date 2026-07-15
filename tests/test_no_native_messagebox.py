"""Guard: native tkinter message/simple dialogs are banned under app/.

Native ``tkinter.messagebox`` / ``simpledialog`` windows are drawn by
the OS with the light theme, so they can never match the app's dark
style. Every user-facing message box must go through the
``app.ui.dialogs.message`` wrappers instead.

Whitelist:

- ``app/ui/dialogs/message.py`` — the wrapper module itself (owns the
  native fallback path).
- ``app/ui/crash_dialog.py`` — deliberate exception: at crash time CTk
  may itself be broken, so the last-resort error box stays native.
"""

from __future__ import annotations

import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"

ALLOWED = {
    Path("ui") / "dialogs" / "message.py",
    Path("ui") / "crash_dialog.py",
}

# Call sites only — prose mentions in docstrings don't have the paren.
NATIVE_CALL = re.compile(r"\b(?:messagebox|simpledialog)\.\w+\(")


def test_no_native_messagebox_calls() -> None:
    offenders: list[str] = []
    for path in sorted(APP_DIR.rglob("*.py")):
        rel = path.relative_to(APP_DIR)
        if rel in ALLOWED:
            continue
        text = path.read_text(encoding="utf-8")
        for match in NATIVE_CALL.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"app/{rel.as_posix()}:{line} {match.group(0)}")
    assert not offenders, (
        "Native tkinter dialogs found — use the app.ui.dialogs.message "
        "wrappers (show_info / show_error / ask_yes_no / ...) instead:\n"
        + "\n".join(offenders)
    )
