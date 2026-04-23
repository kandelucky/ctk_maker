"""Pure formatting and coercion helpers for the Properties panel v2.

These functions depend only on the schema dict and current property
values — no references to `self`, the Treeview, or any Tk state.
Kept in a separate module so the panel module stays focused on
Tkinter glue and per-row overlay management.
"""

from __future__ import annotations

from app.widgets.layout_schema import (
    GRID_STICKY_OPTIONS,
    LAYOUT_DISPLAY_NAMES,
    LAYOUT_TYPE_OPTIONS,
    STRETCH_OPTIONS,
)

from .constants import (
    ANCHOR_CODE_TO_LABEL,
    ANCHOR_DROPDOWN_ORDER,
    COMPOUND_OPTIONS,
    JUSTIFY_OPTIONS,
    ORIENTATION_OPTIONS,
    TEXT_POSITION_OPTIONS,
    WRAP_OPTIONS,
)

GRID_STYLE_OPTIONS = ("none", "dots", "lines")
LAYOUT_ENUM_TYPES = frozenset({
    "layout_type", "stretch", "grid_sticky",
})


def format_value(ptype: str, value, prop: dict) -> str:
    """Render a schema value as the string shown in the tree cell."""
    if ptype == "color":
        # Leading spaces reserve room for the swatch overlay.
        # "transparent" is CTk's sentinel for "no fill" — the builder
        # doesn't truly render transparency (CTk fakes it with the
        # parent's fg_color), so surface the clearer label "none" to
        # the user while keeping the stored value compatible.
        if not value:
            return ""
        display = "none" if str(value) == "transparent" else str(value)
        return f"              {display}"
    if ptype == "boolean":
        return "☑" if value else "☐"
    if ptype == "anchor":
        return ANCHOR_CODE_TO_LABEL.get(str(value), str(value or ""))
    if ptype in ("compound", "justify", "orientation", "grid_style"):
        return str(value) if value is not None else ""
    if ptype == "layout_type":
        # layout_type stores the internal key (``place`` / ``vbox`` /
        # …); show the friendly Qt-style label in the tree cell.
        return LAYOUT_DISPLAY_NAMES.get(str(value), str(value or "—"))
    if ptype in LAYOUT_ENUM_TYPES:
        return str(value) if value not in (None, "") else "—"
    if ptype in ("multiline", "image", "segment_values"):
        # Shown via overlay label / button, not the tree cell.
        return ""
    if ptype == "segment_initial":
        # Render the picked segment text in the cell; the dropdown
        # popup is the actual editor.
        return str(value) if value not in (None, "") else "—"
    if value is None:
        return ""
    return str(value)


def format_numeric_pair_preview(items: list[dict], properties: dict) -> str:
    parts = []
    for item in items:
        label = item.get("label") or item["name"].upper()[:1]
        val = properties.get(item["name"])
        parts.append(f"{label} {val}")
    return "  ".join(parts)


def compute_subgroup_preview(
    descriptor, group: str, subgroup: str, properties: dict,
) -> str:
    """Preview string shown next to a subgroup header row.

    - Rectangle › Corners → the `corner_radius` value.
    - Rectangle › Border → "active" / "not active" based on
      `border_enabled`.
    - Everything else → empty.
    """
    name = subgroup.lower()
    if name == "corners":
        for p in descriptor.property_schema:
            if p.get("group") == group and \
                    p.get("subgroup") == subgroup and \
                    p["name"] == "corner_radius":
                return str(properties.get("corner_radius", ""))
    if name == "border":
        return (
            "active"
            if properties.get("border_enabled")
            else "not active"
        )
    return ""


def enum_options_for(ptype: str):
    if ptype == "anchor":
        return ANCHOR_DROPDOWN_ORDER
    if ptype == "compound":
        return COMPOUND_OPTIONS
    if ptype == "justify":
        return JUSTIFY_OPTIONS
    if ptype == "orientation":
        return ORIENTATION_OPTIONS
    if ptype == "wrap":
        return WRAP_OPTIONS
    if ptype == "text_position":
        return TEXT_POSITION_OPTIONS
    if ptype == "grid_style":
        return GRID_STYLE_OPTIONS
    if ptype == "layout_type":
        return LAYOUT_TYPE_OPTIONS
    if ptype == "stretch":
        return STRETCH_OPTIONS
    if ptype == "grid_sticky":
        return GRID_STICKY_OPTIONS
    return []


def coerce_value(ptype: str | None, raw: str):
    if ptype == "number":
        try:
            return int(raw)
        except ValueError:
            try:
                return float(raw)
            except ValueError:
                return None
    return raw
