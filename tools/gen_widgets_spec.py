"""Generate docs/spec/WIDGETS.md from app/widgets/ descriptors.

Run:    python tools/gen_widgets_spec.py
Writes: docs/spec/WIDGETS.md (overwritten in place)

Produces a markdown reference of every registered widget's properties,
types, defaults, ranges, and group placement. Lambdas in schema entries
(e.g. dynamic max bounds) are rendered as "<dynamic>" — non-lambda
values land verbatim.

Hand-written sections (manual nuances) live between
<!-- BEGIN MANUAL --> and <!-- END MANUAL --> blocks. The generator
preserves them across regeneration so authors can add limitations
or examples without losing them on the next run.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Make the project importable without installing.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ui.palette import CATALOG  # noqa: E402
from app.widgets.registry import get_descriptor  # noqa: E402

OUT = ROOT / "docs" / "spec" / "WIDGETS.md"

MANUAL_BEGIN = "<!-- BEGIN MANUAL -->"
MANUAL_END = "<!-- END MANUAL -->"


def _format_value(v) -> str:
    if v is None:
        return "`None`"
    if isinstance(v, bool):
        return "`True`" if v else "`False`"
    if callable(v):
        return "_dynamic_"
    if isinstance(v, str):
        return f"`\"{v}\"`"
    if isinstance(v, (int, float)):
        return f"`{v}`"
    if isinstance(v, (list, tuple)):
        if not v:
            return "`[]`"
        items = ", ".join(_format_value(x) for x in v)
        return f"[{items}]"
    return f"`{v!r}`"


def _format_default(default_properties: dict, name: str) -> str:
    if name not in default_properties:
        return ""
    return _format_value(default_properties[name])


def _format_range(prop: dict) -> str:
    bits = []
    for key in ("min", "max", "step"):
        if key in prop:
            bits.append(f"{key}={_format_value(prop[key])}")
    return ", ".join(bits)


def _format_values(prop: dict) -> str:
    if "values" in prop:
        return _format_value(prop["values"])
    return ""


def _conditional(prop: dict) -> str:
    bits = []
    if "disabled_when" in prop:
        bits.append(f"disabled when {prop['disabled_when']}")
    if "hidden_when" in prop:
        bits.append(f"hidden when {prop['hidden_when']}")
    if prop.get("recreate_triggers"):
        bits.append("**recreates on change**")
    return "; ".join(bits)


def _format_palette_entry(entry, descriptor) -> list[str]:
    """Render one palette entry. ``entry`` is a ``WidgetEntry`` from
    ``app/ui/palette.py:CATALOG``. ``descriptor`` is the resolved
    ``WidgetDescriptor`` class (looked up from ``entry.type_name``).
    """
    d = descriptor
    lines: list[str] = []
    lines.append(f"## {entry.display_name} (`{entry.type_name}`)")
    lines.append("")

    meta_rows = []
    if d.ctk_class_name and d.ctk_class_name != entry.type_name:
        meta_rows.append(f"| CTk class | `{d.ctk_class_name}` |")
    if not getattr(d, "is_ctk_class", True):
        meta_rows.append(
            "| Generated as | inline class (not from `customtkinter`) |"
        )
    if getattr(d, "is_container", False):
        meta_rows.append("| Container | yes — can hold children |")
    if getattr(d, "prefers_fill_in_layout", False):
        meta_rows.append(
            "| Layout default | fills parent (vbox/hbox/grid) |"
        )
    if getattr(d, "multiline_list_keys", set()):
        keys = ", ".join(f"`{k}`" for k in sorted(d.multiline_list_keys))
        meta_rows.append(
            f"| Multiline-list keys | {keys} |"
        )
    if getattr(d, "init_only_keys", set()):
        keys = ", ".join(f"`{k}`" for k in sorted(d.init_only_keys))
        meta_rows.append(f"| Init-only keys | {keys} |")
    if not getattr(d, "image_inline_kwarg", True):
        meta_rows.append(
            "| Image kwarg | manual (descriptor builds image separately) |"
        )
    if entry.preset_overrides:
        # Multiple palette entries can share one descriptor (e.g. all
        # three layout entries on top of CTkFrame). Surface the
        # specific overrides this entry applies on top of the
        # descriptor defaults.
        bits = ", ".join(
            f"`{k}={_format_value(v)}`" for k, v in entry.preset_overrides
        )
        meta_rows.append(f"| Palette preset | {bits} |")
    if entry.default_name:
        meta_rows.append(f"| Default name slug | `{entry.default_name}` |")

    if meta_rows:
        lines.append("| Attribute | Value |")
        lines.append("|---|---|")
        lines.extend(meta_rows)
        lines.append("")

    schema = list(getattr(d, "property_schema", []) or [])
    defaults = dict(getattr(d, "default_properties", {}) or {})
    # Merge palette-entry preset overrides on top of descriptor defaults
    # so the documented default reflects what the user actually sees
    # when dragging this palette item.
    for key, value in entry.preset_overrides:
        defaults[key] = value

    if not schema:
        lines.append("_No property schema._")
        lines.append("")
        return lines

    # Group schema rows by `group` then `subgroup` while preserving
    # original ordering.
    groups: dict[str, list[dict]] = {}
    group_order: list[str] = []
    for prop in schema:
        g = prop.get("group", "Other")
        if g not in groups:
            groups[g] = []
            group_order.append(g)
        groups[g].append(prop)

    for group in group_order:
        rows = groups[group]
        lines.append(f"### {group}")
        lines.append("")
        lines.append(
            "| Property | Type | Label | Default | "
            "Range / Values | Notes |",
        )
        lines.append("|---|---|---|---|---|---|")
        for prop in rows:
            name = prop.get("name", "")
            ptype = prop.get("type", "")
            label = prop.get("label") or prop.get("row_label") or ""
            default = _format_default(defaults, name)
            rng = _format_range(prop)
            vals = _format_values(prop)
            range_or_values = rng or vals
            notes = _conditional(prop)
            lines.append(
                f"| `{name}` | {ptype} | {label} | "
                f"{default} | {range_or_values} | {notes} |",
            )
        lines.append("")

    # Hand-written nuances section (preserved across regenerations).
    lines.append(MANUAL_BEGIN)
    lines.append(f"### Notes — {entry.display_name}")
    lines.append("")
    lines.append("_(none yet)_")
    lines.append("")
    lines.append(MANUAL_END)
    lines.append("")

    return lines


def _preserve_manual_blocks(new_text: str, old_text: str) -> str:
    """Carry forward the body of every BEGIN MANUAL / END MANUAL block
    from ``old_text`` into ``new_text`` based on section heading.
    """
    if not old_text:
        return new_text
    pattern = re.compile(
        re.escape(MANUAL_BEGIN) + r"(.*?)" + re.escape(MANUAL_END),
        re.DOTALL,
    )
    old_blocks = pattern.findall(old_text)
    new_blocks = pattern.findall(new_text)
    if len(old_blocks) != len(new_blocks):
        # Section count drift — skip migration so the user notices and
        # merges manually.
        return new_text
    out = new_text
    for old_block, new_block in zip(old_blocks, new_blocks, strict=False):
        old_full = MANUAL_BEGIN + old_block + MANUAL_END
        new_full = MANUAL_BEGIN + new_block + MANUAL_END
        out = out.replace(new_full, old_full, 1)
    return out


def main() -> None:
    # Resolve every palette entry to its descriptor up front so we can
    # surface missing-descriptor errors loudly instead of producing a
    # half-empty spec.
    resolved = []
    for group in CATALOG:
        for entry in group.items:
            descriptor = get_descriptor(entry.type_name)
            if descriptor is None:
                raise RuntimeError(
                    f"Palette entry {entry.display_name!r} references "
                    f"unknown descriptor type {entry.type_name!r}",
                )
            resolved.append((group, entry, descriptor))

    total = len(resolved)
    group_titles = [g.title for g in CATALOG]

    lines: list[str] = []
    lines.append("# CTkMaker — Widget Reference")
    lines.append("")
    lines.append(
        f"Auto-generated from `app/ui/palette.py:CATALOG` "
        f"(palette grouping + presets) plus `app/widgets/*.py` "
        f"descriptors (schema + defaults). "
        f"**{total} palette entries across "
        f"{len(group_titles)} groups.** "
        f"Run `python tools/gen_widgets_spec.py` to regenerate. "
        f"Hand-written notes between `<!-- BEGIN MANUAL -->` / "
        f"`<!-- END MANUAL -->` blocks are preserved across "
        f"regenerations.",
    )
    lines.append("")
    lines.append(
        "For the descriptor system itself see "
        "[EXTENSION.md](EXTENSION.md). "
        "For user-facing concepts see [CONCEPTS.md](CONCEPTS.md). "
        "Some palette entries (e.g. Vertical Layout, Horizontal "
        "Layout, Grid Layout) share one underlying descriptor with "
        "different preset overrides — the **Palette preset** row "
        "lists those.",
    )
    lines.append("")

    # Summary — grouped by palette category, mirrors palette UI.
    lines.append("## Summary")
    lines.append("")
    for group in CATALOG:
        lines.append(f"### {group.title}")
        lines.append("")
        lines.append("| Widget | Descriptor | Container | Notes |")
        lines.append("|---|---|---|---|")
        for entry in group.items:
            d = get_descriptor(entry.type_name)
            notes_bits: list[str] = []
            if entry.preset_overrides:
                notes_bits.append("palette-preset")
            if not getattr(d, "is_ctk_class", True):
                notes_bits.append("inlined class")
            if getattr(d, "prefers_fill_in_layout", False):
                notes_bits.append("layout-fills")
            if getattr(d, "multiline_list_keys", set()):
                notes_bits.append("multiline-list")
            notes = ", ".join(notes_bits)
            lines.append(
                f"| {entry.display_name} | `{entry.type_name}` | "
                f"{'✓' if getattr(d, 'is_container', False) else ''} | "
                f"{notes} |",
            )
        lines.append("")

    # Per-entry detail sections, also grouped.
    for group in CATALOG:
        lines.append(f"# {group.title}")
        lines.append("")
        for entry in group.items:
            descriptor = get_descriptor(entry.type_name)
            lines.extend(_format_palette_entry(entry, descriptor))

    new_text = "\n".join(lines).rstrip() + "\n"

    # Preserve manual blocks if the file already exists.
    old_text = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    final = _preserve_manual_blocks(new_text, old_text)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(final, encoding="utf-8")
    print(f"Wrote {OUT}")
    print(
        f"  {total} palette entries across "
        f"{len(group_titles)} groups documented",
    )


if __name__ == "__main__":
    main()
