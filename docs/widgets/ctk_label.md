# CTkLabel

A non-interactive text label with font styling, anchor/justify alignment,
optional wrap, and separate enabled/disabled text colors.

Wraps [`customtkinter.CTkLabel`](https://customtkinter.tomschimansky.com/documentation/widgets/label).
**Descriptor:** [`../../app/widgets/ctk_label.py`](../../app/widgets/ctk_label.py)

## Geometry

| Row | Property | Default | Range |
|---|---|---|---|
| Position X / Y | `x` / `y` | 120 / 120 | — |
| Size W / H | `width` / `height` | 100 / 28 | 20–2000 / 10–2000 |

## Text

**Label** — `text` (multiline), default `"CTkLabel"`. Click the pencil
icon to open the full multi-line editor.

### Size

| Row | Property | Default | Notes |
|---|---|---|---|
| Size | `font_size` | 13 | 6–96; disabled while Best Fit is on |
| Best Fit | `font_autofit` | False | Derives `font_size` from `w × h × text` |

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
| Anchor | `anchor` | `center` | `nw`, `n`, `ne`, `w`, `center`, `e`, `sw`, `s`, `se` |
| Line Align | `justify` | `center` | `left`, `center`, `right` |

**Anchor** places the entire text block inside the label widget.
**Line Align** controls how individual lines align *within* the text
block — only visible on multi-line text.

### Wrap

| Row | Property | Default | Notes |
|---|---|---|---|
| Enabled | `font_wrap` | True | Master toggle for wrapping |
| Length | `wraplength` | 0 | 0–2000 px; disabled when Enabled is off; 0 = no wrap |

### Color

| Row | Property | Default |
|---|---|---|
| Normal Text Color | `text_color` | `#ffffff` |
| Disabled Text Color | `text_color_disabled` | `#a0a0a0` |

## Tips

- For icon-only labels, clear `text` and the widget renders just its
  background.
- Use **Best Fit** when the label sits inside a resizable container —
  font size adapts automatically.
- **Line Align** has no visible effect on single-line text; set a
  `wraplength` or add `\n` in the text to see it work.
