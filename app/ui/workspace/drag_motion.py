"""Motion-tick helpers for ``WidgetDragController``.

Owns the per-frame logic that runs while ``<B1-Motion>`` is firing:

* ``motion_feedback`` — for managed-layout (pack / grid) drags,
  paints the drag ghost via ``DragGhost`` and the grid-cell
  highlight via ``GridDropIndicator``. Returns True when the cursor
  is hovering a grid cell so the orchestrator can skip place-group
  motion math entirely.
* ``grid_candidate_at`` — hit-tests the cached grid containers
  (from press-time) by canvas bbox, returning the deepest match for
  grid-in-grid layouts.
* ``compute_drag_snap`` — resolves snap deltas for single-widget
  place drags via ``app.core.snap.compute_snap_offsets``. Multi-
  widget drags skip snap (group cohesion > arbitrary primary
  alignment).
* ``draw_snap_guides`` / ``clear_snap_guides`` — pink alignment
  guides rendered as ``tk.Frame`` children of the canvas so they
  stack above the document frames (canvas line items would sit
  underneath).
* ``motion_place_group`` — the main per-tick worker for place-
  managed children: translates the press delta into per-widget
  visual + model updates, supports two modes (live widget drag
  vs hidden-mode placeholder rect).

Lives on ``WidgetDragController.motion``; reads/writes the
``controller._drag`` dict for gesture state.
"""
from __future__ import annotations

import tkinter as tk


DRAG_THRESHOLD = 5  # mirrored from drag.py for the threshold defense check


