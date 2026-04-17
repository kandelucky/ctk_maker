"""Widget lifecycle controller — turns model events into canvas
actions.

Every ``widget_added`` / ``widget_removed`` / ``widget_reparented``
/ ``widget_z_changed`` / ``widget_visibility_changed`` /
``widget_locked_changed`` event on the project bus lands here.
The controller owns the creation side of the pipeline (descriptor
→ real tk widget → canvas placement with the right geometry
manager) plus the destruction + reparent replay that tkinter
forces on us (a widget can't change its master after creation).

Split out of the old monolithic ``core.py`` so widget-lifecycle
logic lives in one focused module. ``Workspace`` holds a single
instance on ``self.lifecycle`` and re-exposes a couple of methods
for the property-change path that still wants to recreate a
subtree in place.
"""

from __future__ import annotations

import tkinter as tk

from app.ui.workspace.layout_overlay import (
    _child_manager_kwargs,
    _grid_child_place_kwargs,
    _strip_layout_keys,
)
from app.widgets.layout_schema import (
    next_free_grid_cell,
    normalise_layout_type,
)
from app.widgets.registry import get_descriptor


class WidgetLifecycle:
    """Per-workspace widget add / remove / reparent / z-order /
    visibility handler. All external state (project, canvas, zoom,
    selection, layout overlay, widget_views) is read through the
    workspace ref; the controller holds no state of its own.
    """

    def __init__(self, workspace) -> None:
        self.workspace = workspace

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------
    @property
    def canvas(self) -> tk.Canvas:
        return self.workspace.canvas

    @property
    def project(self):
        return self.workspace.project

    @property
    def zoom(self):
        return self.workspace.zoom

    @property
    def selection(self):
        return self.workspace.selection

    @property
    def layout_overlay(self):
        return self.workspace.layout_overlay

    @property
    def widget_views(self) -> dict:
        return self.workspace.widget_views

    @property
    def anchor_views(self) -> dict:
        return self.workspace._anchor_views

    # ------------------------------------------------------------------
    # Event bus subscriptions
    # ------------------------------------------------------------------
    def subscribe(self, bus) -> None:
        bus.subscribe("widget_added", self.on_widget_added)
        bus.subscribe("widget_removed", self.on_widget_removed)
        bus.subscribe("widget_reparented", self.on_widget_reparented)
        bus.subscribe("widget_z_changed", self.on_widget_z_changed)
        bus.subscribe(
            "widget_visibility_changed", self.on_widget_visibility_changed,
        )
        bus.subscribe(
            "widget_locked_changed", self.on_widget_locked_changed,
        )

    # ------------------------------------------------------------------
    # Widget creation
    # ------------------------------------------------------------------
    def _auto_assign_grid_cell(self, parent_node, node) -> None:
        """If the new child would land in a grid parent at a cell
        already taken by a sibling, bump it to the next free cell
        via row-major scan. Respects an explicit non-default cell
        the caller already set (e.g. palette drop under the cursor).
        """
        if parent_node is None:
            return
        if normalise_layout_type(
            parent_node.properties.get("layout_type", "place"),
        ) != "grid":
            return
        props = node.properties
        try:
            row = int(props.get("grid_row", 0) or 0)
            col = int(props.get("grid_column", 0) or 0)
        except (TypeError, ValueError):
            return
        # Only auto-assign when the child is sitting at the default
        # (0, 0) — explicit cursor-based drops already picked their
        # cell, paste/load keeps saved positions.
        if row != 0 or col != 0:
            return
        occupied_at_00 = any(
            sibling is not node
            and int(sibling.properties.get("grid_row", 0) or 0) == 0
            and int(sibling.properties.get("grid_column", 0) or 0) == 0
            for sibling in parent_node.children
        )
        if not occupied_at_00:
            return
        free_row, free_col = next_free_grid_cell(
            [s for s in parent_node.children if s is not node],
            parent_node.properties,
        )
        props["grid_row"] = free_row
        props["grid_column"] = free_col

    def on_widget_added(self, node) -> None:
        ws = self.workspace
        descriptor = get_descriptor(node.widget_type)
        if descriptor is None:
            return
        parent_node = node.parent
        if parent_node is None:
            master = self.canvas
        else:
            parent_entry = self.widget_views.get(parent_node.id)
            if parent_entry is None:
                master = self.canvas
            else:
                master, _ = parent_entry
            self._auto_assign_grid_cell(parent_node, node)
        init_kwargs = ws._get_radio_init_kwargs(node)
        widget = descriptor.create_widget(
            master, _strip_layout_keys(node.properties),
            init_kwargs=init_kwargs,
        )
        ws._sync_radio_initial(widget, node)
        anchor_widget = descriptor.canvas_anchor(widget)
        if anchor_widget is not widget:
            self.anchor_views[node.id] = anchor_widget
        # Containers must keep their configured size in the designer —
        # tk's default ``propagate(True)`` would shrink a Frame to fit
        # its children the moment a vbox/hbox child is packed into it,
        # hiding the Frame's outline and breaking drop-into UX. Disable
        # on every container; ``place`` children don't trigger it
        # anyway so non-pack modes are unaffected.
        if getattr(descriptor, "is_container", False):
            for forget_target in {widget, anchor_widget}:
                try:
                    forget_target.pack_propagate(False)
                except tk.TclError:
                    pass
                try:
                    forget_target.grid_propagate(False)
                except tk.TclError:
                    pass

        lx = int(node.properties.get("x", 0))
        ly = int(node.properties.get("y", 0))
        lw = int(node.properties.get("width", 0) or 0)
        lh = int(node.properties.get("height", 0) or 0)
        is_composite = anchor_widget is not widget
        owning_doc = self.project.find_document_for_widget(node.id)
        if parent_node is None:
            # Top-level widgets sit inside a specific document; the
            # document's canvas_x/y offset feeds into logical_to_canvas
            # so a second document at canvas_x=900 lands its widgets
            # at (pad + 900*zoom + x*zoom).
            cx, cy = self.zoom.logical_to_canvas(
                lx, ly, document=owning_doc,
            )
            kwargs = {"anchor": "nw", "window": anchor_widget}
            # Composite widgets (CTkScrollableFrame) don't propagate
            # their requested size to the canvas; pin the canvas item
            # size explicitly so the outer container doesn't grow.
            if is_composite and lw > 0 and lh > 0:
                kwargs["width"] = max(1, int(lw * self.zoom.value))
                kwargs["height"] = max(1, int(lh * self.zoom.value))
            window_id = self.canvas.create_window(cx, cy, **kwargs)
        else:
            # Nested: the geometry manager depends on parent's
            # ``layout_type``. ``place`` keeps absolute x/y;
            # ``vbox`` / ``hbox`` / ``grid`` switch to real
            # ``.pack()`` / ``.grid()`` so the canvas preview matches
            # the exported runtime.
            manager, mgr_kwargs = _child_manager_kwargs(
                parent_node, node.properties, zoom=self.zoom.value,
            )
            if manager == "pack":
                if is_composite and lw > 0 and lh > 0:
                    # Composite widgets don't auto-size — reserve the
                    # configured dimensions so pack has something to
                    # work with.
                    anchor_widget.configure(
                        width=max(1, int(lw * self.zoom.value)),
                        height=max(1, int(lh * self.zoom.value)),
                    )
                anchor_widget.pack(**mgr_kwargs)
            elif manager == "grid":
                # Placement deferred until after apply_to_widget — see
                # the re-apply block below. apply_to_widget's
                # place_configure skips widgets not currently managed
                # by place, so leaving the widget unplaced here avoids
                # the 0,0 override.
                pass
            else:
                place_kwargs: dict = {
                    "x": int(lx * self.zoom.value),
                    "y": int(ly * self.zoom.value),
                }
                if is_composite and lw > 0 and lh > 0:
                    place_kwargs["width"] = max(1, int(lw * self.zoom.value))
                    place_kwargs["height"] = max(1, int(lh * self.zoom.value))
                anchor_widget.place(**place_kwargs)
            window_id = None
        # Pass the owning document so apply_to_widget lands the
        # canvas coords against the *correct* form's offset — not the
        # currently-active one, which for a cross-doc drag is still
        # the source document.
        self.zoom.apply_to_widget(
            widget, window_id, node.properties, document=owning_doc,
        )
        # Grid children: place AFTER apply_to_widget using the same
        # path as drag-reassigns, so fresh drops and manual moves go
        # through identical code.
        if parent_node is not None and normalise_layout_type(
            parent_node.properties.get("layout_type", "place"),
        ) == "grid":
            self.layout_overlay.apply_child_manager(
                anchor_widget, parent_node, node,
            )
        self.widget_views[node.id] = (widget, window_id)
        ws._bind_widget_events(anchor_widget, node.id)
        if not node.visible:
            self._set_widget_visibility(widget, window_id, node, False)

    def create_widget_subtree(self, node) -> None:
        self.on_widget_added(node)
        for child in node.children:
            self.create_widget_subtree(child)

    # ------------------------------------------------------------------
    # Widget destruction
    # ------------------------------------------------------------------
    def destroy_widget_subtree(self, node) -> None:
        for child in list(node.children):
            self.destroy_widget_subtree(child)
        entry = self.widget_views.pop(node.id, None)
        if entry is None:
            return
        widget, window_id = entry
        if window_id is not None:
            try:
                self.canvas.delete(window_id)
            except tk.TclError:
                pass
        try:
            widget.destroy()
        except tk.TclError:
            pass

    def on_widget_removed(
        self, widget_id: str, parent_id: str | None = None,
    ) -> None:
        _ = parent_id  # reserved for future per-parent hooks
        if widget_id not in self.widget_views:
            return
        widget, window_id = self.widget_views.pop(widget_id)
        self.workspace._unbind_radio_group(widget_id)
        anchor = self.anchor_views.pop(widget_id, None)
        if window_id is not None:
            try:
                self.canvas.delete(window_id)
            except tk.TclError:
                pass
        try:
            (anchor or widget).destroy()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Reparent + z-order
    # ------------------------------------------------------------------
    def on_widget_reparented(
        self, widget_id: str,
        _old_parent_id: str | None, _new_parent_id: str | None,
    ) -> None:
        """When a widget's parent changes, destroy its widget view
        subtree and recreate it under the new parent.

        Tkinter doesn't let a widget change its master after creation,
        so reparenting means destroying the CTk/tk widget(s) and
        rebuilding them inside the new master. A selected widget's
        Properties panel needs to refresh too — the Layout rows it
        shows depend on the parent's ``layout_type``, which just
        changed — so we re-publish ``selection_changed`` to force a
        panel rebuild.
        """
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        was_selected = self.project.selected_id == widget_id
        if was_selected:
            self.selection.clear()
        self.destroy_widget_subtree(node)
        self.create_widget_subtree(node)
        if was_selected:
            self.project.event_bus.publish(
                "selection_changed", widget_id,
            )
            self.workspace.after(20, self.selection.draw)

    def on_widget_z_changed(
        self, widget_id: str, direction: str,
    ) -> None:
        """Restack the reordered widget's siblings in project order.

        Using `widget.lower()` directly on a nested child would push it
        behind CTkFrame's internal drawing canvas and hide it forever.
        Instead we re-`lift()` every sibling from bottom to top so the
        stacking order matches `parent.children`, leaving CTk internals
        below everything we control.

        For vbox / hbox / grid parents, z-order alone doesn't move the
        children — pack/grid ordering is decided at ``.pack()`` time.
        So we also rearrange the parent's children so the new model
        sequence drives the new visual sequence.
        """
        _ = direction  # reserved for future per-direction hooks
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        siblings = (
            node.parent.children if node.parent is not None
            else self.project.root_widgets
        )
        for sibling in siblings:
            entry = self.widget_views.get(sibling.id)
            if entry is None:
                continue
            try:
                entry[0].lift()
            except tk.TclError:
                pass
        if node.parent is not None:
            parent_layout = normalise_layout_type(
                node.parent.properties.get("layout_type", "place"),
            )
            if parent_layout != "place":
                self.layout_overlay.rearrange_container_children(
                    node.parent.id,
                )
        if widget_id == self.project.selected_id:
            self.workspace._schedule_selection_redraw()

    # ------------------------------------------------------------------
    # Visibility + lock
    # ------------------------------------------------------------------
    def on_widget_locked_changed(
        self, _widget_id: str, _locked: bool,
    ) -> None:
        # Locked state affects whether selection handles render;
        # redraw if this or an ancestor change touched the selection.
        if self.project.selected_id is not None:
            self.selection.draw()

    def on_widget_visibility_changed(
        self, widget_id: str, visible: bool,
    ) -> None:
        entry = self.widget_views.get(widget_id)
        if entry is None:
            return
        widget, window_id = entry
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        self._set_widget_visibility(widget, window_id, node, visible)
        if widget_id == self.project.selected_id:
            if visible:
                self.workspace._schedule_selection_redraw()
            else:
                self.selection.clear()

    def _set_widget_visibility(
        self, widget, window_id, node, visible: bool,
    ) -> None:
        """Show or hide a widget in the workspace without destroying
        it. Canvas children toggle via `canvas.itemconfigure(state=…)`,
        nested children toggle via fresh `place()` / `place_forget()`
        (can't use `place_configure` after a forget — no place info
        to edit). The model is unchanged — pure rendering control."""
        if window_id is not None:
            try:
                self.canvas.itemconfigure(
                    window_id, state="normal" if visible else "hidden",
                )
            except tk.TclError:
                pass
            return
        if visible:
            try:
                lx = int(node.properties.get("x", 0))
                ly = int(node.properties.get("y", 0))
                widget.place(
                    x=int(lx * self.zoom.value),
                    y=int(ly * self.zoom.value),
                )
                lw = int(node.properties.get("width", 0))
                lh = int(node.properties.get("height", 0))
                if lw > 0 and lh > 0:
                    widget.configure(
                        width=max(1, int(lw * self.zoom.value)),
                        height=max(1, int(lh * self.zoom.value)),
                    )
            except (TypeError, ValueError, tk.TclError):
                pass
        else:
            try:
                widget.place_forget()
            except tk.TclError:
                pass
