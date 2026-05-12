"""Palette + component drop sidecar for ``Workspace``.

Materialises new widgets on the canvas from three entry points:

* **Palette drop** — the user dragged a widget chip out of the
  palette and released over the canvas. ``_create_node_from_entry``
  is the shared instantiator that figures out the drop target
  (container vs top-level vs Tabview tab) and pushes the
  ``AddWidgetCommand`` history entry.
* **Component drop** — a saved ``.ctkcomp`` file dropped onto the
  canvas. Fragment components instantiate a node tree under the
  cursor; window components hand off to the context-menu sidecar's
  ``_insert_window_component`` (new Toplevel document instead of a
  child subtree).
* **Add Widget cascade** — the right-click context menu builds its
  catalogue submenu through ``_build_add_widget_menu``; each leaf
  command calls ``_create_node_from_entry`` so menu-driven adds
  produce identical history records to palette drags.

All three rely on the same nesting + grid-cell snap + asset-extract
plumbing — extracting them into one place keeps the rules
consistent across paths.
"""
from __future__ import annotations

import tkinter as tk

from app.core.commands import AddWidgetCommand, BulkAddCommand
from app.core.widget_node import WidgetNode
from app.widgets.layout_schema import is_layout_container, normalise_layout_type
from app.widgets.registry import get_descriptor


