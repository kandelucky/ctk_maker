"""Grid cell highlight for drag-to-cell drops.

Extracted from the drag controller so the geometry + stripe-frame
bookkeeping lives in one place. The indicator is a 4-stripe outline
laid down by ``.place()`` around the target cell — a single solid
rectangle would cover whatever's below, and canvas primitives can't
render above a ``create_window`` Frame, so the border is faked with
four thin stripe frames parented to the container widget itself.

Stripes are created ONCE per gesture and repositioned on each motion
event. Destroying + recreating every tick freezes the UI. The
indicator keeps a ``(container_id, row, col)`` cache key so repeated
calls for the same cell are a no-op.
"""

from __future__ import annotations

import tkinter as tk

from app.widgets.layout_schema import grid_effective_dims

GRID_HIGHLIGHT_COLOR = "#6fb4f0"
STRIPE_THICKNESS = 2
INSET = 2


class GridDropIndicator:
    """Owns the stripe frames + cache key for the grid cell overlay.

    One instance per workspace lives on the drag controller. Callers
    drive it via ``cell_at`` / ``draw`` during motion and ``clear``
    on release.
    """

    def __init__(self, workspace) -> None:
        self.workspace = workspace
        self._stripes: tuple[tk.Frame, ...] | None = None
        self._stripe_parent: tk.Widget | None = None
        self._cache_key: tuple | None = None

    # ------------------------------------------------------------------
    # Public API — match the old drag-controller method names.
    # ------------------------------------------------------------------
    def dimensions(self, container_node) -> tuple[int, int]:
        """Rows × cols of ``container`` — authoritative user-set
        ``grid_rows`` / ``grid_cols``. No auto-grow: children past
        capacity wrap into existing cells.
        """
        return grid_effective_dims(
            len(container_node.children), container_node.properties,
        )

    def cell_at(
        self, container_node, canvas_x: float, canvas_y: float,
    ) -> tuple[int, int]:
        """Map a canvas position to a (row, col) cell on
        ``container``. Clamped to the container's current cell grid;
        out-of-range clicks land on the nearest edge cell.
        """
        entry = self.workspace.widget_views.get(container_node.id)
        if entry is None:
            return (0, 0)
        widget, _ = entry
        bbox = self.workspace._widget_canvas_bbox(widget)
        if bbox is None:
            return (0, 0)
        x1, y1, x2, y2 = bbox
        nrows, ncols = self.dimensions(container_node)
        cell_w = (x2 - x1) / max(ncols, 1)
        cell_h = (y2 - y1) / max(nrows, 1)
        if cell_w <= 0 or cell_h <= 0:
            return (0, 0)
        col = int((canvas_x - x1) / cell_w)
        row = int((canvas_y - y1) / cell_h)
        col = max(0, min(ncols - 1, col))
        row = max(0, min(nrows - 1, row))
        return (row, col)

    def draw(self, container_node, row: int, col: int) -> None:
        """Paint a light-blue outline on the target cell. Idempotent
        per (container, row, col) — repeat calls are free.
        """
        cache_key = (container_node.id, row, col)
        if self._cache_key == cache_key:
            return
        entry = self.workspace.widget_views.get(container_node.id)
        if entry is None:
            self.clear()
            return
        container_widget, _ = entry
        try:
            cw = int(container_widget.winfo_width())
            ch = int(container_widget.winfo_height())
        except tk.TclError:
            self.clear()
            return
        if cw <= 0 or ch <= 0:
            self.clear()
            return
        nrows, ncols = self.dimensions(container_node)
        cell_w = cw / max(ncols, 1)
        cell_h = ch / max(nrows, 1)
        if cell_w <= 0 or cell_h <= 0:
            self.clear()
            return
        rx = int(col * cell_w) + INSET
        ry = int(row * cell_h) + INSET
        rw = max(1, int(cell_w) - INSET * 2)
        rh = max(1, int(cell_h) - INSET * 2)
        # Reparent stripes if the highlighted container changed under
        # us — stripes are ``place``-d inside the container widget,
        # so a switch requires a fresh set parented to the new widget.
        if (
            self._stripes is not None
            and self._stripe_parent is not container_widget
        ):
            self.clear()
        if self._stripes is None:
            try:
                self._stripes = tuple(
                    tk.Frame(
                        container_widget,
                        bg=GRID_HIGHLIGHT_COLOR,
                        bd=0, highlightthickness=0,
                    )
                    for _ in range(4)
                )
            except tk.TclError:
                return
            self._stripe_parent = container_widget
        top, bottom, left, right = self._stripes
        bw = STRIPE_THICKNESS
        try:
            top.place(x=rx, y=ry, width=rw, height=bw)
            bottom.place(x=rx, y=ry + rh - bw, width=rw, height=bw)
            left.place(x=rx, y=ry, width=bw, height=rh)
            right.place(x=rx + rw - bw, y=ry, width=bw, height=rh)
            for stripe in self._stripes:
                stripe.lift()
        except tk.TclError:
            self.clear()
            return
        self._cache_key = cache_key

    def clear(self) -> None:
        if self._stripes is not None:
            for stripe in self._stripes:
                try:
                    stripe.destroy()
                except tk.TclError:
                    pass
        self._stripes = None
        self._stripe_parent = None
        self._cache_key = None
