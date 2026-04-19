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
    _composite_configure,
    _composite_place_size,
    _grid_child_place_kwargs,
    _strip_layout_keys,
)
from app.widgets.layout_schema import (
    normalise_layout_type,
    resolve_grid_drop_cell,
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
        """Route every new child's grid placement through
        ``resolve_grid_drop_cell`` — the single source of truth for
        "pick a free cell, grow the grid if full" semantics. If the
        caller set an explicit ``grid_row`` / ``grid_column`` (e.g.
        palette drop under the cursor, paste with saved cell), that
        preferred cell is honoured unless another sibling already
        claims it; collisions bump the child to the next free cell
        or grow the grid by one row / column when every cell is
        taken.
        """
        if parent_node is None:
            return
        if normalise_layout_type(
            parent_node.properties.get("layout_type", "place"),
        ) != "grid":
            return
        props = node.properties
        try:
            preferred_row = int(props.get("grid_row", 0) or 0)
            preferred_col = int(props.get("grid_column", 0) or 0)
        except (TypeError, ValueError):
            preferred_row = preferred_col = 0
        row, col, dim_updates = resolve_grid_drop_cell(
            [s for s in parent_node.children if s is not node],
            parent_node.properties,
            preferred_row=preferred_row,
            preferred_col=preferred_col,
            exclude_node=node,
        )
        props["grid_row"] = row
        props["grid_column"] = col
        if dim_updates:
            # Grid grew — push the new dimensions through the bus so
            # the Inspector readout + rearrange_container_children
            # both pick them up. Capture before-values and stash on
            # the node so the outer caller (palette / drop path) can
            # bundle them into the AddWidgetCommand — otherwise undo
            # removes the widget but leaves the parent expanded.
            parent_before = {
                k: parent_node.properties.get(k) for k in dim_updates
            }
            for key, val in dim_updates.items():
                self.project.update_property(parent_node.id, key, val)
            node._pending_parent_dim_changes = (
                parent_node.id,
                {
                    k: (parent_before[k], dim_updates[k])
                    for k in dim_updates
                },
            )

    def apply_fill_defaults_to_children(self, container_node) -> None:
        """Re-apply fill defaults to every child of ``container_node``.
        Called from the layout_type swap path so fill-friendly widgets
        inherit the new manager's default (``stretch="grow"`` for
        vbox / hbox, ``grid_sticky="nsew"`` for grid) without the user
        editing each child individually. Direct dict assignment — no
        history push — so the layout swap itself remains a single
        undo entry; the property readout will re-surface on next
        Inspector rebuild.
        """
        for child in container_node.children:
            descriptor = get_descriptor(child.widget_type)
            if descriptor is None:
                continue
            self._apply_fill_default(descriptor, container_node, child)

    def _apply_fill_default(self, descriptor, parent_node, node) -> None:
        """Fresh drops of fill-friendly widgets (Button / Label / Entry
        / Frame / …) into a layout container commit ``stretch="fill"``
        (vbox / hbox) or ``grid_sticky="nsew"`` (grid) instead of the
        schema default so form-shaped UIs land edge-to-edge without a
        manual Inspector tweak. Only applies when the node hasn't
        already carried the layout key in from its snapshot — paste /
        duplicate / undo-redo preserve the source's intent. Widgets
        with natural sizing (CheckBox, Switch, OptionMenu) leave
        ``prefers_fill_in_layout`` at False and are unaffected.
        """
        if not getattr(descriptor, "prefers_fill_in_layout", False):
            return
        parent_layout = normalise_layout_type(
            parent_node.properties.get("layout_type", "place"),
        )
        if parent_layout in ("vbox", "hbox"):
            if "stretch" not in node.properties:
                node.properties["stretch"] = "grow"
        elif parent_layout == "grid":
            if "grid_sticky" not in node.properties:
                node.properties["grid_sticky"] = "nsew"

    def on_widget_added(self, node) -> None:
        ws = self.workspace
        descriptor = get_descriptor(node.widget_type)
        if descriptor is None:
            return
        parent_node = node.parent
        master = self._resolve_master(parent_node)
        if parent_node is not None:
            self._apply_fill_default(descriptor, parent_node, node)
            self._auto_assign_grid_cell(parent_node, node)
        widget, anchor_widget = self._instantiate_widget(
            descriptor, node, master,
        )
        self._disable_container_propagate(
            widget, anchor_widget, descriptor,
        )
        try:
            lx = int(node.properties.get("x", 0))
            ly = int(node.properties.get("y", 0))
        except (TypeError, ValueError):
            lx = ly = 0
        try:
            lw = int(node.properties.get("width", 0) or 0)
            lh = int(node.properties.get("height", 0) or 0)
        except (TypeError, ValueError):
            lw = lh = 0
        is_composite = anchor_widget is not widget
        owning_doc = self.project.find_document_for_widget(node.id)
        if parent_node is None:
            window_id = self._place_top_level(
                anchor_widget, owning_doc, lx, ly, lw, lh, is_composite,
            )
        else:
            self._place_nested(
                anchor_widget, parent_node, node,
                lx, ly, lw, lh, is_composite,
            )
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

    # ------------------------------------------------------------------
    # on_widget_added helpers
    # ------------------------------------------------------------------
    def _resolve_master(self, parent_node) -> tk.Widget:
        """Return the tk master for a new widget under ``parent_node``.
        Top-level widgets live directly on the canvas; nested widgets
        live inside their parent's tk widget. Falls back to the canvas
        when a parent exists in the model but its view hasn't been
        created yet (e.g. mid-reparent).
        """
        if parent_node is None:
            return self.canvas
        parent_entry = self.widget_views.get(parent_node.id)
        if parent_entry is None:
            return self.canvas
        master, _ = parent_entry
        return master

    def _instantiate_widget(
        self, descriptor, node, master,
    ) -> tuple:
        """Build the tk / CTk widget via ``descriptor`` and return
        ``(widget, anchor_widget)``. The anchor differs from the widget
        for composite descriptors (CTkScrollableFrame's inner canvas,
        CTkTabview's button bar parent, etc.) where events + canvas
        placement target the outer container, not the inner widget.
        """
        ws = self.workspace
        init_kwargs = ws._get_radio_init_kwargs(node)
        widget = descriptor.create_widget(
            master, _strip_layout_keys(node.properties),
            init_kwargs=init_kwargs,
        )
        ws._sync_radio_initial(widget, node)
        anchor_widget = descriptor.canvas_anchor(widget)
        if anchor_widget is not widget:
            self.anchor_views[node.id] = anchor_widget
        return widget, anchor_widget

    def _disable_container_propagate(
        self, widget, anchor_widget, descriptor,
    ) -> None:
        """Pin container size — tk's default ``propagate(True)`` would
        shrink a Frame to fit its children the moment a vbox/hbox
        child is packed into it, hiding the Frame's outline and
        breaking drop-into UX. Disabled on every container; ``place``
        children don't trigger propagate anyway so non-pack modes
        are unaffected.
        """
        if not getattr(descriptor, "is_container", False):
            return
        for forget_target in {widget, anchor_widget}:
            # CTkScrollableFrame overrides pack_propagate /
            # grid_propagate to take no argument (the inner canvas
            # it wraps can't honour "don't shrink to content"), so
            # the call raises TypeError instead of tk.TclError.
            # Catch both so a composite container doesn't crash the
            # whole on_widget_added pipeline on load.
            try:
                forget_target.pack_propagate(False)
            except (tk.TclError, TypeError):
                pass
            try:
                forget_target.grid_propagate(False)
            except (tk.TclError, TypeError):
                pass

    def _place_top_level(
        self, anchor_widget, owning_doc,
        lx: int, ly: int, lw: int, lh: int, is_composite: bool,
    ) -> int:
        """Canvas.create_window for a top-level widget. The owning
        doc's ``canvas_x`` / ``canvas_y`` offset feeds into
        ``logical_to_canvas`` so a second document at ``canvas_x=900``
        lands its widgets at ``(pad + 900*zoom + x*zoom)`` — not the
        active form's offset.
        """
        cx, cy = self.zoom.logical_to_canvas(
            lx, ly, document=owning_doc,
        )
        kwargs = {"anchor": "nw", "window": anchor_widget}
        # Composite widgets (CTkScrollableFrame) don't propagate their
        # requested size to the canvas; pin the canvas item size
        # explicitly so the outer container doesn't grow.
        if is_composite:
            kwargs.update(
                _composite_place_size(lw, lh, self.zoom.value),
            )
        return self.canvas.create_window(cx, cy, **kwargs)

    def _place_nested(
        self, anchor_widget, parent_node, node,
        lx: int, ly: int, lw: int, lh: int, is_composite: bool,
    ) -> None:
        """Pack / place a nested child under its parent. The geometry
        manager depends on the parent's ``layout_type``: ``place``
        keeps absolute x/y, ``vbox`` / ``hbox`` switch to real
        ``.pack()`` so canvas preview matches exported runtime, and
        ``grid`` is placement-deferred — ``apply_child_manager``
        handles it post-``apply_to_widget`` so fresh drops and manual
        moves share the same code path.
        """
        manager, mgr_kwargs = _child_manager_kwargs(
            parent_node, node.properties, zoom=self.zoom.value,
        )
        if manager == "pack":
            # Composite widgets don't auto-size — reserve the
            # configured dimensions so pack has something to work with.
            if is_composite:
                _composite_configure(
                    anchor_widget, lw, lh, self.zoom.value,
                )
            anchor_widget.pack(**mgr_kwargs)
        elif manager == "grid":
            # Placement deferred — see the apply_child_manager block
            # in ``on_widget_added`` that runs after apply_to_widget.
            # Leaving the widget unplaced here avoids place_configure
            # overriding the grid placement we're about to apply.
            return
        else:
            place_kwargs: dict = {
                "x": int(lx * self.zoom.value),
                "y": int(ly * self.zoom.value),
            }
            if is_composite:
                place_kwargs.update(
                    _composite_place_size(lw, lh, self.zoom.value),
                )
            anchor_widget.place(**place_kwargs)

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
        """Show or hide a widget without destroying it. Canvas
        children toggle via ``canvas.itemconfigure(state=…)``; nested
        children use the same geometry manager their parent dictates
        (place / pack / grid). Earlier this path blindly called
        ``widget.place(x, y)`` on unhide — grid children landed at
        cell (0, 0) because their real placement key is
        ``grid_row``/``grid_column``, not ``x/y``.
        """
        if window_id is not None:
            try:
                self.canvas.itemconfigure(
                    window_id, state="normal" if visible else "hidden",
                )
            except tk.TclError:
                pass
            return
        # Nested child — operate on the anchor widget if composite.
        anchor_widget = self.anchor_views.get(node.id, widget)
        if not visible:
            # Unknown which manager is active (pack/grid/place) —
            # forget all three so every path is covered.
            for forget in ("place_forget", "pack_forget", "grid_forget"):
                try:
                    getattr(anchor_widget, forget)()
                except tk.TclError:
                    pass
            return
        # Re-establish placement under the parent's layout. Same
        # dispatch as on_widget_added so grid / pack / place all
        # flow through one codepath.
        parent_node = node.parent
        if parent_node is None:
            return
        try:
            lx = int(node.properties.get("x", 0))
            ly = int(node.properties.get("y", 0))
        except (TypeError, ValueError):
            lx = ly = 0
        try:
            lw = int(node.properties.get("width", 0) or 0)
            lh = int(node.properties.get("height", 0) or 0)
        except (TypeError, ValueError):
            lw = lh = 0
        is_composite = anchor_widget is not widget
        self._place_nested(
            anchor_widget, parent_node, node,
            lx, ly, lw, lh, is_composite,
        )
        # Grid parents defer placement to apply_child_manager — run
        # it now so the child lands in its saved grid_row / column
        # instead of the (0, 0) fallback.
        if normalise_layout_type(
            parent_node.properties.get("layout_type", "place"),
        ) == "grid":
            self.layout_overlay.apply_child_manager(
                anchor_widget, parent_node, node,
            )
