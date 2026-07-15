"""Click-triggered help popup + a small ``?`` trigger icon.

Unlike the Properties-panel hover ``PropertyTooltip``, this is a
*click* affordance for dialog fields that need more than a one-line
hint: the ``?`` icon sits next to a control, and clicking it opens a
small dark borderless window with a bold title + a full plain-language
explanation. Dismisses on:

    - ``Escape``
    - the ``✕`` close label
    - focus leaving the popup (click elsewhere)
    - clicking the same ``?`` again (the open call closes any prior one)

Only one popup is ever open at a time (module-level ``_current``).
Styling reuses the tooltip palette so it reads as the same family as
the Properties-panel tips.
"""

from __future__ import annotations

import tkinter as tk

import app.ui.stk as stk
from app.core.screen import get_screen_size
from app.ui.properties_panel.constants import (
    TOOLTIP_BG,
    TOOLTIP_BORDER,
    TOOLTIP_FG,
)
from app.ui.system_fonts import ui_font

# Accent used for the ``?`` trigger + the popup title — matches the
# "Recommended" block accent in the Settings dialog so the help
# affordances read as one system.
_ACCENT = "#7dd3fc"
_ACCENT_HOVER = "#bae6fd"
_POPUP_WRAPLENGTH = 360

# Single live popup — opening a new one (or a second click) retires
# whatever was showing so we never stack windows.
_current: tk.Toplevel | None = None


def _close_current() -> None:
    global _current
    if _current is not None:
        try:
            _current.destroy()
        except tk.TclError:
            pass
        _current = None


def make_help_icon(
    parent: tk.Misc,
    title: str,
    body: str,
) -> stk.Label:
    """Return an unpacked ``?`` label that opens a help popup on click.

    Caller packs/grids the returned widget — mirrors the dialog's
    ``_section_label`` / ``_hint`` convention.
    """
    icon = stk.Label(
        parent,
        text="?",
        bg=parent["bg"],
        fg=_ACCENT,
        font=ui_font(10, "bold"),
        cursor="hand2",
        width=2,
    )
    icon.bind("<Enter>", lambda _e: icon.configure(fg=_ACCENT_HOVER))
    icon.bind("<Leave>", lambda _e: icon.configure(fg=_ACCENT))
    icon.bind("<Button-1>", lambda _e: _show(icon, title, body))
    return icon


def _show(anchor: tk.Widget, title: str, body: str) -> None:
    global _current
    _close_current()

    tip = tk.Toplevel(anchor)
    tip.withdraw()
    tip.overrideredirect(True)
    try:
        tip.attributes("-topmost", True)
    except tk.TclError:
        pass

    outer = stk.Frame(tip, bg=TOOLTIP_BORDER, padx=1, pady=1)
    outer.pack()
    inner = stk.Frame(outer, bg=TOOLTIP_BG, padx=12, pady=10)
    inner.pack()

    header = stk.Frame(inner, bg=TOOLTIP_BG)
    header.pack(fill="x", anchor="w")
    stk.Label(
        header,
        text=title,
        bg=TOOLTIP_BG,
        fg=_ACCENT,
        font=ui_font(11, "bold"),
        anchor="w",
    ).pack(side="left")
    close = stk.Label(
        header,
        text="✕",
        bg=TOOLTIP_BG,
        fg=TOOLTIP_FG,
        font=ui_font(10, "bold"),
        cursor="hand2",
        padx=6,
    )
    close.pack(side="right")
    close.bind("<Button-1>", lambda _e: _close_current())

    stk.Label(
        inner,
        text=body,
        bg=TOOLTIP_BG,
        fg=TOOLTIP_FG,
        font=ui_font(10),
        justify="left",
        wraplength=_POPUP_WRAPLENGTH,
    ).pack(anchor="w", pady=(6, 0))

    # Rough position first (just below the icon), then clamp to the
    # screen after_idle so we don't pump the event loop mid-build —
    # matches the Toplevel race-condition guidance the tooltip follows.
    x = anchor.winfo_rootx()
    y = anchor.winfo_rooty() + anchor.winfo_height() + 6
    tip.geometry(f"+{x}+{y}")
    tip.deiconify()
    _current = tip
    tip.after_idle(lambda: _clamp_to_screen(tip, x, y))

    # Dismissal. Escape + focus-out cover keyboard + click-elsewhere;
    # the ✕ label is the always-there fallback. focus_set lets the
    # borderless window receive the Escape / FocusOut at all.
    tip.bind("<Escape>", lambda _e: _close_current())
    tip.bind("<FocusOut>", lambda _e: _close_current())
    try:
        tip.focus_set()
    except tk.TclError:
        pass


def _clamp_to_screen(tip: tk.Toplevel, x: int, y: int) -> None:
    try:
        w = tip.winfo_width()
        h = tip.winfo_height()
    except tk.TclError:
        return
    size = get_screen_size()
    if size is not None:
        sw, sh = size
    else:
        try:
            sw = tip.winfo_screenwidth()
            sh = tip.winfo_screenheight()
        except tk.TclError:
            return
    if x + w > sw:
        x = max(0, sw - w - 4)
    if y + h > sh:
        y = max(0, y - h - 12)
    try:
        tip.geometry(f"+{x}+{y}")
    except tk.TclError:
        pass
