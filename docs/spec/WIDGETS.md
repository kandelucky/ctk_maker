# CTkMaker — Widget Reference

Auto-generated from `app/ui/palette.py:CATALOG` (palette grouping + presets) plus `app/widgets/*.py` descriptors (schema + defaults). **21 palette entries across 5 groups.** Run `python tools/gen_widgets_spec.py` to regenerate. Hand-written notes between `<!-- BEGIN MANUAL -->` / `<!-- END MANUAL -->` blocks are preserved across regenerations.

For the descriptor system itself see [EXTENSION.md](EXTENSION.md). For user-facing concepts see [CONCEPTS.md](CONCEPTS.md). Some palette entries (e.g. Vertical Layout, Horizontal Layout, Grid Layout) share one underlying descriptor with different preset overrides — the **Palette preset** row lists those.

## Summary

### Display

| Widget | Descriptor | Container | Notes |
|---|---|---|---|
| Label | `CTkLabel` |  | layout-fills |
| Image | `Image` |  | layout-fills |
| Card | `Card` |  | layout-fills |

### Controls

| Widget | Descriptor | Container | Notes |
|---|---|---|---|
| Button | `CTkButton` |  | inlined class, layout-fills |
| Entry | `CTkEntry` |  | layout-fills |
| Textbox | `CTkTextbox` |  | layout-fills |
| Check Box | `CTkCheckBox` |  |  |
| Switch | `CTkSwitch` |  |  |
| Radio Button | `CTkRadioButton` |  |  |
| Segmented Button | `CTkSegmentedButton` |  | layout-fills, multiline-list |
| Combo Box | `CTkComboBox` |  | multiline-list |
| Option Menu | `CTkOptionMenu` |  | multiline-list |
| Slider | `CTkSlider` |  | layout-fills |

### Containers

| Widget | Descriptor | Container | Notes |
|---|---|---|---|
| Frame | `CTkFrame` | ✓ | layout-fills |
| Scrollable Frame | `CTkScrollableFrame` | ✓ | layout-fills |
| Tab View | `CTkTabview` | ✓ | layout-fills |

### Layouts

| Widget | Descriptor | Container | Notes |
|---|---|---|---|
| Vertical Layout | `CTkFrame` | ✓ | palette-preset, layout-fills |
| Horizontal Layout | `CTkFrame` | ✓ | palette-preset, layout-fills |
| Grid Layout | `CTkFrame` | ✓ | palette-preset, layout-fills |

### Indicators

| Widget | Descriptor | Container | Notes |
|---|---|---|---|
| Progress Bar | `CTkProgressBar` |  | layout-fills |
| Circular Progress | `CircularProgress` |  | inlined class |

# Display

## Label (`CTkLabel`)

| Attribute | Value |
|---|---|
| Layout default | fills parent (vbox/hbox/grid) |

### Text

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `text` | multiline | Label | `"CTkLabel"` |  |  |
| `font_family` | font | Font | `None` |  |  |
| `font_size` | number | Size | `13` | min=`6`, max=`96` | disabled when <function CTkLabelDescriptor.<lambda> at 0x000001FFC405F110> |
| `font_autofit` | boolean | Auto Fit | `False` |  |  |
| `font_bold` | boolean | Bold | `False` |  |  |
| `font_italic` | boolean | Italic | `False` |  |  |
| `font_underline` | boolean | Underline | `False` |  |  |
| `font_overstrike` | boolean | Strike | `False` |  |  |
| `justify` | justify | Line Align | `"center"` |  |  |
| `font_wrap` | boolean | Enabled | `True` |  |  |
| `wraplength` | number | Length | `0` | min=`0`, max=`2000` | disabled when <function CTkLabelDescriptor.<lambda> at 0x000001FFC405F1C0> |
| `text_color` | color | Normal Text Color | `"#ffffff"` |  |  |
| `text_color_disabled` | color | Disabled Text Color | `"#a0a0a0"` |  |  |

### Icon

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `image` | image | Icon | `None` |  |  |
| `image_color` | color | Normal Color | `None` |  | disabled when <function CTkLabelDescriptor.<lambda> at 0x000001FFC405F270> |
| `image_color_disabled` | color | Disabled Color | `None` |  | disabled when <function CTkLabelDescriptor.<lambda> at 0x000001FFC405F320> |
| `image_width` | number | W | `20` | min=`4`, max=`512` | disabled when <function CTkLabelDescriptor.<lambda> at 0x000001FFC405F3D0> |
| `image_height` | number | H | `20` | min=`4`, max=`512` | disabled when <function CTkLabelDescriptor.<lambda> at 0x000001FFC405F480> |
| `compound` | compound | Icon Side | `"left"` |  | disabled when <function CTkLabelDescriptor.<lambda> at 0x000001FFC405F530> |
| `preserve_aspect` | boolean | Preserve Aspect | `False` |  | disabled when <function CTkLabelDescriptor.<lambda> at 0x000001FFC405F5E0> |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `100` | min=`20`, max=`2000` |  |
| `height` | number | H | `28` | min=`10`, max=`2000` |  |

### Alignment

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `anchor` | anchor | Anchor | `"center"` |  |  |
| `padx` | number | X | `0` | min=`0`, max=`50` |  |
| `pady` | number | Y | `0` | min=`0`, max=`50` |  |

### Rectangle

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `corner_radius` | number | Corner Radius | `0` | min=`0`, max=_dynamic_ |  |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Foreground | `"transparent"` |  |  |
| `bg_color` | color | Background | `"transparent"` |  |  |

### Interaction

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `label_enabled` | boolean | Enabled | `True` |  |  |
| `cursor` | cursor | Cursor | `""` |  |  |
| `takefocus` | boolean | Take Focus | `False` |  |  |

<!-- BEGIN MANUAL -->
### Notes — Radio Button

_(none yet)_

<!-- END MANUAL -->

## Image (`Image`)

| Attribute | Value |
|---|---|
| CTk class | `CTkLabel` |
| Layout default | fills parent (vbox/hbox/grid) |

### Image

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `image` | image | Image | `"C:\Users\likak\Desktop\ctk_maker\app\assets\defaults\image.png"` |  |  |
| `preserve_aspect` | boolean | Preserve Aspect | `True` |  | disabled when <function ImageDescriptor.<lambda> at 0x000001FFC40B5010> |

### Tint

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `image_color` | color | Normal Color | `None` |  | disabled when <function ImageDescriptor.<lambda> at 0x000001FFC40B50C0> |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `128` | min=`4`, max=`4000` |  |
| `height` | number | H | `128` | min=`4`, max=`4000` | disabled when <function ImageDescriptor.<lambda> at 0x000001FFC40B5170> |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Background | `"transparent"` |  |  |

