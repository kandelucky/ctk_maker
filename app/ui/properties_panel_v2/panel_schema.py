"""Schema traversal + disabled/hidden state mixin for PropertiesPanelV2.

Split out of the monolithic ``panel.py`` (v0.0.15.11 refactor round).
Covers the "schema → Treeview rows" pipeline:

- ``_parent_layout_type`` / ``_compute_layout_extras`` /
  ``_effective_schema`` — compose the full schema (descriptor +
  parent-driven pack_*/grid_* extras) for the selected node.
- ``_populate_schema`` — walk the schema, emit group / subgroup /
  paired / single rows into ``self.tree``.
- ``_insert_pair`` / ``_insert_prop`` / ``_refresh_cell`` — row-level
  renderers + value-cell updaters.
- ``_compute_disabled_states`` / ``_apply_managed_layout_disabled`` /
  ``_is_hidden`` / ``_row_tags_for`` / ``_apply_disabled_overlay`` —
  ``disabled_when`` / ``hidden_when`` evaluation + per-row overlay
  state sync.

Relies on ``self.tree``, ``self.project``, ``self.current_id``,
``self._prop_iids``, ``self._subgroup_preview_iids``,
``self._style_subgroup_iid``, ``self._disabled_states``,
``self._layout_extras`` — all set up in ``PropertiesPanelV2.__init__``.
"""

from __future__ import annotations

import tkinter as tk

from app.core.project import WINDOW_ID
from app.core.variables import is_var_token, parse_var_token
from app.widgets.layout_schema import (
    DEFAULT_LAYOUT_TYPE,
    child_layout_schema,
)

from .constants import STYLE_BOOL_NAMES, TREE_BG
from .editors import get_editor
from .format_utils import (
    compute_subgroup_preview,
    format_numeric_pair_preview,
    format_value,
)
from .overlays import (
    SLOT_BIND_BUTTON,
    SLOT_BIND_CLEAR,
    place_bind_button,
    place_bind_clear,
)


def _binding_chip_text(project, value) -> str | None:
    """Render a bound value as the variable's plain name. The cell's
    ``bound`` tag colours the row background — no glyph prefix needed
    on the text itself. Returns None for literal values.
    """
    var_id = parse_var_token(value)
    if var_id is None:
        return None
    entry = project.get_variable(var_id) if project is not None else None
    return entry.name if entry is not None else "(missing)"


