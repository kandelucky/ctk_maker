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


def prepare_dialog(toplevel: tk.Misc) -> None:
    """Hide the toplevel via alpha while __init__ builds widgets.
    Pair with ``reveal_dialog`` at the end of __init__. Otherwise
    Windows briefly paints the WM-default white BG before Tk applies
    the configured colours — a visible flash on dialog open.
    """
    try:
        toplevel.attributes("-alpha", 0.0)
    except tk.TclError:
        pass


def reveal_dialog(toplevel: tk.Misc) -> None:
    """Reveal a dialog hidden by ``prepare_dialog``. Forces a paint
    pass while still invisible, then flips alpha to 1 so the user
    only ever sees the fully-rendered window.
    """
    try:
        toplevel.update_idletasks()
    except tk.TclError:
        pass
    try:
        toplevel.attributes("-alpha", 1.0)
    except tk.TclError:
        pass