<!-- BEGIN MANUAL -->
### Notes — Switch

_(none yet)_

<!-- END MANUAL -->

## Card (`Card`)

| Attribute | Value |
|---|---|
| CTk class | `CTkFrame` |
| Layout default | fills parent (vbox/hbox/grid) |
| Image kwarg | manual (descriptor builds image separately) |

### Image

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `image` | image | File | `None` |  |  |
| `image_color` | color | Tint | `None` |  | disabled when <function CardDescriptor.<lambda> at 0x000001FFC409E350> |
| `image_anchor` | anchor | Alignment | `"center"` |  | disabled when <function CardDescriptor.<lambda> at 0x000001FFC409E400> |
| `image_width` | number | W | `48` | min=`4`, max=`4000` | disabled when <function CardDescriptor.<lambda> at 0x000001FFC409E4B0> |
| `image_height` | number | H | `48` | min=`4`, max=`4000` | disabled when <function CardDescriptor.<lambda> at 0x000001FFC409E560> |
| `image_preserve_aspect` | boolean | Preserve Aspect | `True` |  | disabled when <function CardDescriptor.<lambda> at 0x000001FFC409E610> |
| `image_pad_x` | number | X | `0` | min=_dynamic_, max=_dynamic_ | disabled when <function CardDescriptor.<lambda> at 0x000001FFC409E820> |
| `image_pad_y` | number | Y | `0` | min=_dynamic_, max=_dynamic_ | disabled when <function CardDescriptor.<lambda> at 0x000001FFC409EA30> |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `200` | min=`8`, max=`4000` |  |
| `height` | number | H | `200` | min=`8`, max=`4000` |  |

### Shape

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `shape_type` | enum | Type | `"rounded"` |  |  |
| `corner_radius` | number | Corner Radius | `12` | min=`0`, max=_dynamic_ | disabled when <function CardDescriptor.<lambda> at 0x000001FFC409EB90> |

### Border

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `border_enabled` | boolean | Enabled | `False` |  |  |
| `border_width` | number | Thickness | `1` | min=`1`, max=_dynamic_ | disabled when <function CardDescriptor.<lambda> at 0x000001FFC409ECF0> |
| `border_color` | color | Color | `"#565b5e"` |  | disabled when <function CardDescriptor.<lambda> at 0x000001FFC409EDA0> |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Fill | `"#a2a2a2"` |  |  |

<!-- BEGIN MANUAL -->
### Notes — Entry

_(none yet)_

<!-- END MANUAL -->

# Controls

## Button (`CTkButton`)

| Attribute | Value |
|---|---|
| CTk class | `CircleButton` |
| Generated as | inline class (not from `customtkinter`) |
| Layout default | fills parent (vbox/hbox/grid) |

### Text

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `text` | multiline | Label | `"CTkButton"` |  |  |
| `font_family` | font | Font | `None` |  |  |
| `font_size` | number | Size | `13` | min=`6`, max=`96` | disabled when <function CTkButtonDescriptor.<lambda> at 0x000001FFC3809F30> |
| `font_autofit` | boolean | Auto Fit | `False` |  |  |
| `font_bold` | boolean | Bold | `False` |  |  |
| `font_italic` | boolean | Italic | `False` |  |  |
| `font_underline` | boolean | Underline | `False` |  |  |
| `font_overstrike` | boolean | Strike | `False` |  |  |
| `anchor` | anchor | Alignment | `"center"` |  |  |
| `text_color` | color | Normal Text Color | `"#ffffff"` |  |  |
| `text_color_disabled` | color | Disabled Text Color | `"#a0a0a0"` |  |  |
| `text_hover` | boolean | Hover Color Effect | `False` |  |  |
| `text_hover_color` | color | Hover Color | `"#b2b2b2"` |  | disabled when <function CTkButtonDescriptor.<lambda> at 0x000001FFC380A350> |

### Icon

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `image` | image | Icon | `None` |  |  |
| `image_color` | color | Normal Color | `None` |  | disabled when <function CTkButtonDescriptor.<lambda> at 0x000001FFC380A400> |
| `image_color_disabled` | color | Disabled Color | `None` |  | disabled when <function CTkButtonDescriptor.<lambda> at 0x000001FFC380A4B0> |
| `image_width` | number | W | `20` | min=`4`, max=`512` | disabled when <function CTkButtonDescriptor.<lambda> at 0x000001FFC380A560> |
| `image_height` | number | H | `20` | min=`4`, max=`512` | disabled when <function CTkButtonDescriptor.<lambda> at 0x000001FFC380A610> |
| `compound` | compound | Icon Side | `"left"` |  | disabled when <function CTkButtonDescriptor.<lambda> at 0x000001FFC380A6C0> |
| `preserve_aspect` | boolean | Preserve Aspect | `False` |  | disabled when <function CTkButtonDescriptor.<lambda> at 0x000001FFC380A770> |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `140` | min=`20`, max=`2000` |  |
| `height` | number | H | `32` | min=`20`, max=`2000` |  |

### Rectangle

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `corner_radius` | number | Corner Radius | `6` | min=`0`, max=_dynamic_ |  |
| `border_enabled` | boolean | Enabled | `False` |  |  |
| `border_width` | number | Thickness | `1` | min=`1`, max=_dynamic_ | disabled when <function CTkButtonDescriptor.<lambda> at 0x000001FFC380A980> |
| `border_color` | color | Color | `"#565b5e"` |  | disabled when <function CTkButtonDescriptor.<lambda> at 0x000001FFC380AA30> |
| `border_spacing` | number | Inner Padding | `2` | min=`0`, max=`20` |  |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Background | `"#6366f1"` |  |  |
| `hover_color` | color | Hover Color | `"#4f46e5"` |  | disabled when <function CTkButtonDescriptor.<lambda> at 0x000001FFC380AAE0> |

### Button Interaction

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `button_enabled` | boolean | Interactable | `True` |  |  |
| `hover` | boolean | Hover Effect | `True` |  |  |

<!-- BEGIN MANUAL -->
### Notes — Button

_(none yet)_

<!-- END MANUAL -->

## Entry (`CTkEntry`)

| Attribute | Value |
|---|---|
| Layout default | fills parent (vbox/hbox/grid) |

### Content

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `placeholder_text` | multiline | Placeholder | `"Enter text…"` |  |  |
| `initial_value` | multiline | Initial Text | `""` |  |  |
| `password` | boolean | Password | `False` |  |  |

