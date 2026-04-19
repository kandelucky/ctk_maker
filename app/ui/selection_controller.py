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

from app.core.commands import ResizeCommand

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
        anchor_views: dict | None = None,
        handles_enabled: Callable[[], bool] = lambda: True,
    ):
        self.canvas = canvas
        self.project = project
        self.widget_views = widget_views
        # Composite widgets (e.g. CTkScrollableFrame) put a different
        # outer container on the canvas — selection geometry must
        # measure that container, not the inner widget.
        self.anchor_views = anchor_views if anchor_views is not None else {}
        self._zoom_provider = zoom_provider
        # Called before drawing handles — lets the workspace suppress
        # them (e.g. Select tool hides them so the user can't resize
        # by accident while doing selection work).
        self._handles_enabled = handles_enabled

        # Primary chrome — 4 edge frames + 8 resize handles. Allocated
        # lazily on the first draw, then REUSED across every
        # ``draw()`` / ``clear()`` cycle by flipping
        # ``state="hidden"`` / ``"normal"`` on the canvas window
        # items. Avoids the per-draw tk.Frame alloc+destroy storm
        # that made multi-select + rapid redraws expensive.
        # side → (canvas_window_id, tk.Frame)
        self._edges: dict[str, tuple[int, tk.Frame]] = {}
        # name → (canvas_window_id, tk.Frame)
        self._handles: dict[str, tuple[int, tk.Frame]] = {}
        # Pool of outline entries for non-primary multi-selection
        # widgets. Each entry is a 4-edge dict; the pool grows as
        # needed, shrinks only by hiding surplus entries (the tk.Frame
        # itself stays around for future reuse).
        self._outline_pool: list[dict[str, tuple[int, tk.Frame]]] = []

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
        # Flush pending tk geometry once at the top so every
        # ``_bbox_for`` below reads settled coords without doing
        # its own ``update_idletasks``. For N-wide multi-selection
        # that's N-1 redundant flushes saved per draw.
        try:
            self.canvas.update_idletasks()
        except tk.TclError:
            pass
        ids = list(getattr(self.project, "selected_ids", set()) or [])
        primary = self.project.selected_id
        primary_bbox = None
        if primary and primary in ids:
            primary_bbox = self._bbox_for(primary)
        self._show_primary_chrome(primary, primary_bbox)
        # Non-primary multi-select outlines — one entry per widget,
        # pool-backed so repeat draws with the same selection size
        # run zero allocations.
        non_primary = [wid for wid in ids if wid != primary]
        for i, wid in enumerate(non_primary):
            bbox = self._bbox_for(wid)
            if bbox is None:
                self._hide_outline(i)
                continue
            self._ensure_outline_allocated(i)
            self._position_outline(i, bbox, wid)
        for i in range(len(non_primary), len(self._outline_pool)):
            self._hide_outline(i)

    def update(self) -> None:
        """Lightweight chrome refresh for the primary widget only —
        called in the resize hot path. If chrome hasn't been
        allocated yet, fall through to a full ``draw``. Flushes
        pending idle tasks once before reading the widget's
        post-configure geometry.
        """
        if not self._edges:
            self.draw()
            return
        try:
            self.canvas.update_idletasks()
        except tk.TclError:
            pass
        bbox = self._selected_bbox()
        if bbox is None:
            return
        self._position_edges(bbox)
        if self._handles:
            self._position_handles(bbox)

    def clear(self) -> None:
        """Hide every chrome item but leave the frames + pool in place
        so the next ``draw`` can reuse them. Pre-pool this destroyed
        + recreated the whole selection chrome on every clear+draw
        cycle, which dominated the multi-select redraw budget.
        """
        self._set_edges_visible(False)
        self._set_handles_visible(False)
        for i in range(len(self._outline_pool)):
            self._hide_outline(i)

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
        r = self._resize
        self._resize = None
        try:
            self.canvas.configure(cursor="")
        except tk.TclError:
            pass
        if r is not None:
            node = self.project.get_widget(r["nid"])
            if node is not None:
                try:
                    end_x = int(node.properties.get("x", 0))
                    end_y = int(node.properties.get("y", 0))
                    end_w = int(node.properties.get("width", 0))
                    end_h = int(node.properties.get("height", 0))
                except (TypeError, ValueError):
                    end_x, end_y = r["start_x"], r["start_y"]
                    end_w, end_h = r["start_w"], r["start_h"]
                before = {
                    "x": r["start_x"], "y": r["start_y"],
                    "width": r["start_w"], "height": r["start_h"],
                }
                after = {
                    "x": end_x, "y": end_y,
                    "width": end_w, "height": end_h,
                }
                if before != after:
                    self.project.history.push(
                        ResizeCommand(r["nid"], before, after),
                    )
        self.draw()

    # ------------------------------------------------------------------
    # Internal rendering
    # ------------------------------------------------------------------
    def _selected_bbox(self) -> tuple[int, int, int, int] | None:
        """Canvas-coord bbox of the primary selected widget.
        Legacy wrapper around ``_bbox_for`` — kept so ``update()`` and
        any other single-select callers still work.
        """
        return self._bbox_for(self.project.selected_id)

    def _bbox_for(
        self, widget_id: str | None,
    ) -> tuple[int, int, int, int] | None:
        """Canvas-coord bbox of a given widget. Works for both canvas
        children (created via ``create_window``) and nested children
        (placed inside a parent widget) — we read the widget's actual
        screen position so the parent chain doesn't matter.

        Assumes the caller already ran ``update_idletasks`` once so
        pending geometry tasks are flushed. Public entry points
        (``draw`` / ``update``) flush once at the top; skipping the
        flush per-call avoids N redundant flushes when iterating N
        selected widgets in a multi-selection.
        """
        if widget_id is None or widget_id not in self.widget_views:
            return None
        inner, _window_id = self.widget_views[widget_id]
        widget = self.anchor_views.get(widget_id, inner)
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

    def _edge_geoms(
        self, x1: int, y1: int, x2: int, y2: int,
    ) -> dict[str, tuple[int, int, int, int]]:
        """Return the ``{side: (x, y, w, h)}`` rectangle for each of
        the four selection-chrome edges around a widget bbox. Single
        source of truth for every positioning path.
        """
        ox1, oy1 = x1 - SELECTION_PAD, y1 - SELECTION_PAD
        ox2, oy2 = x2 + SELECTION_PAD, y2 + SELECTION_PAD
        w = ox2 - ox1
        h = oy2 - oy1
        t = RECT_THICKNESS
        return {
            "top":    (ox1, oy1, w, t),
            "bottom": (ox1, oy2 - t, w, t),
            "left":   (ox1, oy1, t, h),
            "right":  (ox2 - t, oy1, t, h),
        }

    # ------------------------------------------------------------------
    # Primary chrome (pool-backed)
    # ------------------------------------------------------------------
    def _show_primary_chrome(self, widget_id, bbox) -> None:
        if bbox is None:
            self._set_edges_visible(False)
            self._set_handles_visible(False)
            return
        self._ensure_edges_allocated()
        self._position_edges(bbox)
        self._retag_entry(self._edges, widget_id)
        node = (
            self.project.get_widget(widget_id)
            if widget_id is not None else None
        )
        locked = node is not None and self._is_locked(node)
        show_handles = not locked and self._handles_enabled()
        if not show_handles:
            self._set_handles_visible(False)
            return
        self._ensure_handles_allocated()
        self._position_handles(bbox)
        self._retag_entry(self._handles, widget_id)
        self._set_handles_visible(True)

    def _ensure_edges_allocated(self) -> None:
        if self._edges:
            return
        for side in ("top", "bottom", "left", "right"):
            self._edges[side] = self._allocate_edge_frame()

    def _ensure_handles_allocated(self) -> None:
        if self._handles:
            return
        for name in HANDLE_NAMES:
            self._handles[name] = self._allocate_handle_frame(name)

    def _position_edges(self, bbox) -> None:
        x1, y1, x2, y2 = bbox
        for side, (x, y, w, h) in self._edge_geoms(x1, y1, x2, y2).items():
            window_id, _ = self._edges[side]
            try:
                self.canvas.coords(window_id, x, y)
                self.canvas.itemconfigure(
                    window_id, width=max(1, w), height=max(1, h),
                    state="normal",
                )
            except tk.TclError:
                pass

    def _position_handles(self, bbox) -> None:
        x1, y1, x2, y2 = bbox
        for name, (window_id, _) in self._handles.items():
            hx, hy = self._handle_center(name, x1, y1, x2, y2)
            try:
                self.canvas.coords(window_id, hx, hy)
            except tk.TclError:
                pass

    def _set_edges_visible(self, visible: bool) -> None:
        state = "normal" if visible else "hidden"
        for window_id, _ in self._edges.values():
            try:
                self.canvas.itemconfigure(window_id, state=state)
            except tk.TclError:
                pass

    def _set_handles_visible(self, visible: bool) -> None:
        state = "normal" if visible else "hidden"
        for window_id, _ in self._handles.values():
            try:
                self.canvas.itemconfigure(window_id, state=state)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Multi-select outline pool
    # ------------------------------------------------------------------
    def _ensure_outline_allocated(self, index: int) -> None:
        while len(self._outline_pool) <= index:
            entry: dict[str, tuple[int, tk.Frame]] = {}
            for side in ("top", "bottom", "left", "right"):
                entry[side] = self._allocate_edge_frame()
            self._outline_pool.append(entry)

    def _position_outline(
        self, index: int, bbox, widget_id: str,
    ) -> None:
        entry = self._outline_pool[index]
        x1, y1, x2, y2 = bbox
        for side, (x, y, w, h) in self._edge_geoms(x1, y1, x2, y2).items():
            window_id, _ = entry[side]
            try:
                self.canvas.coords(window_id, x, y)
                self.canvas.itemconfigure(
                    window_id, width=max(1, w), height=max(1, h),
                    state="normal",
                )
            except tk.TclError:
                pass
        self._retag_entry(entry, widget_id)

    def _hide_outline(self, index: int) -> None:
        if index >= len(self._outline_pool):
            return
        entry = self._outline_pool[index]
        for window_id, _ in entry.values():
            try:
                self.canvas.itemconfigure(window_id, state="hidden")
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Frame allocation + per-widget tag bookkeeping
    # ------------------------------------------------------------------
    def _allocate_edge_frame(self) -> tuple[int, tk.Frame]:
        """Create one edge frame + its canvas window item, hidden by
        default. Position + state get updated by the caller.
        """
        frame = tk.Frame(
            self.canvas, bg=RECT_COLOR, highlightthickness=0,
            width=1, height=1,
        )
        window_id = self.canvas.create_window(
            0, 0, window=frame, anchor="nw",
            width=1, height=1, state="hidden",
            tags=("selection_chrome",),
        )
        frame.lift()
        return window_id, frame

    def _allocate_handle_frame(self, name: str) -> tuple[int, tk.Frame]:
        """Create one resize-handle frame + its canvas window item,
        hidden by default. Bindings get wired once — the pool keeps
        the same frame alive across every ``draw`` so the handle
        name ↔ cursor ↔ begin_resize(name) mapping stays stable.
        """
        frame = tk.Frame(
            self.canvas, bg=HANDLE_FILL,
            highlightthickness=1, highlightbackground=HANDLE_OUTLINE,
            width=HANDLE_SIZE, height=HANDLE_SIZE,
            cursor=HANDLE_CURSORS[name],
        )
        window_id = self.canvas.create_window(
            0, 0, window=frame, anchor="center",
            width=HANDLE_SIZE, height=HANDLE_SIZE,
            state="hidden",
            tags=("selection_chrome",),
        )
        frame.bind(
            "<ButtonPress-1>",
            lambda e, n=name: self.begin_resize(e, n),
            add="+",
        )
        frame.bind("<B1-Motion>", self.update_resize, add="+")
        frame.bind("<ButtonRelease-1>", self.end_resize, add="+")
        frame.lift()
        return window_id, frame

    def _retag_entry(
        self, entry: dict[str, tuple[int, tk.Frame]], widget_id,
    ) -> None:
        """Swap every ``chrome_wid_*`` tag on the entry's canvas
        items to ``chrome_wid_{widget_id}``. Drag.py relies on this
        per-widget tag to move only the chrome tied to widgets that
        actually shifted.
        """
        if widget_id is None:
            return
        new_tag = f"chrome_wid_{widget_id}"
        for window_id, _ in entry.values():
            try:
                current = self.canvas.gettags(window_id)
            except tk.TclError:
                continue
            if new_tag in current:
                continue
            for t in current:
                if t.startswith("chrome_wid_") and t != new_tag:
                    try:
                        self.canvas.dtag(window_id, t)
                    except tk.TclError:
                        pass
            try:
                self.canvas.addtag_withtag(new_tag, window_id)
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
