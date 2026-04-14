"""CTkButton Properties panel — ttk.Treeview mock.

Standalone prototype that renders the CTkButton property list via a
single `ttk.Treeview` widget, following the same pattern Object Tree
uses. Edit values in-place via a temporary overlay widget that appears
over the clicked cell.

Run:
    python tools/ctk_button_treeview_mock.py

Nothing in this file touches app/. Goal: demonstrate a flicker-free
Properties panel that never destroys/recreates its editors.
"""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

# Allow running this script directly from `tools/` without installing
# the app package — add the project root to sys.path.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import customtkinter as ctk

from app.ui.icons import load_icon
from tools.text_editor_dialog import TextEditorDialog


# =====================================================================
# Colors (match Object Tree's style for consistency)
# =====================================================================
BG = "#1e1e1e"
PANEL_BG = "#252526"
TREE_BG = "#1e1e1e"
TREE_FG = "#cccccc"
TREE_SELECTED_BG = "#094771"
TREE_HEADING_BG = "#333338"
TREE_HEADING_FG = "#cccccc"
CLASS_ROW_BG = "#2b2b2b"
CLASS_ROW_FG = "#dddddd"
PREVIEW_FG = "#888888"

COLUMN_SEP = "#3a3a3a"

PANEL_WIDTH = 380
PANEL_HEIGHT = 720


# =====================================================================
# Schema
#
# Flat list of row definitions; parent links via `parent` key.
# Each entry:
#   ("iid", "parent_iid", "label", editor_type, initial_value)
#
# editor_type: "class" | "number" | "text" | "bool" | "color" | "enum"
#              | "image" | "group"  (group == collapsible non-edit row)
# =====================================================================
# (iid, parent, label, editor, value, options)
# Master bool rows — toggling one updates a parent preview and a set
# of disabled children. This demonstrates the "group header that
# controls its children" pattern.
# Bool rows whose toggled state updates a parent row's preview text
# (e.g. Border: "active" / "not active"). The children rows are NOT
# disabled — only the parent preview text changes.
PARENT_PREVIEW_BOOLS: dict[str, dict] = {
    "border_enabled": {
        "parent": "border",
        "active_preview": "active",
        "inactive_preview": "not active",
    },
}

# Font-style bool rows that contribute to the `style` row's preview.
# Maps the row iid to its display label.
STYLE_BOOL_LABELS: dict[str, str] = {
    "bold": "Bold",
    "italic": "Italic",
    "underline": "Underline",
    "strike": "Strike",
    "wrap": "Wrap",
}


