"""Base class for floating tool windows in the app.

``ManagedToplevel`` centralizes everything every floating window
needs in one place:

- colors / styling via ``fg_color`` and consistent inner padding
- ``transient(parent)`` and ``minsize`` wiring
- flicker-free open via the alpha-0 → build → alpha-1 trick
- dark titlebar that paints dark on the *first* visible frame —
  the ``ctkmaker-core`` fork's ``CTkToplevel`` sets + persists the DWM
  dark attribute, but the visual NC paint is still deferred until a
  user-driven event (move/focus). ``_kick_dark_remap`` forces it by
  withdrawing + deiconifying once after reveal. Verified 2026-05-14:
  the fork's one-shot ``SWP_FRAMECHANGED`` alone does *not* prevent
  the first-frame light flash here — this remap is still required.
- geometry that fits the screen and is remembered per ``window_key``
  across runs (debounced ``<Configure>`` save + clamp on load)

Subclasses set class-level attrs and override ``build_content`` to
return the inner frame. The frame is a normal ``CTkFrame``, so the
same content class can also be embedded directly in a sidebar or
tabview — the floating wrapper is opt-in.

Example::

    class HistoryWindow(ManagedToplevel):
        window_key = "history"
        window_title = "History"
        default_size = (300, 400)
        min_size = (220, 200)
        fg_color = "#1e1e1e"

        def __init__(self, parent, project, on_close=None):
            self.project = project
            super().__init__(parent)
            self.set_on_close(on_close)

        def build_content(self):
            return HistoryPanel(self, self.project)
"""

from __future__ import annotations

import re
import sys
import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk

from app.core.settings import load_settings, save_setting

SCREEN_BOTTOM_MARGIN = 40
SCREEN_EDGE_MARGIN = 4
SAVE_DEBOUNCE_MS = 400
DARK_REMAP_DELAY_MS = 50

_GEOMETRIES_KEY = "window_geometries"
_GEOMETRY_RE = re.compile(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$")


# ----------------------------------------------------------------------
# Geometry: parsing, clamping, persistence

def _parse_geometry(geom: str) -> Optional[tuple[int, int, int, int]]:
    m = _GEOMETRY_RE.match(geom.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))


def clamp_to_screen(
    toplevel: tk.Misc, x: int, y: int, w: int, h: int,
) -> tuple[int, int, int, int]:
    """Adjust ``(x, y, w, h)`` so the window fits on its screen."""
    try:
        sw = toplevel.winfo_screenwidth()
        sh = toplevel.winfo_screenheight()
    except tk.TclError:
        return (x, y, w, h)

    max_w = max(100, sw - 2 * SCREEN_EDGE_MARGIN)
    max_h = max(100, sh - SCREEN_BOTTOM_MARGIN - SCREEN_EDGE_MARGIN)
    if w > max_w:
        w = max_w
    if h > max_h:
        h = max_h

    min_x = SCREEN_EDGE_MARGIN
    min_y = SCREEN_EDGE_MARGIN
    max_x = max(min_x, sw - w - SCREEN_EDGE_MARGIN)
    max_y = max(min_y, sh - h - SCREEN_BOTTOM_MARGIN)

    if x < min_x:
        x = min_x
    elif x > max_x:
        x = max_x
    if y < min_y:
        y = min_y
    elif y > max_y:
        y = max_y

    return (x, y, w, h)


def _load_geometries() -> dict:
    raw = load_settings().get(_GEOMETRIES_KEY, {})
    return raw if isinstance(raw, dict) else {}


def _load_geometry(key: str) -> Optional[str]:
    val = _load_geometries().get(key)
    return val if isinstance(val, str) and val else None


def _persist_geometry(key: str, geom: str) -> None:
    geometries = _load_geometries()
    if geometries.get(key) == geom:
        return
    geometries[key] = geom
    save_setting(_GEOMETRIES_KEY, geometries)


# ----------------------------------------------------------------------
# ManagedToplevel base class