### Text

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `font_family` | font | Font | `None` |  |  |
| `font_size` | number | Size | `13` | min=`6`, max=`96` |  |
| `font_bold` | boolean | Bold | `False` |  |  |
| `font_italic` | boolean | Italic | `False` |  |  |
| `font_underline` | boolean | Underline | `False` |  |  |
| `font_overstrike` | boolean | Strike | `False` |  |  |
| `justify` | justify | Text Align | `"left"` |  |  |
| `text_color` | color | Normal Text Color | `"#dce4ee"` |  |  |
| `placeholder_text_color` | color | Placeholder Color | `"#9ea0a2"` |  |  |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `140` | min=`40`, max=`2000` |  |
| `height` | number | H | `28` | min=`20`, max=`2000` |  |

### Rectangle

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `corner_radius` | number | Corner Radius | `6` | min=`0`, max=_dynamic_ |  |
| `border_enabled` | boolean | Enabled | `True` |  |  |
| `border_width` | number | Thickness | `2` | min=`1`, max=_dynamic_ | disabled when <function CTkEntryDescriptor.<lambda> at 0x000001FFC405D2D0> |
| `border_color` | color | Color | `"#565b5e"` |  | disabled when <function CTkEntryDescriptor.<lambda> at 0x000001FFC405D380> |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Field Background | `"#343638"` |  |  |

### Button Interaction

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `button_enabled` | boolean | Interactable | `True` |  | disabled when <function CTkEntryDescriptor.<lambda> at 0x000001FFC405D430> |
| `readonly` | boolean | Read-only | `False` |  |  |

<!-- BEGIN MANUAL -->
### Notes — Combo Box

_(none yet)_

<!-- END MANUAL -->

## Textbox (`CTkTextbox`)

| Attribute | Value |
|---|---|
| Layout default | fills parent (vbox/hbox/grid) |
| Init-only keys | `activate_scrollbars` |

### Content

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `initial_text` | multiline | Initial Text | `""` |  |  |
| `wrap` | wrap | Wrap | `"char"` |  |  |
| `activate_scrollbars` | boolean | Show Scrollbars | `True` |  |  |

### Text

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `font_family` | font | Font | `None` |  |  |
| `font_size` | number | Size | `13` | min=`6`, max=`96` |  |
| `font_bold` | boolean | Bold | `False` |  |  |
| `font_italic` | boolean | Italic | `False` |  |  |
| `font_underline` | boolean | Underline | `False` |  |  |
| `font_overstrike` | boolean | Strike | `False` |  |  |
| `text_color` | color | Normal Text Color | `"#dce4ee"` |  |  |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `200` | min=`50`, max=`4000` |  |
| `height` | number | H | `200` | min=`30`, max=`4000` |  |

### Rectangle

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `corner_radius` | number | Corner Radius | `6` | min=`0`, max=_dynamic_ |  |
| `border_enabled` | boolean | Enabled | `False` |  |  |
| `border_width` | number | Thickness | `1` | min=`1`, max=`20` | disabled when <function CTkTextboxDescriptor.<lambda> at 0x000001FFC409DBC0> |
| `border_color` | color | Color | `"#565b5e"` |  | disabled when <function CTkTextboxDescriptor.<lambda> at 0x000001FFC409DC70> |
| `border_spacing` | number | Inner Padding | `3` | min=`0`, max=`50` |  |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Background | `"#1d1e1e"` |  |  |
| `scrollbar_button_color` | color | Scrollbar | `"#696969"` |  |  |
| `scrollbar_button_hover_color` | color | Scrollbar Hover | `"#878787"` |  |  |

### Button Interaction

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `button_enabled` | boolean | Interactable | `True` |  |  |

<!-- BEGIN MANUAL -->
### Notes — Label

- **Autofit + Wrap:** when `font_autofit=True` and `font_wrap=True`,
  Auto Fit picks the largest font size where the *wrapped* text fits
  the box (multi-line aware via greedy word-wrap).
- **Wraplength fallback:** `font_wrap=True` + `wraplength=0` →
  effective wraplength = `width - 8`. Tk's native `wraplength=0` means
  "no wrap"; the descriptor remaps it so the "Enabled" checkbox
  actually enables wrap without forcing the user to type a length.
- **`_font_size_pre_autofit` shadow:** stashed when Auto Fit toggles
  ON so the user's pre-autofit size is restored on toggle OFF.
  Persists to JSON; filtered out of CTk kwargs by `_SHADOW_KEYS`.
- **Anchor scope is the content block, not text alone.** `anchor`
  positions the entire text + icon block within the widget — that's
  why it lives in its own `Alignment` group rather than `Text`.
  Multi-line text relative alignment is `justify` (stays in `Text`).
- **Disabled visuals are manual, not Tk `state`.** `label_enabled=False`
  does NOT pass `state="disabled"` to the inner Tk Label — Windows-Tk
  paints a native white "wash" over the `image=` in disabled mode,
  which would make icons look broken when no `image_color_disabled`
  is set. Instead, `transform_properties` swaps `text_color` →
  `text_color_disabled` and lets `_build_image` apply
  `image_color_disabled` (or fall back to `image_color`) as a tint.
  Side effect: `state` is not set on the inner Tk Label, so
  `disabledforeground` is unused and `text_color_disabled` is read
  directly as the new `text_color` instead.
- **Image tint pipeline mirrors CTkButton.** `_build_image`,
  `_tint_image`, `_native_aspect`, `_aspect_cache`, and
  `compute_derived(preserve_aspect)` are 1:1 copies of the Button
  descriptor. Keep them in lockstep — if you change one, change the
  other.
- **Events.** Label has 16 bind-style events registered in
  `EVENT_REGISTRY` — five mouse-button events (`<Button-1>`,
  `<Double-Button-1>`, `<Button-2>`, `<Button-3>`, `<ButtonRelease-1>`),
  four mouse-motion / wheel events (`<Enter>`, `<Leave>`, `<Motion>`,
  `<MouseWheel>`), three lifecycle / geometry events (`<Configure>`,
  `<Map>`, `<Unmap>`), and four focus / keyboard events (`<FocusIn>`,
  `<FocusOut>`, `<KeyPress>`, `<KeyRelease>`). The last group requires
  `takefocus=True` to fire — Tk delivers focus / key events only to
  the focused widget. CTkLabel has no `command=` constructor kwarg —
  every binding is post-construction `.bind()`, which CTkLabel routes
  onto both inner canvas and inner Tk Label so the rounded-corner hit
  area is also clickable. `<Motion>` and `<Configure>` carry warnings
  on their `EventEntry` for high-frequency event firing.
