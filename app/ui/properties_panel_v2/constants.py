"""Module-level constants for the Properties panel v2.

Colors, sizing, enum maps, and style dictionaries shared across the
panel, format utilities, and any future editor modules.
"""

from __future__ import annotations


# =====================================================================
# Colors / sizing
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
DISABLED_FG = "#555555"
COLUMN_SEP = "#3a3a3a"
VALUE_BG = "#2d2d2d"
TEXT_BG = "#181818"
HEADER_BG = "#2a2a2a"
TYPE_LABEL_FG = "#3b8ed0"
STATIC_FG = "#888888"
BOOL_OFF_FG = "#666666"

PROP_COL_WIDTH = 170
ROW_HEIGHT = 28
PANEL_MIN_WIDTH = 300


# =====================================================================
# Enum value maps
# =====================================================================
ANCHOR_CODE_TO_LABEL = {
    "nw": "Top Left",    "n":  "Top Center",    "ne": "Top Right",
    "w":  "Middle Left", "center": "Center",    "e":  "Middle Right",
    "sw": "Bottom Left", "s":  "Bottom Center", "se": "Bottom Right",
}
ANCHOR_LABEL_TO_CODE = {v: k for k, v in ANCHOR_CODE_TO_LABEL.items()}
ANCHOR_DROPDOWN_ORDER = list(ANCHOR_CODE_TO_LABEL.values())

COMPOUND_OPTIONS = ["top", "left", "right", "bottom"]
JUSTIFY_OPTIONS = ["left", "center", "right"]


# =====================================================================
# Popup menu style
# =====================================================================
MENU_STYLE = dict(
    bg="#2d2d30", fg="#cccccc",
    activebackground="#094771", activeforeground="#ffffff",
    bd=0, borderwidth=0, relief="flat",
    font=("Segoe UI", 10),
)


# Style bool rows that contribute to the "Style" subgroup preview.
STYLE_BOOL_NAMES = {
    "font_bold": "Bold",
    "font_italic": "Italic",
    "font_underline": "Underline",
    "font_overstrike": "Strike",
    "font_wrap": "Wrap",
}
