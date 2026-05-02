"""Cross-platform dialog helpers."""

from __future__ import annotations

import tkinter as tk


def safe_grab_set(toplevel: tk.Misc) -> None:
    # macOS Tk-aqua silently crashes when grab_set() is called on a
    # Toplevel that hasn't been mapped yet. wait_visibility() blocks
    # until the window manager has mapped the window; after that
    # grab_set() is safe everywhere. Win/Linux Tk tolerates the wrong
    # order, Mac does not.
    try:
        toplevel.wait_visibility()
    except tk.TclError:
        pass
    try:
        toplevel.grab_set()
    except tk.TclError:
        pass
