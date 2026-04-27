"""Widget drag-to-move + drag-to-reparent controller.

Holds the per-gesture drag state (``_drag``) and the three press /
motion / release handlers every canvas widget is bound to. The
controller owns the logic for:

- press      — capture the widget's starting logical x/y
- motion     — translate the mouse delta (zoom-adjusted) into x/y
               property updates; tripping the 5 px threshold before
               committing so click-without-drag stays silent. For
               grid-parented widgets, x/y stays frozen and a cell
               highlight is drawn under the cursor instead.
- release    — either record a single ``MoveCommand`` for the
               gesture, a ``MultiChangePropertyCommand`` for a grid
               cell change, or a ``ReparentCommand`` if the widget
               was dropped into a different container / document.

Split out of the old monolithic ``workspace.py`` so drag logic lives
in one focused module. Core ``Workspace`` holds a single instance on
``self.drag_controller`` and wires widget bindings through it.
"""

from __future__ import annotations

import tkinter as tk

from app.core.commands import (
    BulkMoveCommand,
    BulkReparentCommand,
    MoveCommand,
    MultiChangePropertyCommand,
    ReparentCommand,
)
from app.ui.workspace.grid_drop_indicator import GridDropIndicator
from app.widgets.layout_schema import (
    is_layout_container,
    normalise_layout_type,
    resolve_grid_drop_cell,
)
from app.widgets.registry import get_descriptor

DRAG_THRESHOLD = 5

# Past this group size the per-motion canvas/place updates add up — at
# 10+ widgets the drag visibly stutters. Switch to "ghost mode": hide
# every widget + chrome in the group, show a single dashed bounding
# rect that tracks the cursor, and resync positions once on release.
HIDE_THRESHOLD = 10
HIDE_OUTLINE_COLOR = "#3b8ed0"


