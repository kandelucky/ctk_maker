# Area 7 — Widgets (19 palette entries)

Per-widget sanity sweep. Covers every palette entry — all 19:

- 12 leaf widgets (CTkButton / Label / Entry / Textbox / CheckBox /
  RadioButton / Switch / SegmentedButton / Slider / ProgressBar /
  ComboBox / OptionMenu)
- 4 container variants backed by `CTkFrameDescriptor` (plain Frame,
  Vertical / Horizontal / Grid Layout presets)
- 2 partial containers (ScrollableFrame, Tabview)
- 1 builder composite (Image → `CTkLabel + CTkImage`)

## Per-widget checklist (template)

Run this 8-item sweep for every entry below. Entries just reference
the template instead of repeating it.

1. **Palette drop** — widget appears with descriptor defaults, no error
2. **Every property edits live** — canvas updates on change, no crash
3. **`disabled_when` / `hidden_when`** — lambdas fire on their triggers, dependent rows dim / vanish
4. **`transform_properties`** — generated CTk kwargs are the right shape (no builder-only keys leaked)
5. **`apply_state`** — runtime state (checked, value, inserted text, tabs) reflects on canvas
6. **Save + load round-trip** — reopen the project, widget looks identical
7. **Export + run** — generated `.py` launches, visual matches canvas preview
8. **Undo / redo** — every property change reversible; selection survives

---

## Simple

### CTkButton
- [ ] Template (1–8)
- [ ] `text` / `font` / `fg_color` / `hover_color` / `text_color` all visible on canvas + export
- [ ] `image` + `compound` combinations (left / right / top / bottom / center)
- [ ] `image_color` tint exports via `_tint_image` helper
- [ ] `anchor` picker with 9 positions
- [ ] `border_enabled` toggles `border_width` + `border_color` dim

### CTkLabel
- [ ] Template (1–8)
- [ ] `text` + `font` (size, bold, italic, underline, strike)
- [ ] `anchor` 3×3 picker
- [ ] `wraplength` + enabled/disabled (`Wrap` subgroup)
- [ ] `image` + `compound` (label-as-icon pattern)
- [ ] `text_color` / `fg_color` (background) / `bg_color`

### CTkEntry
- [ ] Template (1–8)
- [ ] `placeholder_text` renders when empty, cleared on focus
- [ ] `initial_value` populated on widget create (via `apply_state` delete + insert)
- [ ] `state` `normal` / `disabled` / `readonly`
- [ ] `justify` left / center / right
- [ ] `password_char` (bullets)

### CTkTextbox
- [ ] Template (1–8)
- [ ] Multi-line `initial_text` round-trip with newlines preserved
- [ ] `wrap` none / char / word
- [ ] `font` changes
- [ ] `activate_scrollbars` (init-only → recreate_triggers)
- [ ] `state` disabled path (no direct state kwarg, uses `configure`)

---

## Selection

### CTkCheckBox
- [ ] Template (1–8)
- [ ] `initially_checked` → runtime checked on open
- [ ] `checkbox_width` / `checkbox_height`
- [ ] `text` + font + `text_color`
- [ ] `fg_color` / `hover_color` / `checkmark_color`
- [ ] `border_enabled` + `border_width` + `border_color`
- [ ] `hover` toggle

### CTkRadioButton
- [ ] Template (1–8)
- [ ] Shared `group` name — two radios same group → exclusive
- [ ] `value` per radio → selected value on export
- [ ] `initially_checked` respects group (only one wins)
- [ ] `border_width_unchecked` / `border_width_checked`

### CTkSwitch
- [ ] Template (1–8)
- [ ] `initially_checked` — runtime ON state
- [ ] `switch_width` / `switch_height`
- [ ] `button_length` > 0 → pill knob
- [ ] `corner_radius` large → fully-rounded

### CTkSegmentedButton
- [ ] Template (1–8)
- [ ] `values` list (multiline → `list[str]` via `transform_properties`)
- [ ] `selected_value` populates on load
- [ ] Adding / removing values on the fly updates segments

---

## Input

### CTkSlider
- [ ] Template (1–8)
- [ ] `from_` / `to` / `number_of_steps` (0 = continuous, exporter emits `None`)
- [ ] `initial_value` set on create
- [ ] `orientation` flip → width/height swap (recreate_trigger)
- [ ] `button_length` shape variants (0 = circle, >0 = pill)
- [ ] `button_corner_radius` ≥ 1 (0 causes CTk internal visual split bug)

### CTkProgressBar
- [ ] Template (1–8)
- [ ] `initial_percent` 0–100 → runtime `.set(pct/100)`
- [ ] `orientation` flip → width/height swap
- [ ] `progress_color` / `fg_color` (track)
- [ ] `border_enabled` + `border_width`

