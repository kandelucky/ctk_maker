"""Properties panel — ttk.Treeview-based implementation.

Uses a single `ttk.Treeview` as the backbone (same pattern as
`app/ui/object_tree_window.py`) plus thin overlays for editors
that can't be text-only:

    - Inline `tk.Entry` overlay on double-click for number / multiline
    - `tk.Frame` color swatches persistently overlaid on color rows
    - Native `tk.Menu` popup for anchor / compound enums
    - Unicode checkboxes (☑ / ☐) for bools + `bool_off` tag graying

The class lives inside the `app.ui.properties_panel` package.
Pure helpers (formatting, enum options, value coercion) live in
`format_utils`; shared constants in `constants`; widget-type icon
lookup in `type_icons`.
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
from app.ui.system_fonts import ui_font
from .drag_scrub import DragScrubController
from .overlays import (
    SLOT_STYLE_PREVIEW,
    OverlayRegistry,
    place_style_preview,
)
from .panel_commit import CommitMixin
from .panel_schema import SchemaMixin
from .property_help import PROPERTY_HELP, ROW_HELP

# Tooltip iids that work on every widget type — bypass the CTkLabel
# scope gate. Object Reference rows + the Advanced events sub-group
# are universal across panels, so they should always show their help.
_WIDGET_AGNOSTIC_TOOLTIP_IIDS = frozenset({
    "events:advanced",
    "g:Object Reference",
    "g:Object References",
})
from .tooltip import PropertyTooltip
from .type_icons import icon_for_type


class PropertiesPanel(CommitMixin, SchemaMixin, ctk.CTkFrame):
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
        # Rows whose value is rendered as a VALUE_BG overlay box instead
        # of native cell text (Interaction-group text rows — see
        # _insert_prop). _refresh_cell updates the overlay for these.
        self._boxed_value_iids: set[str] = set()
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
        # Phase 2 visual scripting — Events group row metadata. Maps
        # tree iid → shape varies by row kind so the click router
        # can dispatch without re-parsing the iid string itself.
        # Shapes:
        #   ("group", None, None)
        #   ("header", event_key, None)
        #   ("method", event_key, method_index)       # parent row
        #   ("function", event_key, method_index)     # Function child
        #   ("param", event_key, method_index, p_idx) # parameter child
        #   ("pending", event_key, None)              # placeholder
        self._event_row_meta: dict[str, tuple] = {}
        # Unity-style pending event rows — count of "Add target"
        # placeholders per ``(widget_id, event_key)``. Each gets
        # rendered after the committed handler entries; the inner
        # ``[+]`` opens the cascade picker, which commits via
        # ``on_commit`` callback that decrements the count.
        # Cleared on widget selection change so pending rows don't
        # haunt unrelated widgets.
        self._pending_event_rows: dict[tuple[str, str], int] = {}
        # Cached disabled_when results — diffed on every property change
        # so we can flip the "disabled" tag on the affected rows only.
        self._disabled_states: dict[str, bool] = {}
        # Schema rows injected per-rebuild based on the selected node's
        # parent layout_type — pack_* / grid_* fields the descriptor
        # itself doesn't carry. Empty when parent uses ``place``.
        self._layout_extras: list[dict] = []
        # Top-level group iids the user has manually closed — persisted
        # across rebuilds and app restarts via settings.json.
        from app.core.settings import load_settings
        self._collapsed_groups: set[str] = set(
            load_settings().get("ui_properties_collapsed_groups", [])
        )
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
        bus.subscribe(
            "widget_description_changed", self._on_description_changed,
        )
        bus.subscribe(
            "request_edit_description", self._on_edit_description_request,
        )
        # Variable state can change without touching widget properties
        # (e.g. rename, type change). Re-render the panel so the chip
        # text in any bound row stays in sync with the variable's name
        # / type label.
        for ev in (
            "variable_renamed", "variable_type_changed",
            "variable_default_changed", "variable_removed",
        ):
            bus.subscribe(ev, self._on_variable_state_changed)
        # Phase 2 — handler list mutations (bind / unbind / reorder)
        # need to repaint the Events group so action counts + method
        # rows match the model.
        bus.subscribe(
            "widget_handler_changed", self._on_widget_handler_changed,
        )

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
            font=ui_font(11, "bold"), text_color=TYPE_LABEL_FG,
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
            font=ui_font(9), text_color="#999999", height=18,
        )
        self._id_label.pack(side="right", padx=(0, 4))

        # Name row
        self._name_row = tk.Frame(self, bg=BG, height=30,
                                  highlightthickness=0)
        self._name_row.pack(fill="x", pady=(2, 4), padx=6)
        self._name_row.pack_propagate(False)

        tk.Label(
            self._name_row, text="Name", bg=BG, fg=STATIC_FG,
            font=ui_font(10), anchor="w",
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
            font=ui_font(10, "bold"),
            command=self._on_edit_button,
        )
        self._edit_btn_visible = False

        self._name_var = tk.StringVar()
        self._name_entry = tk.Entry(
            self._name_row, textvariable=self._name_var,
            bg=VALUE_BG, fg="#cccccc", insertbackground="#cccccc",
            disabledbackground=VALUE_BG, disabledforeground="#555555",
            font=ui_font(11),
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

        # Description row — Phase 0 AI bridge. Click "Edit Description…"
        # opens a Toplevel; the typed text is emitted as Python comments
        # above the widget's constructor in code export so an AI can
        # read intent + structure and fill in the missing logic.
        self._desc_row = tk.Frame(
            self, bg=BG, height=30, highlightthickness=0,
        )
        self._desc_row.pack(fill="x", pady=(0, 4), padx=6)
        self._desc_row.pack_propagate(False)

        tk.Label(
            self._desc_row, text="Desc", bg=BG, fg=STATIC_FG,
            font=ui_font(10), anchor="w",
        ).pack(side="left", padx=(6, 8))

        self._desc_preview_var = tk.StringVar(
            value="Click to add description…",
        )
        self._desc_preview = tk.Label(
            self._desc_row, textvariable=self._desc_preview_var,
            bg=VALUE_BG, fg="#666666",
            font=ui_font(10, "italic"), anchor="w",
            relief="flat", bd=0, padx=6, cursor="hand2",
        )
        self._desc_preview.pack(side="left", fill="x", expand=True)
        self._desc_preview.bind(
            "<Button-1>", lambda _e: self._open_description_dialog(),
        )

        desc_edit_icon = load_icon("square-pen", size=14)
        self._desc_edit_btn = ctk.CTkButton(
            self._desc_row, text="" if desc_edit_icon else "Edit",
            image=desc_edit_icon,
            width=26, height=22, corner_radius=3,
            fg_color="#2d2d2d", hover_color="#3a3a3a",
            text_color="#cccccc",
            font=ui_font(10, "bold"),
            command=self._open_description_dialog,
        )
        self._desc_edit_btn.pack(side="right", padx=(4, 6))

    def _open_widget_docs(self) -> None:
        # Best-effort: open the widget's wiki page if we have a selection.
        # Falls back to the display name for descriptors whose
        # ``type_name`` is a private marker (e.g. ``__window__``) so
        # the URL stays human-readable. CTkFrame routes to the
        # layout-specific page when the node carries ``layout_type``
        # vbox / hbox / grid — those have dedicated wiki pages.
        import webbrowser
        descriptor = self._current_descriptor()
        if descriptor is None:
            return
        page = descriptor.type_name
        if not page or page.startswith("__"):
            page = (
                getattr(descriptor, "display_name", None) or "Home"
            )
        if page == "CTkFrame" and self.current_id is not None:
            node = self.project.get_widget(self.current_id)
            layout = (
                node.properties.get("layout_type") if node else None
            )
            page = {
                "vbox": "Vertical-Layout",
                "hbox": "Horizontal-Layout",
                "grid": "Grid-Layout",
            }.get(layout, page)
        # Wiki page slugs use hyphens for spaces.
        page = page.replace(" ", "-")
        url = f"https://github.com/kandelucky/ctk_maker/wiki/{page}"
        try:
            webbrowser.open(url)
        except Exception:
            log_error("PropertiesPanel._open_widget_docs")

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
            fg=TREE_HEADING_FG, font=ui_font(10, "bold"),
        ).grid(row=0, column=0, sticky="nsew")
        tk.Label(
            header_bar, text="Value", bg=TREE_HEADING_BG,
            fg=TREE_HEADING_FG, font=ui_font(10, "bold"),
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
        # Phase 1.5 binding: the bound-state cue lives on the diamond
        # glyph + chip text + ✕ button now, so the row tag is a no-op
        # tinted to match the tree background. Kept as a tag in case
        # we want a subtle cue back later — switching colour here will
        # apply across every bound row without touching call sites.
        self.tree.tag_configure(
            "bound", background=TREE_BG,
        )
        # Phase 3 — orphan handler indicator. Method rows whose
        # name doesn't resolve to a ``def`` on the behavior class
        # render with a soft red foreground so the user spots the
        # break before they hit F5. Pairs with the ``❌ `` label
        # prefix added in ``_populate_events_group``.
        # Trailing-section spacer row on the Window panel — darker
        # band that visually breaks the schema/window-property block
        # from the trailing Local Variables / Object References list.
        self.tree.tag_configure(
            "spacer", background="#121212", foreground="#121212",
        )
        self.tree.tag_configure(
            "missing_method", foreground="#ef4444", background=TREE_BG,
        )
        # Events group — header rows read dim when the event has no
        # handlers and brighten once one is bound, so active events stand
        # out from the long list of empty ones.
        self.tree.tag_configure("event_empty", foreground="#666666")
        self.tree.tag_configure("event_active", foreground=TREE_FG)

        # Tooltip created BEFORE the scrollbar wires up — yscrollcommand
        # may fire during initial layout, and ``_on_yscrollcommand``
        # touches ``self._tooltip``.
        self._tooltip = PropertyTooltip(self.tree)

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
        self.tree.bind("<Button-3>", self._on_tree_right_click, add="+")
        self.tree.bind("<<TreeviewOpen>>", self._on_layout_change,
                       add="+")
        self.tree.bind("<<TreeviewClose>>", self._on_layout_change,
                       add="+")
        self.tree.bind("<<TreeviewOpen>>", self._on_group_open, add="+")
        self.tree.bind("<<TreeviewClose>>", self._on_group_close, add="+")
        self.tree.bind("<Configure>", self._on_layout_change, add="+")
        self.tree.bind("<FocusOut>", self._on_tree_focus_out, add="+")
        self.tree.bind("<Motion>", self._on_tree_motion, add="+")
        self.tree.bind("<Leave>", self._on_tree_leave, add="+")
        self.tree.bind(
            "<MouseWheel>",
            lambda _e: self._tooltip.cancel(),
            add="+",
        )

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
            font=ui_font(11),
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
        self._tooltip.cancel()

    def _on_vscroll(self, *args) -> None:
        self.tree.yview(*args)
        self._schedule_reposition()
        self._tooltip.cancel()

    def _on_layout_change(self, _event=None) -> None:
        self._schedule_reposition()

    def _on_group_open(self, _event=None) -> None:
        iid = self.tree.focus()
        if iid and iid.startswith("g:"):
            self._collapsed_groups.discard(iid)
            self._save_collapsed_groups()

    def _on_group_close(self, _event=None) -> None:
        iid = self.tree.focus()
        if iid and iid.startswith("g:"):
            self._collapsed_groups.add(iid)
            self._save_collapsed_groups()

    def _save_collapsed_groups(self) -> None:
        from app.core.settings import save_setting
        save_setting("ui_properties_collapsed_groups", list(self._collapsed_groups))

    def _schedule_reposition(self) -> None:
        self.after_idle(self._reposition_overlays)

    def _reposition_overlays(self) -> None:
        if self.overlays is not None:
            self.overlays.reposition_all()
        # Overlays lift themselves; keep the column separator on top so
        # full-width cell overlays (e.g. the Scripts rows) don't bury it.
        sep = getattr(self, "_col_separator", None)
        if sep is not None:
            try:
                sep.lift()
            except tk.TclError:
                pass

    def _on_tree_focus_out(self, _event=None) -> None:
        sel = self.tree.selection()
        if sel:
            self.tree.selection_remove(*sel)
        try:
            self.tree.focus("")
        except tk.TclError:
            pass
        self._tooltip.cancel()

    # ==================================================================
    # Property help tooltip
    # ==================================================================
    def _on_tree_motion(self, event) -> None:
        # Only the property-name column (#0) gets a tooltip — value-cell
        # hover would compete with the inline editors and color swatches.
        if event.x > PROP_COL_WIDTH:
            self._tooltip.cancel()
            return

        iid = self.tree.identify_row(event.y)
        if not iid:
            self._tooltip.cancel()
            return

        # Event rows — work for every widget type, sourced from the
        # event registry (label + warning already maintained there).
        if iid.startswith("events:e:"):
            self._show_event_tooltip(iid, event.x_root, event.y_root)
            return

        # Widget-agnostic parent rows — Advanced events sub-group.
        # Bypass the CTkLabel scope gate below.
        agnostic_key: str | None = None
        if iid in _WIDGET_AGNOSTIC_TOOLTIP_IIDS:
            agnostic_key = iid
        if agnostic_key is not None:
            entry = ROW_HELP.get(agnostic_key)
            if entry is not None:
                self._tooltip.schedule(
                    event.x_root, event.y_root,
                    entry["description"],
                    entry.get("warning"),
                    key=agnostic_key,
                )
            else:
                self._tooltip.cancel()
            return

        # Property + subgroup rows — V1 scope is CTkLabel only.
        if not self._is_label_selected():
            self._tooltip.cancel()
            return

        # Parent rows — virtual numeric pairs (``pair:pos`` / ``pair:size``
        # / ``pair:pad`` / ``pair:img_size``) and schema subgroups
        # (``g:Text/Style``, ``g:Text/Wrap``). Top-level group headers
        # (``g:<group>`` without ``/``) intentionally have no tooltip:
        # the names ("Text", "Geometry", ...) read as self-explanatory.
        if iid.startswith("pair:") or (
            iid.startswith("g:") and "/" in iid
        ):
            entry = ROW_HELP.get(iid)
            if entry is None:
                self._tooltip.cancel()
                return
            self._tooltip.schedule(
                event.x_root, event.y_root,
                entry["description"],
                entry.get("warning"),
                key=iid,
            )
            return

        if iid.startswith("p:"):
            pname = iid[2:]
            entry = PROPERTY_HELP.get(pname)
            if entry is None:
                self._tooltip.cancel()
                return
            self._tooltip.schedule(
                event.x_root, event.y_root,
                entry["description"],
                entry.get("warning"),
                key=pname,
            )
            return

        self._tooltip.cancel()

    def _show_event_tooltip(
        self, iid: str, x_root: int, y_root: int,
    ) -> None:
        from app.widgets.event_registry import event_by_key
        meta = self._event_row_meta.get(iid)
        if meta is None or meta[0] != "header" or self.current_id is None:
            self._tooltip.cancel()
            return
        node = self.project.get_widget(self.current_id)
        if node is None:
            self._tooltip.cancel()
            return
        entry = event_by_key(node.widget_type, meta[1])
        if entry is None:
            self._tooltip.cancel()
            return
        # Prefer the explicit per-event description; fall back to the
        # capitalised label when an entry hasn't been backfilled yet.
        if entry.description:
            description = entry.description
        else:
            description = (entry.label[:1].upper() + entry.label[1:])
        warning = entry.warning or None
        self._tooltip.schedule(
            x_root, y_root, description, warning, key=f"event:{iid}",
        )

    def _on_tree_leave(self, _event=None) -> None:
        self._tooltip.cancel()

    def _is_label_selected(self) -> bool:
        if self.current_id is None:
            return False
        node = self.project.get_widget(self.current_id)
        if node is None:
            return False
        return getattr(node, "widget_type", None) == "CTkLabel"

    # ==================================================================
    # Event bus handlers
    # ==================================================================
    def _on_tool_changed(self, _tool: str) -> None:
        # Rebuild so the schema appears / disappears to match the new
        # tool. Cheap when nothing is selected (early return in
        # ``_rebuild``).
        self._rebuild()

    def _on_selection(self, widget_id: str | None) -> None:
        # Discard pending event rows when the user moves to a
        # different widget — incomplete placeholders are scoped to
        # the editing session for the widget that spawned them.
        if widget_id != self.current_id:
            self._pending_event_rows.clear()
        self.current_id = widget_id
        self._rebuild()
        # Release keyboard focus so arrow keys nudge the newly selected
        # widget in the canvas instead of moving the tree cursor.
        try:
            self.tree.focus("")
        except tk.TclError:
            pass
        self.winfo_toplevel().focus_set()
        self._tooltip.cancel()

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
        # Capture the pre-update state before the rebuild so the
        # row-tag flip loop below can detect transitions correctly.
        prev_states = dict(self._disabled_states)
        self._disabled_states = self._compute_disabled_states(
            descriptor, node.properties,
        )
        # Re-apply managed-layout disable AFTER the schema-driven
        # recompute — _compute_disabled_states returns a fresh dict
        # without the parent-layout-aware x/y/W/H entries, so without
        # this call the geometry fields would re-open whenever any
        # property changes (notably ``stretch``: changing grow→fill
        # in an hbox child should disable height but leave width
        # editable, and that flip won't show up unless we re-derive
        # the managed-layout state on every commit).
        self._apply_managed_layout_disabled(node)
        new_states = self._disabled_states
        changed: list[str] = []
        for p in self._effective_schema(descriptor):
            name = p["name"]
            before = prev_states.get(name, False)
            after = new_states.get(name, False)
            if before != after:
                changed.append(name)
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

    def _on_description_changed(
        self, widget_id: str, _value: str,
    ) -> None:
        if widget_id != self.current_id:
            return
        node = self.project.get_widget(widget_id)
        if node is not None:
            self._update_description_preview(node)

    def _on_edit_description_request(self) -> None:
        """Open the description editor for whatever the panel currently
        targets. Caller is expected to have selected the right widget /
        window first (chrome icon + canvas context menu both do this
        before publishing the event)."""
        if self.current_id is not None:
            self._open_description_dialog()

    def _on_variable_state_changed(self, *_args, **_kwargs) -> None:
        """Cheap blanket refresh — a variable's user-visible label
        changed, so any bound row's chip text needs updating. Only
        rebuilds when the panel currently has a selection."""
        if self.current_id is not None:
            self._rebuild()

    def _on_widget_handler_changed(
        self, widget_id: str, *_args, **_kwargs,
    ) -> None:
        """Repaint when a handler is bound / unbound / reordered.
        Filters on ``widget_id == current_id`` so the rebuild only
        fires for the currently-selected widget — handlers on
        siblings shouldn't trigger a panel rebuild.
        """
        if self.current_id == widget_id:
            self._rebuild()

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
        self._update_description_preview(None)

    def _clear_tree(self) -> None:
        for child in self.tree.get_children(""):
            self.tree.delete(child)
        if self.overlays is not None:
            self.overlays.clear()
        self._style_labels.clear()
        self._style_subgroup_iid = None
        self._subgroup_preview_iids.clear()
        self._prop_iids.clear()
        self._boxed_value_iids.clear()
        self._event_row_meta.clear()

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
        for giid in self._collapsed_groups:
            try:
                self.tree.item(giid, open=False)
            except tk.TclError:
                pass
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
                font=ui_font(10),
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
        self._update_description_preview(node)
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

    # ==================================================================
    # Description dialog (Phase 0 AI bridge)
    # ==================================================================
    def _open_description_dialog(self) -> None:
        """Open the multiline editor for the current widget's
        ``description`` meta-property. Empty / unchanged result skips
        the history push so a no-op cancel doesn't pollute undo.
        """
        if self.current_id is None:
            return
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        before = getattr(node, "description", "") or ""
        from tools.text_editor_dialog import TextEditorDialog
        from app.core.commands import ChangeDescriptionCommand
        descriptor = get_descriptor(node.widget_type)
        label = node.name or (
            descriptor.display_name if descriptor is not None
            else node.widget_type
        )
        dialog = TextEditorDialog(
            self.winfo_toplevel(),
            f"Description: {label}",
            before,
            width=720, height=420,
            show_hints=True,
        )
        dialog.wait_window()
        if dialog.result is None or dialog.result == before:
            return
        from app.core.project import WINDOW_ID
        document_id = (
            self.project.active_document_id
            if self.current_id == WINDOW_ID else None
        )
        node.description = dialog.result
        self.project.event_bus.publish(
            "widget_description_changed",
            self.current_id, dialog.result,
        )
        self.project.history.push(
            ChangeDescriptionCommand(
                self.current_id, before, dialog.result,
                document_id=document_id,
            ),
        )

    def _update_description_preview(self, node) -> None:
        desc = (
            (getattr(node, "description", "") or "").strip()
            if node is not None else ""
        )
        if not desc:
            preview = "Click to add description…"
            fg = "#666666"
        else:
            first_line = desc.partition("\n")[0]
            if len(first_line) > 60:
                first_line = first_line[:57] + "…"
            elif "\n" in desc:
                first_line += " …"
            preview = first_line
            fg = "#cccccc"
        self._desc_preview_var.set(preview)
        try:
            self._desc_preview.configure(fg=fg)
        except tk.TclError:
            pass

    # ==================================================================
    # Variable binding (Phase 1 visual scripting)
    # ==================================================================
    def _on_tree_right_click(self, event) -> None:
        """Right-click on a property row → bind / unbind menu. Right
        click stays as a backup gesture — the visible 🔗 button on
        each row is the primary path."""
        iid = self.tree.identify_row(event.y)
        if iid and iid.startswith("localvar:") and iid != "localvar:empty":
            self._show_local_var_menu(event)
            return
        # Phase 2 visual scripting — Events group rows route to a
        # dedicated menu. Side-table lookup avoids re-parsing iid
        # strings; ``_event_row_meta`` is populated alongside the
        # rows in ``_populate_events_group``.
        if iid and iid in self._event_row_meta:
            self._show_event_menu(event, iid)
            return
        if self.current_id is None:
            return
        if not iid or not iid.startswith("p:"):
            return
        pname = iid[2:]
        descriptor = self._current_descriptor()
        if descriptor is None:
            return
        prop = self._find_prop(descriptor, pname)
        if prop is None:
            return
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        self._show_binding_menu(event, pname, prop, node)

    def _add_menu_item(self, menu, label, command, enabled=True) -> None:
        """Add a menu command. When ``enabled`` is False, render it as a
        dimmed, inert item rather than ``state="disabled"`` — Windows
        native menus draw disabled entries as etched-ghost text on the
        dark theme ("ჯადო"); a grey foreground + no-op reads cleanly."""
        if enabled:
            menu.add_command(label=label, command=command)
        else:
            menu.add_command(
                label=label, command=lambda: None,
                foreground="#777777", activeforeground="#777777",
                activebackground="#2d2d30",
            )

    def _show_event_menu(self, event, iid: str) -> None:
        """Phase 2 — right-click menus for the Events group rows.
        Routing is driven by ``kind``:

        - ``group`` — no actions; the top-level "Events" header is
          a passive container. Skip.
        - ``header`` — the per-event row. Offer "Add action" so the
          user can attach a fresh stub via the same flow the canvas
          right-click cascade uses.
        - ``method`` — a bound method row. Offer Open / Move up /
          Move down / Unbind.
        """
        kind, event_key, method_index = self._event_row_meta[iid]
        if kind == "group":
            return
        if self.current_id is None:
            return
        # Event header → same gesture as the inline [+]: begin a new
        # action (pending target row, then the script_call target
        # picker). No menu — the right-click performs the add directly.
        if kind == "header":
            self._add_pending_event_row(self.current_id, event_key)
            return
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        from app.ui.properties_panel.constants import menu_style
        menu = tk.Menu(self.tree, tearoff=0, **menu_style())
        if kind == "pending":
            # An accidental [+] leaves an uncommitted "Add target" row;
            # offer a way to discard it (mirrors the inline ✕).
            menu.add_command(
                label="Delete",
                command=lambda: self._remove_pending_event_row(
                    self.current_id, event_key,
                ),
            )
        elif kind == "method":
            methods = list(node.handlers.get(event_key, []) or [])
            if method_index is None or method_index >= len(methods):
                return
            method_name = methods[method_index]
            self._add_menu_item(
                menu, "Move up",
                lambda: self._reorder_event_method(
                    self.current_id, event_key,
                    method_index, method_index - 1,
                ),
                enabled=method_index > 0,
            )
            self._add_menu_item(
                menu, "Move down",
                lambda: self._reorder_event_method(
                    self.current_id, event_key,
                    method_index, method_index + 1,
                ),
                enabled=method_index < len(methods) - 1,
            )
            menu.add_separator()
            menu.add_command(
                label="Delete action…",
                command=lambda: self._delete_event_action(
                    self.current_id, event_key,
                    method_index, method_name,
                ),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _add_pending_event_row(
        self, widget_id: str, event_key: str,
    ) -> None:
        """Outer ``[+]`` on an event header — adds a pending UI row
        with the ``Add target`` placeholder. The row only commits
        to ``WidgetNode.handlers`` once the user picks a target via
        its inner ``[+]``; until then it lives in
        ``self._pending_event_rows`` so unrelated rebuilds don't
        wipe it.
        """
        key = (widget_id, event_key)
        self._pending_event_rows[key] = (
            self._pending_event_rows.get(key, 0) + 1
        )
        self._rebuild()

    def _remove_pending_event_row(
        self, widget_id: str, event_key: str,
    ) -> None:
        """Inner ``[✕]`` on a pending row — discards one placeholder.
        Idempotent: removing past zero is a no-op so duplicate clicks
        don't break the panel state.
        """
        key = (widget_id, event_key)
        remaining = self._pending_event_rows.get(key, 0) - 1
        if remaining > 0:
            self._pending_event_rows[key] = remaining
        else:
            self._pending_event_rows.pop(key, None)
        self._rebuild()

    def _open_pending_target_picker(
        self, widget_id: str, event_key: str,
    ) -> None:
        """Inner ``[+]`` on a pending row — opens the flat target
        picker (Page Script + Object References, no method cascade)
        at the cursor. Pick commits the entry with an empty method
        and the user fills it next via the Function row ``▾``. The
        picker's ``on_commit`` decrements the pending count so the
        placeholder vanishes as the committed entry takes its place
        on the next rebuild.
        """
        from app.ui.event_bind_menu import show_target_only_menu_at_cursor
        show_target_only_menu_at_cursor(
            self.tree, self.project, widget_id, event_key,
            on_commit=lambda: self._remove_pending_event_row(
                widget_id, event_key,
            ),
        )

    def _open_target_retarget_picker(
        self, widget_id: str, event_key: str, m_idx: int,
    ) -> None:
        """``▾`` / target box on a committed entry — opens a picker of the
        CTkScript components attached to this widget (and the window) and
        REPLACES the entry's target in place, resetting the method since
        the new class has its own pool of functions. Same component list
        the pending ``Add target…`` picker uses.
        """
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        entries = node.handlers.get(event_key, []) or []
        if m_idx >= len(entries):
            return
        document = self.project.find_document_for_widget(widget_id)
        if document is None:
            return
        from app.io.scripts import iter_script_call_targets
        from app.ui.properties_panel.constants import menu_style
        comp_targets = iter_script_call_targets(node, document)
        menu = tk.Menu(self.tree, tearoff=0, **menu_style())
        if not comp_targets:
            # Inert dim hint, NOT state="disabled" (Windows etches a 3D
            # "ghost" on disabled menu entries — the "ჯადო" quirk).
            menu.add_command(
                label="No scripts attached — add one in the Scripts group",
                command=lambda: None,
                foreground="#6a6a6a", activeforeground="#6a6a6a",
                activebackground="#2d2d30",
            )
        else:
            current = entries[m_idx] if isinstance(entries[m_idx], dict) else {}
            cur_cls, cur_scope = current.get("class", ""), current.get("scope")
            for _script_rel, cls, scope in comp_targets:
                label_scope = "this widget" if scope == "widget" else "window"
                mark = "● " if (cls == cur_cls and scope == cur_scope) else "    "
                menu.add_command(
                    label=f"{mark}{cls}  ({label_scope})",
                    command=lambda c=cls, s=scope:
                    self._retarget_handler(widget_id, event_key, m_idx, c, s),
                )
        try:
            menu.tk_popup(
                self.tree.winfo_pointerx(),
                self.tree.winfo_pointery(),
            )
        finally:
            menu.grab_release()

    def _retarget_handler(
        self, widget_id: str, event_key: str, m_idx: int,
        class_name: str, scope: str,
    ) -> None:
        """Replace the entry at ``m_idx`` with a fresh ``script_call`` for
        the picked class — method reset to empty so the Function row's
        picker offers the new class's public methods. Direct mutation,
        same no-undo policy as ``_set_handler_method_*``.
        """
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        entries = node.handlers.get(event_key)
        if entries is None or m_idx >= len(entries):
            return
        entries[m_idx] = {
            "kind": "script_call", "class": class_name,
            "method": "", "scope": scope,
        }
        self.project.event_bus.publish(
            "widget_handler_changed", widget_id, event_key, "",
        )

    def _open_function_picker(
        self, widget_id: str, event_key: str, m_idx: int,
    ) -> None:
        """Single-click on the ``Function:`` child row opens a
        cascade menu of the attached CTkScript component's public
        methods. Picking replaces the entry's method in place — no
        auto-stub creation, no rebind plumbing.
        """
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        entries = node.handlers.get(event_key, []) or []
        if m_idx >= len(entries):
            return
        entry = entries[m_idx]
        if not (
            isinstance(entry, dict)
            and entry.get("kind") == "script_call"
        ):
            return
        from pathlib import Path

        from app.core.script_paths import user_scripts_dir
        from app.io.scripts import (
            parse_handler_methods, resolve_script_component,
        )
        from app.ui.properties_panel.constants import menu_style
        menu = tk.Menu(self.tree, tearoff=0, **menu_style())
        cls = entry.get("class", "")
        methods: list[str] = []
        scripts_dir = user_scripts_dir(
            getattr(self.project, "path", None),
        )
        # The attachment already stores the exact file path — resolve
        # it (honoring the entry's scope) instead of rescanning the
        # whole scripts/ folder, so two files sharing a class name
        # can't be confused.
        document = self.project.find_document_for_widget(widget_id)
        comp = resolve_script_component(
            node, document, cls, entry.get("scope"),
        )
        if comp is not None and scripts_dir is not None:
            methods = [
                m for m in parse_handler_methods(
                    Path(scripts_dir) / comp["script"], cls,
                )
                if m not in ("on_start", "on_close")
            ]
        if not methods:
            # Normal-state no-op, not state="disabled" — Windows
            # native menu draw renders disabled items as etched
            # ghost text on the dark theme ("ჯადო"). Dimmed
            # foreground + inert command gives a clean hint instead.
            menu.add_command(
                label=(
                    f"No public methods in {cls}" if cls
                    else "Script not set"
                ),
                command=lambda: None,
                foreground="#777777", activeforeground="#777777",
                activebackground="#2d2d30",
            )
        for method_name in methods:
            menu.add_command(
                label=method_name,
                command=lambda m=method_name:
                self._set_handler_method_script(
                    widget_id, event_key, m_idx, m,
                ),
            )
        try:
            menu.tk_popup(
                self.tree.winfo_pointerx(),
                self.tree.winfo_pointery(),
            )
        finally:
            menu.grab_release()

    def _set_handler_method_script(
        self, widget_id: str, event_key: str,
        m_idx: int, method_name: str,
    ) -> None:
        """Set a ``script_call`` entry's method (a public method on the
        attached CTkScript class). Direct mutation; publishes
        ``widget_handler_changed``."""
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        entries = node.handlers.get(event_key)
        if entries is None or m_idx >= len(entries):
            return
        entry = entries[m_idx]
        if not isinstance(entry, dict):
            return
        entry["method"] = method_name
        self.project.event_bus.publish(
            "widget_handler_changed", widget_id, event_key, method_name,
        )

    def _begin_param_edit(
        self, widget_id: str, event_key: str,
        m_idx: int, p_idx: int, target_iid: str,
    ) -> None:
        """Single-click on a ``<param>:`` child row opens an inline
        Entry editor over the value cell. Tab / Enter commit the new
        value into the handler entry's ``args[p_idx]["value"]``; Escape
        cancels. Type-coerced on commit (int / float / bool); empty
        strings stay empty. ``target_iid`` is the clicked row's iid
        (passed by the click router so we don't search the meta map
        for it again).
        """
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        entries = node.handlers.get(event_key)
        if entries is None or m_idx >= len(entries):
            return
        entry = entries[m_idx]
        if not isinstance(entry, dict):
            return
        args = entry.get("args", []) or []
        if p_idx >= len(args):
            return
        try:
            bbox = self.tree.bbox(target_iid, "value")
        except tk.TclError:
            return
        if not bbox:
            return
        x, y, w, h = bbox
        editor = tk.Entry(
            self.tree, borderwidth=0,
            highlightthickness=1,
            highlightbackground="#3b3b3b",
            highlightcolor="#5b5b5b",
        )
        current = args[p_idx].get("value", "")
        editor.insert(0, str(current))
        editor.place(x=x, y=y, width=w, height=h)
        editor.focus_set()
        editor.select_range(0, "end")

        def _commit(_event=None):
            text = editor.get()
            arg_type = args[p_idx].get("type", "str")
            try:
                if arg_type == "int":
                    args[p_idx]["value"] = int(text) if text else 0
                elif arg_type == "float":
                    args[p_idx]["value"] = float(text) if text else 0.0
                elif arg_type == "bool":
                    args[p_idx]["value"] = text.strip().lower() in (
                        "true", "1", "yes",
                    )
                else:
                    args[p_idx]["value"] = text
            except ValueError:
                args[p_idx]["value"] = text
            try:
                editor.destroy()
            except tk.TclError:
                pass
            self.project.event_bus.publish(
                "widget_handler_changed", widget_id, event_key, "",
            )

        def _cancel(_event=None):
            try:
                editor.destroy()
            except tk.TclError:
                pass

        editor.bind("<Return>", _commit)
        editor.bind("<Tab>", _commit)
        editor.bind("<FocusOut>", _commit)
        editor.bind("<Escape>", _cancel)

    def _reorder_event_method(
        self, widget_id: str, event_key: str,
        from_index: int, to_index: int,
    ) -> None:
        """Push a ``ReorderHandlerCommand`` for the method at
        ``from_index`` → ``to_index``. The command itself publishes
        ``widget_handler_changed`` after applying, which fans out to
        the panel + workspace so neither has to refresh by hand.
        """
        from app.core.commands import ReorderHandlerCommand
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        methods = node.handlers.get(event_key)
        if not methods or not (0 <= to_index < len(methods)):
            return
        cmd = ReorderHandlerCommand(
            widget_id, event_key, from_index, to_index,
        )
        cmd.redo(self.project)
        self.project.history.push(cmd)

    def _delete_event_action(
        self, widget_id: str, event_key: str,
        index: int, method_name,
    ) -> None:
        """Drop one handler entry — direct unbind, undoable in one
        step. No dialog, no file mutation; the behavior file is the
        user's source of truth, so a ``def`` they wrote stays put
        even if no widget binds it. Re-bind via ``[+]`` puts it
        back.
        """
        from app.core.commands import UnbindHandlerCommand
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        methods = node.handlers.get(event_key)
        if not methods or index >= len(methods):
            return
        if methods[index] != method_name:
            return
        cmd = UnbindHandlerCommand(
            widget_id, event_key, method_name, index,
        )
        cmd.redo(self.project)
        self.project.history.push(cmd)

    # ------------------------------------------------------------------
    # v1.10.8 — Object Reference toggle handlers
    # ------------------------------------------------------------------
    def _component_target(self, node):
        """Object that holds ``attached_components`` for ``node`` — the
        active Document for the Window node, else the WidgetNode."""
        from app.core.project import WINDOW_ID
        if self.project is None or node is None:
            return None
        if node.id == WINDOW_ID:
            return self.project.active_document
        return node

    def _open_component_picker(self, node) -> None:
        """Pop a menu of CTkScript classes from the project's
        ``scripts/`` folder that aren't already attached to ``node``;
        picking one attaches it."""
        import tkinter as tk

        from app.core.script_paths import user_scripts_dir
        from app.io.scripts import find_attachable_scripts
        from app.ui.properties_panel.constants import menu_style
        target = self._component_target(node)
        if target is None:
            return
        attached = {
            c.get("class") for c in (target.attached_components or [])
        }
        found = find_attachable_scripts(
            user_scripts_dir(getattr(self.project, "path", None)),
        )
        available = [(p, c) for (p, c) in found if c not in attached]
        menu = tk.Menu(self.tree, tearoff=0, **menu_style())
        menu.add_command(
            label="✚  New script…",
            command=lambda n=node: self._create_and_attach_script(n),
        )
        if available:
            menu.add_separator()
            for path, cls in available:
                menu.add_command(
                    label=f"{cls}  ({path})",
                    command=lambda p=path, c=cls:
                    self._attach_script_component(node, p, c),
                )
        try:
            menu.tk_popup(
                self.tree.winfo_pointerx(), self.tree.winfo_pointery(),
            )
        finally:
            menu.grab_release()

    def _create_and_attach_script(self, node) -> None:
        """Prompt for a script name (any style — normalized to a
        PascalCase class), create ``scripts/<snake>.py`` with a CTkScript
        skeleton, attach it to ``node``, and open it in the editor — so
        the user never hand-creates the file."""
        from pathlib import Path

        from app.core.script_paths import user_scripts_dir
        from app.io.scripts import create_user_script, find_attachable_scripts
        from app.ui.dialogs.message import show_error, show_info
        from app.ui.dialogs.new_script import NewScriptDialog
        parent = self.winfo_toplevel()
        scripts_dir = user_scripts_dir(getattr(self.project, "path", None))
        if scripts_dir is None:
            show_info(
                "Save first",
                "Save the project before creating scripts.",
                parent=parent,
            )
            return
        # Themed prompt that takes the name in any style, normalizes it
        # to a PascalCase class + snake_case file and previews both live;
        # it refuses names whose class already exists in ``scripts/``.
        existing = {
            cls: path
            for path, cls in find_attachable_scripts(scripts_dir)
        }
        dlg = NewScriptDialog(parent, existing)
        name = dlg.result
        if not name:
            return
        result = create_user_script(scripts_dir, name)
        if result is None:
            show_error(
                "Couldn't create script",
                "Failed to write the new script file.",
                parent=parent,
            )
            return
        rel, cls = result
        self._attach_script_component(node, rel, cls)
        self._launch_script_editor(Path(scripts_dir) / rel)

    def _open_script_in_editor(self, rel_path: str) -> None:
        """Open an attached script in the user's editor (F7-style)."""
        from pathlib import Path

        from app.core.script_paths import user_scripts_dir
        scripts_dir = user_scripts_dir(getattr(self.project, "path", None))
        if scripts_dir is None or not rel_path:
            return
        self._launch_script_editor(Path(scripts_dir) / rel_path)

    def _launch_script_editor(self, file_path) -> None:
        """Open a script with the project folder as workspace, so
        VS Code / PyCharm pick up ``pyrightconfig.json`` + the root
        ``ctkmaker.py`` sidecar (import resolution + autocomplete)
        without the user opening the folder by hand."""
        from app.core.settings import load_settings
        from app.io.scripts import (
            launch_editor_from_settings, resolve_project_root_for_editor,
        )
        launch_editor_from_settings(
            file_path,
            None,
            resolve_project_root_for_editor(self.project),
            load_settings(),
        )

    def _attach_script_component(self, node, script: str, cls: str) -> None:
        """Attach a CTkScript class to ``node`` (widget or window) via an
        undoable command. No-op if that class is already attached."""
        if self.project is None:
            return
        target = self._component_target(node)
        if target is None:
            return
        existing = getattr(target, "attached_components", None) or []
        if any(c.get("class") == cls for c in existing):
            return
        from app.core.commands import AttachComponentCommand
        cmd = AttachComponentCommand(node.id, {"script": script, "class": cls})
        cmd.redo(self.project)
        self.project.history.push(cmd)
        self._rebuild()

    def _detach_script_component(self, node, cls: str) -> None:
        """Detach the CTkScript class ``cls`` from ``node`` via an
        undoable command."""
        if self.project is None:
            return
        from app.core.commands import DetachComponentCommand
        cmd = DetachComponentCommand(node.id, cls)
        cmd.redo(self.project)
        self.project.history.push(cmd)
        self._rebuild()

    def _show_local_var_menu(self, event) -> None:
        """Right-click on a Local Variables row → "Open Variables
        Editor" entry that routes to the shared bus-open path. Same
        mechanism the chrome strip uses (chrome.py:_on_vars_click)."""
        doc_id = self.project.active_document_id if self.project else None
        menu = tk.Menu(self.tree, tearoff=0)
        menu.add_command(
            label="Open Variables Editor",
            command=lambda: self.project.event_bus.publish(
                "request_open_variables_window", "local", doc_id,
            ),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_binding_menu_for(self, event, pname: str, prop: dict) -> None:
        """Click handler for the per-row 🔗 button. Resolves the
        current widget, then defers to the shared menu builder so
        the bind / unbind flows match the right-click path."""
        if self.current_id is None:
            return
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        self._show_binding_menu(event, pname, prop, node)

    def _show_binding_menu(self, event, pname, prop, node) -> None:
        from app.core.variables import (
            compatible_var_types,
            parse_var_token,
        )
        current = node.properties.get(pname)
        bound_var_id = parse_var_token(current)
        bound_entry = (
            self.project.get_variable(bound_var_id)
            if bound_var_id else None
        )
        ptype = prop.get("type", "")
        compat_types = compatible_var_types(ptype)

        # disabledforeground MUST be set explicitly on Windows —
        # the system default uses a 3D etched effect that renders as
        # ghost-doubled text on dark backgrounds. Flat grey kills the
        # bevel and matches the rest of the dark UI.
        menu_style = dict(
            bg="#2d2d30", fg="#cccccc",
            activebackground="#094771",
            activeforeground="#ffffff",
            disabledforeground="#777777",
            bd=0, borderwidth=0, relief="flat",
            font=ui_font(10),
        )
        menu = tk.Menu(self.tree, tearoff=0, **menu_style)

        if bound_entry is not None:
            menu.add_command(
                label=f"Unbind from: {bound_entry.name}",
                command=lambda: self._unbind_property(pname, prop),
            )
            menu.add_separator()

        # Find the document this widget belongs to so we know which
        # locals to expose in the bind menu. The properties panel
        # only shows the active document's widgets, but we look the
        # owner up explicitly so a stale selection still resolves to
        # the right scope.
        owner_doc = self.project.find_document_for_widget(node.id)
        owner_doc_id = owner_doc.id if owner_doc is not None else None

        # Variables visible from this widget, grouped by scope.
        global_vars = [
            v for v in self.project.iter_variables(scope="global")
            if v.type in compat_types and v.id != bound_var_id
        ]
        local_vars = [
            v for v in self.project.iter_variables(
                scope="local", document_id=owner_doc_id,
            )
            if v.type in compat_types and v.id != bound_var_id
        ]

        bind_submenu = tk.Menu(menu, tearoff=0, **menu_style)
        # Section-header label colours match the toolbar / Add button
        # accents. Headers + the "(no …)" placeholder use a no-op
        # command instead of ``state="disabled"`` because Windows
        # native menus draw disabled items with an etched-3D shadow
        # that looks like double-stamped text on dark backgrounds.
        # ``disabledforeground`` doesn't kill the bevel either.
        # Trade-off: clicking a header closes the menu. Acceptable —
        # users target the variable items below, not the labels.
        global_header_fg = "#0e639c"
        local_header_fg = "#8a541a"
        muted_label_fg = "#777777"
        if not global_vars and not local_vars:
            type_hint = " / ".join(compat_types)
            visible_total = sum(1 for _ in self.project.iter_variables(
                document_id=owner_doc_id,
            ))
            if visible_total == 0:
                bind_submenu.add_command(
                    label="(no variables yet)",
                    foreground=muted_label_fg,
                    activeforeground=muted_label_fg,
                    activebackground="#2d2d30",
                    command=lambda: None,
                )
            else:
                bind_submenu.add_command(
                    label=f"(no {type_hint} variables)",
                    foreground=muted_label_fg,
                    activeforeground=muted_label_fg,
                    activebackground="#2d2d30",
                    command=lambda: None,
                )
            bind_submenu.add_separator()
        else:
            if global_vars:
                bind_submenu.add_command(
                    label="Global",
                    foreground=muted_label_fg,
                    activeforeground=muted_label_fg,
                    activebackground="#2d2d30",
                    command=lambda: None,
                )
                for v in global_vars:
                    bind_submenu.add_command(
                        label=f"{v.name}  ({v.type})",
                        foreground=global_header_fg,
                        activeforeground="#ffffff",
                        command=(
                            lambda var_id=v.id:
                            self._bind_property(pname, prop, var_id)
                        ),
                    )
            if local_vars:
                if global_vars:
                    bind_submenu.add_separator()
                doc_label = (
                    owner_doc.name if owner_doc is not None else "Local"
                )
                bind_submenu.add_command(
                    label=f"Local: {doc_label}",
                    foreground=muted_label_fg,
                    activeforeground=muted_label_fg,
                    activebackground="#2d2d30",
                    command=lambda: None,
                )
                for v in local_vars:
                    bind_submenu.add_command(
                        label=f"{v.name}  ({v.type})",
                        foreground=local_header_fg,
                        activeforeground="#ffffff",
                        command=(
                            lambda var_id=v.id:
                            self._bind_property(pname, prop, var_id)
                        ),
                    )
            bind_submenu.add_separator()
        bind_submenu.add_command(
            label="+ Create new global variable…",
            foreground=global_header_fg,
            activeforeground="#1177bb",
            command=lambda: self._create_and_bind(
                pname, prop, scope="global",
            ),
        )
        bind_submenu.add_command(
            label="+ Create new local variable…",
            foreground=local_header_fg,
            activeforeground="#a0651e",
            command=lambda: self._create_and_bind(
                pname, prop, scope="local",
                document_id=owner_doc_id,
            ),
        )
        menu.add_cascade(label="Bind to variable", menu=bind_submenu)
        menu.add_separator()
        menu.add_command(
            label="Open Variables window…",
            command=self._open_variables_window_from_menu,
        )

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass

    def _bind_property(self, pname: str, prop: dict, var_id: str) -> None:
        """Replace the property's literal value with a ``var:<uuid>``
        token. Pushes a ``ChangePropertyCommand`` so undo / redo work,
        then rebuilds the panel so the cell re-renders as a chip and
        the editor overlay tears down cleanly.
        """
        from app.core.commands import ChangePropertyCommand
        from app.core.variables import make_var_token
        from app.ui.dialogs.message import ask_ok_cancel
        if self.current_id is None:
            return
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        # Boolean property + int variable whose value isn't 0 / 1 is
        # technically "compatible" (Tk's checkbox/switch use IntVar
        # under the hood), but Tk only treats onvalue=1 / offvalue=0
        # as meaningful. Anything else renders as off, and the first
        # click overwrites the variable to 1 — silently losing the
        # original value. Warn before binding so the user can pick
        # between fixing the variable's default and binding anyway.
        entry = self.project.get_variable(var_id)
        if (
            entry is not None
            and prop.get("type") == "boolean"
            and entry.type == "int"
            and str(entry.default).strip().lower()
            not in ("0", "1", "true", "false")
        ):
            ok = ask_ok_cancel(
                "Bind to non-boolean int?",
                (
                    f"Variable '{entry.name}' holds {entry.default!r}, "
                    f"which isn't a boolean value (0 / 1).\n\n"
                    "Tk's switch / checkbox only recognises 0 (off) and "
                    "1 (on). The widget will render as off, and the "
                    "first click will overwrite the variable to 1 — "
                    f"the current value ({entry.default}) will be lost."
                    "\n\nBind anyway?"
                ),
                parent=self.winfo_toplevel(),
                ok_text="Bind anyway",
            )
            if not ok:
                return
        before = node.properties.get(pname)
        token = make_var_token(var_id)
        if before == token:
            return
        self.project.update_property(self.current_id, pname, token)
        self.project.history.push(
            ChangePropertyCommand(self.current_id, pname, before, token),
        )
        # Full rebuild — a literal-value editor overlay was just
        # replaced by a chip, and the per-cell refresh path can't
        # destroy overlays cleanly across editor types.
        self._rebuild()

    def _unbind_property(self, pname: str, prop: dict) -> None:
        """Drop the ``var:<uuid>`` token and restore the descriptor's
        default literal so the row falls back to its normal editor.
        """
        from app.core.commands import ChangePropertyCommand
        if self.current_id is None:
            return
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        descriptor = self._current_descriptor()
        if descriptor is None:
            return
        before = node.properties.get(pname)
        # Fall back to the descriptor's declared default — keeps the
        # property type valid (no dangling None) and renders cleanly
        # in the literal editor.
        default = descriptor.default_properties.get(pname, "")
        self.project.update_property(self.current_id, pname, default)
        self.project.history.push(
            ChangePropertyCommand(self.current_id, pname, before, default),
        )
        self._rebuild()

    def _create_and_bind(
        self, pname: str, prop: dict,
        scope: str = "global",
        document_id: str | None = None,
    ) -> None:
        """Open the Variables Add dialog with a name suggestion
        derived from the property, then bind on success. ``scope``
        picks where the new variable lands — globals are project-wide,
        locals attach to the given document (which must own the
        currently selected widget for the binding to be reachable).
        """
        from app.ui.variables_window import VariableEditDialog
        from app.core.commands import AddVariableCommand
        from app.core.variables import compatible_var_types
        suggestion = self._suggest_var_name(pname)
        if scope == "local":
            doc = (
                self.project.get_document(document_id)
                if document_id else self.project.active_document
            )
            existing = {
                v.name for v in (doc.local_variables if doc else [])
            }
            title = "Create local variable + bind"
        else:
            existing = {v.name for v in self.project.variables}
            title = "Create global variable + bind"
        # Default type guess based on the property's editor kind, then
        # constrain the Type dropdown to the property's compatibility
        # set so the user can't, say, declare a String variable from a
        # Boolean row's "+ Create new …" entry.
        ptype = prop.get("type", "")
        compat_types = compatible_var_types(ptype)
        guess_type = {
            "boolean": "bool",
            "number": "int",
            "color": "color",
        }.get(ptype, "str")
        if guess_type not in compat_types:
            guess_type = compat_types[0]
        dialog = VariableEditDialog(
            self.winfo_toplevel(),
            title=title,
            initial_name=suggestion,
            initial_type=guess_type,
            initial_default="",
            existing_names=existing,
            allowed_types=compat_types,
        )
        dialog.wait_window()
        if dialog.result is None:
            return
        name, var_type, default = dialog.result
        entry = self.project.add_variable(
            name, var_type, default,
            scope=scope, document_id=document_id,
        )
        # Index in the right scope's list — locals on doc, globals on
        # project — so undo restores the entry to the correct spot.
        if scope == "local":
            doc = (
                self.project.get_document(document_id)
                if document_id else self.project.active_document
            )
            target_len = len(doc.local_variables) if doc else 0
        else:
            target_len = len(self.project.variables)
        self.project.history.push(
            AddVariableCommand(
                entry.to_dict(), target_len - 1,
                scope=scope, document_id=document_id,
            ),
        )
        self._bind_property(pname, prop, entry.id)

    def _suggest_var_name(self, pname: str) -> str:
        """Build a friendly variable name guess from the widget name
        + property name (e.g. button_1.text -> button_1_text)."""
        if self.current_id is None:
            return pname
        node = self.project.get_widget(self.current_id)
        if node is None or not node.name:
            return pname
        return f"{node.name}_{pname}"

    def _open_variables_window_from_menu(self) -> None:
        """Try to flip the MainWindow's Variables window var so it
        opens (or focuses if already open). Falls back silently if
        the parent doesn't expose the toggle (used in standalone
        tests of the panel)."""
        top = self.winfo_toplevel()
        toggle = getattr(top, "_on_f11_variables_window", None)
        if callable(toggle):
            try:
                toggle()
            except Exception:
                pass

