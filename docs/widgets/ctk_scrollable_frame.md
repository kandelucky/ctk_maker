# CTkScrollableFrame

A scrollable container with an optional header label. Acts as a parent for nested widgets when the content grows taller (or wider) than the visible area.

Wraps [`customtkinter.CTkScrollableFrame`](https://customtkinter.tomschimansky.com/documentation/widgets/scrollable_frame).
**Descriptor:** [`../../app/widgets/ctk_scrollable_frame.py`](../../app/widgets/ctk_scrollable_frame.py)

> **Status: partial.** The descriptor, schema, and registry entry are in place and the widget renders with every colour and label property working. Nesting children through the builder's `place()` path still clashes with CTk's internal grid/pack-based scrollregion tracking, so dropping widgets inside a scrollable frame is not fully reliable yet. Tracked under Phase 6.8 in [TODO.md](../../TODO.md).

`is_container = True` — the workspace accepts drops into it.

## Geometry

| Row | Property | Default | Range |
|---|---|---|---|
| Position X / Y | `x` / `y` | 120 / 120 | — |
| Size W / H | `width` / `height` | 200 / 200 | 50–4000 |

## Rectangle

| Row | Property | Default | Notes |
|---|---|---|---|
| Corner Radius | `corner_radius` | 6 | Max = `min(w, h) // 2` |
| Border › Enabled / Thickness / Color | `border_enabled` / `border_width` / `border_color` | False / 1 / `#565b5e` | |

## Label

Optional header strip across the top of the frame.

| Row | Property | Default | Notes |
|---|---|---|---|
| Label Text | `label_text` | `""` | Empty hides the header entirely |
| Label Alignment | `label_text_align` | `center` | `left` / `center` / `right` — maps to CTk `label_anchor` (`w` / `center` / `e`) |
| Label Background | `label_fg_color` | `#3a3a3a` | |
| Label Text Color | `label_text_color` | `#dce4ee` | |

## Scrollbar

| Row | Property | Default | Notes |
|---|---|---|---|
| Orientation | `orientation` | `vertical` | `vertical` / `horizontal`. Init-only — workspace destroys + recreates on change. |
| Scrollbar Background | `scrollbar_fg_color` | `#1a1a1a` | |
| Scrollbar Button | `scrollbar_button_color` | `#3a3a3a` | |
| Scrollbar Button Hover | `scrollbar_button_hover_color` | `#4a4a4a` | |

## Main Colors

| Row | Property | Default |
|---|---|---|
| Background | `fg_color` | `#2b2b2b` |