class WidgetDragController:
    """Per-workspace widget drag handler.

    All external state (project, canvas, zoom, selection, tool mode,
    lock/cover logic) is read through the workspace ref. The only
    state this class owns is the in-progress drag gesture.
    """

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

    # "Quick second click = drill" window. Longer than Windows'
    # double-click threshold (500 ms) — matches the rename-style
    # pause Explorer / Photoshop use, so a deliberate second click
    # feels distinct from both a double-click and a fresh session.
    _DRILL_WINDOW_MS = 800

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
        resolved_nid = self._resolve_selection(event, nid)
        if resolved_nid is None:
            # Canvas click landed on a locked widget with no unlocked
            # ancestor — block entirely. Locked widgets can only be
            # interacted with from the Object Tree.
            return "break"
        if ws._effective_locked(resolved_nid):
            # Defensive: should never happen because _resolve_selection
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
        group_starts = self._build_group_starts(resolved_nid)
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
            "grid_candidates": self._collect_grid_candidates(
                exclude_id=resolved_nid,
            ),
        }
        self._tag_drag_group(group_starts)
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
            self._enter_hidden_mode(group_starts)
        return "break"

    # ------------------------------------------------------------------
    # Press-time helpers
    # ------------------------------------------------------------------
    def _resolve_selection(self, event, nid: str) -> str | None:
        """Figure out which widget the press actually targets. Three
        branches:

        - Ctrl+click → multi-select toggle (add or remove nid).
        - Plain click inside an existing multi-selection → keep the
          group intact (Photoshop / Figma convention) so the drag
          moves everyone together.
        - Otherwise → Unity-style drill-down via
          ``_resolve_click_target``; updates the single selection.

        Returns ``None`` when the click should be ignored — currently
        that's a canvas click on a locked widget (and its chain has
        no unlocked alternative). Locked widgets are only reachable
        via the Object Tree.
        """
        ws = self.workspace
        multi = bool(event.state & 0x0004)
        existing_ids = set(
            getattr(self.project, "selected_ids", set()) or set(),
        )
        # Canvas clicks on locked widgets are silently ignored — all
        # three branches below would otherwise either select or toggle
        # the locked id, which Figma / Photoshop treat as off-limits.
        if ws._effective_locked(nid):
            return None
        if multi:
            current_ids = set(existing_ids)
            if nid in current_ids:
                current_ids.discard(nid)
                new_primary = next(iter(current_ids), None)
            else:
                current_ids.add(nid)
                new_primary = nid
            self.project.set_multi_selection(current_ids, new_primary)
            # Entering multi-select while in Edit mode flips the tool
            # to Select — resize handles don't make sense for a group,
            # and property edits on multi are ambiguous.
            if len(current_ids) > 1 and ws.controls.tool == "edit":
                ws.controls.set_tool("select")
            return new_primary or nid
        if len(existing_ids) > 1 and nid in existing_ids:
            return nid
        resolved = self._resolve_click_target(nid)
        if resolved is None:
            return None
        self.project.select_widget(resolved)
        return resolved

    def _build_group_starts(self, resolved_nid: str) -> dict:
        """Snapshot every place-managed selected widget's press-time
        x/y so ``on_motion`` can shift the whole group by a single
        delta. Locked widgets stay put; pack/grid children skip the
        snapshot entirely because their positions are parent-owned
        and any x/y we wrote would be stale on release.
        """
        ws = self.workspace
        selected_ids = set(
            getattr(self.project, "selected_ids", set()) or set(),
        )
        if resolved_nid not in selected_ids:
            selected_ids = {resolved_nid}
        group_starts: dict = {}
        for wid in selected_ids:
            w_node = self.project.get_widget(wid)
            if w_node is None:
                continue
            if ws._effective_locked(wid):
                continue
            parent_layout = (
                normalise_layout_type(
                    w_node.parent.properties.get("layout_type", "place"),
                ) if w_node.parent is not None else "place"
            )
            if parent_layout != "place":
                continue
            try:
                sx = int(w_node.properties.get("x", 0))
                sy = int(w_node.properties.get("y", 0))
            except (ValueError, TypeError):
                sx, sy = 0, 0
            group_starts[wid] = (sx, sy)
        return group_starts

    def _collect_grid_candidates(self, exclude_id: str) -> list:
        """Return every grid-layout container in the project whose
        subtree doesn't include ``exclude_id`` (skip self so a widget
        can't drop into itself). The list is used by ``_motion_feedback``
        to hit-test grid-cell highlights without the per-tick O(N)
        ``_find_container_at`` tree walk — for most projects this is
        a 0- to 2-entry list, so motion tick cost collapses.
        """
        candidates: list = []
        for node in self.project.iter_all_widgets():
            if node.id == exclude_id:
                continue
            descriptor = get_descriptor(node.widget_type)
            if descriptor is None:
                continue
            if not getattr(descriptor, "is_container", False):
                continue
            layout = normalise_layout_type(
                node.properties.get("layout_type", "place"),
            )
            if layout != "grid":
                continue
            # Skip if the dragged widget is an ancestor of this grid
            # container — dropping into a descendant of yourself is
            # the same "can't nest self inside self" rule that
            # ``exclude_id`` encodes in ``_find_container_at``.
            ancestor = node.parent
            skip = False
            while ancestor is not None:
                if ancestor.id == exclude_id:
                    skip = True
                    break
                ancestor = ancestor.parent
            if skip:
                continue
            candidates.append(node)
        return candidates

    def _tag_drag_group(self, group_starts: dict) -> None:
        """Stamp every group member with the shared ``drag_group`` +
        ``drag_chrome_group`` canvas tags so ``on_motion`` can move
        them all with a single ``canvas.move(tag, dx, dy)`` per frame
        instead of N round-trips. Nested (place-managed) children
        can't be tagged — they're inside a parent Frame, not on the
        canvas — and fall through to per-widget ``place_configure``
        in motion.
        """
        for wid in group_starts.keys():
            entry = self.widget_views.get(wid)
            if entry is None:
                continue
            _, window_id = entry
            if window_id is not None:
                try:
                    self.canvas.addtag_withtag("drag_group", window_id)
                except tk.TclError:
                    pass
            try:
                self.canvas.addtag_withtag(
                    "drag_chrome_group", f"chrome_wid_{wid}",
                )
            except tk.TclError:
                pass

    def _enter_hidden_mode(self, group_starts: dict) -> None:
        """Swap from live widget dragging to a single dashed-rect
        placeholder. Stores the placeholder item id + unhide state on
        ``self._drag`` so release can tear down the ghost cleanly.
        """
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")
        for wid in group_starts.keys():
            entry = self.widget_views.get(wid)
            if entry is None:
                continue
            _, window_id = entry
            if window_id is None:
                continue
            try:
                bbox = self.canvas.bbox(window_id)
            except tk.TclError:
                bbox = None
            if not bbox:
                continue
            x1, y1, x2, y2 = bbox
            if x1 < min_x:
                min_x = x1
            if y1 < min_y:
                min_y = y1
            if x2 > max_x:
                max_x = x2
            if y2 > max_y:
                max_y = y2
        if min_x == float("inf"):
            return  # no canvas-hosted widgets in the group — skip
        try:
            placeholder_id = self.canvas.create_rectangle(
                min_x, min_y, max_x, max_y,
                outline=HIDE_OUTLINE_COLOR, dash=(4, 4),
                width=2, fill="",
            )
        except tk.TclError:
            return
        try:
            self.canvas.itemconfigure("drag_group", state="hidden")
        except tk.TclError:
            pass
        try:
            self.canvas.itemconfigure(
                "drag_chrome_group", state="hidden",
            )
        except tk.TclError:
            pass
        self._drag["hidden_mode"] = True
        self._drag["placeholder_id"] = placeholder_id

    def _resolve_click_target(self, clicked_nid: str) -> str | None:
        """Drill-down selection gated by a fast-click window.

        Revised semantics (v0.0.15.17):

        - First click on a leaf → select outermost unlocked ancestor.
        - Second click on the SAME leaf within ``_DRILL_WINDOW_MS`` →
          drill one level deeper (parent → child → grandchild).
        - Slow (> window) successive clicks → reset to the outermost
          ancestor, so the user can drag the parent repeatedly without
          auto-descending into children on every follow-up press.
        - Different leaf OR sibling inside an already-entered scope →
          select the leaf directly (shared-scope shortcut preserved).

        Returns ``None`` when every widget in the click's ancestor
        chain is locked — the click has no valid canvas target and
        should be ignored. Locked widgets stay reachable through the
        Object Tree.
        """
        ws = self.workspace
        clicked_node = self.project.get_widget(clicked_nid)
        if clicked_node is None:
            return clicked_nid
        chain: list = []
        cur = clicked_node
        while cur is not None:
            if not ws._effective_locked(cur.id):
                chain.append(cur)
            cur = cur.parent
        chain.reverse()  # [outermost unlocked, ..., clicked-if-unlocked]
        if not chain:
            return None
        now_ms = int(self.workspace.tk.call("clock", "milliseconds"))
        same_leaf = clicked_nid == self._last_click_leaf_id
        within_window = (now_ms - self._last_click_time_ms) <= self._DRILL_WINDOW_MS
        fast_follow_up = same_leaf and within_window
        # Stamp for the next click BEFORE returning so nested returns
        # all share the same post-condition.
        self._last_click_leaf_id = clicked_nid
        self._last_click_time_ms = now_ms

        current_id = self.project.selected_id
        # Case 1 — fast click on same leaf: drill one level deeper
        # from the current selection toward the leaf.
        if fast_follow_up and current_id is not None:
            for idx, node in enumerate(chain):
                if node.id == current_id:
                    if idx + 1 < len(chain):
                        return chain[idx + 1].id
                    return chain[idx].id
        # Case 2 — shared-scope shortcut. If the current selection is
        # NOT an outermost ancestor (i.e. the user has already entered
        # a child scope on this branch), keep them at child level —
        # clicking a sibling or the same subtree selects the leaf
        # directly. Once a child is selected we stay at child depth
        # until selection is cleared.
        if current_id is not None:
            current_node = self.project.get_widget(current_id)
            if current_node is not None:
                ancestor_ids: set = set()
                c = current_node
                while c is not None:
                    ancestor_ids.add(c.id)
                    c = c.parent
                on_same_branch = any(
                    node.id in ancestor_ids for node in chain
                )
                outermost_id = chain[0].id
                already_at_child_depth = current_id != outermost_id
                if on_same_branch and already_at_child_depth:
                    return chain[-1].id
        # Case 3 — slow fresh click OR different branch: start at the
        # outermost unlocked ancestor so drag-the-parent flows survive
        # repeated clicks without being kidnapped into children.
        return chain[0].id

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
            self._destroy_ghost()
            return
        if (
            self._drag is None
            or self._drag.get("click_nid", self._drag["nid"]) != nid
        ):
            return
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
        if self._motion_feedback(nid, cx, cy, node, src_layout):
            return
        # pack / grid parent: skip x/y updates — their positions are
        # owned by the geometry manager, and release either reparents
        # or snaps back to the captured start.
        if src_layout != "place":
            return
        self._motion_place_group(event, dx_root, dy_root)

    # ------------------------------------------------------------------
    # Motion-time helpers
    # ------------------------------------------------------------------
    def _motion_feedback(
        self, nid: str, cx: float, cy: float,
        node, src_layout: str,
    ) -> bool:
        """Update the grid cell highlight + drag ghost. Returns True
        when the motion is fully handled (cursor sitting on a grid
        cell) so ``on_motion`` can skip the place-group path below.

        Hit-tests only the grid containers cached at press time (see
        ``_collect_grid_candidates``) rather than walking every widget
        per tick — the common case (no grid containers) skips the
        search entirely; the typical case (1-2 grid containers) is
        O(1-2) instead of O(N).
        """
        # Ghost: pack/grid children can't move via x/y updates, so we
        # surface drag feedback as canvas items near the cursor.
        # place children already slide under the cursor — no ghost.
        if src_layout in ("vbox", "hbox", "grid"):
            self._update_ghost(node, cx, cy)
        candidates = self._drag.get("grid_candidates") or []
        if not candidates:
            self._grid_indicator.clear()
            return False
        target = self._grid_candidate_at(cx, cy, candidates)
        if target is not None:
            row, col = self._grid_indicator.cell_at(target, cx, cy)
            self._grid_indicator.draw(target, row, col)
            return True
        # Cursor left every grid container — erase stale highlight.
        self._grid_indicator.clear()
        return False

    def _grid_candidate_at(
        self, cx: float, cy: float, candidates: list,
    ) -> object:
        """Return the deepest grid container whose canvas bbox
        contains (cx, cy), or None. Depth is inferred from parent
        chain length — deeper wins so a grid-inside-grid scenario
        lands on the inner cell.
        """
        best = None
        best_depth = -1
        for cand in candidates:
            entry = self.widget_views.get(cand.id)
            if entry is None:
                continue
            widget, _ = entry
            bbox = self.workspace._widget_canvas_bbox(widget)
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
    # Snap-to-siblings + container guides (motion-time helpers)
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
        if len(self._drag.get("group_starts") or {}) != 1:
            return 0, 0, [], []
        sx, sy = self._drag["group_starts"][primary_node.id]
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
                n for n in self.project.active_document.root_widgets
                if n.id != primary_node.id
            ]
            doc = self.project.active_document
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
        self._clear_snap_guides()
        if not guide_xs and not guide_ys:
            return
        entry = self.widget_views.get(primary_node.id)
        if entry is None:
            return
        widget, _wid = entry
        bbox = self.workspace._widget_canvas_bbox(widget)
        if bbox is None:
            return
        canvas_scale = self.zoom.canvas_scale or 1.0
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
            doc = self.project.active_document
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
            scroll_off_x = int(self.canvas.canvasx(0))
            scroll_off_y = int(self.canvas.canvasy(0))
        except tk.TclError:
            scroll_off_x, scroll_off_y = 0, 0
        for gx in guide_xs:
            xc = parent_cx + int(gx * canvas_scale)
            try:
                f = tk.Frame(
                    self.canvas, bg="#5bc0f8",
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
                    self.canvas, bg="#5bc0f8",
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

    def _clear_snap_guides(self) -> None:
        for guide in getattr(self, "_snap_guide_widgets", []) or []:
            try:
                guide.destroy()
            except (tk.TclError, AttributeError):
                pass
        self._snap_guide_widgets = []

    def _motion_place_group(
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
        # Two scales in play:
        # - ``canvas_scale`` (= user_zoom × DPI_factor) maps physical
        #   cursor pixels to logical model pixels — used for the delta.
        # - ``zoom.value`` (= user_zoom only) is what ``_place_nested``
        #   feeds to ``.place(x, y)``, because tk already applies DPI
        #   scaling to place() args on DPI-aware windows. Drag motion
        #   must re-use that same scale when writing back to
        #   ``place_configure`` so the widget lands where the cursor
        #   is instead of drifting by DPI_factor on nested children.
        canvas_scale = self.zoom.canvas_scale or 1.0
        place_scale = self.zoom.value or 1.0
        dx_logical = int(dx_root / canvas_scale)
        dy_logical = int(dy_root / canvas_scale)
        dx_tick = event.x_root - self._drag["last_mx"]
        dy_tick = event.y_root - self._drag["last_my"]
        hidden_mode = self._drag.get("hidden_mode", False)
        # Snap-to-siblings + container guides. Single-widget place
        # drags only — multi-widget snap would have to pick which
        # group member's edge counts and tends to fight the user.
        # Hold Alt to bypass snap (mask 0x20000 on Windows / Linux).
        primary_node = self.project.get_widget(self._drag["nid"])
        snap_dx_logical = 0
        snap_dy_logical = 0
        prev_snap_dx = self._drag.get("snap_dx_logical", 0)
        prev_snap_dy = self._drag.get("snap_dy_logical", 0)
        alt_held = bool(event.state & 0x20000)
        if (
            primary_node is not None
            and not hidden_mode
            and not alt_held
        ):
            snap_dx_logical, snap_dy_logical, gxs, gys = (
                self._compute_drag_snap(
                    primary_node, dx_logical, dy_logical,
                )
            )
            self._draw_snap_guides(primary_node, gxs, gys)
        else:
            self._clear_snap_guides()
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
        self._drag["snap_dx_logical"] = snap_dx_logical
        self._drag["snap_dy_logical"] = snap_dy_logical
        if dx_tick or dy_tick:
            if hidden_mode:
                pid = self._drag.get("placeholder_id")
                if pid is not None:
                    try:
                        self.canvas.move(pid, dx_tick, dy_tick)
                    except tk.TclError:
                        pass
            else:
                try:
                    self.canvas.move("drag_group", dx_tick, dy_tick)
                except tk.TclError:
                    pass
                try:
                    self.canvas.move(
                        "drag_chrome_group", dx_tick, dy_tick,
                    )
                except tk.TclError:
                    pass
        # Model update: write x / y to the nodes directly (bypasses
        # project.update_property's event bus for the duration of the
        # gesture so Inspector / Object Tree aren't re-rendered on
        # every motion). Release fires one property_changed pair per
        # moved widget to resync downstream panels.
        for wid, (sx, sy) in self._drag["group_starts"].items():
            new_x = sx + dx_logical
            new_y = sy + dy_logical
            w_node = self.project.get_widget(wid)
            if w_node is None:
                continue
            w_node.properties["x"] = new_x
            w_node.properties["y"] = new_y
            if hidden_mode:
                continue  # widgets are invisible — skip tk calls
            entry = self.widget_views.get(wid)
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
        self._drag["last_mx"] = event.x_root
        self._drag["last_my"] = event.y_root

    def on_release(self, event, _nid: str) -> None:
        ws = self.workspace
        if ws._tool == "hand":
            ws._end_pan(event)
            return
        # Snap guides only live for the duration of the gesture —
        # release tears them down regardless of how the drag ends
        # (drop / snap-back / no-op click).
        self._clear_snap_guides()
        drag = self._drag
        # Clear drag state BEFORE firing any project mutations so
        # ``_schedule_selection_redraw`` stops short-circuiting on
        # ``is_dragging()``. With the guard on, release-time updates
        # (grid snap, reparent, move) would leave selection handles
        # lingering at the pre-drop spot until the next UI event.
        self._drag = None
        self._grid_indicator.clear()
        self._destroy_ghost()
        if drag is not None and drag.get("hidden_mode"):
            self._teardown_hidden_mode(drag)
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
                if self._maybe_extract_from_container(event, drag):
                    ws._update_widget_visibility_across_docs()
                    return
                # Dropped inside source container — fall through to
                # normal move / grid cell-snap paths.
            elif self._should_snap_back(cx_r, cy_r, drag):
                self._apply_snap_back(drag)
                return
            grid_handled = self._maybe_grid_drop(event, drag)
            if not grid_handled:
                reparented = self._maybe_reparent_dragged(event, drag)
                # Skip the Move record if the widget jumped parents — a
                # proper ReparentCommand captures the full before/after,
                # Move would duplicate part of that record.
                if not reparented:
                    self._record_bulk_move(drag)
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

    # ------------------------------------------------------------------
    # Release-time helpers
    # ------------------------------------------------------------------
    def _teardown_hidden_mode(self, drag: dict) -> None:
        """Delete the dashed placeholder rect, unhide widgets +
        chromes, and slide them to their final position via a single
        ``apply_all``. Must run BEFORE the shared drag tags are
        removed — ``itemconfigure`` can't reach items once dtag has
        cleared their tag membership.
        """
        pid = drag.get("placeholder_id")
        if pid is not None:
            try:
                self.canvas.delete(pid)
            except tk.TclError:
                pass
        for tag in ("drag_group", "drag_chrome_group"):
            try:
                self.canvas.itemconfigure(tag, state="normal")
            except tk.TclError:
                pass
        # Widgets were frozen at their press-time canvas positions
        # during motion — run apply_all once to slide them to the
        # drag's final logical x/y.
        self.zoom.apply_all()

    def _should_snap_back(
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
        ws = self.workspace
        nid = drag["nid"]
        cursor_target = (
            ws._find_container_at(cx_r, cy_r, exclude_id=nid) is not None
            or ws._find_document_at_canvas(cx_r, cy_r) is not None
        )
        if not cursor_target:
            return True
        all_docs = list(self.project.documents)
        for wid in drag["group_starts"].keys():
            g_node = self.project.get_widget(wid)
            if g_node is None:
                continue
            doc = self.project.find_document_for_widget(wid)
            if doc is None:
                continue
            try:
                ex = int(g_node.properties.get("x", 0))
                ey = int(g_node.properties.get("y", 0))
            except (TypeError, ValueError):
                continue
            abs_x = doc.canvas_x + ex
            abs_y = doc.canvas_y + ey
            inside_any = any(
                d.canvas_x <= abs_x < d.canvas_x + d.width
                and d.canvas_y <= abs_y < d.canvas_y + d.height
                for d in all_docs
            )
            if not inside_any:
                return True
        return False

    def _apply_snap_back(self, drag: dict) -> None:
        """Restore every dragged widget's x/y to its press-time value
        and kick the cross-doc visibility mask to hide / show widgets
        that may have slid under another doc during the gesture.
        """
        for wid, (sx, sy) in drag["group_starts"].items():
            self.project.update_property(wid, "x", sx)
            self.project.update_property(wid, "y", sy)
        self.workspace._update_widget_visibility_across_docs()

    def _record_bulk_move(self, drag: dict) -> None:
        """Push one ``BulkMoveCommand`` covering every widget shifted
        by this drag + fire the ``property_changed`` events the motion
        path skipped for perf. One undo rewinds the whole gesture;
        single-widget drags degrade cleanly to a one-entry command.
        """
        moves: list = []
        for wid, (sx, sy) in drag["group_starts"].items():
            g_node = self.project.get_widget(wid)
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
        self.project.history.push(BulkMoveCommand(moves))
        bus = self.project.event_bus
        for wid, _before, after in moves:
            for key, val in after.items():
                bus.publish("property_changed", wid, key, val)

    # ------------------------------------------------------------------
    # Drag ghost for layout-managed children
    # ------------------------------------------------------------------
    def _update_ghost(self, node, cx: float, cy: float) -> None:
        """Draw (or slide) a label near the cursor so pack/grid
        children have drag feedback. Two canvas items — a filled rect
        behind a text label — both tagged ``drag_ghost`` so a single
        ``canvas.move`` on the tag shifts them together. Canvas items
        are orders of magnitude cheaper than a per-drag Toplevel.
        """
        if node is None:
            return
        canvas = self.canvas
        nx = int(cx) + 12
        ny = int(cy) + 12
        if self._ghost_items is None:
            label_text = node.name or node.widget_type
            try:
                text_id = canvas.create_text(
                    nx + 10, ny + 4,
                    text=label_text, anchor="nw",
                    font=("Segoe UI", 10, "bold"),
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
            self._ghost_items = {"text": text_id, "rect": rect_id}
            self._ghost_last = (nx, ny)
            return
        last_x, last_y = self._ghost_last or (nx, ny)
        dx = nx - last_x
        dy = ny - last_y
        if dx or dy:
            try:
                canvas.move("drag_ghost", dx, dy)
            except tk.TclError:
                return
            self._ghost_last = (nx, ny)

    def _destroy_ghost(self) -> None:
        if self._ghost_items is not None:
            try:
                self.canvas.delete("drag_ghost")
            except tk.TclError:
                pass
            self._ghost_items = None
            self._ghost_last = None

    # ------------------------------------------------------------------
    # Container extraction (two-step reparent)
    # ------------------------------------------------------------------
    def _maybe_extract_from_container(self, event, drag: dict) -> bool:
        """Extract a child out of its container to the source document's
        root at a cascade-offset default position. Fires only when the
        widget started inside a container and wasn't dropped inside
        that same container. Returns True when extraction happened —
        callers skip grid / reparent fallbacks after.
        """
        ws = self.workspace
        nid = drag["nid"]
        node = self.project.get_widget(nid)
        if node is None or node.parent is None:
            return False
        self.canvas.update_idletasks()
        cx, cy = ws._screen_to_canvas(event.x_root, event.y_root)
        target = ws._find_container_at(cx, cy, exclude_id=nid)
        if target is not None and target.id == node.parent.id:
            return False
        old_parent_id = node.parent.id
        old_doc = (
            self.project.find_document_for_widget(nid)
            or self.project.active_document
        )
        if old_doc is None:
            return False
        # Land at the cursor's position translated into the source
        # document's logical coords — that's where the user aimed.
        # If the cursor is outside the source document (dropped over
        # another form or empty canvas), fall back to a cascade
        # default so the widget doesn't vanish off-form.
        cursor_doc = ws._find_document_at_canvas(cx, cy)
        if cursor_doc is old_doc:
            lx, ly = self.zoom.canvas_to_logical(cx, cy, document=old_doc)
            try:
                w = int(node.properties.get("width", 0) or 0)
                h = int(node.properties.get("height", 0) or 0)
            except (TypeError, ValueError):
                w = h = 0
            # Centre-ish on cursor so the release point lines up
            # visually with the drop location.
            nx = max(0, min(lx - w // 2, max(0, old_doc.width - w)))
            ny = max(0, min(ly - h // 2, max(0, old_doc.height - h)))
        else:
            from app.core.project import find_free_cascade_slot
            nx, ny = find_free_cascade_slot(
                old_doc.root_widgets, start_xy=(20, 20), exclude=node,
            )
        # Undo snapshot
        old_siblings = node.parent.children
        try:
            old_index = old_siblings.index(node)
        except ValueError:
            old_index = len(old_siblings)
        old_x = drag["start_x"]
        old_y = drag["start_y"]
        old_parent_slot = node.parent_slot
        # Mutate: remove from container, append to doc root, reset x/y
        node.properties["x"] = nx
        node.properties["y"] = ny
        node.parent_slot = None
        if node in old_siblings:
            old_siblings.remove(node)
        node.parent = None
        old_doc.root_widgets.append(node)
        self.project.event_bus.publish(
            "widget_reparented", nid, old_parent_id, None,
        )
        same_doc_id = old_doc.id if old_doc is not None else None
        self.project.history.push(
            ReparentCommand(
                nid,
                old_parent_id=old_parent_id,
                old_index=old_index,
                old_x=old_x,
                old_y=old_y,
                new_parent_id=None,
                new_index=len(old_doc.root_widgets) - 1,
                new_x=nx,
                new_y=ny,
                old_document_id=same_doc_id,
                new_document_id=same_doc_id,
                old_parent_slot=old_parent_slot,
                new_parent_slot=None,
            ),
        )
        return True

    # ------------------------------------------------------------------
    # Reparent detection
    # ------------------------------------------------------------------
    def _maybe_reparent_dragged(self, event, drag: dict) -> bool:
        """On drag release, check if the widget was dropped into a
        different container OR a different document. Either case
        reparents (containers via ``project.reparent``, cross-doc via
        a manual move between document root lists) so undo + rendering
        stay consistent. Returns True when a reparent happened so the
        caller skips the per-widget Move history record.

        ``drag`` is the captured gesture snapshot — ``self._drag`` has
        already been cleared by ``on_release`` (so the selection
        redraw guard sees ``is_dragging() == False``), hence the
        explicit parameter.
        """
        ws = self.workspace
        nid = drag["nid"]
        node = self.project.get_widget(nid)
        if node is None:
            return False
        self.canvas.update_idletasks()
        cx, cy = ws._screen_to_canvas(event.x_root, event.y_root)
        target = ws._find_container_at(cx, cy, exclude_id=nid)
        # Block layout-in-layout nesting — if both the dragged widget
        # and the target are managed-layout containers, treat the
        # drop as a top-level move instead of reparenting.
        if (
            target is not None
            and is_layout_container(node.properties)
            and is_layout_container(target.properties)
        ):
            target = None
        new_parent_id = target.id if target is not None else None
        old_parent_id = node.parent.id if node.parent is not None else None
        old_doc = self.project.find_document_for_widget(nid)
        if target is not None:
            new_doc = self.project.find_document_for_widget(target.id)
        else:
            new_doc = (
                ws._find_document_at_canvas(cx, cy)
                or old_doc
                or self.project.active_document
            )
        cross_doc = new_doc is not None and new_doc is not old_doc
        if new_parent_id == old_parent_id and not cross_doc:
            return False  # same parent, same doc — in-place drag
        # Capture the pre-reparent state for undo BEFORE any mutation.
        old_siblings = (
            node.parent.children if node.parent is not None
            else (
                old_doc.root_widgets if old_doc is not None
                else self.project.root_widgets
            )
        )
        try:
            old_index = old_siblings.index(node)
        except ValueError:
            old_index = len(old_siblings)
        old_parent_slot = node.parent_slot
        # Compute + commit the new logical x/y in the drop target's
        # frame of reference (container-local, or doc-local for a
        # top-level drop).
        new_x, new_y = self._compute_drop_coords(nid, target, new_doc)
        node.properties["x"] = max(0, new_x)
        node.properties["y"] = max(0, new_y)
        # Tabview target: drop lands in the currently-active tab. Any
        # other target (or a top-level drop) clears the slot so the
        # node stops referring to a tab it no longer belongs to.
        new_parent_slot = self._resolve_tabview_slot(target)
        node.parent_slot = new_parent_slot
        if cross_doc and target is None:
            # Cross-doc top-level drop: bypass project.reparent (which
            # always targets the active doc) and move the whole group
            # between document root lists manually so the bulk undo
            # rewinds all members at once.
            self._perform_cross_doc_group_move(
                drag, old_doc, new_doc,
                old_parent_id, new_parent_id,
            )
            return True
        self.project.reparent(nid, new_parent_id)
        self._push_reparent_command(
            nid, old_parent_id, old_index,
            drag["start_x"], drag["start_y"],
            new_parent_id, new_x, new_y,
            old_doc, new_doc,
            parent_dim_changes=drag.get("parent_dim_changes"),
            old_parent_slot=old_parent_slot,
            new_parent_slot=new_parent_slot,
        )
        return True

    def _resolve_tabview_slot(self, target) -> str | None:
        """Return the currently-active tab name when ``target`` is a
        CTkTabview; None otherwise. Used by both the reparent-drag and
        extract paths to stamp (or clear) the node's ``parent_slot``.
        """
        if target is None or target.widget_type != "CTkTabview":
            return None
        entry = self.widget_views.get(target.id)
        if entry is None:
            return None
        target_widget, _ = entry
        try:
            return target_widget.get() or None
        except Exception:
            return None

    def _compute_drop_coords(
        self, nid: str, target, new_doc,
    ) -> tuple[int, int]:
        """Resolve the dragged widget's logical x/y in the target's
        coordinate space. Top-level drops use doc-local logical coords
        derived from the widget's current canvas position; container
        drops use coords relative to the container widget. Non-place
        containers ignore x/y so we zero them for a clean Inspector
        reading after the drop.

        ``rel_x`` / ``rel_y`` are in physical screen pixels (winfo_*
        returns physical), so dividing by ``canvas_scale`` (= user
        zoom × DPI factor) yields the logical model coords. Using
        ``zoom.value`` alone here was the source of a long-standing
        bug on DPI > 1.0 systems where dropped widgets landed below /
        right of the cursor by an amount proportional to the drop y
        (the off-by-DPI multiplier compounded with each tk pixel).
        """
        widget, _ = self.widget_views[nid]
        if target is None:
            rx = widget.winfo_rootx() - self.canvas.winfo_rootx()
            ry = widget.winfo_rooty() - self.canvas.winfo_rooty()
            canvas_x = self.canvas.canvasx(rx)
            canvas_y = self.canvas.canvasy(ry)
            target_doc = new_doc or self.project.active_document
            new_x, new_y = self.zoom.canvas_to_logical(
                canvas_x, canvas_y, document=target_doc,
            )
            return new_x, new_y
        target_widget, _ = self.widget_views[target.id]
        # Tabview target: measure against the active tab's inner frame
        # (same reference CTk will use as the widget's master after
        # reparent) so the dropped x/y land where the cursor aimed.
        coord_ref = target_widget
        if target.widget_type == "CTkTabview":
            try:
                active = target_widget.get() or None
            except Exception:
                active = None
            if active:
                try:
                    coord_ref = target_widget.tab(active)
                except Exception:
                    coord_ref = target_widget
        canvas_scale = self.zoom.canvas_scale or 1.0
        rel_x = widget.winfo_rootx() - coord_ref.winfo_rootx()
        rel_y = widget.winfo_rooty() - coord_ref.winfo_rooty()
        new_x = int(rel_x / canvas_scale)
        new_y = int(rel_y / canvas_scale)
        if normalise_layout_type(
            target.properties.get("layout_type", "place"),
        ) != "place":
            new_x = new_y = 0
        return new_x, new_y

    def _perform_cross_doc_group_move(
        self, drag: dict, old_doc, new_doc,
        old_parent_id: str | None, new_parent_id: str | None,
    ) -> None:
        """Manually move every top-level group member from old_doc to
        new_doc + push a BulkReparentCommand so one undo rewinds the
        whole group. A single ReparentCommand alone would strand the
        non-primary members in new_doc on undo.
        """
        nid = drag["nid"]
        node = self.project.get_widget(nid)
        group_starts = drag.get("group_starts", {})
        old_doc_id = old_doc.id if old_doc is not None else None
        new_doc_id = new_doc.id
        # Snapshot every member's pre-move state BEFORE any mutation.
        snapshots: list = []
        old_doc_rw = (
            old_doc.root_widgets if old_doc is not None else []
        )
        for wid, (sx, sy) in group_starts.items():
            w_node = self.project.get_widget(wid)
            if w_node is None or w_node.parent is not None:
                continue
            try:
                g_old_idx = old_doc_rw.index(w_node)
            except ValueError:
                g_old_idx = len(old_doc_rw)
            snapshots.append({
                "wid": wid, "old_index": g_old_idx,
                "old_x": sx, "old_y": sy,
            })
        # Primary first — its final position drives the event bus.
        if (
            node is not None and old_doc is not None
            and node in old_doc.root_widgets
        ):
            old_doc.root_widgets.remove(node)
        if node is not None:
            node.parent = None
            new_doc.root_widgets.append(node)
            self.project._index_subtree(node, new_doc)
            self.project.event_bus.publish(
                "widget_reparented", nid,
                old_parent_id, new_parent_id,
            )
        # Remaining members in press order — keeps their new-doc
        # index matching the visual stack.
        for wid in list(group_starts.keys()):
            if wid == nid:
                continue
            other = self.project.get_widget(wid)
            if other is None or other.parent is not None:
                continue
            try:
                ox = int(other.properties.get("x", 0))
                oy = int(other.properties.get("y", 0))
            except (TypeError, ValueError):
                ox = oy = 0
            # old_doc.canvas_x + ox == new_doc.canvas_x + new_ox
            # so each member stays visually put while switching
            # logical reference frames.
            new_ox = int(ox + (old_doc.canvas_x - new_doc.canvas_x))
            new_oy = int(oy + (old_doc.canvas_y - new_doc.canvas_y))
            other.properties["x"] = max(0, new_ox)
            other.properties["y"] = max(0, new_oy)
            if other in old_doc.root_widgets:
                old_doc.root_widgets.remove(other)
            new_doc.root_widgets.append(other)
            self.project._index_subtree(other, new_doc)
            self.project.event_bus.publish(
                "widget_reparented", wid, None, None,
            )
        # Build per-member ReparentCommand + push bulk.
        reparent_cmds: list = []
        for snap in snapshots:
            g_wid = snap["wid"]
            g_node = self.project.get_widget(g_wid)
            if g_node is None:
                continue
            try:
                g_new_idx = new_doc.root_widgets.index(g_node)
            except ValueError:
                g_new_idx = len(new_doc.root_widgets) - 1
            try:
                g_new_x = int(g_node.properties.get("x", 0))
                g_new_y = int(g_node.properties.get("y", 0))
            except (TypeError, ValueError):
                g_new_x = g_new_y = 0
            reparent_cmds.append(ReparentCommand(
                g_wid,
                old_parent_id=None,
                old_index=snap["old_index"],
                old_x=snap["old_x"],
                old_y=snap["old_y"],
                new_parent_id=None,
                new_index=g_new_idx,
                new_x=g_new_x,
                new_y=g_new_y,
                old_document_id=old_doc_id,
                new_document_id=new_doc_id,
            ))
        if len(reparent_cmds) == 1:
            self.project.history.push(reparent_cmds[0])
        elif reparent_cmds:
            self.project.history.push(BulkReparentCommand(reparent_cmds))

    def _push_reparent_command(
        self, nid: str, old_parent_id: str | None, old_index: int,
        old_x: int, old_y: int, new_parent_id: str | None,
        new_x: int, new_y: int, old_doc, new_doc,
        parent_dim_changes: tuple[str, dict] | None = None,
        old_parent_slot: str | None = None,
        new_parent_slot: str | None = None,
    ) -> None:
        """Compute the widget's post-reparent sibling index and push a
        single ``ReparentCommand``. Used for in-doc reparents and for
        drops into a specific container (cross-doc or not).
        """
        post_node = self.project.get_widget(nid)
        if post_node is not None:
            new_siblings = (
                post_node.parent.children if post_node.parent is not None
                else self.project.root_widgets
            )
            try:
                new_index = new_siblings.index(post_node)
            except ValueError:
                new_index = len(new_siblings) - 1
        else:
            new_index = 0
        old_doc_id = old_doc.id if old_doc is not None else None
        new_doc_id = new_doc.id if new_doc is not None else old_doc_id
        self.project.history.push(ReparentCommand(
            nid,
            old_parent_id=old_parent_id,
            old_index=old_index,
            old_x=old_x,
            old_y=old_y,
            new_parent_id=new_parent_id,
            new_index=new_index,
            new_x=new_x,
            new_y=new_y,
            old_document_id=old_doc_id,
            new_document_id=new_doc_id,
            parent_dim_changes=parent_dim_changes,
            old_parent_slot=old_parent_slot,
            new_parent_slot=new_parent_slot,
        ))

    # ------------------------------------------------------------------
    # Grid drag-to-cell
    # ------------------------------------------------------------------
    def _maybe_grid_drop(self, event, drag: dict) -> bool:
        """Explicit-cell grid drop. Cursor cell becomes the child's
        own ``grid_row`` / ``grid_column`` — no sibling shift. Cross-
        parent drops hand off to ``_maybe_reparent_dragged`` after
        pre-setting the new cell on the node so the post-reparent
        ``.grid()`` call lands in the target cell.
        """
        ws = self.workspace
        nid = drag["nid"]
        node = self.project.get_widget(nid)
        if node is None:
            return False
        self.canvas.update_idletasks()
        cx, cy = ws._screen_to_canvas(event.x_root, event.y_root)
        target = ws._find_container_at(cx, cy, exclude_id=nid)
        if target is None:
            return False
        # Layout Frame being dropped onto a grid Frame — block the
        # grid cell-snap path so ``_maybe_reparent_dragged`` gets a
        # chance to redirect to top-level via its own check.
        if (
            is_layout_container(node.properties)
            and is_layout_container(target.properties)
        ):
            return False
        target_layout = normalise_layout_type(
            target.properties.get("layout_type", "place"),
        )
        if target_layout != "grid":
            return False
        cursor_row, cursor_col = self._grid_indicator.cell_at(
            target, cx, cy,
        )
        old_parent_id = node.parent.id if node.parent is not None else None
        new_parent_id = target.id
        try:
            old_row = int(node.properties.get("grid_row", 0) or 0)
            old_col = int(node.properties.get("grid_column", 0) or 0)
        except (TypeError, ValueError):
            old_row, old_col = 0, 0
        # Route the cursor cell through resolve_grid_drop_cell so a
        # drop onto an occupied cell gets redirected to the next
        # free cell (or grows the grid). Without this the user
        # could stack two children on the exact same cell — silent
        # overlap, invisible on canvas.
        resolved_row, resolved_col, dim_updates = resolve_grid_drop_cell(
            target.children,
            target.properties,
            preferred_row=cursor_row,
            preferred_col=cursor_col,
            exclude_node=node,
        )
        if new_parent_id == old_parent_id:
            if (resolved_row, resolved_col) == (old_row, old_col):
                return True  # same cell — no-op drop
            parent_before = (
                {k: target.properties.get(k) for k in dim_updates}
                if dim_updates else None
            )
            if dim_updates:
                for key, val in dim_updates.items():
                    self.project.update_property(target.id, key, val)
            self.project.update_property(nid, "grid_row", resolved_row)
            self.project.update_property(nid, "grid_column", resolved_col)
            self.project.history.push(
                MultiChangePropertyCommand(
                    nid,
                    {
                        "grid_row": (old_row, resolved_row),
                        "grid_column": (old_col, resolved_col),
                    },
                    parent_dim_changes=(
                        target.id,
                        {
                            k: (parent_before[k], dim_updates[k])
                            for k in dim_updates
                        },
                    ) if dim_updates else None,
                ),
            )
            return True
        # Different parent — pre-set the new cell so the reparent's
        # widget rebuild lands at the resolved cell, then fall
        # through to the standard reparent flow for the destroy /
        # recreate + history push.
        node.properties["grid_row"] = resolved_row
        node.properties["grid_column"] = resolved_col
        if dim_updates:
            parent_before = {k: target.properties.get(k) for k in dim_updates}
            for key, val in dim_updates.items():
                self.project.update_property(target.id, key, val)
            drag["parent_dim_changes"] = (
                target.id,
                {
                    k: (parent_before[k], dim_updates[k])
                    for k in dim_updates
                },
            )
        self._maybe_reparent_dragged(event, drag)
        return True
