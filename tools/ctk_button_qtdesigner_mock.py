"""CTkButton Properties panel — Qt Designer style mock v2.

v2 collapses the earlier "group header vs property row vs subgroup row"
distinction into a single row abstraction, matching Qt Designer's
actual shape: every entry is just a row that may have an expand arrow
and may have children. Class-name separators ("Geometry", "Rectangle")
are rendered with the same row builder, only with a darker stripe and
bold text.

Run:
    python tools/ctk_button_qtdesigner_mock.py

Nothing in this file touches app/.
"""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk


# =====================================================================
# Colors (builder dark theme)
# =====================================================================
BG = "#1e1e1e"
PANEL_BG = "#252526"
VALUE_BG = "#2d2d2d"
CLASS_ROW_BG = "#2b2b2b"     # class-name separator stripe
TABLE_HEADER_BG = "#383838"
COL_SEP = "#3a3a3a"
ROW_HOVER_BG = "#2f2f33"

STATIC_FG = "#888888"
HEADER_FG = "#cccccc"
CLASS_FG = "#dddddd"          # class-row label (bold)
VALUE_FG = "#cccccc"
PREVIEW_FG = "#888888"        # collapsed parent preview value
TYPE_LABEL_FG = "#3b8ed0"
DISABLED_FG = "#555555"

# =====================================================================
# Dimensions
# =====================================================================
PANEL_WIDTH = 380
PROP_COL_WIDTH = 160
ROW_HEIGHT = 20
TABLE_HEADER_HEIGHT = 22
ENTRY_HEIGHT = 16
ARROW_CELL_WIDTH = 14
INDENT_PER_LEVEL = 12

# =====================================================================
# Schema — Qt Designer-style nested rows
#
# Row = {
#     "label": str,
#     "editor": str | None,        # "number", "text", "color",
#                                  # "checkbox", "dropdown", "image", None
#     "value": Any,                # for dropdown: (current, options)
#     "preview": str | None,       # shown in value cell when collapsed
#     "children": list[Row] | None,
#     "is_class": bool,            # True for class-name separator rows
#     "start_collapsed": bool,
# }
# =====================================================================
def _row(label, editor=None, value=None, preview=None,
         children=None, is_class=False, start_collapsed=False):
    return {
        "label": label,
        "editor": editor,
        "value": value,
        "preview": preview,
        "children": children,
        "is_class": is_class,
        "start_collapsed": start_collapsed,
    }


SCHEMA = [
    _row("Geometry", is_class=True, children=[
        _row("position", preview="120, 120", start_collapsed=True, children=[
            _row("x", editor="number", value=120),
            _row("y", editor="number", value=120),
        ]),
        _row("size", preview="140 × 32", start_collapsed=True, children=[
            _row("width", editor="number", value=140),
            _row("height", editor="number", value=32),
        ]),
    ]),

    _row("Rectangle", is_class=True, children=[
        _row("corners", preview="6", start_collapsed=True, children=[
            _row("roundness", editor="number", value=6),
        ]),
        _row("border", preview="0", start_collapsed=True, children=[
            _row("thickness", editor="number", value=0),
            _row("color", editor="color", value="#565b5e"),
        ]),
    ]),

    _row("State", is_class=True, children=[
        _row("disabled", editor="checkbox", value=False),
    ]),

    _row("Main Colors", is_class=True, children=[
        _row("background", editor="color", value="#1f6aa5"),
        _row("hover", editor="color", value="#144870"),
    ]),

    _row("Text", is_class=True, children=[
        _row("label", editor="text", value="CTkButton"),
        _row("style", preview="13", start_collapsed=True, children=[
            _row("size", editor="number", value=13),
            _row("best fit", editor="checkbox", value=False),
            _row("bold", editor="checkbox", value=False),
            _row("italic", editor="checkbox", value=False),
            _row("underline", editor="checkbox", value=False),
            _row("strike", editor="checkbox", value=False),
        ]),
        _row("alignment", editor="dropdown", value=("Center", [
            "Top Left", "Top Center", "Top Right",
            "Middle Left", "Center", "Middle Right",
            "Bottom Left", "Bottom Center", "Bottom Right",
        ])),
        _row("color", preview="#ffffff", start_collapsed=True, children=[
            _row("normal", editor="color", value="#ffffff"),
            _row("disabled", editor="color", value="#a0a0a0"),
        ]),
    ]),

    _row("Image & Alignment", is_class=True, children=[
        _row("image", editor="image", value="(no image)"),
        _row("color", preview="#ffffff", start_collapsed=True, children=[
            _row("normal", editor="color", value="#ffffff"),
            _row("disabled", editor="color", value="#a0a0a0"),
        ]),
        _row("alignment", preview="20 × 20, left", start_collapsed=True,
             children=[
                 _row("width", editor="number", value=20),
                 _row("height", editor="number", value=20),
                 _row("position", editor="dropdown", value=(
                     "left", ["top", "left", "right", "bottom"])),
                 _row("preserve aspect", editor="checkbox", value=False),
             ]),
    ]),
]


