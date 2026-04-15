# CTkTextbox

A multi-line text editor — CTkEntry's big brother. Inherits from
`tkinter.Text` so `.insert(index, text)` / `.delete(start, end)` /
`.get(start, end)` follow the Text widget's `"line.col"` index
conventions.

Wraps [`customtkinter.CTkTextbox`](https://customtkinter.tomschimansky.com/documentation/widgets/textbox).
**Descriptor:** [`../../app/widgets/ctk_textbox.py`](../../app/widgets/ctk_textbox.py)

## Geometry

| Row | Property | Default | Range |
|---|---|---|---|
| Position X / Y | `x` / `y` | 120 / 120 | — |
| Size W / H | `width` / `height` | 200 / 200 | 50–4000 / 30–4000 |

## Rectangle

| Row | Property | Default | Notes |
|---|---|---|---|
| Corner Radius | `corner_radius` | 6 | Max = `min(w, h) // 2` |
| Border › Enabled | `border_enabled` | False | Master toggle |
| Border › Thickness | `border_width` | 1 | Disabled when Enabled is off |
| Border › Color | `border_color` | `#565b5e` | Disabled when Enabled is off |
| Inner Padding | `border_spacing` | 3 | Gap between the text and the inner edge |

## Content

| Row | Property | Default | Notes |
|---|---|---|---|
| Initial Text | `initial_text` | `""` | Multiline editor in the panel. `apply_state` runs `delete("1.0","end")` + `insert("1.0", text)` so edits sync live into the builder canvas; `export_state` mirrors that with an `insert("1.0", …)` call in the exported file |
| Show Scrollbars | `activate_scrollbars` | True | **Init-only** — changing this destroys and recreates the widget because CTkTextbox raises `ValueError` on `configure(activate_scrollbars=…)` |

## Button Interaction

| Row | Property | Default | Notes |
|---|---|---|---|
| Interactable | `button_enabled` | True | Off → `configure(state="disabled")`. CTkTextbox doesn't take `state` in `__init__`, so `apply_state` applies it after construction. The exporter emits a `{var}.configure(state="disabled")` line when Interactable is off |

## Main Colors

| Row | Property | Default |
|---|---|---|
| Background | `fg_color` | `#1d1e1e` |
| Scrollbar | `scrollbar_button_color` | `#696969` |
| Scrollbar Hover | `scrollbar_button_hover_color` | `#878787` |

## Text

| Row | Property | Default | Notes |
|---|---|---|---|
| Size | `font_size` | 13 | 6–96 |
| Style › Bold / Italic / Underline / Strike | `font_bold` / `font_italic` / `font_underline` / `font_overstrike` | False | |
| Normal Text Color | `text_color` | `#dce4ee` | |
