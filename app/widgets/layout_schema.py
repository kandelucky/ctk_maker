"""Shared layout schema for tk geometry managers.

A container widget (Frame, Window, ScrollableFrame, …) carries a
``layout_type`` property — one of ``place`` / ``vbox`` / ``hbox`` /
``grid``. All children of that container are emitted by the code
exporter through the matching geometry manager, and the Properties
panel shows the matching child-layout rows on every selected child.

Qt Designer split QBoxLayout into QVBoxLayout + QHBoxLayout for a
reason — 95% of real layouts pick one direction and stick with it,
and a per-child ``pack_side`` row created more confusion than
flexibility. We mirror that split: ``vbox`` hardcodes ``side="top"``
and ``hbox`` hardcodes ``side="left"`` at export time.

The properties panel reads ``LAYOUT_TYPE_ROW`` directly when it
builds a container's schema, and calls ``child_layout_schema``
for every selected child to inject the parent-driven rows.
"""

from __future__ import annotations

LAYOUT_TYPES = ("place", "vbox", "hbox", "grid")
DEFAULT_LAYOUT_TYPE = "place"

# User-facing labels + internal keys. Internal keys stay short
# (``vbox`` / ``hbox``) so they serialise compactly and match tk/Qt
# convention; display labels read like English so the Properties
# popup and tooltips are self-explanatory.
LAYOUT_DISPLAY_NAMES: dict[str, str] = {
    "place": "Absolute",
    "vbox": "Vertical",
    "hbox": "Horizontal",
    "grid": "Grid",
}

# Lucide icon names (relative to the builder's icon loader). Used by
# the Properties panel enum popup, Object Tree container suffix, and
# the canvas container badge.
LAYOUT_ICON_NAMES: dict[str, str] = {
    "place": "crosshair",
    "vbox": "rows-3",
    "hbox": "columns-3",
    "grid": "grid-3x3",
}

# tk side= value each container emits for its children. ``grid`` /
# ``place`` don't use pack, so they have no entry.
_VBOX_SIDE = "top"
_HBOX_SIDE = "left"

# Container rows — append to a container's property_schema. The
# Manager row is always visible; ``Spacing`` is only meaningful for
# vbox/hbox/grid layouts, so the panel's ``disabled_when`` grey-
# scales it under the default ``place`` mode (where pack/grid aren't
# in use). The two rows are intentionally split — callers may skip
# the spacing row on a container that has no space-aware layout
# (e.g. Tabview, whose layout is internal).
LAYOUT_TYPE_ROW = {
    "name": "layout_type",
    "type": "layout_type",
    "label": "",
    "group": "Layout",
    "row_label": "Manager",
}
LAYOUT_SPACING_ROW = {
    "name": "layout_spacing",
    "type": "number",
    "label": "",
    "group": "Layout",
    "row_label": "Spacing",
    "min": 0,
    "max": 200,
    "disabled_when": lambda p: normalise_layout_type(
        p.get("layout_type", "place"),
    ) == "place",
}
# Grid-only dimensions — rows × columns. Hidden outside grid mode
# so the Inspector doesn't clutter vbox / hbox / place users with
# fields that don't apply.
_GRID_ROWS_HIDDEN = lambda p: normalise_layout_type(  # noqa: E731
    p.get("layout_type", "place"),
) != "grid"
LAYOUT_GRID_ROWS_ROW = {
    "name": "grid_rows",
    "type": "number",
    "label": "R",
    "group": "Layout",
    "pair": "grid_dims",
    "row_label": "Dimensions",
    "min": 1,
    "max": 50,
    "hidden_when": _GRID_ROWS_HIDDEN,
}
LAYOUT_GRID_COLS_ROW = {
    "name": "grid_cols",
    "type": "number",
    "label": "C",
    "group": "Layout",
    "pair": "grid_dims",
    "min": 1,
    "max": 50,
    "hidden_when": _GRID_ROWS_HIDDEN,
}
CONTAINER_LAYOUT_ROWS: list[dict] = [
    LAYOUT_TYPE_ROW, LAYOUT_SPACING_ROW,
    LAYOUT_GRID_ROWS_ROW, LAYOUT_GRID_COLS_ROW,
]

# Defaults merged into every child node so save / undo / export all
# see consistent values regardless of which manager is active. Per-
# child layout tuning is deliberately thin — pack children have a
# single ``stretch`` hint, grid children have a single ``grid_sticky``
# hint (cell fill direction). Cell assignment for grid is derived
# from the child's index in ``parent.children`` + the parent's
# ``grid_cols`` — there is no per-child row/column on the model.
LAYOUT_DEFAULTS: dict = {
    # fixed = natural size, fill = stretch across-axis,
    # grow = take extra space + fill both.
    "stretch": "fixed",
    # Explicit grid cell per child — (row, column) in the parent
    # grid. Defaults to (0, 0); fresh drops auto-assign to the next
    # free cell so the user doesn't have to edit Inspector for a
    # normal fill-top-to-bottom flow.
    "grid_row": 0,
    "grid_column": 0,
    # Cell fill — empty = natural-size centered, "nsew" = fill.
    "grid_sticky": "",
}

# Defaults merged onto a container node itself. ``layout_spacing``
# controls the gap between siblings for pack (vbox/hbox) + grid.
# ``grid_rows`` / ``grid_cols`` are only meaningful when
# ``layout_type == "grid"`` — they carve the container into that
# many cells even if no child occupies the trailing rows/cols.
LAYOUT_CONTAINER_DEFAULTS: dict = {
    "layout_spacing": 4,
    "grid_rows": 2,
    "grid_cols": 2,
}