# =====================================================================
# Panel
# =====================================================================
class QtDesignerMockPanel(ctk.CTkScrollableFrame):
    def __init__(self, master):
        super().__init__(
            master, fg_color=PANEL_BG, corner_radius=0,
            label_text="", width=PANEL_WIDTH,
        )

        # Track collapsed rows by stable id — the row dict's id().
        # Seed from start_collapsed flag.
        self._collapsed: set[int] = set()
        self._seed_collapsed(SCHEMA)

        self.rebuild()

    def _seed_collapsed(self, rows):
        for r in rows:
            if r["start_collapsed"]:
                self._collapsed.add(id(r))
            if r["children"]:
                self._seed_collapsed(r["children"])

    # ------------------------------------------------------------------
    def rebuild(self) -> None:
        for child in self.winfo_children():
            child.destroy()

        self._build_table_header()
        self._build_type_header()

        for row in SCHEMA:
            self._render_row(row, depth=0)

    # ------------------------------------------------------------------
    # Fixed headers
    # ------------------------------------------------------------------
    def _build_table_header(self) -> None:
        bar = ctk.CTkFrame(
            self, fg_color=TABLE_HEADER_BG, height=TABLE_HEADER_HEIGHT,
            corner_radius=0,
        )
        bar.pack(fill="x", pady=(0, 0))
        bar.pack_propagate(False)
        bar.grid_columnconfigure(0, minsize=PROP_COL_WIDTH)
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            bar, text="Property", fg_color=TABLE_HEADER_BG,
            font=("Segoe UI", 10, "bold"), text_color=HEADER_FG,
            anchor="w", height=16,
        ).grid(row=0, column=0, sticky="w", padx=(10, 0))

        # Thin column separator
        sep = ctk.CTkFrame(
            bar, fg_color=COL_SEP, width=1, corner_radius=0,
        )
        sep.place(x=PROP_COL_WIDTH - 1, rely=0, relheight=1)

        ctk.CTkLabel(
            bar, text="Value", fg_color=TABLE_HEADER_BG,
            font=("Segoe UI", 10, "bold"), text_color=HEADER_FG,
            anchor="w", height=16,
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))

    def _build_type_header(self) -> None:
        bar = ctk.CTkFrame(
            self, fg_color="#2a2a2a", height=22, corner_radius=0,
        )
        bar.pack(fill="x", pady=(0, 0))
        bar.pack_propagate(False)

        ctk.CTkLabel(
            bar, text="CTkButton", fg_color="#2a2a2a",
            font=("Segoe UI", 11, "bold"), text_color=TYPE_LABEL_FG,
            height=16,
        ).pack(side="left", padx=(10, 0))

        ctk.CTkLabel(
            bar, text="?", fg_color="#2a2a2a",
            font=("Segoe UI", 10, "bold"), text_color=STATIC_FG,
            height=16, width=18,
        ).pack(side="right", padx=(0, 8))

        ctk.CTkLabel(
            bar, text="ID: a3f8b2c1", fg_color="#2a2a2a",
            font=("Segoe UI", 8), text_color=DISABLED_FG, height=16,
        ).pack(side="right", padx=(0, 4))

    # ------------------------------------------------------------------
    # Unified row renderer
    # ------------------------------------------------------------------
    def _render_row(self, row: dict, depth: int) -> None:
        """Render one row, then recurse into its children if expanded."""
        has_children = bool(row["children"])
        is_collapsed = id(row) in self._collapsed
        is_class = row["is_class"]

        row_bg = CLASS_ROW_BG if is_class else "transparent"

        frame = ctk.CTkFrame(
            self, fg_color=row_bg, height=ROW_HEIGHT, corner_radius=0,
        )
        frame.pack(fill="x", pady=0)
        frame.pack_propagate(False)
        frame.grid_columnconfigure(0, minsize=PROP_COL_WIDTH)
        frame.grid_columnconfigure(1, weight=1)

        # --- Property column (label + optional arrow) ----------------
        prop_cell = ctk.CTkFrame(
            frame, fg_color=row_bg, height=ROW_HEIGHT,
        )
        prop_cell.grid(row=0, column=0, sticky="nsew")
        prop_cell.pack_propagate(False)

        arrow_text = ""
        if has_children:
            arrow_text = "▶" if is_collapsed else "▼"

        indent = 6 + depth * INDENT_PER_LEVEL
        arrow_label = ctk.CTkLabel(
            prop_cell, text=arrow_text, fg_color=row_bg,
            font=("Segoe UI", 8, "bold"), text_color=STATIC_FG,
            width=ARROW_CELL_WIDTH, height=16,
        )
        arrow_label.pack(side="left", padx=(indent, 2))

        label_font = (
            ("Segoe UI", 10, "bold") if is_class
            else ("Segoe UI", 10)
        )
        label_color = CLASS_FG if is_class else VALUE_FG
        label_widget = ctk.CTkLabel(
            prop_cell, text=row["label"], fg_color=row_bg,
            font=label_font, text_color=label_color,
            anchor="w", height=16,
        )
        label_widget.pack(side="left")

        # --- Column separator ----------------------------------------
        sep = ctk.CTkFrame(
            frame, fg_color=COL_SEP, width=1, corner_radius=0,
        )
        sep.place(x=PROP_COL_WIDTH - 1, rely=0, relheight=1)

        # --- Value column --------------------------------------------
        value_cell = ctk.CTkFrame(
            frame, fg_color=row_bg, height=ROW_HEIGHT,
        )
        value_cell.grid(row=0, column=1, sticky="nsew", padx=(8, 10))
        value_cell.pack_propagate(False)

        if has_children and is_collapsed and row["preview"] is not None:
            ctk.CTkLabel(
                value_cell, text=row["preview"], fg_color=row_bg,
                font=("Segoe UI", 9), text_color=PREVIEW_FG,
                anchor="w", height=16,
            ).pack(side="left", fill="x", expand=True)
        elif row["editor"] is not None:
            self._build_editor(value_cell, row["editor"], row["value"])

        # --- Click-to-toggle for rows with children ------------------
        if has_children:
            for w in (frame, prop_cell, arrow_label, label_widget):
                w.bind("<Button-1>",
                       lambda _e, r=row: self._toggle(r))
                try:
                    w.configure(cursor="hand2")
                except tk.TclError:
                    pass

        # --- Recurse into children -----------------------------------
        if has_children and not is_collapsed:
            for child in row["children"]:
                self._render_row(child, depth + 1)

    def _toggle(self, row: dict) -> None:
        rid = id(row)
        if rid in self._collapsed:
            self._collapsed.discard(rid)
        else:
            self._collapsed.add(rid)
        self.rebuild()

    # ------------------------------------------------------------------
    # Editor factories (all dummies)
    # ------------------------------------------------------------------
    def _build_editor(self, parent, editor_type: str, value) -> None:
        if editor_type == "number":
            self._mk_entry(parent, value)
        elif editor_type == "text":
            self._mk_entry(parent, value, fill=True)
        elif editor_type == "color":
            self._mk_color(parent, value)
        elif editor_type == "checkbox":
            self._mk_checkbox(parent, value)
        elif editor_type == "dropdown":
            current, options = value
            self._mk_dropdown(parent, current, options)
        elif editor_type == "image":
            self._mk_image_picker(parent, value)

    def _mk_entry(self, parent, value, *, fill: bool = False) -> None:
        entry = ctk.CTkEntry(
            parent, height=ENTRY_HEIGHT, width=52,
            corner_radius=2, font=("Segoe UI", 10),
            fg_color=VALUE_BG, border_width=0,
        )
        entry.insert(0, str(value))
        if fill:
            entry.pack(side="left", fill="x", expand=True)
        else:
            entry.pack(side="left")

    def _mk_color(self, parent, value) -> None:
        btn = ctk.CTkButton(
            parent, text="", height=ENTRY_HEIGHT, width=40,
            corner_radius=2, fg_color=value,
            hover_color=value, border_width=0,
        )
        btn.pack(side="left")
        ctk.CTkLabel(
            parent, text=str(value),
            font=("Segoe UI", 9), text_color=STATIC_FG, height=16,
        ).pack(side="left", padx=(6, 0))

    def _mk_checkbox(self, parent, value) -> None:
        cb = ctk.CTkCheckBox(
            parent, text="", width=14, height=14,
            checkbox_width=14, checkbox_height=14,
        )
        if value:
            cb.select()
        cb.pack(side="left")

    def _mk_dropdown(self, parent, current, options) -> None:
        menu = ctk.CTkOptionMenu(
            parent, values=options,
            height=ENTRY_HEIGHT + 4,
            font=("Segoe UI", 10), dropdown_font=("Segoe UI", 10),
            corner_radius=2, fg_color=VALUE_BG, button_color=VALUE_BG,
            button_hover_color="#3a3a3a",
        )
        menu.set(current)
        menu.pack(side="left", fill="x", expand=True)

    def _mk_image_picker(self, parent, value) -> None:
        name_box = ctk.CTkFrame(
            parent, fg_color=VALUE_BG, corner_radius=2,
            height=ENTRY_HEIGHT, width=1,
        )
        name_box.pack(side="left", fill="x", expand=True, padx=(0, 4))
        name_box.pack_propagate(False)

        ctk.CTkLabel(
            name_box, text=str(value), fg_color=VALUE_BG,
            anchor="w", height=ENTRY_HEIGHT,
            font=("Segoe UI", 9), text_color=VALUE_FG,
        ).pack(side="left", fill="x", expand=True, padx=(6, 4))

        ctk.CTkButton(
            parent, text="...",
            width=20, height=ENTRY_HEIGHT,
            font=("Segoe UI", 10, "bold"),
            fg_color=VALUE_BG, hover_color="#3a3a3a",
            border_width=0, corner_radius=2,
        ).pack(side="left", padx=(0, 2))

        ctk.CTkButton(
            parent, text="×",
            width=20, height=ENTRY_HEIGHT,
            font=("Segoe UI", 12),
            fg_color=VALUE_BG, hover_color="#3a3a3a",
            border_width=0, corner_radius=2,
        ).pack(side="left")


# =====================================================================
# Main window
# =====================================================================
class MockApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CTkButton — Qt Designer Style Mock v2")
        self.geometry(f"{PANEL_WIDTH + 40}x780")
        ctk.set_appearance_mode("dark")
        self.configure(fg_color=BG)

        wrap = ctk.CTkFrame(self, fg_color=BG)
        wrap.pack(fill="both", expand=True, padx=10, pady=10)

        self.panel = QtDesignerMockPanel(wrap)
        self.panel.pack(fill="both", expand=True)


if __name__ == "__main__":
    MockApp().mainloop()
