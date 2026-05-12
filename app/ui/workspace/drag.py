"""Widget drag-to-move + drag-to-reparent controller.

Holds the per-gesture drag state (``_drag``) and the three press /
motion / release orchestrators every canvas widget is bound to.

The actual logic lives in 5 helper sidecars (one level deeper than
the usual workspace sidecar pattern — the drag controller is itself
a ``Workspace`` sidecar, and these helpers carve up its surface):

* ``click_resolver`` (``drag_select.py``) — press-time selection
  policy, drill-down, group-tagging, hidden-mode placeholder.
* ``motion`` (``drag_motion.py``) — per-tick feedback, snap guides,
  place-group motion writer.
* ``ghost`` (``drag_ghost.py``) — drag-ghost label for managed-
  layout children that can't slide via x/y.
* ``release_handler`` (``drag_release.py``) — release-time tear-
  down, snap-back gate, bulk-move history.
* ``reparent`` (``drag_reparent.py``) — extract / cross-doc move /
  grid drop / single + group reparent.

External callers still talk to ``WidgetDragController.on_press`` /
``on_motion`` / ``on_release`` + the ``_resolve_click_target`` and
``_grid_indicator`` pass-throughs context-menu / palette-drop code
already depends on.
"""

from __future__ import annotations

import tkinter as tk

from app.ui.workspace.drag_ghost import DragGhost
from app.ui.workspace.drag_motion import DragMotion
from app.ui.workspace.drag_release import DragRelease
from app.ui.workspace.drag_reparent import DragReparent
from app.ui.workspace.drag_select import (
    HIDE_OUTLINE_COLOR,  # noqa: F401 — re-exported for tests
    HIDE_THRESHOLD,
    DragClickResolver,
)
from app.ui.workspace.grid_drop_indicator import GridDropIndicator

DRAG_THRESHOLD = 5


