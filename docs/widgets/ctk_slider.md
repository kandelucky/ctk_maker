# CTkSlider

A draggable value picker over a numeric range. Supports continuous and stepped modes plus horizontal / vertical orientation.

Wraps [`customtkinter.CTkSlider`](https://customtkinter.tomschimansky.com/documentation/widgets/slider).
**Descriptor:** [`../../app/widgets/ctk_slider.py`](../../app/widgets/ctk_slider.py)

Unlike CTkProgressBar, CTkSlider accepts `orientation` via `configure(...)` so flipping it does not require a destroy + recreate dance.

## Geometry

| Row | Property | Default | Range |
|---|---|---|---|
| Position X / Y | `x` / `y` | 120 / 120 | — |
| Size W / H | `width` / `height` | 200 / 16 | 20–2000 / 8–2000 |

## Rectangle

| Row | Property | Default | Notes |
|---|---|---|---|
| Track Radius | `corner_radius` | 8 | 0–50 |
| Button Radius | `button_corner_radius` | 8 | 0–50 |
| Button Length | `button_length` | 0 | Pill-shaped handle when > 0; capped at `width // 2` |
| Border › Enabled | `border_enabled` | False | Master toggle |
| Border › Thickness | `border_width` | 6 | 1–20 |
| Border › Color | `border_color` | `#565b5e` | Disabled when Enabled is off |

## Value Range

| Row | Property | Default | Notes |
|---|---|---|---|
| Min | `from_` | 0 | The exported code uses the trailing underscore to avoid the Python keyword. |
| Max | `to` | 100 | |
| Steps | `number_of_steps` | 0 | 0 = continuous; N > 0 = quantised to N+1 positions |
| Initial Value | `initial_value` | 50 | `apply_state` calls `widget.set(value)` |

## Orientation

| Row | Property | Default | Notes |
|---|---|---|---|
| Orientation | `orientation` | `horizontal` | `horizontal` / `vertical`. `on_prop_recreate` swaps `width`↔`height` when flipped. |

## Button Interaction

| Row | Property | Default |
|---|---|---|
| Interactable | `button_enabled` | True |
| Hover Effect | `hover` | True |

## Main Colors

| Row | Property | Default |
|---|---|---|
| Track Background | `fg_color` | `#4a4d50` |
| Progress Fill | `progress_color` | `#aab0b5` |
| Button | `button_color` | `#1f6aa5` |
| Button Hover | `button_hover_color` | `#144870` |
