# CTkCheckBox

A labelled checkbox. The checkbox square and the label sit side by side.

Wraps [`customtkinter.CTkCheckBox`](https://customtkinter.tomschimansky.com/documentation/widgets/checkbox).
**Descriptor:** [`../../app/widgets/ctk_check_box.py`](../../app/widgets/ctk_check_box.py)

## Geometry

| Row | Property | Default | Range |
|---|---|---|---|
| Position X / Y | `x` / `y` | 120 / 120 | — |
| Size W / H | `width` / `height` | 100 / 24 | 20–2000 / 10–2000 |

## Rectangle

| Row | Property | Default | Notes |
|---|---|---|---|
| Corner Radius | `corner_radius` | 6 | Max = `min(box_w, box_h) // 2` |
| Border › Enabled | `border_enabled` | True | Master toggle |
| Border › Thickness | `border_width` | 3 | Clamped to half the checkbox square |
| Border › Color | `border_color` | `#949A9F` | Disabled when Enabled is off |

## Checkbox

| Row | Property | Default | Range |
|---|---|---|---|
| Box Size W / H | `checkbox_width` / `checkbox_height` | 24 / 24 | 10–200 |

The inner clickable square is sized separately from the row itself — `width`/`height` above cover the whole widget (square + label), `checkbox_width`/`checkbox_height` are the square alone.

## Button Interaction

| Row | Property | Default | Notes |
|---|---|---|---|
| Interactable | `button_enabled` | True | Off → CTk `state="disabled"` |
| Hover Effect | `hover` | True | |
| Initially Checked | `initially_checked` | False | `apply_state` calls `.select()` / `.deselect()` |

## Main Colors

| Row | Property | Default |
|---|---|---|
| Fill (Checked) | `fg_color` | `#1f6aa5` |
| Hover | `hover_color` | `#144870` |
| Check Mark | `checkmark_color` | `#e5e5e5` |

## Text

| Row | Property | Default | Notes |
|---|---|---|---|
| Label | `text` | `CTkCheckBox` | Multiline editor, one-line preview |
| Size | `font_size` | 13 | 6–96 |
| Style › Bold/Italic/Underline/Strike | `font_bold` / `font_italic` / `font_underline` / `font_overstrike` | False | |
| Normal Text Color | `text_color` | `#dce4ee` | |
| Disabled Text Color | `text_color_disabled` | `#737373` | |
