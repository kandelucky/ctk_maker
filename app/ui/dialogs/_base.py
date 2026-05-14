"""Shared ``CTkToplevel`` base for CTkMaker's raw-tk dialogs.

These dialogs (About / Confirm / Choice / RenamePage /
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

from app.ui.dialog_utils import prepare_dialog, reveal_dialog
from app.ui.dialogs._colors import _ABT_BG


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
        """Center the dialog over ``parent`` using REAL pixels.

        Bypasses ``CTkToplevel.geometry`` (and its window-scaling pass)
        because the dialog content is raw tk and is not CTk-scaled.
        """
        px = parent.winfo_rootx() + parent.winfo_width() // 2
        py = parent.winfo_rooty() + parent.winfo_height() // 2
        x = px - width // 2
        y = py - height // 2
        tkinter.Toplevel.geometry(self, f"{width}x{height}+{x}+{y}")

    def reveal(self) -> None:
        """Flip alpha back to 1 once the window is fully built."""
        reveal_dialog(self)
