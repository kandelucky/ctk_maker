# CTkComboBox

An editable text field with a dropdown of predefined values. The user can pick from the list or type a custom value.

Wraps [`customtkinter.CTkComboBox`](https://customtkinter.tomschimansky.com/documentation/widgets/combobox).
**Descriptor:** [`../../app/widgets/ctk_combo_box.py`](../../app/widgets/ctk_combo_box.py)

## Geometry

| Row | Property | Default | Range |
|---|---|---|---|
| Position X / Y | `x` / `y` | 120 / 120 | — |
| Size W / H | `width` / `height` | 140 / 28 | 40–2000 / 20–2000 |

## Rectangle

| Row | Property | Default | Notes |
|---|---|---|---|
| Corner Radius | `corner_radius` | 6 | Max = `min(w, h) // 2` |
| Border › Enabled / Thickness / Color | `border_enabled` / `border_width` / `border_color` | True / 2 / `#565b5e` | |

## Values

| Row | Property | Default | Notes |
|---|---|---|---|
| Values | `values` | `Option 1 / Option 2 / Option 3` | One option per line in the multiline editor. Exporter converts to a Python list literal via `multiline_list_keys`. |
| Initial Value | `initial_value` | `Option 1` | Shown in the field at widget creation. |

## Button Interaction

| Row | Property | Default | Notes |
|---|---|---|---|
| Interactable | `button_enabled` | True | Off → CTk `state="disabled"` |
| Hover Effect | `hover` | True | |

## Main Colors

| Row | Property | Default |
|---|---|---|
| Field Background | `fg_color` | `#343638` |
| Arrow Button | `button_color` | `#565b5e` |
| Arrow Hover | `button_hover_color` | `#7a848d` |

## Dropdown Colors

| Row | Property | Default |
|---|---|---|
| Background | `dropdown_fg_color` | `#2b2b2b` |
| Hover | `dropdown_hover_color` | `#3a3a3a` |
| Text | `dropdown_text_color` | `#dce4ee` |

## Text

| Row | Property | Default | Notes |
|---|---|---|---|
| Size | `font_size` | 13 | 6–96 |
| Style › Bold/Italic/Underline/Strike | `font_*` | False | |
| Text Align | `justify` | `left` | `left` / `center` / `right` |
| Normal Text Color | `text_color` | `#dce4ee` | |
| Disabled Text Color | `text_color_disabled` | `#737373` | |
