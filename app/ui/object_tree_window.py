"""Object Tree inspector — Qt Designer-style hierarchical widget list.

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
ARROW_EXPANDED = "▾ "
ARROW_COLLAPSED = "▸ "
ARROW_LEAF = "   "
INDENT_STR = "      "  # 6 spaces per depth level — clearer nesting
TREE_ROW_HEIGHT = 22
TREE_FONT_SIZE = 10

DIALOG_W = 360
DIALOG_H = 460
DRAG_THRESHOLD = 5

FILTER_ALL_LABEL = "All types"

CTX_MENU_STYLE = dict(
    bg="#2d2d30",
    fg="#cccccc",
    activebackground="#094771",
    activeforeground="#ffffff",
    disabledforeground="#6a6a6a",
    bd=0,
    borderwidth=0,
    activeborderwidth=0,
    relief="flat",
    font=("Segoe UI", 10),
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
        self._collapsed_ids: set[str] = set()

        # Row images for the visibility toggle (must be tk.PhotoImage
        # because ttk.Treeview's image= parameter rejects CTkImage).
        self._eye_icon = load_tk_icon("eye", size=16, color="#cccccc")
        self._eye_off_icon = load_tk_icon("eye-off", size=16, color="#666666")
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
            ("selection_changed", self._on_selection_changed),
            ("active_document_changed", self._on_project_changed),
            # layout_type changes the container's name suffix, so we
            # need to repaint the affected row.
            ("property_changed", self._on_property_changed),
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
        self.tree.bind("<Control-c>", self._on_copy_shortcut)
        self.tree.bind("<Control-C>", self._on_copy_shortcut)
        self.tree.bind("<Control-v>", self._on_paste_shortcut)
        self.tree.bind("<Control-V>", self._on_paste_shortcut)
        # Non-Latin layout fallback (Georgian, Russian, ...): MainWindow's
        # bind_all("<Control-KeyPress>") routes by hardware keycode and
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
        style.map(
            "ObjectTree.Treeview",
            background=[("selected", TREE_SELECTED_BG)],
            foreground=[("selected", "#ffffff")],
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

        # Centered bold title — matches the Properties panel.
        self._title = tk.Label(
            self, text="Object Tree",
            bg=BG, fg="#cccccc",
            font=("Segoe UI", 11, "bold"),
        )
        self._title.pack(side="top", pady=(2, 1))

        # Accent-coloured border wrap — 1px of the active document's
        # theme colour. Starts below the title.
        wrap = tk.Frame(
            self, bg=BG,
            highlightbackground=accent,
            highlightcolor=accent,
            highlightthickness=1,
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
        self.tree.heading("type", text="Type")
        self.tree.heading("layer", text="Layer")
        self.tree.column("#0", width=36, stretch=False, anchor="center")
        self.tree.column("lock", width=32, stretch=False, anchor="center")
        self.tree.column("name", width=160, stretch=True, anchor="w")
        self.tree.column("type", width=100, stretch=False, anchor="w")
        self.tree.column("layer", width=56, stretch=False, anchor="center")

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

        # Insertion line overlay — placed on demand above the tree row.
        self._insert_line = tk.Frame(tree_row, bg=DROP_TARGET_BG, height=2)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<ButtonPress-1>", self._on_drag_press, add="+")
        self.tree.bind("<B1-Motion>", self._on_drag_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self._on_drag_release, add="+")
        self.tree.bind("<Button-3>", self._on_right_click, add="+")

    # ------------------------------------------------------------------
    # Refresh / population
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._syncing = True
        try:
            self._rebuild_filter_options()
            self.tree.delete(*self.tree.get_children(""))
            self._refresh_doc_header()
            visible = self._compute_visible_set()
            active = self.project.active_document
            if active is not None:
                for index, node in enumerate(active.root_widgets):
                    self._insert_node_flat(
                        node, depth=0, layer=index, visible=visible,
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

    def _rebuild_filter_options(self) -> None:
        """Rebuild the filter dropdown so it only lists widget types
        actually present in the project (sorted by display name).
        """
        if self._filter_menu is None:
            return
        type_names_in_project = {
            node.widget_type for node in self.project.iter_all_widgets()
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
        for node in self.project.iter_all_widgets():
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
    ) -> None:
        """Insert a row for `node` at the top level (no real tree
        parent), with indentation + arrow simulated in the Name
        column text and the visibility icon in the #0 column image.
        """
        if visible is not None and node.id not in visible:
            return
        name_cell = self._build_name_cell(node)
        icon = self._eye_icon if node.visible else self._eye_off_icon
        lock_cell = LOCK_ON if node.locked else LOCK_OFF
        tags: tuple[str, ...] = ()
        if not self._effective_visible(node):
            tags += ("hidden-row",)
        if self._effective_locked(node):
            tags += ("locked-row",)
        self.tree.insert(
            "", "end",
            iid=node.id,
            text="",
            image=icon if icon is not None else "",
            values=(lock_cell, name_cell, node.widget_type, str(layer)),
            tags=tags,
        )
        if not node.children or node.id in self._collapsed_ids:
            return
        for child_index, child in enumerate(node.children):
            self._insert_node_flat(
                child, depth=depth + 1, layer=child_index, visible=visible,
            )

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

    def _iter_subtree(self, node: "WidgetNode"):
        for child in node.children:
            yield child
            yield from self._iter_subtree(child)

    def _build_name_cell(self, node: "WidgetNode") -> str:
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
        depth = self._node_depth(node)
        has_children = bool(node.children)
        expanded = node.id not in self._collapsed_ids
        if has_children:
            arrow = ARROW_EXPANDED if expanded else ARROW_COLLAPSED
        else:
            arrow = ARROW_LEAF
        return f"{INDENT_STR * depth}{arrow}{base_name}"

    def _refresh_row_visual(self, node: "WidgetNode") -> None:
        """Update image / lock cell / tags for a single row without
        touching its sibling position. Row must already exist in the
        tree — silently no-op otherwise (e.g. filtered out)."""
        if not self.tree.exists(node.id):
            return
        icon = self._eye_icon if node.visible else self._eye_off_icon
        lock_cell = LOCK_ON if node.locked else LOCK_OFF
        tags: list[str] = []
        if not self._effective_visible(node):
            tags.append("hidden-row")
        if self._effective_locked(node):
            tags.append("locked-row")
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
                else:
                    self.project.select_widget(iid)
            else:
                focus = self.tree.focus()
                primary = focus if focus in sel else sel[-1]
                # Skip document header rows when tracking multi.
                ids = {i for i in sel if not i.startswith("doc:")}
                if not ids:
                    return
                primary_id = primary if not primary.startswith("doc:") else None
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
            node = self.project.get_widget(iid)
            if node is not None and node.children:
                if iid in self._collapsed_ids:
                    self._collapsed_ids.discard(iid)
                else:
                    self._collapsed_ids.add(iid)
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
        node = self.project.get_widget(iid)
        if node is None:
            return False
        depth = self._node_depth(node)
        indent_px = depth * 18
        arrow_start = cell_x + indent_px
        arrow_end = arrow_start + 18
        return arrow_start <= event_x <= arrow_end and event_x <= cell_x + cell_w

    def _node_depth(self, node: "WidgetNode") -> int:
        depth = 0
        current = node.parent
        while current is not None:
            depth += 1
            current = current.parent
        return depth

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
        # Tree drag has no cursor position — without a reset the widget
        # would keep its old absolute x/y (valid for the old parent's
        # space) and land off-screen or overlapping inside the new one.
        self._reset_position_for_tree_reparent(source_id, parent_id)
        try:
            new_x = int(node.properties.get("x", 0))
            new_y = int(node.properties.get("y", 0))
        except (TypeError, ValueError):
            new_x = new_y = 0
        self.project.reparent(source_id, parent_id, index=index)
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
    def _on_right_click(self, event) -> str:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return "break"
        # If a multi-selection is active and the right-clicked row is
        # part of it, only Delete is meaningful — every other action
        # (rename, duplicate, z-order) is per-widget. Skip selection
        # reset so the multi stays.
        multi_active = (
            len(self.project.selected_ids) > 1
            and iid in self.project.selected_ids
        )

        menu = tk.Menu(self, tearoff=0, **CTX_MENU_STYLE)
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
        else:
            self.project.select_widget(iid)
            menu.add_command(
                label="Copy",
                command=lambda nid=iid: self._copy_single_to_clipboard(nid),
            )
            paste_state = "normal" if self.project.clipboard else "disabled"
            ctx_node = self.project.get_widget(iid)
            descriptor = (
                get_descriptor(ctx_node.widget_type)
                if ctx_node is not None else None
            )
            is_container = (
                descriptor is not None
                and getattr(descriptor, "is_container", False)
            )
            paste_child_state = (
                paste_state if is_container else "disabled"
            )
            menu.add_command(
                label="Paste",
                command=self._paste_in_window,
                state=paste_state,
            )
            menu.add_command(
                label="Paste as child",
                command=lambda nid=iid: self._paste_as_child(nid),
                state=paste_child_state,
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

    def _copy_single_to_clipboard(self, widget_id: str) -> None:
        self.project.copy_to_clipboard({widget_id})

    def _copy_selection_to_clipboard(self) -> None:
        ids = self.project.selected_ids
        if ids:
            self.project.copy_to_clipboard(ids)

    def _paste_as_child(self, widget_id: str) -> None:
        """Tree paste — drop the clipboard inside the right-clicked
        widget. Menu disables this entry on non-container nodes so the
        callback never lands on a leaf, but keep the no-op guard for
        the keyboard-driven path."""
        if not self.project.clipboard:
            return
        new_ids = self.project.paste_from_clipboard(parent_id=widget_id)
        self._push_paste_history(new_ids)

    def _paste_in_window(self) -> None:
        """Tree paste — drop the clipboard at the document root,
        regardless of where the right-click landed."""
        if not self.project.clipboard:
            return
        new_ids = self.project.paste_from_clipboard(parent_id=None)
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
        new_ids = self.project.paste_from_clipboard(parent_id=parent_id)
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
