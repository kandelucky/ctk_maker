"""Drag-ghost overlay for layout-managed children.

pack / grid children can't visually slide under the cursor by
updating their x/y (the parent layout owns positioning), so the
drag controller renders a small label near the cursor as feedback
while a managed-layout widget is being dragged.

Two canvas items (a rectangle behind a text label) sharing the
``drag_ghost`` tag — a single ``canvas.move`` on that tag shifts
both per tick. Canvas items are orders of magnitude cheaper than
a per-drag Toplevel, so this stays smooth even at high zoom.

Lives on ``WidgetDragController.ghost``; read/written via
``controller._ghost_items`` + ``controller._ghost_last``.
"""
from __future__ import annotations

import tkinter as tk

from app.ui.system_fonts import ui_font


class DragGhost:
    """Per-controller ghost overlay manager."""

    def __init__(self, controller) -> None:
        self.controller = controller

    def update(self, node, cx: float, cy: float) -> None:
        """Draw (or slide) a label near the cursor so pack/grid
        children have drag feedback. Two canvas items — a filled rect
        behind a text label — both tagged ``drag_ghost`` so a single
        ``canvas.move`` on the tag shifts them together. Canvas items
        are orders of magnitude cheaper than a per-drag Toplevel.
        """
        if node is None:
            return
        ctl = self.controller
        canvas = ctl.canvas
        nx = int(cx) + 12
        ny = int(cy) + 12
        if ctl._ghost_items is None:
            label_text = node.name or node.widget_type
            try:
                text_id = canvas.create_text(
                    nx + 10, ny + 4,
                    text=label_text, anchor="nw",
                    font=ui_font(10, "bold"),
                    fill="white",
                    tags=("drag_ghost", "drag_ghost_text"),
                )
                bbox = canvas.bbox(text_id)
                if not bbox:
                    canvas.delete(text_id)
                    return
                rect_id = canvas.create_rectangle(
                    bbox[0] - 6, bbox[1] - 4,
                    bbox[2] + 6, bbox[3] + 4,
                    fill="#6366f1", outline="#3b8ed0", width=1,
                    tags=("drag_ghost", "drag_ghost_rect"),
                )
                # Text was created first (below rect on the stack);
                # raise it above the rect so the label shows through.
                canvas.tag_raise(text_id, rect_id)
            except tk.TclError:
                return
            ctl._ghost_items = {"text": text_id, "rect": rect_id}
            ctl._ghost_last = (nx, ny)
            return
        last_x, last_y = ctl._ghost_last or (nx, ny)
        dx = nx - last_x
        dy = ny - last_y
        if dx or dy:
            try:
                canvas.move("drag_ghost", dx, dy)
            except tk.TclError:
                return
            ctl._ghost_last = (nx, ny)

    def destroy(self) -> None:
        ctl = self.controller
        if ctl._ghost_items is not None:
            try:
                ctl.canvas.delete("drag_ghost")
            except tk.TclError:
                pass
            ctl._ghost_items = None
            ctl._ghost_last = None