- **Default vs Advanced split.** Of the 16 events, 5 sit on the flat
  default list — `<Button-1>`, `<Double-Button-1>`, `<Enter>`,
  `<Leave>`, `<MouseWheel>`. The remaining 11 carry `advanced=True`
  on their `EventEntry` and render inside a collapsible "Advanced"
  sub-section in the right-click cascade and the Properties panel
  Events group: middle / right click, mouse release, motion, the
  three lifecycle events, and the four `takefocus`-gated focus / key
  events. Properties panel auto-expands the Advanced sub-section
  when at least one of those events already has a binding so the
  user doesn't lose track of an existing handler.
- **`padx` / `pady` and italic clipping.** These map onto the inner
  Tk Label as `padx=`, `pady=`. Defaults are `0` — clean / flush
  rendering. Italic / script fonts under-count the slant tail in
  Tk's glyph-advance measurement, so the last character of an italic
  line clips at `padx=0`. Bump `padx ≥ 4` in projects that use
  italic Label text. Pre-v1.14.2 the descriptor force-applied
  `padx=4` via `apply_state` and re-emitted that line in
  `export_state`; both are gone now that the value is a real
  property.
- **Interaction group.** `Enabled`, `Cursor`, `Take Focus`. Cursor
  uses a curated subset of Tk cursor names — empty string (`""`)
  means "inherit from parent" and reads as "(default)" in the cell.
  `Take Focus` flips the inner Tk Label's `takefocus` to `True` so
  the label can receive keyboard focus and fire `<FocusIn>` /
  `<FocusOut>` / `<KeyPress>` / `<KeyRelease>` bindings — by default
  Label has `takefocus=0` and these events are dead.
- **Main Colors — Foreground vs Background.** Label is the only
  widget that exposes BOTH `fg_color` and `bg_color`. To avoid the
  ambiguity of two rows both labelled "Background", `fg_color`
  renders as **Foreground** (the body fill) and `bg_color` as
  **Background** (the antialiasing layer behind rounded corners).
  Other widgets keep `fg_color` row as "Background" because they
  don't surface `bg_color` and there's no name collision. `bg_color`
  default `"transparent"` triggers CTk's auto-derive from parent;
  setting an explicit color is only useful when the parent is a
  gradient / image where CTk's auto-detect can't read a single solid
  color. ✕ on either reverts to `"transparent"`.

<!-- END MANUAL -->

## Check Box (`CTkCheckBox`)

### Text

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `text` | multiline | Label | `"CTkCheckBox"` |  |  |
| `font_family` | font | Font | `None` |  |  |
| `font_size` | number | Size | `13` | min=`6`, max=`96` |  |
| `font_bold` | boolean | Bold | `False` |  |  |
| `font_italic` | boolean | Italic | `False` |  |  |
| `font_underline` | boolean | Underline | `False` |  |  |
| `font_overstrike` | boolean | Strike | `False` |  |  |
| `text_color` | color | Normal Text Color | `"#dce4ee"` |  |  |
| `text_color_disabled` | color | Disabled Text Color | `"#737373"` |  |  |
| `text_position` | text_position | Text Position | `"right"` |  |  |
| `text_spacing` | number | Text Spacing | `6` | min=`0`, max=`100` |  |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `20` | min=`20`, max=`2000` |  |
| `height` | number | H | `10` | min=`10`, max=`2000` |  |

### Box

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `checkbox_width` | number | W | `24` | min=`10`, max=`200` |  |
| `checkbox_height` | number | H | `24` | min=`10`, max=`200` |  |
| `corner_radius` | number | Corner Radius | `6` | min=`0`, max=_dynamic_ |  |
| `border_enabled` | boolean | Enabled | `True` |  |  |
| `border_width` | number | Thickness | `3` | min=`1`, max=_dynamic_ | disabled when <function CTkCheckBoxDescriptor.<lambda> at 0x000001FFC380BAB0> |
| `border_color` | color | Color | `"#949A9F"` |  | disabled when <function CTkCheckBoxDescriptor.<lambda> at 0x000001FFC380BB60> |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Fill (Checked) | `"#6366f1"` |  |  |
| `hover_color` | color | Hover | `"#4f46e5"` |  | disabled when <function CTkCheckBoxDescriptor.<lambda> at 0x000001FFC380BC10> |
| `checkmark_color` | color | Check Mark | `"#e5e5e5"` |  |  |

### Button Interaction

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `button_enabled` | boolean | Interactable | `True` |  |  |
| `hover` | boolean | Hover Effect | `True` |  |  |
| `initially_checked` | boolean | Initially Checked | `False` |  |  |

<!-- BEGIN MANUAL -->
### Notes — Image

_(none yet)_

<!-- END MANUAL -->

## Switch (`CTkSwitch`)

### Text

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `text` | multiline | Label | `"CTkSwitch"` |  |  |
| `font_family` | font | Font | `None` |  |  |
| `font_size` | number | Size | `13` | min=`6`, max=`96` |  |
| `font_bold` | boolean | Bold | `False` |  |  |
| `font_italic` | boolean | Italic | `False` |  |  |
| `font_underline` | boolean | Underline | `False` |  |  |
| `font_overstrike` | boolean | Strike | `False` |  |  |
| `text_color` | color | Normal Text Color | `"#dce4ee"` |  |  |
| `text_color_disabled` | color | Disabled Text Color | `"#737373"` |  |  |
| `text_position` | text_position | Text Position | `"right"` |  |  |
| `text_spacing` | number | Text Spacing | `6` | min=`0`, max=`100` |  |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `20` | min=`20`, max=`2000` |  |
| `height` | number | H | `10` | min=`10`, max=`2000` |  |

### Toggle

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `switch_width` | number | W | `36` | min=`10`, max=`200` |  |
| `switch_height` | number | H | `18` | min=`8`, max=`200` |  |
| `corner_radius` | number | Corner Radius | `9` | min=`0`, max=_dynamic_ |  |
| `button_length` | number | Button Length | `0` | min=`0`, max=_dynamic_ |  |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Track (Off) | `"#4a4d50"` |  |  |
| `progress_color` | color | Track (On) | `"#6366f1"` |  |  |
| `button_color` | color | Knob | `"#d5d9de"` |  |  |
| `button_hover_color` | color | Knob Hover | `"#ffffff"` |  | disabled when <function CTkSwitchDescriptor.<lambda> at 0x000001FFC409C460> |

### Button Interaction

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `button_enabled` | boolean | Interactable | `True` |  |  |
| `hover` | boolean | Hover Effect | `True` |  |  |
| `initially_checked` | boolean | Initially On | `False` |  |  |

