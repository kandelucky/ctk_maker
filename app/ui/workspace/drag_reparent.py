"""Drop-time reparent + extract + grid-snap helpers for
``WidgetDragController``.

Owns every branch the release path takes after the threshold check
+ snap-back gate:

* ``maybe_extract_from_container`` — child was dragged out of its
  container; the helper either hops the whole group (when every
  drag member shares the source parent) or the single primary to
  the source document's root. Returns True when extraction ran
  (callers skip grid / reparent fallbacks).
* ``maybe_grid_drop`` — explicit drop into a grid cell. Resolves
  the cursor cell, redirects to a free slot when occupied, and
  pushes a ``MultiChangePropertyCommand`` (same parent) or hands
  off to the standard reparent flow (different parent).
* ``maybe_reparent_dragged`` — main entry point for "dropped into
  different container OR different document". Handles cross-doc
  variable-policy prompt + cross-doc group move + in-doc group
  reparent + single-widget reparent paths.

Plus the small computational helpers each branch needs:

* ``compute_drop_coords`` — resolve the dragged widget's logical
  x/y in the target's coordinate space (canvas → logical via
  ``canvas_scale``; Tabview targets measure against the active
  tab's inner frame).
* ``resolve_tabview_slot`` — return the active tab name when the
  target is a Tabview; None otherwise.
* ``push_reparent_command`` — compute post-reparent sibling index
  + emit a single ``ReparentCommand``.
* ``resolve_cross_doc_var_policy`` — surface the cross-doc
  variable dialog when bound local vars cross document boundaries.
* ``revert_drag_visuals`` — force destroy+recreate of every
  dragged widget via the lifecycle subscriber when a cross-doc
  drag is cancelled.

All state reads/writes go through ``controller`` so the helper
stays purely behavioural.
"""
from __future__ import annotations

from app.core.commands import (
    BulkReparentCommand,
    MultiChangePropertyCommand,
    ReparentCommand,
)
from app.widgets.layout_schema import (
    is_layout_container,
    normalise_layout_type,
    resolve_grid_drop_cell,
)


