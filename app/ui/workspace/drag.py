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
    MoveCommand,
    MultiChangePropertyCommand,
    ReparentCommand,
)
from app.widgets.layout_schema import (
    grid_effective_dims,
    normalise_layout_type,
)

DRAG_THRESHOLD = 5
GRID_HIGHLIGHT_TAG = "grid_drop_highlight"
GRID_HIGHLIGHT_COLOR = "#6fb4f0"

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
        # Drag ghost — a small Toplevel showing the widget's label
        # while the cursor follows. Used only for layout-managed
        # children (pack / grid) because place children already move
        # under the cursor via x/y updates; a ghost on top of that
        # would just duplicate the motion.
        self._ghost: tk.Toplevel | None = None
        # De-dup ButtonPress firings by tk event serial. Composite
        # widgets can fire the same press through a parent + child
        # binding both carrying different nids — running drill-down
        # twice in one event loop pass skips past the intended
        # container on the very first click.
        self._last_press_serial: int | None = None

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
        # Ctrl+click — multi-select toggle. Adds the widget if not
        # already in the selection set, removes it otherwise. Drill-
        # down is bypassed so the user stays in control of exactly
        # which widget gets flipped.
        multi = bool(event.state & 0x0004)
        existing_ids = set(
            getattr(self.project, "selected_ids", set()) or set(),
        )
        if multi:
            current_ids = set(existing_ids)
            if nid in current_ids:
                current_ids.discard(nid)
                new_primary = next(iter(current_ids), None)
            else:
                current_ids.add(nid)
                new_primary = nid
            self.project.set_multi_selection(current_ids, new_primary)
            resolved_nid = new_primary or nid
            # Entering multi-select while in Edit mode flips the tool
            # to Select — resize handles don't make sense for a group,
            # and property edits on multi are ambiguous. The user can
            # flip back to Edit manually when they want to tweak a
            # single widget's properties again.
            if len(current_ids) > 1 and ws.controls.tool == "edit":
                ws.controls.set_tool("select")
        elif len(existing_ids) > 1 and nid in existing_ids:
            # Clicking one widget in an existing multi-selection
            # (no modifier) should not collapse the group — Photoshop
            # / Figma convention. Keep the selection as-is so the
            # drag below moves every selected widget together.
            resolved_nid = nid
        else:
            # Unity-style drill-down selection: first click on a
            # hierarchy selects the outermost ancestor; subsequent
            # clicks descend one level at a time. Ensures you can
            # reach a container even when it's fully covered by its
            # children.
            resolved_nid = self._resolve_click_target(nid)
            self.project.select_widget(resolved_nid)
        if ws._effective_locked(resolved_nid):
            # Locked widgets are selectable (for property editing)
            # but not draggable.
            return "break"
        node = self.project.get_widget(resolved_nid)
        if node is None:
            return
        try:
            start_x = int(node.properties.get("x", 0))
            start_y = int(node.properties.get("y", 0))
        except (ValueError, TypeError):
            start_x, start_y = 0, 0
        # Delta-based drag — works for canvas children and nested
        # children alike because we only care about the mouse delta
        # from the press point and apply it (zoom-adjusted) to the
        # logical coordinate stored in properties.
        # ``click_nid`` is the widget that received the tk event;
        # ``nid`` is the one we're actually dragging (after
        # drill-down resolution). Motion events come through the
        # clicked widget's binding so we match against click_nid.
        # Group drag: if multiple widgets are selected, snapshot every
        # place-managed widget's starting x/y so on_motion can shift
        # the whole group by the same delta. Layout-managed children
        # (pack / grid) are excluded — their position is owned by the
        # parent and x/y writes would be stale values only.
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
            # Locked widgets stay put on group drag — otherwise the
            # lock only means "can't delete", which is half a feature.
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
        self._drag = {
            "nid": resolved_nid,
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
        }
        # Shared canvas tag across every top-level widget in the drag
        # group. During motion we issue a single ``canvas.move`` on
        # this tag — one Tk round-trip per frame instead of N — and a
        # matching move for their chrome items so selection outlines
        # track with the widgets. Nested (place-managed) children in
        # the group can't be moved by canvas tag; they fall through to
        # the per-widget place_configure path in on_motion.
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
        # Ghost mode for large groups — hide every tagged widget +
        # chrome and draw a dashed outline rect the size of the group's
        # bounding box. Motion just translates the rect; release runs
        # apply_all once to put widgets at their final positions.
        if len(group_starts) >= HIDE_THRESHOLD:
            self._enter_hidden_mode(group_starts)
        return "break"

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

    def _resolve_click_target(self, clicked_nid: str) -> str:
        """Drill-down selection with shared-context shortcut.

        Three cases, in order of precedence:

        1. Current selection is an ancestor of the clicked widget →
           descend one level toward the click.
        2. Current selection shares a common ancestor with the clicked
           widget (i.e. they're already in the same Frame / parent
           scope) → select the clicked widget directly; no drill-up.
           Lets the user switch between siblings inside a Frame once
           the Frame has been "entered".
        3. No overlap (different branch, or nothing selected) →
           select the outermost ancestor so the user has to descend
           explicitly.
        """
        clicked_node = self.project.get_widget(clicked_nid)
        if clicked_node is None:
            return clicked_nid
        chain: list = []
        cur = clicked_node
        while cur is not None:
            chain.append(cur)
            cur = cur.parent
        chain.reverse()  # [outermost ancestor, ..., clicked]
        if not chain:
            return clicked_nid
        current_id = self.project.selected_id
        if current_id is None:
            return chain[0].id
        # Case 1 — current is an ancestor of clicked (or clicked itself).
        for idx, node in enumerate(chain):
            if node.id == current_id:
                if idx + 1 < len(chain):
                    return chain[idx + 1].id
                return chain[idx].id
        # Case 2 — shared scope. Collect current's ancestor ids (incl.
        # itself) and see if any clicked ancestor (excluding clicked
        # itself) is among them; if so, we're already "inside" that
        # scope.
        current_node = self.project.get_widget(current_id)
        if current_node is not None:
            current_ancestor_ids: set = set()
            c = current_node
            while c is not None:
                current_ancestor_ids.add(c.id)
                c = c.parent
            for node in chain[:-1]:
                if node.id in current_ancestor_ids:
                    return clicked_nid
        # Case 3 — start at outermost.
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
            self._clear_grid_highlight()
            self._destroy_ghost()
            return
        if self._drag is None or self._drag.get("click_nid", self._drag["nid"]) != nid:
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
        # Determine the container under the cursor. If it's a grid
        # container, the drag switches to cell-snap mode: no x/y
        # updates, just a highlight on the target cell so the user
        # sees where the widget will land on release.
        cx, cy = ws._screen_to_canvas(event.x_root, event.y_root)
        target = ws._find_container_at(cx, cy, exclude_id=nid)
        target_grid = (
            target is not None
            and normalise_layout_type(
                target.properties.get("layout_type", "place"),
            ) == "grid"
        )
        node = self.project.get_widget(nid)
        src_layout = (
            normalise_layout_type(
                node.parent.properties.get("layout_type", "place"),
            ) if node is not None and node.parent is not None else "place"
        )
        src_grid = src_layout == "grid"
        src_managed = src_layout in ("vbox", "hbox", "grid")
        # Ghost: pack/grid children can't move via x/y updates, so we
        # surface drag feedback as a small Toplevel following the
        # cursor. place children already slide under the cursor — no
        # ghost needed there.
        if src_managed:
            self._update_ghost(node, event.x_root, event.y_root)
        if target_grid:
            row, col = self._grid_cell_at(target, cx, cy)
            self._draw_grid_highlight(target, row, col)
            return
        # Cursor left a grid container — erase any stale highlight.
        self._clear_grid_highlight()
        if src_grid:
            # Grid-parented widget dragged outside any grid — still
            # skip x/y updates so the model stays clean; we'll either
            # reparent on release or snap back to its current cell.
            return
        if src_managed:
            # pack (vbox/hbox) parent — same story: skip x/y updates.
            return
        zoom = self.zoom.value or 1.0
        dx_logical = int(dx_root / zoom)
        dy_logical = int(dy_root / zoom)
        dx_tick = event.x_root - self._drag["last_mx"]
        dy_tick = event.y_root - self._drag["last_my"]
        hidden_mode = self._drag.get("hidden_mode", False)
        # Visual move — one Tk call shifts every canvas-hosted widget
        # in the group via the shared ``drag_group`` tag, and another
        # shifts their chrome items via ``drag_chrome_group``. This
        # was N canvas.coords + N canvas.move calls per motion before;
        # now 2 calls regardless of group size. Nested place-managed
        # children aren't tagged (they live inside a parent Frame, not
        # on the canvas) — their loop below handles them individually.
        # Ghost mode: widgets + chromes are hidden; we only translate
        # the dashed placeholder rect.
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
                # keep it in sync via place_configure.
                try:
                    if w_widget.winfo_manager() == "place":
                        w_widget.place_configure(
                            x=int(new_x * zoom),
                            y=int(new_y * zoom),
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
        drag = self._drag
        # Clear drag state BEFORE firing any project mutations so
        # ``_schedule_selection_redraw`` stops short-circuiting on
        # ``is_dragging()``. With the guard on, release-time updates
        # (grid snap, reparent, move) would leave selection handles
        # lingering at the pre-drop spot until the next UI event.
        self._drag = None
        self._clear_grid_highlight()
        self._destroy_ghost()
        # Ghost-mode teardown — delete the placeholder rect and unhide
        # every widget + chrome we hid on press. Must happen BEFORE
        # dtag so the itemconfigure has something to match.
        if drag is not None and drag.get("hidden_mode"):
            pid = drag.get("placeholder_id")
            if pid is not None:
                try:
                    self.canvas.delete(pid)
                except tk.TclError:
                    pass
            try:
                self.canvas.itemconfigure(
                    "drag_group", state="normal",
                )
            except tk.TclError:
                pass
            try:
                self.canvas.itemconfigure(
                    "drag_chrome_group", state="normal",
                )
            except tk.TclError:
                pass
            # Widgets were frozen at their press-time canvas positions
            # during motion — run apply_all once to slide them to the
            # drag's final logical x/y.
            self.zoom.apply_all()
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
            else:
                # Top-level drop — two snap-back triggers:
                #   1. Cursor landed in the void (no container, no doc).
                #   2. Any widget in the group ended up off its owning
                #      doc's rectangle (peripheral widgets can be
                #      pushed off-form by a group delta even when the
                #      primary / cursor stays inside).
                # Either trigger → snap the whole group back so users
                # don't end up with silent off-screen widgets.
                cursor_target = (
                    ws._find_container_at(
                        cx_r, cy_r, exclude_id=drag["nid"],
                    ) is not None
                    or ws._find_document_at_canvas(cx_r, cy_r)
                    is not None
                )
                should_snap = not cursor_target
                if not should_snap:
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
                        # The widget's logical x/y is stored in its
                        # current (source) document's space. Translate
                        # it to absolute canvas logical coords and
                        # check whether the drop lands inside *any*
                        # document — cross-doc drops are valid even
                        # though they look off-form from the source
                        # doc's perspective.
                        abs_x = doc.canvas_x + ex
                        abs_y = doc.canvas_y + ey
                        inside_any = any(
                            d.canvas_x <= abs_x < d.canvas_x + d.width
                            and d.canvas_y <= abs_y < d.canvas_y + d.height
                            for d in all_docs
                        )
                        if not inside_any:
                            should_snap = True
                            break
                if should_snap:
                    for wid, (sx, sy) in drag["group_starts"].items():
                        self.project.update_property(wid, "x", sx)
                        self.project.update_property(wid, "y", sy)
                    ws._update_widget_visibility_across_docs()
                    return
            grid_handled = self._maybe_grid_drop(event, drag)
            if not grid_handled:
                reparented = self._maybe_reparent_dragged(event, drag)
                # Skip the Move record if the widget jumped parents — a
                # proper ReparentCommand captures the full before/after,
                # Move would duplicate part of that record.
                if not reparented:
                    # Group move: one BulkMoveCommand covers every
                    # widget shifted by this drag so a single undo
                    # rewinds the whole gesture. Single-widget drags
                    # still go through this path — BulkMoveCommand
                    # degrades cleanly to one entry.
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
                    if moves:
                        self.project.history.push(BulkMoveCommand(moves))
                        # Motion path bypassed the event bus for perf;
                        # fire one pair of property_changed events per
                        # widget now so Inspector + Object Tree pick up
                        # the final x / y. Cheap (≤ 2 × N events, once
                        # per gesture) vs. the per-motion event storm
                        # it would otherwise have to handle.
                        bus = self.project.event_bus
                        for wid, _before, after in moves:
                            for key, val in after.items():
                                bus.publish(
                                    "property_changed", wid, key, val,
                                )
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
    # Drag ghost for layout-managed children
    # ------------------------------------------------------------------
    def _update_ghost(self, node, x_root: int, y_root: int) -> None:
        """Create (or move) a small Toplevel showing the widget's
        display label near the cursor. Needed for pack/grid children
        because their real widgets can't follow the mouse visually.
        """
        if node is None:
            return
        if self._ghost is None:
            label_text = node.name or node.widget_type
            ghost = tk.Toplevel(self.workspace)
            ghost.overrideredirect(True)
            ghost.attributes("-topmost", True)
            try:
                ghost.attributes("-alpha", 0.85)
            except tk.TclError:
                pass
            frame = tk.Frame(
                ghost, bg="#1f6aa5", bd=1, relief="solid",
                highlightthickness=1, highlightbackground="#3b8ed0",
            )
            frame.pack()
            tk.Label(
                frame, text=label_text,
                bg="#1f6aa5", fg="white",
                font=("Segoe UI", 10, "bold"), padx=10, pady=4,
            ).pack()
            ghost.update_idletasks()
            self._ghost = ghost
        try:
            self._ghost.geometry(f"+{x_root + 12}+{y_root + 12}")
        except tk.TclError:
            pass

    def _destroy_ghost(self) -> None:
        if self._ghost is not None:
            try:
                self._ghost.destroy()
            except tk.TclError:
                pass
            self._ghost = None

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
        # Mutate: remove from container, append to doc root, reset x/y
        node.properties["x"] = nx
        node.properties["y"] = ny
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
        old_x = drag["start_x"]
        old_y = drag["start_y"]
        # Compute the widget's new logical x/y in the target's
        # coordinate space.
        widget, _ = self.widget_views[nid]
        zoom = self.zoom.value or 1.0
        if target is None:
            # Top-level drop — logical coords relative to whichever
            # document the drop landed in.
            rx = widget.winfo_rootx() - self.canvas.winfo_rootx()
            ry = widget.winfo_rooty() - self.canvas.winfo_rooty()
            canvas_x = self.canvas.canvasx(rx)
            canvas_y = self.canvas.canvasy(ry)
            target_doc = new_doc or self.project.active_document
            new_x, new_y = self.zoom.canvas_to_logical(
                canvas_x, canvas_y, document=target_doc,
            )
        else:
            target_widget, _ = self.widget_views[target.id]
            rel_x = widget.winfo_rootx() - target_widget.winfo_rootx()
            rel_y = widget.winfo_rooty() - target_widget.winfo_rooty()
            new_x = int(rel_x / zoom)
            new_y = int(rel_y / zoom)
        # Non-place containers (vbox / hbox / grid) ignore child x/y
        # entirely, so the drag-time coord mutations above would just
        # leave stale values in the Inspector. Zero them out so the
        # panel reads 0/0 after the drop instead of the old canvas
        # position.
        if target is not None and normalise_layout_type(
            target.properties.get("layout_type", "place"),
        ) != "place":
            new_x = new_y = 0
        # Write the new coords directly; reparent will trigger a
        # widget rebuild that picks them up.
        node.properties["x"] = max(0, new_x)
        node.properties["y"] = max(0, new_y)
        if cross_doc and target is None:
            # Cross-document top-level move: project.reparent targets
            # the active document, which isn't necessarily the drop
            # target. Pop from old doc, push to new doc manually and
            # raise the reparent event so the workspace rebuilds the
            # widget under the new root.
            if old_doc is not None and node in old_doc.root_widgets:
                old_doc.root_widgets.remove(node)
            node.parent = None
            new_doc.root_widgets.append(node)
            # Manual move bypasses project.reparent, so refresh the
            # widget's doc-index entry (and its subtree's) directly.
            self.project._index_subtree(node, new_doc)
            self.project.event_bus.publish(
                "widget_reparented", nid,
                old_parent_id, new_parent_id,
            )
            # Group cross-doc drag — every other top-level widget
            # the user had selected moved in lockstep visually. The
            # primary just changed document tree; without the loop
            # below the group would end up split (primary in new_doc,
            # others still listed under old_doc). Translate each
            # other widget's x/y from old_doc to new_doc by the
            # difference in canvas offsets so its on-canvas position
            # stays put.
            group_starts = drag.get("group_starts", {})
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
                # old_doc.x_canvas + ox == new_doc.x_canvas + new_ox
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
        else:
            self.project.reparent(nid, new_parent_id)
        # Capture post-reparent index so redo can restore z-order.
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
        self.project.history.push(
            ReparentCommand(
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
            ),
        )
        return True

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
        target_layout = normalise_layout_type(
            target.properties.get("layout_type", "place"),
        )
        if target_layout != "grid":
            return False
        row, col = self._grid_cell_at(target, cx, cy)
        old_parent_id = node.parent.id if node.parent is not None else None
        new_parent_id = target.id
        try:
            old_row = int(node.properties.get("grid_row", 0) or 0)
            old_col = int(node.properties.get("grid_column", 0) or 0)
        except (TypeError, ValueError):
            old_row, old_col = 0, 0
        if new_parent_id == old_parent_id:
            if (row, col) == (old_row, old_col):
                return True  # same cell — no-op drop
            self.project.update_property(nid, "grid_row", row)
            self.project.update_property(nid, "grid_column", col)
            self.project.history.push(
                MultiChangePropertyCommand(
                    nid,
                    {
                        "grid_row": (old_row, row),
                        "grid_column": (old_col, col),
                    },
                ),
            )
            return True
        # Different parent — pre-set the new cell so the reparent's
        # widget rebuild lands at the user's chosen cell, then fall
        # through to the standard reparent flow for the destroy /
        # recreate + history push.
        node.properties["grid_row"] = row
        node.properties["grid_column"] = col
        self._maybe_reparent_dragged(event, drag)
        return True

    def _grid_dimensions(
        self, container_node, *, extra_child: bool = False,
    ) -> tuple[int, int]:
        """Rows × cols of ``container`` — authoritative user-set
        ``grid_rows`` / ``grid_cols``. No auto-grow: children past
        capacity wrap into existing cells (see
        ``grid_cell_for_index``). ``extra_child`` kept for API
        compatibility but no longer affects the answer.
        """
        _ = extra_child
        return grid_effective_dims(
            len(container_node.children), container_node.properties,
        )

    def _grid_cell_at(
        self, container_node, canvas_x: float, canvas_y: float,
    ) -> tuple[int, int]:
        """Map a canvas position to a (row, col) cell on ``container``.
        The cell grid matches the container's current structure — the
        overlay won't show phantom rows/columns past the last filled
        one. To grow the grid the user can drag onto an already-full
        cell (overlap lands a sibling there) or edit row/col directly.
        """
        entry = self.widget_views.get(container_node.id)
        if entry is None:
            return (0, 0)
        widget, _ = entry
        bbox = self.workspace._widget_canvas_bbox(widget)
        if bbox is None:
            return (0, 0)
        x1, y1, x2, y2 = bbox
        nrows, ncols = self._grid_dimensions(container_node)
        cell_w = (x2 - x1) / max(ncols, 1)
        cell_h = (y2 - y1) / max(nrows, 1)
        if cell_w <= 0 or cell_h <= 0:
            return (0, 0)
        col = int((canvas_x - x1) / cell_w)
        row = int((canvas_y - y1) / cell_h)
        col = max(0, min(ncols - 1, col))
        row = max(0, min(nrows - 1, row))
        return (row, col)

    def _draw_grid_highlight(
        self, container_node, row: int, col: int,
    ) -> None:
        """Paint a light-blue outline on the target cell — only the
        border, so the cell's content (if any) stays visible. The
        overlay is four thin ``tk.Frame`` stripes laid out around
        the cell via ``.place()``: a single solid-bg Frame would
        cover anything below, and canvas primitives can't render
        above a window-item Frame. Frames are created ONCE per
        gesture and repositioned on subsequent motion events —
        recreating them every tick freezes the UI.
        """
        cache_key = (container_node.id, row, col)
        if getattr(self, "_grid_highlight_key", None) == cache_key:
            return  # nothing changed
        entry = self.widget_views.get(container_node.id)
        if entry is None:
            self._clear_grid_highlight()
            return
        container_widget, _ = entry
        try:
            cw = int(container_widget.winfo_width())
            ch = int(container_widget.winfo_height())
        except tk.TclError:
            self._clear_grid_highlight()
            return
        if cw <= 0 or ch <= 0:
            self._clear_grid_highlight()
            return
        nrows, ncols = self._grid_dimensions(container_node)
        cell_w = cw / max(ncols, 1)
        cell_h = ch / max(nrows, 1)
        if cell_w <= 0 or cell_h <= 0:
            self._clear_grid_highlight()
            return
        rx = int(col * cell_w) + 2
        ry = int(row * cell_h) + 2
        rw = max(1, int(cell_w) - 4)
        rh = max(1, int(cell_h) - 4)
        stripes = getattr(self, "_grid_highlight", None)
        stripe_parent = getattr(self, "_grid_highlight_parent", None)
        if stripes is not None and stripe_parent is not container_widget:
            self._clear_grid_highlight()
            stripes = None
        if stripes is None:
            try:
                stripes = tuple(
                    tk.Frame(
                        container_widget,
                        bg=GRID_HIGHLIGHT_COLOR,
                        bd=0, highlightthickness=0,
                    )
                    for _ in range(4)
                )
            except tk.TclError:
                return
            self._grid_highlight = stripes
            self._grid_highlight_parent = container_widget
        top, bottom, left, right = stripes
        bw = 2  # border thickness
        try:
            top.place(x=rx, y=ry, width=rw, height=bw)
            bottom.place(x=rx, y=ry + rh - bw, width=rw, height=bw)
            left.place(x=rx, y=ry, width=bw, height=rh)
            right.place(x=rx + rw - bw, y=ry, width=bw, height=rh)
            for stripe in stripes:
                stripe.lift()
        except tk.TclError:
            self._clear_grid_highlight()
            return
        self._grid_highlight_key = cache_key

    def _clear_grid_highlight(self) -> None:
        stripes = getattr(self, "_grid_highlight", None)
        if stripes is not None:
            for stripe in stripes:
                try:
                    stripe.destroy()
                except tk.TclError:
                    pass
        self._grid_highlight = None
        self._grid_highlight_parent = None
        self._grid_highlight_key = None