<!-- BEGIN MANUAL -->
### Notes — Card

_(none yet)_

<!-- END MANUAL -->

## Radio Button (`CTkRadioButton`)

### Text

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `text` | multiline | Label | `"CTkRadioButton"` |  |  |
| `font_family` | font | Font | `None` |  |  |
| `font_size` | number | Size | `13` | min=`6`, max=`96` |  |
| `font_bold` | boolean | Bold | `False` |  |  |
| `font_italic` | boolean | Italic | `False` |  |  |
| `font_underline` | boolean | Underline | `False` |  |  |
| `font_overstrike` | boolean | Strike | `False` |  |  |
| `text_color` | color | Normal Text Color | `"#dce4ee"` |  |  |
| `text_color_disabled` | color | Disabled Text Color | `"#737373"` |  |  |
| `text_position` | text_position | Text Position | `"right"` |  |  |
| `text_spacing` | number | Text Spacing | `6` | min=`0`, max=`100` |  |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `20` | min=`20`, max=`2000` |  |
| `height` | number | H | `10` | min=`10`, max=`2000` |  |

### Dot

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `radiobutton_width` | number | W | `22` | min=`10`, max=`200` |  |
| `radiobutton_height` | number | H | `22` | min=`10`, max=`200` |  |
| `corner_radius` | number | Corner Radius | `11` | min=`0`, max=_dynamic_ |  |
| `border_width_unchecked` | number | Unchecked Width | `3` | min=`0`, max=_dynamic_ |  |
| `border_width_checked` | number | Checked Width | `6` | min=`0`, max=_dynamic_ |  |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Fill (Checked) | `"#6366f1"` |  |  |
| `hover_color` | color | Hover | `"#4f46e5"` |  | disabled when <function CTkRadioButtonDescriptor.<lambda> at 0x000001FFC4079C70> |

### Button Interaction

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `button_enabled` | boolean | Interactable | `True` |  |  |
| `hover` | boolean | Hover Effect | `True` |  |  |
| `initially_checked` | boolean | Initially Checked | `False` |  |  |
| `group` | multiline | Group | `""` |  |  |

<!-- BEGIN MANUAL -->
### Notes — Textbox

_(none yet)_

<!-- END MANUAL -->

## Segmented Button (`CTkSegmentedButton`)

| Attribute | Value |
|---|---|
| Layout default | fills parent (vbox/hbox/grid) |
| Multiline-list keys | `values` |

### Values

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `values` | segment_values | Values | `"First
Second
Third"` |  |  |
| `initial_value` | segment_initial | Initial Value | `"First"` |  |  |

### Text

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `font_family` | font | Font | `None` |  |  |
| `font_size` | number | Size | `13` | min=`6`, max=`96` |  |
| `font_bold` | boolean | Bold | `False` |  |  |
| `font_italic` | boolean | Italic | `False` |  |  |
| `font_underline` | boolean | Underline | `False` |  |  |
| `font_overstrike` | boolean | Strike | `False` |  |  |
| `text_color` | color | Normal Text Color | `"#dce4ee"` |  |  |
| `text_color_disabled` | color | Disabled Text Color | `"#737373"` |  |  |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `240` | min=`60`, max=`2000` |  |
| `height` | number | H | `32` | min=`20`, max=`2000` |  |

### Rectangle

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `corner_radius` | number | Corner Radius | `6` | min=`0`, max=_dynamic_ |  |
| `border_enabled` | boolean | Enabled | `False` |  |  |
| `border_width` | number | Thickness | `2` | min=`1`, max=`20` | disabled when <function CTkSegmentedButtonDescriptor.<lambda> at 0x000001FFC407ACF0> |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Outer Background | `"#4a4d50"` |  |  |
| `selected_color` | color | Selected | `"#6366f1"` |  |  |
| `selected_hover_color` | color | Selected Hover | `"#4f46e5"` |  |  |
| `unselected_color` | color | Unselected | `"#4a4d50"` |  |  |
| `unselected_hover_color` | color | Unselected Hover | `"#696969"` |  |  |

### Button Interaction

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `button_enabled` | boolean | Interactable | `True` |  |  |

<!-- BEGIN MANUAL -->
### Notes — Segmented Button

_(none yet)_

<!-- END MANUAL -->

## Combo Box (`CTkComboBox`)

| Attribute | Value |
|---|---|
| Multiline-list keys | `values` |

### Values

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `values` | segment_values | Values | `"Option 1
Option 2
Option 3"` |  |  |
| `initial_value` | segment_initial | Initial Value | `"Option 1"` |  |  |

### Text

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `font_family` | font | Font | `None` |  |  |
| `font_size` | number | Size | `13` | min=`6`, max=`96` |  |
| `font_bold` | boolean | Bold | `False` |  |  |
| `font_italic` | boolean | Italic | `False` |  |  |
| `font_underline` | boolean | Underline | `False` |  |  |
| `font_overstrike` | boolean | Strike | `False` |  |  |
| `justify` | justify | Text Align | `"left"` |  |  |
| `text_color` | color | Normal Text Color | `"#dce4ee"` |  |  |
| `text_color_disabled` | color | Disabled Text Color | `"#737373"` |  |  |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `140` | min=`40`, max=`2000` |  |
| `height` | number | H | `28` | min=`20`, max=`2000` |  |

### Rectangle

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `corner_radius` | number | Corner Radius | `6` | min=`0`, max=_dynamic_ |  |
| `border_enabled` | boolean | Enabled | `True` |  |  |
| `border_width` | number | Thickness | `2` | min=`1`, max=_dynamic_ | disabled when <function CTkComboBoxDescriptor.<lambda> at 0x000001FFC405C670> |
| `border_color` | color | Color | `"#565b5e"` |  | disabled when <function CTkComboBoxDescriptor.<lambda> at 0x000001FFC405C720> |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Field Background | `"#343638"` |  |  |
| `button_color` | color | Arrow Button | `"#565b5e"` |  |  |
| `button_hover_color` | color | Arrow Hover | `"#7a848d"` |  | disabled when <function CTkComboBoxDescriptor.<lambda> at 0x000001FFC405C7D0> |

### Dropdown Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `dropdown_fg_color` | color | Background | `"#2b2b2b"` |  |  |
| `dropdown_hover_color` | color | Hover | `"#3a3a3a"` |  |  |
| `dropdown_text_color` | color | Text | `"#dce4ee"` |  |  |

