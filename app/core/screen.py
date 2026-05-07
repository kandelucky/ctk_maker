"""DPI factor + cached primary-monitor screen / work-area info.

The single source of truth for OS display metadata. CTk activates
DPI awareness itself when ``ctk.CTk`` is instantiated, so we don't
re-do that — we just read the resulting OS DPI here and let
``ZoomController`` mirror CTk's widget scaling on the canvas.

DPI factor + screen geometry are cached; monitor configuration
rarely changes mid-session, and recomputing per dialog (via
``update_idletasks`` + Tk geometry queries) adds visible lag to
window opens.

``get_dpi_factor()`` returns the OS scaling multiplier
(1.0 / 1.25 / 1.5 / …). ``get_work_area()`` for centering windows
that should clear the taskbar; ``get_screen_size()`` for the raw
monitor pixel rectangle. ``center_geometry(w, h, scale)`` builds
a Tk geometry string with CTk's W/H scaling factored into the
centering math.
"""
from __future__ import annotations

import sys

_work_area: tuple[int, int, int, int] | None = None
_screen_size: tuple[int, int] | None = None
_computed: bool = False
_dpi_factor: float | None = None


def get_dpi_factor() -> float:
    """OS DPI factor as a multiplier: 96 DPI → 1.0, 125 % → 1.25,
    150 % → 1.5, etc. Cached after first call. Non-Windows returns
    1.0 since CTk's ScalingTracker only reports an OS factor on
    Windows; designer canvas drawing on macOS / Linux falls back to
    user-zoom only.
    """
    global _dpi_factor
    if _dpi_factor is not None:
        return _dpi_factor
    if sys.platform != "win32":
        _dpi_factor = 1.0
        return _dpi_factor
    try:
        import ctypes
        dpi = ctypes.windll.user32.GetDpiForSystem()
        _dpi_factor = max(1.0, dpi / 96.0)
    except Exception:
        _dpi_factor = 1.0
    return _dpi_factor


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


def center_geometry(w: int, h: int, scale: float = 1.0) -> str | None:
    """Compute a Tk geometry string ``"WxH+X+Y"`` that centers a
    window of size ``w × h`` within the work area. Returns None when
    the work area isn't available — caller should use Tk-side info.

    ``scale`` accommodates CTk's ``_apply_geometry_scaling``, which
    multiplies width/height by the window scaling factor but leaves
    x/y untouched. So the *physical* window footprint on screen is
    ``w * scale × h * scale``, while the geometry string we return
    still carries the logical ``w × h``. Passing ``scale=1.0`` (the
    default) is correct for raw tk widgets; CTk callers pass
    ``self._get_window_scaling()`` so the centering math compares
    physical-against-physical against the work-area pixels we read
    from Win32.
    """
    rect = get_work_area()
    if rect is None:
        return None
    left, top, right, bottom = rect
    physical_w = w * scale
    physical_h = h * scale
    x = int(left + max(0, ((right - left) - physical_w) // 2))
    y = int(top + max(0, ((bottom - top) - physical_h) // 2))
    return f"{w}x{h}+{x}+{y}"
