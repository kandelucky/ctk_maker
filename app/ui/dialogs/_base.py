"""Shared ``CTkToplevel`` base for CTkMaker's raw-tk dialogs.

These dialogs (Message / About / RenamePage / CursorAdvanced /
AmbiguousProjectPicker) build their content out of plain ``tk.Frame``
/ ``tk.Label`` / ``tk.Button`` widgets, but the *window* is a
``CTkToplevel`` so the fork's dark-titlebar persistence applies — no
``dark_titlebar.py`` monkey-patch needed.

``DarkDialog`` centralizes the three things every one of them needs:

* ``fg_color`` setup — ``CTkToplevel`` owns its background via
  ``_fg_color``; a raw ``configure(bg=...)`` is not a valid kwarg.
* real-pixel geometry — ``CTkToplevel.geometry()`` applies window
  scaling, but the raw-tk content does *not* scale with CTk's scaling
  system. Feeding scaled geometry to unscaled content mismatches on
  any non-100% display, so ``place_centered`` deliberately bypasses
  the CTk layer and positions in real pixels.
* the ``prepare_dialog`` / ``reveal_dialog`` alpha-hide pair.
"""

from __future__ import annotations

import tkinter

import customtkinter as ctk

from app.ui.dialog_utils import (
    prepare_dialog,
    reveal_dialog,
    screen_work_area,
)
from app.ui.dialogs._colors import _ABT_BG, dialog_scaling


class DarkDialog(ctk.CTkToplevel):
    """``CTkToplevel`` base for the raw-tk dialog family.

    Subclasses build their widgets, then call ``place_centered`` and
    ``reveal``.
    """

    def __init__(self, parent, *, fg_color: str = _ABT_BG) -> None:
        super().__init__(parent, fg_color=fg_color)
        # Hide via alpha while __init__ builds widgets — otherwise
        # Windows briefly paints the WM-default background.
        prepare_dialog(self)
        self.resizable(False, False)
        self.transient(parent)

    def place_centered(self, width: int, height: int, parent) -> None:
        """Center the dialog over ``parent``'s toplevel using REAL pixels.

        Bypasses ``CTkToplevel.geometry`` (and its window-scaling pass)
        because the dialog content is raw tk and is not CTk-scaled.
        ``parent`` may be any widget (call sites pass docked panels) —
        centering targets the owning window, and the result is clamped
        to the monitor's work area so no edge ends up off-screen.
        """
        owner = parent.winfo_toplevel()
        x = owner.winfo_rootx() + (owner.winfo_width() - width) // 2
        y = owner.winfo_rooty() + (owner.winfo_height() - height) // 2
        area = screen_work_area(owner)
        if area is not None:
            ax, ay, aw, ah = area
            edge = round(8 * dialog_scaling(self))
            x = min(max(x, ax + edge), max(ax + edge, ax + aw - width - edge))
            y = min(max(y, ay + edge), max(ay + edge, ay + ah - height - edge))
        tkinter.Toplevel.geometry(self, f"{width}x{height}+{x}+{y}")

    def invoke_focused_or(self, default) -> None:
        """Return-key semantics shared by the dialog family: activate
        the Tab-focused button when there is one, otherwise run
        ``default()``. Without this, Tab to Cancel + Enter would fire
        the affirmative (possibly destructive) default instead of the
        focused button.
        """
        try:
            focused = self.focus_get()
        except (KeyError, tkinter.TclError):
            # focus_get raises for foreign/unresolvable widget paths
            focused = None
        if isinstance(focused, tkinter.Button):
            focused.invoke()
            return
        default()

    def reveal(self) -> None:
        """Flip alpha back to 1 once the window is fully built."""
        reveal_dialog(self)
