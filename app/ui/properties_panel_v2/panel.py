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
from tkinter import ttk

import customtkinter as ctk

from app.core.commands import RenameCommand
from app.core.logger import log_error
from app.core.project import WINDOW_ID, Project
from app.ui.icons import load_icon
from app.widgets.layout_schema import LAYOUT_DEFAULTS
from app.widgets.registry import get_descriptor

from .constants import (
    BG,
    BOOL_OFF_FG,
    CLASS_ROW_BG,
    CLASS_ROW_FG,
    COLUMN_SEP,
    DISABLED_FG,
    HEADER_BG,
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
from .overlays import (
    SLOT_STYLE_PREVIEW,
    OverlayRegistry,
    place_style_preview,
)
from .panel_commit import CommitMixin
from .panel_schema import SchemaMixin
from .type_icons import icon_for_type


class PropertiesPanelV2(CommitMixin, SchemaMixin, ctk.CTkFrame):
    """ttk.Treeview-based Properties panel. API-compatible with v1.

    Method surface split across mixins:

    - ``CommitMixin`` (``panel_commit.py``) — commit path, pickers,
      inline editors, click routing, enum popup, geometry bounds.
    - ``SchemaMixin`` (``panel_schema.py``) — schema traversal → tree
      rows, disabled / hidden state, paired-row rendering.
    """

    def __init__(
        self, master, project: Project,
        tool_provider=None, tool_setter=None,
    ):
        super().__init__(master, fg_color=PANEL_BG)
        self.project = project
        self.current_id: str | None = None
        # Called with no args, returns the current workspace tool
        # name ("edit" / "select" / "hand"). When set to something
        # other than "edit", `_rebuild` skips the full schema build
        # and only refreshes the name / type / id chrome so picking a
        # widget in Select mode doesn't pay for a 30-row panel
        # rebuild + disabled_when lambda pass.
        self._tool_provider = tool_provider or (lambda: "edit")
        # Called with a tool name to flip the workspace tool. Lets
        # the Select-mode "Edit ✏" button jump straight into editing
        # without making the user hunt for the toolbar.
        self._tool_setter = tool_setter

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
        # Schema rows injected per-rebuild based on the selected node's
        # parent layout_type — pack_* / grid_* fields the descriptor
        # itself doesn't carry. Empty when parent uses ``place``.
        self._layout_extras: list[dict] = []
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
        bus.subscribe("tool_changed", self._on_tool_changed)
        bus.subscribe("property_changed", self._on_property_changed)
        bus.subscribe("widget_renamed", self._on_widget_renamed)

        self._show_empty()

    # ==================================================================
    # Chrome: panel title, type header, name row
    # ==================================================================
    def _build_chrome(self) -> None:
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

        # Edit-tool shortcut button — only packed (i.e. visible) when
        # Select tool is active AND the panel has a non-Window
        # selection. Click flips the workspace tool to Edit so the
        # user can start editing the current widget without hunting
        # for the toolbar. ``_update_chrome`` pack/forgets it.
        edit_icon = load_icon("pencil", size=14)
        self._edit_btn = ctk.CTkButton(
            self._name_row, text="" if edit_icon else "Edit",
            image=edit_icon,
            width=26, height=22, corner_radius=3,
            fg_color="#2d2d2d", hover_color="#3a3a3a",
            text_color="#cccccc",
            font=("Segoe UI", 10, "bold"),
            command=self._on_edit_button,
        )
        self._edit_btn_visible = False

        self._name_var = tk.StringVar()
        self._name_entry = tk.Entry(
            self._name_row, textvariable=self._name_var,
            bg=VALUE_BG, fg="#cccccc", insertbackground="#cccccc",
            disabledbackground=VALUE_BG, disabledforeground="#555555",
            font=("Segoe UI", 11),
            relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground="#3a3a3a",
            highlightcolor="#3b8ed0",
        )
        self._name_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._name_var.trace_add("write", self._on_name_var_write)
        self._name_entry.bind(
            "<Return>", lambda _e: self.tree.focus_set(),
        )
        self._attach_inline_context_menu(self._name_entry, prop=None)

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
            fg_color="transparent", button_color="#3a3a3a",
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
    def _on_tool_changed(self, _tool: str) -> None:
        # Rebuild so the schema appears / disappears to match the new
        # tool. Cheap when nothing is selected (early return in
        # ``_rebuild``).
        self._rebuild()

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
        # layout_type flips which rows are hidden (grid Dimensions
        # etc.), so rebuild the whole panel rather than patching one
        # cell — the row count changes.
        if prop_name == "layout_type":
            self._rebuild()
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
        for p in self._effective_schema(descriptor):
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
    def _clear_type_icon(self) -> None:
        """CTkLabel._update_image is a no-op when _image is None, so
        the underlying tk.Label keeps the old PhotoImage.  Clear it
        directly via the internal _label attribute."""
        self._type_icon_label.configure(image=None)
        self._type_icon_label.image = None
        inner = getattr(self._type_icon_label, "_label", None)
        if inner is not None:
            try:
                inner.configure(image="")
            except tk.TclError:
                pass

    def _show_empty(self) -> None:
        self._clear_tree()
        self._type_label.configure(text="")
        self._id_label.configure(text="")
        self._clear_type_icon()
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

        # Select tool: skip the full schema rebuild so click-to-pick
        # stays cheap. Name / type / id chrome still updates. Window
        # settings are the Select-mode exception — they describe the
        # whole form, not a single widget, so clicking the settings
        # chrome in Select mode should still open them. Hand mode
        # stays strict: it's a pure canvas panner, opening anything
        # there would contradict its "does nothing else" contract.
        tool = self._tool_provider()
        allow_full_rebuild = (
            tool == "edit"
            or (tool == "select" and node.id == WINDOW_ID)
        )
        if not allow_full_rebuild:
            self._clear_tree()
            self._update_chrome(node, descriptor)
            return

        # Backfill any default properties missing from the node — e.g.
        # legacy widgets persisted before `button_enabled` / `font_wrap`
        # / `border_enabled` existed in the schema.
        for k, v in descriptor.default_properties.items():
            if k not in node.properties:
                node.properties[k] = v

        # Recompute the parent-driven Layout rows (pack_* / grid_*).
        self._layout_extras = self._compute_layout_extras(node)
        # Backfill defaults for any layout key the node hasn't seen
        # before so editors render with a sensible value.
        for prop in self._layout_extras:
            key = prop["name"]
            if key not in node.properties and key in LAYOUT_DEFAULTS:
                node.properties[key] = LAYOUT_DEFAULTS[key]

        self._update_chrome(node, descriptor)
        self._disabled_states = self._compute_disabled_states(
            descriptor, node.properties,
        )
        self._apply_managed_layout_disabled(node)
        self._populate_schema(descriptor, node.properties, node)
        self._build_style_preview(node.properties)
        # Sync overlay appearance with initial disabled state
        for prop in self._effective_schema(descriptor):
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
        # For the Window node we show the active document's UUID
        # instead of the sentinel WINDOW_ID — otherwise every window
        # reads as the same "__window_" prefix in the header.
        if node.id == WINDOW_ID:
            id_text = self.project.active_document.id[:8]
        else:
            id_text = node.id[:8]
        self._id_label.configure(text=f"ID: {id_text}")

        # Widget-type icon (mirrors palette's icon name convention).
        icon_name = icon_for_type(descriptor.type_name)
        if icon_name:
            icon = load_icon(icon_name, size=14, color=TYPE_LABEL_FG)
            self._type_icon_label.configure(image=icon)
            self._type_icon_label.image = icon  # retain ref
        else:
            self._clear_type_icon()

        self._suspend_name_trace = True
        try:
            if self._name_var is not None:
                self._name_var.set(node.name or descriptor.display_name)
        finally:
            self._suspend_name_trace = False
        self._name_entry.configure(state="normal")
        self._sync_edit_button(node)

    def _sync_edit_button(self, node) -> None:
        """Show the Edit shortcut only when it makes sense: we're in
        Select mode, there's a regular widget selected (not the
        sentinel Window node), and a tool_setter is wired. Otherwise
        pack_forget so the row stays clean.
        """
        if self._tool_setter is None:
            return
        tool = self._tool_provider()
        should_show = (
            tool == "select"
            and node is not None
            and node.id != WINDOW_ID
        )
        if should_show and not self._edit_btn_visible:
            self._edit_btn.pack(side="right", padx=(4, 6))
            self._edit_btn_visible = True
        elif not should_show and self._edit_btn_visible:
            self._edit_btn.pack_forget()
            self._edit_btn_visible = False

    def _on_edit_button(self) -> None:
        """Narrow multi-selection to the primary widget and flip the
        workspace tool to Edit. Matches Figma-style "open for edit"
        where clicking Edit on a group focuses on the one you were
        last looking at, not the whole group.
        """
        if self._tool_setter is None:
            return
        primary = self.project.selected_id
        if primary is not None:
            # Collapse multi-selection if any; select_widget sets a
            # single primary without touching tool state.
            current_ids = set(
                getattr(self.project, "selected_ids", set()) or set(),
            )
            if len(current_ids) > 1:
                self.project.select_widget(primary)
        self._tool_setter("edit")

