# CTkSegmentedButton

A row of mutually-exclusive buttons — a Mac-style segmented control or a tab bar. One segment is always highlighted as "selected".

Wraps [`customtkinter.CTkSegmentedButton`](https://customtkinter.tomschimansky.com/documentation/widgets/segmented_button).
**Descriptor:** [`../../app/widgets/ctk_segmented_button.py`](../../app/widgets/ctk_segmented_button.py)

## Geometry

| Row | Property | Default | Range |
|---|---|---|---|
| Position X / Y | `x` / `y` | 120 / 120 | — |
| Size W / H | `width` / `height` | 240 / 32 | 60–2000 / 20–2000 |

## Rectangle

| Row | Property | Default | Notes |
|---|---|---|---|
| Corner Radius | `corner_radius` | 6 | Max = `min(w, h) // 2` |
| Border › Enabled | `border_enabled` | False | Master toggle |
| Border › Thickness | `border_width` | 2 | 1–20 |

## Values

| Row | Property | Default | Notes |
|---|---|---|---|
| Values | `values` | `First / Second / Third` | One segment per line in the multiline editor. Exporter converts to list literal via `multiline_list_keys`. |
| Initial Value | `initial_value` | `First` | Segment pre-selected at widget creation. |

## Button Interaction

| Row | Property | Default | Notes |
|---|---|---|---|
| Interactable | `button_enabled` | True | Off → CTk `state="disabled"` |

## Main Colors

| Row | Property | Default |
|---|---|---|
| Outer Background | `fg_color` | `#4a4d50` |
| Selected | `selected_color` | `#1f6aa5` |
| Selected Hover | `selected_hover_color` | `#144870` |
| Unselected | `unselected_color` | `#4a4d50` |
| Unselected Hover | `unselected_hover_color` | `#696969` |

## Text

| Row | Property | Default | Notes |
|---|---|---|---|
| Size | `font_size` | 13 | 6–96 |
| Style › Bold/Italic/Underline/Strike | `font_*` | False | |
| Normal Text Color | `text_color` | `#dce4ee` | |
| Disabled Text Color | `text_color_disabled` | `#737373` | |
