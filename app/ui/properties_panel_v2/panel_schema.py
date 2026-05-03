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
    SLOT_BEHAVIOR_CLEAR,
    SLOT_BEHAVIOR_FIELD_ADD,
    SLOT_BEHAVIOR_PICK,
    SLOT_BIND_BUTTON,
    SLOT_BIND_CLEAR,
    SLOT_EVENT_ADD,
    SLOT_EVENT_UNBIND,
    place_behavior_field_add,
    place_behavior_field_clear,
    place_behavior_field_pick,
    place_bind_button,
    place_bind_clear,
    place_event_add,
    place_event_unbind,
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

        # Window selection: append a read-only "Local Variables" group
        # at the very end so the user can see what locals belong to the
        # current document without opening the F11 Variables window.
        if descriptor.type_name == WINDOW_ID:
            self._populate_local_variables_group()

        # Phase 2 visual scripting — Events group for event-capable
        # widgets (button, slider, entry, …). Renders below every
        # property group; event-less widgets (Label, Frame, Image)
        # skip it entirely so their panels stay tidy.
        if node is not None:
            self._populate_events_group(node)

        # Phase 3 — Behavior Fields render on every selection so the
        # user can pick widgets for the window's Inspector slots from
        # any panel they happen to be viewing. The slots are class-
        # level on the window's behavior file (one class per window),
        # but exposing them on every widget panel matters for
        # discoverability — users tend to live on widget panels and
        # rarely click the window background. Position itself right
        # after the Events group when present so the visual rhythm
        # mirrors Unity's "events first, references next" Inspector
        # layout.
        self._populate_behavior_fields_group()

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
        for entry in locals_list:
            default_str = str(entry.default or "")
            if len(default_str) > 30:
                default_str = default_str[:29] + "…"
            self.tree.insert(
                group_iid, "end", iid=f"localvar:{entry.id}",
                text=entry.name,
                values=(f"({entry.type}) {default_str}",),
            )

    def _populate_behavior_fields_group(self) -> None:
        """Phase 3 visual scripting — render the active document's
        Behavior Field slots in a dedicated group. Visible on every
        selection (widget OR window) since the slots themselves are
        class-level on the window's behavior file but the picker
        affordance benefits from being reachable from any panel.

        Each ``<name>: ref[<WidgetType>]`` annotation becomes one row
        whose value cell shows the bound widget's name and a
        ``[Pick…]`` button that opens the modal widget picker.

        Empty state (no annotations declared yet) shows a one-line
        hint pointing at the syntax users add to their behavior file.

        Position: hoists the group right after the Events group when
        present so it sits visually close to the other Phase 2/3
        scripting affordances. Falls back to end-of-tree when the
        Events group is absent (Window panel, or widgets without
        events like Label / Frame / Image).
        """
        doc = self.project.active_document if self.project else None
        if doc is None:
            return
        group_iid = "g:Behavior Fields"
        self.tree.insert(
            "", "end", iid=group_iid,
            text="Behavior Fields", values=("",), open=True,
            tags=("class",),
        )
        # Inline ``[+]`` lets the user create a field via the Add
        # Behavior Field dialog instead of editing the .py source
        # by hand. Routed through the panel layer so the dialog +
        # the SetBehaviorFieldCommand push live next to the rest of
        # the Phase 3 surface.
        self._attach_behavior_field_add_button(group_iid)
        fields = self._lookup_behavior_fields(doc)
        if not fields:
            self.tree.insert(
                group_iid, "end", iid="behaviorfield:empty",
                text="",
                values=("declare `name: ref[Type]` in behavior file",),
                tags=("disabled",),
            )
        else:
            values = doc.behavior_field_values
            for spec in fields:
                current_id = values.get(spec.name, "")
                current_widget = (
                    self.project.get_widget(current_id)
                    if current_id else None
                )
                if current_widget is not None:
                    widget_label = (
                        current_widget.name or current_widget.widget_type
                    )
                    # Compatibility check — if the user changed the
                    # field's type in the .py source after binding,
                    # surface the mismatch in the cell text rather
                    # than silently carrying on with the stale id.
                    if current_widget.widget_type != spec.type_name:
                        value_text = (
                            f"{widget_label}  — wrong type "
                            f"({current_widget.widget_type})"
                        )
                    else:
                        value_text = widget_label
                elif current_id:
                    value_text = "(missing widget)"
                else:
                    value_text = f"empty   ref[{spec.type_name}]"
                row_iid = f"behaviorfield:{spec.name}"
                self.tree.insert(
                    group_iid, "end", iid=row_iid,
                    text=spec.name, values=(value_text,),
                )
                self._attach_behavior_field_pick_button(
                    row_iid, spec.name, spec.type_name,
                )
                if current_id:
                    self._attach_behavior_field_clear_button(
                        row_iid, spec.name,
                    )

        # Hoist right after the Events group when present — keeps the
        # scripting-related groups adjacent so the panel reads as a
        # single "behavior" cluster. Events group iid is "events:group"
        # (set in ``_populate_events_group``); when no Events exist,
        # leave Behavior Fields at its natural end-of-list position so
        # it still appears below the regular property groups.
        if not self.tree.exists("events:group"):
            return
        anchor_index = self.tree.index("events:group")
        self.tree.move(group_iid, "", anchor_index + 1)

    def _lookup_behavior_fields(self, doc) -> list:
        """Build the FieldSpec list for the active document's behavior
        class. Empty when the project is unsaved, the file is missing,
        or the class isn't found — those map naturally onto the
        "no fields" empty state.
        """
        if not getattr(self.project, "path", None):
            return []
        from app.core.script_paths import (
            behavior_class_name, behavior_file_path,
        )
        from app.io.scripts import parse_behavior_class_fields
        file_path = behavior_file_path(self.project.path, doc)
        if file_path is None or not file_path.exists():
            return []
        return parse_behavior_class_fields(
            file_path, behavior_class_name(doc),
        )

    def _attach_behavior_field_add_button(self, header_iid: str) -> None:
        """Inline ``[+]`` next to the Behavior Fields group header.
        Click delegates to ``_show_add_behavior_field_dialog`` on
        the panel — that runs the picker dialog, writes the new
        annotation + missing imports to the behavior file, and
        pushes the binding command.
        """
        btn = tk.Label(
            self.tree,
            text="+", bg=TREE_BG, fg="#7dd3fc",
            font=("Segoe UI", 11, "bold"),
            cursor="hand2", borderwidth=0, padx=0, pady=0,
        )
        btn.bind(
            "<Enter>",
            lambda _e, b=btn: b.configure(fg="#ffffff"),
        )
        btn.bind(
            "<Leave>",
            lambda _e, b=btn: b.configure(fg="#7dd3fc"),
        )
        btn.bind(
            "<Button-1>",
            lambda _e: self._show_add_behavior_field_dialog(),
        )
        if self.overlays is not None:
            self.overlays.add(
                header_iid, SLOT_BEHAVIOR_FIELD_ADD, btn,
                place_behavior_field_add,
            )

    def _attach_behavior_field_pick_button(
        self, row_iid: str, field_name: str, type_name: str,
    ) -> None:
        """Inline ``[Pick…]`` button on a Behavior Field row. Routes
        through ``_show_behavior_field_picker`` on the panel which
        opens the modal picker, applies the resulting widget id via
        ``SetBehaviorFieldCommand``, and triggers a panel rebuild via
        the ``behavior_field_changed`` event subscription.
        """
        btn = tk.Label(
            self.tree,
            text="Pick…", bg=TREE_BG, fg="#7dd3fc",
            font=("Segoe UI", 9),
            cursor="hand2", borderwidth=0, padx=2, pady=0,
        )
        btn.bind(
            "<Enter>",
            lambda _e, b=btn: b.configure(fg="#ffffff"),
        )
        btn.bind(
            "<Leave>",
            lambda _e, b=btn: b.configure(fg="#7dd3fc"),
        )
        btn.bind(
            "<Button-1>",
            lambda _e, fn=field_name, tn=type_name:
            self._show_behavior_field_picker(fn, tn),
        )
        if self.overlays is not None:
            self.overlays.add(
                row_iid, SLOT_BEHAVIOR_PICK, btn,
                place_behavior_field_pick,
            )

    def _attach_behavior_field_clear_button(
        self, row_iid: str, field_name: str,
    ) -> None:
        """Inline ``[✕]`` to clear an existing Behavior Field binding.
        Hidden on empty slots — the empty value cell + Pick… button
        is enough surface area; ``[✕]`` would just be visual noise.
        """
        btn = tk.Label(
            self.tree,
            text="✕", bg=TREE_BG, fg="#888888",
            font=("Segoe UI", 9),
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
            lambda _e, fn=field_name:
            self._clear_behavior_field(fn),
        )
        if self.overlays is not None:
            self.overlays.add(
                row_iid, SLOT_BEHAVIOR_CLEAR, btn,
                place_behavior_field_clear,
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

        The group inserts at the end of the walk and then re-positions
        right after the ``Colors`` group when that group exists —
        events sit conceptually closer to the visual styling rows
        than to the trailing layout / state knobs, so this placement
        matches the order the user reads the panel.
        """
        from app.widgets.event_registry import events_for
        events = events_for(node.widget_type)
        if not events:
            return
        # Resolve docstrings once per panel rebuild so each method
        # row can show a human description when one is available.
        # Empty when the project is unsaved / the behavior file is
        # missing / the class can't be found — bare method names
        # render fine in those cases.
        docs = self._lookup_handler_docstrings(node)
        # Phase 3 — set of method names that actually exist as
        # ``def`` statements on the per-window class. Method rows
        # whose name isn't in this set get the ``missing_method``
        # tag + a ``❌`` prefix so orphan bindings show up before
        # the user hits F5. Empty set means "couldn't scan" —
        # treated as "all bindings allowed" so unsaved projects /
        # missing files render the same as before.
        existing_methods = self._lookup_existing_method_names(node)
        scanned_existing = existing_methods is not None
        group_iid = "events:group"
        self.tree.insert(
            "", "end", iid=group_iid,
            text="Events", values=("",), open=True,
            tags=("class",),
        )
        meta = self._event_row_meta
        meta[group_iid] = ("group", "", None)
        widget_id = node.id
        for ev_idx, entry in enumerate(events):
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
            self.tree.insert(
                group_iid, "end", iid=header_iid,
                text=label, values=(preview,), open=True,
                tags=("group",),
            )
            meta[header_iid] = ("header", entry.key, None)
            self._attach_event_add_button(
                header_iid, widget_id, entry.key,
            )
            for m_idx, method in enumerate(methods):
                method_iid = f"events:m:{ev_idx}:{m_idx}"
                # Docstring (when the user wrote one) reads as the
                # primary label. Otherwise we surface ``Action N`` —
                # the auto-generated ``on_button_click_3`` method
                # name carries no useful information for someone
                # browsing the panel and reads as visual noise. The
                # bare method name still lives on disk; the user
                # sees it in the editor when they jump there.
                doc_text = docs.get(method)
                if doc_text:
                    row_label = doc_text
                else:
                    row_label = f"Action {m_idx + 1}"
                missing = (
                    scanned_existing
                    and method not in (existing_methods or set())
                )
                # ``❌`` glyph + red row tag for orphan bindings —
                # method name is recorded on the model but the
                # behavior file's class doesn't define it. Caught
                # here so the user spots the break in the panel
                # before F5 surfaces it as an AttributeError.
                if missing:
                    row_label = f"❌ {row_label}"
                    value_text = f"{method} (missing in file)"
                    row_tags: tuple[str, ...] = ("missing_method",)
                else:
                    value_text = method
                    row_tags = ()
                # Method name in the value column as quiet metadata —
                # useful when the user can't remember which action
                # is which, but stays out of the primary label.
                self.tree.insert(
                    header_iid, "end", iid=method_iid,
                    text=row_label, values=(value_text,),
                    tags=row_tags,
                )
                meta[method_iid] = ("method", entry.key, m_idx)
                self._attach_event_unbind_button(
                    method_iid, widget_id, entry.key, m_idx, method,
                )

        # Hoist the Events group up to live right after the LAST
        # group whose name contains "Color" (CTkButton uses
        # "Main Colors", CTkComboBox has "Main Colors" + "Dropdown
        # Colors", etc. — the events sit conceptually closest to the
        # final colour batch). When no colour-related group exists,
        # leave Events at its natural end-of-list position.
        anchor_iid: str | None = None
        for child_iid in self.tree.get_children(""):
            text = self.tree.item(child_iid, "text") or ""
            if "color" in text.lower():
                anchor_iid = child_iid
        if anchor_iid is None:
            return
        anchor_index = self.tree.index(anchor_iid)
        self.tree.move(group_iid, "", anchor_index + 1)

    def _lookup_existing_method_names(self, node) -> set[str] | None:
        """Phase 3 — return the set of method names defined on the
        widget's per-window behavior class, used to flag orphan
        bindings in ``_populate_events_group``. ``None`` when we
        can't reach the file (unsaved project / missing .py / class
        not found) — caller treats that as "skip the orphan check"
        so legacy projects without behavior files render identically
        to the pre-Phase-3 build.
        """
        if not getattr(self.project, "path", None):
            return None
        document = self.project.find_document_for_widget(node.id)
        if document is None:
            return None
        from app.core.script_paths import (
            behavior_class_name, behavior_file_path,
        )
        from app.io.scripts import parse_handler_methods
        file_path = behavior_file_path(self.project.path, document)
        if file_path is None or not file_path.exists():
            return None
        return set(parse_handler_methods(
            file_path, behavior_class_name(document),
        ))

    def _lookup_handler_docstrings(self, node) -> dict[str, str]:
        """Build a ``{method_name: first_docstring_line}`` map for the
        node's window's behavior class. Empty when the project is
        unsaved, the behavior file is missing, or the class isn't
        found. Used by ``_populate_events_group`` to label each
        method row with the user's own description.
        """
        if not getattr(self.project, "path", None):
            return {}
        document = self.project.find_document_for_widget(node.id)
        if document is None:
            return {}
        from app.core.script_paths import (
            behavior_class_name, behavior_file_path,
        )
        from app.io.scripts import parse_method_docstrings
        file_path = behavior_file_path(self.project.path, document)
        if file_path is None or not file_path.exists():
            return {}
        return parse_method_docstrings(
            file_path, behavior_class_name(document),
        )

    def _attach_event_add_button(
        self, header_iid: str, widget_id: str, event_key: str,
    ) -> None:
        """Inline ``[+]`` next to the event-header row preview.
        Click delegates to ``_add_event_action`` (same path the
        right-click "Add action" entry uses) so the cascade flow
        stays single-source.
        """
        btn = tk.Label(
            self.tree,
            text="+", bg=TREE_BG, fg="#7dd3fc",
            font=("Segoe UI", 11, "bold"),
            cursor="hand2", borderwidth=0, padx=0, pady=0,
        )
        btn.bind(
            "<Enter>",
            lambda _e, b=btn: b.configure(fg="#ffffff"),
        )
        btn.bind(
            "<Leave>",
            lambda _e, b=btn: b.configure(fg="#7dd3fc"),
        )
        btn.bind(
            "<Button-1>",
            lambda _e, wid=widget_id, k=event_key:
            self._add_event_action(wid, k),
        )
        if self.overlays is not None:
            self.overlays.add(
                header_iid, SLOT_EVENT_ADD, btn, place_event_add,
            )

    def _attach_event_unbind_button(
        self, method_iid: str, widget_id: str,
        event_key: str, index: int, method_name: str,
    ) -> None:
        """Inline ``[✕]`` on bound-method rows. Routes through the
        same ``_delete_event_action`` flow as the right-click
        "Delete action…" entry so the user sees the
        ``ActionDeleteDialog`` (Cancel / Open in editor / Delete)
        regardless of which surface they clicked.
        """
        btn = tk.Label(
            self.tree,
            text="✕", bg=TREE_BG, fg="#888888",
            font=("Segoe UI", 9),
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
