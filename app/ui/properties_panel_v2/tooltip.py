"""Dark hover tooltip for the Properties panel label column.

A single ``PropertyTooltip`` instance per panel manages one Toplevel
that's destroyed and recreated per row hover. The widget is shown
``TOOLTIP_DELAY_MS`` after the cursor settles on a row and reused as
the cursor moves between rows that share the same key (debounced).

Hides on:
    - cursor leaving the tree
    - mouse wheel / scroll
    - any click
    - moving to a row without a help entry
"""

from __future__ import annotations

import tkinter as tk

from app.core.screen import get_screen_size

from .constants import (
    TOOLTIP_BG,
    TOOLTIP_BORDER,
    TOOLTIP_DELAY_MS,
    TOOLTIP_FG,
    TOOLTIP_WARNING_FG,
    TOOLTIP_WRAPLENGTH,
)


class PropertyTooltip:
    """Manages a single dark-themed tooltip Toplevel for a Treeview."""

    def __init__(self, master: tk.Widget) -> None:
        self.master = master
        self._tip: tk.Toplevel | None = None
        self._after_id: str | None = None
        self._current_key: str | None = None

    def schedule(
        self,
        x_root: int,
        y_root: int,
        description: str,
        warning: str | None = None,
        key: str | None = None,
    ) -> None:
        """Schedule a tooltip to appear after the standard delay.

        If ``key`` matches the currently-shown tooltip, this is a no-op
        — keeps the tooltip stable as the cursor moves over the same
        row's label area.
        """
        if key is not None and key == self._current_key and self._tip:
            return
        self.cancel()
        self._after_id = self.master.after(
            TOOLTIP_DELAY_MS,
            lambda: self._show(x_root, y_root, description, warning, key),
        )

    def cancel(self) -> None:
        """Cancel any pending show + hide an existing tooltip."""
        if self._after_id is not None:
            try:
                self.master.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        self._hide()

    def _show(
        self,
        x_root: int,
        y_root: int,
        description: str,
        warning: str | None,
        key: str | None,
    ) -> None:
        self._after_id = None
        self._hide()

        tip = tk.Toplevel(self.master)
        tip.withdraw()
        tip.overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass

        outer = tk.Frame(tip, bg=TOOLTIP_BORDER, padx=1, pady=1)
        outer.pack()
        inner = tk.Frame(outer, bg=TOOLTIP_BG, padx=8, pady=6)
        inner.pack()

        tk.Label(
            inner,
            text=description,
            bg=TOOLTIP_BG,
            fg=TOOLTIP_FG,
            font=("Segoe UI", 9),
            justify="left",
            wraplength=TOOLTIP_WRAPLENGTH,
        ).pack(anchor="w")

        if warning:
            tk.Label(
                inner,
                text=f"⚠  {warning}",
                bg=TOOLTIP_BG,
                fg=TOOLTIP_WARNING_FG,
                font=("Segoe UI", 9),
                justify="left",
                wraplength=TOOLTIP_WRAPLENGTH,
            ).pack(anchor="w", pady=(4, 0))

        # Rough position first; defer screen-edge clamp to after_idle so
        # we don't pump the event loop in __init__ (matches the
        # Toplevel race-condition guidance in feedback memory).
        tip.geometry(f"+{x_root + 16}+{y_root + 18}")
        tip.deiconify()
        self._tip = tip
        self._current_key = key
        tip.after_idle(lambda: self._clamp_to_screen(tip, x_root, y_root))

    @staticmethod
    def _clamp_to_screen(
        tip: tk.Toplevel, x_root: int, y_root: int,
    ) -> None:
        try:
            w = tip.winfo_width()
            h = tip.winfo_height()
        except tk.TclError:
            return
        # Cached primary-monitor size from screen.py — physical pixels,
        # populated once at startup. Falls back to Tk's screen-info on
        # non-Windows / lookup failure.
        size = get_screen_size()
        if size is not None:
            sw, sh = size
        else:
            try:
                sw = tip.winfo_screenwidth()
                sh = tip.winfo_screenheight()
            except tk.TclError:
                return
        x = x_root + 16
        y = y_root + 18
        if x + w > sw:
            x = max(0, sw - w - 4)
        if y + h > sh:
            y = max(0, y_root - h - 8)
        try:
            tip.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def _hide(self) -> None:
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None
        self._current_key = None
