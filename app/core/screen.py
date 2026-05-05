"""Cached primary-monitor screen / work-area info.

Computed once on first access and reused — monitor configuration
rarely changes mid-session, and recomputing per dialog (especially
via ``update_idletasks`` + Tk geometry queries) adds visible lag to
window opens.

Returns physical-pixel coordinates that match what Tk's ``geometry()``
expects (the app runs DPI-aware via ``SetProcessDpiAwareness(1)``).

Use ``get_work_area()`` for centering — it excludes the taskbar so
windows don't overlap it. ``get_screen_size()`` for raw screen pixels.
"""
from __future__ import annotations

import sys

_work_area: tuple[int, int, int, int] | None = None
_screen_size: tuple[int, int] | None = None
_computed: bool = False


def _compute() -> None:
    global _work_area, _screen_size, _computed
    _computed = True
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class _RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG),
            ]
        rect = _RECT()
        # SPI_GETWORKAREA = 0x0030
        if ctypes.windll.user32.SystemParametersInfoW(
            0x0030, 0, ctypes.byref(rect), 0,
        ):
            _work_area = (rect.left, rect.top, rect.right, rect.bottom)
        # SM_CXSCREEN = 0, SM_CYSCREEN = 1 — primary monitor pixel size.
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)
        if sw > 0 and sh > 0:
            _screen_size = (sw, sh)
    except Exception:
        pass


def get_work_area() -> tuple[int, int, int, int] | None:
    """Primary monitor's work area as (left, top, right, bottom).
    Excludes the taskbar. Returns None on non-Windows or on failure
    — callers should fall back to ``winfo_screenwidth/height``.
    """
    if not _computed:
        _compute()
    return _work_area


def get_screen_size() -> tuple[int, int] | None:
    """Primary monitor's full pixel size as (width, height). Returns
    None on non-Windows or on failure.
    """
    if not _computed:
        _compute()
    return _screen_size


def center_geometry(w: int, h: int) -> str | None:
    """Compute a Tk geometry string ``"WxH+X+Y"`` that centers a
    window of size ``w × h`` within the work area. Returns None when
    the work area isn't available — caller should use Tk-side info.
    """
    rect = get_work_area()
    if rect is None:
        return None
    left, top, right, bottom = rect
    wa_w = right - left
    wa_h = bottom - top
    x = left + max(0, (wa_w - w) // 2)
    y = top + max(0, (wa_h - h) // 2)
    return f"{w}x{h}+{x}+{y}"