# Keys the workspace must strip from CTk constructor / configure
# kwargs — they're stored on the node only for export and the panel.
# ``pack_side`` / ``pack_fill`` / ``pack_expand`` / ``pack_padx`` /
# ``pack_pady`` stay in the strip list because legacy v0.0.10 — v0.0.11
# projects may still carry them; the migration layer rewrites them to
# ``stretch`` but the workspace must not hand a stale copy to CTk if
# one survives. Same deal for the v0.0.12 per-child grid_row / column
# / span / padding keys the v0.0.13 auto-flow rewrite dropped.
LAYOUT_NODE_ONLY_KEYS = frozenset(LAYOUT_DEFAULTS.keys()) | {
    "layout_type", "layout_spacing",
    "grid_rows", "grid_cols",
    "pack_side", "pack_fill", "pack_expand",
    "pack_padx", "pack_pady",
    "grid_rowspan", "grid_columnspan",
    "grid_padx", "grid_pady",
}

GRID_STICKY_OPTIONS = (
    "", "n", "s", "e", "w",
    "ns", "ew", "ne", "nw", "se", "sw",
    "nsew",
)
STRETCH_OPTIONS = ("fixed", "fill", "grow")
STRETCH_TO_INT: dict[str, int] = {"fixed": 0, "fill": 1, "grow": 2}
STRETCH_INT_TO_LABEL: dict[int, str] = {0: "fixed", 1: "fill", 2: "grow"}
LAYOUT_TYPE_OPTIONS = LAYOUT_TYPES


_PACK_ROWS: list[dict] = [
    {"name": "stretch", "type": "stretch", "label": "",
     "group": "Layout", "row_label": "Stretch"},
]

_GRID_ROWS: list[dict] = [
    {"name": "grid_row", "type": "number", "label": "R",
     "group": "Layout", "pair": "grid_cell", "row_label": "Cell",
     "min": 0, "max": 99},
    {"name": "grid_column", "type": "number", "label": "C",
     "group": "Layout", "pair": "grid_cell", "min": 0, "max": 99},
    {"name": "grid_sticky", "type": "grid_sticky", "label": "",
     "group": "Layout", "row_label": "Fill"},
]


def child_layout_schema(parent_layout_type: str) -> list[dict]:
    """Schema rows the Properties panel injects for the selected
    child, based on its parent's layout manager. ``place`` adds no
    rows because the existing Geometry group already covers x/y/w/h;
    ``vbox`` and ``hbox`` share the same pack rows (direction lives
    on the parent, not the child).
    """
    if parent_layout_type in ("vbox", "hbox"):
        return _PACK_ROWS
    if parent_layout_type == "grid":
        return _GRID_ROWS
    return []


def normalise_layout_type(value) -> str:
    """Coerce an unknown / legacy ``layout_type`` to something the
    exporter + panel know how to handle. v0.0.10 shipped ``pack``;
    we migrate it to ``vbox`` (pack's default side was ``top``).
    """
    if value == "pack":
        return "vbox"
    if value in LAYOUT_TYPES:
        return value
    return DEFAULT_LAYOUT_TYPE


MANAGED_LAYOUT_TYPES = ("vbox", "hbox", "grid")


def is_layout_container(properties: dict) -> bool:
    """True when the widget's own ``layout_type`` is one of the
    managed layouts (``vbox`` / ``hbox`` / ``grid``). Used to block
    layout-in-layout nesting at drop time — Qt Designer allows it
    but our rendering of nested grids on canvas is fragile (see
    backlog) so we disallow it until it's worth the engineering.
    """
    return normalise_layout_type(
        properties.get("layout_type", "place"),
    ) in MANAGED_LAYOUT_TYPES


def pack_side_for(parent_layout_type: str) -> str | None:
    """Hardcoded ``side=`` value emitted for each pack-family parent.
    Returns ``None`` for non-pack parents so the exporter can skip
    the call entirely.
    """
    if parent_layout_type == "vbox":
        return _VBOX_SIDE
    if parent_layout_type == "hbox":
        return _HBOX_SIDE
    return None


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def grid_effective_dims(
    child_count: int, container_props: dict | None = None,
) -> tuple[int, int]:
    """Effective grid dimensions. The user's ``grid_rows`` /
    ``grid_cols`` are authoritative — no auto-growth for capacity.
    The ``child_count`` argument is kept in the signature for API
    stability / future use.
    """
    _ = child_count
    if container_props is None:
        container_props = {}
    cols = max(1, _safe_int(container_props.get("grid_cols", 1), 1))
    rows = max(1, _safe_int(container_props.get("grid_rows", 1), 1))
    return rows, cols


def next_free_grid_cell(
    siblings, container_props: dict | None = None,
) -> tuple[int, int]:
    """Scan the container's grid row-major and return the first
    (row, col) no sibling occupies. Used at widget-add time to
    auto-place a fresh child without asking the user to pick a
    cell. Wraps around (reuses ``(0, 0)``) once every cell in the
    declared ``grid_rows × grid_cols`` is taken.
    """
    if container_props is None:
        container_props = {}
    rows, cols = grid_effective_dims(len(siblings), container_props)
    occupied: set[tuple[int, int]] = set()
    for sibling in siblings:
        try:
            r = int(sibling.properties.get("grid_row", 0) or 0)
            c = int(sibling.properties.get("grid_column", 0) or 0)
        except (TypeError, ValueError):
            continue
        occupied.add((r, c))
    for r in range(rows):
        for c in range(cols):
            if (r, c) not in occupied:
                return r, c
    return 0, 0
