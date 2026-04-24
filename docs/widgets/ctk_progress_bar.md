# CTkProgressBar

A decorative bar showing fractional progress between 0% and 100%. Static preview — the builder treats it as a snapshot of the progress value, not as an animated indicator.

Wraps [`customtkinter.CTkProgressBar`](https://customtkinter.tomschimansky.com/documentation/widgets/progressbar).
**Descriptor:** [`../../app/widgets/ctk_progress_bar.py`](../../app/widgets/ctk_progress_bar.py)

## Geometry

| Row | Property | Default | Range |
|---|---|---|---|
| Position X / Y | `x` / `y` | 120 / 120 | — |
| Size W / H | `width` / `height` | 200 / 16 | 10–2000 / 4–2000 |

Flipping orientation automatically swaps width and height (`on_prop_recreate` hook) so a 200×16 horizontal bar becomes a 16×200 vertical bar.

## Rectangle

| Row | Property | Default | Notes |
|---|---|---|---|
| Corner Radius | `corner_radius` | 8 | 0–50 |
| Border › Enabled | `border_enabled` | False | Master toggle |
| Border › Thickness | `border_width` | 2 | 1–20 |
| Border › Color | `border_color` | `#7a7a7a` | Disabled when Enabled is off |

## Progress

| Row | Property | Default | Notes |
|---|---|---|---|
| Orientation | `orientation` | `horizontal` | `horizontal` / `vertical`. Init-only — workspace destroys + recreates the widget on change. |
| Progress % | `initial_percent` | 50 | 0–100 integer. `apply_state` divides by 100 and calls `widget.set(...)`. |

## Main Colors

| Row | Property | Default |
|---|---|---|
| Track Background | `fg_color` | `#4a4d50` |
| Progress Fill | `progress_color` | `#6366f1` |

The builder hardcodes `mode="determinate"` so what you see in the editor matches the exported widget exactly.
