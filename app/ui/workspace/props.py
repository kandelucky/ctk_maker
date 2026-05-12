"""Property-change router sidecar for ``Workspace``.

Owns the entire ``property_changed`` dispatch pipeline plus the
related variable / binding lifecycle subscribers:

* ``on_property_changed`` reads as a flat router — Window props,
  container layout, child layout, coords, var-binding transitions,
  recreate triggers, derived props, generic configure — each path
  short-circuits the rest when it fires.
* ``_seed_binding_cache_on_add`` / ``_drop_binding_cache_on_remove``
  keep the ``widget_id → {prop_name: var_id}`` cache in sync with
  the project's add / remove events.
* ``on_variable_default_changed`` / ``on_variable_type_changed``
  fan out across the binding cache — cosmetic bindings only need a
  configure pass, but a type swap (or any wired binding pointed at
  a recycled ``tk.Variable``) needs a full subtree recreate so the
  descriptor's ``init_kwargs`` plumbing rewires the new variable.

Radio-button group coordination (``_get_radio_init_kwargs``,
``_sync_radio_initial``, ``_unbind_radio_group``) lives here too —
the shared ``StringVar`` per ``group`` name is owned by the
workspace's ``_radio_groups`` dict, which the router reads /
writes when widgets enter and leave the canvas.
"""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.layout_schema import normalise_layout_type, resolve_grid_drop_cell
from app.widgets.registry import get_descriptor
from app.ui.workspace.layout_overlay import _strip_layout_keys


_CONTAINER_LAYOUT_PROPS = frozenset({
    "layout_type", "layout_spacing", "grid_rows", "grid_cols",
})
_CHILD_LAYOUT_PROPS = frozenset({
    "grid_sticky", "grid_row", "grid_column", "stretch",
})


