"""Drag release helpers for ``WidgetDragController``.

* ``teardown_hidden_mode`` — tear down the dashed-rect placeholder
  that ``DragClickResolver.enter_hidden_mode`` put up for large
  groups, restore the hidden widgets to ``state="normal"``, and
  ``zoom.apply_all`` so widgets slide to their final logical x/y.
* ``should_snap_back`` — decide whether a top-level drop is off-form
  and should bounce the group back to its press position. Two
  triggers: cursor landed in the void OR any group member ended up
  outside every document.
* ``apply_snap_back`` — restore every dragged widget's x/y to its
  press-time value + refresh the cross-doc visibility mask.
* ``record_bulk_move`` — push one ``BulkMoveCommand`` covering every
  widget shifted by this drag + fire the ``property_changed`` events
  the motion path skipped for perf.

State is read from the ``drag`` dict snapshot captured at press
time; the controller has already cleared its in-progress ``_drag``
attr before this helper runs (see ``WidgetDragController.on_release``).
"""
from __future__ import annotations

import tkinter as tk

from app.core.commands import BulkMoveCommand


class DragRelease:
    """Per-controller release-time helper. See module docstring."""

    def __init__(self, controller) -> None:
        self.controller = controller

    def teardown_hidden_mode(self, drag: dict) -> None:
        """Delete the dashed placeholder rect, unhide widgets +
        chromes, and slide them to their final position via a single
        ``apply_all``. Must run BEFORE the shared drag tags are
        removed — ``itemconfigure`` can't reach items once dtag has
        cleared their tag membership.
        """
        ctl = self.controller
        pid = drag.get("placeholder_id")
        if pid is not None:
            try:
                ctl.canvas.delete(pid)
            except tk.TclError:
                pass
        for tag in ("drag_group", "drag_chrome_group"):
            try:
                ctl.canvas.itemconfigure(tag, state="normal")
            except tk.TclError:
                pass
        # Widgets were frozen at their press-time canvas positions
        # during motion — run apply_all once to slide them to the
        # drag's final logical x/y.
        ctl.zoom.apply_all()

    def should_snap_back(
        self, cx_r: float, cy_r: float, drag: dict,
    ) -> bool:
        """Decide whether a top-level drop is off-form and should
        bounce the group back to its press position. Two triggers:

        1. The cursor landed in the void (no container, no doc).
        2. Any widget in the group ended up outside every document —
           a peripheral widget can get pushed off-form by a group
           delta even when the primary / cursor stayed inside.

        Cross-doc drops count as valid; the bounds test checks the
        drop's absolute canvas position against every doc's rect.
        """
        ctl = self.controller
        ws = ctl.workspace
        nid = drag["nid"]
        cursor_target = (
            ws._find_container_at(cx_r, cy_r, exclude_id=nid) is not None
            or ws._find_document_at_canvas(cx_r, cy_r) is not None
        )
        if not cursor_target:
            return True
        all_docs = list(ctl.project.documents)
        for wid in drag["group_starts"].keys():
            g_node = ctl.project.get_widget(wid)
            if g_node is None:
                continue
            doc = ctl.project.find_document_for_widget(wid)
            if doc is None:
                continue
            try:
                ex = int(g_node.properties.get("x", 0))
                ey = int(g_node.properties.get("y", 0))
                gw = int(g_node.properties.get("width", 0) or 0)
                gh = int(g_node.properties.get("height", 0) or 0)
            except (TypeError, ValueError):
                continue
            abs_x = doc.canvas_x + ex
            abs_y = doc.canvas_y + ey
            inside_any = any(
                d.canvas_x <= abs_x
                and abs_x + gw <= d.canvas_x + d.width
                and d.canvas_y <= abs_y
                and abs_y + gh <= d.canvas_y + d.height
                for d in all_docs
            )
            if not inside_any:
                return True
        return False

    def apply_snap_back(self, drag: dict) -> None:
        """Restore every dragged widget's x/y to its press-time value
        and kick the cross-doc visibility mask to hide / show widgets
        that may have slid under another doc during the gesture.
        """
        ctl = self.controller
        for wid, (sx, sy) in drag["group_starts"].items():
            ctl.project.update_property(wid, "x", sx)
            ctl.project.update_property(wid, "y", sy)
        ctl.workspace._update_widget_visibility_across_docs()

    def record_bulk_move(self, drag: dict) -> None:
        """Push one ``BulkMoveCommand`` covering every widget shifted
        by this drag + fire the ``property_changed`` events the motion
        path skipped for perf. One undo rewinds the whole gesture;
        single-widget drags degrade cleanly to a one-entry command.
        """
        ctl = self.controller
        moves: list = []
        for wid, (sx, sy) in drag["group_starts"].items():
            g_node = ctl.project.get_widget(wid)
            if g_node is None:
                continue
            try:
                ex = int(g_node.properties.get("x", 0))
                ey = int(g_node.properties.get("y", 0))
            except (TypeError, ValueError):
                ex, ey = sx, sy
            if (ex, ey) != (sx, sy):
                moves.append((
                    wid,
                    {"x": sx, "y": sy},
                    {"x": ex, "y": ey},
                ))
        if not moves:
            return
        ctl.project.history.push(BulkMoveCommand(moves))
        bus = ctl.project.event_bus
        for wid, _before, after in moves:
            for key, val in after.items():
                bus.publish("property_changed", wid, key, val)
