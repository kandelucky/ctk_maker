"""Press-time selection + group-tag helpers for ``WidgetDragController``.

Six methods that decide what gets dragged + how it's tagged before
the first motion tick:

* ``resolve_selection`` — three-branch press-time policy:
  Ctrl+click → multi-toggle, click on existing multi-selection →
  keep group, plain → Unity-style drill-down via
  ``resolve_click_target``. Returns ``None`` to ignore the click
  (locked canvas widget with no unlocked ancestor).
* ``resolve_click_target`` — fast-click-gated drill-down. First
  click selects the outermost unlocked ancestor; a follow-up
  within ``_DRILL_WINDOW_MS`` drills one level deeper. Shared
  with the right-click context menu via a pass-through on the
  controller.
* ``build_group_starts`` — snapshot every place-managed selected
  widget's press-time x/y so motion can shift the whole group by
  one delta. Locked widgets and pack/grid children skip the
  snapshot.
* ``collect_grid_candidates`` — cache the project's grid
  containers at press time so motion can hit-test just these
  instead of an O(N) walk per tick.
* ``tag_drag_group`` — stamp the shared ``drag_group`` +
  ``drag_chrome_group`` canvas tags so one ``canvas.move(tag,
  dx, dy)`` per frame shifts the whole group.
* ``enter_hidden_mode`` — for groups past ``HIDE_THRESHOLD``,
  hide every tagged widget + chrome and replace them with a
  single dashed-rect placeholder so motion stays smooth.

State (``_last_click_leaf_id`` / ``_last_click_time_ms``) lives on
the controller so successive press events share the drill-down
state — same controller instance bridges click N and click N+1.
"""
from __future__ import annotations

import tkinter as tk

from app.widgets.layout_schema import normalise_layout_type
from app.widgets.registry import get_descriptor


HIDE_THRESHOLD = 10
HIDE_OUTLINE_COLOR = "#3b8ed0"


