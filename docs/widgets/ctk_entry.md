# CTkEntry

A single-line text input with an optional placeholder hint.

Wraps [`customtkinter.CTkEntry`](https://customtkinter.tomschimansky.com/documentation/widgets/entry).
**Descriptor:** [`../../app/widgets/ctk_entry.py`](../../app/widgets/ctk_entry.py)

## Geometry

| Row | Property | Default | Range |
|---|---|---|---|
| Position X / Y | `x` / `y` | 120 / 120 | — |
| Size W / H | `width` / `height` | 140 / 28 | 40–2000 / 20–2000 |

## Rectangle

| Row | Property | Default | Notes |
|---|---|---|---|
| Corner Radius | `corner_radius` | 6 | Max = `min(w, h) // 2` |
| Border › Enabled | `border_enabled` | True | Master toggle |
| Border › Thickness | `border_width` | 2 | Disabled when Enabled is off |
| Border › Color | `border_color` | `#565b5e` | Disabled when Enabled is off |

## Content

| Row | Property | Default | Notes |
|---|---|---|---|
| Placeholder | `placeholder_text` | `Enter text…` | Grey hint shown while the field is empty |
| Initial Text | `initial_value` | `""` | Value inserted at widget creation |

Both fields open a multi-line editor so long strings or line breaks are manageable; the widget itself still renders on a single line.

## Button Interaction

| Row | Property | Default | Notes |
|---|---|---|---|
| Interactable | `button_enabled` | True | Off → CTk `state="disabled"` (placeholder stays visible) |

## Main Colors

| Row | Property | Default |
|---|---|---|
| Field Background | `fg_color` | `#343638` |

## Text

| Row | Property | Default | Notes |
|---|---|---|---|
| Size | `font_size` | 13 | 6–96 |
| Style › Bold | `font_bold` | False | |
| Style › Italic | `font_italic` | False | |
| Style › Underline | `font_underline` | False | |
| Style › Strike | `font_overstrike` | False | |
| Normal Text Color | `text_color` | `#dce4ee` | |
| Placeholder Color | `placeholder_text_color` | `#9ea0a2` | |
