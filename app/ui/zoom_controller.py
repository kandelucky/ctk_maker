"""Zoom state + controls extracted from Workspace.

Owns the zoom value, the coordinate-conversion helpers that depend
on it (logical ↔ canvas), the per-widget `apply` logic, and the
bottom status-bar zoom widgets (−/+, percentage menu, warning label).

Workspace creates one `ZoomController` per workspace instance and
wires an `on_zoom_changed` callback that redraws the document rect,
grid, and selection chrome when the zoom value updates.
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk

from app.core.logger import log_error
from app.ui.icons import load_icon

ZOOM_LEVELS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0)
ZOOM_MIN = ZOOM_LEVELS[0]
ZOOM_MAX = ZOOM_LEVELS[-1]


def _detect_dpi_factor() -> float:
    """System DPI factor used to size canvas-side drawing so it tracks
    CTk's DPI-aware widget rendering. 1.0 on 96-DPI; 1.25 on 125 %;
    1.5 on 150 %, etc. Non-Windows falls back to 1.0 since CTk's
    ScalingTracker only reports an OS factor on Windows.
    """
    import sys
    if sys.platform != "win32":
        return 1.0
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        dpi = ctypes.windll.user32.GetDpiForSystem()
        return max(1.0, dpi / 96.0)
    except Exception:
        return 1.0

ZOOM_MENU_LABELS = [
    "25%", "50%", "75%", "100%", "125%", "150%", "200%", "300%", "400%",
    "Fit to window", "Actual size",
]

ZOOM_WARNING_FG = "#d4a340"
ZOOM_WARNING_TEXT = "      ⚠  Not actual size — set 100% for real preview"


class ZoomController:
    def __init__(
        self,
        canvas: tk.Canvas,
        widget_views: dict,
        project,
        document_padding: int,
        on_zoom_changed: Callable[[], None],
    ):
        self.canvas = canvas
        self.widget_views = widget_views
        self.project = project
        self.document_padding = document_padding
        self._on_zoom_changed = on_zoom_changed

        self.value: float = 1.0
        # Canvas-side drawing (doc rect, grid, top-level widget
        # placement on canvas) multiplies by ``canvas_scale`` = user
        # zoom × OS DPI factor, while widget.configure(width=...)
        # stays on ``value`` (CTk's ScalingTracker adds DPI itself,
        # doubling if we also applied it here). The DPI factor is
        # baked in as a zoom multiplier so doc rects render at their
        # runtime physical size — fixes the "button overflows window"
        # illusion on high-DPI displays where canvas coords are raw
        # physical pixels but CTk widgets render at logical × DPI.
        self._dpi_factor: float = _detect_dpi_factor()
        self._menu: ctk.CTkOptionMenu | None = None
        self._menu_var: tk.StringVar | None = None
        self._warning: ctk.CTkLabel | None = None

    @property
    def canvas_scale(self) -> float:
        """``user zoom × OS DPI`` — for canvas drawing + canvas-item
        coords. See ``_dpi_factor`` comment for rationale."""
        return self.value * self._dpi_factor

    # ------------------------------------------------------------------
    # Coordinate helpers (zoom + padding + per-document offset)
    # ------------------------------------------------------------------
    def logical_to_canvas(
        self, lx: int, ly: int, document=None,
    ) -> tuple[int, int]:
        """Return canvas coordinates for a logical point inside
        ``document`` (defaults to the project's active document).
        Applies padding, zoom × DPI, and the document's canvas_x /
        canvas_y offset so multi-document projects render at their
        own positions on the shared canvas.
        """
        if document is None:
            document = self.project.active_document
        scale = self.canvas_scale
        offset_x = int(document.canvas_x * scale)
        offset_y = int(document.canvas_y * scale)
        return (
            self.document_padding + offset_x + int(lx * scale),
            self.document_padding + offset_y + int(ly * scale),
        )

    def canvas_to_logical(
        self, cx: float, cy: float, document=None,
    ) -> tuple[int, int]:
        if document is None:
            document = self.project.active_document
        z = self.canvas_scale or 1.0
        offset_x = document.canvas_x * z
        offset_y = document.canvas_y * z
        return (
            int((cx - self.document_padding - offset_x) / z),
            int((cy - self.document_padding - offset_y) / z),
        )

    # ------------------------------------------------------------------
    # Zoom setters
    # ------------------------------------------------------------------
    def set(self, new_zoom: float) -> None:
        new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, new_zoom))
        if abs(new_zoom - self.value) < 0.001:
            return
        self.value = new_zoom
        self.apply_all()
        self._refresh_readout()

    def step(self, delta: int) -> None:
        try:
            idx = ZOOM_LEVELS.index(self.value)
        except ValueError:
            idx = min(
                range(len(ZOOM_LEVELS)),
                key=lambda i: abs(ZOOM_LEVELS[i] - self.value),
            )
        new_idx = max(0, min(len(ZOOM_LEVELS) - 1, idx + delta))
        self.set(ZOOM_LEVELS[new_idx])

    def fit_window(self) -> None:
        self.canvas.update_idletasks()
        viewport_w = self.canvas.winfo_width()
        viewport_h = self.canvas.winfo_height()
        if viewport_w <= 1 or viewport_h <= 1:
            return
        doc_w = self.project.document_width
        doc_h = self.project.document_height
        if doc_w <= 0 or doc_h <= 0:
            return
        pad2 = self.document_padding * 2
        zoom_w = (viewport_w - pad2) / doc_w
        zoom_h = (viewport_h - pad2) / doc_h
        zoom = max(ZOOM_MIN, min(ZOOM_MAX, min(zoom_w, zoom_h)))
        self.set(zoom)

    def reset(self) -> None:
        self.set(1.0)

    def handle_ctrl_wheel(self, event) -> str:
        self.step(1 if event.delta > 0 else -1)
        return "break"

    # ------------------------------------------------------------------
    # Apply to widgets
    # ------------------------------------------------------------------
    def apply_all(self) -> None:
        # Precompute widget_id → (node, doc) once per call. Without this,
        # each loop iteration does ``get_widget`` + ``find_document_for_widget``
        # which are both O(N) linear scans over every widget in every
        # document — apply_all becomes O(N²). At 100 widgets that's
        # 10 000 lookup ops per call, and chrome drag fires apply_all
        # at motion rate (~100 Hz) so the hot path was burning ~1M
        # lookups/sec in pure Python dict/attr access.
        id_index: dict[str, tuple] = {}
        for doc in self.project.documents:
            stack = list(doc.root_widgets)
            while stack:
                node = stack.pop()
                id_index[node.id] = (node, doc)
                stack.extend(node.children)
        for nid, (widget, window_id) in self.widget_views.items():
            entry = id_index.get(nid)
            if entry is None:
                continue
            node, document = entry
            self.apply_to_widget(
                widget, window_id, node.properties, document=document,
            )
        self._on_zoom_changed()

    def apply_to_widget(
        self, widget, window_id, properties: dict, document=None,
    ) -> None:
        # Skip destroyed widgets up-front. ``winfo_exists()`` on a
        # gone widget returns 0; catching ``tk.TclError`` covers the
        # even more degenerate "interpreter already tearing down"
        # case. Without this guard the per-call try/except blocks
        # below all swallow the same "widget is gone" TclError and
        # silently hide any legitimate option / geometry errors that
        # share the same exception class — harder to debug later.
        try:
            if not widget.winfo_exists():
                return
        except tk.TclError:
            return
        try:
            lx = int(properties.get("x", 0))
            ly = int(properties.get("y", 0))
        except (TypeError, ValueError):
            lx, ly = 0, 0
        if window_id is not None:
            cx, cy = self.logical_to_canvas(lx, ly, document=document)
            self.canvas.coords(window_id, cx, cy)
        else:
            # Nested child — position via place() in local-parent coords.
            # Guard: only re-place if the widget is currently managed by
            # `place`. A widget that was hidden via `place_forget` returns
            # an empty manager string, and calling `place_configure` on it
            # would un-hide it unexpectedly.
            try:
                if widget.winfo_manager() == "place":
                    widget.place_configure(
                        x=int(lx * self.value),
                        y=int(ly * self.value),
                    )
            except tk.TclError:
                pass
        try:
            lw = int(properties.get("width", 0))
            lh = int(properties.get("height", 0))
        except (TypeError, ValueError):
            return
        if lw > 0 and lh > 0:
            try:
                widget.configure(
                    width=max(1, int(lw * self.value)),
                    height=max(1, int(lh * self.value)),
                )
            except tk.TclError:
                pass
        scaled_font = self._build_scaled_font(properties)
        if scaled_font is not None:
            try:
                widget.configure(font=scaled_font)
            except tk.TclError:
                pass

    def _build_scaled_font(self, properties: dict):
        """Return a CTkFont whose size is `font_size * zoom` (or None).

        Only applies to widgets whose descriptor carries a logical
        `font_size` property. Leaves widgets without text (e.g.
        CTkFrame) untouched.
        """
        if "font_size" not in properties:
            return None
        try:
            logical_size = int(properties.get("font_size") or 13)
        except (TypeError, ValueError):
            return None
        scaled = max(6, int(round(logical_size * self.value)))
        weight = "bold" if properties.get("font_bold") else "normal"
        slant = "italic" if properties.get("font_italic") else "roman"
        underline = bool(properties.get("font_underline"))
        overstrike = bool(properties.get("font_overstrike"))
        try:
            return ctk.CTkFont(
                size=scaled, weight=weight, slant=slant,
                underline=underline, overstrike=overstrike,
            )
        except Exception:
            log_error("ZoomController._build_scaled_font")
            return None

    # ------------------------------------------------------------------
    # Status-bar UI
    # ------------------------------------------------------------------
    def mount_controls(self, bar) -> None:
        """Populate `bar` with [−] [+] [1:1] [menu ▼] + warning label.

        `bar` is expected to be a CTkFrame already packed into the
        workspace. This method owns nothing about the bar itself —
        only the zoom-related widgets inside it.
        """
        minus_icon = load_icon("minus", size=14)
        plus_icon = load_icon("plus", size=14)

        ctk.CTkButton(
            bar, text="" if minus_icon else "−",
            image=minus_icon, width=24, height=20,
            corner_radius=3,
            fg_color="transparent", hover_color="#3a3a3a",
            command=lambda: self.step(-1),
        ).pack(side="left", padx=(8, 2), pady=3)

        ctk.CTkButton(
            bar, text="" if plus_icon else "+",
            image=plus_icon, width=24, height=20,
            corner_radius=3,
            fg_color="transparent", hover_color="#3a3a3a",
            command=lambda: self.step(1),
        ).pack(side="left", padx=2, pady=3)

        ctk.CTkButton(
            bar, text="1:1",
            font=("Segoe UI", 10, "bold"),
            width=28, height=20,
            corner_radius=3,
            fg_color="transparent", hover_color="#3a3a3a",
            text_color="#cccccc",
            command=self.reset,
        ).pack(side="left", padx=2, pady=3)

        self._menu_var = tk.StringVar(value="100%")
        self._menu = ctk.CTkOptionMenu(
            bar,
            values=ZOOM_MENU_LABELS,
            variable=self._menu_var,
            width=120, height=20,
            font=("Segoe UI", 10),
            dropdown_font=("Segoe UI", 10),
            fg_color="#2d2d2d", button_color="#2d2d2d",
            button_hover_color="#3a3a3a", corner_radius=3,
            command=self._on_menu_select,
        )
        self._menu.pack(side="left", padx=(4, 8), pady=3)

        self._warning = ctk.CTkLabel(
            bar, text="",
            font=("Segoe UI", 10), text_color=ZOOM_WARNING_FG,
            anchor="w",
        )
        self._warning.pack(side="left", padx=(4, 0), pady=3)

    def _refresh_readout(self) -> None:
        if self._menu_var is None:
            return
        pct = round(self.value * 100, 1)
        label = f"{int(pct)}%" if pct == int(pct) else f"{pct}%"
        self._menu_var.set(label)
        if self._warning is not None:
            if abs(self.value - 1.0) > 0.001:
                self._warning.configure(text=ZOOM_WARNING_TEXT)
            else:
                self._warning.configure(text="")

    def _on_menu_select(self, label: str) -> None:
        if label == "Actual size":
            self.set(1.0)
            return
        if label == "Fit to window":
            self.fit_window()
            return
        if label.endswith("%"):
            try:
                pct = float(label[:-1])
            except ValueError:
                return
            self.set(pct / 100.0)