SCHEMA: list[tuple] = [
    # --- Geometry -----------------------------------------------------
    ("geometry", "", "Geometry", "class", "", None),
    ("position", "geometry", "position", "group", "X 120  Y 120", None),
    ("x", "position", "x", "number", "120", None),
    ("y", "position", "y", "number", "120", None),
    ("size", "geometry", "size", "group", "W 140  H 32", None),
    ("width", "size", "width", "number", "140", None),
    ("height", "size", "height", "number", "32", None),

    # --- Rectangle ----------------------------------------------------
    ("rectangle", "", "Rectangle", "class", "", None),
    ("corners", "rectangle", "corners", "group", "6", None),
    ("roundness", "corners", "roundness", "number", "6", None),
    ("border", "rectangle", "border", "group", "not active", None),
    ("border_enabled", "border", "enabled", "bool", False, None),
    ("border_thickness", "border", "thickness", "number", "1", None),
    ("border_color", "border", "color", "color", "#565b5e", None),

    # --- Button Interaction -------------------------------------------
    ("interaction", "", "Button Interaction", "class", "", None),
    ("button_enabled", "interaction", "Interactable", "bool", True, None),

    # --- Main Colors --------------------------------------------------
    ("main_colors", "", "Main Colors", "class", "", None),
    ("fg_color", "main_colors", "background", "color", "#1f6aa5", None),
    ("hover_color", "main_colors", "hover", "color", "#144870", None),

    # --- Text ---------------------------------------------------------
    ("text", "", "Text", "class", "", None),
    ("label", "text", "label", "text", "CTkButton", None),
    ("font_size", "text", "Size", "number", "13", None),
    ("best_fit", "text", "Best Fit", "bool", False, None),
    ("style", "text", "style", "group", "bold", None),
    ("bold", "style", "bold", "bool", False, None),
    ("italic", "style", "italic", "bool", False, None),
    ("underline", "style", "underline", "bool", False, None),
    ("strike", "style", "strike", "bool", False, None),
    ("wrap", "style", "wrap", "bool", True, None),
    ("alignment", "text", "alignment", "enum", "Center", [
        "Top Left", "Top Center", "Top Right",
        "Middle Left", "Center", "Middle Right",
        "Bottom Left", "Bottom Center", "Bottom Right",
    ]),
    ("text_color_normal", "text", "Normal Text Color", "color",
     "#ffffff", None),
    ("text_color_disabled", "text", "Disabled Text Color", "color",
     "#a0a0a0", None),

    # --- Image & Alignment --------------------------------------------
    ("image_group", "", "Image & Alignment", "class", "", None),
    ("image", "image_group", "image", "image", "(no image)", None),
    ("image_color_normal", "image_group", "Normal Image Color", "color",
     "#ffffff", None),
    ("image_color_disabled", "image_group", "Disabled Image Color", "color",
     "#a0a0a0", None),
    ("image_alignment", "image_group", "alignment", "group",
     "W 20  H 20", None),
    ("image_width", "image_alignment", "width", "number", "20", None),
    ("image_height", "image_alignment", "height", "number", "20", None),
    ("compound", "image_group", "Position", "enum", "left",
     ["top", "left", "right", "bottom"]),
    ("preserve_aspect", "image_group", "Preserve Aspect", "bool",
     False, None),
]