class DragMotion:
    """Per-controller motion-time helper. See module docstring."""

    def __init__(self, controller) -> None:
        self.controller = controller
        # Snap-guide widgets are owned by the helper so clear()
        # doesn't depend on the controller stashing them under an
        # attribute name.
        self._snap_guide_widgets: list = []

    # ------------------------------------------------------------------
    # Cell + ghost feedback
    # ------------------------------------------------------------------
    def motion_feedback(
        self, nid: str, cx: float, cy: float,
        node, src_layout: str,
    ) -> bool:
        """Update the grid cell highlight + drag ghost. Returns True
        when the motion is fully handled (cursor sitting on a grid
        cell) so ``on_motion`` can skip the place-group path below.

        Hit-tests only the grid containers cached at press time (see
        ``DragClickResolver.collect_grid_candidates``) rather than
        walking every widget per tick — the common case (no grid
        containers) skips the search entirely; the typical case (1-2
        grid containers) is O(1-2) instead of O(N).
        """
        ctl = self.controller
        # Ghost: pack/grid children can't move via x/y updates, so we
        # surface drag feedback as canvas items near the cursor.
        # place children already slide under the cursor — no ghost.
        if src_layout in ("vbox", "hbox", "grid"):
            ctl.ghost.update(node, cx, cy)
        candidates = ctl._drag.get("grid_candidates") or []
        if not candidates:
            ctl._grid_indicator.clear()
            return False
        target = self._grid_candidate_at(cx, cy, candidates)
        if target is not None:
            row, col = ctl._grid_indicator.cell_at(target, cx, cy)
            ctl._grid_indicator.draw(target, row, col)
            return True
        # Cursor left every grid container — erase stale highlight.
        ctl._grid_indicator.clear()
        return False

    def _grid_candidate_at(
        self, cx: float, cy: float, candidates: list,
    ) -> object:
        """Return the deepest grid container whose canvas bbox
        contains (cx, cy), or None. Depth is inferred from parent
        chain length — deeper wins so a grid-inside-grid scenario
        lands on the inner cell.
        """
        ctl = self.controller
        best = None
        best_depth = -1
        for cand in candidates:
            entry = ctl.widget_views.get(cand.id)
            if entry is None:
                continue
            widget, _ = entry
            bbox = ctl.workspace._widget_canvas_bbox(widget)
            if bbox is None:
                continue
            x1, y1, x2, y2 = bbox
            if not (x1 <= cx <= x2 and y1 <= cy <= y2):
                continue
            depth = 0
            anc = cand.parent
            while anc is not None:
                depth += 1
                anc = anc.parent
            if depth > best_depth:
                best = cand
                best_depth = depth
        return best

    # ------------------------------------------------------------------
    # Snap-to-siblings + container guides
    # ------------------------------------------------------------------
    def _compute_drag_snap(
        self, primary_node, dx_logical: int, dy_logical: int,
    ) -> tuple[int, int, list[int], list[int]]:
        """Resolve snap deltas for the current motion tick.

        Snaps the primary widget's would-be bbox against its
        siblings' bboxes plus the parent container's edges /
        centre. Multi-widget drags skip snap (group cohesion is
        more important than aligning an arbitrary primary).
        Returns ``(snap_dx, snap_dy, guide_xs, guide_ys)`` — all
        in logical (parent-local) coordinates.
        """
        ctl = self.controller
        if len(ctl._drag.get("group_starts") or {}) != 1:
            return 0, 0, [], []
        sx, sy = ctl._drag["group_starts"][primary_node.id]
        try:
            w = int(primary_node.properties.get("width", 0) or 0)
            h = int(primary_node.properties.get("height", 0) or 0)
        except (TypeError, ValueError):
            return 0, 0, [], []
        new_x = sx + dx_logical
        new_y = sy + dy_logical
        bbox = (new_x, new_y, new_x + w, new_y + h)
        parent = primary_node.parent
        if parent is None:
            siblings = [
                n for n in ctl.project.active_document.root_widgets
                if n.id != primary_node.id
            ]
            doc = ctl.project.active_document
            container_size = (doc.width, doc.height)
        else:
            siblings = [
                n for n in parent.children
                if n.id != primary_node.id
            ]
            container_size = (
                int(parent.properties.get("width", 0) or 0),
                int(parent.properties.get("height", 0) or 0),
            )
        sibling_bboxes: list[tuple[int, int, int, int]] = []
        for s in siblings:
            try:
                sxx = int(s.properties.get("x", 0) or 0)
                syy = int(s.properties.get("y", 0) or 0)
                sww = int(s.properties.get("width", 0) or 0)
                shh = int(s.properties.get("height", 0) or 0)
            except (TypeError, ValueError):
                continue
            sibling_bboxes.append((sxx, syy, sxx + sww, syy + shh))
        from app.core.snap import compute_snap_offsets
        return compute_snap_offsets(
            bbox, sibling_bboxes, container_size,
        )

    def _draw_snap_guides(
        self, primary_node, guide_xs: list[int], guide_ys: list[int],
    ) -> None:
        """Render the pink alignment lines for the active snap targets.

        Tk canvas line items always sit BELOW any window items
        (frame widgets), so the guides would be hidden inside the
        document frame. Use plain ``tk.Frame`` widgets placed
        directly on the canvas instead — those stack with the
        document frames and ``.lift()`` floats them on top.
        Lines span the primary widget's parent (or doc, when
        top-level) so the user sees clearly which container
        reference they hit.
        """
        ctl = self.controller
        self.clear_snap_guides()
        if not guide_xs and not guide_ys:
            return
        entry = ctl.widget_views.get(primary_node.id)
        if entry is None:
            return
        widget, _wid = entry
        bbox = ctl.workspace._widget_canvas_bbox(widget)
        if bbox is None:
            return
        canvas_scale = ctl.zoom.canvas_scale or 1.0
        try:
            px = int(primary_node.properties.get("x", 0) or 0)
            py = int(primary_node.properties.get("y", 0) or 0)
        except (TypeError, ValueError):
            return
        # Parent origin in canvas coords — derived from the widget's
        # known canvas bbox + its known logical position; saves a
        # second lookup for the parent's canvas item.
        parent_cx = bbox[0] - int(px * canvas_scale)
        parent_cy = bbox[1] - int(py * canvas_scale)
        parent = primary_node.parent
        if parent is None:
            doc = ctl.project.active_document
            cw_logical = doc.width
            ch_logical = doc.height
        else:
            cw_logical = int(parent.properties.get("width", 0) or 0)
            ch_logical = int(parent.properties.get("height", 0) or 0)
        cw_canvas = int(cw_logical * canvas_scale)
        ch_canvas = int(ch_logical * canvas_scale)
        guides: list[tk.Frame] = []
        # Guide widgets are children of the canvas, so place() coords
        # use canvas-internal pixels — convert canvas-coordinate
        # values via canvasx/canvasy inverse: we already have the
        # absolute canvas coords from _widget_canvas_bbox, but
        # ``place`` uses canvas widget-local coords (without scroll
        # offset). The canvas's scroll offset is the difference.
        try:
            scroll_off_x = int(ctl.canvas.canvasx(0))
            scroll_off_y = int(ctl.canvas.canvasy(0))
        except tk.TclError:
            scroll_off_x, scroll_off_y = 0, 0
        for gx in guide_xs:
            xc = parent_cx + int(gx * canvas_scale)
            try:
                f = tk.Frame(
                    ctl.canvas, bg="#5bc0f8",
                    borderwidth=0, highlightthickness=0,
                )
                f.place(
                    x=xc - scroll_off_x,
                    y=parent_cy - scroll_off_y,
                    width=1, height=ch_canvas,
                )
                f.lift()
                guides.append(f)
            except tk.TclError:
                pass
        for gy in guide_ys:
            yc = parent_cy + int(gy * canvas_scale)
            try:
                f = tk.Frame(
                    ctl.canvas, bg="#5bc0f8",
                    borderwidth=0, highlightthickness=0,
                )
                f.place(
                    x=parent_cx - scroll_off_x,
                    y=yc - scroll_off_y,
                    width=cw_canvas, height=1,
                )
                f.lift()
                guides.append(f)
            except tk.TclError:
                pass
        self._snap_guide_widgets = guides

    def clear_snap_guides(self) -> None:
        for guide in self._snap_guide_widgets or []:
            try:
                guide.destroy()
            except (tk.TclError, AttributeError):
                pass
        self._snap_guide_widgets = []

    # ------------------------------------------------------------------
    # place-group motion
    # ------------------------------------------------------------------
    def motion_place_group(
        self, event, dx_root: int, dy_root: int,
    ) -> None:
        """Translate the press-time delta into per-widget visual +
        model updates for place-managed children.

        - Hidden mode: widgets + chromes are already hidden, so we
          just slide the dashed placeholder rect; the model still
          gets updated so release can apply_all() to the final x/y.
        - Normal mode: two ``canvas.move`` calls via shared tags
          shift every canvas-hosted widget + chrome in the group;
          nested place children fall through to per-widget
          ``place_configure`` since tags can't reach them.
        """
        ctl = self.controller
        # Two scales in play:
        # - ``canvas_scale`` (= user_zoom × DPI_factor) maps physical
        #   cursor pixels to logical model pixels — used for the delta.
        # - ``zoom.value`` (= user_zoom only) is what ``_place_nested``
        #   feeds to ``.place(x, y)``, because tk already applies DPI
        #   scaling to place() args on DPI-aware windows. Drag motion
        #   must re-use that same scale when writing back to
        #   ``place_configure`` so the widget lands where the cursor
        #   is instead of drifting by DPI_factor on nested children.
        canvas_scale = ctl.zoom.canvas_scale or 1.0
        place_scale = ctl.zoom.value or 1.0
        dx_logical = int(dx_root / canvas_scale)
        dy_logical = int(dy_root / canvas_scale)
        dx_tick = event.x_root - ctl._drag["last_mx"]
        dy_tick = event.y_root - ctl._drag["last_my"]
        hidden_mode = ctl._drag.get("hidden_mode", False)
        # Snap-to-siblings + container guides. Single-widget place
        # drags only — multi-widget snap would have to pick which
        # group member's edge counts and tends to fight the user.
        # Hold Alt to bypass snap (mask 0x20000 on Windows / Linux).
        primary_node = ctl.project.get_widget(ctl._drag["nid"])
        snap_dx_logical = 0
        snap_dy_logical = 0
        prev_snap_dx = ctl._drag.get("snap_dx_logical", 0)
        prev_snap_dy = ctl._drag.get("snap_dy_logical", 0)
        alt_held = bool(event.state & 0x20000)
        # Per-document toggles in Window properties — both default ON
        # for legacy projects (.get with True fallback) so existing
        # behaviour is unchanged when the keys are missing.
        active_doc = ctl.project.active_document
        if active_doc is not None:
            lines_enabled = bool(
                active_doc.window_properties.get(
                    "alignment_lines_enabled", True,
                ),
            )
            snap_enabled = bool(
                active_doc.window_properties.get("snap_enabled", True),
            )
        else:
            lines_enabled = True
            snap_enabled = True
        if (
            primary_node is not None
            and not hidden_mode
            and not alt_held
            and (lines_enabled or snap_enabled)
        ):
            snap_dx_logical, snap_dy_logical, gxs, gys = (
                self._compute_drag_snap(
                    primary_node, dx_logical, dy_logical,
                )
            )
            if lines_enabled:
                self._draw_snap_guides(primary_node, gxs, gys)
            else:
                self.clear_snap_guides()
            if not snap_enabled:
                snap_dx_logical = 0
                snap_dy_logical = 0
        else:
            self.clear_snap_guides()
        # Apply snap to the model coords; visual canvas item move
        # also gets the snap delta on top of the raw cursor tick so
        # the widget on canvas tracks the snapped logical position
        # (otherwise the visual would drift off the snapped edge).
        dx_logical += snap_dx_logical
        dy_logical += snap_dy_logical
        snap_visual_dx = int(
            (snap_dx_logical - prev_snap_dx) * canvas_scale,
        )
        snap_visual_dy = int(
            (snap_dy_logical - prev_snap_dy) * canvas_scale,
        )
        dx_tick += snap_visual_dx
        dy_tick += snap_visual_dy
        ctl._drag["snap_dx_logical"] = snap_dx_logical
        ctl._drag["snap_dy_logical"] = snap_dy_logical
        if dx_tick or dy_tick:
            if hidden_mode:
                pid = ctl._drag.get("placeholder_id")
                if pid is not None:
                    try:
                        ctl.canvas.move(pid, dx_tick, dy_tick)
                    except tk.TclError:
                        pass
            else:
                try:
                    ctl.canvas.move("drag_group", dx_tick, dy_tick)
                except tk.TclError:
                    pass
                try:
                    ctl.canvas.move(
                        "drag_chrome_group", dx_tick, dy_tick,
                    )
                except tk.TclError:
                    pass
        # Model update: write x / y to the nodes directly (bypasses
        # project.update_property's event bus for the duration of the
        # gesture so Inspector / Object Tree aren't re-rendered on
        # every motion). Release fires one property_changed pair per
        # moved widget to resync downstream panels.
        for wid, (sx, sy) in ctl._drag["group_starts"].items():
            new_x = sx + dx_logical
            new_y = sy + dy_logical
            w_node = ctl.project.get_widget(wid)
            if w_node is None:
                continue
            w_node.properties["x"] = new_x
            w_node.properties["y"] = new_y
            if hidden_mode:
                continue  # widgets are invisible — skip tk calls
            entry = ctl.widget_views.get(wid)
            if entry is None:
                continue
            w_widget, w_window_id = entry
            if w_window_id is None:
                # Nested place child — ``drag_group`` can't reach it;
                # keep it in sync via ``.place(...)``. Must use ``.place``
                # (not ``.place_configure``) because CTk only overrides
                # the former with its DPI scaling wrapper — calling
                # ``place_configure`` bypasses ``_apply_argument_scaling``
                # and lands the widget at raw tk pixels while the
                # initial ``_place_nested`` call routed through CTk's
                # scaling, causing a cross-DPI jump on first drag tick.
                try:
                    if w_widget.winfo_manager() == "place":
                        w_widget.place(
                            x=int(new_x * place_scale),
                            y=int(new_y * place_scale),
                        )
                except tk.TclError:
                    pass
        ctl._drag["last_mx"] = event.x_root
        ctl._drag["last_my"] = event.y_root