class DropDispatcher:
    """Palette / component drop + Add Widget cascade builder."""

    def __init__(self, workspace) -> None:
        self.workspace = workspace

    def on_component_drop(
        self, component_path, x_root: int, y_root: int,
    ) -> None:
        """Drop a component onto the canvas. Loads the ``.ctkcomp``
        payload, reconciles bundled variables against the target
        Window (auto-create / reuse / Rename / Skip via dialog),
        instantiates fresh ``WidgetNode`` trees with new UUIDs,
        offsets root coords so the component's bounding-box top-left
        lands at the drop point, and inserts under the container at
        the cursor (or top-level if outside any container).
        """
        ws = self.workspace
        from app.core.commands import _add_subtree_recursive
        from app.io.component_io import (
            analyze_var_conflicts, apply_var_resolutions,
            extract_component_assets, instantiate_fragment, load_payload,
        )
        from app.ui.component_var_conflict_dialog import (
            ComponentVarConflictDialog,
        )

        canvas_rx = ws.canvas.winfo_rootx()
        canvas_ry = ws.canvas.winfo_rooty()
        canvas_w = ws.canvas.winfo_width()
        canvas_h = ws.canvas.winfo_height()
        local_x = x_root - canvas_rx
        local_y = y_root - canvas_ry
        if not (0 <= local_x < canvas_w and 0 <= local_y < canvas_h):
            return
        payload = load_payload(component_path)
        if payload is None or not payload.get("nodes"):
            return
        # Window-type components don't slot into the current canvas
        # the way fragments do — they create a new Toplevel document
        # in the project. Confirmation modal makes the side-effect
        # explicit since drag/double-click look identical to fragments.
        if payload.get("type") == "window":
            ws.context_menu._insert_window_component(component_path, payload)
            return

        cx, cy = ws._screen_to_canvas(x_root, y_root)
        container_node = ws._find_container_at(cx, cy)

        if container_node is None:
            target_doc = ws._find_document_at_canvas(cx, cy)
            if target_doc is None:
                return
            ws.project.set_active_document(target_doc.id)
            lx, ly = ws.zoom.canvas_to_logical(
                cx, cy, document=target_doc,
            )
            target_x, target_y = max(0, lx), max(0, ly)
            parent_id = None
            document_id = target_doc.id
        else:
            container_widget, _ = ws.widget_views[container_node.id]
            zoom = ws.zoom.value or 1.0
            coord_ref = container_widget
            if container_node.widget_type == "CTkTabview":
                try:
                    active_tab_slot = container_widget.get() or None
                except Exception:
                    active_tab_slot = None
                if active_tab_slot:
                    try:
                        coord_ref = container_widget.tab(active_tab_slot)
                    except Exception:
                        coord_ref = container_widget
            target_x = max(0, int((x_root - coord_ref.winfo_rootx()) / zoom))
            target_y = max(0, int((y_root - coord_ref.winfo_rooty()) / zoom))
            parent_id = container_node.id
            owning_doc = ws.project.find_document_for_widget(parent_id)
            document_id = owning_doc.id if owning_doc is not None else None

        target_window = (
            ws.project.get_document(document_id) if document_id else None
        )
        # Variable bundle reconciliation. The target Window owns the
        # local namespace the bundled vars will land in; any conflict
        # gates the entire insert (Cancel = abort, no widgets / vars
        # touched). Auto bundles + resolved conflicts then materialise
        # via apply_var_resolutions, returning a uuid map that
        # instantiate_fragment uses to rewrite ``var:<uuid>`` tokens.
        uuid_map: dict | None = None
        if target_window is not None and payload.get("variables"):
            plan = analyze_var_conflicts(payload, target_window)
            if plan.conflicts:
                dialog = ComponentVarConflictDialog(
                    ws.winfo_toplevel(), plan.conflicts,
                )
                ws.wait_window(dialog)
                if not dialog.result:
                    return
            uuid_map = apply_var_resolutions(
                ws.project, target_window, plan,
            )

        # Bounding-box top-left → drop point. Root nodes get offset;
        # children's coords stay relative to their parent so the
        # internal layout survives the move.
        roots = payload["nodes"]
        bbox_x = min(int(n.get("properties", {}).get("x", 0) or 0) for n in roots)
        bbox_y = min(int(n.get("properties", {}).get("y", 0) or 0) for n in roots)
        # Asset extraction: bundle tokens get rewritten to absolute
        # paths inside ``<project>/assets/components/<slug>/``. Empty
        # bundles return an empty map; rewrite_bundle_tokens then
        # leaves the property as an empty string for the descriptor
        # to handle.
        from app.core.component_paths import component_display_stem
        extracted_assets, _component_folder = extract_component_assets(
            component_path,
            getattr(ws.project, "path", None),
            payload.get("name") or component_display_stem(component_path),
        )
        nodes = instantiate_fragment(
            payload,
            drop_offset=(target_x - bbox_x, target_y - bbox_y),
            var_uuid_map=uuid_map,
            asset_extracted_map=extracted_assets,
        )
        new_ids: list[str] = []
        for root in nodes:
            _add_subtree_recursive(
                ws.project, root, parent_id, document_id,
            )
            new_ids.append(root.id)
        if not new_ids:
            return
        if len(new_ids) == 1:
            ws.project.select_widget(new_ids[0])
        else:
            ws.project.set_multi_selection(
                set(new_ids), primary=new_ids[0],
            )
        from app.core.commands import build_bulk_add_entries
        entries = build_bulk_add_entries(ws.project, new_ids)
        if entries:
            label = payload.get("name") or "component"
            # NOTE: undo of this command removes the widgets but leaves
            # auto-created local variables behind. Rare edge; user can
            # delete them via the Variables window. Phase D will swap
            # in a proper composite InsertComponentCommand.
            ws.project.history.push(
                BulkAddCommand(entries, label=f"Insert {label}"),
            )

    def on_palette_drop(
        self, entry, descriptor, x_root: int, y_root: int,
    ) -> None:
        ws = self.workspace
        canvas_rx = ws.canvas.winfo_rootx()
        canvas_ry = ws.canvas.winfo_rooty()
        canvas_w = ws.canvas.winfo_width()
        canvas_h = ws.canvas.winfo_height()
        local_x = x_root - canvas_rx
        local_y = y_root - canvas_ry
        if not (0 <= local_x < canvas_w and 0 <= local_y < canvas_h):
            return

        cx, cy = ws._screen_to_canvas(x_root, y_root)
        container_node = ws._find_container_at(cx, cy)
        self._create_node_from_entry(
            entry, descriptor, container_node, cx, cy, x_root, y_root,
        )

    def _create_node_from_entry(
        self, entry, descriptor, container_node,
        cx: float, cy: float, x_root: int, y_root: int,
    ) -> None:
        """Materialise a palette entry as a new widget node. Shared
        by drag-drop and the canvas/widget right-click "Add Widget"
        menus so every entry path uses identical layout-nesting,
        Tabview routing, grid-cell snapping, and history rules.
        """
        ws = self.workspace
        properties = dict(descriptor.default_properties)
        for key, value in getattr(entry, "preset_overrides", ()) or ():
            properties[key] = value
        # Block layout-in-layout nesting — if the palette item is a
        # managed-layout preset (Vertical / Horizontal / Grid) and the
        # drop target is already a layout container, fall through to
        # a top-level drop instead.
        if (
            container_node is not None
            and is_layout_container(properties)
            and is_layout_container(container_node.properties)
        ):
            container_node = None
        if container_node is None:
            # Top-level drop: figure out which document the cursor
            # is over and add the widget to that doc's tree. Drops
            # that land outside every document are rejected — with
            # multi-document canvases, silently falling through to
            # the active form lands widgets on the wrong surface.
            target_doc = ws._find_document_at_canvas(cx, cy)
            if target_doc is None:
                return
            ws.project.set_active_document(target_doc.id)
            lx, ly = ws.zoom.canvas_to_logical(
                cx, cy, document=target_doc,
            )
            properties["x"] = max(0, lx)
            properties["y"] = max(0, ly)
            parent_id = None
        else:
            # Nested drop — coords relative to the container widget.
            container_widget, _ = ws.widget_views[container_node.id]
            zoom = ws.zoom.value or 1.0
            # Tabview drops land inside the currently-active tab's
            # inner frame; rel_x/rel_y are computed against that frame
            # so the place() coords match what the user sees on canvas.
            coord_ref = container_widget
            active_tab_slot: str | None = None
            if container_node.widget_type == "CTkTabview":
                try:
                    active_tab_slot = container_widget.get() or None
                except Exception:
                    active_tab_slot = None
                if active_tab_slot:
                    try:
                        coord_ref = container_widget.tab(active_tab_slot)
                    except Exception:
                        coord_ref = container_widget
            rel_x = (x_root - coord_ref.winfo_rootx()) / zoom
            rel_y = (y_root - coord_ref.winfo_rooty()) / zoom
            parent_layout = normalise_layout_type(
                container_node.properties.get("layout_type", "place"),
            )
            # Non-place containers ignore child x/y at render time, so
            # writing cursor-relative coords there would just land as
            # stale Inspector values. Clamp to 0 / 0 for vbox / hbox
            # / grid drops; ``place`` parents keep the pixel offset.
            if parent_layout == "place":
                properties["x"] = max(0, int(rel_x))
                properties["y"] = max(0, int(rel_y))
            else:
                properties["x"] = 0
                properties["y"] = 0
            parent_id = container_node.id

        # Grid target: snap to whatever cell is under the cursor so
        # the drop lands visibly where the user aimed. Sets the cell
        # BEFORE add_widget so the initial render uses it.
        if container_node is not None:
            from app.widgets.layout_schema import resolve_grid_drop_cell  # noqa: F401
            if normalise_layout_type(
                container_node.properties.get("layout_type", "place"),
            ) == "grid":
                row, col = ws.drag_controller._grid_indicator.cell_at(
                    container_node, cx, cy,
                )
                properties["grid_row"] = row
                properties["grid_column"] = col
        node = WidgetNode(
            widget_type=descriptor.type_name,
            properties=properties,
        )
        if (
            container_node is not None
            and container_node.widget_type == "CTkTabview"
        ):
            node.parent_slot = active_tab_slot
        ws.project.add_widget(
            node, parent_id=parent_id,
            name_base=getattr(entry, "default_name", None),
        )
        ws.project.select_widget(node.id)
        owning_doc = ws.project.find_document_for_widget(node.id)
        document_id = owning_doc.id if owning_doc is not None else None
        dim_changes = getattr(node, "_pending_parent_dim_changes", None)
        if hasattr(node, "_pending_parent_dim_changes"):
            try:
                delattr(node, "_pending_parent_dim_changes")
            except AttributeError:
                pass
        ws.project.history.push(
            AddWidgetCommand(
                node.to_dict(), parent_id, document_id=document_id,
                parent_dim_changes=dim_changes,
            ),
        )

    def _build_add_widget_menu(
        self, parent_menu: tk.Menu, container_node,
        cx: float, cy: float, x_root: int, y_root: int,
    ) -> tk.Menu:
        """Build the "Add Widget" / "Add Widget as Child" cascade —
        same catalog structure as the menubar Widget menu. When
        ``container_node`` is itself a managed-layout container,
        Layouts entries that would nest layout-in-layout are disabled.
        """
        from app.ui.palette import CATALOG
        parent_is_layout = (
            container_node is not None
            and is_layout_container(container_node.properties)
        )
        submenu = tk.Menu(parent_menu, tearoff=0)
        for group in CATALOG:
            group_menu = tk.Menu(submenu, tearoff=0)
            for entry in group.items:
                descriptor = get_descriptor(entry.type_name)
                if descriptor is None:
                    continue
                entry_props = dict(descriptor.default_properties)
                for k, v in entry.preset_overrides:
                    entry_props[k] = v
                disabled = (
                    parent_is_layout and is_layout_container(entry_props)
                )
                group_menu.add_command(
                    label=entry.display_name,
                    command=(
                        lambda e=entry, d=descriptor:
                        self._create_node_from_entry(
                            e, d, container_node, cx, cy, x_root, y_root,
                        )
                    ),
                    state="disabled" if disabled else "normal",
                )
            submenu.add_cascade(label=group.title, menu=group_menu)
        return submenu