class CTkButtonTreeMock(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color=PANEL_BG)

        self._editor_types: dict[str, str] = {}
        self._values: dict[str, object] = {}
        self._enum_options: dict[str, list[str]] = {}

        # Single in-place editor widget reference (Entry/Combobox) —
        # destroyed on commit. Never more than one at a time.
        self._active_editor: tk.Widget | None = None
        self._active_editor_iid: str | None = None

        # Persistent color swatch overlays — tk.Frame per color row,
        # placed at the row's value-cell bbox on scroll/expand/resize.
        self._color_overlays: dict[str, tk.Frame] = {}

        # Per-text-row pencil button overlay that opens the full
        # multi-line editor dialog.
        self._text_edit_overlays: dict[str, tk.Label] = {}
        # Per-text-row value overlay styled like a text-area field.
        self._text_value_overlays: dict[str, tk.Label] = {}
        # Per-enum-row dropdown button that pops up the option menu.
        self._enum_button_overlays: dict[str, tk.Label] = {}

        # Per-image-row filename display + open/clear button group.
        self._image_value_overlays: dict[str, tk.Label] = {}
        self._image_button_overlays: dict[str, tk.Frame] = {}

        # Font-style preview overlay — shows Bold/Italic/Underline/Strike
        # with each name brightened when the matching bool is on.
        self._style_preview_overlay: tk.Frame | None = None
        self._style_labels: dict[str, tk.Label] = {}

        self._build_type_header()
        self._build_name_row()
        self._build_style()
        self._build_tree()
        self._populate()

    # ------------------------------------------------------------------
    # Chrome
    # ------------------------------------------------------------------
    def _build_type_header(self) -> None:
        bar = ctk.CTkFrame(
            self, fg_color="#2a2a2a", height=28, corner_radius=0,
        )
        bar.pack(fill="x", pady=(0, 2))
        bar.pack_propagate(False)

        type_icon = load_icon("square", size=14, color="#3b8ed0")
        ctk.CTkLabel(
            bar, text="", image=type_icon,
            fg_color="#2a2a2a", width=16, height=20,
        ).pack(side="left", padx=(10, 0))

        ctk.CTkLabel(
            bar, text="CTkButton", fg_color="#2a2a2a",
            font=("Segoe UI", 12, "bold"), text_color="#3b8ed0",
            height=20,
        ).pack(side="left", padx=(4, 0))

        ctk.CTkButton(
            bar, text="?",
            font=("Segoe UI", 13, "bold"),
            text_color="#cccccc",
            width=22, height=20, corner_radius=3,
            fg_color="#2a2a2a", hover_color="#3a3a3a",
            border_width=0,
        ).pack(side="right", padx=(0, 8))

        ctk.CTkLabel(
            bar, text="ID: a3f8b2c1", fg_color="#2a2a2a",
            font=("Segoe UI", 10), text_color="#999999", height=20,
        ).pack(side="right", padx=(0, 4))

    def _build_name_row(self) -> None:
        row = tk.Frame(self, bg=BG, height=32, highlightthickness=0)
        row.pack(fill="x", pady=(2, 4), padx=6)
        row.pack_propagate(False)

        tk.Label(
            row, text="Name", bg=BG, fg="#888888",
            font=("Segoe UI", 10), anchor="w",
        ).pack(side="left", padx=(6, 8))

        self._name_var = tk.StringVar(value="Button1")
        entry = tk.Entry(
            row, textvariable=self._name_var,
            bg="#2d2d2d", fg="#cccccc",
            insertbackground="#cccccc",
            font=("Segoe UI", 11),
            relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground="#3a3a3a",
            highlightcolor="#3b8ed0",
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("default")
        except tk.TclError:
            pass
        style.configure(
            "PropTree.Treeview",
            background=TREE_BG,
            foreground=TREE_FG,
            fieldbackground=TREE_BG,
            bordercolor=BG,
            borderwidth=0,
            rowheight=28,
            font=("Segoe UI", 11),
        )
        style.map(
            "PropTree.Treeview",
            background=[("selected", TREE_SELECTED_BG)],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "PropTree.Treeview.Heading",
            background=TREE_HEADING_BG,
            foreground=TREE_HEADING_FG,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padding=(0, 8, 0, 8),
            anchor="center",
        )
        # Disable hover highlight on the heading row.
        style.map(
            "PropTree.Treeview.Heading",
            background=[
                ("active", TREE_HEADING_BG),
                ("pressed", TREE_HEADING_BG),
            ],
            foreground=[("active", TREE_HEADING_FG)],
        )
        style.layout(
            "PropTree.Treeview",
            [("PropTree.Treeview.treearea", {"sticky": "nswe"})],
        )

    def _build_tree(self) -> None:
        wrap = tk.Frame(self, bg=BG, highlightthickness=0)
        wrap.pack(fill="both", expand=True, padx=0, pady=0)

        # Custom header row (ttk heading anchor is unreliable on default
        # theme, so we draw our own centered header).
        header_bar = tk.Frame(
            wrap, bg=TREE_HEADING_BG, height=32,
            highlightthickness=0,
        )
        header_bar.pack(side="top", fill="x")
        header_bar.grid_propagate(False)
        header_bar.pack_propagate(False)
        header_bar.grid_columnconfigure(0, minsize=180)
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
        self._header_bar = header_bar

        self.tree = ttk.Treeview(
            wrap,
            columns=("value",),
            show="tree",
            style="PropTree.Treeview",
            selectmode="browse",
        )
        self.tree.column("#0", width=180, stretch=True, anchor="w")
        self.tree.column("value", width=180, stretch=True, anchor="w")

        # Class separator row styling
        self.tree.tag_configure(
            "class", background=CLASS_ROW_BG, foreground=CLASS_ROW_FG,
        )
        self.tree.tag_configure(
            "group", foreground=PREVIEW_FG,
        )
        self.tree.tag_configure(
            "bool_off", foreground="#666666", background=TREE_BG,
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

        # Vertical column separator placed at the Property/Value boundary.
        # Column #0 defaults to 180px wide; reposition on <Configure> so
        # it still lines up if the user drags the column header.
        self._col_separator = tk.Frame(
            self.tree, bg="#3a3a3a", width=1,
            highlightthickness=0,
        )
        self._col_separator.place(x=180, rely=0, relheight=1)
        self.tree.bind(
            "<Configure>", self._reposition_col_separator, add="+",
        )

        # Bindings
        self.tree.bind("<Double-Button-1>", self._on_double_click)
        self.tree.bind("<Button-1>", self._on_single_click, add="+")
        self.tree.bind("<FocusOut>", self._on_tree_focus_out, add="+")
        self.tree.bind("<<TreeviewOpen>>", self._on_tree_layout_change,
                       add="+")
        self.tree.bind("<<TreeviewClose>>", self._on_tree_layout_change,
                       add="+")
        self.tree.bind("<Configure>", self._on_tree_layout_change, add="+")

    # ------------------------------------------------------------------
    # Scroll / layout forwarding
    # ------------------------------------------------------------------
    def _on_yscrollcommand(self, first, last) -> None:
        self._vscroll.set(first, last)
        self._schedule_reposition()

    def _on_vscroll(self, *args) -> None:
        self.tree.yview(*args)
        self._schedule_reposition()

    def _on_tree_layout_change(self, _event=None) -> None:
        self._schedule_reposition()

    def _on_tree_focus_out(self, _event=None) -> None:
        sel = self.tree.selection()
        if sel:
            self.tree.selection_remove(*sel)

    def _reposition_col_separator(self, _event=None) -> None:
        try:
            col_w = int(self.tree.column("#0", "width"))
        except tk.TclError:
            return
        try:
            self._col_separator.place_configure(x=col_w)
            self._col_separator.lift()
        except tk.TclError:
            pass

    def _schedule_reposition(self) -> None:
        # Defer to after_idle so the tree has laid out and bbox() returns
        # meaningful values for freshly opened / scrolled rows.
        self.after_idle(self._reposition_overlays)

    # ------------------------------------------------------------------
    # Populate
    # ------------------------------------------------------------------
    def _populate(self) -> None:
        for iid, parent, label, editor, value, options in SCHEMA:
            self._editor_types[iid] = editor
            self._values[iid] = value
            if options is not None:
                self._enum_options[iid] = list(options)

            # Text / image rows leave the tree cell empty; the value
            # lives in an overlay label created below. `style` group
            # also uses an overlay for its multi-color preview.
            if editor in ("text", "image") or iid == "style":
                display_value = ""
            else:
                display_value = self._format_value(editor, value)
            tags: tuple[str, ...] = ()
            if editor == "class":
                tags = ("class",)
            elif editor == "group":
                tags = ("group",)
            elif editor == "bool" and not value:
                tags = ("bool_off",)

            self.tree.insert(
                parent, "end", iid=iid,
                text=label,
                values=(display_value,),
                open=(editor == "class"),  # classes start expanded
                tags=tags,
            )

            if editor == "color":
                overlay = tk.Frame(
                    self.tree, bg=str(value),
                    highlightthickness=1, highlightbackground="#3a3a3a",
                    cursor="hand2",
                )
                self._color_overlays[iid] = overlay

            if editor == "text":
                # Text-area styled value box — darker than the tree bg,
                # no border.
                value_label = tk.Label(
                    self.tree, text=self._format_value(editor, value),
                    bg="#181818", fg="#cccccc",
                    font=("Segoe UI", 11), anchor="w",
                    relief="flat", bd=0, padx=6,
                    cursor="xterm",
                )
                value_label.bind(
                    "<Double-Button-1>",
                    lambda _e, i=iid: self._edit_text_inline(i),
                )
                self._text_value_overlays[iid] = value_label

                btn = tk.Label(
                    self.tree, text="✎", bg=TREE_BG,
                    fg="#aaaaaa", font=("Segoe UI Symbol", 12),
                    cursor="hand2", borderwidth=0,
                )
                btn.bind(
                    "<Button-1>",
                    lambda _e, i=iid: self._open_text_editor(i),
                )
                self._text_edit_overlays[iid] = btn

            if editor == "enum":
                btn = tk.Label(
                    self.tree, text="▾", bg=TREE_BG,
                    fg="#aaaaaa", font=("Segoe UI", 12, "bold"),
                    cursor="hand2", borderwidth=0,
                )
                btn.bind(
                    "<Button-1>",
                    lambda _e, i=iid, b=btn: self._popup_enum_menu(
                        i, b.winfo_rootx(),
                        b.winfo_rooty() + b.winfo_height(),
                    ),
                )
                self._enum_button_overlays[iid] = btn

            if editor == "image":
                value_label = tk.Label(
                    self.tree, text=str(value), bg="#181818", fg="#cccccc",
                    font=("Segoe UI", 11), anchor="w",
                    relief="flat", bd=0, padx=6,
                )
                self._image_value_overlays[iid] = value_label

                btn_frame = tk.Frame(self.tree, bg=TREE_BG)
                open_btn = tk.Label(
                    btn_frame, text="open", bg="#2d2d2d", fg="#cccccc",
                    font=("Segoe UI", 10), padx=8, cursor="hand2",
                )
                open_btn.pack(side="left", padx=(0, 2))
                open_btn.bind(
                    "<Button-1>",
                    lambda _e, i=iid: self._on_image_open(i),
                )
                clear_btn = tk.Label(
                    btn_frame, text="clear", bg="#2d2d2d", fg="#cccccc",
                    font=("Segoe UI", 10), padx=8, cursor="hand2",
                )
                clear_btn.pack(side="left")
                clear_btn.bind(
                    "<Button-1>",
                    lambda _e, i=iid: self._on_image_clear(i),
                )
                self._image_button_overlays[iid] = btn_frame

        # Apply parent-preview updates for the initial bool state
        # (e.g. Border shows "not active" when border_enabled is off).
        for bool_iid in PARENT_PREVIEW_BOOLS:
            self._apply_parent_preview(
                bool_iid, bool(self._values.get(bool_iid)),
            )

        # Build the font-style preview frame with 4 labels, one per
        # Bold/Italic/Underline/Strike. Each label's foreground tracks
        # the matching bool value.
        self._style_preview_overlay = tk.Frame(self.tree, bg=TREE_BG)
        for bool_iid, label_text in STYLE_BOOL_LABELS.items():
            lbl = tk.Label(
                self._style_preview_overlay, text=label_text,
                bg=TREE_BG, font=("Segoe UI", 10),
                fg=self._style_label_color(bool_iid),
            )
            lbl.pack(side="left", padx=(0, 8))
            self._style_labels[bool_iid] = lbl

        self._schedule_reposition()

    def _style_label_color(self, bool_iid: str) -> str:
        return "#cccccc" if self._values.get(bool_iid) else "#555555"

    def _refresh_style_preview(self) -> None:
        for bool_iid, lbl in self._style_labels.items():
            try:
                lbl.configure(fg=self._style_label_color(bool_iid))
            except tk.TclError:
                pass

    def _apply_parent_preview(self, bool_iid: str, enabled: bool) -> None:
        spec = PARENT_PREVIEW_BOOLS.get(bool_iid)
        if spec is None:
            return
        preview = (
            spec["active_preview"] if enabled else spec["inactive_preview"]
        )
        self.tree.set(spec["parent"], "value", preview)

    # ------------------------------------------------------------------
    # Overlay positioning — shared between color swatches + bool icons
    # ------------------------------------------------------------------
    def _reposition_overlays(self) -> None:
        """Sync color + text value + text-edit + enum-button + style."""
        for iid, overlay in self._color_overlays.items():
            self._place_overlay_at_row(overlay, iid, width=50, pad_y=4)
        for iid, overlay in self._text_value_overlays.items():
            self._place_text_value_overlay(overlay, iid)
        for iid, overlay in self._text_edit_overlays.items():
            self._place_overlay_right(overlay, iid, width=20, pad_y=4)
        for iid, overlay in self._enum_button_overlays.items():
            self._place_overlay_right(overlay, iid, width=20, pad_y=4)
        if self._style_preview_overlay is not None:
            self._place_overlay_at_row(
                self._style_preview_overlay, "style",
                width=300, pad_y=3,
            )
        for iid, overlay in self._image_value_overlays.items():
            self._place_image_value_overlay(overlay, iid)
        for iid, overlay in self._image_button_overlays.items():
            self._place_image_buttons(overlay, iid)

    # Image value / buttons layout — reserves ~100px on the right
    # (large enough for "open" + "clear" labels).
    _IMAGE_BTN_RESERVE = 100

    def _place_image_value_overlay(
        self, overlay: tk.Widget, iid: str,
    ) -> None:
        try:
            bbox = self.tree.bbox(iid, "value")
        except tk.TclError:
            bbox = ()
        if not bbox:
            overlay.place_forget()
            return
        x, y, w, h = bbox
        overlay.place(
            x=x + 4, y=y + 3,
            width=max(1, w - self._IMAGE_BTN_RESERVE - 4),
            height=max(1, h - 6),
        )
        overlay.lift()

    def _place_image_buttons(
        self, frame: tk.Widget, iid: str,
    ) -> None:
        try:
            bbox = self.tree.bbox(iid, "value")
        except tk.TclError:
            bbox = ()
        if not bbox:
            frame.place_forget()
            return
        x, y, w, h = bbox
        btn_width = self._IMAGE_BTN_RESERVE - 4
        frame.place(
            x=x + w - btn_width - 4, y=y + 3,
            width=btn_width, height=max(1, h - 6),
        )
        frame.lift()

    def _on_image_open(self, iid: str) -> None:
        overlay = self._image_value_overlays.get(iid)
        if overlay is None:
            return
        demo_name = "demo_image.png"
        self._values[iid] = demo_name
        overlay.configure(text=demo_name)

    def _on_image_clear(self, iid: str) -> None:
        overlay = self._image_value_overlays.get(iid)
        if overlay is None:
            return
        placeholder = "(no image)"
        self._values[iid] = placeholder
        overlay.configure(text=placeholder)

    def _place_text_value_overlay(
        self, overlay: tk.Widget, iid: str,
    ) -> None:
        """Text value overlay — fills the value cell left of the pencil
        button (reserves 26px on the right for the button).
        """
        try:
            bbox = self.tree.bbox(iid, "value")
        except tk.TclError:
            bbox = ()
        if not bbox:
            overlay.place_forget()
            return
        x, y, w, h = bbox
        overlay.place(
            x=x + 4, y=y + 3,
            width=max(1, w - 32), height=max(1, h - 6),
        )
        overlay.lift()

    def _place_overlay_at_row(
        self, overlay: tk.Widget, iid: str, *, width: int, pad_y: int,
    ) -> None:
        try:
            bbox = self.tree.bbox(iid, "value")
        except tk.TclError:
            bbox = ()
        if not bbox:
            overlay.place_forget()
            return
        x, y, _w, h = bbox
        overlay.place(
            x=x + 4, y=y + pad_y,
            width=width, height=max(1, h - pad_y * 2),
        )
        overlay.lift()

    def _place_overlay_right(
        self, overlay: tk.Widget, iid: str, *, width: int, pad_y: int,
    ) -> None:
        """Like `_place_overlay_at_row` but anchored to the right edge."""
        try:
            bbox = self.tree.bbox(iid, "value")
        except tk.TclError:
            bbox = ()
        if not bbox:
            overlay.place_forget()
            return
        x, y, w, h = bbox
        overlay.place(
            x=x + w - width - 4, y=y + pad_y,
            width=width, height=max(1, h - pad_y * 2),
        )
        overlay.lift()

    def _format_value(self, editor: str, value) -> str:
        if editor in ("class",):
            return ""
        if editor == "bool":
            return "☑" if value else "☐"
        if editor == "color":
            # Leading spaces clear room for the swatch overlay.
            return f"              {value}" if value else ""
        if editor == "group":
            return str(value)
        if editor == "text":
            s = str(value) if value is not None else ""
            # Collapse newlines to a single-line preview.
            if "\n" in s:
                first, _, _ = s.partition("\n")
                return first + " …"
            return s
        return str(value) if value is not None else ""

    def _refresh_value(self, iid: str) -> None:
        editor = self._editor_types[iid]
        display = self._format_value(editor, self._values[iid])
        if editor == "text":
            # Text rows leave the tree cell empty and paint the value
            # via the overlay label so it can have its own styling.
            self.tree.set(iid, "value", "")
            overlay = self._text_value_overlays.get(iid)
            if overlay is not None:
                overlay.configure(text=display)
            return
        self.tree.set(iid, "value", display)

    # ------------------------------------------------------------------
    # Click handlers
    # ------------------------------------------------------------------
    def _on_single_click(self, event) -> None:
        region = self.tree.identify_region(event.x, event.y)
        if region == "nothing":
            # Click on empty area → clear selection.
            self.tree.selection_remove(*self.tree.selection())
            return
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        if col != "#1":   # not the Value column
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        editor = self._editor_types.get(iid)
        if editor == "bool":
            new_value = not self._values[iid]
            self._values[iid] = new_value
            self._refresh_value(iid)
            if new_value:
                self.tree.item(iid, tags=())
            else:
                self.tree.item(iid, tags=("bool_off",))
            if iid in PARENT_PREVIEW_BOOLS:
                self._apply_parent_preview(iid, new_value)
            if iid in STYLE_BOOL_LABELS:
                self._refresh_style_preview()

    def _on_double_click(self, event) -> str | None:
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return None
        col = self.tree.identify_column(event.x)
        if col != "#1":
            return None
        iid = self.tree.identify_row(event.y)
        if not iid:
            return None
        editor = self._editor_types.get(iid)
        if editor in (None, "class", "group", "bool"):
            return None

        bbox = self.tree.bbox(iid, col)
        if not bbox:
            return None

        self._commit_active_editor()

        if editor == "enum":
            self._popup_enum_menu(iid, event.x_root, event.y_root)
            return "break"

        # text / number / color / image → simple Entry overlay
        var = tk.StringVar(value=str(self._values[iid]))
        entry = tk.Entry(
            self.tree, textvariable=var,
            font=("Segoe UI", 10), bd=1, relief="flat",
            bg="#2d2d2d", fg="#cccccc", insertbackground="#cccccc",
            highlightthickness=1, highlightbackground="#3a3a3a",
            highlightcolor="#3b8ed0",
        )
        entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        entry.select_range(0, tk.END)
        entry.focus_set()
        self._active_editor = entry
        self._active_editor_iid = iid
        entry.bind("<Return>", lambda _e: self._commit_active_editor())
        entry.bind("<FocusOut>", lambda _e: self._commit_active_editor())
        entry.bind("<Escape>", lambda _e: self._cancel_active_editor())
        return "break"

    def _popup_enum_menu(self, iid: str, x_root: int, y_root: int) -> None:
        options = self._enum_options.get(iid, [])
        if not options:
            return
        current = str(self._values.get(iid, ""))
        menu = tk.Menu(
            self, tearoff=0,
            bg="#2d2d30", fg="#cccccc",
            activebackground="#094771", activeforeground="#ffffff",
            bd=0, borderwidth=0, relief="flat",
            font=("Segoe UI", 10),
        )
        for opt in options:
            prefix = "• " if opt == current else "   "
            menu.add_command(
                label=f"{prefix}{opt}",
                command=lambda o=opt, i=iid: self._commit_enum(i, o),
            )
        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()

    def _commit_enum(self, iid: str, value: str) -> None:
        self._values[iid] = value
        self._refresh_value(iid)

    def _edit_text_inline(self, iid: str) -> None:
        """Place a tk.Entry overlay over the text value label so the
        user can do a fast single-line edit without opening the modal.
        """
        overlay = self._text_value_overlays.get(iid)
        if overlay is None:
            return
        self._commit_active_editor()

        # Overlay coordinates relative to tree (both widgets share it).
        self.tree.update_idletasks()
        x = overlay.winfo_x()
        y = overlay.winfo_y()
        w = overlay.winfo_width()
        h = overlay.winfo_height()

        entry = tk.Entry(
            self.tree, font=("Segoe UI", 11),
            bg="#2d2d2d", fg="#cccccc", insertbackground="#cccccc",
            bd=1, relief="flat",
            highlightthickness=1, highlightbackground="#3b8ed0",
            highlightcolor="#3b8ed0",
        )
        entry.insert(0, str(self._values.get(iid, "")))
        entry.place(x=x, y=y, width=w, height=h)
        entry.select_range(0, tk.END)
        entry.focus_set()
        self._active_editor = entry
        self._active_editor_iid = iid
        entry.bind("<Return>", lambda _e: self._commit_active_editor())
        entry.bind("<FocusOut>", lambda _e: self._commit_active_editor())
        entry.bind("<Escape>", lambda _e: self._cancel_active_editor())

    def _open_text_editor(self, iid: str) -> None:
        current = str(self._values.get(iid, ""))
        dialog = TextEditorDialog(
            self.winfo_toplevel(),
            f"Edit: {self.tree.item(iid, 'text')}",
            current,
        )
        dialog.wait_window()
        if dialog.result is None:
            return
        self._values[iid] = dialog.result
        self._refresh_value(iid)
        self._schedule_reposition()

    def _commit_active_editor(self) -> None:
        if self._active_editor is None or self._active_editor_iid is None:
            return
        iid = self._active_editor_iid
        try:
            new_value = self._active_editor.get()
        except tk.TclError:
            new_value = ""
        self._values[iid] = new_value
        self._refresh_value(iid)
        # Sync color overlay background if this row is a color editor.
        if self._editor_types.get(iid) == "color":
            overlay = self._color_overlays.get(iid)
            if overlay is not None:
                try:
                    overlay.configure(bg=str(new_value))
                except tk.TclError:
                    pass
        try:
            self._active_editor.destroy()
        except tk.TclError:
            pass
        self._active_editor = None
        self._active_editor_iid = None
        # Repaint overlays — the temporary Entry may have been drawn
        # on top of persistent ones (color swatches, text edit buttons).
        self._schedule_reposition()

    def _cancel_active_editor(self) -> None:
        if self._active_editor is None:
            return
        try:
            self._active_editor.destroy()
        except tk.TclError:
            pass
        self._active_editor = None
        self._active_editor_iid = None


class MockApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CTkButton — ttk.Treeview Mock")
        self.geometry(f"{PANEL_WIDTH + 40}x{PANEL_HEIGHT}")
        ctk.set_appearance_mode("dark")
        self.configure(fg_color=BG)

        wrap = ctk.CTkFrame(self, fg_color=BG)
        wrap.pack(fill="both", expand=True, padx=10, pady=10)

        self.panel = CTkButtonTreeMock(wrap)
        self.panel.pack(fill="both", expand=True)


if __name__ == "__main__":
    MockApp().mainloop()
