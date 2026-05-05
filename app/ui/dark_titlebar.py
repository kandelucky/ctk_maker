"""Keep the Windows 11 dark titlebar applied across focus / map events.

CustomTkinter sets ``DWMWA_USE_IMMERSIVE_DARK_MODE`` once at window
init. Windows invalidates the DWM non-client cache on common events
— another window covering/uncovering the area, focus changes,
maximize/restore — and the titlebar reverts to the system light
style. We re-set the attribute on ``<Map>`` and ``<FocusIn>``, and
force one ``SetWindowPos(SWP_FRAMECHANGED)`` per window lifetime so
the very first paint is dark (no light flash on open).

Idempotent. No-op on non-Windows platforms.
"""
from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from ctypes import wintypes

# Windows 10 build 19041+ uses 20; older builds (1809–1909) use 19.
# Try the modern one first; fall back if the kernel rejects it.
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19

# SetWindowPos flags — used to force a non-client repaint after the
# DWM attribute is set. Without SWP_FRAMECHANGED, Windows defers the
# titlebar redraw until the next NC event (move / focus / activate),
# so the user sees a flash of the system-light titlebar on open.
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020
_SWP_NOOWNERZORDER = 0x0200


def _hwnd_for(window) -> int:
    try:
        return ctypes.windll.user32.GetParent(window.winfo_id())
    except Exception:
        return 0


def _force_nc_repaint(hwnd: int) -> None:
    flags = (
        _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER
        | _SWP_NOACTIVATE | _SWP_NOOWNERZORDER | _SWP_FRAMECHANGED
    )
    try:
        ctypes.windll.user32.SetWindowPos(
            wintypes.HWND(hwnd), 0, 0, 0, 0, 0, flags,
        )
    except Exception:
        pass


def _set_dark_attr(hwnd: int) -> None:
    if not hwnd:
        return
    try:
        dwmapi = ctypes.windll.dwmapi
    except (OSError, AttributeError):
        return
    value = ctypes.c_int(1)
    rv = dwmapi.DwmSetWindowAttribute(
        wintypes.HWND(hwnd),
        _DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(value), ctypes.sizeof(value),
    )
    if rv != 0:
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            _DWMWA_USE_IMMERSIVE_DARK_MODE_OLD,
            ctypes.byref(value), ctypes.sizeof(value),
        )


def _bind_persistence(window) -> None:
    # Track whether we've forced an NC repaint yet for this window.
    # SetWindowPos(SWP_FRAMECHANGED) is the only way to force the
    # initial dark titlebar without a light flash on open — but it's
    # expensive (full non-client redraw) and on subsequent triggers
    # focus / map already cause Windows to repaint the NC area on its
    # own. So we run it exactly once per window lifetime.
    state = {"forced": False}

    def _reapply(_event=None) -> None:
        try:
            # Skip overrideredirect windows — tooltips, drag ghosts,
            # and similar chromeless popups have no titlebar to paint
            # and waste a SetWindowPos call otherwise.
            try:
                if window.overrideredirect():
                    return
            except tk.TclError:
                return
            hwnd = _hwnd_for(window)
            if not hwnd:
                return
            _set_dark_attr(hwnd)
            if not state["forced"]:
                _force_nc_repaint(hwnd)
                state["forced"] = True
        except Exception:
            pass

    # <Map> fires on initial show + on un-iconify. <FocusIn> fires
    # when the window regains focus (alt-tab back, click on it) —
    # this catches the "another window covered ours and the cache
    # invalidated" case without binding the noisy <Visibility> event.
    window.bind("<Map>", _reapply, add="+")
    window.bind("<FocusIn>", _reapply, add="+")


def install_dark_titlebar_persistence() -> None:
    """Patch ``tk.Tk`` and ``tk.Toplevel`` so every Tk window — plus
    everything that subclasses them (CTk, CTkToplevel, project dialogs
    inheriting tk.Toplevel directly) — keeps its dark titlebar across
    focus / map events. Call once at app startup, before any window
    is constructed.
    """
    if sys.platform != "win32":
        return

    for cls in (tk.Tk, tk.Toplevel):
        orig_init = cls.__init__

        def _patched(self, *args, _orig=orig_init, **kwargs):
            _orig(self, *args, **kwargs)
            try:
                _bind_persistence(self)
            except Exception:
                pass

        cls.__init__ = _patched
