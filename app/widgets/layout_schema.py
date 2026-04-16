"""Shared layout schema for tk geometry managers.

A container widget (Frame, Window, ScrollableFrame, …) carries a
``layout_type`` property — one of ``place`` / ``pack`` / ``grid``.
All children of that container are emitted by the code exporter
through the matching geometry manager, and the Properties panel
shows the matching child-layout rows on every selected child.

The properties panel reads ``LAYOUT_TYPE_ROW`` directly when it
builds a container's schema, and calls ``child_layout_schema``
for every selected child to inject the parent-driven rows.
"""

from __future__ import annotations

LAYOUT_TYPES = ("place", "pack", "grid")
DEFAULT_LAYOUT_TYPE = "place"

# Container row — append to a container's property_schema.
LAYOUT_TYPE_ROW = {
    "name": "layout_type",
    "type": "layout_type",
    "label": "",
    "group": "Layout",
    "row_label": "Manager",
}

# Defaults merged into every child node so save / undo / export all
# see consistent values regardless of which manager is active.
LAYOUT_DEFAULTS: dict = {
    "pack_side": "top",
    "pack_fill": "none",
    "pack_expand": False,
    "pack_padx": 0,
    "pack_pady": 0,
    "grid_row": 0,
    "grid_column": 0,
    "grid_rowspan": 1,
    "grid_columnspan": 1,
    "grid_sticky": "",
    "grid_padx": 0,
    "grid_pady": 0,
}

# Keys the workspace must strip from CTk constructor / configure
# kwargs — they're stored on the node only for export and the panel.
LAYOUT_NODE_ONLY_KEYS = frozenset(LAYOUT_DEFAULTS.keys()) | {"layout_type"}

PACK_SIDE_OPTIONS = ("top", "bottom", "left", "right")
PACK_FILL_OPTIONS = ("none", "x", "y", "both")
GRID_STICKY_OPTIONS = (
    "", "n", "s", "e", "w",
    "ns", "ew", "ne", "nw", "se", "sw",
    "nsew",
)
LAYOUT_TYPE_OPTIONS = LAYOUT_TYPES


_PACK_ROWS: list[dict] = [
    {"name": "pack_side", "type": "pack_side", "label": "",
     "group": "Layout", "row_label": "Side"},
    {"name": "pack_fill", "type": "pack_fill", "label": "",
     "group": "Layout", "row_label": "Fill"},
    {"name": "pack_expand", "type": "boolean", "label": "",
     "group": "Layout", "row_label": "Expand"},
    {"name": "pack_padx", "type": "number", "label": "X",
     "group": "Layout", "pair": "pack_pad", "row_label": "Padding",
     "min": 0, "max": 200},
    {"name": "pack_pady", "type": "number", "label": "Y",
     "group": "Layout", "pair": "pack_pad", "min": 0, "max": 200},
]

_GRID_ROWS: list[dict] = [
    {"name": "grid_row", "type": "number", "label": "R",
     "group": "Layout", "pair": "grid_cell", "row_label": "Cell",
     "min": 0, "max": 99},
    {"name": "grid_column", "type": "number", "label": "C",
     "group": "Layout", "pair": "grid_cell", "min": 0, "max": 99},
    {"name": "grid_rowspan", "type": "number", "label": "R",
     "group": "Layout", "pair": "grid_span", "row_label": "Span",
     "min": 1, "max": 99},
    {"name": "grid_columnspan", "type": "number", "label": "C",
     "group": "Layout", "pair": "grid_span", "min": 1, "max": 99},
    {"name": "grid_sticky", "type": "grid_sticky", "label": "",
     "group": "Layout", "row_label": "Sticky"},
    {"name": "grid_padx", "type": "number", "label": "X",
     "group": "Layout", "pair": "grid_pad", "row_label": "Padding",
     "min": 0, "max": 200},
    {"name": "grid_pady", "type": "number", "label": "Y",
     "group": "Layout", "pair": "grid_pad", "min": 0, "max": 200},
]


def child_layout_schema(parent_layout_type: str) -> list[dict]:
    """Schema rows the Properties panel injects for the selected
    child, based on its parent's layout manager. ``place`` adds no
    rows because the existing Geometry group already covers x/y/w/h.
    """
    if parent_layout_type == "pack":
        return _PACK_ROWS
    if parent_layout_type == "grid":
        return _GRID_ROWS
    return []


def normalise_layout_type(value) -> str:
    if value in LAYOUT_TYPES:
        return value
    return DEFAULT_LAYOUT_TYPE