### CTkComboBox
- [ ] Template (1–8)
- [ ] `values` multi-line list
- [ ] `initial_value` populated on load
- [ ] Dropdown style (`dropdown_fg_color` / `dropdown_hover_color` / `dropdown_text_color`)
- [ ] `text_align` → anchor mapping

### CTkOptionMenu
- [ ] Template (1–8)
- [ ] `values` + `initial_value`
- [ ] `dynamic_resizing` hardcoded False (verify exporter)
- [ ] `text_align` → anchor mapping
- [ ] No border (by design — `_NODE_ONLY_KEYS`?)

---

## Containers

### CTkFrame (plain — `layout_type="place"`)
- [ ] Template (1–8)
- [ ] Nested children placed by x/y
- [ ] `fg_color` + `border_width` + `border_color` + `corner_radius`
- [ ] `bg_color` stays transparent by default
- [ ] Reparent a widget into the Frame via drag

### Vertical Layout Frame (`layout_type="vbox"`)
- [ ] Template (1–8)
- [ ] Children stack top-to-bottom with `.pack(side=top)`
- [ ] `layout_spacing` spreads children apart
- [ ] Child `stretch` = fixed / fill / grow — every mode visible
- [ ] Grow equal-split: multiple grow siblings share available height

### Horizontal Layout Frame (`layout_type="hbox"`)
- [ ] Template (1–8)
- [ ] Children stack left-to-right with `.pack(side=left)`
- [ ] `layout_spacing` + `stretch` work the same as vbox on the other axis
- [ ] Grow equal-split: siblings share width

### Grid Layout Frame (`layout_type="grid"`)
- [ ] Template (1–8)
- [ ] `grid_rows` × `grid_cols` dimensions editable; cells drawn via dashed overlay
- [ ] Child `grid_row` / `grid_column` / `grid_sticky`
- [ ] Drag-to-cell snap + palette drop respects cell under cursor
- [ ] Auto-grow when all cells full; Grid → place swap preserves distribution

### CTkScrollableFrame (partial — nested children path)
- [ ] Template 1, 2, 6, 7 (drop, edit, save/load, export)
- [ ] Scrollbar orientation + colours
- [ ] *(Known: drop-children-inside doesn't work cleanly — verify and document remaining gaps)*

### CTkTabview (partial — tabs yes, per-tab children no)
- [ ] Template 1, 2, 6, 7
- [ ] `tab_names` multi-line list → `.add("name")` per tab in export
- [ ] Rename / reorder tabs
- [ ] *(Known: dropping widgets into a specific tab not yet supported — verify the palette refuses cleanly)*

---

## Display

### Image (builder composite)
- [ ] Template (1–8)
- [ ] `image` file picker + clear
- [ ] `preserve_aspect` → height auto-recomputes from width
- [ ] `image_color` tint → runtime PIL `_tint_image` helper
- [ ] `fg_color` background (transparent by default)
- [ ] Missing image path → placeholder `#444444` fill, no crash
- [ ] Exports as `CTkLabel(text="", image=CTkImage(...))`

---

## Widget-specific surprises

- [ ] CTkRadioButton shared `group` — multi-radio coordination via `tk.StringVar`
- [ ] CTkSlider orientation change — width/height swap + widget recreate
- [ ] CTkProgressBar mode — determinate vs indeterminate (builder shows static only)
- [ ] CTkComboBox editable — user-typed value persisted on export
- [ ] Image missing file — placeholder instead of crash
- [ ] CTkButton `command=` — exporter omits or emits placeholder
- [ ] CTkLabel `image` + no `text` — compound gracefully ignored
- [ ] Font changes across widgets — each widget's `CTkFont(...)` is independent

## Refactor candidates

- [ ] 16 descriptor files — scan for repeated property blocks (Geometry, Main Colors, Border subgroup)
- [ ] Shared schema fragments via module-level constants? (e.g. `POSITION_PAIR`, `SIZE_PAIR`, `BORDER_SUBGROUP`)
- [ ] `_NODE_ONLY_KEYS` vs `LAYOUT_NODE_ONLY_KEYS` — overlap check
- [ ] `transform_properties` boilerplate — central helper for "strip node-only + layout keys"

## Optimize candidates

- [ ] Cold widget creation cost (descriptor → CTk constructor)
- [ ] `CTkFont(...)` cache per (family, size, style) — rebuilt on every prop change?
- [ ] `CTkImage` / `_tint_image` cache per (path, hex, size)?
- [ ] `_apply_grow_equal_split` iterates every grow sibling per re-apply — profile for 10+ children

## Findings

<!-- per-widget bugs here; prefix with widget name, e.g.:
     - **[CTkSlider]** orientation flip clears current value
-->