class ManagedToplevel(ctk.CTkToplevel):
    """Base class for floating tool windows.

    Subclasses override class-level attrs and ``build_content``;
    ``ManagedToplevel`` handles geometry persistence, alpha-based
    flicker prevention, dark-titlebar reinforcement, transient
    parenting, modal grab, Escape-to-close, resize / topmost flags,
    and content auto-cleanup on close.

    Flags:
        ``modal``           Apply ``grab_set`` after the window is
                            visible — events route only to it.
        ``escape_closes``   Close on ``<Escape>``. Bound both locally
                            on the toplevel (fast path when focus is
                            inside) and via ``bind_all`` against a
                            class-level open-window stack (fallback
                            for when focus is on another widget tree
                            — Windows often refuses ``focus_force``).
        ``window_resizable`` Tuple passed to ``self.resizable``.
        ``always_on_top``   Apply ``-topmost`` attribute.

    Cleanup: if ``self._content`` exposes ``cleanup()`` or
    ``_unsubscribe_bus()``, ``destroy`` calls it automatically.
    """

    window_key: str = ""
    window_title: str = ""
    default_size: tuple[int, int] = (400, 300)
    min_size: tuple[int, int] = (200, 150)
    fg_color: Optional[str] = None
    panel_padding: tuple[int, int] = (6, 6)
    # Behavior flags
    modal: bool = False
    escape_closes: bool = True
    window_resizable: tuple[bool, bool] = (True, True)
    always_on_top: bool = False

    # Class-level state for the global Escape handler.
    _open_stack: list = []
    _escape_bind_installed: bool = False

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self._parent = parent
        self._on_close_callback: Optional[Callable[[], None]] = None
        self._track_after_id: Optional[str] = None

        self._prepare()
        if self.window_title:
            self.title(self.window_title)
        if self.fg_color is not None:
            self.configure(fg_color=self.fg_color)
        self.minsize(*self.min_size)
        self.resizable(*self.window_resizable)
        if self.always_on_top:
            try:
                self.attributes("-topmost", True)
            except tk.TclError:
                pass
        try:
            self.transient(parent)
        except tk.TclError:
            pass

        self._content = self.build_content()
        if self._content is not None:
            self._content.pack(
                fill="both", expand=True,
                padx=self.panel_padding[0], pady=self.panel_padding[1],
            )

        self._apply_initial_geometry()
        self._bind_geometry_tracking()

        self.protocol("WM_DELETE_WINDOW", self._handle_close)
        if self.escape_closes:
            # Local toplevel bind: fast path when keyboard focus is
            # already inside this window (bubbles up via bindtags).
            self.bind("<Escape>", self._on_escape, add="+")
            # Global bind_all + open-window stack: fallback for the
            # common case where keyboard focus is on another widget
            # tree (e.g. the main window's canvas) when the user
            # presses Escape — Windows often refuses focus_force,
            # so without this Escape would do nothing until the user
            # clicked into the floating window first.
            ManagedToplevel._open_stack.append(self)
            if not ManagedToplevel._escape_bind_installed:
                self.bind_all(
                    "<Escape>", ManagedToplevel._global_escape, add="+",
                )
                ManagedToplevel._escape_bind_installed = True
        self._reveal()

    # ------------------------------------------------------------------
    # Subclass hooks

    def build_content(self) -> Optional[ctk.CTkFrame]:
        """Return the inner frame to pack into the window. Default
        returns ``None`` (empty window). Override in subclasses.
        """
        return None

    def default_offset(self, parent) -> tuple[int, int]:
        """Return ``(x, y)`` for the first-ever open. Default centers
        the window on its current screen.
        """
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
        except tk.TclError:
            return (100, 100)
        w, h = self.default_size
        return (max(0, (sw - w) // 2), max(0, (sh - h) // 2))

    def on_close(self) -> None:
        """Called from ``_handle_close`` before destroy. Subclasses
        can override for cleanup that must run on user-initiated close.
        """
        pass

    def set_on_close(self, callback: Optional[Callable[[], None]]) -> None:
        self._on_close_callback = callback

    # ------------------------------------------------------------------
    # Internal: prepare / reveal

    def _prepare(self) -> None:
        try:
            self.attributes("-alpha", 0.0)
        except tk.TclError:
            pass

    def _reveal(self) -> None:
        try:
            self.update_idletasks()
        except tk.TclError:
            pass
        try:
            self.attributes("-alpha", 1.0)
        except tk.TclError:
            pass
        if sys.platform == "win32":
            try:
                self.after(DARK_REMAP_DELAY_MS, self._kick_dark_remap)
            except tk.TclError:
                pass

    def _kick_dark_remap(self) -> None:
        # Withdraw + deiconify forces a fresh <Map> event. The fork's
        # CTkToplevel sets the DWM dark attribute on the first map, but
        # Windows on this build defers the visual NC paint until a user
        # event (move/focus). The second map paints with the attribute
        # already in effect — dark from frame 1. Verified 2026-05-14:
        # the fork's SWP_FRAMECHANGED alone is not enough here.
        try:
            if not self.winfo_exists():
                return
            self.withdraw()
            self.update_idletasks()
            self.deiconify()
        except tk.TclError:
            return
        # Lift to Z-order top so the floating window is visually on
        # top. We deliberately do NOT call focus_force — Windows
        # anti-focus-stealing policy refuses it intermittently, which
        # the user perceives as flaky behavior. Escape-to-close is
        # handled by the global bind_all + stack instead.
        try:
            self.lift()
        except tk.TclError:
            pass
        if self.modal:
            self._apply_modal_grab()

    def _apply_modal_grab(self) -> None:
        # macOS Tk crashes if grab_set runs before the window is
        # mapped; wait_visibility blocks until the WM has it on screen.
        try:
            self.wait_visibility()
        except tk.TclError:
            pass
        try:
            self.grab_set()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Internal: geometry

    def _apply_initial_geometry(self) -> None:
        saved = _load_geometry(self.window_key) if self.window_key else None
        parsed = _parse_geometry(saved) if saved else None
        if parsed is not None:
            w, h, x, y = parsed
        else:
            w, h = self.default_size
            try:
                x, y = self.default_offset(self._parent)
            except tk.TclError:
                x, y = 100, 100
        x, y, w, h = clamp_to_screen(self, x, y, w, h)
        try:
            self.geometry(f"{w}x{h}+{x}+{y}")
        except tk.TclError:
            pass

    def _bind_geometry_tracking(self) -> None:
        if not self.window_key:
            return

        def _flush() -> None:
            self._track_after_id = None
            self._save_geometry()

        def _on_configure(event) -> None:
            if event.widget is not self:
                return
            if self._track_after_id is not None:
                try:
                    self.after_cancel(self._track_after_id)
                except tk.TclError:
                    pass
            try:
                self._track_after_id = self.after(SAVE_DEBOUNCE_MS, _flush)
            except tk.TclError:
                pass

        self.bind("<Configure>", _on_configure, add="+")

    def _save_geometry(self) -> None:
        if not self.window_key:
            return
        try:
            state_str = self.state()
        except (tk.TclError, AttributeError):
            state_str = "normal"
        if state_str != "normal":
            return
        try:
            geom = self.geometry()
        except tk.TclError:
            return
        parsed = _parse_geometry(geom)
        if parsed is None or parsed[0] < 50 or parsed[1] < 50:
            return
        _persist_geometry(self.window_key, geom)

    # ------------------------------------------------------------------
    # Close

    def _handle_close(self) -> None:
        self._save_geometry()
        try:
            self.on_close()
        except Exception:
            pass
        if self._on_close_callback is not None:
            try:
                self._on_close_callback()
            except Exception:
                pass
        self.destroy()

    def _on_escape(self, _event=None) -> str:
        self._handle_close()
        return "break"

    @classmethod
    def _global_escape(cls, _event=None) -> str:
        # Close the topmost still-alive managed toplevel. Stale entries
        # (pre-destroyed elsewhere) get popped on the way down.
        while cls._open_stack:
            top = cls._open_stack[-1]
            try:
                if top.winfo_exists():
                    top._handle_close()
                    return "break"
            except tk.TclError:
                pass
            cls._open_stack.pop()
        return ""

    def destroy(self) -> None:
        try:
            ManagedToplevel._open_stack.remove(self)
        except ValueError:
            pass
        if self._track_after_id is not None:
            try:
                self.after_cancel(self._track_after_id)
            except tk.TclError:
                pass
            self._track_after_id = None
        self._cleanup_content()
        super().destroy()

    def _cleanup_content(self) -> None:
        # Auto-call cleanup on the content frame if it exposes one of
        # the standard hooks. Subclasses don't need to override
        # destroy just to tear down event-bus subscriptions etc.
        content = getattr(self, "_content", None)
        if content is None:
            return
        for name in ("cleanup", "_unsubscribe_bus"):
            method = getattr(content, name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass
                return