class SchemaMixin:
    """Schema walker + disabled/hidden state logic. See module docstring."""

    # ------------------------------------------------------------------
    # Layout extras (parent-driven pack_* / grid_* rows)
    # ------------------------------------------------------------------
    def _parent_layout_type(self, node) -> str:
        """``place`` / ``pack`` / ``grid`` for the container holding
        ``node``. Window itself has no parent — we return the default
        so its descriptor's own LAYOUT_TYPE_ROW is the only one shown.
        """
        if node is None or node.id == WINDOW_ID:
            return DEFAULT_LAYOUT_TYPE
        parent = getattr(node, "parent", None)
        if parent is not None:
            return parent.properties.get(
                "layout_type", DEFAULT_LAYOUT_TYPE,
            )
        # Root-level node: parent is the document/window.
        doc = self.project.find_document_for_widget(node.id)
        if doc is None:
            return DEFAULT_LAYOUT_TYPE
        return doc.window_properties.get(
            "layout_type", DEFAULT_LAYOUT_TYPE,
        )

    def _compute_layout_extras(self, node) -> list[dict]:
        if node is None or node.id == WINDOW_ID:
            return []
        return list(child_layout_schema(self._parent_layout_type(node)))

    def _effective_schema(self, descriptor) -> list[dict]:
        return list(descriptor.property_schema) + self._layout_extras

    # ------------------------------------------------------------------
    # Schema traversal → tree hierarchy
    # ------------------------------------------------------------------
    def _populate_schema(self, descriptor, properties: dict, node=None) -> None:
        schema = [
            p for p in self._effective_schema(descriptor)
            if not self._is_hidden(p, properties)
        ]
        current_group: str | None = None
        current_subgroup: str | None = None
        group_iid: str = ""
        subgroup_iid: str = ""

        i = 0
        while i < len(schema):
            prop = schema[i]
            group = prop.get("group", "General")
            subgroup = prop.get("subgroup")
            pair_id = prop.get("pair")

            # Enter new group
            if group != current_group:
                group_iid = f"g:{group}"
                self.tree.insert(
                    "", "end", iid=group_iid,
                    text=group, values=("",), open=True,
                    tags=("class",),
                )
                current_group = group
                current_subgroup = None
                subgroup_iid = group_iid

            # Enter new subgroup (or leave one)
            if subgroup != current_subgroup:
                if subgroup:
                    subgroup_iid = f"g:{group}/{subgroup}"
                    preview = compute_subgroup_preview(
                        descriptor, group, subgroup, properties,
                    )
                    self.tree.insert(
                        group_iid, "end", iid=subgroup_iid,
                        text=subgroup, values=(preview,), open=False,
                        tags=("group",),
                    )
                    self._subgroup_preview_iids[
                        f"{group}/{subgroup}"
                    ] = subgroup_iid
                    # Track the Style subgroup specifically so we can
                    # attach the multi-color preview overlay later.
                    if subgroup.lower() == "style":
                        self._style_subgroup_iid = subgroup_iid
                else:
                    subgroup_iid = group_iid
                current_subgroup = subgroup

            parent_iid = subgroup_iid

            # Paired row detection — collect consecutive same-pair items
            if pair_id:
                items: list[dict] = []
                j = i
                while (
                    j < len(schema) and schema[j].get("pair") == pair_id
                ):
                    items.append(schema[j])
                    j += 1
                self._insert_pair(items, properties, parent_iid)
                i = j
                continue

            # Single prop
            self._insert_prop(prop, properties, parent_iid)
            i += 1

    def _insert_pair(
        self, items: list[dict], properties: dict, parent_iid: str,
    ) -> None:
        """Emit a pair as rows. Pure-numeric pairs (Position, Size)
        get a virtual parent row; mixed pairs flatten into the parent
        subgroup so they read like independent siblings.
        """
        all_numeric = all(p["type"] == "number" for p in items)
        first = items[0]
        pair_label = first.get("row_label") or first.get("label", "")

        if all_numeric and pair_label:
            # Virtual "Position" / "Size" parent row
            virt_iid = f"pair:{first.get('pair')}"
            preview = format_numeric_pair_preview(items, properties)
            self.tree.insert(
                parent_iid, "end", iid=virt_iid,
                text=pair_label, values=(preview,),
                open=False, tags=("group",),
            )
            for item in items:
                self._insert_prop(item, properties, virt_iid)
            return

        # Mixed pair → flatten inline
        for item in items:
            self._insert_prop(item, properties, parent_iid)

    def _insert_prop(
        self, prop: dict, properties: dict, parent_iid: str,
    ) -> None:
        pname = prop["name"]
        ptype = prop["type"]
        # For paired props (x/y, width/height), the `row_label` belongs
        # to the virtual parent row — children show their individual
        # `label` (X/Y, W/H) instead.
        if prop.get("pair"):
            label = prop.get("label") or pname
        else:
            label = (
                prop.get("row_label")
                or prop.get("label")
                or pname
            )
        value = properties.get(pname)
        iid = f"p:{pname}"
        self._prop_iids[pname] = iid

        chip = _binding_chip_text(self.project, value)
        display = chip if chip is not None else format_value(
            ptype, value, prop,
        )
        tags = self._row_tags_for(pname, prop, value)

        self.tree.insert(
            parent_iid, "end", iid=iid,
            text=label, values=(display,),
            open=False, tags=tags,
        )

        # Skip the rich editor overlays when a property is bound to a
        # variable — the chip in the cell is the editor surface, and
        # any literal-value overlay would visually fight with it. The
        # right-click menu handles bind / unbind from this row.
        if chip is None:
            get_editor(ptype).populate(self, iid, pname, prop, value)

        # Resolve binding scope so the diamond carries the same colour
        # cue as the Variables window tab — global = blue, local =
        # orange. Unbound rows stay neutral grey.
        bound_scope = None
        if chip is not None:
            from app.core.variables import parse_var_token
            var_id = parse_var_token(value)
            if var_id is not None:
                bound_scope = self.project.get_variable_scope(var_id)

        # Diamond bind button in the left gutter of the label column.
        # ◇ unbound / ◆ bound, the shape change carries the bind state
        # and the foreground colour carries the scope. The row
        # background stays neutral — fixed orange tint regardless of
        # scope read as inconsistent once globals went blue. The chip
        # text + filled diamond + scope colour + ✕ unbind button are
        # already four signals, no need for a fifth.
        from app.ui.icons import (
            VARIABLES_GLOBAL_COLOR, VARIABLES_LOCAL_COLOR,
        )
        bound_bg = TREE_BG
        idle_bg = TREE_BG
        hover_bg = "#2d2d2d"
        if bound_scope == "global":
            idle_fg = VARIABLES_GLOBAL_COLOR
        elif bound_scope == "local":
            idle_fg = VARIABLES_LOCAL_COLOR
        else:
            idle_fg = "#888888"
        hover_fg = "#ffffff"
        bind_btn = tk.Label(
            self.tree,
            text="◆" if chip is not None else "◇",
            bg=idle_bg, fg=idle_fg,
            font=("Segoe UI Symbol", 10),
            cursor="hand2", borderwidth=0, padx=0, pady=0,
        )
        bind_btn.bind(
            "<Enter>",
            lambda _e, b=bind_btn, bg=hover_bg, fg=hover_fg:
            b.configure(bg=bg, fg=fg),
        )
        bind_btn.bind(
            "<Leave>",
            lambda _e, b=bind_btn, bg=idle_bg, fg=idle_fg:
            b.configure(bg=bg, fg=fg),
        )
        bind_btn.bind(
            "<Button-1>",
            lambda e, p=pname, pr=prop:
            self._open_binding_menu_for(e, p, pr),
        )
        self.overlays.add(
            iid, SLOT_BIND_BUTTON, bind_btn, place_bind_button,
        )

        # ✕ unbind button on bound rows only. Single click clears the
        # binding and restores the descriptor's default literal so
        # the row falls back to its normal editor. Hover treatment
        # matches the diamond so both feel like buttons.
        if chip is not None:
            clear_btn = tk.Label(
                self.tree,
                text="✕",
                bg=bound_bg, fg="#aaaaaa",
                font=("Segoe UI Symbol", 11),
                cursor="hand2", borderwidth=0, padx=0, pady=0,
            )
            clear_btn.bind(
                "<Enter>",
                lambda _e, b=clear_btn:
                b.configure(bg="#3d2c1c", fg="#ff8080"),
            )
            clear_btn.bind(
                "<Leave>",
                lambda _e, b=clear_btn:
                b.configure(bg=bound_bg, fg="#aaaaaa"),
            )
            clear_btn.bind(
                "<Button-1>",
                lambda _e, p=pname, pr=prop:
                self._unbind_property(p, pr),
            )
            self.overlays.add(
                iid, SLOT_BIND_CLEAR, clear_btn, place_bind_clear,
            )

    def _refresh_cell(self, iid: str, prop: dict, value) -> None:
        ptype = prop["type"]
        chip = _binding_chip_text(self.project, value)
        display = chip if chip is not None else format_value(
            ptype, value, prop,
        )
        try:
            self.tree.set(iid, "value", display)
        except tk.TclError:
            return

        # Refresh row tags so the ``bound`` background tint follows
        # bind / unbind changes triggered through undo / redo or any
        # other property mutation that doesn't go through _rebuild.
        try:
            self.tree.item(
                iid,
                tags=self._row_tags_for(prop["name"], prop, value),
            )
        except tk.TclError:
            pass
            if prop["name"] in STYLE_BOOL_NAMES:
                self._refresh_style_preview()

        get_editor(ptype).refresh(self, iid, prop["name"], prop, value)

        # Refresh subgroup preview (corners/border) if this prop feeds
        # one.
        self._maybe_refresh_subgroup_preview(prop)
        # Numeric-pair virtual parents show a combined preview — refresh
        # the parent's preview if this prop belongs to one.
        self._maybe_refresh_pair_parent(prop)

    def _maybe_refresh_subgroup_preview(self, prop: dict) -> None:
        group = prop.get("group")
        subgroup = prop.get("subgroup")
        if not group or not subgroup:
            return
        key = f"{group}/{subgroup}"
        iid = self._subgroup_preview_iids.get(key)
        if iid is None:
            return
        descriptor = self._current_descriptor()
        node = self.project.get_widget(self.current_id)
        if descriptor is None or node is None:
            return
        preview = compute_subgroup_preview(
            descriptor, group, subgroup, node.properties,
        )
        try:
            self.tree.set(iid, "value", preview)
        except tk.TclError:
            pass

    def _maybe_refresh_pair_parent(self, prop: dict) -> None:
        pair_id = prop.get("pair")
        if not pair_id:
            return
        descriptor = self._current_descriptor()
        if descriptor is None:
            return
        pair_items = [
            p for p in self._effective_schema(descriptor)
            if p.get("pair") == pair_id
        ]
        if not all(p["type"] == "number" for p in pair_items):
            return
        virt_iid = f"pair:{pair_id}"
        if not self.tree.exists(virt_iid):
            return
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        preview = format_numeric_pair_preview(
            pair_items, node.properties,
        )
        try:
            self.tree.set(virt_iid, "value", preview)
        except tk.TclError:
            pass

    def _find_prop(self, descriptor, prop_name: str):
        for p in self._effective_schema(descriptor):
            if p["name"] == prop_name:
                return p
        return None

    # ------------------------------------------------------------------
    # disabled_when / hidden_when
    # ------------------------------------------------------------------
    def _compute_disabled_states(
        self, descriptor, properties: dict,
    ) -> dict[str, bool]:
        result: dict[str, bool] = {}
        for prop in self._effective_schema(descriptor):
            fn = prop.get("disabled_when")
            if callable(fn):
                try:
                    result[prop["name"]] = bool(fn(properties))
                except Exception:
                    result[prop["name"]] = False
        return result

    def _apply_managed_layout_disabled(self, node) -> None:
        """Disable geometry fields for managed-layout children — the
        layout manager owns placement so x/y/width/height are read-only.
        """
        from app.widgets.layout_schema import normalise_layout_type
        if node is None or node.parent is None:
            return
        parent_layout = normalise_layout_type(
            node.parent.properties.get("layout_type", "place"),
        )
        if parent_layout == "place":
            return
        for field in ("x", "y", "width", "height"):
            self._disabled_states[field] = True

    def _is_hidden(self, prop: dict, properties: dict) -> bool:
        """Schema rows can declare a ``hidden_when(properties)``
        callable that makes the row vanish (not just disable) when
        the predicate holds. Used for layout-specific fields that
        don't apply under other managers — e.g. grid Dimensions
        shouldn't even show on a vbox Frame.
        """
        fn = prop.get("hidden_when")
        if callable(fn):
            try:
                return bool(fn(properties))
            except Exception:
                return False
        return False

    def _row_tags_for(self, pname: str, prop: dict, value) -> tuple[str, ...]:
        tags: list[str] = []
        if is_var_token(value):
            tags.append("bound")
        elif prop["type"] == "boolean" and not value:
            tags.append("bool_off")
        if self._disabled_states.get(pname):
            tags.append("disabled")
        return tuple(tags)

    def _apply_disabled_overlay(
        self, pname: str, prop: dict, disabled: bool,
    ) -> None:
        """Sync per-row overlays (swatches, buttons) with disabled."""
        iid = self._prop_iids.get(pname)
        if iid is None:
            return
        get_editor(prop["type"]).set_disabled(
            self, iid, pname, prop, disabled,
        )
