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
| Corner Radius | `corner_radius` | 6 | Max = `min(w, h) // 2` |
| Border › Enabled | `border_enabled` | False | Master toggle for the border |
| Border › Thickness | `border_width` | 1 | Disabled when Enabled is off |
| Border › Color | `border_color` | `#565b5e` | Disabled when Enabled is off |

The Border subgroup preview shows **active** / **not active** based on
the Enabled toggle.

## Button Interaction

| Row | Property | Default | Notes |
|---|---|---|---|
| Interactable | `button_enabled` | True | Off → CTk `state="disabled"` |

## Main Colors

| Row | Property | Default |
|---|---|---|
| Background | `fg_color` | `#1f6aa5` |
| Hover | `hover_color` | `#144870` |

CTk reuses `hover_color` for the pressed state.

## Text

**Label** — `text` (multiline), default `"CTkButton"`. Click the pencil
icon to open the full multi-line editor. Leave empty for an icon-only
button.

### Size

| Row | Property | Default | Notes |
|---|---|---|---|
| Size | `font_size` | 13 | 6–96; disabled while Best Fit is on |
| Best Fit | `font_autofit` | False | Auto-sizes to fit `w × h` |

### Style

| Row | Property | Default |
|---|---|---|
| Bold | `font_bold` | False |
| Italic | `font_italic` | False |
| Underline | `font_underline` | False |
| Strike | `font_overstrike` | False |

The Style subgroup header shows a compact preview: **B I U S** with
active styles highlighted.

### Alignment

| Row | Property | Default | Values |
|---|---|---|---|
| Alignment | `anchor` | `center` | `nw`, `n`, `ne`, `w`, `center`, `e`, `sw`, `s`, `se` |

### Color

| Row | Property | Default |
|---|---|---|
| Normal Text Color | `text_color` | `#ffffff` |
| Disabled Text Color | `text_color_disabled` | `#a0a0a0` |

## Image & Alignment

| Row | Property | Default | Notes |
|---|---|---|---|
| Image | `image` | None | Click ⋯ to pick a file, ✕ to clear. Any format PIL can open |
| Normal Color | `image_color` | None | Icon tint. None = original colors |
| Disabled Color | `image_color_disabled` | None | Tint while `button_enabled` is off; falls back to Normal |
| Icon Size W / H | `image_width` / `image_height` | 20 / 20 | 4–512; H disabled when Preserve Aspect is on |
| Icon Side | `compound` | `left` | `top`, `left`, `right`, `bottom` |
| Preserve Aspect | `preserve_aspect` | False | When on, H is derived from W × native aspect |

The Normal / Disabled color swatches replace the image's RGB via PIL
while preserving alpha — best suited for monochrome icons (e.g. Lucide).