class PropertyRouter:
    """Routes ``property_changed`` events to the right handler.
    See module docstring.
    """

    def __init__(self, workspace) -> None:
        self.workspace = workspace

    # ------------------------------------------------------------------
    # Radio-button group coordination
    # ------------------------------------------------------------------
    def get_radio_init_kwargs(self, node) -> dict | None:
        """Compute the `variable` + `value` constructor kwargs for a
        CTkRadioButton node that belongs to a named group. Returns
        None for standalone radios (empty group).
        """
        ws = self.workspace
        group = str(node.properties.get("group") or "").strip()
        if not group:
            return None
        var = ws._radio_groups.setdefault(
            group, tk.StringVar(master=ws, value=""),
        )
        if node.id not in ws._radio_values:
            next_val = ws._radio_group_counts.get(group, 0) + 1
            ws._radio_group_counts[group] = next_val
            ws._radio_values[node.id] = f"r{next_val}"
        value = ws._radio_values[node.id]
        return {"variable": var, "value": value}

    def sync_radio_initial(self, widget, node) -> None:
        """Push the radio's `initially_checked` bool onto the shared
        group variable. Standalone radios fall through to the
        descriptor's `apply_state` select/deselect path.
        """
        ws = self.workspace
        if not isinstance(widget, ctk.CTkRadioButton):
            return
        group = str(node.properties.get("group") or "").strip()
        if not group or group not in ws._radio_groups:
            return
        var = ws._radio_groups[group]
        value = ws._radio_values.get(node.id)
        if value is None:
            return
        try:
            if node.properties.get("initially_checked"):
                var.set(value)
            elif var.get() == value:
                var.set("")
        except Exception:
            log_error("workspace._sync_radio_initial")

    def unbind_radio_group(self, widget_id: str) -> None:
        self.workspace._radio_values.pop(widget_id, None)

    def sync_composite_size(self, widget_id: str, node) -> None:
        """Push width/height onto the outer anchor container for
        composite widgets. Top-level uses `canvas.itemconfigure` on
        the window item (physical pixel coords → ``canvas_scale``);
        nested uses `place_configure` (CTk-scaled → ``zoom.value``).
        """
        ws = self.workspace
        anchor = ws._anchor_views.get(widget_id)
        if anchor is None:
            return
        _widget, window_id = ws.widget_views[widget_id]
        try:
            lw = int(node.properties.get("width", 0) or 0)
            lh = int(node.properties.get("height", 0) or 0)
        except (TypeError, ValueError):
            return
        if lw <= 0 or lh <= 0:
            return
        try:
            if window_id is not None:
                # Canvas items live in physical pixels; match the
                # initial placement in ``_place_top_level`` so a
                # post-creation property change doesn't shrink the
                # outer frame back to ``lw * zoom.value`` while
                # CTk's own scaled widget still wants ``lw * DPI``.
                cw = max(1, int(lw * ws.zoom.canvas_scale))
                ch = max(1, int(lh * ws.zoom.canvas_scale))
                ws.canvas.itemconfigure(window_id, width=cw, height=ch)
            elif anchor.winfo_manager() == "place":
                zw = max(1, int(lw * ws.zoom.value))
                zh = max(1, int(lh * ws.zoom.value))
                anchor.place_configure(width=zw, height=zh)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # property_changed dispatch
    # ------------------------------------------------------------------
    def on_property_changed(
        self, widget_id: str, prop_name: str, value,
    ) -> None:
        from app.core.project import WINDOW_ID
        ws = self.workspace
        if widget_id == WINDOW_ID:
            self._handle_window_property(prop_name)
            return
        if prop_name in _CONTAINER_LAYOUT_PROPS:
            self._handle_container_layout_prop(widget_id, prop_name)
            return
        if prop_name in _CHILD_LAYOUT_PROPS:
            self._handle_child_layout_prop(widget_id)
            return
        if widget_id not in ws.widget_views:
            return
        widget, window_id = ws.widget_views[widget_id]
        node = ws.project.get_widget(widget_id)
        if prop_name in ("x", "y") and node is not None:
            self._handle_coord_prop(widget_id, widget, window_id, node)
            return
        descriptor = get_descriptor(node.widget_type) if node else None
        if self._handle_var_binding_change(
            widget_id, prop_name, value, node, descriptor,
        ):
            return
        if self._handle_recreate_prop(
            widget_id, prop_name, node, descriptor,
        ):
            return
        self._apply_derived_props(widget_id, prop_name, node, descriptor)
        self._apply_generic_configure(
            widget_id, prop_name, value, node, descriptor,
            widget, window_id,
        )
        # v1.10.2 flex-shrink: width/height edits propagate to the
        # vbox/hbox rebalance loop in two directions.
        # 1. Edit on a child whose parent uses pack layout → re-budget
        #    siblings (a fixed sibling growing eats budget away from
        #    the grow ones).
        # 2. Edit on a container that *itself* uses pack layout →
        #    re-budget its children (the container's main axis
        #    changed, so each grow child's slot follows).
        if prop_name in ("width", "height") and node is not None:
            self._maybe_rebalance_after_size_edit(node)

    def _maybe_rebalance_after_size_edit(self, node) -> None:
        """Trigger ``rebalance_pack_siblings`` when a width/height
        edit lands on (a) a child of a vbox/hbox parent or (b) a
        vbox/hbox container itself. Either way the budget shifts and
        grow siblings need fresh slot math.
        """
        ws = self.workspace
        parent_node = getattr(node, "parent", None)
        if parent_node is not None:
            parent_layout = normalise_layout_type(
                parent_node.properties.get("layout_type", "place"),
            )
            if parent_layout in ("vbox", "hbox"):
                ws.layout_overlay.rebalance_pack_siblings(
                    parent_node, parent_layout,
                )
        own_layout = normalise_layout_type(
            node.properties.get("layout_type", "place"),
        )
        if own_layout in ("vbox", "hbox") and node.children:
            ws.layout_overlay.rebalance_pack_siblings(node, own_layout)

    def _handle_window_property(self, prop_name: str) -> None:
        """Window (virtual) node props don't touch a real CTk widget —
        the canvas rectangle + chrome + grid visualise the form. Most
        keys trigger a redraw; ``accent_color`` only touches chrome.
        """
        ws = self.workspace
        if prop_name in (
            "fg_color", "grid_style", "grid_color", "grid_spacing",
            "layout_type",
        ):
            ws._redraw_document()
        elif prop_name == "accent_color":
            ws._draw_window_chrome()

    def _handle_container_layout_prop(
        self, widget_id: str, prop_name: str = "",
    ) -> None:
        """Container-level layout mutation (manager swap, spacing,
        grid dims) — re-pack / re-place every child, redraw overlays.
        Grid-type containers additionally get a stacked-children
        sweep so a ``place → grid`` swap distributes the existing
        kids across free cells instead of stacking them all at (0, 0).
        A ``layout_type`` swap also re-applies fill defaults to
        fill-friendly children so Grid → vbox / hbox picks up
        ``stretch="grow"`` (and vice versa for grid) without a per-
        child manual tweak.
        """
        ws = self.workspace
        node = ws.project.get_widget(widget_id)
        if node is not None and prop_name == "layout_type":
            ws.lifecycle.apply_fill_defaults_to_children(node)
        if node is not None and normalise_layout_type(
            node.properties.get("layout_type", "place"),
        ) == "grid":
            self._redistribute_stacked_grid_children(node)
        ws.layout_overlay.rearrange_container_children(widget_id)
        ws._redraw_document()
        if ws.project.selected_id is not None:
            ws._schedule_selection_redraw()

    def _redistribute_stacked_grid_children(self, container_node) -> None:
        """Detect grid children sharing a cell and relocate the
        extras to free cells (growing the grid if needed). Triggered
        from ``_handle_container_layout_prop`` so layout-type swaps
        (place → grid, vbox → grid, etc.) stop leaving N children
        stacked at the default (0, 0). Idempotent — when no stacks
        exist this is a single dict-scan no-op, so re-entering the
        grid layout type on an already-distributed container costs
        nothing.
        """
        ws = self.workspace
        children = list(container_node.children)
        if len(children) < 2:
            return
        # Group children by their (row, col). A cell with 2+ kids is
        # stacked and triggers redistribution.
        cells: dict[tuple[int, int], list] = {}
        for child in children:
            try:
                r = int(child.properties.get("grid_row", 0) or 0)
                c = int(child.properties.get("grid_column", 0) or 0)
            except (TypeError, ValueError):
                r, c = 0, 0
            cells.setdefault((r, c), []).append(child)
        stacked = {cell: kids for cell, kids in cells.items() if len(kids) > 1}
        if not stacked:
            return
        # Keep the first child in each stacked cell, relocate the
        # rest. Deterministic order for reproducibility.
        for cell in sorted(stacked.keys()):
            for child_to_move in stacked[cell][1:]:
                new_r, new_c, dim_updates = resolve_grid_drop_cell(
                    container_node.children,
                    container_node.properties,
                    exclude_node=child_to_move,
                )
                if dim_updates:
                    for key, val in dim_updates.items():
                        ws.project.update_property(
                            container_node.id, key, val,
                        )
                ws.project.update_property(
                    child_to_move.id, "grid_row", new_r,
                )
                ws.project.update_property(
                    child_to_move.id, "grid_column", new_c,
                )

    def _handle_child_layout_prop(self, widget_id: str) -> None:
        """Per-child layout tweak — re-apply the child's geometry
        manager in place. ``grid_*`` moves within the parent grid;
        ``stretch`` just swaps pack fill / expand kwargs.
        """
        ws = self.workspace
        ws._reapply_child_manager(widget_id)
        if widget_id == ws.project.selected_id:
            ws._schedule_selection_redraw()

    def _handle_coord_prop(
        self, widget_id: str, widget, window_id, node,
    ) -> None:
        """x / y live update — drag motion, scrub, undo / redo all
        hit this path. Canvas items use ``canvas.coords``; placed
        widgets (non-canvas-hosted) use ``place_configure``.
        """
        ws = self.workspace
        try:
            x = int(node.properties.get("x", 0))
            y = int(node.properties.get("y", 0))
            if window_id is not None:
                owning_doc = ws.project.find_document_for_widget(
                    widget_id,
                )
                cx, cy = ws.zoom.logical_to_canvas(
                    x, y, document=owning_doc,
                )
                ws.canvas.coords(window_id, cx, cy)
            elif widget.winfo_manager() == "place":
                # ``.place`` (not ``.place_configure``) routes through
                # CTk's DPI-scaling wrapper — see drag.py for the full
                # rationale. Using ``place_configure`` here would jump
                # the widget back to raw tk pixels after a drag.
                widget.place(
                    x=int(x * ws.zoom.value),
                    y=int(y * ws.zoom.value),
                )
        except Exception:
            log_error("workspace._on_property_changed x/y coords")
        if widget_id == ws.project.selected_id:
            ws._schedule_selection_redraw()

    # ------------------------------------------------------------------
    # Phase 1 binding — recreate widgets when a property toggles in / out
    # of bound state so Tkinter's ``textvariable`` / ``variable`` wiring
    # is rebuilt cleanly.
    # ------------------------------------------------------------------
    def seed_binding_cache_on_add(self, node) -> None:
        ws = self.workspace
        from app.core.variables import parse_var_token
        bound: dict[str, str] = {}
        for k, v in node.properties.items():
            var_id = parse_var_token(v)
            if var_id is not None:
                bound[k] = var_id
        if bound:
            ws._bound_props_cache[node.id] = bound
        else:
            ws._bound_props_cache.pop(node.id, None)

    def drop_binding_cache_on_remove(
        self, widget_id: str, parent_id: str | None = None,
    ) -> None:
        # ``widget_removed`` publishes ``(widget_id, parent_id)`` — the
        # earlier signature only accepted one positional and raised
        # TypeError, which propagated up and killed callers iterating
        # over multiple removals (e.g. the dialog-close ✕ would only
        # remove the first child widget per click).
        _ = parent_id
        self.workspace._bound_props_cache.pop(widget_id, None)

    def on_variable_default_changed(
        self, var_id: str, _new_default,
    ) -> None:
        """Refresh widgets bound to ``var_id`` whose binding is
        cosmetic — i.e. resolves to a literal at build time because
        the property has no ``BINDING_WIRINGS`` entry (``fg_color``,
        ``text_color``, ``border_color``, …). Tk's
        ``textvariable`` / ``variable`` already keeps wired bindings
        live, so we don't touch widgets whose only bindings are wired.
        """
        from app.core.variables import BINDING_WIRINGS
        ws = self.workspace

        affected_ids: list[str] = []
        for wid, bound in ws._bound_props_cache.items():
            cosmetic_bindings = [
                pname for pname, vid in bound.items()
                if vid == var_id
            ]
            if not cosmetic_bindings:
                continue
            node = ws.project.get_widget(wid)
            if node is None:
                continue
            has_cosmetic = any(
                (node.widget_type, pname) not in BINDING_WIRINGS
                for pname in cosmetic_bindings
            )
            if has_cosmetic:
                affected_ids.append(wid)
        for wid in affected_ids:
            node = ws.project.get_widget(wid)
            descriptor = get_descriptor(node.widget_type) if node else None
            if node is None or descriptor is None:
                continue

            def _remove_subtree(n) -> None:
                for c in list(n.children):
                    _remove_subtree(c)
                ws.lifecycle.on_widget_removed(n.id)
            _remove_subtree(node)
            ws.lifecycle.create_widget_subtree(node)
            if wid == ws.project.selected_id:
                ws._schedule_selection_redraw()

    def on_variable_type_changed(self, var_id: str, _new_type) -> None:
        """The Project drops the cached ``tk.Variable`` when a type
        changes (so a fresh instance with the new type is built on
        next ``get_tk_var``). Every widget bound to that variable
        therefore holds a stale reference and needs a full recreate
        so the descriptor's ``init_kwargs`` plumbing rewires the new
        ``tk.Variable``.
        """
        ws = self.workspace
        affected_ids = [
            wid for wid, props in ws._bound_props_cache.items()
            if var_id in props.values()
        ]
        for wid in affected_ids:
            node = ws.project.get_widget(wid)
            descriptor = get_descriptor(node.widget_type) if node else None
            if node is None or descriptor is None:
                continue

            def _remove_subtree(n) -> None:
                for c in list(n.children):
                    _remove_subtree(c)
                ws.lifecycle.on_widget_removed(n.id)
            _remove_subtree(node)
            ws.lifecycle.create_widget_subtree(node)
            if wid == ws.project.selected_id:
                ws._schedule_selection_redraw()

    def _handle_var_binding_change(
        self, widget_id: str, prop_name: str, value,
        node, descriptor,
    ) -> bool:
        """Detect transitions in bound state for a property. Triggers
        a recreate when the property toggles literal ↔ bound, OR when
        it stays bound but switches to a different variable. Returns
        True when a recreate ran — caller skips the rest of the
        property-change pipeline.
        """
        ws = self.workspace
        from app.core.variables import parse_var_token
        if descriptor is None or node is None:
            return False
        bound_dict = ws._bound_props_cache.setdefault(widget_id, {})
        new_var_id = parse_var_token(value)
        old_var_id = bound_dict.get(prop_name)
        if new_var_id == old_var_id:
            return False
        if new_var_id is None:
            bound_dict.pop(prop_name, None)
        else:
            bound_dict[prop_name] = new_var_id
        entry = ws.widget_views.get(widget_id)
        if entry is not None:
            widget_obj, _ = entry
            try:
                descriptor.before_recreate(node, widget_obj, prop_name)
            except Exception:
                log_error(f"{node.widget_type}.before_recreate")

        def _remove_subtree(n) -> None:
            for c in list(n.children):
                _remove_subtree(c)
            ws.lifecycle.on_widget_removed(n.id)
        _remove_subtree(node)
        ws.lifecycle.create_widget_subtree(node)
        if widget_id == ws.project.selected_id:
            ws._schedule_selection_redraw()
        return True

    def _handle_recreate_prop(
        self, widget_id: str, prop_name: str, node, descriptor,
    ) -> bool:
        """Init-only kwargs (e.g. ``CTkProgressBar.orientation``)
        can't be reconfigured live — destroy and rebuild the subtree.
        Returns True when the prop was a recreate trigger and the
        rebuild was done, so the caller can short-circuit.
        """
        ws = self.workspace
        recreate = (
            getattr(descriptor, "recreate_triggers", None)
            if descriptor else None
        )
        if not recreate or prop_name not in recreate:
            return False
        updates = descriptor.on_prop_recreate(prop_name, node.properties)
        for k, v in updates.items():
            if node.properties.get(k) != v:
                ws.project.update_property(widget_id, k, v)
        entry = ws.widget_views.get(widget_id)
        if entry is not None:
            widget_obj, _ = entry
            try:
                descriptor.before_recreate(node, widget_obj, prop_name)
            except Exception:
                log_error(f"{node.widget_type}.before_recreate")

        def _remove_subtree(n) -> None:
            for c in list(n.children):
                _remove_subtree(c)
            ws.lifecycle.on_widget_removed(n.id)
        _remove_subtree(node)
        ws.lifecycle.create_widget_subtree(node)
        if widget_id == ws.project.selected_id:
            ws._schedule_selection_redraw()
        return True

    def _apply_derived_props(
        self, widget_id: str, prop_name: str, node, descriptor,
    ) -> None:
        """Descriptors can declare ``derived_triggers`` — props whose
        change should fan out into computed sibling props via
        ``compute_derived`` (e.g. Image width → height when
        ``preserve_aspect`` is on). Runs BEFORE the generic configure
        path so the derived updates land in the same widget pass.
        """
        ws = self.workspace
        if descriptor is None:
            return
        triggers = getattr(descriptor, "derived_triggers", None)
        if not (triggers and prop_name in triggers
                and hasattr(descriptor, "compute_derived")):
            return
        try:
            derived = descriptor.compute_derived(node.properties)
        except Exception:
            log_error(f"{node.widget_type}.compute_derived")
            derived = {}
        for k, v in derived.items():
            if node.properties.get(k) != v:
                ws.project.update_property(widget_id, k, v)

    def _apply_generic_configure(
        self, widget_id: str, prop_name: str, value,
        node, descriptor, widget, window_id,
    ) -> None:
        """Fallback path for every prop that isn't special-cased above:
        run the descriptor's ``transform_properties`` + ``apply_state``,
        refresh zoom placement, resize composite wrappers, and re-lift
        CTkButton's text label (which can slip behind its background
        when corner_radius approaches half the widget height).
        """
        ws = self.workspace
        from app.core.variables import resolve_bindings
        try:
            if descriptor is not None:
                clean_props = _strip_layout_keys(node.properties)
                # Substitute live values for ``var:<uuid>`` tokens —
                # otherwise CTk.configure raises on the raw token and
                # silently drops every other kwarg in the same call
                # (e.g. editing text_color won't apply when fg_color
                # is bound to a variable).
                clean_props, _ = resolve_bindings(
                    ws.project, node.widget_type, clean_props,
                )
                transformed = descriptor.transform_properties(clean_props)
                if transformed:
                    widget.configure(**transformed)
                descriptor.apply_state(widget, node.properties)
                self.sync_radio_initial(widget, node)
                owning_doc = ws.project.find_document_for_widget(
                    widget_id,
                )
                ws.zoom.apply_to_widget(
                    widget, window_id, node.properties,
                    document=owning_doc,
                )
                if widget_id in ws._anchor_views:
                    self.sync_composite_size(widget_id, node)
            else:
                widget.configure(**{prop_name: value})
        except Exception:
            log_error(
                f"workspace._on_property_changed widget.configure {prop_name}",
            )
        # Re-walk bindings — composites like CTkSegmentedButton tear
        # down inner children inside ``configure(values=…)`` (and
        # transform_properties always passes the full kwarg set, so
        # this fires on every property edit, not just values). The
        # idempotent ``_bind_widget_events`` skips already-bound
        # widgets and only attaches handlers to brand-new children.
        ws._bind_widget_events(widget, widget_id)
        text_label = getattr(widget, "_text_label", None)
        if text_label is not None:
            try:
                text_label.lift()
            except tk.TclError:
                pass
        if prop_name in ("width", "height") and node is not None:
            lt = normalise_layout_type(
                node.properties.get("layout_type", "place"),
            )
            if lt == "grid" and getattr(descriptor, "is_container", False):
                ws.layout_overlay.rearrange_container_children(widget_id)
        # Managed-layout children (vbox / hbox / grid) are place-managed
        # via the grid-as-place hack, but their x/y properties are 0 —
        # zoom.apply_to_widget's place_configure(x=0,y=0) just pulled
        # them to the container's top-left corner. Put them back by
        # re-running the parent's child-manager, which recomputes the
        # correct cell / pack coordinates.
        if node is not None and node.parent is not None:
            parent_lt = normalise_layout_type(
                node.parent.properties.get("layout_type", "place"),
            )
            if parent_lt != "place":
                ws._reapply_child_manager(widget_id)
        if widget_id == ws.project.selected_id:
            ws._schedule_selection_redraw()
