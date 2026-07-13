"""Schema traversal + disabled/hidden state mixin for PropertiesPanel.

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
``self._layout_extras`` — all set up in ``PropertiesPanel.__init__``.
"""

from __future__ import annotations

import tkinter as tk

from app.core.project import WINDOW_ID
from app.core.variables import is_var_token, parse_var_token
from app.widgets.layout_schema import (
    DEFAULT_LAYOUT_TYPE,
    child_layout_schema,
)
from app.ui.system_fonts import ui_font

from app.ui.system_fonts import derive_ui_font

from .constants import (
    DISABLED_FG, STYLE_BOOL_NAMES, TREE_BG, TREE_FG, VALUE_BG,
)
from .editors import get_editor
from .format_utils import (
    compute_subgroup_preview,
    format_numeric_pair_preview,
    format_value,
)
from .overlays import (
    SLOT_BIND_BUTTON,
    SLOT_BIND_CLEAR,
    SLOT_ENUM_BUTTON,
    SLOT_EVENT_ADD,
    SLOT_EVENT_DROPDOWN,
    SLOT_EVENT_UNBIND,
    SLOT_NAME_BOX,
    SLOT_NAME_BOX_BUTTON,
    SLOT_NAME_BOX_CLEAR,
    SLOT_SCRIPT_NAME_CHIP,
    SLOT_SCRIPT_PATH,
    SLOT_TEXT_VALUE,
    SLOT_VAR_COLOR_SWATCH,
    SLOT_VAR_TYPE_CHIP,
    place_bind_button,
    place_bind_clear,
    place_enum_button,
    place_event_add,
    place_event_dropdown,
    place_event_unbind,
    place_name_box,
    place_name_box_button,
    place_name_clear_left,
    place_script_name_chip,
    place_script_open_label,
    place_script_path,
    place_text_value,
    place_var_color_swatch,
    place_var_type_chip,
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


def _script_call_resolvable(project, node, cls: str, scope=None) -> bool:
    """True if a ``script_call``'s class is still usable from ``node``:
    its component is attached (honoring ``scope``) **and**, for a saved
    project, its file still exists under ``scripts/``. Mirrors the
    exporter's resolution so the panel flags exactly what export drops —
    a script detached after wiring, or one whose file was deleted."""
    if not cls:
        return False
    from pathlib import Path
    from app.core.script_paths import user_scripts_dir
    from app.io.scripts import resolve_script_component
    document = project.find_document_for_widget(node.id)
    comp = resolve_script_component(node, document, cls, scope)
    if comp is None:
        return False
    scripts_dir = user_scripts_dir(getattr(project, "path", None))
    if scripts_dir is None:
        # Unsaved project — no folder to verify against; trust the
        # attachment so in-memory / test flows still resolve.
        return True
    return (Path(scripts_dir) / comp.get("script", "")).exists()


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

        # Window selection: append a read-only "Local Variables" group
        # at the very end so the user can see what locals belong to the
        # current document without opening the F11 Variables window.
        if descriptor.type_name == WINDOW_ID:
            # Spacer separates the trailing declarations block (locals)
            # from the window-property block above so the user reads
            # them as a distinct zone.
            self._insert_section_spacer()
            self._populate_local_variables_group()

        # CTkScript model — the "Scripts" group (attach CTkScript
        # classes to this object). Sits above Events: you attach a
        # script, then bind events to its methods. Shown for every
        # object (widget + window).
        if node is not None:
            self._populate_node_scripts_group(node)
            # Script Variables — bind the attached scripts' exposed
            # ``name: tk.StringVar`` fields to project variables. Only
            # shown when a field exists, so plain objects stay tidy.
            self._populate_script_variables_group(node)

        # Phase 2 visual scripting — Events group for event-capable
        # widgets (button, slider, entry, …). Renders below every
        # property group; event-less widgets (Label, Frame, Image)
        # skip it entirely so their panels stay tidy.
        if node is not None:
            self._populate_events_group(node)

    def _insert_section_spacer(self) -> None:
        """Empty top-level row that visually offsets the trailing
        Local Variables / Object References sections from the schema
        groups above. Selectable but click-inert.
        """
        self.tree.insert(
            "", "end", iid="spacer:trailing",
            text="", values=("",),
            tags=("spacer",),
        )

    def _populate_local_variables_group(self) -> None:
        doc = self.project.active_document if self.project else None
        group_iid = "g:Local Variables"
        self.tree.insert(
            "", "end", iid=group_iid,
            text="Local Variables", values=("",), open=True,
            tags=("class",),
        )
        locals_list = list(doc.local_variables) if doc is not None else []
        if not locals_list:
            self.tree.insert(
                group_iid, "end", iid="localvar:empty",
                text="", values=("no local variables",),
                tags=("disabled",),
            )
            return
        from app.core.variables import VAR_TYPE_SHORT
        for entry in locals_list:
            default_str = str(entry.default or "")
            if len(default_str) > 30:
                default_str = default_str[:29] + "…"
            iid = f"localvar:{entry.id}"
            # v1.38 — Layout: name + right-edge type chip in the tree
            # column. Value column carries the default; colour rows
            # additionally get a left-edge swatch overlay in the value
            # cell, so the row reads ``Name [chip] | [swatch] hex``.
            if entry.type == "color":
                row_value = f"        {default_str}"
            else:
                row_value = default_str
            self.tree.insert(
                group_iid, "end", iid=iid,
                text=entry.name,
                values=(row_value,),
            )
            self._attach_var_type_indicator(iid, entry, default_str)

    def _attach_var_type_indicator(
        self, row_iid: str, entry, default_str: str,
    ) -> None:
        """v1.38 — per-row overlays on the Local Variables list. Every
        type wears a dim 3-letter chip (``str`` / ``int`` / ``flt`` /
        ``bol`` / ``col``) at the right edge of the name column.
        Colour rows additionally show a real-hue swatch at the left of
        the value column so the user reads the row as ``Name col |
        [swatch] #hex`` at a glance.
        """
        if self.overlays is None:
            return
        from app.core.variables import VAR_TYPE_SHORT
        short = VAR_TYPE_SHORT.get(entry.type, entry.type)
        chip = tk.Label(
            self.tree,
            text=short,
            bg=TREE_BG, fg="#777777",
            font=ui_font(9),
            anchor="w",
            borderwidth=0, padx=0, pady=0,
        )
        self.overlays.add(
            row_iid, SLOT_VAR_TYPE_CHIP, chip, place_var_type_chip,
        )
        if entry.type == "color":
            from .editors.color import _swatch_bg
            try:
                swatch = tk.Frame(
                    self.tree, bg=_swatch_bg(default_str),
                    highlightthickness=1,
                    highlightbackground="#3a3a3a",
                )
            except tk.TclError:
                swatch = tk.Frame(
                    self.tree, bg="#2b2b2b",
                    highlightthickness=1,
                    highlightbackground="#3a3a3a",
                )
            self.overlays.add(
                row_iid, SLOT_VAR_COLOR_SWATCH, swatch,
                place_var_color_swatch,
            )

    def _populate_script_variables_group(self, node) -> None:
        """CTkScript model — Unity-style per-script field inspector. One
        group per attached script that exposes ``name: tk.StringVar``
        fields (header ``ClassName (Script)``, like Unity's component
        foldout); under it, one row per field as ``label | value``. The
        value cell is an object-field — click to bind a project variable
        through a type-filtered picker (globals + this window's locals).
        A script with no exposed fields contributes no group, so plain
        objects stay tidy. See docs/plans/archive/script_variable_binding.md.
        """
        if self.project is None or node is None:
            return
        target = self._component_target(node)
        if target is None:
            return
        from pathlib import Path

        from app.core.script_paths import user_scripts_dir
        from app.io.scripts import parse_exposed_variables
        scripts_dir = user_scripts_dir(getattr(self.project, "path", None))
        if not scripts_dir:
            return
        doc = self.project.active_document
        locals_ = list(doc.local_variables) if doc is not None else []
        by_id = {v.id: v for v in [*self.project.variables, *locals_]}
        comps = list(getattr(target, "attached_components", []) or [])
        for ci, comp in enumerate(comps):
            cls = comp.get("class") or ""
            script_rel = comp.get("script") or ""
            if not cls or not script_rel:
                continue
            fields = parse_exposed_variables(
                Path(scripts_dir) / script_rel, cls,
            )
            if not fields:
                continue
            bindings = comp.get("var_bindings") or {}
            values = comp.get("field_values") or {}
            group_iid = f"g:scriptvars:{ci}"
            self.tree.insert(
                "", "end", iid=group_iid,
                text=f"{cls} (Script)", values=("",), open=True,
                tags=("class",),
            )
            for fi, (field, var_type) in enumerate(fields):
                row_iid = f"scriptvar:{ci}:{fi}"
                self.tree.insert(
                    group_iid, "end", iid=row_iid,
                    text=field, values=("",),
                )
                self._attach_field_type_chip(row_iid, var_type)
                self._render_field_editor(
                    row_iid, node, cls, field, var_type,
                    bindings.get(field), values.get(field), by_id,
                )

    def _attach_field_type_chip(self, row_iid: str, var_type: str) -> None:
        """Dim 3-letter type chip (``str`` / ``int`` / ``flt`` / ``bol``)
        at the right edge of a Script Variables row's name column —
        mirrors the Local Variables list chip."""
        if self.overlays is None:
            return
        from app.core.variables import VAR_TYPE_SHORT
        chip = tk.Label(
            self.tree,
            text=VAR_TYPE_SHORT.get(var_type, var_type),
            bg=TREE_BG, fg="#777777",
            font=ui_font(9), anchor="w",
            borderwidth=0, padx=0, pady=0,
        )
        self.overlays.add(
            row_iid, SLOT_VAR_TYPE_CHIP, chip, place_var_type_chip,
        )

    def _render_field_editor(
        self, row_iid, node, cls, field, var_type,
        bound_id, inline_val, by_id,
    ) -> None:
        """Value cell of one Script Variables row — Unity-style. Bound to
        a project variable → object-field; otherwise an inline editor for
        the field's type (entry / checkbox / swatch). A 🔗 button at the
        right always opens the variable picker."""
        if self.overlays is None:
            return
        if bound_id is not None:
            name = by_id[bound_id].name if bound_id in by_id else "missing"
            # Bound value reads in the standard panel foreground — the 🔗
            # button already signals the bound state, so the text needs no
            # extra colour. Orange stays only as a real "variable missing"
            # warning, not as styling.
            color = TREE_FG if bound_id in by_id else "#e0a030"
            lbl = tk.Label(
                self.tree, text=name, bg=VALUE_BG, fg=color,
                font=ui_font(11), anchor="w", padx=4, pady=0,
                borderwidth=0, highlightthickness=0, cursor="hand2",
            )
            lbl.bind("<Button-1>", lambda _e: self._open_variable_picker(
                node, cls, field, var_type, bound_id))
            self.overlays.add(row_iid, SLOT_TEXT_VALUE, lbl, place_text_value)
        elif var_type == "bool":
            self._field_checkbox(row_iid, node, cls, field, inline_val)
        elif var_type == "color":
            self._field_swatch(row_iid, node, cls, field, inline_val)
        else:
            self._field_entry(row_iid, node, cls, field, inline_val)
        self._field_link_button(row_iid, node, cls, field, var_type, bound_id)

    def _field_link_button(self, row_iid, node, cls, field, var_type, bound_id):
        btn = tk.Label(
            self.tree, text="🔗", bg=VALUE_BG, fg="#888888",
            font=ui_font(10), cursor="hand2", borderwidth=0, padx=0, pady=0,
        )
        btn.bind("<Enter>", lambda _e, b=btn: b.configure(fg="#a9e0b4"))
        btn.bind("<Leave>", lambda _e, b=btn: b.configure(fg="#888888"))
        btn.bind("<Button-1>", lambda _e: self._open_variable_picker(
            node, cls, field, var_type, bound_id))
        self.overlays.add(row_iid, SLOT_ENUM_BUTTON, btn, place_enum_button)

    def _field_entry(self, row_iid, node, cls, field, inline_val):
        current = "" if inline_val is None else str(inline_val)
        e = tk.Entry(
            self.tree, bg="#2a2a2a", fg=TREE_FG, insertbackground=TREE_FG,
            relief="flat", font=ui_font(11), highlightthickness=1,
            highlightbackground="#212121", highlightcolor="#5a8fd0",
        )
        e.insert(0, current)

        def commit(_e=None):
            new = e.get()
            if new != current:
                self._set_field_value(node, cls, field, new)
        e.bind("<FocusOut>", commit)
        e.bind("<Return>", lambda _e: (commit(), self.tree.focus_set()))
        self.overlays.add(row_iid, SLOT_TEXT_VALUE, e, place_text_value)

    def _field_checkbox(self, row_iid, node, cls, field, inline_val):
        checked = str(inline_val).strip().lower() in ("true", "1", "yes")
        v = tk.IntVar(value=1 if checked else 0)
        cb = tk.Checkbutton(
            self.tree, bg=VALUE_BG, activebackground=VALUE_BG,
            highlightthickness=0, bd=0, cursor="hand2", variable=v,
            command=lambda: self._set_field_value(
                node, cls, field, "True" if v.get() else "False"),
        )
        cb._maker_var = v  # keep the IntVar alive with the widget
        self.overlays.add(
            row_iid, SLOT_VAR_COLOR_SWATCH, cb, place_var_color_swatch,
        )

    def _field_swatch(self, row_iid, node, cls, field, inline_val):
        color = inline_val or "#000000"
        try:
            sw = tk.Frame(self.tree, bg=color, cursor="hand2",
                          highlightthickness=1, highlightbackground="#212121")
        except tk.TclError:
            sw = tk.Frame(self.tree, bg="#2b2b2b", cursor="hand2",
                          highlightthickness=1, highlightbackground="#212121")
        sw.bind("<Button-1>", lambda _e: self._pick_field_color(
            node, cls, field, inline_val))
        self.overlays.add(
            row_iid, SLOT_VAR_COLOR_SWATCH, sw, place_var_color_swatch,
        )

    def _pick_field_color(self, node, cls, field, current):
        from tkinter import colorchooser
        res = colorchooser.askcolor(
            color=current or "#000000", parent=self.winfo_toplevel(),
        )
        if res and res[1]:
            self._set_field_value(node, cls, field, res[1])

    def _set_field_value(self, node, cls: str, field: str, value: str) -> None:
        """Set a field's inline literal value via an undoable command.
        Guarded against re-entrancy (the commit triggers a rebuild that
        destroys the editing widget, which can re-fire FocusOut)."""
        if self.project is None or getattr(self, "_committing_field", False):
            return
        self._committing_field = True
        try:
            from app.core.commands import SetFieldSourceCommand
            cmd = SetFieldSourceCommand(node.id, cls, field, "value", value)
            cmd.redo(self.project)
            self.project.history.push(cmd)
            self._rebuild()
        finally:
            self._committing_field = False

    def _open_variable_picker(
        self, node, cls: str, field: str, var_type: str, bound_id,
    ) -> None:
        """Pop a type-filtered menu of project variables (globals + this
        window's locals) for one script field; picking one binds it, and
        a "Clear binding" entry shows when the field is already bound."""
        from app.core.variables import VAR_TYPE_SHORT, eligible_variables
        from app.ui.properties_panel.constants import menu_style
        doc = self.project.active_document if self.project else None
        globals_ = list(self.project.variables) if self.project else []
        locals_ = list(doc.local_variables) if doc is not None else []
        choices = eligible_variables(globals_, locals_, var_type)
        menu = tk.Menu(self.tree, tearoff=0, **menu_style())
        if choices:
            for v in choices:
                short = VAR_TYPE_SHORT.get(v.type, v.type)
                scope_lbl = "local" if v.scope == "local" else "global"
                mark = "● " if v.id == bound_id else "    "
                menu.add_command(
                    label=f"{mark}{v.name}   ({short} · {scope_lbl})",
                    command=lambda vid=v.id:
                    self._bind_variable(node, cls, field, vid),
                )
        else:
            menu.add_command(
                label="No matching variables", command=lambda: None,
                foreground="#777777", activeforeground="#777777",
                activebackground="#2d2d30",
            )
        if bound_id is not None:
            menu.add_separator()
            menu.add_command(
                label="Clear binding",
                command=lambda: self._bind_variable(node, cls, field, None),
            )
        try:
            menu.tk_popup(
                self.tree.winfo_pointerx(), self.tree.winfo_pointery(),
            )
        finally:
            menu.grab_release()

    def _bind_variable(self, node, cls: str, field: str, var_id) -> None:
        """Bind a script field to a project variable (or clear it when
        ``var_id`` is None — back to its inline default) via an undoable
        command, then repaint. Setting a variable clears any inline
        value for the field (single source)."""
        if self.project is None:
            return
        from app.core.commands import SetFieldSourceCommand
        kind = "var" if var_id else None
        cmd = SetFieldSourceCommand(node.id, cls, field, kind, var_id)
        cmd.redo(self.project)
        self.project.history.push(cmd)
        self._rebuild()

    def _populate_node_scripts_group(self, node) -> None:
        """CTkScript model — the "Scripts" group on any object (widget
        or window). One row per attached script (file location on the
        left, an "Edit Script" action chip + ``×`` detach icon on the
        right), then an always-present "Add Script" row whose ``+`` opens
        a picker of attachable classes from the project's ``scripts/``
        folder. Attaching here decides scope: a widget script knows its
        widget, a window script knows the window. Icons mirror the Events
        group's flat ``+`` / ``✕`` styling.
        """
        if self.project is None or node is None:
            return
        target = self._component_target(node)
        if target is None:
            return
        group_iid = "g:Scripts"
        self.tree.insert(
            "", "end", iid=group_iid,
            text="Scripts", values=("",), open=True,
            tags=("class",),
        )
        from app.core.script_paths import USER_SCRIPTS_DIR_NAME
        comps = list(getattr(target, "attached_components", []) or [])
        for idx, comp in enumerate(comps):
            script_rel = (comp.get("script", "") or "").replace("\\", "/")
            location = (
                f"{USER_SCRIPTS_DIR_NAME}/{script_rel}"
                if script_rel else USER_SCRIPTS_DIR_NAME
            )
            row_iid = f"comp:{idx}"
            self.tree.insert(
                group_iid, "end", iid=row_iid, text="", values=("",),
            )
            self._node_script_path_label(row_iid, location)
            self._node_script_open_label(row_iid, comp.get("script", ""))
            self._node_script_remove_icon(row_iid, node, comp.get("class", ""))
        # Always-present "Add Script" row — the only row in the empty
        # state, an add-more affordance below existing scripts otherwise.
        add_iid = "comp:add"
        self.tree.insert(
            group_iid, "end", iid=add_iid, text="", values=("",),
        )
        self._node_script_add_label(
            add_iid, lambda n=node: self._open_component_picker(n),
        )
        self._node_script_add_icon(add_iid, node)

    def _node_script_path_label(self, row_iid: str, full_path: str) -> None:
        """File-location label in the name column of a script row.
        Left-elides to keep the tail visible (the placer handles it);
        hovering shows the full path as a tooltip when truncated."""
        lbl = tk.Label(
            self.tree,
            text=full_path,
            bg=TREE_BG, fg=TREE_FG,
            font=ui_font(11), anchor="w",
            borderwidth=0, padx=0, pady=0,
        )
        lbl._full_text = full_path
        lbl.bind(
            "<Enter>",
            lambda e, w=lbl, p=full_path: self._tooltip.schedule(
                e.x_root, e.y_root, p, key=f"scriptpath:{id(w)}",
            ),
        )
        lbl.bind("<Leave>", lambda _e: self._tooltip.cancel())
        if self.overlays is not None:
            self.overlays.add(
                row_iid, SLOT_SCRIPT_PATH, lbl, place_script_path,
            )

    def _node_script_add_label(self, row_iid: str, on_click) -> None:
        """"Add Script" prompt in the add row's value cell — a bounded
        box like the attached-script rows, but in a dimmer fill + text
        so it reads as a distinct add affordance, not an attached item.
        Single click runs ``on_click``; the ``+`` icon does the same."""
        chip = tk.Label(
            self.tree,
            text="Add Script",
            bg="#262626", fg="#999999",
            font=ui_font(11), anchor="w", padx=4, pady=0,
            borderwidth=0, highlightthickness=0,
            cursor="hand2",
        )
        chip.bind("<Enter>", lambda _e, b=chip: b.configure(fg="#cccccc"))
        chip.bind("<Leave>", lambda _e, b=chip: b.configure(fg="#999999"))
        chip.bind("<Button-1>", lambda _e: on_click())
        if self.overlays is not None:
            self.overlays.add(
                row_iid, SLOT_SCRIPT_NAME_CHIP, chip, place_script_name_chip,
            )

    def _node_script_open_label(self, row_iid: str, script_rel: str) -> None:
        """"Edit <file>.py" action in a script row's value cell — plain
        text on a slightly lighter fill, single click opens the file in
        the editor. The file name elides from the end (the placer keeps
        the "Edit " prefix) when the cell is too narrow."""
        prefix = "Edit ["
        file_name = (script_rel or "").replace("\\", "/").rsplit("/", 1)[-1]
        full = f"{prefix}{file_name}]"
        lbl = tk.Label(
            self.tree,
            text=full,
            bg=VALUE_BG, fg=TREE_FG,
            font=ui_font(11), anchor="w", padx=4, pady=0,
            borderwidth=0, highlightthickness=0,
            cursor="hand2",
        )
        lbl._full_text = full
        lbl._prefix_len = len(prefix)
        lbl._suffix = "]"
        lbl.bind("<Enter>", lambda _e, b=lbl: b.configure(fg="#ffffff"))
        lbl.bind("<Leave>", lambda _e, b=lbl: b.configure(fg=TREE_FG))
        lbl.bind(
            "<Button-1>",
            lambda _e, p=script_rel: self._open_script_in_editor(p),
        )
        if self.overlays is not None:
            self.overlays.add(
                row_iid, SLOT_SCRIPT_NAME_CHIP, lbl, place_script_open_label,
            )

    def _node_script_remove_icon(self, row_iid: str, node, cls: str) -> None:
        """``✕`` detach icon on a script row — Events-group styling."""
        btn = tk.Label(
            self.tree,
            text="✕", bg=VALUE_BG, fg="#888888",
            font=ui_font(9),
            cursor="hand2", borderwidth=0, padx=0, pady=0,
        )
        btn.bind("<Enter>", lambda _e, b=btn: b.configure(fg="#ef4444"))
        btn.bind("<Leave>", lambda _e, b=btn: b.configure(fg="#888888"))
        btn.bind(
            "<Button-1>",
            lambda _e, n=node, c=cls: self._detach_script_component(n, c),
        )
        if self.overlays is not None:
            self.overlays.add(
                row_iid, SLOT_EVENT_UNBIND, btn, place_enum_button,
            )

    def _node_script_add_icon(self, row_iid: str, node) -> None:
        """``+`` add icon on the "Add Script" row — neutral standard
        colour (matches the 🔗 / ✕ buttons), on the dimmer add-row fill."""
        btn = tk.Label(
            self.tree,
            text="+", bg="#262626", fg="#888888",
            # The thin "+" glyph reads smaller than "✕" at the same size,
            # so bump it to sit at the ✕'s visual size (the panel standard).
            font=ui_font(13, "bold"),
            cursor="hand2", borderwidth=0, padx=0, pady=0,
        )
        btn.bind("<Enter>", lambda _e, b=btn: b.configure(fg="#ffffff"))
        btn.bind("<Leave>", lambda _e, b=btn: b.configure(fg="#888888"))
        btn.bind(
            "<Button-1>",
            lambda _e, n=node: self._open_component_picker(n),
        )
        if self.overlays is not None:
            self.overlays.add(
                row_iid, SLOT_EVENT_ADD, btn, place_event_add,
            )

    def _populate_events_group(self, node) -> None:
        """Phase 2 visual scripting — read-only display of every
        event registered for the widget type plus the methods bound
        to each. Empty events still render as headers so the user
        sees what's available; right-click on a header attaches a
        new action via the existing cascade flow.

        Each renderable row is mirrored into ``self._event_row_meta``
        so the right-click router can look up ``(kind, event_key,
        index)`` without re-deriving it from the iid string.

        The group inserts at the end of the schema walk — under the
        Content-first ordering (Content → Layout → Visual → Behavior),
        the schema's last group is the widget's Behavior cluster
        (Interaction / Button Interaction), so Events lands naturally
        right after Behavior with no manual hoist.
        """
        from app.widgets.event_registry import events_partitioned
        default_events, advanced_events = events_partitioned(node.widget_type)
        if not default_events and not advanced_events:
            return
        group_iid = "events:group"
        self.tree.insert(
            "", "end", iid=group_iid,
            text="Events", values=("",), open=True,
            tags=("class",),
        )
        meta = self._event_row_meta
        meta[group_iid] = ("group", "", None)
        widget_id = node.id
        # Advanced sub-group is created lazily so widgets without any
        # advanced events don't show an empty section. Default open=
        # state: closed unless the user has already bound a method to
        # one of the advanced events — in that case auto-expand so the
        # binding stays visible without an extra click.
        advanced_iid = "events:advanced"
        advanced_has_bindings = any(
            node.handlers.get(entry.key) for entry in advanced_events
        )
        advanced_inserted = False

        def _ensure_advanced_group() -> str:
            nonlocal advanced_inserted
            if not advanced_inserted:
                self.tree.insert(
                    group_iid, "end", iid=advanced_iid,
                    text="Advanced", values=("",),
                    open=advanced_has_bindings,
                    tags=("group",),
                )
                meta[advanced_iid] = ("group", "", None)
                advanced_inserted = True
            return advanced_iid

        # Render in two passes so the Advanced sub-group always lands
        # at the bottom of the Events group regardless of registration
        # order. ``ev_idx`` keeps a single counter across both passes
        # so iids remain unique for the meta lookup.
        ev_idx = 0
        for entry in default_events:
            ev_idx = self._render_event_row(
                ev_idx, entry, group_iid, node, widget_id, meta,
            )
        for entry in advanced_events:
            parent_iid = _ensure_advanced_group()
            ev_idx = self._render_event_row(
                ev_idx, entry, parent_iid, node, widget_id, meta,
            )

    def _render_event_row(
        self, ev_idx: int, entry, parent_iid: str, node,
        widget_id: str, meta: dict,
    ) -> int:
        """Insert one event header + its bound-method rows under
        ``parent_iid``. Shared by ``_populate_events_group`` for both
        the default block (parent = ``events:group``) and the advanced
        sub-section (parent = ``events:advanced``). Returns the next
        free ``ev_idx`` so the caller can keep iids unique across
        both passes.
        """
        methods = list(node.handlers.get(entry.key, []) or [])
        header_iid = f"events:e:{ev_idx}"
        label = entry.label[:1].upper() + entry.label[1:]
        if methods:
            preview = (
                f"({len(methods)} action"
                f"{'s' if len(methods) != 1 else ''})"
            )
        else:
            preview = "no action"
        # Empty events read dim (de-emphasised) so the bound ones stand
        # out; an event with handlers brightens to normal — same affordance
        # logic as the "Add Script" row vs attached scripts.
        self.tree.insert(
            parent_iid, "end", iid=header_iid,
            text=label, values=(preview,), open=True,
            tags=("event_active",) if methods else ("event_empty",),
        )
        meta[header_iid] = ("header", entry.key, None)
        self._attach_event_add_button(
            header_iid, widget_id, entry.key, dim=not methods,
        )
        for m_idx, handler_entry in enumerate(methods):
            self._render_handler_entry(
                ev_idx, m_idx, handler_entry, header_iid, entry,
                node, widget_id, meta,
            )
        # Unity-style placeholder rows for outer ``[+]`` clicks that
        # haven't picked a target yet. Each shows ``Add target``
        # with an inner ``[+]`` that opens the cascade picker.
        pending = self._pending_event_rows.get(
            (widget_id, entry.key), 0,
        )
        for p_idx in range(pending):
            self._render_pending_event_row(
                ev_idx, len(methods) + p_idx, header_iid, entry,
                widget_id, meta,
            )
        return ev_idx + 1

    def _render_pending_event_row(
        self, ev_idx: int, m_idx: int, header_iid: str,
        event_entry, widget_id: str, meta: dict,
    ) -> None:
        """Placeholder for a pending action — the same one-line layout as
        a committed handler: an empty ``Add target…`` box in the name
        column (click opens the target picker) + ✕ cancel, and a dark,
        disabled ``Pick function…`` box in the value column so the two-
        column shape is visible while the function side reads as not-yet-
        available. Lives only in panel state until a target commits it.
        """
        row_iid = f"events:m:{ev_idx}:{m_idx}"
        self.tree.insert(
            header_iid, "end", iid=row_iid,
            text="", values=("",), open=True,
        )
        meta[row_iid] = ("pending", event_entry.key, None)
        # Name column: ✕ (cancel) [ Add target… ] ▾ (pick), same shape as
        # a committed row so the pending → committed transition is smooth.
        self._attach_pending_cancel_button(
            row_iid, widget_id, event_entry.key,
        )
        self._attach_pending_target_box(
            row_iid, widget_id, event_entry.key,
        )
        self._attach_name_box_dropdown(
            row_iid,
            lambda wid=widget_id, k=event_entry.key:
            self._open_pending_target_picker(wid, k),
        )
        self._attach_disabled_function_box(row_iid)

    def _render_handler_entry(
        self, ev_idx: int, m_idx: int, handler_entry,
        header_iid: str, event_entry, node,
        widget_id: str, meta: dict,
    ) -> None:
        """Emit one handler entry as a single Unity-style row:
        ``target | function`` on one line. The target (attached
        CTkScript class) is boxed in the name column with a ✕ remove
        button; the method is boxed in the value column with a ▾
        function picker. Allowlisted ``<param>:`` child rows surface
        below only when the chosen function carries args.

        Missing bindings (target or method unresolvable) tint the
        offending box red — no glyph, just the colour cue.
        """
        row_iid = f"events:m:{ev_idx}:{m_idx}"
        _prefix, target_value, target_missing, target_picked = (
            self._target_label_for_entry(handler_entry, node)
        )
        method_label, method_missing, param_pairs = (
            self._method_and_params_for_entry(handler_entry)
        )
        # Single row — both columns are overlay boxes (name = target,
        # value = function), so the native cell text stays empty.
        self.tree.insert(
            header_iid, "end", iid=row_iid,
            text="", values=("",), open=True,
        )
        meta[row_iid] = ("method", event_entry.key, m_idx)
        # Name column: ✕ (left, two-stage clear) [ target box ] ▾ (retarget).
        self._attach_handler_clear_button(
            row_iid, widget_id, event_entry.key, m_idx, handler_entry,
        )
        self._attach_handler_target_box(
            row_iid, widget_id, event_entry.key, m_idx,
            target_value, target_missing, handler_entry,
        )
        self._attach_name_box_dropdown(
            row_iid,
            lambda wid=widget_id, k=event_entry.key, i=m_idx:
            self._open_target_retarget_picker(wid, k, i),
        )
        # Function box (value column) + ▾ picker — only once a target
        # is picked (matches the old "function appears after target").
        if target_picked:
            self._attach_handler_function_box(
                row_iid, widget_id, event_entry.key, m_idx,
                method_label, method_missing,
            )
            self._attach_function_dropdown_button(
                row_iid, widget_id, event_entry.key, m_idx,
            )
            # Parameter rows — only when a method is picked and the
            # allowlist entry carries args. Children of the single row.
            for p_idx, (pname, pvalue) in enumerate(param_pairs):
                param_iid = f"{row_iid}:p{p_idx}"
                self.tree.insert(
                    row_iid, "end",
                    iid=param_iid,
                    text=f"{pname}:", values=(pvalue,),
                )
                meta[param_iid] = (
                    "param", event_entry.key, m_idx, p_idx,
                )

    def _attach_handler_target_box(
        self, row_iid: str, widget_id: str, event_key: str, m_idx: int,
        target_value: str, target_missing: str | None, handler_entry,
    ) -> None:
        """Boxed target (script) value in the name column. Retarget is on
        the ▾ only (no left-click here); right-click opens Delete / Edit
        and double-click opens the script in the editor. Red text when the
        target is unresolvable."""
        if self.overlays is None:
            return
        lbl = tk.Label(
            self.tree, text=target_value, bg=VALUE_BG,
            fg="#ef4444" if target_missing else TREE_FG,
            font=ui_font(11), anchor="w", padx=4, pady=0,
            borderwidth=0, highlightthickness=0, cursor="hand2",
        )
        lbl._full_text = target_value
        lbl.bind(
            "<Button-3>",
            lambda e, wid=widget_id, k=event_key, i=m_idx, m=handler_entry:
            self._open_handler_target_menu(e, wid, k, i, m),
        )
        lbl.bind(
            "<Double-Button-1>",
            lambda _e, wid=widget_id, k=event_key, i=m_idx:
            self._open_handler_script(wid, k, i),
        )
        self.overlays.add(row_iid, SLOT_NAME_BOX, lbl, place_name_box)

    def _attach_handler_clear_button(
        self, row_iid: str, widget_id: str, event_key: str,
        m_idx: int, handler_entry,
    ) -> None:
        """✕ at the LEFT edge of the name column — first stage of the
        two-stage delete: drops the script binding but leaves a pending
        ``Add target…`` placeholder so the user can re-pick. A second ✕
        (on that pending row) removes the action entirely."""
        if self.overlays is None:
            return
        btn = tk.Label(
            self.tree, text="✕", bg=VALUE_BG, fg="#888888",
            font=ui_font(9), cursor="hand2", borderwidth=0, padx=0, pady=0,
        )
        btn.bind("<Enter>", lambda _e, b=btn: b.configure(fg="#ef4444"))
        btn.bind("<Leave>", lambda _e, b=btn: b.configure(fg="#888888"))
        btn.bind(
            "<Button-1>",
            lambda _e, wid=widget_id, k=event_key, i=m_idx, m=handler_entry:
            self._clear_handler_to_pending(wid, k, i, m),
        )
        self.overlays.add(
            row_iid, SLOT_NAME_BOX_CLEAR, btn, place_name_clear_left,
        )

    def _attach_name_box_dropdown(self, row_iid: str, on_click) -> None:
        """▾ at the right edge of the name column — the target picker.
        Used by both committed (retarget) and pending (pick) rows; the
        ``on_click`` decides which picker opens."""
        if self.overlays is None:
            return
        btn = tk.Label(
            self.tree, text="▾", bg=VALUE_BG, fg="#aaaaaa",
            font=ui_font(12, "bold"), cursor="hand2", borderwidth=0,
        )
        btn.bind("<Enter>", lambda _e, b=btn: b.configure(fg="#ffffff"))
        btn.bind("<Leave>", lambda _e, b=btn: b.configure(fg="#aaaaaa"))
        btn.bind("<Button-1>", lambda _e: on_click())
        self.overlays.add(
            row_iid, SLOT_NAME_BOX_BUTTON, btn, place_name_box_button,
        )

    def _clear_handler_to_pending(
        self, widget_id: str, event_key: str, m_idx: int, handler_entry,
    ) -> None:
        """First ✕ on a committed handler — drops the script binding via
        ``_delete_event_action`` and immediately re-adds a pending
        ``Add target…`` placeholder in its place, so the slot stays put
        and the user can re-pick. A second ✕ on the pending row removes
        it for good."""
        self._delete_event_action(widget_id, event_key, m_idx, handler_entry)
        self._add_pending_event_row(widget_id, event_key)

    def _attach_handler_function_box(
        self, row_iid: str, widget_id: str, event_key: str, m_idx: int,
        method_label: str, method_missing: str | None,
    ) -> None:
        """Boxed method value in the value column. Picking is on the ▾ only
        (no left-click here); right-click opens Delete / Edit and double-
        click opens the script. Red text when the method is unresolvable."""
        if self.overlays is None:
            return
        lbl = tk.Label(
            self.tree, text=method_label, bg=VALUE_BG,
            fg="#ef4444" if method_missing else TREE_FG,
            font=ui_font(11), anchor="w", padx=4, pady=0,
            borderwidth=0, highlightthickness=0, cursor="hand2",
        )
        lbl.bind(
            "<Button-3>",
            lambda e, wid=widget_id, k=event_key, i=m_idx:
            self._open_handler_function_menu(e, wid, k, i),
        )
        lbl.bind(
            "<Double-Button-1>",
            lambda _e, wid=widget_id, k=event_key, i=m_idx:
            self._open_handler_script(wid, k, i),
        )
        self.overlays.add(row_iid, SLOT_TEXT_VALUE, lbl, place_text_value)

    def _open_handler_target_menu(
        self, event, widget_id: str, event_key: str, m_idx: int, handler_entry,
    ) -> None:
        """Right-click on the target box — Delete (clear the script,
        reverting the row to a pending ``Add target…``) + Edit (open the
        script in the editor)."""
        from app.ui.properties_panel.constants import menu_style
        menu = tk.Menu(self.tree, tearoff=0, **menu_style())
        menu.add_command(
            label="Delete",
            command=lambda: self._clear_handler_to_pending(
                widget_id, event_key, m_idx, handler_entry),
        )
        menu.add_command(
            label="Edit",
            command=lambda: self._open_handler_script(
                widget_id, event_key, m_idx),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_handler_function_menu(
        self, event, widget_id: str, event_key: str, m_idx: int,
    ) -> None:
        """Right-click on the function box — Delete (clear the chosen
        method, back to ``Pick function…``) + Edit (open the script).
        Delete is disabled when no method is picked yet (nothing to
        clear) — there's nothing to delete on a ``Pick function…`` cell."""
        node = self.project.get_widget(widget_id)
        entries = (node.handlers.get(event_key, []) or []) if node else []
        entry = entries[m_idx] if m_idx < len(entries) else None
        has_method = bool(isinstance(entry, dict) and entry.get("method"))
        from app.ui.properties_panel.constants import menu_style
        menu = tk.Menu(self.tree, tearoff=0, **menu_style())
        if has_method:
            menu.add_command(
                label="Delete",
                command=lambda: self._clear_handler_method(
                    widget_id, event_key, m_idx),
            )
        else:
            # Inert dim item, NOT state="disabled" — Windows native menus
            # etch a 3D "ghost" on disabled entries (the "ჯადო" quirk), so
            # a grey foreground + no-op command + neutralised hover reads
            # cleanly. Nothing to delete until a function is picked.
            menu.add_command(
                label="Delete", command=lambda: None,
                foreground="#6a6a6a", activeforeground="#6a6a6a",
                activebackground="#2d2d30",
            )
        menu.add_command(
            label="Edit",
            command=lambda: self._open_handler_script(
                widget_id, event_key, m_idx),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _clear_handler_method(
        self, widget_id: str, event_key: str, m_idx: int,
    ) -> None:
        """Clear a handler's chosen method (back to ``Pick function…``)
        without touching the script target. Direct mutation + repaint,
        same no-undo policy as the function picker."""
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        entries = node.handlers.get(event_key)
        if entries is None or m_idx >= len(entries):
            return
        entry = entries[m_idx]
        if isinstance(entry, dict):
            entry["method"] = ""
        self.project.event_bus.publish(
            "widget_handler_changed", widget_id, event_key, "",
        )

    def _open_handler_script(
        self, widget_id: str, event_key: str, m_idx: int,
    ) -> None:
        """Open the script file backing a handler's target in the editor —
        used by the boxes' Edit menu item and double-click."""
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        entries = node.handlers.get(event_key, []) or []
        if m_idx >= len(entries):
            return
        entry = entries[m_idx]
        if not isinstance(entry, dict):
            return
        cls = entry.get("class", "")
        if not cls:
            return
        document = self.project.find_document_for_widget(widget_id)
        from app.io.scripts import resolve_script_component
        comp = resolve_script_component(
            node, document, cls, entry.get("scope"),
        )
        if comp:
            self._open_script_in_editor(comp.get("script", ""))

    def _target_label_for_entry(
        self, handler_entry, node,
    ) -> tuple[str, str, str | None, bool]:
        """Return ``(label_prefix, target_display,
        missing_reason_or_None, target_picked)``.

        ``label_prefix`` is the primary-column text — varies by
        target kind so the user reads the row as a category:

        * ``"Script:"`` — a resolved ``script_call`` entry (a method
          on an attached CTkScript).
        * ``"Target:"`` — pending placeholder (no target picked
          yet); the value cell carries the ``Add target`` prompt.

        ``target_picked`` controls whether the Function / param
        child rows render at all — ``False`` for the placeholder
        state.
        """
        if isinstance(handler_entry, dict) and (
            handler_entry.get("kind") == "script_call"
        ):
            cls = handler_entry.get("class", "")
            if not cls:
                return "Target:", "Add target", None, False
            scope = handler_entry.get("scope")
            if not _script_call_resolvable(self.project, node, cls, scope):
                return "Script:", cls, "script unavailable", True
            return "Script:", cls, None, True
        # Unknown legacy shape — render as an unpicked placeholder.
        return "Target:", "Add target", None, False

    def _method_and_params_for_entry(
        self, handler_entry,
    ) -> tuple[str, str | None, list[tuple[str, str]]]:
        """Return ``(method_display, missing_reason_or_None,
        [(param_name, param_value_text), ...])``. Empty-method
        entries (target picked, function not chosen yet) render
        with the ``Pick function…`` placeholder.
        """
        if isinstance(handler_entry, dict) and (
            handler_entry.get("kind") == "script_call"
        ):
            method = handler_entry.get("method", "")
            if not method:
                return "Pick function…", None, []
            return method, None, []
        return "Pick function…", None, []

    def _attach_event_add_button(
        self, header_iid: str, widget_id: str, event_key: str,
        dim: bool = False,
    ) -> None:
        """Inline ``[+]`` next to the event-header row preview.
        Click adds a pending "Add target" placeholder row; the
        target picker opens from THAT row's inner ``[+]`` rather
        than from this header button. Neutral colour (no accent blue);
        dimmer on empty events so it tracks the de-emphasised header.
        """
        rest = "#666666" if dim else "#999999"
        btn = tk.Label(
            self.tree,
            text="+", bg=TREE_BG, fg=rest,
            font=ui_font(11, "bold"),
            cursor="hand2", borderwidth=0, padx=0, pady=0,
        )
        btn.bind(
            "<Enter>",
            lambda _e, b=btn: b.configure(fg="#ffffff"),
        )
        btn.bind(
            "<Leave>",
            lambda _e, b=btn, c=rest: b.configure(fg=c),
        )
        btn.bind(
            "<Button-1>",
            lambda _e, wid=widget_id, k=event_key:
            self._add_pending_event_row(wid, k),
        )
        if self.overlays is not None:
            self.overlays.add(
                header_iid, SLOT_EVENT_ADD, btn, place_event_add,
            )

    def _attach_pending_target_box(
        self, row_iid: str, widget_id: str, event_key: str,
    ) -> None:
        """Empty "Add target…" box in the name column of a pending row —
        click opens the cascade target picker; picking commits the entry
        to ``handlers`` (and the row rebuilds as a real handler)."""
        if self.overlays is None:
            return
        lbl = tk.Label(
            self.tree, text="Add target…", bg=VALUE_BG, fg="#999999",
            font=ui_font(11), anchor="w", padx=4, pady=0,
            borderwidth=0, highlightthickness=0, cursor="hand2",
        )
        lbl._full_text = "Add target…"
        lbl.bind("<Enter>", lambda _e, b=lbl: b.configure(fg="#cccccc"))
        lbl.bind("<Leave>", lambda _e, b=lbl: b.configure(fg="#999999"))
        lbl.bind(
            "<Button-1>",
            lambda _e, wid=widget_id, k=event_key:
            self._open_pending_target_picker(wid, k),
        )
        self.overlays.add(row_iid, SLOT_NAME_BOX, lbl, place_name_box)

    def _attach_pending_cancel_button(
        self, row_iid: str, widget_id: str, event_key: str,
    ) -> None:
        """✕ at the right edge of a pending row's name column — discards
        the "Add target…" placeholder via ``_remove_pending_event_row``.
        No committed entry exists yet, so nothing else to undo."""
        if self.overlays is None:
            return
        btn = tk.Label(
            self.tree, text="✕", bg=VALUE_BG, fg="#888888",
            font=ui_font(9), cursor="hand2", borderwidth=0, padx=0, pady=0,
        )
        btn.bind("<Enter>", lambda _e, b=btn: b.configure(fg="#ef4444"))
        btn.bind("<Leave>", lambda _e, b=btn: b.configure(fg="#888888"))
        btn.bind(
            "<Button-1>",
            lambda _e, wid=widget_id, k=event_key:
            self._remove_pending_event_row(wid, k),
        )
        self.overlays.add(
            row_iid, SLOT_NAME_BOX_CLEAR, btn, place_name_clear_left,
        )

    def _attach_disabled_function_box(self, row_iid: str) -> None:
        """Dark, non-clickable "Pick function…" box + dim ▾ in the value
        column of a pending row. Shows the two-column shape before a
        target is picked, while reading as not-yet-available — the
        function side only lights up once the target commits."""
        if self.overlays is None:
            return
        lbl = tk.Label(
            self.tree, text="Pick function…", bg="#262626", fg="#5a5a5a",
            font=ui_font(11), anchor="w", padx=4, pady=0,
            borderwidth=0, highlightthickness=0,
        )
        self.overlays.add(row_iid, SLOT_TEXT_VALUE, lbl, place_text_value)
        arrow = tk.Label(
            self.tree, text="▾", bg="#262626", fg="#5a5a5a",
            font=ui_font(12, "bold"), borderwidth=0,
        )
        self.overlays.add(
            row_iid, SLOT_EVENT_DROPDOWN, arrow, place_enum_button,
        )

    def _attach_target_dropdown_button(
        self, parent_iid: str, widget_id: str,
        event_key: str, m_idx: int,
    ) -> None:
        """``▾`` dropdown on a committed handler entry's parent row
        — opens the target retarget picker (same Page Script /
        Object References cascade the outer ``[+]`` uses, but
        replacing the entry's target in place rather than appending
        a new one). Sits left of the row's ``[✕]`` button via the
        offset ``place_event_dropdown`` placer.
        """
        btn = tk.Label(
            self.tree,
            text="▾", bg=TREE_BG, fg="#aaaaaa",
            font=ui_font(12, "bold"),
            cursor="hand2", borderwidth=0,
        )
        btn.bind(
            "<Enter>",
            lambda _e, b=btn: b.configure(fg="#ffffff"),
        )
        btn.bind(
            "<Leave>",
            lambda _e, b=btn: b.configure(fg="#aaaaaa"),
        )
        btn.bind(
            "<Button-1>",
            lambda _e, wid=widget_id, k=event_key, i=m_idx:
            self._open_target_retarget_picker(wid, k, i),
        )
        if self.overlays is not None:
            self.overlays.add(
                parent_iid, SLOT_EVENT_DROPDOWN,
                btn, place_event_dropdown,
            )

    def _attach_function_dropdown_button(
        self, function_iid: str, widget_id: str,
        event_key: str, m_idx: int,
    ) -> None:
        """``▾`` function picker at the right edge of the handler row's
        value cell. Sits on the VALUE_BG fill so it reads as its own box
        beside the boxed method value — the [ method ] … [ ▾ ] rhythm,
        matching the script-variable / Cursor rows.
        """
        btn = tk.Label(
            self.tree,
            text="▾", bg=VALUE_BG, fg="#aaaaaa",
            font=ui_font(12, "bold"),
            cursor="hand2", borderwidth=0,
        )
        btn.bind(
            "<Enter>",
            lambda _e, b=btn: b.configure(fg="#ffffff"),
        )
        btn.bind(
            "<Leave>",
            lambda _e, b=btn: b.configure(fg="#aaaaaa"),
        )
        btn.bind(
            "<Button-1>",
            lambda _e, wid=widget_id, k=event_key, i=m_idx:
            self._open_function_picker(wid, k, i),
        )
        if self.overlays is not None:
            self.overlays.add(
                function_iid, SLOT_EVENT_DROPDOWN,
                btn, place_enum_button,
            )

    def _attach_event_unbind_button(
        self, method_iid: str, widget_id: str,
        event_key: str, index: int, method_name: str,
    ) -> None:
        """Inline ``[✕]`` on bound-method rows — direct unbind via
        ``_delete_event_action``. No confirmation dialog: the
        behavior file's ``def`` is untouched, so re-binding restores
        the entry without losing user code.
        """
        btn = tk.Label(
            self.tree,
            text="✕", bg=TREE_BG, fg="#888888",
            font=ui_font(9),
            cursor="hand2", borderwidth=0, padx=0, pady=0,
        )
        btn.bind(
            "<Enter>",
            lambda _e, b=btn: b.configure(fg="#ef4444"),
        )
        btn.bind(
            "<Leave>",
            lambda _e, b=btn: b.configure(fg="#888888"),
        )
        btn.bind(
            "<Button-1>",
            lambda _e, wid=widget_id, k=event_key,
            i=index, m=method_name:
            self._delete_event_action(wid, k, i, m),
        )
        if self.overlays is not None:
            self.overlays.add(
                method_iid, SLOT_EVENT_UNBIND, btn, place_event_unbind,
            )

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
        # Color rows are the exception: a small swatch sits to the
        # left of the ✕ unbind button so the picker-edits-variable
        # flow stays discoverable on bound rows.
        if chip is None:
            get_editor(ptype).populate(self, iid, pname, prop, value)
        elif ptype == "color":
            get_editor(ptype).populate_bound(self, iid, pname)

        # Interaction-group text rows wear the boxed-value look (matches
        # the script-variable / Scripts rows): the value sits in a
        # VALUE_BG box and the dropdown reads as a separate button at the
        # right edge — [ value ] … [ ▾ ]. Booleans (checkbox) / colours
        # (swatch) keep their own editors, so only the text rows qualify.
        if chip is None and self._is_boxed_value_prop(prop):
            self._add_boxed_value_overlay(iid, pname, ptype, display)

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

    def _is_boxed_value_prop(self, prop: dict) -> bool:
        """True for rows that render their value in a VALUE_BG box (the
        script-variable / Scripts look) instead of plain cell text.
        Applies to every enum-family row — a text value + ▾ dropdown
        (cursor / anchor / justify / compound / wrap / …) — so they all
        read as ``[ value ] … [ ▾ ]`` consistently across widgets."""
        from .editors.enum import EnumEditor
        return isinstance(get_editor(prop["type"]), EnumEditor)

    def _add_boxed_value_overlay(
        self, iid: str, pname: str, ptype: str, display: str,
    ) -> None:
        """Render an enum-family value inside a VALUE_BG box so the row
        reads as ``[ value ] … [ ▾ ]``. Clears the native cell text (the
        overlay carries the value; _refresh_cell keeps it in sync) and
        tints the dropdown button to match the box. Dimmed when the row's
        ``disabled_when`` is active (e.g. Icon Side with no image)."""
        if self.overlays is None:
            return
        self.tree.set(iid, "value", "")
        disabled = bool(self._disabled_states.get(pname))
        # Tint the dropdown button so it reads as its own box beside the
        # value — mirrors the variable row's value + 🔗 pairing.
        btn = self.overlays.get(iid, SLOT_ENUM_BUTTON)
        if btn is not None:
            try:
                btn.configure(bg=VALUE_BG)
            except tk.TclError:
                pass
        lbl = tk.Label(
            self.tree, text=display, bg=VALUE_BG,
            fg=DISABLED_FG if disabled else TREE_FG,
            font=ui_font(11), anchor="w", padx=4, pady=0,
            borderwidth=0, highlightthickness=0, cursor="hand2",
        )
        lbl.bind(
            "<Button-1>",
            lambda _e, p=pname, t=ptype, w=lbl: self._popup_enum_menu_at(
                p, t, w.winfo_rootx(), w.winfo_rooty() + w.winfo_height()),
        )
        self.overlays.add(iid, SLOT_TEXT_VALUE, lbl, place_text_value)
        self._boxed_value_iids.add(iid)

    def _refresh_cell(self, iid: str, prop: dict, value) -> None:
        ptype = prop["type"]
        chip = _binding_chip_text(self.project, value)
        display = chip if chip is not None else format_value(
            ptype, value, prop,
        )
        # Boxed Interaction values live in a VALUE_BG overlay label, not
        # the native cell text — update the label and keep the cell empty.
        if iid in self._boxed_value_iids and chip is None:
            lbl = (
                self.overlays.get(iid, SLOT_TEXT_VALUE)
                if self.overlays is not None else None
            )
            if lbl is not None:
                try:
                    lbl.configure(text=display)
                except tk.TclError:
                    pass
            display = ""
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
        """Disable geometry fields for managed-layout children based on
        the parent's layout manager + the child's ``stretch`` setting:

        - ``place`` parent — no override; user owns x/y/width/height.
        - ``grid`` parent — placement is grid-cell driven; disable
          x/y/width/height across the board (per-cell sizing replaces
          per-widget sizing).
        - ``vbox`` / ``hbox`` parent — disable x/y always; width/height
          per-stretch (v1.10.2):
            - ``fixed``: nothing extra disabled — user controls W and H.
            - ``fill``: cross axis disabled (auto-fills the parent).
              hbox → height disabled; vbox → width disabled.
            - ``grow``: main axis owned by ``rebalance_pack_siblings``,
              cross axis filled by pack — both disabled.
        """
        from app.widgets.layout_schema import normalise_layout_type
        if node is None or node.parent is None:
            return
        parent_layout = normalise_layout_type(
            node.parent.properties.get("layout_type", "place"),
        )
        if parent_layout == "place":
            return
        # grid: legacy behavior — disable everything geometry-related.
        if parent_layout == "grid":
            for field in ("x", "y", "width", "height"):
                self._disabled_states[field] = True
            return
        # vbox / hbox: x/y always managed by pack, never user-editable.
        for field in ("x", "y"):
            self._disabled_states[field] = True
        stretch = str(node.properties.get("stretch", "fixed"))
        main_axis = "width" if parent_layout == "hbox" else "height"
        cross_axis = "height" if parent_layout == "hbox" else "width"
        if stretch == "grow":
            self._disabled_states[main_axis] = True
            self._disabled_states[cross_axis] = True
        elif stretch == "fill":
            self._disabled_states[cross_axis] = True
        # stretch == "fixed" — leave both W/H editable; user owns both.

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
        # Boxed enum value label dims with the row (its ▾ is handled by
        # the editor's set_disabled above).
        if iid in self._boxed_value_iids and self.overlays is not None:
            lbl = self.overlays.get(iid, SLOT_TEXT_VALUE)
            if lbl is not None:
                try:
                    lbl.configure(fg=DISABLED_FG if disabled else TREE_FG)
                except tk.TclError:
                    pass
