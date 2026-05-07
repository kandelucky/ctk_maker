"""Module-level constants for the Properties panel v2.

Colors, sizing, enum maps, and style dictionaries shared across the
panel, format utilities, and any future editor modules.
"""

from __future__ import annotations
from app.ui.system_fonts import ui_font


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

# Property tooltip — dark popup shown on label-column hover.
TOOLTIP_BG = "#2d2d30"
TOOLTIP_FG = "#cccccc"
TOOLTIP_WARNING_FG = "#fbbf24"
TOOLTIP_BORDER = "#3f3f46"
TOOLTIP_DELAY_MS = 750
TOOLTIP_WRAPLENGTH = 320


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

COMPOUND_OPTIONS = ["top", "left", "right", "bottom", "center"]
CURSOR_OPTIONS = [
    "",
    "arrow",
    "hand2",
    "xterm",
    "watch",
    "crosshair",
    "plus",
    "circle",
    "question_arrow",
]
JUSTIFY_OPTIONS = ["left", "center", "right"]
TAB_BAR_ALIGN_OPTIONS = ["left", "center", "right", "stretch"]
TAB_BAR_POSITION_OPTIONS = ["top", "bottom"]
ORIENTATION_OPTIONS = ["horizontal", "vertical"]
TEXT_POSITION_OPTIONS = ["left", "right", "top", "bottom"]
WRAP_OPTIONS = ["none", "char", "word"]
UNIT_SUFFIX_OPTIONS = ["none", "%", "°", "°C", "°F", "kg", "g", "km", "m", "s", "ms"]


# =====================================================================
# Popup menu style
# =====================================================================
def menu_style() -> dict:
    """Return popup-menu kwargs. Built lazily so the ``ui_font`` call
    runs after Tk root exists (it reads ``TkDefaultFont``)."""
    return dict(
        bg="#2d2d30", fg="#cccccc",
        activebackground="#094771", activeforeground="#ffffff",
        bd=0, borderwidth=0, relief="flat",
        font=ui_font(10),
    )


# Style bool rows that contribute to the "Style" subgroup preview.
# The preview renders compact single-letter initials; the individual
# row labels (Bold / Italic / ...) come from the widget schema.
STYLE_BOOL_NAMES = {
    "font_bold": "B",
    "font_italic": "I",
    "font_underline": "U",
    "font_overstrike": "S",
}
