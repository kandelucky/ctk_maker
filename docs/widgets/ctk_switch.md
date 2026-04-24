# CTkSwitch

A toggle switch — conceptually a checkbox, visually an iOS-style
slider with a moving knob.

Wraps [`customtkinter.CTkSwitch`](https://customtkinter.tomschimansky.com/documentation/widgets/switch).
**Descriptor:** [`../../app/widgets/ctk_switch.py`](../../app/widgets/ctk_switch.py)

## Geometry

| Row | Property | Default | Range |
|---|---|---|---|
| Position X / Y | `x` / `y` | 120 / 120 | — |
| Size W / H | `width` / `height` | 100 / 24 | 20–2000 / 10–2000 |

## Rectangle

| Row | Property | Default | Notes |
|---|---|---|---|
| Corner Radius | `corner_radius` | 1000 | Fully rounded; max clamped to half the switch box |
| Button Length | `button_length` | 0 | 0 = circular knob. Values > 0 stretch the knob into a pill |

## Switch

The inner toggle box — sized separately from the whole row so the
label has room beside it.

| Row | Property | Default | Range |
|---|---|---|---|
| Switch Size W / H | `switch_width` / `switch_height` | 36 / 18 | 10–200 / 8–200 |

## Button Interaction

| Row | Property | Default | Notes |
|---|---|---|---|
| Interactable | `button_enabled` | True | Off → CTk `state="disabled"` |
| Hover Effect | `hover` | True | Knob hover colour fades in |
| Initially On | `initially_checked` | False | `apply_state` calls `.select()` / `.deselect()`; `export_state` emits the same on the exported file |

## Main Colors

| Row | Property | Default |
|---|---|---|
| Track (Off) | `fg_color` | `#4a4d50` |
| Track (On) | `progress_color` | `#6366f1` |
| Knob | `button_color` | `#d5d9de` |
| Knob Hover | `button_hover_color` | `#ffffff` |

Knob Hover is disabled in the Properties panel when Hover Effect is off.

## Text

| Row | Property | Default | Notes |
|---|---|---|---|
| Label | `text` | `CTkSwitch` | Multiline editor, one-line preview |
| Size | `font_size` | 13 | 6–96 |
| Style › Bold / Italic / Underline / Strike | `font_bold` / `font_italic` / `font_underline` / `font_overstrike` | False | |
| Normal Text Color | `text_color` | `#dce4ee` | |
| Disabled Text Color | `text_color_disabled` | `#737373` | |
