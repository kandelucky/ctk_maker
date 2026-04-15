# CTkFrame

A plain rounded container with optional border. The simplest CTk widget — no text, no state, no interaction. Acts as a parent for nested widgets.

Wraps [`customtkinter.CTkFrame`](https://customtkinter.tomschimansky.com/documentation/widgets/frame).
**Descriptor:** [`../../app/widgets/ctk_frame.py`](../../app/widgets/ctk_frame.py)

`is_container = True` — the workspace accepts drops into it so nested trees are built by dragging widgets inside.

## Geometry

| Row | Property | Default | Range |
|---|---|---|---|
| Position X / Y | `x` / `y` | 120 / 120 | — |
| Size W / H | `width` / `height` | 200 / 150 | 20–4000 |

## Rectangle

| Row | Property | Default | Notes |
|---|---|---|---|
| Corner Radius | `corner_radius` | 6 | Max = `min(w, h) // 2` |
| Border › Enabled | `border_enabled` | False | Master toggle for the border |
| Border › Thickness | `border_width` | 1 | Disabled when Enabled is off |
| Border › Color | `border_color` | `#565b5e` | Disabled when Enabled is off |

## Main Colors

| Row | Property | Default |
|---|---|---|
| Background | `fg_color` | `#2b2b2b` |

Set `fg_color` to `transparent` to let the parent's colour show through.
