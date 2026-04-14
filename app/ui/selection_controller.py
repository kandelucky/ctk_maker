"""Draws the selection rectangle + resize handles around the selected widget.

Both the rectangle edges and the 8 resize handles are rendered as
**embedded tk.Frame widgets** (via `canvas.create_window`), not canvas
items. Canvas items sit below any `create_window`-embedded widget, so
a plain `create_rectangle` would hide behind overlapping widgets. By
using real widgets and calling `.lift()` after creation we make the
selection chrome stay on top of everything else.

Trade-off: we lose the dashed border pattern (tk.Frame has no dashes),
so the rectangle renders as four solid 2px edges.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

HANDLE_NAMES = ("nw", "n", "ne", "w", "e", "sw", "s", "se")
HANDLE_SIZE = 8
HANDLE_FILL = "#3b8ed0"
HANDLE_OUTLINE = "#ffffff"
RECT_COLOR = "#3b8ed0"
RECT_THICKNESS = 2
SELECTION_PAD = 6
MIN_WIDGET_SIZE = 20

HANDLE_CURSORS = {
    "nw": "size_nw_se",
    "n":  "sb_v_double_arrow",
    "ne": "size_ne_sw",
    "w":  "sb_h_double_arrow",
    "e":  "sb_h_double_arrow",
    "sw": "size_ne_sw",
    "s":  "sb_v_double_arrow",
    "se": "size_nw_se",
}

HANDLE_OFFSETS = {
    "nw": (-1, -1), "n":  (0, -1), "ne": (1, -1),
    "w":  (-1,  0),               "e":  (1,  0),
    "sw": (-1,  1), "s":  (0,  1), "se": (1,  1),
}


class SelectionController:
    def __init__(
        self,
        canvas: tk.Canvas,
        project,
        widget_views: dict,
        zoom_provider: Callable[[], float] = lambda: 1.0,
    ):
        self.canvas = canvas
        self.project = project
        self.widget_views = widget_views
        self._zoom_provider = zoom_provider

        # name → (canvas_window_id, tk.Frame)
        self._handles: dict[str, tuple[int, tk.Frame]] = {}
        # side → (canvas_window_id, tk.Frame)  where side ∈ {top,right,bottom,left}
        self._edges: dict[str, tuple[int, tk.Frame]] = {}

        self._resize: dict | None = None

    def is_resizing(self) -> bool:
        return self._resize is not None

    def _is_locked(self, node) -> bool:
        """True when this node or any ancestor carries locked=True."""
        current = node
        while current is not None:
            if getattr(current, "locked", False):
                return True
            current = current.parent
        return False

    # ------------------------------------------------------------------
    # Public drawing API
    # ------------------------------------------------------------------
    def draw(self) -> None:
        bbox = self._selected_bbox()
        if bbox is None:
            self.clear()
            return
        self.clear()
        self._create(*bbox)

    def update(self) -> None:
        if not self._handles:
            self.draw()
            return
        bbox = self._selected_bbox()
        if bbox is None:
            return
        self._update_coords(*bbox)

    def clear(self) -> None:
        for window_id, frame in self._handles.values():
            try:
                self.canvas.delete(window_id)
            except tk.TclError:
                pass
            try:
                frame.destroy()
            except tk.TclError:
                pass
        self._handles = {}
        for window_id, frame in self._edges.values():
            try:
                self.canvas.delete(window_id)
            except tk.TclError:
                pass
            try:
                frame.destroy()
            except tk.TclError:
                pass
        self._edges = {}

    # ------------------------------------------------------------------
    # Resize flow — driven by handle widget bindings
    # ------------------------------------------------------------------
    def begin_resize(self, event, handle_name: str) -> None:
        sid = self.project.selected_id
        if sid is None:
            return
        node = self.project.get_widget(sid)
        if node is None:
            return
        if self._is_locked(node):
            return
        try:
            x = int(node.properties.get("x", 0))
            y = int(node.properties.get("y", 0))
            w = int(node.properties.get("width", 0))
            h = int(node.properties.get("height", 0))
        except (ValueError, TypeError):
            return
        self._resize = {
            "nid": sid, "handle": handle_name,
            "start_x": x, "start_y": y, "start_w": w, "start_h": h,
            "press_mx": event.x_root, "press_my": event.y_root,
        }

    def update_resize(self, event) -> None:
        r = self._resize
        if r is None:
            return
        zoom = self._zoom_provider() or 1.0
        dx = int((event.x_root - r["press_mx"]) / zoom)
        dy = int((event.y_root - r["press_my"]) / zoom)
        new_x, new_y, new_w, new_h = self._compute_resize(
            r["handle"], r["start_x"], r["start_y"],
            r["start_w"], r["start_h"], dx, dy,
        )
        nid = r["nid"]
        node = self.project.get_widget(nid)
        if node is None:
            return
        if int(node.properties.get("x", 0)) != new_x:
            self.project.update_property(nid, "x", new_x)
        if int(node.properties.get("y", 0)) != new_y:
            self.project.update_property(nid, "y", new_y)
        if int(node.properties.get("width", 0)) != new_w:
            self.project.update_property(nid, "width", new_w)
        if int(node.properties.get("height", 0)) != new_h:
            self.project.update_property(nid, "height", new_h)
        self.update()

    def end_resize(self, _event=None) -> None:
        self._resize = None
        try:
            self.canvas.configure(cursor="")
        except tk.TclError:
            pass
        self.draw()

    # ------------------------------------------------------------------
    # Internal rendering
    # ------------------------------------------------------------------
    def _selected_bbox(self) -> tuple[int, int, int, int] | None:
        """Canvas-coord bbox of the selected widget.

        Works for both canvas children (created via create_window) and
        nested children (placed inside a parent widget). We compute the
        bbox from the widget's actual screen position so the parent
        chain doesn't matter. Returns None for multi-selection so the
        workspace stays clean of selection handles when the Object
        Tree has 2+ rows highlighted.
        """
        if len(getattr(self.project, "selected_ids", set())) > 1:
            return None
        sid = self.project.selected_id
        if sid is None or sid not in self.widget_views:
            return None
        widget, _window_id = self.widget_views[sid]
        self.canvas.update_idletasks()
        try:
            rx = widget.winfo_rootx() - self.canvas.winfo_rootx()
            ry = widget.winfo_rooty() - self.canvas.winfo_rooty()
            w = widget.winfo_width()
            h = widget.winfo_height()
        except tk.TclError:
            return None
        if w <= 1 or h <= 1:
            return None
        cx1 = int(self.canvas.canvasx(rx))
        cy1 = int(self.canvas.canvasy(ry))
        return cx1, cy1, cx1 + w, cy1 + h

    def _create(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self._create_rect_edges(x1, y1, x2, y2)
        # Suppress resize handles on locked widgets — rectangle is
        # still drawn so the user sees what's selected.
        node = self.project.get_widget(self.project.selected_id)
        if node is not None and self._is_locked(node):
            return
        self._create_handles(x1, y1, x2, y2)

    def _create_rect_edges(self, x1: int, y1: int, x2: int, y2: int) -> None:
        ox1, oy1 = x1 - SELECTION_PAD, y1 - SELECTION_PAD
        ox2, oy2 = x2 + SELECTION_PAD, y2 + SELECTION_PAD
        self._edges["top"] = self._make_edge_frame(
            ox1, oy1, ox2 - ox1, RECT_THICKNESS,
        )
        self._edges["bottom"] = self._make_edge_frame(
            ox1, oy2 - RECT_THICKNESS, ox2 - ox1, RECT_THICKNESS,
        )
        self._edges["left"] = self._make_edge_frame(
            ox1, oy1, RECT_THICKNESS, oy2 - oy1,
        )
        self._edges["right"] = self._make_edge_frame(
            ox2 - RECT_THICKNESS, oy1, RECT_THICKNESS, oy2 - oy1,
        )

    def _make_edge_frame(
        self, x: int, y: int, w: int, h: int,
    ) -> tuple[int, tk.Frame]:
        frame = tk.Frame(
            self.canvas, bg=RECT_COLOR, highlightthickness=0,
            width=max(1, w), height=max(1, h),
        )
        window_id = self.canvas.create_window(
            x, y, window=frame, anchor="nw",
            width=max(1, w), height=max(1, h),
        )
        frame.lift()
        return window_id, frame

    def _create_handles(self, x1: int, y1: int, x2: int, y2: int) -> None:
        for name in HANDLE_NAMES:
            hx, hy = self._handle_center(name, x1, y1, x2, y2)
            frame = tk.Frame(
                self.canvas,
                bg=HANDLE_FILL,
                highlightthickness=1,
                highlightbackground=HANDLE_OUTLINE,
                width=HANDLE_SIZE, height=HANDLE_SIZE,
                cursor=HANDLE_CURSORS[name],
            )
            window_id = self.canvas.create_window(
                hx, hy, window=frame, anchor="center",
                width=HANDLE_SIZE, height=HANDLE_SIZE,
            )
            frame.bind(
                "<ButtonPress-1>",
                lambda e, n=name: self.begin_resize(e, n),
                add="+",
            )
            frame.bind("<B1-Motion>", self.update_resize, add="+")
            frame.bind("<ButtonRelease-1>", self.end_resize, add="+")
            frame.lift()
            self._handles[name] = (window_id, frame)

    def _update_coords(self, x1: int, y1: int, x2: int, y2: int) -> None:
        ox1, oy1 = x1 - SELECTION_PAD, y1 - SELECTION_PAD
        ox2, oy2 = x2 + SELECTION_PAD, y2 + SELECTION_PAD
        # Move + resize the 4 edge frames in place
        edge_geoms = {
            "top":    (ox1, oy1, ox2 - ox1, RECT_THICKNESS),
            "bottom": (ox1, oy2 - RECT_THICKNESS, ox2 - ox1, RECT_THICKNESS),
            "left":   (ox1, oy1, RECT_THICKNESS, oy2 - oy1),
            "right":  (ox2 - RECT_THICKNESS, oy1, RECT_THICKNESS, oy2 - oy1),
        }
        for side, (ex, ey, ew, eh) in edge_geoms.items():
            entry = self._edges.get(side)
            if entry is None:
                continue
            window_id, frame = entry
            try:
                self.canvas.coords(window_id, ex, ey)
                self.canvas.itemconfigure(
                    window_id, width=max(1, ew), height=max(1, eh),
                )
            except tk.TclError:
                pass
        for name, (window_id, _frame) in self._handles.items():
            hx, hy = self._handle_center(name, x1, y1, x2, y2)
            try:
                self.canvas.coords(window_id, hx, hy)
            except tk.TclError:
                pass

    def _handle_center(
        self, name: str, x1: int, y1: int, x2: int, y2: int,
    ) -> tuple[int, int]:
        ox, oy = HANDLE_OFFSETS[name]
        if ox < 0:
            cx = x1 - SELECTION_PAD
        elif ox > 0:
            cx = x2 + SELECTION_PAD
        else:
            cx = (x1 + x2) // 2
        if oy < 0:
            cy = y1 - SELECTION_PAD
        elif oy > 0:
            cy = y2 + SELECTION_PAD
        else:
            cy = (y1 + y2) // 2
        return cx, cy

    def _compute_resize(
        self, handle: str,
        sx: int, sy: int, sw: int, sh: int,
        dx: int, dy: int,
    ) -> tuple[int, int, int, int]:
        x, y, w, h = sx, sy, sw, sh
        if handle in ("nw", "w", "sw"):
            x = sx + dx
            w = sw - dx
        elif handle in ("ne", "e", "se"):
            w = sw + dx
        if handle in ("nw", "n", "ne"):
            y = sy + dy
            h = sh - dy
        elif handle in ("sw", "s", "se"):
            h = sh + dy
        if w < MIN_WIDGET_SIZE:
            if handle in ("nw", "w", "sw"):
                x = sx + sw - MIN_WIDGET_SIZE
            w = MIN_WIDGET_SIZE
        if h < MIN_WIDGET_SIZE:
            if handle in ("nw", "n", "ne"):
                y = sy + sh - MIN_WIDGET_SIZE
            h = MIN_WIDGET_SIZE
        return x, y, w, h
