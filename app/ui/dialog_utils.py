"""Cross-platform dialog helpers."""

from __future__ import annotations

import sys
import tkinter as tk


def screen_work_area(toplevel: tk.Misc) -> tuple[int, int, int, int] | None:
    """``(x, y, w, h)`` of the usable desktop area, in REAL pixels, of
    the monitor hosting ``toplevel``'s window. ``None`` when it can't
    be determined (caller should skip clamping).

    Under CTk's per-monitor DPI awareness Tk's ``winfo_screenwidth`` /
    ``winfo_screenheight`` return DPI-virtualized (logical) values —
    physically wrong on any non-100% display — and know nothing about
    the taskbar. On Windows ask the OS for the hosting monitor's work
    area instead; elsewhere fall back to the Tk numbers.
    """
    if sys.platform == "win32":
        try:
            import ctypes

            class _RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long),
                ]

            class _MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_ulong),
                    ("rcMonitor", _RECT),
                    ("rcWork", _RECT),
                    ("dwFlags", ctypes.c_ulong),
                ]

            user32 = ctypes.windll.user32
            MONITOR_DEFAULTTONEAREST = 2
            monitor = user32.MonitorFromWindow(
                toplevel.winfo_id(), MONITOR_DEFAULTTONEAREST,
            )
            info = _MONITORINFO()
            info.cbSize = ctypes.sizeof(_MONITORINFO)
            if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                work = info.rcWork
                return (
                    work.left, work.top,
                    work.right - work.left, work.bottom - work.top,
                )
        except (OSError, tk.TclError, AttributeError):
            pass
    try:
        return (
            0, 0,
            toplevel.winfo_screenwidth(), toplevel.winfo_screenheight(),
        )
    except tk.TclError:
        return None


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
