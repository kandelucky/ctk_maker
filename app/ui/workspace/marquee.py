"""Marquee (drag-rect on empty canvas → multi-select) sidecar.

Owns the canvas-level click / motion / release dispatch plus the
marquee-rect drawing + hit-testing.

* **Click** decides between three branches by inspecting ``_tool``
  and what canvas item the cursor is over: chrome tag → no-op
  (chrome's own tag_bind handlers ran), Hand tool → start pan,
  Select / Edit on empty → arm marquee state and defer the
  deselect to release so a past-threshold drag can grow into a
  rectangle.
* **Motion** dispatches between chrome-drag-in-progress (highest
  priority), Hand-tool pan, and marquee rect update.
* **Release** ends the chrome drag or pan, or finalises the
  marquee — plain click clears the selection (Shift preserves it),
  drag past threshold runs the hit-test and applies the resulting
  set (Shift adds, plain replaces).

Hit-testing uses touch overlap (Photoshop / Illustrator
convention), and Children stay out of the result so the marquee
picks the whole Frame rather than its inner pieces.
"""
from __future__ import annotations

import tkinter as tk

from app.ui.workspace.chrome import CHROME_TAG
from app.ui.workspace.controls import TOOL_EDIT, TOOL_HAND, TOOL_SELECT


_MARQUEE_THRESHOLD_PX = 5