### Dropdown Layout

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `dropdown_offset` | number | Offset | `4` | min=`0`, max=`40` |  |
| `dropdown_button_align` | justify | Item Align | `"center"` |  |  |
| `dropdown_max_visible` | number | Max Visible | `8` | min=`1`, max=`30` |  |
| `dropdown_corner_radius` | number | Corner Radius | `6` | min=`0`, max=`30` |  |
| `dropdown_border_enabled` | boolean | Enabled | `True` |  |  |
| `dropdown_border_width` | number | Thickness | `1` | min=`1`, max=`10` | disabled when <function CTkComboBoxDescriptor.<lambda> at 0x000001FFC405C880> |
| `dropdown_border_color` | color | Color | `"#3c3c3c"` |  | disabled when <function CTkComboBoxDescriptor.<lambda> at 0x000001FFC405C930> |

### Button Interaction

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `button_enabled` | boolean | Interactable | `True` |  |  |
| `hover` | boolean | Hover Effect | `True` |  |  |

<!-- BEGIN MANUAL -->
### Notes — Check Box

_(none yet)_

<!-- END MANUAL -->

## Option Menu (`CTkOptionMenu`)

| Attribute | Value |
|---|---|
| Multiline-list keys | `values` |

### Values

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `values` | segment_values | Values | `"Option 1
Option 2
Option 3"` |  |  |
| `initial_value` | segment_initial | Initial Value | `"Option 1"` |  |  |

### Text

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `font_family` | font | Font | `None` |  |  |
| `font_size` | number | Size | `13` | min=`6`, max=`96` |  |
| `font_bold` | boolean | Bold | `False` |  |  |
| `font_italic` | boolean | Italic | `False` |  |  |
| `font_underline` | boolean | Underline | `False` |  |  |
| `font_overstrike` | boolean | Strike | `False` |  |  |
| `text_align` | justify | Text Align | `"left"` |  |  |
| `text_color` | color | Normal Text Color | `"#dce4ee"` |  |  |
| `text_color_disabled` | color | Disabled Text Color | `"#737373"` |  |  |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `140` | min=`40`, max=`2000` |  |
| `height` | number | H | `28` | min=`20`, max=`2000` |  |

### Rectangle

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `corner_radius` | number | Corner Radius | `6` | min=`0`, max=_dynamic_ |  |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Background | `"#6366f1"` |  |  |
| `button_color` | color | Arrow Button | `"#4f46e5"` |  |  |
| `button_hover_color` | color | Arrow Hover | `"#203a4f"` |  | disabled when <function CTkOptionMenuDescriptor.<lambda> at 0x000001FFC4078510> |

### Dropdown Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `dropdown_fg_color` | color | Background | `"#2b2b2b"` |  |  |
| `dropdown_hover_color` | color | Hover | `"#3a3a3a"` |  |  |
| `dropdown_text_color` | color | Text | `"#dce4ee"` |  |  |

### Dropdown Layout

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `dropdown_offset` | number | Offset | `4` | min=`0`, max=`40` |  |
| `dropdown_button_align` | justify | Item Align | `"center"` |  |  |
| `dropdown_max_visible` | number | Max Visible | `8` | min=`1`, max=`30` |  |
| `dropdown_corner_radius` | number | Corner Radius | `6` | min=`0`, max=`30` |  |
| `dropdown_border_enabled` | boolean | Enabled | `True` |  |  |
| `dropdown_border_width` | number | Thickness | `1` | min=`1`, max=`10` | disabled when <function CTkOptionMenuDescriptor.<lambda> at 0x000001FFC40785C0> |
| `dropdown_border_color` | color | Color | `"#3c3c3c"` |  | disabled when <function CTkOptionMenuDescriptor.<lambda> at 0x000001FFC4078670> |

### Button Interaction

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `button_enabled` | boolean | Interactable | `True` |  |  |
| `hover` | boolean | Hover Effect | `True` |  |  |

<!-- BEGIN MANUAL -->
### Notes — Option Menu

_(none yet)_

<!-- END MANUAL -->

## Slider (`CTkSlider`)

| Attribute | Value |
|---|---|
| Layout default | fills parent (vbox/hbox/grid) |
| Init-only keys | `orientation` |

### Value Range

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `from_` | number | Min | `0` |  |  |
| `to` | number | Max | `100` |  |  |
| `number_of_steps` | number | Steps | `0` | min=`0`, max=`1000` |  |
| `initial_value` | number | Initial Value | `50` |  |  |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `200` | min=_dynamic_, max=`2000` |  |
| `height` | number | H | `16` | min=_dynamic_, max=`2000` |  |

### Orientation

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `orientation` | orientation | Orientation | `"horizontal"` |  |  |

### Rectangle

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `corner_radius` | number | Track Radius | `8` | min=`1`, max=`50` |  |
| `button_corner_radius` | number | Button Radius | `8` | min=`1`, max=`50` |  |
| `button_length` | number | Button Length | `1` | min=`1`, max=_dynamic_ |  |
| `border_enabled` | boolean | Enabled | `False` |  |  |
| `border_width` | number | Thickness | `6` | min=`1`, max=`20` | disabled when <function CTkSliderDescriptor.<lambda> at 0x000001FFC407B690> |
| `border_color` | color | Color | `"#565b5e"` |  | disabled when <function CTkSliderDescriptor.<lambda> at 0x000001FFC407B740> |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Track | `"#4a4d50"` |  |  |
| `progress_color` | color | Progress | `"#aab0b5"` |  |  |
| `button_color` | color | Button | `"#6366f1"` |  |  |
| `button_hover_color` | color | Button Hover | `"#4f46e5"` |  | disabled when <function CTkSliderDescriptor.<lambda> at 0x000001FFC407B7F0> |

### Button Interaction

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `button_enabled` | boolean | Interactable | `True` |  |  |
| `hover` | boolean | Hover Effect | `True` |  |  |

<!-- BEGIN MANUAL -->
### Notes — Slider

_(none yet)_

<!-- END MANUAL -->

# Containers

## Frame (`CTkFrame`)

| Attribute | Value |
|---|---|
| Container | yes — can hold children |
| Layout default | fills parent (vbox/hbox/grid) |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `200` | min=`20`, max=`4000` |  |
| `height` | number | H | `150` | min=`20`, max=`4000` |  |

### Rectangle

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `corner_radius` | number | Corner Radius | `6` | min=`0`, max=_dynamic_ |  |
| `border_enabled` | boolean | Enabled | `False` |  |  |
| `border_width` | number | Thickness | `1` | min=`1`, max=_dynamic_ | disabled when <function CTkFrameDescriptor.<lambda> at 0x000001FFC405EAE0> |
| `border_color` | color | Color | `"#565b5e"` |  | disabled when <function CTkFrameDescriptor.<lambda> at 0x000001FFC405EB90> |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Background | `"#2b2b2b"` |  |  |

