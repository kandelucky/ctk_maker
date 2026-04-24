# CTkRadioButton

A labelled radio button. Multiple radios that share a group name form a set where only one can be selected at a time.

Wraps [`customtkinter.CTkRadioButton`](https://customtkinter.tomschimansky.com/documentation/widgets/radiobutton).
**Descriptor:** [`../../app/widgets/ctk_radio_button.py`](../../app/widgets/ctk_radio_button.py)

## Geometry

| Row | Property | Default | Range |
|---|---|---|---|
| Position X / Y | `x` / `y` | 120 / 120 | — |
| Size W / H | `width` / `height` | 100 / 22 | 20–2000 / 10–2000 |

## Rectangle

| Row | Property | Default | Notes |
|---|---|---|---|
| Corner Radius | `corner_radius` | 11 | Max = `min(box_w, box_h) // 2` |
| Border › Unchecked Width | `border_width_unchecked` | 3 | Thickness when the radio is not selected |
| Border › Checked Width | `border_width_checked` | 6 | Thickness when selected (creates the "filled dot" effect) |
| Border › Color | `border_color` | `#949A9F` | Used for both checked and unchecked border |

## Radio Button

| Row | Property | Default | Range |
|---|---|---|---|
| Box Size W / H | `radiobutton_width` / `radiobutton_height` | 22 / 22 | 10–200 |

The inner circle is sized separately from the row. `width`/`height` above cover the whole widget (circle + label), `radiobutton_width`/`radiobutton_height` are the circle alone.

## Button Interaction

| Row | Property | Default | Notes |
|---|---|---|---|
| Interactable | `button_enabled` | True | Off → CTk `state="disabled"` |
| Hover Effect | `hover` | True | |
| Initially Checked | `initially_checked` | False | Only one radio per group can start checked; the workspace enforces this. |
| Group | `group` | `""` | Group name. Radios with the same group share a `tk.StringVar` so only one is selected at a time. Leave empty for a standalone radio (rare). |

Group coordination is handled by the workspace: radios with a shared name get a common variable and each one's `value` defaults to its widget name. Changing the group re-creates the widget (`recreate_triggers = {"group"}`).

## Main Colors

| Row | Property | Default |
|---|---|---|
| Fill (Checked) | `fg_color` | `#6366f1` |
| Hover | `hover_color` | `#4f46e5` |

## Text

| Row | Property | Default | Notes |
|---|---|---|---|
| Label | `text` | `CTkRadioButton` | Multiline editor, one-line preview |
| Size | `font_size` | 13 | 6–96 |
| Style › Bold/Italic/Underline/Strike | `font_*` | False | |
| Normal Text Color | `text_color` | `#dce4ee` | |
| Disabled Text Color | `text_color_disabled` | `#737373` | |
