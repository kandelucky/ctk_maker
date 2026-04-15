# CTkOptionMenu

A dropdown picker: the main button shows the current value, clicking it opens a native menu to pick from a fixed list of strings. Unlike CTkComboBox, the user cannot type a custom value.

Wraps [`customtkinter.CTkOptionMenu`](https://customtkinter.tomschimansky.com/documentation/widgets/optionmenu).
**Descriptor:** [`../../app/widgets/ctk_option_menu.py`](../../app/widgets/ctk_option_menu.py)

## Geometry

| Row | Property | Default | Range |
|---|---|---|---|
| Position X / Y | `x` / `y` | 120 / 120 | — |
| Size W / H | `width` / `height` | 140 / 28 | 40–2000 / 20–2000 |

## Rectangle

| Row | Property | Default | Notes |
|---|---|---|---|
| Corner Radius | `corner_radius` | 6 | Max = `min(w, h) // 2`. CTkOptionMenu has no border. |

## Values

| Row | Property | Default | Notes |
|---|---|---|---|
| Values | `values` | `Option 1 / Option 2 / Option 3` | One option per line. Exporter converts to list literal via `multiline_list_keys`. |
| Initial Value | `initial_value` | `Option 1` | Pre-selected entry. |

## Button Interaction

| Row | Property | Default |
|---|---|---|
| Interactable | `button_enabled` | True |
| Hover Effect | `hover` | True |

## Main Colors

| Row | Property | Default |
|---|---|---|
| Background | `fg_color` | `#1f6aa5` |
| Arrow Button | `button_color` | `#144870` |
| Arrow Hover | `button_hover_color` | `#203a4f` |

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
| Text Align | `text_align` | `left` | `left` / `center` / `right`. Builder converts to CTk `anchor` (`w` / `center` / `e`). |
| Normal Text Color | `text_color` | `#dce4ee` | |
| Disabled Text Color | `text_color_disabled` | `#737373` | |

The builder hardcodes `dynamic_resizing=False` so the widget honours the width you set instead of growing to fit the longest value.