### Layout

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `layout_type` | layout_type | Manager | `"place"` |  |  |
| `layout_spacing` | number | Spacing | `4` | min=`0`, max=`200` | hidden when <function <lambda> at 0x000001FFC405DC70> |
| `grid_rows` | number | R | `2` | min=`1`, max=`50` | hidden when <function <lambda> at 0x000001FFC405DD20> |
| `grid_cols` | number | C | `2` | min=`1`, max=`50` | hidden when <function <lambda> at 0x000001FFC405DD20> |

<!-- BEGIN MANUAL -->
### Notes — Frame

_(none yet)_

<!-- END MANUAL -->

## Scrollable Frame (`CTkScrollableFrame`)

| Attribute | Value |
|---|---|
| Container | yes — can hold children |
| Layout default | fills parent (vbox/hbox/grid) |
| Init-only keys | `orientation` |

### Label

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `label_text` | multiline | Label Text | `""` |  |  |
| `label_text_align` | justify | Label Align | `"center"` |  |  |
| `font_family` | font | Label Font | `None` |  |  |
| `label_fg_color` | color | Label Background | `"#3a3a3a"` |  |  |
| `label_text_color` | color | Label Text Color | `"#dce4ee"` |  |  |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `200` | min=`50`, max=`4000` |  |
| `height` | number | H | `200` | min=`50`, max=`4000` |  |

### Rectangle

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `corner_radius` | number | Corner Radius | `6` | min=`0`, max=_dynamic_ |  |
| `border_enabled` | boolean | Enabled | `False` |  |  |
| `border_width` | number | Thickness | `1` | min=`1`, max=`50` | disabled when <function CTkScrollableFrameDescriptor.<lambda> at 0x000001FFC407A4B0> |
| `border_color` | color | Color | `"#565b5e"` |  | disabled when <function CTkScrollableFrameDescriptor.<lambda> at 0x000001FFC407A560> |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Frame Background | `"#2b2b2b"` |  |  |

### Scrollbar

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `orientation` | orientation | Orientation | `"vertical"` |  |  |
| `scrollbar_fg_color` | color | Track | `"#1a1a1a"` |  |  |
| `scrollbar_button_color` | color | Thumb | `"#3a3a3a"` |  |  |
| `scrollbar_button_hover_color` | color | Thumb Hover | `"#4a4a4a"` |  |  |

### Layout

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `layout_spacing` | number | Spacing | `4` | min=`0`, max=`200` | hidden when <function <lambda> at 0x000001FFC405DC70> |

<!-- BEGIN MANUAL -->
### Notes — Scrollable Frame

_(none yet)_

<!-- END MANUAL -->

## Tab View (`CTkTabview`)

| Attribute | Value |
|---|---|
| Container | yes — can hold children |
| Layout default | fills parent (vbox/hbox/grid) |

### Tabs

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `tab_names` | segment_values | Tab Names | `"Tab 1
Tab 2
Tab 3"` |  |  |
| `initial_tab` | segment_initial | Initial Tab | `"Tab 1"` |  |  |
| `tab_position` | tab_bar_position | Tab Bar Position | `"top"` |  |  |
| `tab_anchor` | tab_bar_align | Tab Bar Align | `"center"` |  |  |

### Text

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `font_family` | font | Tab Font | `None` |  |  |
| `text_color` | color | Normal Text Color | `"#dce4ee"` |  |  |
| `text_color_disabled` | color | Disabled Text Color | `"#737373"` |  |  |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `300` | min=`80`, max=`4000` |  |
| `height` | number | H | `250` | min=`60`, max=`4000` |  |

### Rectangle

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `corner_radius` | number | Corner Radius | `6` | min=`0`, max=_dynamic_ |  |
| `border_enabled` | boolean | Enabled | `False` |  |  |
| `border_width` | number | Thickness | `2` | min=`1`, max=`20` | disabled when <function CTkTabviewDescriptor.<lambda> at 0x000001FFC409CCA0> |
| `border_color` | color | Color | `"#565b5e"` |  | disabled when <function CTkTabviewDescriptor.<lambda> at 0x000001FFC409CD50> |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Frame Background | `"#2b2b2b"` |  |  |
| `segmented_button_fg_color` | color | Tab Bar Background | `"#4a4d50"` |  |  |
| `segmented_button_selected_color` | color | Tab Selected | `"#6366f1"` |  |  |
| `segmented_button_selected_hover_color` | color | Tab Selected Hover | `"#4f46e5"` |  |  |
| `segmented_button_unselected_color` | color | Tab Unselected | `"#4a4d50"` |  |  |
| `segmented_button_unselected_hover_color` | color | Tab Unselected Hover | `"#696969"` |  |  |

### Button Interaction

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `button_enabled` | boolean | Interactable | `True` |  |  |

<!-- BEGIN MANUAL -->
### Notes — Tab View

_(none yet)_

<!-- END MANUAL -->

# Layouts

## Vertical Layout (`CTkFrame`)

| Attribute | Value |
|---|---|
| Container | yes — can hold children |
| Layout default | fills parent (vbox/hbox/grid) |
| Palette preset | `layout_type=`"vbox"``, `fg_color=`"transparent"``, `width=`240``, `height=`180`` |
| Default name slug | `vertical_layout` |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `240` | min=`20`, max=`4000` |  |
| `height` | number | H | `180` | min=`20`, max=`4000` |  |

### Rectangle

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `corner_radius` | number | Corner Radius | `6` | min=`0`, max=_dynamic_ |  |
| `border_enabled` | boolean | Enabled | `False` |  |  |
| `border_width` | number | Thickness | `1` | min=`1`, max=_dynamic_ | disabled when <function CTkFrameDescriptor.<lambda> at 0x000001FFC405EAE0> |
| `border_color` | color | Color | `"#565b5e"` |  | disabled when <function CTkFrameDescriptor.<lambda> at 0x000001FFC405EB90> |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Background | `"transparent"` |  |  |

### Layout

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `layout_type` | layout_type | Manager | `"vbox"` |  |  |
| `layout_spacing` | number | Spacing | `4` | min=`0`, max=`200` | hidden when <function <lambda> at 0x000001FFC405DC70> |
| `grid_rows` | number | R | `2` | min=`1`, max=`50` | hidden when <function <lambda> at 0x000001FFC405DD20> |
| `grid_cols` | number | C | `2` | min=`1`, max=`50` | hidden when <function <lambda> at 0x000001FFC405DD20> |

<!-- BEGIN MANUAL -->
### Notes — Vertical Layout

