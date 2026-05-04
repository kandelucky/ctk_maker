"""Object Tree inspector — hierarchical widget list.

A floating Toplevel that shows the entire project tree with each
widget's display name, type, short ID, and sibling layer index.
Selection is two-way: clicking a row selects the widget in the
project; selecting a widget elsewhere highlights the matching row.

Event-bus subscriptions keep the tree in sync with add/remove/
reparent/rename operations.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from app.core.commands import (
    BulkAddCommand,
    BulkToggleFlagCommand,
    DeleteMultipleCommand,
    DeleteWidgetCommand,
    RenameCommand,
    ReparentCommand,
    ToggleFlagCommand,
    build_bulk_add_entries,
    paste_target_parent_id,
    push_zorder_history,
)
from app.ui.dialogs import RenameDialog
from app.ui.icons import load_icon, load_tk_icon
from app.widgets.layout_schema import normalise_layout_type
from app.widgets.registry import all_descriptors, get_descriptor
from app.core.platform_compat import MOD_KEY, MOD_LABEL_PLUS

if TYPE_CHECKING:
    from app.core.project import Project
    from app.core.widget_node import WidgetNode

BG = "#1e1e1e"
PANEL_BG = "#252526"
TREE_BG = "#1e1e1e"
TREE_FG = "#cccccc"
TREE_SELECTED_BG = "#094771"
TREE_HEADING_BG = "#2d2d30"
TREE_HEADING_FG = "#cccccc"
DROP_TARGET_BG = "#0c5a8c"
DROP_INVALID_BG = "#5c2020"
HIDDEN_ROW_FG = "#666666"

EYE_VISIBLE = "👁"
EYE_HIDDEN = ""
LOCK_ON = "🔒"
LOCK_OFF = ""
ARROW_EXPANDED = "▼ "
ARROW_COLLAPSED = "▶ "
ARROW_LEAF = "   "
INDENT_STR = "      "  # 6 spaces per depth level — clearer nesting
TREE_ROW_HEIGHT = 22
TREE_FONT_SIZE = 10

DIALOG_W = 360
DIALOG_H = 460
DRAG_THRESHOLD = 5

FILTER_ALL_LABEL = "All types"

_TYPE_INITIALS: dict[str, str] = {
    "CTkButton":          "Btn",
    "CTkLabel":           "Lbl",
    "CTkEntry":           "Ent",
    "CTkTextbox":         "Txt",
    "CTkCheckBox":        "Chk",
    "CTkRadioButton":     "Rad",
    "CTkSwitch":          "Sw",
    "CTkSegmentedButton": "Seg",
    "CTkSlider":          "Sld",
    "CTkProgressBar":     "Bar",
    "CTkComboBox":        "Cmb",
    "CTkOptionMenu":      "Opt",
    "CTkScrollableFrame": "ScF",
    "CTkTabview":         "Tab",
    "Image":              "Img",
}
_FRAME_LAYOUT_INITIALS: dict[str, str] = {
    "place": "Frm",
    "vbox":  "VFr",
    "hbox":  "HFr",
    "grid":  "GFr",
}

CTX_MENU_STYLE = dict(
    bg="#2d2d30",
    fg="#cccccc",
    activebackground="#094771",
    activeforeground="#ffffff",
    disabledforeground="#888888",
    bd=0,
    borderwidth=0,
    activeborderwidth=0,
    relief="flat",
    font=("Segoe UI", 11),
)


class ObjectTreePanel(ctk.CTkFrame):
    """Embeddable Object Tree panel.

    The same logic previously lived inside a floating
    `ObjectTreeWindow(CTkToplevel)`; now it's a plain CTkFrame so
    the main window can dock it into the right sidebar above the
    Properties panel. `ObjectTreeWindow` (at the bottom of this file)
    is a thin Toplevel wrapper that composes a panel inside itself
    for users who still want a detachable floating view.
    """

    def __init__(
        self,
        parent,
        project: "Project",
    ):
        super().__init__(parent, fg_color=BG, corner_radius=0)

        self.project = project
        self._syncing = False  # guard against selection feedback loops

        self._filter_var = tk.StringVar(value=FILTER_ALL_LABEL)
        self._filter_var.trace_add("write", lambda *_a: self._on_filter_changed())
        self._search_text: str = ""
        self._search_entry: ctk.CTkEntry | None = None
        self._filter_type: str | None = None
        self._filter_menu: ctk.CTkOptionMenu | None = None
        self._display_to_type: dict[str, str] = {}
        # Debounce id for the search entry — each keystroke cancels
        # the previous after() and schedules a fresh one 200ms out so
        # we refresh once per burst of typing, not per character.
        self._search_refresh_id: str | None = None

        # Expand/collapse state for containers. None = expand by
        # default; a node id in this set means "user collapsed me".
        from app.core.settings import load_settings
        self._collapsed_ids: set[str] = set(
            load_settings().get("ui_object_tree_collapsed", [])
        )
        # Per-virtual-group-row depth — populated on every refresh
        # so ``_click_on_arrow`` can hit-test the arrow region for
        # synthetic ``group:<gid>`` rows (which have no widget node
        # backing them, so ``_node_depth`` doesn't apply).
        self._group_row_depths: dict[str, int] = {}

        # Row images for the visibility toggle (must be tk.PhotoImage
        # because ttk.Treeview's image= parameter rejects CTkImage).
        self._eye_icon = load_tk_icon("eye", size=16, color="#cccccc")
        self._eye_off_icon = load_tk_icon("eye-off", size=16, color="#666666")
        # Cascade-dimmed eye: same ``eye`` glyph, dim colour. Used
        # when a node's own ``visible=True`` but a hidden ancestor
        # cascades the row to "effective hidden" — the user can tell
        # at a glance that this row IS being hidden, but not because
        # of an explicit toggle on this node.
        self._eye_dim_icon = load_tk_icon("eye", size=16, color="#666666")
        self._window_icon_active = load_tk_icon(
            "app-window", size=16, color="#cccccc",
        )
        self._window_icon_dim = load_tk_icon(
            "app-window", size=16, color="#666666",
        )

        # Drag-to-reparent / reorder state
        self._drag_source_id: str | None = None
        self._drag_press_y: int = 0
        self._drag_active: bool = False
        self._drop_info: dict | None = None
        self._insert_line: tk.Frame | None = None
        self._insert_line_visible: bool = False
        self._highlighted_iid: str | None = None

        self._build_style()
        self._build_tree()

        # Structural events need a full rebuild — the set of rows or
        # their order is changing. Cosmetic events (rename / visibility
        # / lock) update a handful of cells in place so typing, toggling
        # and click-heavy UX stay snappy even on bigger projects.
        self._bus_subs: list[tuple[str, Callable]] = [
            ("widget_added", self._on_project_changed),
            ("widget_removed", self._on_project_changed),
            ("widget_reparented", self._on_project_changed),
            ("widget_z_changed", self._on_project_changed),
            ("widget_renamed", self._on_widget_renamed),
            ("widget_visibility_changed", self._on_widget_visibility_changed),
            ("widget_locked_changed", self._on_widget_locked_changed),
            ("widget_group_changed", self._on_widget_group_changed),
            ("selection_changed", self._on_selection_changed),
            ("active_document_changed", self._on_project_changed),
            # layout_type changes the container's name suffix, so we
            # need to repaint the affected row.
            ("property_changed", self._on_property_changed),
            # Phase 2 — handler list mutations need to flip the ▶
            # marker on / off in the affected row. Cheap repaint via
            # the same renamed-row path since both kinds of change
            # only touch the name cell text. The handler change
            # publish sends (widget_id, event_key, method_name); the
            # rename path sends (widget_id, new_name) — separate
            # subscriber that ignores the extras keeps the event
            # bus from crashing on signature mismatch.
            ("widget_handler_changed", self._on_widget_handler_changed),
        ]
        bus = self.project.event_bus
        for event_name, handler in self._bus_subs:
            bus.subscribe(event_name, handler)

        self.tree.bind(
            "<Escape>", lambda _e: self.project.select_widget(None),
        )
        # Copy / paste — widget-level bindings on the tree so the
        # shortcut only fires when the tree has keyboard focus (typing
        # into the search entry still does plain text copy/paste).
        # Latin keysym bindings (standard English keyboard layout):
        self.tree.bind(f"<{MOD_KEY}-c>", self._on_copy_shortcut)
        self.tree.bind(f"<{MOD_KEY}-C>", self._on_copy_shortcut)
        self.tree.bind(f"<{MOD_KEY}-v>", self._on_paste_shortcut)
        self.tree.bind(f"<{MOD_KEY}-V>", self._on_paste_shortcut)
        # Non-Latin layout fallback: MainWindow's
        # bind_all(f"<{MOD_KEY}-KeyPress>") routes by hardware keycode and
        # emits <<Copy>>/<<Paste>> virtual events on the focused widget
        # — when the tree has focus, that's the tree.
        self.tree.bind("<<Copy>>", self._on_copy_shortcut)
        self.tree.bind("<<Paste>>", self._on_paste_shortcut)
        self.refresh()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("default")
        except tk.TclError:
            pass
        # Dark-theme scrollbar — tk.Scrollbar on Windows uses the OS
        # theme and ignores colour kwargs, so we route through a
        # styled ttk.Scrollbar instead.
        style.configure(
            "ObjectTree.Vertical.TScrollbar",
            background="#3a3a3a",
            troughcolor="#1a1a1a",
            bordercolor=BG,
            arrowcolor="#888888",
            lightcolor="#3a3a3a",
            darkcolor="#3a3a3a",
            relief="flat",
        )
        style.map(
            "ObjectTree.Vertical.TScrollbar",
            background=[
                ("active", "#4a4a4a"),
                ("pressed", "#5a5a5a"),
            ],
        )
        style.configure(
            "ObjectTree.Treeview",
            background=TREE_BG,
            foreground=TREE_FG,
            fieldbackground=TREE_BG,
            bordercolor=BG,
            borderwidth=0,
            rowheight=TREE_ROW_HEIGHT,
            font=("Segoe UI", TREE_FONT_SIZE),
            indent=0,  # kill depth indentation — we fake it in the name col
        )
        # Tk Treeview's default style.map for foreground/background
        # contains a `("!disabled", "!selected")` entry that wins over
        # tag_configure colors — well-known bug. Filter it out so tags
        # like ``group-row`` keep their orange foreground when selected.
        def _fixed_map(option: str):
            return [
                elm for elm in style.map(
                    "ObjectTree.Treeview", query_opt=option,
                )
                if elm[:2] != ("!disabled", "!selected")
            ]
        style.map(
            "ObjectTree.Treeview",
            background=_fixed_map("background") + [
                ("selected", TREE_SELECTED_BG),
            ],
            foreground=_fixed_map("foreground") + [
                ("selected", "#ffffff"),
            ],
        )
        style.configure(
            "ObjectTree.Treeview.Heading",
            background=TREE_HEADING_BG,
            foreground=TREE_HEADING_FG,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
        )
        style.layout(
            "ObjectTree.Treeview",
            [
                ("ObjectTree.Treeview.treearea", {"sticky": "nswe"}),
            ],
        )

    def _build_tree(self) -> None:
        # The Object Tree lives inside a vertical PanedWindow pane.
        # Locking propagation on the outer panel frame + the inner
        # container forces the PanedWindow sash to dictate height,
        # which in turn lets ttk.Treeview overflow properly and
        # engage the scrollbar instead of silently pushing the
        # container taller than its assigned pane size.
        self.pack_propagate(False)

        accent = self.project.get_accent_color()

        # Accent-coloured border wrap — 1px of the active document's
        # theme colour.
        wrap = tk.Frame(
            self, bg=BG,
            highlightthickness=0,
        )
        wrap.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        wrap.pack_propagate(False)
        self._accent_wrap = wrap

        container = tk.Frame(wrap, bg=BG, highlightthickness=0)
        container.pack(fill="both", expand=True, padx=6, pady=(8, 6))
        container.pack_propagate(False)
        self._tree_container = container

        # Active-document status strip — pinned to the BOTTOM of the
        # container. Shows which form is currently being edited.
        # Accent fg matches the border.
        doc_header = tk.Frame(
            container, bg=BG, highlightthickness=0, height=20,
        )
        doc_header.pack(side="bottom", fill="x", pady=(4, 0))
        doc_header.pack_propagate(False)
        self._doc_header_icon = load_tk_icon(
            "app-window", size=14, color=accent,
        )
        self._doc_header_icon_label = tk.Label(
            doc_header,
            image=self._doc_header_icon,
            bg=BG,
            borderwidth=0,
        )
        self._doc_header_icon_label.pack(side="left", padx=(2, 6))
        self._doc_header_label = tk.Label(
            doc_header,
            text="",
            bg=BG,
            fg=accent,
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self._doc_header_label.pack(side="left", fill="x", expand=True)
        for w in (doc_header, self._doc_header_label,
                  self._doc_header_icon_label):
            w.configure(cursor="hand2")
            w.bind("<Button-1>", self._on_doc_header_click)
        self._doc_header = doc_header

        # Filter row: dropdown (type) + entry (name search). Both
        # apply together (AND).
        filter_row = tk.Frame(container, bg=BG, highlightthickness=0)
        filter_row.pack(side="top", fill="x", pady=(0, 6))
        self._filter_menu = ctk.CTkOptionMenu(
            filter_row,
            values=[FILTER_ALL_LABEL],
            variable=self._filter_var,
            width=110, height=26,
            font=("Segoe UI", 10),
            dropdown_font=("Segoe UI", 10),
            fg_color="#2d2d2d", button_color="#2d2d2d",
            button_hover_color="#3a3a3a", corner_radius=3,
        )
        self._filter_menu.pack(side="left")

        # NOTE: we deliberately don't pass `textvariable` here.
        # CTkEntry's _activate_placeholder() checks
        # `self._textvariable == ""` which is always False when the
        # textvariable is a StringVar object, so placeholder text
        # never renders. We sync to `self._search_text` via a
        # <KeyRelease> binding instead.
        search_entry = ctk.CTkEntry(
            filter_row,
            placeholder_text="Search by name…",
            placeholder_text_color="#888888",
            height=26,
            corner_radius=3,
            font=("Segoe UI", 10),
            border_color="#3c3c3c", border_width=1,
            fg_color="#2d2d2d",
        )
        search_entry.pack(side="left", fill="x", expand=True, padx=(6, 4))
        search_entry.bind("<KeyRelease>", self._on_search_key, add="+")
        self._search_entry = search_entry

        search_icon = load_icon("search", size=14, color="#cccccc")
        ctk.CTkButton(
            filter_row, text="" if search_icon else "🔍",
            image=search_icon, width=26, height=26,
            corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=lambda: search_entry.focus_set(),
        ).pack(side="left")


        tree_row = tk.Frame(container, bg=BG, highlightthickness=0)
        tree_row.pack(side="top", fill="both", expand=True)
        tree_row.pack_propagate(False)
        self._tree_row = tree_row

        self.tree = ttk.Treeview(
            tree_row,
            columns=("lock", "name", "type", "layer"),
            show="tree headings",
            style="ObjectTree.Treeview",
            selectmode="extended",
        )
        # #0 hosts only the visibility icon (no text, no arrow).
        # style.configure(indent=0) keeps every row's image at the
        # same x regardless of tree depth.
        self.tree.heading("#0", text="👁")
        self.tree.heading("lock", text="🔒")
        self.tree.heading("name", text="Name")
        self.tree.heading("type", text="T")
        self.tree.heading("layer", text="Order")
        self.tree.column("#0", width=36, stretch=False, anchor="center")
        self.tree.column("lock", width=32, stretch=False, anchor="center")
        self.tree.column("name", width=160, stretch=True, anchor="w")
        self.tree.column("type", width=36, stretch=False, anchor="center")
        self.tree.column("layer", width=52, stretch=False, anchor="center")

        # CTkScrollbar — matches the Properties panel style so the
        # docked right sidebar reads consistently. Kwargs mirror the
        # Properties vscroll in panel.py.
        vscroll = ctk.CTkScrollbar(
            tree_row, orientation="vertical",
            command=self.tree.yview,
            width=10, corner_radius=4,
            fg_color="transparent", button_color="#3a3a3a",
            button_hover_color="#4a4a4a",
        )
        self.tree.configure(yscrollcommand=vscroll.set)

        # Pack the scrollbar FIRST so tree's `expand=True` doesn't
        # eat the horizontal space that the scrollbar needs.
        vscroll.pack(side="right", fill="y", padx=(2, 0))
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.tag_configure("drop-target", background=DROP_TARGET_BG)
        self.tree.tag_configure("drop-invalid", background=DROP_INVALID_BG)
        self.tree.tag_configure("hidden-row", foreground=HIDDEN_ROW_FG)
        self.tree.tag_configure(
            "locked-row",
            font=("Segoe UI", TREE_FONT_SIZE, "italic"),
        )
        # Group rows — name text colored, NOT the row background
        # (background tint would override the tk selection highlight
        # and make the selected row indistinguishable from siblings).
        # Virtual parent gets the strong group orange; member rows
        # get a softer tint so they read as "in the group" without
        # competing with the parent.
        self.tree.tag_configure("group-row", foreground="#ff9f43")
        self.tree.tag_configure("group-member", foreground="#d49764")

        # Insertion line overlay — placed on demand above the tree row.
        self._insert_line = tk.Frame(tree_row, bg=DROP_TARGET_BG, height=2)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<ButtonPress-1>", self._on_drag_press, add="+")
        self.tree.bind("<B1-Motion>", self._on_drag_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self._on_drag_release, add="+")
        self.tree.bind("<Button-3>", self._on_right_click, add="+")
        self.tree.bind("<Double-Button-1>", self._on_double_click, add="+")

    def _save_collapsed_ids(self) -> None:
        from app.core.settings import save_setting
        save_setting("ui_object_tree_collapsed", list(self._collapsed_ids))

    # ------------------------------------------------------------------
    # Refresh / population
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._syncing = True
        try:
            self._rebuild_filter_options()
            self.tree.delete(*self.tree.get_children(""))
            self._group_row_depths.clear()
            self._refresh_doc_header()
            visible = self._compute_visible_set()
            active = self.project.active_document
            if active is not None:
                self._insert_children_with_groups(
                    active.root_widgets, depth=0, visible=visible,
                )
            self._apply_selection(self.project.selected_id)
        finally:
            self._syncing = False

    def _refresh_doc_header(self) -> None:
        """Update the 'currently editing' strip above the treeview
        to match the active document."""
        active = self.project.active_document
        if active is None or self._doc_header_label is None:
            return
        label = active.name or "Untitled"
        if active.is_toplevel:
            label = f"{label}  (Dialog)"
        self._doc_header_label.configure(text=label)

    def _on_doc_header_click(self, _event=None) -> None:
        """Clicking the doc header opens the active document's
        Window settings in the Properties panel."""
        from app.core.project import WINDOW_ID
        self.project.select_widget(WINDOW_ID)

    def _insert_document_row(self, doc, index: int) -> None:
        from app.core.project import WINDOW_ID
        is_active = doc.id == self.project.active_document_id
        icon = (
            self._window_icon_active if is_active
            else self._window_icon_dim
        )
        # Use a synthetic iid for document rows — distinct from the
        # virtual WINDOW_ID sentinel so selection handling can tell
        # them apart. Clicking one sets that document active.
        doc_iid = f"doc:{doc.id}"
        label = f"{doc.name}"
        if doc.is_toplevel:
            label = f"{label}  (Dialog)"
        if is_active:
            label = f"▸ {label}"
        else:
            label = f"  {label}"
        self.tree.insert(
            "", "end",
            iid=doc_iid,
            text="",
            image=icon if icon is not None else "",
            values=("", label, "Window", str(index)),
            tags=("doc-row",),
        )

    def _iter_active_widgets(self):
        """Yield every widget in the active document only, depth-first."""
        active = self.project.active_document
        if active is None:
            return

        def _walk(nodes):
            for node in nodes:
                yield node
                yield from _walk(node.children)

        yield from _walk(active.root_widgets)

    def _rebuild_filter_options(self) -> None:
        """Rebuild the filter dropdown so it only lists widget types
        actually present in the active document (sorted by display name).
        """
        if self._filter_menu is None:
            return
        type_names_in_project = {
            node.widget_type for node in self._iter_active_widgets()
        }
        entries: list[tuple[str, str]] = []
        for desc in all_descriptors():
            if desc.type_name in type_names_in_project:
                entries.append((desc.display_name, desc.type_name))
        entries.sort(key=lambda e: e[0].lower())
        values = [FILTER_ALL_LABEL] + [display for display, _ in entries]
        self._display_to_type = {display: type_name for display, type_name in entries}
        self._filter_menu.configure(values=values)
        # If the current selection is no longer valid (last widget of
        # that type just got removed), fall back to "All types".
        if self._filter_var.get() not in values:
            self._filter_var.set(FILTER_ALL_LABEL)

    def _compute_visible_set(self) -> set[str] | None:
        """Visible nodes under the current type filter AND name search.

        Returns `None` when both filters are inactive (show all).
        A node "matches" when:
            - its `widget_type` equals the selected type (or the
              type filter is "All types"), AND
            - its `node.name` contains the search text case-insensitively
              (or the search box is empty).
        Ancestors of every match stay visible so the tree hierarchy
        makes sense.
        """
        selected = self._filter_var.get()
        search = self._search_text.strip().lower()

        type_name: str | None
        if selected == FILTER_ALL_LABEL:
            type_name = None
        else:
            type_name = self._display_to_type.get(selected)
        self._filter_type = type_name

        if type_name is None and not search:
            return None

        visible: set[str] = set()
        for node in self._iter_active_widgets():
            if type_name is not None and node.widget_type != type_name:
                continue
            if search and search not in (node.name or "").lower():
                continue
            current = node
            while current is not None:
                if current.id in visible:
                    break
                visible.add(current.id)
                current = current.parent
        return visible

    def _insert_node_flat(
        self,
        node: "WidgetNode",
        depth: int,
        layer: int,
        visible: set[str] | None = None,
        in_group: bool = False,
    ) -> None:
        """Insert a row for `node` at the top level (no real tree
        parent), with indentation + arrow simulated in the Name
        column text and the visibility icon in the #0 column image.
        """
        if visible is not None and node.id not in visible:
            return
        name_cell = self._build_name_cell(
            node, extra_depth=1 if in_group else 0,
        )
        icon = self._resolve_eye_icon(node)
        lock_cell = LOCK_ON if node.locked else LOCK_OFF
        tags: tuple[str, ...] = ()
        if not self._effective_visible(node):
            tags += ("hidden-row",)
        if self._effective_locked(node):
            tags += ("locked-row",)
        if in_group:
            tags += ("group-member",)
        self.tree.insert(
            "", "end",
            iid=node.id,
            text="",
            image=icon if icon is not None else "",
            values=(lock_cell, name_cell, self._type_initial(node), str(layer)),
            tags=tags,
        )
        if not node.children or node.id in self._collapsed_ids:
            return
        self._insert_children_with_groups(
            node.children, depth=depth + 1, visible=visible,
        )

    def _insert_children_with_groups(
        self,
        children: list,
        depth: int,
        visible: set | None = None,
    ) -> None:
        """Walk a sibling list and insert each child row, but bundle
        every group into a virtual "Group" row that owns its members.
        Members render at ``depth + 1`` so the indent matches the
        usual parent → child visual; non-grouped siblings stay at
        ``depth`` like before. Group order follows whichever member
        comes first in the original child list.
        """
        emitted_groups: set = set()
        for child_index, child in enumerate(children):
            gid = getattr(child, "group_id", None)
            if gid and gid in emitted_groups:
                continue
            if gid:
                members = [
                    c for c in children
                    if getattr(c, "group_id", None) == gid
                ]
                if len(members) >= 2:
                    emitted_groups.add(gid)
                    if visible is not None and not any(
                        m.id in visible for m in members
                    ):
                        continue
                    self._insert_group_row(gid, members, depth=depth)
                    if f"group:{gid}" in self._collapsed_ids:
                        continue
                    for member_index, member in enumerate(members):
                        self._insert_node_flat(
                            member, depth=depth + 1,
                            layer=member_index, visible=visible,
                            in_group=True,
                        )
                    continue
            self._insert_node_flat(
                child, depth=depth, layer=child_index, visible=visible,
            )

    def _insert_group_row(
        self, group_id: str, members: list, depth: int,
    ) -> None:
        """Virtual parent row for a group. Synthetic iid keeps it
        out of every code path that walks ``project.iter_all_widgets``
        — the row only exists in the tree view, never in the model.
        """
        iid = f"group:{group_id}"
        expanded = iid not in self._collapsed_ids
        arrow = ARROW_EXPANDED if expanded else ARROW_COLLAPSED
        label = f"{INDENT_STR * depth}{arrow}◆ Group ({len(members)})"
        self._group_row_depths[iid] = depth
        eye_icon = self._resolve_group_eye_icon(members)
        lock_cell = LOCK_ON if self._group_any_locked(members) else LOCK_OFF
        tags: tuple[str, ...] = ("group-row",)
        if self._group_all_hidden(members):
            tags += ("hidden-row",)
        self.tree.insert(
            "", "end",
            iid=iid,
            text="",
            image=eye_icon if eye_icon is not None else "",
            values=(lock_cell, label, "---", ""),
            tags=tags,
        )

    def _group_all_hidden(self, members: list) -> bool:
        return bool(members) and all(
            not getattr(m, "visible", True) for m in members
        )

    def _group_any_locked(self, members: list) -> bool:
        return any(getattr(m, "locked", False) for m in members)

    def _group_any_hidden(self, members: list) -> bool:
        return any(not getattr(m, "visible", True) for m in members)

    def _resolve_group_eye_icon(self, members: list):
        """Eye glyph for the virtual Group row. Mirrors per-widget
        logic: all hidden → eye-off, all visible → eye, mixed → dim eye.
        """
        hidden_count = sum(
            1 for m in members if not getattr(m, "visible", True)
        )
        if hidden_count == len(members) and members:
            return self._eye_off_icon
        if hidden_count == 0:
            return self._eye_icon
        return self._eye_dim_icon

    def _toggle_group_flag(self, group_id: str, flag: str) -> None:
        """Batch-toggle ``visible`` or ``locked`` across every member
        of a group as one undo step. Convention: if ANY member has
        the flag in the "active" state (visible=True for eye, or
        locked=True for lock), the click turns it OFF for everyone;
        if all are already off, the click turns it ON. Mirrors how
        most tree UIs collapse mixed group state to a single action.
        """
        members = self.project.iter_group_members(group_id)
        if not members:
            return
        if flag == "visible":
            # Eye toggle: if any member is hidden → show all; else hide all.
            any_hidden = any(
                not getattr(m, "visible", True) for m in members
            )
            target = True if any_hidden else False
            entries: list[tuple[str, bool, bool]] = []
            for m in members:
                before = getattr(m, "visible", True)
                if before == target:
                    continue
                self.project.set_visibility(m.id, target)
                entries.append((m.id, before, target))
            if entries:
                self.project.history.push(
                    BulkToggleFlagCommand("visible", entries),
                )
        elif flag == "locked":
            # Lock toggle: if any member is locked → unlock all; else lock all.
            any_locked = any(
                getattr(m, "locked", False) for m in members
            )
            target = False if any_locked else True
            entries = []
            for m in members:
                before = getattr(m, "locked", False)
                if before == target:
                    continue
                self.project.set_locked(m.id, target)
                entries.append((m.id, before, target))
            if entries:
                self.project.history.push(
                    BulkToggleFlagCommand("locked", entries),
                )

    def _refresh_group_row(self, group_id: str) -> None:
        """Refresh lock cell + eye image on a virtual Group row after
        a member's flag changed. Silent no-op if the row isn't in the
        tree (e.g. group filtered out or fewer than 2 members left)."""
        iid = f"group:{group_id}"
        if not self.tree.exists(iid):
            return
        members = self.project.iter_group_members(group_id)
        if not members:
            return
        eye_icon = self._resolve_group_eye_icon(members)
        lock_cell = LOCK_ON if self._group_any_locked(members) else LOCK_OFF
        tags: tuple[str, ...] = ("group-row",)
        if self._group_all_hidden(members):
            tags += ("hidden-row",)
        try:
            self.tree.item(
                iid,
                image=eye_icon if eye_icon is not None else "",
                tags=tags,
            )
            self.tree.set(iid, "lock", lock_cell)
        except tk.TclError:
            pass

    def _resolve_eye_icon(self, node: "WidgetNode"):
        """Pick the eye glyph for a row. Three states:
        - own ``visible=False`` → ``eye-off`` (explicit hide on this node)
        - cascade-hidden (own ``visible=True`` but ancestor hidden) →
          dim ``eye`` so the icon shape stays familiar but reads as
          inactive
        - fully visible → bright ``eye``
        """
        if not node.visible:
            return self._eye_off_icon
        if not self._effective_visible(node):
            return self._eye_dim_icon
        return self._eye_icon

    def _effective_visible(self, node: "WidgetNode") -> bool:
        """True iff this node and every ancestor are visible."""
        current: "WidgetNode | None" = node
        while current is not None:
            if not current.visible:
                return False
            current = current.parent
        return True

    def _effective_locked(self, node: "WidgetNode") -> bool:
        """True iff this node or any ancestor is locked."""
        current: "WidgetNode | None" = node
        while current is not None:
            if getattr(current, "locked", False):
                return True
            current = current.parent
        return False

    def _on_filter_changed(self) -> None:
        self.refresh()
        if self._filter_menu is not None:
            is_active = self._filter_var.get() != FILTER_ALL_LABEL
            self._filter_menu.configure(
                text_color="#5bc0f8" if is_active else "#cccccc",
            )

    def _on_search_key(self, _event=None) -> None:
        if self._search_entry is None:
            return
        new_text = self._search_entry.get()
        if new_text == self._search_text:
            return
        self._search_text = new_text
        if self._search_refresh_id is not None:
            try:
                self.after_cancel(self._search_refresh_id)
            except tk.TclError:
                pass
        self._search_refresh_id = self.after(200, self._do_search_refresh)

    def _do_search_refresh(self) -> None:
        self._search_refresh_id = None
        self.refresh()

    def _apply_selection(self, _widget_id: str | None) -> None:
        """Mirror the full `project.selected_ids` set onto the tree
        widget so multi-row highlights survive `selection_changed`
        events that carry `None` (which signal workspace/props to
        clear, not the tree)."""
        ids = list(self.project.selected_ids)
        valid = [i for i in ids if self.tree.exists(i)]
        # Virtual group row mirroring — when every member of one
        # group is in the selection AND nothing else is, also light
        # up the synthetic ``group:<gid>`` row so the user sees the
        # whole-group selection at a glance.
        sel_set = set(valid)
        for gid in self._groups_in_selection(sel_set):
            row_id = f"group:{gid}"
            if self.tree.exists(row_id):
                valid.append(row_id)
        current = set(self.tree.selection())
        if set(valid) != current:
            if valid:
                self.tree.selection_set(valid)
            else:
                for s in current:
                    self.tree.selection_remove(s)
        primary = self.project.selected_id
        if primary and self.tree.exists(primary):
            self.tree.see(primary)

    def _groups_in_selection(self, ids: set) -> list:
        """Group IDs that are FULLY represented in ``ids`` (every
        member present, no widgets outside the group). Used to
        mirror the virtual Group row's selection state.
        """
        if not ids:
            return []
        by_group: dict = {}
        non_group_count = 0
        for wid in ids:
            node = self.project.get_widget(wid)
            gid = getattr(node, "group_id", None) if node else None
            if gid:
                by_group.setdefault(gid, set()).add(wid)
            else:
                non_group_count += 1
        if non_group_count > 0 or len(by_group) != 1:
            return []
        gid, present = next(iter(by_group.items()))
        full = {m.id for m in self.project.iter_group_members(gid)}
        return [gid] if present == full else []

    # ------------------------------------------------------------------
    # Event-bus callbacks
    # ------------------------------------------------------------------
    def _on_project_changed(self, *_args, **_kwargs) -> None:
        self._refresh_accent()
        self.refresh()

    def _refresh_accent(self) -> None:
        accent = self.project.get_accent_color()
        if hasattr(self, "_accent_wrap"):
            self._accent_wrap.configure(
                highlightbackground=accent,
                highlightcolor=accent,
            )
        if hasattr(self, "_doc_header_label"):
            self._doc_header_label.configure(fg=accent)
        if hasattr(self, "_doc_header_icon_label"):
            self._doc_header_icon = load_tk_icon(
                "app-window", size=14, color=accent,
            )
            self._doc_header_icon_label.configure(
                image=self._doc_header_icon,
            )

    def _on_selection_changed(self, widget_id: str | None) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self._apply_selection(widget_id)
        finally:
            # Reset _syncing after the event loop drains — tree.selection_remove
            # inside _apply_selection queues a <<TreeviewSelect>> that fires
            # AFTER this finally block; without the defer, _on_tree_select
            # would see _syncing=False and call select_widget(None).
            self.after(0, self._clear_syncing)

    def _clear_syncing(self) -> None:
        self._syncing = False

    def _on_widget_renamed(self, widget_id: str, _new_name: str) -> None:
        """In-place update of the Name cell only. The full refresh path
        would delete + reinsert every row on every keystroke of a
        rename dialog — way too heavy."""
        if not self.tree.exists(widget_id):
            return
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        self.tree.set(widget_id, "name", self._build_name_cell(node))

    def _on_widget_handler_changed(
        self, widget_id: str, *_args, **_kwargs,
    ) -> None:
        """Refresh the tree row's name cell so the ▶ marker matches
        the latest handler list. Event signature differs from
        ``widget_renamed`` (3 args vs 2), so this thin wrapper
        absorbs the extras before delegating to the rename refresh
        path.
        """
        self._on_widget_renamed(widget_id, "")

    def _on_property_changed(
        self, widget_id: str, prop_name: str, _value,
    ) -> None:
        """Container's ``layout_type`` affects the tree name cell,
        and the virtual Window's ``accent_color`` affects our border
        + doc-header tint. Everything else is a no-op so prop edits
        stay cheap."""
        if prop_name == "accent_color":
            self._refresh_accent()
            return
        if prop_name != "layout_type":
            return
        if not self.tree.exists(widget_id):
            return
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        try:
            self.tree.set(widget_id, "name", self._build_name_cell(node))
        except tk.TclError:
            pass

    def _on_widget_visibility_changed(
        self, widget_id: str, _visible: bool,
    ) -> None:
        """In-place update of the eye icon + hidden-row tag cascade.
        Visibility cascades through descendants via `_effective_visible`,
        so every row in this node's subtree needs a tag refresh."""
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        self._refresh_row_visual(node)
        for descendant in self._iter_subtree(node):
            self._refresh_row_visual(descendant)
        gid = getattr(node, "group_id", None)
        if gid:
            self._refresh_group_row(gid)

    def _on_widget_locked_changed(
        self, widget_id: str, _locked: bool,
    ) -> None:
        """Same pattern as visibility — the lock cell + locked-row tag
        cascade through descendants via `_effective_locked`."""
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        self._refresh_row_visual(node)
        for descendant in self._iter_subtree(node):
            self._refresh_row_visual(descendant)
        gid = getattr(node, "group_id", None)
        if gid:
            self._refresh_group_row(gid)

    def _on_widget_group_changed(
        self, _widget_id: str, _group_id,
    ) -> None:
        """Group changes alter tree structure (virtual Group rows
        appear / vanish, members move between sibling positions) so
        a full refresh is the cheapest correct path. In-place tag
        toggling can't model the parent row insertion.
        """
        self.refresh()

    def _iter_subtree(self, node: "WidgetNode"):
        for child in node.children:
            yield child
            yield from self._iter_subtree(child)

    def _build_name_cell(
        self, node: "WidgetNode", extra_depth: int = 0,
    ) -> str:
        descriptor = get_descriptor(node.widget_type)
        display_name = (
            descriptor.display_name if descriptor else node.widget_type
        )
        base_name = node.name or display_name
        # Container layout suffix — surfaces pack/grid choice without
        # opening Properties. Default ``place`` stays unmarked so plain
        # rows read the same as before.
        if descriptor is not None and getattr(
            descriptor, "is_container", False,
        ):
            layout = normalise_layout_type(
                node.properties.get("layout_type", "place"),
            )
            if layout != "place":
                base_name = f"{base_name}  [{layout}]"
        # Phase 2 visual scripting marker — show ▶ on widgets with at
        # least one bound event handler so the user can spot wired
        # behaviour at a glance, without expanding the Properties
        # panel for every row. Hidden by default for unwired widgets
        # so the tree stays uncluttered.
        if any(methods for methods in node.handlers.values()):
            base_name = f"{base_name}  ▶"
        depth = self._node_depth(node) + extra_depth
        has_children = bool(node.children)
        expanded = node.id not in self._collapsed_ids
        if has_children:
            arrow = ARROW_EXPANDED if expanded else ARROW_COLLAPSED
        else:
            arrow = ARROW_LEAF
        # ◆ marker now lives on the virtual Group row, so per-member
        # rows render plainly — the row tint + parent-row already
        # show membership.
        return f"{INDENT_STR * depth}{arrow}{base_name}"

    def _refresh_row_visual(self, node: "WidgetNode") -> None:
        """Update image / lock cell / tags for a single row without
        touching its sibling position. Row must already exist in the
        tree — silently no-op otherwise (e.g. filtered out)."""
        if not self.tree.exists(node.id):
            return
        icon = self._resolve_eye_icon(node)
        lock_cell = LOCK_ON if node.locked else LOCK_OFF
        tags: list[str] = []
        if not self._effective_visible(node):
            tags.append("hidden-row")
        if self._effective_locked(node):
            tags.append("locked-row")
        # Preserve the soft orange "in a group" tint — without this the
        # row drops to default gray after any flag toggle, which reads
        # as the row "leaving the group" visually.
        gid = getattr(node, "group_id", None)
        if gid and self.tree.exists(f"group:{gid}"):
            tags.append("group-member")
        try:
            self.tree.item(
                node.id,
                image=icon if icon is not None else "",
                tags=tuple(tags),
            )
            self.tree.set(node.id, "lock", lock_cell)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Tree interactions
    # ------------------------------------------------------------------
    def _on_tree_select(self, _event=None) -> None:
        if self._syncing:
            return
        sel = self.tree.selection()
        self._syncing = True
        try:
            if not sel:
                self.project.select_widget(None)
            elif len(sel) == 1:
                iid = sel[0]
                if iid.startswith("doc:"):
                    # Clicking a document header sets it active and
                    # opens its Window properties; it's not a real
                    # widget so skip select_widget(iid).
                    from app.core.project import WINDOW_ID
                    doc_id = iid[4:]
                    self.project.set_active_document(doc_id)
                    self.project.select_widget(WINDOW_ID)
                elif iid.startswith("group:"):
                    # Virtual Group row — selects every member at
                    # once. The group invariant in
                    # ``set_multi_selection`` keeps the whole-group
                    # set as-is; partial selections collapse on the
                    # way through.
                    gid = iid[len("group:"):]
                    members = self.project.iter_group_members(gid)
                    ids = {m.id for m in members}
                    if not ids:
                        return
                    primary = next(iter(ids))
                    self.project.set_multi_selection(ids, primary)
                else:
                    self.project.select_widget(iid)
            else:
                focus = self.tree.focus()
                primary = focus if focus in sel else sel[-1]
                # Skip document header + virtual group rows when
                # tracking multi — only real widget ids land in
                # ``project.selected_ids``.
                ids = {
                    i for i in sel
                    if not i.startswith("doc:")
                    and not i.startswith("group:")
                }
                if not ids:
                    return
                primary_id = (
                    primary
                    if not primary.startswith("doc:")
                    and not primary.startswith("group:")
                    else None
                )
                self.project.set_multi_selection(ids, primary_id)
        finally:
            self._syncing = False

    # ------------------------------------------------------------------
    # Drag-to-reparent and drag-to-reorder
    # ------------------------------------------------------------------
    def _on_drag_press(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            # Click on empty tree area → clear selection everywhere.
            self._drag_source_id = None
            self.project.select_widget(None)
            return
        # Ctrl/Shift click: let ttk's native extended-selection logic
        # do its thing and don't start a drag. `<<TreeviewSelect>>`
        # will fire afterwards and sync the multi-selection into the
        # project via `_on_tree_select`.
        if event.state & 0x0005:  # 0x0001 Shift | 0x0004 Control
            self._drag_source_id = None
            return
        column = self.tree.identify_column(event.x)
        # #0 column (tree column) holds the visibility icon image.
        if column == "#0":
            if iid.startswith("group:"):
                self._toggle_group_flag(iid[len("group:"):], "visible")
                self._drag_source_id = None
                return "break"
            before = self._node_visible(iid)
            after = not before
            self.project.set_visibility(iid, after)
            self.project.history.push(
                ToggleFlagCommand(iid, "visible", before, after),
            )
            self._drag_source_id = None
            return "break"
        # #1 is the lock column — click toggles locked flag.
        if column == "#1":
            if iid.startswith("group:"):
                self._toggle_group_flag(iid[len("group:"):], "locked")
                self._drag_source_id = None
                return "break"
            node = self.project.get_widget(iid)
            if node is not None:
                before = node.locked
                after = not before
                self.project.set_locked(iid, after)
                self.project.history.push(
                    ToggleFlagCommand(iid, "locked", before, after),
                )
            self._drag_source_id = None
            return "break"
        # #2 is the Name column — click on the leading arrow area
        # (within the first ~18px after the indent) toggles expand/
        # collapse for containers.
        if column == "#2" and self._click_on_arrow(iid, event.x):
            # Virtual Group rows are always expandable — they own
            # the group members and have no underlying widget node.
            if iid.startswith("group:"):
                if iid in self._collapsed_ids:
                    self._collapsed_ids.discard(iid)
                else:
                    self._collapsed_ids.add(iid)
                self._save_collapsed_ids()
                self.refresh()
                self._drag_source_id = None
                return "break"
            node = self.project.get_widget(iid)
            if node is not None and node.children:
                if iid in self._collapsed_ids:
                    self._collapsed_ids.discard(iid)
                else:
                    self._collapsed_ids.add(iid)
                self._save_collapsed_ids()
                self.refresh()
            self._drag_source_id = None
            return "break"
        # Locked widgets refuse tree-drag reparenting the same way
        # canvas drag refuses locked move — lock means "stay put".
        node = self.project.get_widget(iid)
        if node is not None and self._effective_locked(node):
            self._drag_source_id = None
            return
        self._drag_source_id = iid
        self._drag_press_y = event.y
        self._drag_active = False
        self._drop_info = None

    def _click_on_arrow(self, iid: str, event_x: int) -> bool:
        """Return True if event_x falls within the arrow glyph area
        of the name cell for `iid` (first ~18px after the indent)."""
        try:
            bbox = self.tree.bbox(iid, column="name")
        except tk.TclError:
            return False
        if not bbox:
            return False
        cell_x, _, cell_w, _ = bbox
        if iid.startswith("group:"):
            depth = self._group_row_depths.get(iid, 0)
        else:
            node = self.project.get_widget(iid)
            if node is None:
                return False
            depth = self._node_depth(node)
        # Cell text is "{INDENT_STR*depth}{arrow}{label}" rendered in
        # the tree font — measure it directly rather than guessing
        # 18px/depth (which is far off for 6-space indents in Segoe UI).
        import tkinter.font as tkfont
        font = tkfont.Font(family="Segoe UI", size=TREE_FONT_SIZE)
        indent_px = font.measure(INDENT_STR * depth)
        arrow_px = font.measure(ARROW_EXPANDED)
        # ttk Treeview's default cell text padding is ~4px from cell_x.
        cell_pad = 4
        arrow_start = cell_x + cell_pad + indent_px
        arrow_end = arrow_start + arrow_px
        return arrow_start <= event_x <= arrow_end and event_x <= cell_x + cell_w

    def _node_depth(self, node: "WidgetNode") -> int:
        depth = 0
        current = node.parent
        while current is not None:
            depth += 1
            current = current.parent
        return depth

    def _type_initial(self, node: "WidgetNode") -> str:
        if node.widget_type == "CTkFrame":
            layout = normalise_layout_type(
                node.properties.get("layout_type", "place"),
            )
            return _FRAME_LAYOUT_INITIALS.get(layout, "Frm")
        return _TYPE_INITIALS.get(node.widget_type, node.widget_type[:3])

    def _node_visible(self, widget_id: str) -> bool:
        node = self.project.get_widget(widget_id)
        return bool(node.visible) if node is not None else True

    def _on_drag_motion(self, event) -> None:
        if self._drag_source_id is None:
            return
        if not self._drag_active:
            if abs(event.y - self._drag_press_y) < DRAG_THRESHOLD:
                return
            self._drag_active = True
            try:
                self.tree.configure(cursor="fleur")
            except tk.TclError:
                pass

        drop_info = self._compute_drop_info(event.y)
        if drop_info == self._drop_info:
            return
        self._drop_info = drop_info
        self._apply_drop_feedback(drop_info)

    def _on_drag_release(self, _event) -> None:
        source_id = self._drag_source_id
        drop_info = self._drop_info
        was_dragging = self._drag_active

        self._clear_drop_feedback()
        self._drag_source_id = None
        self._drag_active = False
        self._drop_info = None
        try:
            self.tree.configure(cursor="")
        except tk.TclError:
            pass

        if not was_dragging or source_id is None or drop_info is None:
            return
        mode = drop_info.get("mode")
        if mode in (None, "invalid"):
            return
        parent_id = drop_info.get("parent_id")
        index = drop_info.get("index")
        node = self.project.get_widget(source_id)
        if node is None:
            return
        old_parent_id = node.parent.id if node.parent is not None else None
        old_siblings = (
            node.parent.children if node.parent is not None
            else self.project.root_widgets
        )
        try:
            old_index = old_siblings.index(node)
        except ValueError:
            old_index = len(old_siblings)
        try:
            old_x = int(node.properties.get("x", 0))
            old_y = int(node.properties.get("y", 0))
        except (TypeError, ValueError):
            old_x = old_y = 0
        old_doc = self.project.find_document_for_widget(source_id)
        old_doc_id = old_doc.id if old_doc is not None else None
        # Determine target doc for the drop. When the user drops
        # before / after a widget at another doc's root, parent_id is
        # None and the project would otherwise default to the active
        # doc — which during a tree drag may still be the source.
        # Derive it from drop_info instead so cross-doc moves
        # ``Project.migrate_local_var_bindings`` correctly.
        target_iid = drop_info.get("target_iid", "")
        if parent_id:
            target_doc_node = self.project.find_document_for_widget(parent_id)
        elif target_iid:
            target_doc_node = self.project.find_document_for_widget(target_iid)
        else:
            target_doc_node = old_doc
        target_doc_id = (
            target_doc_node.id if target_doc_node is not None else None
        )
        # Cross-doc var policy dialog. Same path as the canvas drag —
        # ask the user once when the dragged widget binds local vars
        # owned by the source doc.
        cross_doc = (
            old_doc is not None
            and target_doc_node is not None
            and old_doc.id != target_doc_node.id
        )
        var_policy: tuple[str, str] | None = None
        if cross_doc:
            var_entries, external = (
                self.project.collect_cross_doc_local_vars(
                    [node], target_doc_node,
                )
            )
            if var_entries:
                from app.ui.variables_window import (
                    ReparentVariablesDialog,
                )
                dialog = ReparentVariablesDialog(
                    self,
                    source_doc_name=old_doc.name,
                    target_doc_name=target_doc_node.name,
                    var_entries=var_entries,
                    external_usage=external,
                )
                dialog.wait_window()
                if dialog.result is None:
                    return  # cancel — leave the widget where it was
                var_policy = dialog.result
        # Tree drag has no cursor position — without a reset the widget
        # would keep its old absolute x/y (valid for the old parent's
        # space) and land off-screen or overlapping inside the new one.
        self._reset_position_for_tree_reparent(source_id, parent_id)
        try:
            new_x = int(node.properties.get("x", 0))
            new_y = int(node.properties.get("y", 0))
        except (TypeError, ValueError):
            new_x = new_y = 0
        self.project.reparent(
            source_id, parent_id, index=index,
            document_id=target_doc_id,
        )
        if var_policy is not None and target_doc_node is not None:
            moved = self.project.get_widget(source_id)
            if moved is not None:
                self.project.migrate_local_var_bindings(
                    moved, target_doc_node,
                    source_policy=var_policy[0],
                    target_policy=var_policy[1],
                )
        post_node = self.project.get_widget(source_id)
        if post_node is None:
            return
        new_siblings = (
            post_node.parent.children if post_node.parent is not None
            else self.project.root_widgets
        )
        try:
            new_index = new_siblings.index(post_node)
        except ValueError:
            new_index = len(new_siblings) - 1
        new_doc = self.project.find_document_for_widget(source_id)
        new_doc_id = new_doc.id if new_doc is not None else old_doc_id
        if (old_parent_id == parent_id and old_index == new_index
                and old_x == new_x and old_y == new_y
                and old_doc_id == new_doc_id):
            return
        self.project.history.push(
            ReparentCommand(
                source_id,
                old_parent_id=old_parent_id,
                old_index=old_index,
                old_x=old_x,
                old_y=old_y,
                new_parent_id=parent_id,
                new_index=new_index,
                new_x=new_x,
                new_y=new_y,
                old_document_id=old_doc_id,
                new_document_id=new_doc_id,
            ),
        )

    def _reset_position_for_tree_reparent(
        self, source_id: str, new_parent_id: str | None,
    ) -> None:
        node = self.project.get_widget(source_id)
        if node is None:
            return
        old_parent_id = node.parent.id if node.parent is not None else None
        if old_parent_id == new_parent_id:
            return
        new_parent = (
            self.project.get_widget(new_parent_id)
            if new_parent_id else None
        )
        # Non-place parents ignore x/y — leave stored values intact so
        # a later move back to a place context preserves them.
        if new_parent is not None:
            layout = normalise_layout_type(
                new_parent.properties.get("layout_type", "place"),
            )
            if layout != "place":
                return
        from app.core.project import find_free_cascade_slot
        siblings = (
            new_parent.children if new_parent is not None
            else self.project.root_widgets
        )
        x, y = find_free_cascade_slot(siblings, exclude=node)
        node.properties["x"] = x
        node.properties["y"] = y

    # ---- drop-zone computation + visual feedback ---------------------
    def _compute_drop_info(self, event_y: int) -> dict:
        """Figure out where a drop at event_y would land.

        Returns a dict with keys:
            mode      — "before" / "into" / "after" /
                        "top-append" / "invalid"
            parent_id — target parent id (or None for top-level)
            index     — insertion index in target's sibling list
            target_iid — tree iid used for visual feedback (may be "")
        """
        target_iid = self.tree.identify_row(event_y) or ""
        if not target_iid:
            return {
                "mode": "top-append",
                "parent_id": None,
                "index": None,
                "target_iid": "",
            }

        if self._is_source_or_descendant(target_iid):
            return {"mode": "invalid", "target_iid": target_iid}

        bbox = self.tree.bbox(target_iid)
        if not bbox:
            return {"mode": "invalid", "target_iid": target_iid}
        _, by, _, h = bbox
        rel = (event_y - by) / max(1, h)

        target_node = self.project.get_widget(target_iid)
        if target_node is None:
            return {"mode": "invalid", "target_iid": target_iid}
        descriptor = get_descriptor(target_node.widget_type)
        is_container = (
            descriptor is not None
            and getattr(descriptor, "is_container", False)
        )

        parent_node = target_node.parent
        parent_id = parent_node.id if parent_node is not None else None
        sibs = (
            parent_node.children if parent_node is not None
            else self.project.root_widgets
        )
        try:
            target_index = sibs.index(target_node)
        except ValueError:
            return {"mode": "invalid", "target_iid": target_iid}

        # Container: top 25% = before, mid 50% = into, bottom 25% = after.
        # Non-container: 50% split (before/after).
        if is_container:
            if rel < 0.25:
                return {
                    "mode": "before", "target_iid": target_iid,
                    "parent_id": parent_id, "index": target_index,
                }
            if rel > 0.75:
                return {
                    "mode": "after", "target_iid": target_iid,
                    "parent_id": parent_id, "index": target_index + 1,
                }
            return {
                "mode": "into", "target_iid": target_iid,
                "parent_id": target_iid, "index": None,
            }
        if rel < 0.5:
            return {
                "mode": "before", "target_iid": target_iid,
                "parent_id": parent_id, "index": target_index,
            }
        return {
            "mode": "after", "target_iid": target_iid,
            "parent_id": parent_id, "index": target_index + 1,
        }

    def _apply_drop_feedback(self, drop_info: dict) -> None:
        self._clear_drop_feedback()
        mode = drop_info.get("mode")
        iid = drop_info.get("target_iid") or ""
        if mode == "invalid":
            if iid:
                try:
                    self.tree.item(iid, tags=("drop-invalid",))
                    self._highlighted_iid = iid
                except tk.TclError:
                    pass
            return
        if mode == "into":
            try:
                self.tree.item(iid, tags=("drop-target",))
                self._highlighted_iid = iid
            except tk.TclError:
                pass
            return
        if mode in ("before", "after") and iid:
            bbox = self.tree.bbox(iid)
            if bbox:
                _, by, _, h = bbox
                line_y = by if mode == "before" else by + h
                self._show_insert_line(line_y)
            return
        # top-append has no visual indicator

    def _clear_drop_feedback(self) -> None:
        if self._highlighted_iid:
            try:
                self.tree.item(self._highlighted_iid, tags=())
            except tk.TclError:
                pass
            self._highlighted_iid = None
        self._hide_insert_line()

    def _show_insert_line(self, y: int) -> None:
        if self._insert_line is None:
            return
        try:
            # y is relative to the Treeview widget's content area.
            # The tree is the only packed child of _tree_container
            # other than a CTkScrollbar on the right, so tree y == 0
            # inside the container.
            self._insert_line.place(
                x=0, y=max(0, y - 1), relwidth=1, height=2,
            )
            self._insert_line.lift()
            self._insert_line_visible = True
        except tk.TclError:
            pass

    def _hide_insert_line(self) -> None:
        if not self._insert_line_visible or self._insert_line is None:
            return
        try:
            self._insert_line.place_forget()
        except tk.TclError:
            pass
        self._insert_line_visible = False

    def _is_source_or_descendant(self, candidate_iid: str) -> bool:
        """True if `candidate_iid` is the drag source or is inside
        the drag source's subtree (cycle-prevention)."""
        if self._drag_source_id is None:
            return False
        node = self.project.get_widget(candidate_iid)
        while node is not None:
            if node.id == self._drag_source_id:
                return True
            node = node.parent
        return False

    # ------------------------------------------------------------------
    # Right-click context menu
    # ------------------------------------------------------------------
    def _on_double_click(self, event) -> str | None:
        iid = self.tree.identify_row(event.y)
        if not iid or iid.startswith("doc:") or iid.startswith("group:"):
            return None
        if self.tree.identify_column(event.x) != "#2":
            return None
        self._start_inline_rename(iid)
        return "break"

    def _start_inline_rename(self, iid: str) -> None:
        import tkinter.font as tkfont
        from app.core.project import WINDOW_ID
        node = self.project.get_widget(iid)
        if node is None or iid == WINDOW_ID:
            return
        try:
            bbox = self.tree.bbox(iid, "name")
        except tk.TclError:
            return
        if not bbox:
            return
        cell_x, cell_y, cell_w, cell_h = bbox

        depth = self._node_depth(node)
        has_children = bool(node.children)
        expanded = node.id not in self._collapsed_ids
        arrow = (ARROW_EXPANDED if expanded else ARROW_COLLAPSED) if has_children else ARROW_LEAF
        prefix = INDENT_STR * depth + arrow
        try:
            prefix_px = tkfont.Font(family="Segoe UI", size=TREE_FONT_SIZE).measure(prefix)
        except Exception:
            prefix_px = 0

        x = cell_x + prefix_px
        w = max(40, cell_w - prefix_px - 4)
        before = node.name or ""

        entry = tk.Entry(
            self.tree,
            font=("Segoe UI", TREE_FONT_SIZE),
            bg="#2d2d30", fg="#cccccc",
            insertbackground="#cccccc",
            relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground="#3b8ed0",
            highlightcolor="#3b8ed0",
        )
        entry.insert(0, before)
        entry.select_range(0, tk.END)
        entry.place(x=x, y=cell_y, width=w, height=cell_h)
        entry.focus_set()

        committed = [False]

        def _commit(_e=None):
            if committed[0]:
                return
            committed[0] = True
            new_name = entry.get().strip()
            entry.destroy()
            if new_name and new_name != before:
                self.project.rename_widget(iid, new_name)
                self.project.history.push(
                    RenameCommand(iid, before, new_name),
                )

        def _cancel(_e=None):
            if committed[0]:
                return
            committed[0] = True
            entry.destroy()

        entry.bind("<Return>", _commit)
        entry.bind("<Escape>", _cancel)
        entry.bind("<FocusOut>", _commit)

    def _on_right_click(self, event) -> str:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return "break"
        # Virtual Group row — short menu (Select Group / Ungroup).
        if iid.startswith("group:"):
            gid = iid[len("group:"):]
            members = self.project.iter_group_members(gid)
            if not members:
                return "break"
            toplevel = self.winfo_toplevel()
            menu = tk.Menu(
                self.winfo_toplevel(), tearoff=0, **CTX_MENU_STYLE,
            )
            menu.add_command(
                label=f"Select Group ({len(members)})",
                command=lambda g=gid: toplevel._on_select_group(g),
            )
            menu.add_separator()
            ids = {m.id for m in members}
            primary = next(iter(ids))
            menu.add_command(
                label="Ungroup",
                accelerator=f"{MOD_LABEL_PLUS}Shift+G",
                command=lambda ids=ids, p=primary, t=toplevel: (
                    self.project.set_multi_selection(ids, p),
                    t._on_ungroup_shortcut(),
                ),
            )
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
            return "break"
        # If a multi-selection is active and the right-clicked row is
        # part of it, only Delete is meaningful — every other action
        # (rename, duplicate, z-order) is per-widget. Skip selection
        # reset so the multi stays.
        multi_active = (
            len(self.project.selected_ids) > 1
            and iid in self.project.selected_ids
        )

        menu = tk.Menu(
            self.winfo_toplevel(), tearoff=0, **CTX_MENU_STYLE,
        )
        toplevel = self.winfo_toplevel()
        if multi_active:
            count = len(self.project.selected_ids)
            menu.add_command(
                label=f"Copy {count} widgets",
                command=self._copy_selection_to_clipboard,
            )
            menu.add_separator()
            menu.add_command(
                label=f"Delete {count} widgets",
                command=lambda nid=iid: self._delete_widget(nid),
            )
            self._add_group_entries(menu, toplevel)
        else:
            self.project.select_widget(iid)
            menu.add_command(
                label="Copy",
                command=lambda nid=iid: self._copy_single_to_clipboard(nid),
            )
            # tk.Menu on Windows emboss-shadows any ``state="disabled"``
            # entry, so we keep items enabled and only swap the
            # foreground colour to communicate unavailability — callbacks
            # no-op when the action can't run. Same trick the top menu's
            # Edit submenu uses (see main_window._refresh_edit_menu_state).
            ctx_node = self.project.get_widget(iid)
            descriptor = (
                get_descriptor(ctx_node.widget_type)
                if ctx_node is not None else None
            )
            is_container = (
                descriptor is not None
                and getattr(descriptor, "is_container", False)
            )
            disabled_fg = CTX_MENU_STYLE.get("disabledforeground", "#888888")
            enabled_fg = CTX_MENU_STYLE.get("fg", "#cccccc")
            paste_fg = enabled_fg if self.project.clipboard else disabled_fg
            paste_child_fg = (
                enabled_fg
                if (self.project.clipboard and is_container)
                else disabled_fg
            )
            menu.add_command(
                label="Paste",
                command=self._paste_in_window,
                foreground=paste_fg,
            )
            menu.add_command(
                label="Paste as child",
                command=lambda nid=iid: self._paste_as_child(nid),
                foreground=paste_child_fg,
            )
            menu.add_command(
                label="Duplicate",
                command=lambda nid=iid: self._duplicate_in_window(nid),
            )
            menu.add_separator()
            menu.add_command(
                label="Rename",
                command=lambda nid=iid: self._prompt_rename(nid),
            )
            menu.add_command(
                label="Delete",
                command=lambda nid=iid: self._delete_widget(nid),
            )
            self._add_group_entries(menu, toplevel)
            menu.add_separator()
            menu.add_command(
                label="Bring to Front",
                command=lambda nid=iid: self._z_order_with_history(
                    nid, "front",
                ),
            )
            menu.add_command(
                label="Send to Back",
                command=lambda nid=iid: self._z_order_with_history(
                    nid, "back",
                ),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _add_group_entries(self, menu, toplevel) -> None:
        """Append Group / Ungroup / Select Group entries to a tree
        context menu — only what's currently runnable. Routes to the
        same MainWindow handlers as the Edit menu and the Ctrl+G /
        Ctrl+Shift+G shortcuts so undo/redo stays consistent across
        every entry point.
        """
        sel_ids = set(self.project.selected_ids or set())
        can_group = self.project.can_group_selection(sel_ids)
        select_group_id: str | None = None
        for wid in sel_ids:
            node = self.project.get_widget(wid)
            gid = getattr(node, "group_id", None) if node else None
            if not gid:
                continue
            members = self.project.iter_group_members(gid)
            if len(members) > 1 and sel_ids != {m.id for m in members}:
                select_group_id = gid
                break
        can_ungroup = any(
            getattr(self.project.get_widget(wid), "group_id", None)
            for wid in sel_ids
        )
        if not (can_group or can_ungroup or select_group_id):
            return
        menu.add_separator()
        if can_group:
            menu.add_command(
                label="Group",
                accelerator=f"{MOD_LABEL_PLUS}G",
                command=toplevel._on_group_shortcut,
            )
        if select_group_id:
            menu.add_command(
                label="Select Group",
                command=lambda gid=select_group_id: toplevel._on_select_group(gid),
            )
        if can_ungroup:
            menu.add_command(
                label="Ungroup",
                accelerator=f"{MOD_LABEL_PLUS}Shift+G",
                command=toplevel._on_ungroup_shortcut,
            )

    def _copy_single_to_clipboard(self, widget_id: str) -> None:
        self.project.copy_to_clipboard({widget_id})

    def _copy_selection_to_clipboard(self) -> None:
        ids = self.project.selected_ids
        if ids:
            self.project.copy_to_clipboard(ids)

    def _paste_as_child(self, widget_id: str) -> None:
        """Tree paste — drop the clipboard inside the right-clicked
        widget. Menu keeps this entry enabled at all times (Windows
        emboss on state=disabled) so the guards here handle the
        unavailable cases: empty clipboard and non-container target
        are both silent no-ops."""
        if not self.project.clipboard:
            return
        node = self.project.get_widget(widget_id)
        descriptor = (
            get_descriptor(node.widget_type) if node is not None else None
        )
        if descriptor is None or not getattr(
            descriptor, "is_container", False,
        ):
            return
        from app.ui.variables_window import confirm_clipboard_paste_policy
        target_doc = self.project.find_document_for_widget(widget_id)
        proceed, policy = confirm_clipboard_paste_policy(
            self, self.project, target_doc,
        )
        if not proceed:
            return
        new_ids = self.project.paste_from_clipboard(
            parent_id=widget_id, var_policy=policy,
        )
        self._push_paste_history(new_ids)

    def _paste_in_window(self) -> None:
        """Tree paste — drop the clipboard at the document root,
        regardless of where the right-click landed."""
        if not self.project.clipboard:
            return
        from app.ui.variables_window import confirm_clipboard_paste_policy
        proceed, policy = confirm_clipboard_paste_policy(
            self, self.project, self.project.active_document,
        )
        if not proceed:
            return
        new_ids = self.project.paste_from_clipboard(
            parent_id=None, var_policy=policy,
        )
        self._push_paste_history(new_ids)

    def _duplicate_in_window(self, widget_id: str) -> None:
        """Tree duplicate — clone the subtree to the document root
        instead of next to the source. Tree-side variant only; the
        canvas right-click keeps duplicating in place."""
        new_id = self.project.duplicate_widget(
            widget_id, force_top_level=True,
        )
        if new_id is None:
            return
        entries = build_bulk_add_entries(self.project, [new_id])
        if entries:
            self.project.history.push(
                BulkAddCommand(entries, label="Duplicate"),
            )

    def _prompt_rename(self, widget_id: str) -> None:
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        dialog = RenameDialog(self, node.name)
        if dialog.result and dialog.result != node.name:
            before = node.name
            self.project.rename_widget(widget_id, dialog.result)
            self.project.history.push(
                RenameCommand(widget_id, before, dialog.result),
            )

    # ------------------------------------------------------------------
    # Copy / paste shortcuts
    # ------------------------------------------------------------------
    def _on_copy_shortcut(self, _event=None) -> str | None:
        if isinstance(self.focus_get(), (tk.Entry, tk.Text)):
            return None  # let the entry handle its own Ctrl+C
        ids = self.project.selected_ids
        if not ids:
            return "break"
        self.project.copy_to_clipboard(ids)
        # Keep the tree focused so subsequent Ctrl+C/V keep routing
        # through our bindings — rebuilds in the docked version
        # otherwise drop focus back to the main window.
        self.tree.focus_set()
        return "break"

    def _on_paste_shortcut(self, _event=None) -> str | None:
        if isinstance(self.focus_get(), (tk.Entry, tk.Text)):
            return None
        if not self.project.clipboard:
            return "break"
        parent_id = self._paste_target_parent_id()
        from app.ui.variables_window import confirm_clipboard_paste_policy
        target_doc = (
            self.project.find_document_for_widget(parent_id)
            if parent_id else self.project.active_document
        )
        proceed, policy = confirm_clipboard_paste_policy(
            self, self.project, target_doc,
        )
        if not proceed:
            return "break"
        new_ids = self.project.paste_from_clipboard(
            parent_id=parent_id, var_policy=policy,
        )
        self._push_paste_history(new_ids)
        self.tree.focus_set()
        return "break"

    def _push_paste_history(self, new_ids: list[str]) -> None:
        if not new_ids:
            return
        entries = build_bulk_add_entries(self.project, new_ids)
        if entries:
            self.project.history.push(BulkAddCommand(entries, label="Paste"))

    def _z_order_with_history(self, nid: str, direction: str) -> None:
        push_zorder_history(self.project, nid, direction)

    def _paste_target_parent_id(self) -> str | None:
        return paste_target_parent_id(self.project, self.project.selected_id)

    def _delete_widget(self, widget_id: str) -> None:
        # Locked widgets reject canvas-side delete; the tree should
        # match so lock is meaningful from every surface.
        node_check = self.project.get_widget(widget_id)
        if node_check is not None and self._effective_locked(node_check):
            messagebox.showinfo(
                title="Widget locked",
                message=(
                    "This widget is locked. Unlock it "
                    "(padlock icon) before deleting."
                ),
                parent=self,
            )
            return
        # If the clicked row is part of a multi-selection, delete all
        # selected widgets in one confirmation.
        selected = set(self.project.selected_ids)
        if widget_id in selected and len(selected) > 1:
            count = len(selected)
            confirmed = messagebox.askyesno(
                title="Delete widgets",
                message=f"Delete {count} selected widgets?",
                icon="warning",
                parent=self,
            )
            if not confirmed:
                return
            # Walk the project's tree once in top-down order to
            # capture per-id snapshots + parent/index before any
            # removal shifts the sibling lists. Skip descendants
            # whose ancestor is also selected — a parent deletion
            # already covers them.
            entries: list[tuple[dict, str | None, int, str | None]] = []
            for node in self.project.iter_all_widgets():
                if node.id not in selected:
                    continue
                ancestor = node.parent
                covered = False
                while ancestor is not None:
                    if ancestor.id in selected:
                        covered = True
                        break
                    ancestor = ancestor.parent
                if covered:
                    continue
                parent_id = (
                    node.parent.id if node.parent is not None else None
                )
                siblings = (
                    node.parent.children if node.parent is not None
                    else self.project.root_widgets
                )
                try:
                    index = siblings.index(node)
                except ValueError:
                    index = len(siblings)
                owning_doc = self.project.find_document_for_widget(node.id)
                document_id = (
                    owning_doc.id if owning_doc is not None else None
                )
                entries.append(
                    (node.to_dict(), parent_id, index, document_id),
                )
            for snapshot, _parent_id, _index, _doc_id in entries:
                self.project.remove_widget(snapshot["id"])
            if entries:
                self.project.history.push(DeleteMultipleCommand(entries))
            return
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        descriptor = get_descriptor(node.widget_type)
        type_label = (
            descriptor.display_name if descriptor else node.widget_type
        )
        confirmed = messagebox.askyesno(
            title="Delete widget",
            message=f"Delete this {type_label}?",
            icon="warning",
            parent=self,
        )
        if not confirmed:
            return
        snapshot = node.to_dict()
        parent_id = node.parent.id if node.parent is not None else None
        siblings = (
            node.parent.children if node.parent is not None
            else self.project.root_widgets
        )
        try:
            index = siblings.index(node)
        except ValueError:
            index = len(siblings)
        owning_doc = self.project.find_document_for_widget(widget_id)
        document_id = owning_doc.id if owning_doc is not None else None
        self.project.remove_widget(widget_id)
        self.project.history.push(
            DeleteWidgetCommand(snapshot, parent_id, index, document_id),
        )

    def destroy(self) -> None:
        # Ensure bus unsubscribes happen even if the caller calls
        # destroy() directly (e.g. main window toggling the menu item).
        self._unsubscribe_bus()
        if self._search_refresh_id is not None:
            try:
                self.after_cancel(self._search_refresh_id)
            except tk.TclError:
                pass
            self._search_refresh_id = None
        super().destroy()

    def _unsubscribe_bus(self) -> None:
        try:
            bus = self.project.event_bus
            for event_name, handler in self._bus_subs:
                bus.unsubscribe(event_name, handler)
        except Exception:
            pass


# ======================================================================
# Floating-window wrapper — keeps the old "pop-out" Object Tree alive
# ======================================================================
class ObjectTreeWindow(ctk.CTkToplevel):
    """Thin Toplevel wrapper around `ObjectTreePanel`.

    Most users see the docked ObjectTreePanel embedded in the right
    sidebar; this wrapper is only created when the View menu's
    "Object Tree" option is checked, or programmatically for a
    detachable floating inspector.
    """

    def __init__(
        self,
        parent,
        project: "Project",
        on_close: Callable[[], None] | None = None,
    ):
        super().__init__(parent)
        self.title("Object Tree")
        self.configure(fg_color=BG)
        self.geometry(f"{DIALOG_W}x{DIALOG_H}")
        self.minsize(280, 200)
        try:
            self.transient(parent)
        except tk.TclError:
            pass

        self._on_close_callback = on_close
        self.panel = ObjectTreePanel(self, project)
        self.panel.pack(fill="both", expand=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._center_on_parent)
        self.after(150, self._raise_above_parent)

    def refresh(self) -> None:
        self.panel.refresh()

    def _raise_above_parent(self) -> None:
        """Force the Toplevel above the main builder window.

        `transient()` alone is sometimes not enough on Windows —
        briefly flip `-topmost` so the window lands in front instead
        of behind its parent on launch.
        """
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.after(200, lambda: self.attributes("-topmost", False))
        except tk.TclError:
            pass

    def _center_on_parent(self) -> None:
        self.update_idletasks()
        try:
            px = self.master.winfo_rootx()
            py = self.master.winfo_rooty()
            pw = self.master.winfo_width()
        except tk.TclError:
            return
        x = px + pw - DIALOG_W - 24
        y = py + 80
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _on_close(self) -> None:
        if self._on_close_callback is not None:
            try:
                self._on_close_callback()
            except Exception:
                pass
        self.destroy()