class DragClickResolver:
    """Press-time selection + group tagging. See module docstring."""

    def __init__(self, controller) -> None:
        self.controller = controller

    def resolve_selection(self, event, nid: str) -> str | None:
        """Figure out which widget the press actually targets. Three
        branches:

        - Ctrl+click → multi-select toggle (add or remove nid).
        - Plain click inside an existing multi-selection → keep the
          group intact (Photoshop / Figma convention) so the drag
          moves everyone together.
        - Otherwise → Unity-style drill-down via
          ``resolve_click_target``; updates the single selection.

        Returns ``None`` when the click should be ignored — currently
        that's a canvas click on a locked widget (and its chain has
        no unlocked alternative). Locked widgets are only reachable
        via the Object Tree.
        """
        ctl = self.controller
        ws = ctl.workspace
        multi = bool(event.state & 0x0004)
        existing_ids = set(
            getattr(ctl.project, "selected_ids", set()) or set(),
        )
        # Canvas clicks on locked widgets are silently ignored — all
        # three branches below would otherwise either select or toggle
        # the locked id, which Figma / Photoshop treat as off-limits.
        if ws._effective_locked(nid):
            return None
        if multi:
            current_ids = set(existing_ids)
            # Ctrl+click on a grouped widget toggles the whole group —
            # never picks just one member. Keeps the within-group
            # invariant (no partial group selections) consistent with
            # plain-click and drag, so a Ctrl+G that follows can't
            # silently break an existing group.
            clicked_node = ctl.project.get_widget(nid)
            click_gid = (
                getattr(clicked_node, "group_id", None)
                if clicked_node is not None else None
            )
            target_ids = {nid}
            if click_gid:
                target_ids = {
                    m.id for m in ctl.project.iter_group_members(click_gid)
                }
            if target_ids.issubset(current_ids):
                current_ids -= target_ids
                new_primary = next(iter(current_ids), None)
            else:
                # Cross-parent shift+click clears the prior selection
                # so multi-select stays single-parent only — keeps
                # Group/Ungroup, drag, and reparent invariants simple
                # (everything operates inside one geometry context).
                clicked_parent = (
                    clicked_node.parent.id
                    if clicked_node is not None
                       and clicked_node.parent is not None
                    else None
                )
                existing_parents: set = set()
                for wid in current_ids:
                    n = ctl.project.get_widget(wid)
                    if n is None:
                        continue
                    existing_parents.add(
                        n.parent.id if n.parent is not None else None,
                    )
                if existing_parents and clicked_parent not in existing_parents:
                    current_ids = set()
                current_ids |= target_ids
                new_primary = nid
            ctl.project.set_multi_selection(current_ids, new_primary)
            # Entering multi-select while in Edit mode flips the tool
            # to Select — resize handles don't make sense for a group,
            # and property edits on multi are ambiguous.
            if len(current_ids) > 1 and ws.controls.tool == "edit":
                ws.controls.set_tool("select")
            return new_primary or nid
        # Group-member shortcut — bypasses the Frame-outermost drill
        # so a click on a grouped widget targets the group directly:
        #   - cold click on a member → whole group selected
        #   - fast follow-up click on the same member → drill to
        #     single member (Figma-style)
        #   - slow follow-up → group stays as-is (no change), so
        #     the user can repeatedly grab + reposition the group
        #     without the selection cycling out from under them
        # Mirrors the Frame drill-down rhythm in resolve_click_target
        # (same _DRILL_WINDOW_MS, same _last_click_* state).
        clicked_node = ctl.project.get_widget(nid)
        click_gid = (
            getattr(clicked_node, "group_id", None)
            if clicked_node is not None else None
        )
        if click_gid and not ws._effective_locked(nid):
            members = list(ctl.project.iter_group_members(click_gid))
            member_ids = {m.id for m in members}
            if len(member_ids) > 1:
                now_ms = int(ws.tk.call("clock", "milliseconds"))
                same_leaf = nid == ctl._last_click_leaf_id
                within_window = (
                    now_ms - ctl._last_click_time_ms
                ) <= ctl._DRILL_WINDOW_MS
                fast_follow_up = same_leaf and within_window
                # Update the stamp BEFORE returning so the next
                # click sees the correct timing context.
                ctl._last_click_leaf_id = nid
                ctl._last_click_time_ms = now_ms
                if existing_ids == member_ids:
                    if fast_follow_up:
                        # Fast click on member of selected group → drill
                        ctl.project.select_widget(nid)
                        return nid
                    # Slow click — keep group selected, no change.
                    return nid
                # Group is already part of a larger multi-selection
                # (e.g. {Button, Frame, group A,B,C}) — clicking a
                # member should NOT collapse the selection back down
                # to just the group, so the press still drags every
                # selected widget together.
                if member_ids.issubset(existing_ids):
                    return nid
                # Cold / unrelated previous selection → whole group
                ctl.project.set_multi_selection(member_ids, nid)
                if ws.controls.tool == "edit":
                    ws.controls.set_tool("select")
                return nid
        if len(existing_ids) > 1 and nid in existing_ids:
            return nid
        resolved = self.resolve_click_target(nid)
        if resolved is None:
            return None
        ctl.project.select_widget(resolved)
        return resolved

    def build_group_starts(self, resolved_nid: str) -> dict:
        """Snapshot every place-managed selected widget's press-time
        x/y so ``DragMotion.motion_place_group`` can shift the whole
        group by a single delta. Locked widgets stay put; pack/grid
        children skip the snapshot entirely because their positions
        are parent-owned and any x/y we wrote would be stale on
        release.
        """
        ctl = self.controller
        ws = ctl.workspace
        selected_ids = set(
            getattr(ctl.project, "selected_ids", set()) or set(),
        )
        if resolved_nid not in selected_ids:
            selected_ids = {resolved_nid}
        # Group expansion — drag of any grouped widget always carries
        # every member of its group, regardless of which member is
        # currently the selection. Keeps the group invariant: a
        # single member can't be moved away from its siblings.
        for wid in list(selected_ids):
            w_node = ctl.project.get_widget(wid)
            gid = (
                getattr(w_node, "group_id", None)
                if w_node is not None else None
            )
            if gid:
                for member in ctl.project.iter_group_members(gid):
                    selected_ids.add(member.id)
        group_starts: dict = {}
        for wid in selected_ids:
            w_node = ctl.project.get_widget(wid)
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

    def collect_grid_candidates(self, exclude_id: str) -> list:
        """Return every grid-layout container in the project whose
        subtree doesn't include ``exclude_id`` (skip self so a widget
        can't drop into itself). The list is used by ``motion_feedback``
        to hit-test grid-cell highlights without the per-tick O(N)
        ``_find_container_at`` tree walk — for most projects this is
        a 0- to 2-entry list, so motion tick cost collapses.
        """
        ctl = self.controller
        candidates: list = []
        for node in ctl.project.iter_all_widgets():
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

    def tag_drag_group(self, group_starts: dict) -> None:
        """Stamp every group member with the shared ``drag_group`` +
        ``drag_chrome_group`` canvas tags so ``motion_place_group``
        can move them all with a single ``canvas.move(tag, dx, dy)``
        per frame instead of N round-trips. Nested (place-managed)
        children can't be tagged — they're inside a parent Frame, not
        on the canvas — and fall through to per-widget
        ``place_configure`` in motion.
        """
        ctl = self.controller
        for wid in group_starts.keys():
            entry = ctl.widget_views.get(wid)
            if entry is None:
                continue
            _, window_id = entry
            if window_id is not None:
                try:
                    ctl.canvas.addtag_withtag("drag_group", window_id)
                except tk.TclError:
                    pass
            try:
                ctl.canvas.addtag_withtag(
                    "drag_chrome_group", f"chrome_wid_{wid}",
                )
            except tk.TclError:
                pass
        # Pull every visible orange group-bbox frame into the drag
        # chrome tag so the bbox follows the moving widgets per tick.
        # (The bbox frames live in selection_controller's pool, not
        # under any chrome_wid_ tag, so they need explicit tagging.)
        pool = getattr(
            ctl.workspace.selection, "_group_bbox_pool", [],
        )
        for entry in pool:
            for window_id, _frame in entry.values():
                try:
                    state = ctl.canvas.itemcget(window_id, "state")
                except tk.TclError:
                    continue
                if state == "hidden":
                    continue
                try:
                    ctl.canvas.addtag_withtag(
                        "drag_chrome_group", window_id,
                    )
                except tk.TclError:
                    pass

    def enter_hidden_mode(self, group_starts: dict) -> None:
        """Swap from live widget dragging to a single dashed-rect
        placeholder. Stores the placeholder item id + unhide state on
        ``controller._drag`` so release can tear down the ghost cleanly.
        """
        ctl = self.controller
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")
        for wid in group_starts.keys():
            entry = ctl.widget_views.get(wid)
            if entry is None:
                continue
            _, window_id = entry
            if window_id is None:
                continue
            try:
                bbox = ctl.canvas.bbox(window_id)
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
            placeholder_id = ctl.canvas.create_rectangle(
                min_x, min_y, max_x, max_y,
                outline=HIDE_OUTLINE_COLOR, dash=(4, 4),
                width=2, fill="",
            )
        except tk.TclError:
            return
        try:
            ctl.canvas.itemconfigure("drag_group", state="hidden")
        except tk.TclError:
            pass
        try:
            ctl.canvas.itemconfigure(
                "drag_chrome_group", state="hidden",
            )
        except tk.TclError:
            pass
        ctl._drag["hidden_mode"] = True
        ctl._drag["placeholder_id"] = placeholder_id

    def resolve_click_target(self, clicked_nid: str) -> str | None:
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
        ctl = self.controller
        ws = ctl.workspace
        clicked_node = ctl.project.get_widget(clicked_nid)
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
        now_ms = int(ws.tk.call("clock", "milliseconds"))
        same_leaf = clicked_nid == ctl._last_click_leaf_id
        within_window = (now_ms - ctl._last_click_time_ms) <= ctl._DRILL_WINDOW_MS
        fast_follow_up = same_leaf and within_window
        # Stamp for the next click BEFORE returning so nested returns
        # all share the same post-condition.
        ctl._last_click_leaf_id = clicked_nid
        ctl._last_click_time_ms = now_ms

        current_id = ctl.project.selected_id
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
            current_node = ctl.project.get_widget(current_id)
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