_(none yet)_

<!-- END MANUAL -->

## Horizontal Layout (`CTkFrame`)

| Attribute | Value |
|---|---|
| Container | yes — can hold children |
| Layout default | fills parent (vbox/hbox/grid) |
| Palette preset | `layout_type=`"hbox"``, `fg_color=`"transparent"``, `width=`320``, `height=`60`` |
| Default name slug | `horizontal_layout` |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `320` | min=`20`, max=`4000` |  |
| `height` | number | H | `60` | min=`20`, max=`4000` |  |

### Rectangle

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `corner_radius` | number | Corner Radius | `6` | min=`0`, max=_dynamic_ |  |
| `border_enabled` | boolean | Enabled | `False` |  |  |
| `border_width` | number | Thickness | `1` | min=`1`, max=_dynamic_ | disabled when <function CTkFrameDescriptor.<lambda> at 0x000001FFC405EAE0> |
| `border_color` | color | Color | `"#565b5e"` |  | disabled when <function CTkFrameDescriptor.<lambda> at 0x000001FFC405EB90> |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Background | `"transparent"` |  |  |

### Layout

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `layout_type` | layout_type | Manager | `"hbox"` |  |  |
| `layout_spacing` | number | Spacing | `4` | min=`0`, max=`200` | hidden when <function <lambda> at 0x000001FFC405DC70> |
| `grid_rows` | number | R | `2` | min=`1`, max=`50` | hidden when <function <lambda> at 0x000001FFC405DD20> |
| `grid_cols` | number | C | `2` | min=`1`, max=`50` | hidden when <function <lambda> at 0x000001FFC405DD20> |

<!-- BEGIN MANUAL -->
### Notes — Horizontal Layout

_(none yet)_

<!-- END MANUAL -->

## Grid Layout (`CTkFrame`)

| Attribute | Value |
|---|---|
| Container | yes — can hold children |
| Layout default | fills parent (vbox/hbox/grid) |
| Palette preset | `layout_type=`"grid"``, `fg_color=`"transparent"``, `width=`320``, `height=`240`` |
| Default name slug | `grid_layout` |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `320` | min=`20`, max=`4000` |  |
| `height` | number | H | `240` | min=`20`, max=`4000` |  |

### Rectangle

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `corner_radius` | number | Corner Radius | `6` | min=`0`, max=_dynamic_ |  |
| `border_enabled` | boolean | Enabled | `False` |  |  |
| `border_width` | number | Thickness | `1` | min=`1`, max=_dynamic_ | disabled when <function CTkFrameDescriptor.<lambda> at 0x000001FFC405EAE0> |
| `border_color` | color | Color | `"#565b5e"` |  | disabled when <function CTkFrameDescriptor.<lambda> at 0x000001FFC405EB90> |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Background | `"transparent"` |  |  |

### Layout

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `layout_type` | layout_type | Manager | `"grid"` |  |  |
| `layout_spacing` | number | Spacing | `4` | min=`0`, max=`200` | hidden when <function <lambda> at 0x000001FFC405DC70> |
| `grid_rows` | number | R | `2` | min=`1`, max=`50` | hidden when <function <lambda> at 0x000001FFC405DD20> |
| `grid_cols` | number | C | `2` | min=`1`, max=`50` | hidden when <function <lambda> at 0x000001FFC405DD20> |

<!-- BEGIN MANUAL -->
### Notes — Grid Layout

_(none yet)_

<!-- END MANUAL -->

# Indicators

## Progress Bar (`CTkProgressBar`)

| Attribute | Value |
|---|---|
| Layout default | fills parent (vbox/hbox/grid) |
| Init-only keys | `orientation` |

### Progress

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `orientation` | orientation | Orientation | `"horizontal"` |  |  |
| `initial_percent` | number | Progress % | `50` | min=`0`, max=`100` |  |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `200` | min=_dynamic_, max=`2000` |  |
| `height` | number | H | `16` | min=_dynamic_, max=`2000` |  |

### Rectangle

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `corner_radius` | number | Corner Radius | `8` | min=`1`, max=`50` |  |
| `border_enabled` | boolean | Enabled | `False` |  |  |
| `border_width` | number | Thickness | `2` | min=`1`, max=`20` | disabled when <function CTkProgressBarDescriptor.<lambda> at 0x000001FFC4079170> |
| `border_color` | color | Color | `"#7a7a7a"` |  | disabled when <function CTkProgressBarDescriptor.<lambda> at 0x000001FFC4079220> |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Track Background | `"#4a4d50"` |  |  |
| `progress_color` | color | Progress Fill | `"#6366f1"` |  |  |

<!-- BEGIN MANUAL -->
### Notes — Progress Bar

_(none yet)_

<!-- END MANUAL -->

## Circular Progress (`CircularProgress`)

| Attribute | Value |
|---|---|
| Generated as | inline class (not from `customtkinter`) |
| Image kwarg | manual (descriptor builds image separately) |

### Progress

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `initial_percent` | number | Percent | `50` | min=`0`, max=`100` |  |

### Text

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `show_text` | boolean | Show | `True` |  |  |
| `suffix` | unit | Unit | `"%"` |  | disabled when <function CircularProgressDescriptor.<lambda> at 0x000001FFC409FCC0> |
| `text_color` | color | Color | `"#ffffff"` |  | disabled when <function CircularProgressDescriptor.<lambda> at 0x000001FFC40B4930> |
| `font_family` | font | Font | `"TkDefaultFont"` |  | disabled when <function CircularProgressDescriptor.<lambda> at 0x000001FFC40B49E0> |
| `font_size` | number | Size | `18` | min=`8`, max=`72` | disabled when <function CircularProgressDescriptor.<lambda> at 0x000001FFC40B4A90> |
| `font_bold` | boolean | Bold | `True` |  | disabled when <function CircularProgressDescriptor.<lambda> at 0x000001FFC40B4B40> |

### Geometry

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `x` | number | X | `120` |  |  |
| `y` | number | Y | `120` |  |  |
| `width` | number | W | `120` | min=`40`, max=`1000` |  |
| `height` | number | H | `120` | min=`40`, max=`1000` |  |

### Ring

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `thickness` | number | Thickness | `12` | min=`1`, max=`60` |  |

### Main Colors

| Property | Type | Label | Default | Range / Values | Notes |
|---|---|---|---|---|---|
| `fg_color` | color | Track | `"#4a4d50"` |  |  |
| `progress_color` | color | Progress | `"#6366f1"` |  |  |

<!-- BEGIN MANUAL -->
### Notes — Circular Progress

_(none yet)_

<!-- END MANUAL -->
