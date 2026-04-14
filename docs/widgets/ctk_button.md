# CTkButton

A clickable button with rounded corners, hover/pressed states, optional
border, text + icon composition, and full text formatting.

Wraps [`customtkinter.CTkButton`](https://customtkinter.tomschimansky.com/documentation/widgets/button).
**Descriptor:** [`../../app/widgets/ctk_button.py`](../../app/widgets/ctk_button.py)

## Geometry

| Row | Property | Default | Range |
|---|---|---|---|
| Position X / Y | `x` / `y` | 120 / 120 | — |
| Size W / H | `width` / `height` | 140 / 32 | 20–2000 |

## Rectangle

| Row | Property | Default | Notes |
|---|---|---|---|
| Corners › Roundness | `corner_radius` | 6 | Max = `min(w, h) // 2` |
| Border › Thickness | `border_width` | 0 | |
| Border › Color | `border_color` | `#565b5e` | Disabled when thickness is 0 |

## State

| Row | Property | Default |
|---|---|---|
| Disabled | `state_disabled` | False |

## Main Colors

| Row | Property | Default |
|---|---|---|
| Background | `fg_color` | `#1f6aa5` |
| Hover | `hover_color` | `#144870` |

CTk reuses `hover_color` for the pressed state.

## Text

**Label** — `text` (multiline), default `"CTkButton"`. Leave empty for an
icon-only button.

### Style

| Row | Property | Default | Notes |
|---|---|---|---|
| Size | `font_size` | 13 | 6–96 |
| Best Fit | `font_autofit` | False | Auto-sizes to fit `w × h` |
| Bold / Italic | `font_bold` / `font_italic` | False | |
| Underline / Strike | `font_underline` / `font_overstrike` | False | |

### Alignment

| Row | Property | Default | Values |
|---|---|---|---|
| Align | `anchor` | `center` | `nw`, `n`, `ne`, `w`, `center`, `e`, `sw`, `s`, `se` |

### Color

| Row | Property | Default |
|---|---|---|
| Normal | `text_color` | `#ffffff` |
| Disabled | `text_color_disabled` | `#a0a0a0` |

## Image & Alignment

| Row | Property | Default | Notes |
|---|---|---|---|
| Image | `image` | None | Any image PIL can open |
| Color → Normal | `image_color` | None | Icon tint. None = original colors |
| Color → Disabled | `image_color_disabled` | None | Tint when `state_disabled` is on; falls back to Normal |
| Alignment → Size W / H | `image_width` / `image_height` | 20 / 20 | 4–512 |
| Alignment → Position | `compound` | `left` | `top`, `left`, `right`, `bottom` |
| Alignment → Preserve Aspect | `preserve_aspect` | False | When on, H is derived from W × native aspect |

The Color swatches replace the image's RGB via PIL while preserving
alpha — best suited for monochrome icons (e.g. Lucide).