class WidgetDragController:
    """Per-workspace widget drag handler.

    All external state (project, canvas, zoom, selection, tool mode,
    lock/cover logic) is read through the workspace ref. The only
    state this class owns is the in-progress drag gesture; helpers
    read/write it through their ``self.controller._drag`` access.
    """

    # "Quick second click = drill" window. Longer than Windows'
    # double-click threshold (500 ms) — matches the rename-style
    # pause Explorer / Photoshop use, so a deliberate second click
    # feels distinct from both a double-click and a fresh session.
    _DRILL_WINDOW_MS = 800

    def __init__(self, workspace) -> None:
        self.workspace = workspace
        self._drag: dict | None = None
        # Drag ghost — two canvas items (bg rect + text label) drawn
        # near the cursor while a layout-managed child (pack / grid)
        # is being dragged. Canvas items are ~free compared to a
        # Toplevel window, so each motion is just a single tag move.
        # Place children don't need a ghost — their real widget slides
        # with the cursor via x/y updates already.
        self._ghost_items: dict | None = None
        self._ghost_last: tuple[int, int] | None = None
        # Grid cell outline painted while the cursor hovers over a
        # grid-layout container. Owns its own stripe frames + cache.
        self._grid_indicator = GridDropIndicator(workspace)
        # De-dup ButtonPress firings by tk event serial. Composite
        # widgets can fire the same press through a parent + child
        # binding both carrying different nids — running drill-down
        # twice in one event loop pass skips past the intended
        # container on the very first click.
        self._last_press_serial: int | None = None
        # Drill-down is gated by a fast-click window. Each resolved
        # click stamps the leaf widget id + timestamp; the next click
        # only drills one level when it lands on the same leaf within
        # ``_DRILL_WINDOW_MS``. Slow successive clicks reset to the
        # outermost ancestor so the user can drag the parent repeatedly
        # without clicking into children on every second press.
        self._last_click_leaf_id: str | None = None
        self._last_click_time_ms: int = 0
        # Helper sidecars. Each takes ``self`` (the controller) and
        # reads gesture state through it. See module docstring.
        self.click_resolver = DragClickResolver(self)
        self.motion = DragMotion(self)
        self.ghost = DragGhost(self)
        self.release_handler = DragRelease(self)
        self.reparent = DragReparent(self)

    # ------------------------------------------------------------------
    # Convenience accessors — keep call sites terse.
    # ------------------------------------------------------------------
    @property
    def project(self):
        return self.workspace.project

    @property
    def zoom(self):
        return self.workspace.zoom

    @property
    def canvas(self) -> tk.Canvas:
        return self.workspace.canvas

    @property
    def widget_views(self) -> dict:
        return self.workspace.widget_views

    def is_dragging(self) -> bool:
        return self._drag is not None and self._drag.get("moved", False)

    # ------------------------------------------------------------------
    # Pass-through shim — used by ContextMenu's right-click drill and
    # any other out-of-package caller that pre-existed the helper
    # split. Keeps the legacy ``self.drag_controller._resolve_click_target``
    # call site working unchanged.
    # ------------------------------------------------------------------
    def _resolve_click_target(self, clicked_nid: str) -> str | None:
        return self.click_resolver.resolve_click_target(clicked_nid)

    # ------------------------------------------------------------------
    # Bound handlers
    # ------------------------------------------------------------------
    def on_press(self, event, nid: str) -> str | None:
        ws = self.workspace
        if ws._tool == "hand":
            ws._begin_pan(event)
            return "break"
        # Clear any stale drag state from a prior interaction whose
        # ButtonRelease was lost (widget destroyed mid-drag, focus
        # switch to another toplevel, etc).
        self._drag = None
        # Suppress duplicate ButtonPress firings within a single tk
        # event loop pass — some composite widgets route the press
        # through both their own binding and an internal child's,
        # which would otherwise run drill-down twice and descend past
        # the intended container on the very first click.
        serial = getattr(event, "serial", None)
        if serial is not None and self._last_press_serial == serial:
            return "break"
        self._last_press_serial = serial
        # Switch active document to the one owning this widget so
        # drag / resize coords are computed against the right form's
        # offset instead of the previously-active form's.
        owning_doc = self.project.find_document_for_widget(nid)
        if owning_doc is not None and (
            self.project.active_document is not owning_doc
        ):
            self.project.set_active_document(owning_doc.id)
        resolved_nid = self.click_resolver.resolve_selection(event, nid)
        if resolved_nid is None:
            # Canvas click landed on a locked widget with no unlocked
            # ancestor — block entirely. Locked widgets can only be
            # interacted with from the Object Tree.
            return "break"
        if ws._effective_locked(resolved_nid):
            # Defensive: should never happen because resolve_selection
            # filters locked targets out, but keep the guard so a
            # missed code path never starts a drag on a locked widget.
            return "break"
        node = self.project.get_widget(resolved_nid)
        if node is None:
            return
        try:
            start_x = int(node.properties.get("x", 0))
            start_y = int(node.properties.get("y", 0))
        except (ValueError, TypeError):
            start_x, start_y = 0, 0
        group_starts = self.click_resolver.build_group_starts(resolved_nid)
        self._drag = {
            "nid": resolved_nid,
            # ``click_nid`` is the widget that received the tk event;
            # motion events come through its binding so we match the
            # incoming nid against click_nid, not the drill-down one.
            "click_nid": nid,
            "start_x": start_x,
            "start_y": start_y,
            "press_mx": event.x_root,
            "press_my": event.y_root,
            # Last seen screen coords — used to canvas.move() the
            # selection chrome by the per-tick delta so the rect +
            # handles track the cursor as a single tagged group.
            "last_mx": event.x_root,
            "last_my": event.y_root,
            "moved": False,
            # Per-widget starting position for group drag — iterated
            # on every motion event so all selected place widgets
            # shift by the same delta.
            "group_starts": group_starts,
            # Precomputed list of grid containers so on_motion can
            # hit-test just these instead of walking every widget in
            # the project. Skips `_find_container_at` entirely when
            # the project has no grid containers — the dominant case.
            "grid_candidates": self.click_resolver.collect_grid_candidates(
                exclude_id=resolved_nid,
            ),
        }
        self.click_resolver.tag_drag_group(group_starts)
        # Lift every dragged canvas-hosted widget to the top of the
        # canvas stack for the duration of the gesture. Without this,
        # dragging a widget "into" a Frame that was added later reads
        # as the widget disappearing behind the Frame, because later
        # canvas window items stack above earlier ones. Lift is
        # transient — the next ``_redraw_document`` restores the
        # project-tree ordering automatically.
        for wid in group_starts.keys():
            entry = self.widget_views.get(wid)
            if entry is None:
                continue
            _, window_id = entry
            if window_id is None:
                continue
            try:
                self.canvas.tag_raise(window_id)
            except tk.TclError:
                pass
        # Ghost mode for large groups — hide every tagged widget +
        # chrome and draw a dashed outline rect the size of the group's
        # bounding box. Motion just translates the rect; release runs
        # apply_all once to put widgets at their final positions.
        if len(group_starts) >= HIDE_THRESHOLD:
            self.click_resolver.enter_hidden_mode(group_starts)
        return "break"

    def on_motion(self, event, nid: str) -> None:
        ws = self.workspace
        if ws._tool == "hand":
            ws._update_pan(event)
            return
        # Defense: <B1-Motion> should only fire while button 1 is
        # held. If the state mask says otherwise, a prior release
        # was missed — drop the stale drag and refuse to move.
        if not (event.state & 0x0100):
            self._drag = None
            self._grid_indicator.clear()
            self.ghost.destroy()
            return
        if (
            self._drag is None
            or self._drag.get("click_nid", self._drag["nid"]) != nid
        ):
            return
        from app.widgets.layout_schema import normalise_layout_type
        nid = self._drag["nid"]
        dx_root = event.x_root - self._drag["press_mx"]
        dy_root = event.y_root - self._drag["press_my"]
        if not self._drag["moved"]:
            if (
                abs(dx_root) < DRAG_THRESHOLD
                and abs(dy_root) < DRAG_THRESHOLD
            ):
                return
            self._drag["moved"] = True
        cx, cy = ws._screen_to_canvas(event.x_root, event.y_root)
        node = self.project.get_widget(nid)
        src_layout = (
            normalise_layout_type(
                node.parent.properties.get("layout_type", "place"),
            ) if node is not None and node.parent is not None else "place"
        )
        # Ghost / grid-cell feedback for managed parents. Returns True
        # when the cursor is hovering a grid cell — the whole motion
        # is "target feedback only", no x/y updates.
        if self.motion.motion_feedback(nid, cx, cy, node, src_layout):
            return
        # pack / grid parent: skip x/y updates — their positions are
        # owned by the geometry manager, and release either reparents
        # or snaps back to the captured start.
        if src_layout != "place":
            return
        self.motion.motion_place_group(event, dx_root, dy_root)

    def on_release(self, event, _nid: str) -> None:
        ws = self.workspace
        if ws._tool == "hand":
            ws._end_pan(event)
            return
        # Snap guides only live for the duration of the gesture —
        # release tears them down regardless of how the drag ends
        # (drop / snap-back / no-op click).
        self.motion.clear_snap_guides()
        drag = self._drag
        # Clear drag state BEFORE firing any project mutations so
        # ``_schedule_selection_redraw`` stops short-circuiting on
        # ``is_dragging()``. With the guard on, release-time updates
        # (grid snap, reparent, move) would leave selection handles
        # lingering at the pre-drop spot until the next UI event.
        self._drag = None
        self._grid_indicator.clear()
        self.ghost.destroy()
        if drag is not None and drag.get("hidden_mode"):
            self.release_handler.teardown_hidden_mode(drag)
        # Remove the shared drag tags — leaving them around would
        # accidentally re-tag the same items on the next drag start.
        for tag in ("drag_group", "drag_chrome_group"):
            try:
                self.canvas.dtag(tag, tag)
            except tk.TclError:
                pass
        if drag is not None and drag.get("moved"):
            node = self.project.get_widget(drag["nid"])
            cx_r, cy_r = ws._screen_to_canvas(event.x_root, event.y_root)
            started_in_container = (
                node is not None and node.parent is not None
            )
            # Container children follow extract-only semantics: dropped
            # anywhere except the source container → hop to the source
            # document's root at a default position. Blocks the "drag
            # straight from one container to another" shortcut because
            # mid-layout moves were getting confusing in practice.
            if started_in_container:
                if self.reparent.maybe_extract_from_container(event, drag):
                    ws._update_widget_visibility_across_docs()
                    return
                # Dropped inside source container — fall through to
                # normal move / grid cell-snap paths.
            elif self.release_handler.should_snap_back(cx_r, cy_r, drag):
                self.release_handler.apply_snap_back(drag)
                return
            grid_handled = self.reparent.maybe_grid_drop(event, drag)
            if not grid_handled:
                reparented = self.reparent.maybe_reparent_dragged(event, drag)
                # Skip the Move record if the widget jumped parents — a
                # proper ReparentCommand captures the full before/after,
                # Move would duplicate part of that record.
                if not reparented:
                    self.release_handler.record_bulk_move(drag)
        # Refresh cover-mask after a drag release so a widget that
        # just slid into / out of another document's area picks up
        # the right hidden state.
        ws._update_widget_visibility_across_docs()
        # Grid / pack moves change position without mutating x/y, so
        # the property-change-driven selection redraw fires before
        # the tk geometry manager has settled. Clear first so the
        # stale edge frames are torn down, then redraw once the
        # event loop is idle — the new bbox reflects the committed
        # position.
        if self.project.selected_id is not None:
            ws.selection.clear()
            self.workspace.after_idle(ws.selection.draw)
