"""Skeleton ``ManagedToplevel`` subclasses for testing the helper.

Triggered via Ctrl+Shift+Alt+1..4 from the main window. Each window
exercises a different "force NC repaint" technique so dark-titlebar
behavior can be observed in isolation.

Not user-facing; remove when the helper is fully validated.
"""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from ctypes import wintypes

import customtkinter as ctk

from app.ui.managed_window import ManagedToplevel


def _hwnd_of(window) -> int:
    if sys.platform != "win32":
        return 0
    try:
        return ctypes.windll.user32.GetParent(window.winfo_id())
    except Exception:
        return 0


def _redraw_frame(hwnd: int) -> None:
    """RedrawWindow with RDW_FRAME | RDW_INVALIDATE | RDW_UPDATENOW —
    invalidates the non-client frame and forces an immediate repaint.
    """
    if not hwnd:
        return
    RDW_INVALIDATE = 0x0001
    RDW_UPDATENOW = 0x0100
    RDW_FRAME = 0x0400
    try:
        ctypes.windll.user32.RedrawWindow(
            wintypes.HWND(hwnd), 0, 0,
            RDW_FRAME | RDW_INVALIDATE | RDW_UPDATENOW,
        )
    except Exception:
        pass


def _send_nc_activate_cycle(hwnd: int) -> None:
    """Toggle WM_NCACTIVATE inactive/active to fake a focus transition,
    which on Windows reliably forces a NC repaint.
    """
    if not hwnd:
        return
    WM_NCACTIVATE = 0x0086
    try:
        ctypes.windll.user32.SendMessageW(wintypes.HWND(hwnd), WM_NCACTIVATE, 0, 0)
        ctypes.windll.user32.SendMessageW(wintypes.HWND(hwnd), WM_NCACTIVATE, 1, 0)
    except Exception:
        pass


class _BaseTestWindow(ManagedToplevel):
    """Tiny content frame with a single label — overridden per variant."""

    label_text = ""

    def build_content(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(
            frame,
            text=self.label_text or self.window_title,
            font=("Segoe UI", 14),
            justify="center",
        ).pack(expand=True)
        return frame


class TestWindowA(_BaseTestWindow):
    """Diagnostic — fixed size (resizable disabled on both axes)."""

    window_key = "dev_test_a"
    window_title = "Test A — fixed size"
    default_size = (320, 200)
    min_size = (200, 120)
    fg_color = "#1e1e1e"
    window_resizable = (False, False)
    label_text = "Test A\nwindow_resizable=\n(False, False)"


class TestWindowB(_BaseTestWindow):
    """Diagnostic — alpha trick + RedrawWindow(RDW_FRAME) post-reveal.
    Tests whether forcing an immediate frame invalidation paints dark.
    """

    window_key = "dev_test_b"
    window_title = "Test B — RedrawWindow"
    default_size = (520, 280)
    min_size = (300, 150)
    fg_color = "#252526"
    label_text = "Test B\nalpha + RedrawWindow\n(RDW_FRAME)"

    def _reveal(self) -> None:
        super()._reveal()
        for delay in (50, 200):
            try:
                self.after(delay, self._kick_redraw)
            except tk.TclError:
                pass

    def _kick_redraw(self) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        _redraw_frame(_hwnd_of(self))


class TestWindowC(_BaseTestWindow):
    """Diagnostic — alpha trick + withdraw/deiconify kick post-reveal.
    Tests whether re-mapping the window forces a fresh NC paint.
    """

    window_key = "dev_test_c"
    window_title = "Test C — withdraw kick"
    default_size = (260, 480)
    min_size = (180, 200)
    fg_color = "#1e1e1e"
    label_text = "Test C\nalpha + withdraw/\ndeiconify kick"

    def _reveal(self) -> None:
        super()._reveal()
        try:
            self.after(50, self._kick_remap)
        except tk.TclError:
            pass

    def _kick_remap(self) -> None:
        try:
            if not self.winfo_exists():
                return
            self.withdraw()
            self.update_idletasks()
            self.deiconify()
        except (tk.TclError, Exception):
            pass


class TestWindowD(_BaseTestWindow):
    """Diagnostic — alpha trick + WM_NCACTIVATE 0/1 cycle post-reveal.
    Tests whether faking a focus transition paints dark.
    """

    window_key = "dev_test_d"
    window_title = "Test D — NCACTIVATE cycle"
    default_size = (640, 420)
    min_size = (400, 250)
    fg_color = "#252526"
    label_text = "Test D\nalpha + WM_NCACTIVATE\n0/1 cycle"

    def _reveal(self) -> None:
        super()._reveal()
        try:
            self.after(50, self._kick_ncactivate)
        except tk.TclError:
            pass

    def _kick_ncactivate(self) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        _send_nc_activate_cycle(_hwnd_of(self))


DEV_TEST_WINDOW_CLASSES = (TestWindowA, TestWindowB, TestWindowC, TestWindowD)
