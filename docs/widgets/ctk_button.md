# CTkButton

A clickable button widget with rich styling: rounded corners, hover and
pressed states, an optional border, text + icon composition, and full
text formatting (font family inherited from CTk, size, bold, italic,
auto-fit, alignment, normal/disabled text color).

Wraps [`customtkinter.CTkButton`](https://customtkinter.tomschimansky.com/documentation/widgets/button).

**Descriptor:** [`app/widgets/ctk_button.py`](../../app/widgets/ctk_button.py)
**Type name:** `CTkButton`
**Display name:** `Button`

---

## Properties panel layout

The builder's Properties panel renders a CTkButton with six collapsible
groups, in this top-to-bottom order:

| Group | Subgroup | Rows |
|---|---|---|
| **Geometry** | — | Position, Size |
| **Rectangle** | Corners | Roundness |
| **Rectangle** | Border | Thickness, Color |
| **State** | — | Disabled |
| **Main Colors** | — | Background, Hover |
| **Text** | — | Label (multiline) |
| **Text** | Style | Size + Best Fit, Style (Bold + Italic), Decoration (Underline + Strike) |
| **Text** | Alignment | Align |
| **Text** | Color | Normal, Disabled |
| **Image & Alignment** | — | Image, Size (W + H), Position |

---

## Geometry

Top-left origin is `(0, 0)`; `x`/`y` is the widget's top-left corner in
canvas coordinates. `width`/`height` is the button's requested size; the
actual rendered size may be larger when the text or `corner_radius`
forces CTk to grow the widget (see the Rectangle → Corners notes below).

| Row | Property | Type | Default | Min | Max |
|---|---|---|---|---|---|
| Position | `x` | int | 120 | — | — |
| Position | `y` | int | 120 | — | — |
| Size | `width` | int | 140 | 20 | 2000 |
| Size | `height` | int | 32 | 20 | 2000 |

All four are draggable (Photoshop-style horizontal scrub) via the small
`X` / `Y` / `W` / `H` sub-labels.

---

## Rectangle

### Corners

| Row | Property | Type | Default | Min | Max |
|---|---|---|---|---|---|
| Roundness | `corner_radius` | int | 6 | 0 | `min(width, height) // 2` |

**Note:** CTkButton's minimum width/height grows with `corner_radius`
(approximately `text_width + 2 * corner_radius + padding`). A button
configured as `100×100` with `corner_radius=50` will actually render at
around `223×135` because CTk won't let the rounded corners eat into the
text area. To get a true circular button, use either very short text
or match the width to the calculation above. See also the
`CTk corner_radius limitation` note in [TODO.md](../../TODO.md).

### Border

| Row | Property | Type | Default |
|---|---|---|---|
| Thickness | `border_width` | int | 0 |
| Color | `border_color` | hex | `#565b5e` |

Color is disabled when thickness is `0`.

---

## State

| Row | Property | Type | Default |
|---|---|---|---|
| Disabled | `state_disabled` | bool | False |

When checked, the descriptor passes `state="disabled"` to CTkButton,
making the button grayed out and unclickable.

---

## Main Colors

| Row | Property | Type | Default |
|---|---|---|---|
| Background | `fg_color` | hex | `#1f6aa5` |
| Hover | `hover_color` | hex | `#144870` |

In CTk, the "pressed" visual state uses the same color as `hover_color`;
there is no separate pressed color. The disabled background is computed
automatically by CTk and cannot be overridden (only the disabled text
color is user-settable — see Text → Color).

**Gradient** backgrounds are not supported (CTk limitation). See
[TODO.md](../../TODO.md) Phase 8 for the exploration plan.

---

## Text

### Label (multiline)

| Row | Property | Type | Default |
|---|---|---|---|
| Label | `text` | multiline string | `"CTkButton"` |

The label is rendered as a full-width textbox without a row header, so
multi-line values work naturally. Leave empty to draw an icon-only
button (combine with an Image below).

### Style

| Row | Property | Type | Default | Notes |
|---|---|---|---|---|
| Size | `font_size` | int | 13 | 6–96. Disabled while Best Fit is on. |
| Best Fit | `font_autofit` | bool | False | Binary-searches the largest size that fits `width × height`. |
| Style › Bold | `font_bold` | bool | False | |
| Style › Italic | `font_italic` | bool | False | |
| Decoration › Underline | `font_underline` | bool | False | |
| Decoration › Strike | `font_overstrike` | bool | False | Maps to CTkFont `overstrike`. |

Descriptor builds a single
`CTkFont(size=..., weight=..., slant=..., underline=..., overstrike=...)`
and passes it to `CTkButton(font=...)`. Best Fit runs automatically on
any change to `text`, `width`, `height`, `font_bold`, or `font_autofit`.

### Alignment

| Row | Property | Type | Default | Values |
|---|---|---|---|---|
| Align | `anchor` | enum | `center` | `nw`, `n`, `ne`, `w`, `center`, `e`, `sw`, `s`, `se` |

Rendered as a dropdown with human-readable labels ("Top Left", "Top
Center", …). The underlying value is the tkinter anchor code.

### Color

| Row | Property | Type | Default |
|---|---|---|---|
| Normal | `text_color` | hex | `#ffffff` |
| Disabled | `text_color_disabled` | hex | `#a0a0a0` |

Normal is used in the `state="normal"` state; Disabled is used when
`state_disabled` is on.

---

## Image & Alignment

| Row | Property | Type | Default | Notes |
|---|---|---|---|---|
| Image | `image` | file path | None | Any image PIL can open. |
| Size (W) | `image_width` | int | 20 | 4–512, disabled when no image |
| Size (H) | `image_height` | int | 20 | 4–512, disabled when no image |
| Position | `compound` | enum | `left` | Image position relative to text: `top`, `left`, `right`, `bottom`. Disabled when no image. |

The descriptor loads the image path through PIL and wraps it in a
`CTkImage(light_image=..., dark_image=..., size=(W, H))`, then passes
the CTkImage to `CTkButton(image=..., compound=...)`. For an icon-only
button, clear the Label text and keep only the image.

---

## Exported Python example

A CTkButton configured with all defaults produces code equivalent to:

```python
import customtkinter as ctk

button = ctk.CTkButton(
    master,
    width=140,
    height=32,
    corner_radius=6,
    border_width=0,
    border_color="#565b5e",
    fg_color="#1f6aa5",
    hover_color="#144870",
    text="CTkButton",
    font=ctk.CTkFont(size=13, weight="normal", slant="roman",
                     underline=False, overstrike=False),
    anchor="center",
    text_color="#ffffff",
    text_color_disabled="#a0a0a0",
    compound="left",
    state="normal",
)
button.place(x=120, y=120)
```

The builder places the widget with `.place(x=x, y=y)` by default; layout
manager support (`pack`/`grid`/`place`) is planned for Phase 6.

---

## Node-only properties (not passed to CTkButton)

These live in the builder's `node.properties` dict but are transformed
away before reaching CTkButton's constructor:

| Property | Used to compute |
|---|---|
| `x`, `y` | Canvas `create_window` position |
| `image_width`, `image_height` | `CTkImage` `size=(w, h)` |
| `state_disabled` | `state="disabled"` or `"normal"` |
| `font_size`, `font_bold`, `font_italic`, `font_underline`, `font_overstrike`, `font_autofit` | `CTkFont(size, weight, slant, underline, overstrike)` |

See [`CTkButtonDescriptor.transform_properties`](../../app/widgets/ctk_button.py)
for the exact translation logic.

---

## Limitations

- **Gradient fill** — not supported by CTkButton. Planned exploration in
  Phase 8; see [TODO.md](../../TODO.md).
- **Separate pressed color** — CTk reuses `hover_color` for press. No
  schema option.
- **Custom pressed animation** — not exposed. CTk handles this internally.
- **corner_radius ≥ min(width, height)/2** — CTk grows the widget beyond
  its requested size. Preview = reality: the exported code reproduces
  the same behavior.
