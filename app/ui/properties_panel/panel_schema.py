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
    SLOT_EVENT_ADD,
    SLOT_EVENT_UNBIND,
    SLOT_OBJECT_REFERENCE_TOGGLE,
    place_bind_button,
    place_bind_clear,
    place_event_add,
    place_event_unbind,
    place_object_reference_toggle,
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
            # v1.10.8 — symmetric per-Window global toggle. Mirrors
            # the per-widget local toggle: ``+`` creates a global
            # reference whose target is this Window/Dialog itself;
            # ``×`` removes it. Behavior code from any doc reaches
            # the window class through ``self.<name>``. Sits with the
            # schema-side window properties — it describes how the
            # window itself is exposed, not user-declared content.
            self._populate_window_global_reference_toggle()
            # Spacer separates the trailing declarations block (locals
            # + references list) from the window-property block above
            # so the user reads them as a distinct zone.
            self._insert_section_spacer()
            self._populate_local_variables_group()
            # Local refs of this doc — read-only list.
            self._populate_object_references_group()

        # Phase 2 visual scripting — Events group for event-capable
        # widgets (button, slider, entry, …). Renders below every
        # property group; event-less widgets (Label, Frame, Image)
        # skip it entirely so their panels stay tidy.
        if node is not None:
            self._populate_events_group(node)

        # v1.10.8 — per-widget Object Reference toggle. Replaces the
        # ``Behavior Fields`` group from v1.10.7 with a one-row
        # status + button: "this widget is/is not exposed as a
        # reference; click to toggle". Window panel skips this since
        # it shows the consolidated list above.
        if node is not None and node.id != WINDOW_ID:
            self._populate_object_reference_toggle(node)

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
        for entry in locals_list:
            default_str = str(entry.default or "")
            if len(default_str) > 30:
                default_str = default_str[:29] + "…"
            self.tree.insert(
                group_iid, "end", iid=f"localvar:{entry.id}",
                text=entry.name,
                values=(f"({entry.type}) {default_str}",),
            )

    def _populate_object_references_group(self) -> None:
        """v1.10.8 — read-only Object References list on Window panel.
        Shows every LOCAL reference of the active document. Globals
        live on the F11 Object References tab and the per-window
        toggle row above (a window-as-global is a separate concept
        that doesn't belong in this list).
        """
        doc = self.project.active_document if self.project else None
        if doc is None:
            return
        group_iid = "g:Object References"
        self.tree.insert(
            "", "end", iid=group_iid,
            text="Object References", values=("",), open=True,
            tags=("class",),
        )
        local_refs = list(doc.local_object_references or [])
        if not local_refs:
            self.tree.insert(
                group_iid, "end", iid="objref:empty",
                text="",
                values=("no references — toggle from a widget panel",),
                tags=("disabled",),
            )
            return
        from app.core.object_references import short_type_label
        for entry in local_refs:
            target_label = self._object_ref_target_label(entry)
            self.tree.insert(
                group_iid, "end",
                iid=f"objref:l:{entry.id}",
                text=entry.name,
                values=(
                    f"({short_type_label(entry.target_type)})  "
                    f"→  {target_label}",
                ),
            )

    def _populate_window_global_reference_toggle(self) -> None:
        """v1.10.8 — per-Window toggle row. Creates / removes a
        global Object Reference whose target is the active document
        itself. ``+`` makes the window callable from any doc's
        behavior code via ``self.<name>``; ``×`` removes the ref.
        """
        if self.project is None:
            return
        doc = self.project.active_document
        if doc is None:
            return
        group_iid = "g:Object Reference"
        self.tree.insert(
            "", "end", iid=group_iid,
            text="Object Reference", values=("",), open=True,
            tags=("class",),
        )
        existing_entry = None
        for entry in self.project.object_references or []:
            if entry.target_id == doc.id:
                existing_entry = entry
                break
        row_iid = f"objref_toggle:doc:{doc.id}"
        if existing_entry is None:
            self.tree.insert(
                group_iid, "end", iid=row_iid,
                text="Reference",
                values=("",),
            )
            self._attach_window_global_make_button(row_iid, doc)
        else:
            self.tree.insert(
                group_iid, "end", iid=row_iid,
                text="Reference",
                values=(existing_entry.name,),
            )
            self._attach_object_reference_remove_button(
                row_iid, existing_entry.id,
            )

    def _attach_window_global_make_button(self, row_iid: str, doc) -> None:
        """``+`` button on the Window toggle row. Click promotes the
        active document to a global Object Reference. Style mirrors
        the per-widget Make button.
        """
        btn = tk.Label(
            self.tree,
            text="+",
            bg="#0e639c", fg="#ffffff",
            font=derive_ui_font(size=12, weight="bold"),
            cursor="hand2", borderwidth=0, padx=0, pady=0,
            anchor="center",
        )
        btn.bind(
            "<Enter>",
            lambda _e, b=btn: b.configure(bg="#1177bb"),
        )
        btn.bind(
            "<Leave>",
            lambda _e, b=btn: b.configure(bg="#0e639c"),
        )
        btn.bind(
            "<Button-1>",
            lambda _e, d=doc: self._make_window_global_reference(d),
        )
        if self.overlays is not None:
            self.overlays.add(
                row_iid, SLOT_OBJECT_REFERENCE_TOGGLE, btn,
                place_object_reference_toggle,
            )

    def _populate_object_reference_toggle(self, node) -> None:
        """v1.10.8 — per-widget toggle row. Shows whether the selected
        widget is currently exposed as a local Object Reference and
        offers a one-click Make / Remove button.
        """
        doc = self.project.active_document if self.project else None
        if doc is None:
            return
        group_iid = "g:Object Reference"
        self.tree.insert(
            "", "end", iid=group_iid,
            text="Object Reference", values=("",), open=True,
            tags=("class",),
        )
        # Find any local ref whose target_id matches this widget.
        existing_entry = None
        for entry in doc.local_object_references or []:
            if entry.target_id == node.id:
                existing_entry = entry
                break
        row_iid = f"objref_toggle:{node.id}"
        if existing_entry is None:
            self.tree.insert(
                group_iid, "end", iid=row_iid,
                text="Reference",
                values=("",),
            )
            self._attach_object_reference_make_button(row_iid, node)
        else:
            self.tree.insert(
                group_iid, "end", iid=row_iid,
                text="Reference",
                values=(existing_entry.name,),
            )
            self._attach_object_reference_remove_button(
                row_iid, existing_entry.id,
            )
        # Hoist right after the Events group when present.
        if not self.tree.exists("events:group"):
            return
        anchor_index = self.tree.index("events:group")
        self.tree.move(group_iid, "", anchor_index + 1)

    def _object_ref_target_label(self, entry) -> str:
        """Resolve the display name of a reference's target. Local
        refs point at widgets; globals point at documents. Empty
        target_id renders as ``(unbound)``; a stale id renders as
        ``(missing)`` so the user spots the dangling slot.
        """
        if not entry.target_id:
            return "(unbound)"
        if entry.scope == "global":
            doc = self.project.get_document(entry.target_id)
            return doc.name if doc is not None else "(missing)"
        widget = self.project.get_widget(entry.target_id)
        if widget is None:
            return "(missing)"
        return widget.name or widget.widget_type

    def _attach_object_reference_make_button(
        self, row_iid: str, node,
    ) -> None:
        """Inline ``[ + Make Reference ]`` button on the toggle row.
        Click promotes the widget to a local Object Reference.
        """
        btn = tk.Label(
            self.tree,
            text="+",
            bg="#0e639c", fg="#ffffff",
            font=derive_ui_font(size=12, weight="bold"),
            cursor="hand2", borderwidth=0, padx=0, pady=0,
            anchor="center",
        )
        btn.bind(
            "<Enter>",
            lambda _e, b=btn: b.configure(bg="#1177bb"),
        )
        btn.bind(
            "<Leave>",
            lambda _e, b=btn: b.configure(bg="#0e639c"),
        )
        btn.bind(
            "<Button-1>",
            lambda _e, n=node: self._make_object_reference(n),
        )
        if self.overlays is not None:
            self.overlays.add(
                row_iid, SLOT_OBJECT_REFERENCE_TOGGLE, btn,
                place_object_reference_toggle,
            )

    def _attach_object_reference_remove_button(
        self, row_iid: str, ref_id: str,
    ) -> None:
        """Inline ``[×]`` (red) button on the toggle row when the
        widget IS already a reference. Click drops the reference +
        its ``ref[Type]`` annotation in the behavior file.
        """
        btn = tk.Label(
            self.tree,
            text="×",
            bg="#a33d3d", fg="#ffffff",
            font=derive_ui_font(size=12, weight="bold"),
            cursor="hand2", borderwidth=0, padx=0, pady=0,
            anchor="center",
        )
        btn.bind(
            "<Enter>",
            lambda _e, b=btn: b.configure(bg="#c94545"),
        )
        btn.bind(
            "<Leave>",
            lambda _e, b=btn: b.configure(bg="#a33d3d"),
        )
        btn.bind(
            "<Button-1>",
            lambda _e, rid=ref_id: self._remove_object_reference(rid),
        )
        if self.overlays is not None:
            self.overlays.add(
                row_iid, SLOT_OBJECT_REFERENCE_TOGGLE, btn,
                place_object_reference_toggle,
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
                ev_idx, entry, group_iid, node, docs,
                existing_methods, scanned_existing, widget_id, meta,
            )
        for entry in advanced_events:
            parent_iid = _ensure_advanced_group()
            ev_idx = self._render_event_row(
                ev_idx, entry, parent_iid, node, docs,
                existing_methods, scanned_existing, widget_id, meta,
            )

    def _render_event_row(
        self, ev_idx: int, entry, parent_iid: str, node, docs: dict,
        existing_methods, scanned_existing: bool, widget_id: str, meta: dict,
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
        self.tree.insert(
            parent_iid, "end", iid=header_iid,
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
        return ev_idx + 1

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
            font=ui_font(11, "bold"),
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