class DragReparent:
    """Drop-time reparent / extract / grid-snap helper.
    See module docstring.
    """

    def __init__(self, controller) -> None:
        self.controller = controller

    # ------------------------------------------------------------------
    # Container extraction (two-step reparent)
    # ------------------------------------------------------------------
    def maybe_extract_from_container(self, event, drag: dict) -> bool:
        """Extract a child out of its container to the source document's
        root at a cascade-offset default position. Fires only when the
        widget started inside a container and wasn't dropped inside
        that same container. Returns True when extraction happened —
        callers skip grid / reparent fallbacks after.

        Multi-widget grouped extracts: when ``drag_ids`` covers more
        than the primary AND every member shares the source parent
        (group invariant), the whole group is extracted together so
        the user can drag a group out of a Frame as one unit.
        """
        ctl = self.controller
        ws = ctl.workspace
        nid = drag["nid"]
        node = ctl.project.get_widget(nid)
        if node is None or node.parent is None:
            return False
        ctl.canvas.update_idletasks()
        cx, cy = ws._screen_to_canvas(event.x_root, event.y_root)
        target = ws._find_container_at(cx, cy, exclude_id=nid)
        if target is not None and target.id == node.parent.id:
            return False
        old_parent_id = node.parent.id
        old_doc = (
            ctl.project.find_document_for_widget(nid)
            or ctl.project.active_document
        )
        if old_doc is None:
            return False
        # Multi-widget group extract — when every group_starts member
        # shares ``old_parent_id``, extract them all together so the
        # group invariant survives. Single-widget path stays the same.
        drag_ids = list(drag.get("group_starts", {}).keys())
        all_share_parent = (
            len(drag_ids) >= 2
            and nid in drag_ids
            and all(
                (lambda w: w is not None and w.parent is not None
                 and w.parent.id == old_parent_id)(
                    ctl.project.get_widget(wid),
                )
                for wid in drag_ids
            )
        )
        if all_share_parent:
            self._perform_group_extract(
                event, drag, old_parent_id, old_doc, cx, cy,
            )
            return True
        # Single-widget path.
        cursor_doc = ws._find_document_at_canvas(cx, cy)
        if cursor_doc is old_doc:
            lx, ly = ctl.zoom.canvas_to_logical(cx, cy, document=old_doc)
            try:
                w = int(node.properties.get("width", 0) or 0)
                h = int(node.properties.get("height", 0) or 0)
            except (TypeError, ValueError):
                w = h = 0
            nx = max(0, min(lx - w // 2, max(0, old_doc.width - w)))
            ny = max(0, min(ly - h // 2, max(0, old_doc.height - h)))
        else:
            from app.core.project import find_free_cascade_slot
            nx, ny = find_free_cascade_slot(
                old_doc.root_widgets, start_xy=(20, 20), exclude=node,
            )
        old_siblings = node.parent.children
        try:
            old_index = old_siblings.index(node)
        except ValueError:
            old_index = len(old_siblings)
        old_x = drag["start_x"]
        old_y = drag["start_y"]
        old_parent_slot = node.parent_slot
        node.properties["x"] = nx
        node.properties["y"] = ny
        node.parent_slot = None
        if node in old_siblings:
            old_siblings.remove(node)
        node.parent = None
        old_doc.root_widgets.append(node)
        ctl.project.event_bus.publish(
            "widget_reparented", nid, old_parent_id, None,
        )
        same_doc_id = old_doc.id if old_doc is not None else None
        ctl.project.history.push(
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

    def _perform_group_extract(
        self, event, drag: dict, old_parent_id: str,
        old_doc, cx: float, cy: float,
    ) -> None:
        """Extract every widget in ``drag['group_starts']`` from a
        shared container to the source document's root, preserving
        each member's relative offset to the primary so the group
        keeps its visual layout after the drop. Pushes a single
        ``BulkReparentCommand`` so undo rewinds everything together.
        """
        ctl = self.controller
        ws = ctl.workspace
        nid = drag["nid"]
        primary = ctl.project.get_widget(nid)
        if primary is None:
            return
        # Anchor: where the cursor lands in old_doc's logical coords
        # (or a cascade slot when dropped on a different form).
        cursor_doc = ws._find_document_at_canvas(cx, cy)
        try:
            primary_w = int(primary.properties.get("width", 0) or 0)
            primary_h = int(primary.properties.get("height", 0) or 0)
        except (TypeError, ValueError):
            primary_w = primary_h = 0
        if cursor_doc is old_doc:
            lx, ly = ctl.zoom.canvas_to_logical(
                cx, cy, document=old_doc,
            )
            anchor_x = max(0, min(
                lx - primary_w // 2,
                max(0, old_doc.width - primary_w),
            ))
            anchor_y = max(0, min(
                ly - primary_h // 2,
                max(0, old_doc.height - primary_h),
            ))
        else:
            from app.core.project import find_free_cascade_slot
            anchor_x, anchor_y = find_free_cascade_slot(
                old_doc.root_widgets, start_xy=(20, 20), exclude=primary,
            )
        # Compute per-member offset from the primary's pre-drag pos.
        primary_start_x, primary_start_y = drag["group_starts"][nid]
        snapshots: list = []
        old_parent_node = ctl.project.get_widget(old_parent_id)
        old_siblings = (
            old_parent_node.children if old_parent_node is not None
            else []
        )
        same_doc_id = old_doc.id
        drag_ids = list(drag["group_starts"].keys())
        for wid in drag_ids:
            w_node = ctl.project.get_widget(wid)
            if w_node is None:
                continue
            sx, sy = drag["group_starts"][wid]
            try:
                old_idx = old_siblings.index(w_node)
            except ValueError:
                old_idx = len(old_siblings)
            old_parent_slot = w_node.parent_slot
            new_x = max(0, anchor_x + (sx - primary_start_x))
            new_y = max(0, anchor_y + (sy - primary_start_y))
            snapshots.append({
                "wid": wid, "old_index": old_idx,
                "old_x": sx, "old_y": sy,
                "new_x": new_x, "new_y": new_y,
                "old_parent_slot": old_parent_slot,
            })
        # Mutate in two phases: detach all from old parent, then
        # append to doc root in original sibling order so z-order
        # carries over to the new top-level layer.
        nodes_to_move: list = []
        for snap in snapshots:
            w_node = ctl.project.get_widget(snap["wid"])
            if w_node is None:
                continue
            w_node.properties["x"] = snap["new_x"]
            w_node.properties["y"] = snap["new_y"]
            w_node.parent_slot = None
            if w_node in old_siblings:
                old_siblings.remove(w_node)
            w_node.parent = None
            nodes_to_move.append(w_node)
        # Stable order: lowest old_index first → preserves z-order
        # in the new container.
        nodes_to_move.sort(
            key=lambda n: next(
                (s["old_index"] for s in snapshots if s["wid"] == n.id),
                0,
            ),
        )
        for w_node in nodes_to_move:
            old_doc.root_widgets.append(w_node)
            ctl.project.event_bus.publish(
                "widget_reparented", w_node.id, old_parent_id, None,
            )
        # Push BulkReparentCommand — one entry per moved member.
        cmds: list = []
        for snap in snapshots:
            w_node = ctl.project.get_widget(snap["wid"])
            if w_node is None:
                continue
            try:
                new_idx = old_doc.root_widgets.index(w_node)
            except ValueError:
                new_idx = len(old_doc.root_widgets) - 1
            cmds.append(ReparentCommand(
                snap["wid"],
                old_parent_id=old_parent_id,
                old_index=snap["old_index"],
                old_x=snap["old_x"],
                old_y=snap["old_y"],
                new_parent_id=None,
                new_index=new_idx,
                new_x=snap["new_x"],
                new_y=snap["new_y"],
                old_document_id=same_doc_id,
                new_document_id=same_doc_id,
                old_parent_slot=snap["old_parent_slot"],
                new_parent_slot=None,
            ))
        if len(cmds) == 1:
            ctl.project.history.push(cmds[0])
        elif cmds:
            ctl.project.history.push(BulkReparentCommand(cmds))

    # ------------------------------------------------------------------
    # Reparent detection
    # ------------------------------------------------------------------
    def maybe_reparent_dragged(self, event, drag: dict) -> bool:
        """On drag release, check if the widget was dropped into a
        different container OR a different document. Either case
        reparents (containers via ``project.reparent``, cross-doc via
        a manual move between document root lists) so undo + rendering
        stay consistent. Returns True when a reparent happened so the
        caller skips the per-widget Move history record.

        ``drag`` is the captured gesture snapshot — ``controller._drag``
        has already been cleared by ``on_release`` (so the selection
        redraw guard sees ``is_dragging() == False``), hence the
        explicit parameter.
        """
        ctl = self.controller
        ws = ctl.workspace
        nid = drag["nid"]
        node = ctl.project.get_widget(nid)
        if node is None:
            return False
        ctl.canvas.update_idletasks()
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
        old_doc = ctl.project.find_document_for_widget(nid)
        if target is not None:
            new_doc = ctl.project.find_document_for_widget(target.id)
        else:
            new_doc = (
                ws._find_document_at_canvas(cx, cy)
                or old_doc
                or ctl.project.active_document
            )
        cross_doc = new_doc is not None and new_doc is not old_doc
        if new_parent_id == old_parent_id and not cross_doc:
            return False  # same parent, same doc — in-place drag
        # Cross-doc var policy dialog. Fires only when the moved
        # subtree(s) bind ≥1 local variable owned by the source doc.
        # Cancelled dialog aborts the whole reparent BEFORE any
        # geometry or tree mutation happens. No-op when bindings are
        # all global / absent. Stored on the drag dict so the
        # subsequent branches (manual cross-doc move, in-doc group,
        # single reparent) all reuse the same answer.
        proceed, policy = self._resolve_cross_doc_var_policy(
            drag, old_doc, new_doc, cross_doc,
        )
        if not proceed:
            return True  # Treat cancel as "we handled this drop" —
            # caller skips the per-widget Move record so the widget
            # stays put in its original parent / doc.
        drag["_var_policy"] = policy
        # Capture the pre-reparent state for undo BEFORE any mutation.
        old_siblings = (
            node.parent.children if node.parent is not None
            else (
                old_doc.root_widgets if old_doc is not None
                else ctl.project.root_widgets
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
        # Multi-widget group reparent — when the drag carries a full
        # selection (clicked a grouped widget), every member must
        # follow the primary into the new parent. Without this only
        # the clicked widget reparents and the rest stay in the old
        # Frame visually shifted by the drag delta.
        if self._perform_in_doc_group_reparent(
            drag, target, new_parent_id, old_parent_id,
            old_doc, new_doc, new_parent_slot, old_parent_slot,
        ):
            return True
        # Pass ``document_id`` so the project can detect a cross-doc
        # drop without falling back to the (possibly stale) active
        # document. Local-variable migration is policy-driven: the
        # cross-doc dialog's pick lands in ``drag["_var_policy"]``;
        # we apply it after the move completes so
        # ``find_document_for_widget`` sees the widget at its new
        # home before the migrate helper walks the subtree.
        ctl.project.reparent(
            nid, new_parent_id,
            document_id=(new_doc.id if new_doc is not None else None),
        )
        policy = drag.get("_var_policy")
        if policy is not None and new_doc is not None:
            moved_node = ctl.project.get_widget(nid)
            if moved_node is not None:
                ctl.project.migrate_local_var_bindings(
                    moved_node, new_doc,
                    source_policy=policy[0], target_policy=policy[1],
                )
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
        ctl = self.controller
        if target is None or target.widget_type != "CTkTabview":
            return None
        entry = ctl.widget_views.get(target.id)
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
        ctl = self.controller
        widget, _ = ctl.widget_views[nid]
        if target is None:
            rx = widget.winfo_rootx() - ctl.canvas.winfo_rootx()
            ry = widget.winfo_rooty() - ctl.canvas.winfo_rooty()
            canvas_x = ctl.canvas.canvasx(rx)
            canvas_y = ctl.canvas.canvasy(ry)
            target_doc = new_doc or ctl.project.active_document
            new_x, new_y = ctl.zoom.canvas_to_logical(
                canvas_x, canvas_y, document=target_doc,
            )
            return new_x, new_y
        target_widget, _ = ctl.widget_views[target.id]
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
        canvas_scale = ctl.zoom.canvas_scale or 1.0
        rel_x = widget.winfo_rootx() - coord_ref.winfo_rootx()
        rel_y = widget.winfo_rooty() - coord_ref.winfo_rooty()
        new_x = int(rel_x / canvas_scale)
        new_y = int(rel_y / canvas_scale)
        if normalise_layout_type(
            target.properties.get("layout_type", "place"),
        ) != "place":
            new_x = new_y = 0
        return new_x, new_y

    def _perform_in_doc_group_reparent(
        self, drag: dict, target, new_parent_id: str | None,
        old_parent_id: str | None, old_doc, new_doc,
        new_parent_slot: str | None, old_parent_slot: str | None,
    ) -> bool:
        """Same-doc multi-widget reparent for a grouped drag. Returns
        True when the multi-widget path ran (and pushed bulk undo);
        False to fall through to the single-widget reparent.

        Triggers only when (a) the drag carries 2+ widgets, (b) every
        carried widget shares ``old_parent_id``, and (c) every widget
        has place layout. Mixed-parent or non-place groups fall back
        to the single-widget path so behavior degrades gracefully
        instead of corrupting the model.
        """
        ctl = self.controller
        nid = drag["nid"]
        drag_ids = list(drag.get("group_starts", {}).keys())
        if len(drag_ids) < 2 or nid not in drag_ids:
            return False
        # Every member must share the primary's source parent — group
        # invariants enforce this at Group time, but a stale selection
        # might still slip through, so verify.
        for wid in drag_ids:
            w_node = ctl.project.get_widget(wid)
            if w_node is None:
                return False
            wp_id = (
                w_node.parent.id if w_node.parent is not None else None
            )
            if wp_id != old_parent_id:
                return False
        # Snapshot every member's pre-reparent state before any of
        # them get moved — needed for the bulk undo path.
        snapshots: list = []
        for wid in drag_ids:
            w_node = ctl.project.get_widget(wid)
            if w_node is None:
                continue
            siblings = (
                w_node.parent.children if w_node.parent is not None
                else (
                    old_doc.root_widgets if old_doc is not None
                    else ctl.project.root_widgets
                )
            )
            try:
                old_idx = siblings.index(w_node)
            except ValueError:
                old_idx = len(siblings)
            sx, sy = drag["group_starts"][wid]
            snapshots.append({
                "wid": wid, "old_index": old_idx,
                "old_x": sx, "old_y": sy,
            })
        # Reparent each member with its own target-space coords.
        # Primary already has its coords updated by the caller — skip
        # the recompute for it; for everyone else, _compute_drop_coords
        # reads the post-drag canvas position so each lands relative
        # to the target.
        for wid in drag_ids:
            w_node = ctl.project.get_widget(wid)
            if w_node is None:
                continue
            if wid != nid:
                wx, wy = self._compute_drop_coords(wid, target, new_doc)
                w_node.properties["x"] = max(0, wx)
                w_node.properties["y"] = max(0, wy)
                w_node.parent_slot = new_parent_slot
            # Pass document_id so cross-doc moves resolve target doc
            # without falling back to the active doc.
            ctl.project.reparent(
                wid, new_parent_id,
                document_id=(new_doc.id if new_doc is not None else None),
            )
            policy = drag.get("_var_policy")
            if policy is not None and new_doc is not None:
                moved = ctl.project.get_widget(wid)
                if moved is not None:
                    ctl.project.migrate_local_var_bindings(
                        moved, new_doc,
                        source_policy=policy[0],
                        target_policy=policy[1],
                    )
        # Bulk undo command, one per member, in the same order they
        # were reparented so redo replays the original sequence.
        old_doc_id = old_doc.id if old_doc is not None else None
        new_doc_id = new_doc.id if new_doc is not None else old_doc_id
        reparent_cmds: list = []
        for snap in snapshots:
            wid = snap["wid"]
            w_node = ctl.project.get_widget(wid)
            if w_node is None:
                continue
            new_siblings = (
                w_node.parent.children if w_node.parent is not None
                else ctl.project.root_widgets
            )
            try:
                new_idx = new_siblings.index(w_node)
            except ValueError:
                new_idx = len(new_siblings) - 1
            try:
                new_x = int(w_node.properties.get("x", 0))
                new_y = int(w_node.properties.get("y", 0))
            except (TypeError, ValueError):
                new_x = new_y = 0
            reparent_cmds.append(ReparentCommand(
                wid,
                old_parent_id=old_parent_id,
                old_index=snap["old_index"],
                old_x=snap["old_x"],
                old_y=snap["old_y"],
                new_parent_id=new_parent_id,
                new_index=new_idx,
                new_x=new_x,
                new_y=new_y,
                old_document_id=old_doc_id,
                new_document_id=new_doc_id,
                old_parent_slot=old_parent_slot if wid == nid else None,
                new_parent_slot=new_parent_slot,
            ))
        if len(reparent_cmds) == 1:
            ctl.project.history.push(reparent_cmds[0])
        elif reparent_cmds:
            ctl.project.history.push(BulkReparentCommand(reparent_cmds))
        return True

    def _resolve_cross_doc_var_policy(
        self, drag: dict, old_doc, new_doc, cross_doc: bool,
    ) -> tuple[bool, tuple[str, str] | None]:
        """Show the cross-doc variable dialog when the moved subtree
        binds local vars from the source doc. Returns:

        ``(True, None)``         no dialog needed (in-doc move, no
                                 cross-doc bindings, etc.).
        ``(True, (src, tgt))``   user picked source + target policies.
        ``(False, None)``        user cancelled — caller aborts.

        Aggregates all dragged top-level nodes (single + group) into
        one survey so a multi-widget drag asks once for the whole
        selection.
        """
        ctl = self.controller
        if not cross_doc or new_doc is None:
            return True, None
        moved_ids = set()
        nid = drag.get("nid")
        if nid:
            moved_ids.add(nid)
        for gid in (drag.get("group_starts") or {}):
            moved_ids.add(gid)
        moved_nodes = []
        for wid in moved_ids:
            n = ctl.project.get_widget(wid)
            if n is not None:
                moved_nodes.append(n)
        var_entries, external = (
            ctl.project.collect_cross_doc_local_vars(
                moved_nodes, new_doc,
            )
        )
        if not var_entries:
            return True, None
        from app.ui.variables_window import ReparentVariablesDialog
        try:
            parent = ctl.workspace.winfo_toplevel()
        except Exception:
            parent = ctl.canvas.winfo_toplevel()
        dialog = ReparentVariablesDialog(
            parent,
            source_doc_name=old_doc.name if old_doc is not None else "",
            target_doc_name=new_doc.name,
            var_entries=var_entries,
            external_usage=external,
        )
        dialog.wait_window()
        if dialog.result is None:
            self._revert_drag_visuals(drag)
            return False, None
        return True, dialog.result

    def _revert_drag_visuals(self, drag: dict) -> None:
        """Force a full destroy + recreate of each dragged widget so
        the canvas re-renders at its (unchanged) model parent / x / y.

        ``property_changed`` alone wasn't enough — during a cross-doc
        drag the widget can end up visually inside the *other* doc's
        canvas region, and only widget_lifecycle's ``on_widget_reparented``
        path tears that view down and rebuilds it under the original
        master. Publishing the event with same-parent on both ends
        triggers exactly that destroy + recreate without changing the
        model.
        """
        ctl = self.controller
        bus = ctl.project.event_bus
        ids = set()
        nid = drag.get("nid")
        if nid:
            ids.add(nid)
        for gid in (drag.get("group_starts") or {}):
            ids.add(gid)
        for wid in ids:
            node = ctl.project.get_widget(wid)
            if node is None:
                continue
            try:
                same_parent = (
                    node.parent.id if node.parent is not None else None
                )
                bus.publish(
                    "widget_reparented", wid, same_parent, same_parent,
                )
            except Exception:
                pass

    def _perform_cross_doc_group_move(
        self, drag: dict, old_doc, new_doc,
        old_parent_id: str | None, new_parent_id: str | None,
    ) -> None:
        """Manually move every top-level group member from old_doc to
        new_doc + push a BulkReparentCommand so one undo rewinds the
        whole group. A single ReparentCommand alone would strand the
        non-primary members in new_doc on undo.
        """
        ctl = self.controller
        nid = drag["nid"]
        node = ctl.project.get_widget(nid)
        group_starts = drag.get("group_starts", {})
        old_doc_id = old_doc.id if old_doc is not None else None
        new_doc_id = new_doc.id
        # Snapshot every member's pre-move state BEFORE any mutation.
        snapshots: list = []
        old_doc_rw = (
            old_doc.root_widgets if old_doc is not None else []
        )
        for wid, (sx, sy) in group_starts.items():
            w_node = ctl.project.get_widget(wid)
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
            ctl.project._index_subtree(node, new_doc)
            # Local-variable migration runs with the policy picked by
            # the cross-doc dialog (or skipped entirely when no local
            # bindings cross). ``drag["_var_policy"]`` is set by
            # ``_resolve_cross_doc_var_policy`` before any mutation.
            policy = drag.get("_var_policy")
            if policy is not None:
                ctl.project.migrate_local_var_bindings(
                    node, new_doc,
                    source_policy=policy[0], target_policy=policy[1],
                )
            ctl.project.event_bus.publish(
                "widget_reparented", nid,
                old_parent_id, new_parent_id,
            )
        # Remaining members in press order — keeps their new-doc
        # index matching the visual stack.
        for wid in list(group_starts.keys()):
            if wid == nid:
                continue
            other = ctl.project.get_widget(wid)
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
            ctl.project._index_subtree(other, new_doc)
            policy = drag.get("_var_policy")
            if policy is not None:
                ctl.project.migrate_local_var_bindings(
                    other, new_doc,
                    source_policy=policy[0], target_policy=policy[1],
                )
            ctl.project.event_bus.publish(
                "widget_reparented", wid, None, None,
            )
        # Build per-member ReparentCommand + push bulk.
        reparent_cmds: list = []
        for snap in snapshots:
            g_wid = snap["wid"]
            g_node = ctl.project.get_widget(g_wid)
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
            ctl.project.history.push(reparent_cmds[0])
        elif reparent_cmds:
            ctl.project.history.push(BulkReparentCommand(reparent_cmds))

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
        ctl = self.controller
        post_node = ctl.project.get_widget(nid)
        if post_node is not None:
            new_siblings = (
                post_node.parent.children if post_node.parent is not None
                else ctl.project.root_widgets
            )
            try:
                new_index = new_siblings.index(post_node)
            except ValueError:
                new_index = len(new_siblings) - 1
        else:
            new_index = 0
        old_doc_id = old_doc.id if old_doc is not None else None
        new_doc_id = new_doc.id if new_doc is not None else old_doc_id
        ctl.project.history.push(ReparentCommand(
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
    def maybe_grid_drop(self, event, drag: dict) -> bool:
        """Explicit-cell grid drop. Cursor cell becomes the child's
        own ``grid_row`` / ``grid_column`` — no sibling shift. Cross-
        parent drops hand off to ``maybe_reparent_dragged`` after
        pre-setting the new cell on the node so the post-reparent
        ``.grid()`` call lands in the target cell.
        """
        ctl = self.controller
        ws = ctl.workspace
        nid = drag["nid"]
        node = ctl.project.get_widget(nid)
        if node is None:
            return False
        ctl.canvas.update_idletasks()
        cx, cy = ws._screen_to_canvas(event.x_root, event.y_root)
        target = ws._find_container_at(cx, cy, exclude_id=nid)
        if target is None:
            return False
        # Layout Frame being dropped onto a grid Frame — block the
        # grid cell-snap path so ``maybe_reparent_dragged`` gets a
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
        cursor_row, cursor_col = ctl._grid_indicator.cell_at(
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
                    ctl.project.update_property(target.id, key, val)
            ctl.project.update_property(nid, "grid_row", resolved_row)
            ctl.project.update_property(nid, "grid_column", resolved_col)
            ctl.project.history.push(
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
                ctl.project.update_property(target.id, key, val)
            drag["parent_dim_changes"] = (
                target.id,
                {
                    k: (parent_before[k], dim_updates[k])
                    for k in dim_updates
                },
            )
        self.maybe_reparent_dragged(event, drag)
        return True
