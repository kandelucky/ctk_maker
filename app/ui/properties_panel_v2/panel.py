"""Properties panel v2 — ttk.Treeview-based implementation.

Phase 1 port of the `tools/ctk_button_treeview_mock.py` prototype
to the real builder. Uses a single `ttk.Treeview` as the backbone
(same pattern as `app/ui/object_tree_window.py`) plus thin overlays
for editors that can't be text-only:

    - Inline `tk.Entry` overlay on double-click for number / multiline
    - `tk.Frame` color swatches persistently overlaid on color rows
    - Native `tk.Menu` popup for anchor / compound enums
    - Unicode checkboxes (☑ / ☐) for bools + `bool_off` tag graying

After Phase A refactor this class lives inside the
`app.ui.properties_panel_v2` package. Pure helpers (formatting,
enum options, value coercion) moved to `format_utils`; shared
constants to `constants`; widget-type icon lookup to `type_icons`.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk

import customtkinter as ctk

from ctk_color_picker import ColorPickerDialog

from app.core.commands import ChangePropertyCommand, RenameCommand
from app.core.logger import log_error
from app.core.project import Project
from app.ui.icons import load_icon
from app.widgets.registry import get_descriptor
from tools.text_editor_dialog import TextEditorDialog

from .constants import (
    ANCHOR_LABEL_TO_CODE,
    BG,
    BOOL_OFF_FG,
    CLASS_ROW_BG,
    CLASS_ROW_FG,
    COLUMN_SEP,
    DISABLED_FG,
    HEADER_BG,
    MENU_STYLE,
    PANEL_BG,
    PREVIEW_FG,
    PROP_COL_WIDTH,
    ROW_HEIGHT,
    STATIC_FG,
    STYLE_BOOL_NAMES,
    TREE_BG,
    TREE_FG,
    TREE_HEADING_BG,
    TREE_HEADING_FG,
    TREE_SELECTED_BG,
    TYPE_LABEL_FG,
    VALUE_BG,
)
from .drag_scrub import DragScrubController
from .editors import get_editor
from .format_utils import (
    coerce_value,
    compute_subgroup_preview,
    enum_options_for,
    format_numeric_pair_preview,
    format_value,
)
from .overlays import (
    SLOT_STYLE_PREVIEW,
    SLOT_TEXT_VALUE,
    OverlayRegistry,
    place_style_preview,
)
from .type_icons import icon_for_type


class PropertiesPanelV2(ctk.CTkFrame):
    """ttk.Treeview-based Properties panel. API-compatible with v1."""

    def __init__(self, master, project: Project):
        super().__init__(master, fg_color=PANEL_BG)
        self.project = project
        self.current_id: str | None = None

        # Prop name → tree iid (for property_changed updates)
        self._prop_iids: dict[str, str] = {}
        # All persistent overlays (color swatches, pencil buttons,
        # enum dropdowns, text value labels, image buttons, style
        # preview) live in a single registry. Initialized in
        # `_build_tree` once self.tree exists.
        self.overlays: OverlayRegistry | None = None
        # Style preview (multi-color Bold/Italic/Underline/Strike row)
        # The Frame itself is registered in `self.overlays` under
        # SLOT_STYLE_PREVIEW; these track its per-label children.
        self._style_labels: dict[str, tk.Label] = {}
        self._style_subgroup_iid: str | None = None
        # Subgroup iids we recompute previews for (e.g. Corners, Border)
        self._subgroup_preview_iids: dict[str, str] = {}
        # Cached disabled_when results — diffed on every property change
        # so we can flip the "disabled" tag on the affected rows only.
        self._disabled_states: dict[str, bool] = {}
        # Active in-place editor (Entry) — one at a time
        self._active_editor: tk.Widget | None = None
        self._active_prop: str | None = None
        self._active_prop_type: str | None = None

        self._name_var: tk.StringVar | None = None
        self._name_entry: tk.Entry | None = None
        self._suspend_name_trace = False
        # Set True while drag-scrub (or similar live-preview) is
        # running so intermediate _commit_prop calls don't each push
        # a history entry. The scrub controller pushes one command
        # at release.
        self._suspend_history: bool = False

        self._build_chrome()
        self._build_tree()

        bus = self.project.event_bus
        bus.subscribe("selection_changed", self._on_selection)
        bus.subscribe("property_changed", self._on_property_changed)
        bus.subscribe("widget_renamed", self._on_widget_renamed)

        self._show_empty()

    # ==================================================================
    # Chrome: panel title, type header, name row
    # ==================================================================
    def _build_chrome(self) -> None:
        title = ctk.CTkLabel(
            self, text="Properties", font=("Segoe UI", 13, "bold"),
        )
        title.pack(pady=(6, 2), padx=10)

        # Type header bar (dark stripe with widget type + ID + help)
        self._type_bar = ctk.CTkFrame(
            self, fg_color=HEADER_BG, height=26, corner_radius=0,
        )
        self._type_bar.pack(fill="x", pady=(0, 2))
        self._type_bar.pack_propagate(False)

        self._type_icon_label = ctk.CTkLabel(
            self._type_bar, text="", fg_color=HEADER_BG,
            width=16, height=18,
        )
        self._type_icon_label.pack(side="left", padx=(10, 0))

        self._type_label = ctk.CTkLabel(
            self._type_bar, text="", fg_color=HEADER_BG,
            font=("Segoe UI", 11, "bold"), text_color=TYPE_LABEL_FG,
            height=18,
        )
        self._type_label.pack(side="left", padx=(4, 0))

        help_icon = load_icon("circle-help", size=14)
        self._help_btn = ctk.CTkButton(
            self._type_bar, text="", image=help_icon,
            width=20, height=18, corner_radius=3,
            fg_color=HEADER_BG, hover_color="#3a3a3a",
            command=self._open_widget_docs,
        )
        self._help_btn.pack(side="right", padx=(0, 8))

        self._id_label = ctk.CTkLabel(
            self._type_bar, text="", fg_color=HEADER_BG,
            font=("Segoe UI", 9), text_color="#999999", height=18,
        )
        self._id_label.pack(side="right", padx=(0, 4))

        # Name row
        self._name_row = tk.Frame(self, bg=BG, height=30,
                                  highlightthickness=0)
        self._name_row.pack(fill="x", pady=(2, 4), padx=6)
        self._name_row.pack_propagate(False)

        tk.Label(
            self._name_row, text="Name", bg=BG, fg=STATIC_FG,
            font=("Segoe UI", 10), anchor="w",
        ).pack(side="left", padx=(6, 8))

        self._name_var = tk.StringVar()
        self._name_entry = tk.Entry(
            self._name_row, textvariable=self._name_var,
            bg=VALUE_BG, fg="#cccccc", insertbackground="#cccccc",
            font=("Segoe UI", 11),
            relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground="#3a3a3a",
            highlightcolor="#3b8ed0",
        )
        self._name_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._name_var.trace_add("write", self._on_name_var_write)

    def _open_widget_docs(self) -> None:
        # Best-effort: open the widget's wiki page if we have a selection.
        import webbrowser
        descriptor = self._current_descriptor()
        if descriptor is None:
            return
        url = (
            "https://github.com/kandelucky/ctk_visual_builder/"
            f"wiki/{descriptor.type_name}"
        )
        try:
            webbrowser.open(url)
        except Exception:
            log_error("PropertiesPanelV2._open_widget_docs")

    def _current_descriptor(self):
        if self.current_id is None:
            return None
        node = self.project.get_widget(self.current_id)
        if node is None:
            return None
        return get_descriptor(node.widget_type)

    # ==================================================================
    # Tree + custom column header
    # ==================================================================
    def _build_tree(self) -> None:
        wrap = tk.Frame(self, bg=BG, highlightthickness=0)
        wrap.pack(fill="both", expand=True, padx=0, pady=0)

        # Custom header row (ttk heading anchor is unreliable on the
        # "default" theme, so we draw our own centered one).
        header_bar = tk.Frame(
            wrap, bg=TREE_HEADING_BG, height=32,
            highlightthickness=0,
        )
        header_bar.pack(side="top", fill="x")
        header_bar.grid_propagate(False)
        header_bar.pack_propagate(False)
        header_bar.grid_columnconfigure(0, minsize=PROP_COL_WIDTH)
        header_bar.grid_columnconfigure(1, weight=1)
        header_bar.grid_rowconfigure(0, weight=1)

        tk.Label(
            header_bar, text="Property", bg=TREE_HEADING_BG,
            fg=TREE_HEADING_FG, font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="nsew")
        tk.Label(
            header_bar, text="Value", bg=TREE_HEADING_BG,
            fg=TREE_HEADING_FG, font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=1, sticky="nsew")

        self._build_style()

        self.tree = ttk.Treeview(
            wrap,
            columns=("value",),
            show="tree",
            style="PropTreeV2.Treeview",
            selectmode="browse",
        )
        self.tree.column("#0", width=PROP_COL_WIDTH, stretch=True, anchor="w")
        self.tree.column("value", width=160, stretch=True, anchor="w")

        self.tree.tag_configure(
            "class", background=CLASS_ROW_BG, foreground=CLASS_ROW_FG,
        )
        self.tree.tag_configure("group", foreground=PREVIEW_FG)
        self.tree.tag_configure(
            "bool_off", foreground=BOOL_OFF_FG, background=TREE_BG,
        )
        self.tree.tag_configure(
            "disabled", foreground=DISABLED_FG, background=TREE_BG,
        )

        vscroll = ctk.CTkScrollbar(
            wrap, orientation="vertical", command=self._on_vscroll,
            width=10, corner_radius=4,
            fg_color="#1a1a1a", button_color="#3a3a3a",
            button_hover_color="#4a4a4a",
        )
        self._vscroll = vscroll
        self.tree.configure(yscrollcommand=self._on_yscrollcommand)

        self.tree.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y", padx=(2, 0))

        # Vertical separator between Property and Value columns.
        self._col_separator = tk.Frame(
            self.tree, bg=COLUMN_SEP, width=1, highlightthickness=0,
        )
        self._col_separator.place(x=PROP_COL_WIDTH, rely=0, relheight=1)

        self.tree.bind("<Double-Button-1>", self._on_double_click)
        self.tree.bind("<Button-1>", self._on_single_click, add="+")
        self.tree.bind("<<TreeviewOpen>>", self._on_layout_change,
                       add="+")
        self.tree.bind("<<TreeviewClose>>", self._on_layout_change,
                       add="+")
        self.tree.bind("<Configure>", self._on_layout_change, add="+")
        self.tree.bind("<FocusOut>", self._on_tree_focus_out, add="+")

        self.overlays = OverlayRegistry(self.tree)
        self._drag_scrub = DragScrubController(self)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("default")
        except tk.TclError:
            pass
        style.configure(
            "PropTreeV2.Treeview",
            background=TREE_BG,
            foreground=TREE_FG,
            fieldbackground=TREE_BG,
            bordercolor=BG,
            borderwidth=0,
            rowheight=ROW_HEIGHT,
            font=("Segoe UI", 11),
        )
        style.map(
            "PropTreeV2.Treeview",
            background=[("selected", TREE_SELECTED_BG)],
            foreground=[("selected", "#ffffff")],
        )
        style.layout(
            "PropTreeV2.Treeview",
            [("PropTreeV2.Treeview.treearea", {"sticky": "nswe"})],
        )

    # ==================================================================
    # Scroll / layout forwarding → reposition color overlays
    # ==================================================================
    def _on_yscrollcommand(self, first, last) -> None:
        self._vscroll.set(first, last)
        self._schedule_reposition()

    def _on_vscroll(self, *args) -> None:
        self.tree.yview(*args)
        self._schedule_reposition()

    def _on_layout_change(self, _event=None) -> None:
        self._schedule_reposition()

    def _schedule_reposition(self) -> None:
        self.after_idle(self._reposition_overlays)

    def _reposition_overlays(self) -> None:
        if self.overlays is not None:
            self.overlays.reposition_all()

    def _on_tree_focus_out(self, _event=None) -> None:
        sel = self.tree.selection()
        if sel:
            self.tree.selection_remove(*sel)
        try:
            self.tree.focus("")
        except tk.TclError:
            pass

    # ==================================================================
    # Event bus handlers
    # ==================================================================
    def _on_selection(self, widget_id: str | None) -> None:
        self.current_id = widget_id
        self._rebuild()
        # Release keyboard focus so arrow keys nudge the newly selected
        # widget in the canvas instead of moving the tree cursor.
        try:
            self.tree.focus("")
        except tk.TclError:
            pass
        self.winfo_toplevel().focus_set()

    def _on_property_changed(
        self, widget_id: str, prop_name: str, value,
    ) -> None:
        if widget_id != self.current_id:
            return
        descriptor = self._current_descriptor()
        if descriptor is None:
            return
        prop = self._find_prop(descriptor, prop_name)
        iid = self._prop_iids.get(prop_name)
        if prop is not None and iid is not None:
            self._refresh_cell(iid, prop, value)

        # Re-evaluate disabled_when; flip the tag on any row whose
        # state changed since the last update.
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        new_states = self._compute_disabled_states(
            descriptor, node.properties,
        )
        changed: list[str] = []
        for p in descriptor.property_schema:
            name = p["name"]
            before = self._disabled_states.get(name, False)
            after = new_states.get(name, False)
            if before != after:
                changed.append(name)
        self._disabled_states = new_states
        for name in changed:
            p = self._find_prop(descriptor, name)
            if p is None:
                continue
            riid = self._prop_iids.get(name)
            if riid is not None:
                try:
                    self.tree.item(
                        riid,
                        tags=self._row_tags_for(
                            name, p, node.properties.get(name),
                        ),
                    )
                except tk.TclError:
                    pass
            self._apply_disabled_overlay(
                name, p, new_states.get(name, False),
            )

    def _on_widget_renamed(self, widget_id: str, new_name: str) -> None:
        if widget_id != self.current_id or self._name_var is None:
            return
        if self._name_var.get() == new_name:
            return
        self._suspend_name_trace = True
        try:
            self._name_var.set(new_name)
        finally:
            self._suspend_name_trace = False

    def _on_name_var_write(self, *_args) -> None:
        if self._suspend_name_trace or self.current_id is None:
            return
        new_name = self._name_var.get()
        node = self.project.get_widget(self.current_id)
        if node is None or node.name == new_name:
            return
        before = node.name
        self.project.rename_widget(self.current_id, new_name)
        # "rename" coalesce key collapses a burst of keystrokes into
        # a single undo step — History.merge_into preserves the tail's
        # original `before` and refreshes its `after` on each push
        # within COALESCE_WINDOW_SEC.
        self.project.history.push(
            RenameCommand(
                self.current_id, before, new_name,
                coalesce_key="rename",
            ),
        )

    # ==================================================================
    # Rebuild
    # ==================================================================
    def _show_empty(self) -> None:
        self._clear_tree()
        self._type_label.configure(text="")
        self._id_label.configure(text="")
        self._type_icon_label.configure(image=None)
        self._suspend_name_trace = True
        try:
            if self._name_var is not None:
                self._name_var.set("")
        finally:
            self._suspend_name_trace = False
        self._name_entry.configure(state="disabled")

    def _clear_tree(self) -> None:
        for child in self.tree.get_children(""):
            self.tree.delete(child)
        if self.overlays is not None:
            self.overlays.clear()
        self._style_labels.clear()
        self._style_subgroup_iid = None
        self._subgroup_preview_iids.clear()
        self._prop_iids.clear()

    def _rebuild(self) -> None:
        self._clear_tree()
        if self.current_id is None:
            self._show_empty()
            return
        node = self.project.get_widget(self.current_id)
        descriptor = (
            get_descriptor(node.widget_type) if node is not None else None
        )
        if node is None or descriptor is None:
            self._show_empty()
            return

        # Backfill any default properties missing from the node — e.g.
        # legacy widgets persisted before `button_enabled` / `font_wrap`
        # / `border_enabled` existed in the schema.
        for k, v in descriptor.default_properties.items():
            if k not in node.properties:
                node.properties[k] = v

        self._update_chrome(node, descriptor)
        self._disabled_states = self._compute_disabled_states(
            descriptor, node.properties,
        )
        self._populate_schema(descriptor, node.properties)
        self._build_style_preview(node.properties)
        # Sync overlay appearance with initial disabled state
        for prop in descriptor.property_schema:
            pname = prop["name"]
            if self._disabled_states.get(pname):
                self._apply_disabled_overlay(pname, prop, True)
        self._schedule_reposition()

    def _build_style_preview(self, properties: dict) -> None:
        """Create the Bold/Italic/Underline/Strike colored preview
        overlay for the Text > Style subgroup, if that subgroup exists
        in the current schema.
        """
        if self._style_subgroup_iid is None or self.overlays is None:
            return
        frame = tk.Frame(self.tree, bg=TREE_BG)
        for prop_name, label_text in STYLE_BOOL_NAMES.items():
            lbl = tk.Label(
                frame, text=label_text, bg=TREE_BG,
                font=("Segoe UI", 10),
                fg="#cccccc" if properties.get(prop_name)
                else BOOL_OFF_FG,
            )
            lbl.pack(side="left", padx=(0, 8))
            self._style_labels[prop_name] = lbl
        self.overlays.add(
            self._style_subgroup_iid, SLOT_STYLE_PREVIEW,
            frame, place_style_preview,
        )

    def _refresh_style_preview(self) -> None:
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        for prop_name, lbl in self._style_labels.items():
            try:
                lbl.configure(
                    fg="#cccccc" if node.properties.get(prop_name)
                    else BOOL_OFF_FG,
                )
            except tk.TclError:
                pass

    def _update_chrome(self, node, descriptor) -> None:
        self._type_label.configure(text=descriptor.type_name)
        self._id_label.configure(text=f"ID: {node.id[:8]}")

        # Widget-type icon (mirrors palette's icon name convention).
        icon_name = icon_for_type(descriptor.type_name)
        if icon_name:
            icon = load_icon(icon_name, size=14, color=TYPE_LABEL_FG)
            self._type_icon_label.configure(image=icon)
            self._type_icon_label.image = icon  # retain ref
        else:
            self._type_icon_label.configure(image=None)

        self._suspend_name_trace = True
        try:
            if self._name_var is not None:
                self._name_var.set(node.name or descriptor.display_name)
        finally:
            self._suspend_name_trace = False
        self._name_entry.configure(state="normal")

    # ==================================================================
    # Schema traversal → tree hierarchy
    # ==================================================================
    def _populate_schema(self, descriptor, properties: dict) -> None:
        schema = descriptor.property_schema
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

        display = format_value(ptype, value, prop)
        tags = self._row_tags_for(pname, prop, value)

        self.tree.insert(
            parent_iid, "end", iid=iid,
            text=label, values=(display,),
            open=False, tags=tags,
        )

        get_editor(ptype).populate(self, iid, pname, prop, value)

    def _refresh_cell(self, iid: str, prop: dict, value) -> None:
        ptype = prop["type"]
        display = format_value(ptype, value, prop)
        try:
            self.tree.set(iid, "value", display)
        except tk.TclError:
            return

        if ptype == "boolean":
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
            p for p in descriptor.property_schema
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
        for p in descriptor.property_schema:
            if p["name"] == prop_name:
                return p
        return None

    # ==================================================================
    # disabled_when
    # ==================================================================
    def _compute_disabled_states(
        self, descriptor, properties: dict,
    ) -> dict[str, bool]:
        result: dict[str, bool] = {}
        for prop in descriptor.property_schema:
            fn = prop.get("disabled_when")
            if callable(fn):
                try:
                    result[prop["name"]] = bool(fn(properties))
                except Exception:
                    result[prop["name"]] = False
        return result

    def _row_tags_for(self, pname: str, prop: dict, value) -> tuple[str, ...]:
        tags: list[str] = []
        if prop["type"] == "boolean" and not value:
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

    # ==================================================================
    # Enum popup
    # ==================================================================
    def _popup_enum_menu_at(
        self, pname: str, ptype: str, x_root: int, y_root: int,
    ) -> None:
        options = enum_options_for(ptype)
        if not options:
            return
        node = self.project.get_widget(self.current_id)
        current = node.properties.get(pname) if node else None
        menu = tk.Menu(self, tearoff=0, **MENU_STYLE)
        for opt in options:
            stored = (
                ANCHOR_LABEL_TO_CODE.get(opt, opt)
                if ptype == "anchor" else opt
            )
            prefix = "• " if stored == current else "   "
            if ptype == "anchor":
                commit_val = ANCHOR_LABEL_TO_CODE.get(opt, "center")
            else:
                commit_val = opt
            menu.add_command(
                label=f"{prefix}{opt}",
                command=lambda v=commit_val, p=pname:
                    self._commit_prop(p, v),
            )
        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()

    # ==================================================================
    # Text inline edit (fast single-line)
    # ==================================================================
    def _edit_text_inline(self, pname: str) -> None:
        iid = self._prop_iids.get(pname)
        if iid is None or self.overlays is None:
            return
        overlay = self.overlays.get(iid, SLOT_TEXT_VALUE)
        if overlay is None:
            return
        self._commit_active_editor()
        self.tree.update_idletasks()
        x = overlay.winfo_x()
        y = overlay.winfo_y()
        w = overlay.winfo_width()
        h = overlay.winfo_height()

        node = self.project.get_widget(self.current_id)
        current = node.properties.get(pname, "") if node else ""
        entry = tk.Entry(
            self.tree, font=("Segoe UI", 11),
            bg=VALUE_BG, fg="#cccccc", insertbackground="#cccccc",
            bd=1, relief="flat",
            highlightthickness=1, highlightbackground="#3a3a3a",
            highlightcolor="#3b8ed0",
        )
        entry.insert(0, str(current))
        entry.place(x=x, y=y, width=w, height=h)
        entry.select_range(0, tk.END)
        entry.focus_set()
        self._active_editor = entry
        self._active_prop = pname
        self._active_prop_type = "multiline"
        entry.bind("<Return>", lambda _e: self._commit_active_editor())
        entry.bind("<FocusOut>", lambda _e: self._commit_active_editor())
        entry.bind("<Escape>", lambda _e: self._cancel_active_editor())

    # ==================================================================
    # Click routing
    # ==================================================================
    def _on_single_click(self, event) -> None:
        region = self.tree.identify_region(event.x, event.y)
        if region == "nothing":
            self.tree.selection_remove(*self.tree.selection())
            try:
                self.tree.focus("")
            except tk.TclError:
                pass
            self.winfo_toplevel().focus_set()
            return
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        if col != "#1":
            return
        iid = self.tree.identify_row(event.y)
        if not iid or not iid.startswith("p:"):
            return
        pname = iid[2:]
        if self._disabled_states.get(pname):
            return
        prop = self._find_prop_by_name(pname)
        if prop is None:
            return
        get_editor(prop["type"]).on_single_click(self, pname, prop)

    def _on_double_click(self, event) -> str | None:
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return None
        col = self.tree.identify_column(event.x)
        if col != "#1":
            return None
        iid = self.tree.identify_row(event.y)
        if not iid or not iid.startswith("p:"):
            return None
        pname = iid[2:]
        if self._disabled_states.get(pname):
            return "break"
        prop = self._find_prop_by_name(pname)
        if prop is None:
            return None
        if get_editor(prop["type"]).on_double_click(self, pname, prop, event):
            return "break"
        return None

    def _find_prop_by_name(self, pname: str):
        descriptor = self._current_descriptor()
        if descriptor is None:
            return None
        return self._find_prop(descriptor, pname)

    # ==================================================================
    # Editors — inline Entry
    # ==================================================================
    def _open_entry_overlay(
        self, iid: str, pname: str, prop: dict, bbox,
    ) -> None:
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        current = node.properties.get(pname, "")
        entry = tk.Entry(
            self.tree,
            font=("Segoe UI", 11),
            bg=VALUE_BG, fg="#cccccc", insertbackground="#cccccc",
            bd=1, relief="flat",
            highlightthickness=1, highlightbackground="#3a3a3a",
            highlightcolor="#3b8ed0",
        )
        entry.insert(0, str(current) if current is not None else "")
        entry.place(
            x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3],
        )
        entry.select_range(0, tk.END)
        entry.focus_set()
        self._active_editor = entry
        self._active_prop = pname
        self._active_prop_type = prop["type"]

        entry.bind("<Return>", lambda _e: self._commit_active_editor())
        entry.bind("<FocusOut>", lambda _e: self._commit_active_editor())
        entry.bind("<Escape>", lambda _e: self._cancel_active_editor())

    def _commit_active_editor(self) -> None:
        if self._active_editor is None or self._active_prop is None:
            return
        pname = self._active_prop
        ptype = getattr(self, "_active_prop_type", None)
        try:
            raw = self._active_editor.get()
        except tk.TclError:
            raw = ""
        new_value = coerce_value(ptype, raw)
        try:
            self._active_editor.destroy()
        except tk.TclError:
            pass
        self._active_editor = None
        self._active_prop = None
        self._active_prop_type = None
        if new_value is not None:
            self._commit_prop(pname, new_value)

    def _cancel_active_editor(self) -> None:
        if self._active_editor is None:
            return
        try:
            self._active_editor.destroy()
        except tk.TclError:
            pass
        self._active_editor = None
        self._active_prop = None
        self._active_prop_type = None

    # ==================================================================
    # Pickers
    # ==================================================================
    def _pick_color(self, pname: str) -> None:
        if self.current_id is None:
            return
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        initial = node.properties.get(pname) or "#1f6aa5"
        dialog = ColorPickerDialog(
            self.winfo_toplevel(), initial_color=initial,
        )
        dialog.wait_window()
        hex_value = getattr(dialog, "result", None)
        if hex_value:
            self._commit_prop(pname, hex_value)

    def _pick_image(self, pname: str) -> None:
        path = filedialog.askopenfilename(
            title="Select image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._commit_prop(pname, path)

    def _open_text_editor(self, pname: str, prop: dict) -> None:
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        current = node.properties.get(pname) or ""
        label = prop.get("row_label") or prop.get("label") or pname
        dialog = TextEditorDialog(
            self.winfo_toplevel(), f"Edit: {label}", str(current),
        )
        dialog.wait_window()
        if dialog.result is not None:
            self._commit_prop(pname, dialog.result)

    # ==================================================================
    # Commit path
    # ==================================================================
    def _commit_prop(self, pname: str, value) -> None:
        if self.current_id is None:
            return
        node = self.project.get_widget(self.current_id)
        before = node.properties.get(pname) if node is not None else None
        self.project.update_property(self.current_id, pname, value)
        # Skip history records during live drag-scrub — the scrub
        # controller pushes one ChangePropertyCommand at release with
        # the full before → after diff.
        if getattr(self, "_suspend_history", False):
            return
        if before == value:
            return
        self.project.history.push(
            ChangePropertyCommand(self.current_id, pname, before, value),
        )