class MarqueeSelection:
    """Canvas click / motion / release + marquee rect lifecycle."""

    def __init__(self, workspace) -> None:
        self.workspace = workspace

    # ------------------------------------------------------------------
    # Canvas dispatch (Button-1)
    # ------------------------------------------------------------------
    def on_canvas_click(self, event) -> str | None:
        ws = self.workspace
        if event.widget is not ws.canvas:
            return None
        # If the click landed on a chrome item (title bar strip,
        # settings icon, min/close glyphs), the tag_bind handlers
        # already processed it — do NOT run the default
        # deselect-everything behaviour which would undo the
        # selection the tag handler just set. `"current"` is tk's
        # special tag for the item the cursor is hovering over.
        for item in ws.canvas.find_withtag("current"):
            if CHROME_TAG in ws.canvas.gettags(item):
                return "break"
        if ws._tool == TOOL_HAND:
            ws._begin_pan(event)
            return "break"
        # Selection handles are now embedded widgets that capture
        # Button-1 directly, so canvas clicks can't land on them.
        # If the click landed on empty area of a non-active document,
        # switch to that doc before deselecting — otherwise clicking
        # into a background form does nothing and the user has to
        # tap the title bar to change focus.
        cx, cy = ws._screen_to_canvas(event.x_root, event.y_root)
        doc = ws._find_document_at_canvas(cx, cy)
        if doc is not None and doc.id != ws.project.active_document_id:
            ws.project.set_active_document(doc.id)
        # Marquee selection on either Select or Edit tool. Don't
        # deselect immediately — defer to release so a drag past the
        # threshold can define a new selection. State 0x0001 is the
        # Tk Shift-pressed bitmask.
        if ws._tool in (TOOL_SELECT, TOOL_EDIT):
            ws._marquee_state = {
                "start_x": cx, "start_y": cy,
                "shift": bool(event.state & 0x0001),
                "rect_id": None,
                "active": False,
            }
            return None
        ws.project.select_widget(None)
        return None

    def on_canvas_motion(self, event) -> str | None:
        ws = self.workspace
        # Chrome drag in progress wins over every other motion
        # handler — it needs every single Button-1 motion, even when
        # the cursor slips off the title bar items mid-gesture.
        if ws.chrome is not None and ws.chrome.is_dragging():
            return ws.chrome.drive_drag(event)
        if ws._tool == TOOL_HAND and ws._pan_state is not None:
            ws._update_pan(event)
            return "break"
        if ws._marquee_state is not None:
            return self._update_marquee(event)
        return None

    def on_canvas_release(self, event) -> str | None:
        ws = self.workspace
        # Canvas-level release terminates any in-progress chrome drag
        # that started on a title bar but slipped off — same reason
        # the motion handler has a canvas-level fallback.
        if ws.chrome is not None and ws.chrome.is_dragging():
            ws.chrome.end_drag(ws.chrome.current_drag_doc_id())
            return "break"
        if ws._tool == TOOL_HAND:
            ws._end_pan(event)
            return "break"
        if ws._marquee_state is not None:
            return self._finish_marquee(event)
        return None

    # ------------------------------------------------------------------
    # Marquee rect lifecycle
    # ------------------------------------------------------------------
    def _update_marquee(self, event) -> str | None:
        ws = self.workspace
        state = ws._marquee_state
        if state is None:
            return None
        cx, cy = ws._screen_to_canvas(event.x_root, event.y_root)
        sx, sy = state["start_x"], state["start_y"]
        if not state["active"]:
            # Threshold guard so a plain click doesn't draw a
            # zero-pixel rect or trigger the marquee branch in
            # release.
            if max(abs(cx - sx), abs(cy - sy)) < _MARQUEE_THRESHOLD_PX:
                return None
            state["active"] = True
            state["rect_id"] = ws.canvas.create_rectangle(
                sx, sy, cx, cy,
                outline="#5bc0f8", dash=(5, 4), width=2,
                tags=("marquee_rect",),
            )
        else:
            try:
                ws.canvas.coords(state["rect_id"], sx, sy, cx, cy)
            except tk.TclError:
                pass
        return None

    def _finish_marquee(self, event) -> str | None:
        ws = self.workspace
        state = ws._marquee_state
        ws._marquee_state = None
        if state is None:
            return None
        was_drag = state["active"]
        # Tear down the dashed rect first regardless of outcome —
        # leaving it on a corrupted state would confuse the next
        # selection cycle.
        rect_id = state.get("rect_id")
        if rect_id is not None:
            try:
                ws.canvas.delete(rect_id)
            except tk.TclError:
                pass
        if not was_drag:
            # Plain click on empty area — match legacy behaviour:
            # clear the selection (Shift-click on empty preserves
            # the existing set so the user can keep building it).
            if not state["shift"]:
                ws.project.select_widget(None)
            return None
        # Drag completed past the threshold — compute the rect, find
        # widgets it overlaps, and apply the selection.
        cx, cy = ws._screen_to_canvas(event.x_root, event.y_root)
        sx, sy = state["start_x"], state["start_y"]
        rect = (
            min(sx, cx), min(sy, cy),
            max(sx, cx), max(sy, cy),
        )
        hit_ids = self._marquee_intersected_widgets(rect)
        if state["shift"]:
            # Add to the existing selection — same modifier
            # convention as Object Tree multi-select.
            ids = set(ws.project.selected_ids or set()) | hit_ids
        else:
            ids = hit_ids
        if ids:
            primary = (
                ws.project.selected_id
                if state["shift"] and ws.project.selected_id in ids
                else next(iter(ids))
            )
            ws.project.set_multi_selection(ids, primary=primary)
            # Multi-select in Edit mode is ambiguous (resize handles
            # only target one widget), so flip to Select tool when
            # the marquee picked up more than one widget — mirrors
            # the existing _select_all_in_doc auto-switch.
            if len(ids) > 1 and ws.controls.tool == TOOL_EDIT:
                ws.controls.set_tool(TOOL_SELECT)
        elif not state["shift"]:
            ws.project.select_widget(None)
        return None

    def _marquee_intersected_widgets(
        self, rect: tuple[float, float, float, float],
    ) -> set[str]:
        """Top-level widgets in the active document whose canvas
        bbox overlaps ``rect`` (touch mode — any overlap counts).
        Children stay out of the result so a marquee picks the
        whole Frame, not its inner pieces; users still drill in
        with a click for individual children.
        """
        ws = self.workspace
        rl, rt, rr, rb = rect
        hits: set[str] = set()
        doc = ws.project.active_document
        if doc is None:
            return hits
        for node in doc.root_widgets:
            if not getattr(node, "visible", True):
                continue
            view = ws.widget_views.get(node.id)
            if view is None:
                continue
            widget, _wid = view
            bbox = ws._widget_canvas_bbox(widget)
            if bbox is None:
                continue
            wl, wt, wr, wb = bbox
            # Touch test — any overlap (Photoshop / Illustrator
            # convention; Figma uses fully-contained instead).
            if wr < rl or wl > rr or wb < rt or wt > rb:
                continue
            hits.add(node.id)
        return hits
