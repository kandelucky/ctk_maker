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
- [x] Template (1–8)
- [x] `text` / `font` / `fg_color` / `hover_color` / `text_color` all visible on canvas + export
- [x] `image` + `compound` combinations (left / right / top / bottom / center)
- [x] `image_color` tint exports via `_tint_image` helper
- [x] `anchor` picker with 9 positions
- [x] `border_enabled` toggles `border_width` + `border_color` dim

### CTkLabel
- [x] Template (1–8)
- [x] `text` + `font` (size, bold, italic, underline, strike)
- [x] `anchor` 3×3 picker
- [x] `wraplength` + enabled/disabled (`Wrap` subgroup)
- [x] `image` + `compound` (label-as-icon pattern)
- [x] `text_color` / `fg_color` (background) / `bg_color`

### CTkEntry
- [x] Template (1–8)
- [x] `placeholder_text` renders when empty, cleared on focus
- [x] `initial_value` populated on widget create (via `apply_state` delete + insert)
- [x] `state` `normal` / `disabled` / `readonly`
- [x] `justify` left / center / right
- [x] `password_char` (bullets)

### CTkTextbox
- [x] Template (1–8)
- [x] Multi-line `initial_text` round-trip with newlines preserved
- [x] `wrap` none / char / word
- [x] `font` changes
- [x] `activate_scrollbars` (init-only → recreate_triggers)
- [x] `state` disabled path (no direct state kwarg, uses `configure`)

---

## Selection

### CTkCheckBox
- [x] Template (1–8)
- [x] `initially_checked` → runtime checked on open
- [x] `checkbox_width` / `checkbox_height`
- [x] `text` + font + `text_color`
- [x] `fg_color` / `hover_color` / `checkmark_color`
- [x] `border_enabled` + `border_width` + `border_color`
- [x] `hover` toggle

### CTkRadioButton
- [x] Template (1–8)
- [x] Shared `group` name — two radios same group → exclusive
- [x] `value` per radio → selected value on export
- [x] `initially_checked` respects group (only one wins)
- [x] `border_width_unchecked` / `border_width_checked`

### CTkSwitch
- [x] Template (1–8)
- [x] `initially_checked` — runtime ON state
- [x] `switch_width` / `switch_height`
- [x] `button_length` > 0 → pill knob
- [x] `corner_radius` large → fully-rounded

### CTkSegmentedButton
- [x] Template (1–8)
- [x] `values` list (multiline → `list[str]` via `transform_properties`)
- [x] `selected_value` populates on load
- [x] Adding / removing values on the fly updates segments

---

## Input

### CTkSlider
- [x] Template (1–8)
- [x] `from_` / `to` / `number_of_steps` (0 = continuous, exporter emits `None`)
- [x] `initial_value` set on create
- [x] `orientation` flip → width/height swap (recreate_trigger)
- [x] `button_length` shape variants (0 = circle, >0 = pill)
- [x] `button_corner_radius` ≥ 1 (0 causes CTk internal visual split bug)

### CTkProgressBar
- [x] Template (1–8)
- [x] `initial_percent` 0–100 → runtime `.set(pct/100)`
- [x] `orientation` flip → width/height swap
- [x] `progress_color` / `fg_color` (track)
- [x] `border_enabled` + `border_width`

### CTkComboBox
- [x] Template (1–8)
- [x] `values` multi-line list
- [x] `initial_value` populated on load
- [x] Dropdown style (`dropdown_fg_color` / `dropdown_hover_color` / `dropdown_text_color`)
- [x] `text_align` → anchor mapping

### CTkOptionMenu
- [x] Template (1–8)
- [x] `values` + `initial_value`
- [x] `dynamic_resizing` hardcoded False (verify exporter)
- [x] `text_align` → anchor mapping
- [x] No border (by design — `_NODE_ONLY_KEYS`?)

---

## Containers

### CTkFrame (plain — `layout_type="place"`)
- [x] Template (1–8)
- [x] Nested children placed by x/y
- [x] `fg_color` + `border_width` + `border_color` + `corner_radius`
- [x] `bg_color` stays transparent by default
- [x] Reparent a widget into the Frame via drag

### Vertical Layout Frame (`layout_type="vbox"`)
- [x] Template (1–8)
- [x] Children stack top-to-bottom with `.pack(side=top)`
- [x] `layout_spacing` spreads children apart
- [x] Child `stretch` = fixed / fill / grow — every mode visible
- [x] Grow equal-split: multiple grow siblings share available height

### Horizontal Layout Frame (`layout_type="hbox"`)
- [x] Template (1–8)
- [x] Children stack left-to-right with `.pack(side=left)`
- [x] `layout_spacing` + `stretch` work the same as vbox on the other axis
- [x] Grow equal-split: siblings share width

### Grid Layout Frame (`layout_type="grid"`)
- [x] Template (1–8)
- [x] `grid_rows` × `grid_cols` dimensions editable; cells drawn via dashed overlay
- [x] Child `grid_row` / `grid_column` / `grid_sticky`
- [x] Drag-to-cell snap + palette drop respects cell under cursor
- [x] Auto-grow when all cells full; Grid → place swap preserves distribution

### CTkScrollableFrame (partial — nested children path)
- [x] Template 1, 2, 6, 7 (drop, edit, save/load, export)
- [x] Scrollbar orientation + colours
- [!] Drop-children-inside doesn't work — CTk renders children on a hidden inner canvas not accessible via master= assignment; deferred to roadmap

### CTkTabview (partial — tabs yes, per-tab children no)
- [x] Template 1, 2, 6, 7
- [x] `tab_names` multi-line list → `.add("name")` per tab in export
- [x] Rename / reorder tabs (via SegmentValuesDialog — reorder by delete+re-add)
- [!] Dropping widgets into a specific tab not supported — palette drop goes to root canvas; deferred to roadmap

---

## Display

### Image (builder composite)
- [x] Template (1–8)
- [x] `image` file picker + clear
- [x] `preserve_aspect` → height auto-recomputes from width
- [x] `image_color` tint → runtime PIL `_tint_image` helper
- [x] `fg_color` background (transparent by default)
- [x] Missing image path → placeholder `#444444` fill, no crash
- [x] Exports as `CTkLabel(text="", image=CTkImage(...))`

---

## Widget-specific surprises

- [x] CTkRadioButton shared `group` — multi-radio coordination via `tk.StringVar`
- [x] CTkSlider orientation change — width/height swap + widget recreate
- [x] CTkProgressBar mode — determinate vs indeterminate (builder shows static only)
- [x] CTkComboBox editable — user-typed value persisted on export
- [x] Image missing file — placeholder instead of crash
- [x] CTkButton `command=` — exporter omits or emits placeholder
- [x] CTkLabel `image` + no `text` — compound gracefully ignored
- [x] Font changes across widgets — each widget's `CTkFont(...)` is independent

## Refactor candidates

- [ ] 16 descriptor files — scan for repeated property blocks (Geometry, Main Colors, Border subgroup)
- [ ] Shared schema fragments via module-level constants? (e.g. `POSITION_PAIR`, `SIZE_PAIR`, `BORDER_SUBGROUP`)
- [ ] `_NODE_ONLY_KEYS` vs `LAYOUT_NODE_ONLY_KEYS` — overlap check
- [ ] `transform_properties` boilerplate — central helper for "strip node-only + layout keys"

## Optimize candidates

- [ ] Cold widget creation cost (descriptor → CTk constructor)
- [ ] `CTkFont(...)` cache per (family, size, style) — rebuilt on every prop change?
- [ ] `CTkImage` / `_tint_image` cache per (path, hex, size)?
- [ ] CTkImage export redundancy: `light_image=Image.open(path), dark_image=Image.open(path)` opens the same file twice. Open once, assign to a local var, pass twice: `_img = Image.open(path); ctk.CTkImage(light_image=_img, dark_image=_img, ...)`.
- [ ] `_apply_grow_equal_split` iterates every grow sibling per re-apply — profile for 10+ children

## Findings

- **[CTkEntry]** `placeholder_text` invisible on canvas — `apply_state` called `widget.delete(0,"end")` unconditionally, clearing CTk's internal placeholder; fixed by gating on `_placeholder_text_active` flag. Fixed v0.0.15.13.
- **[CTkEntry]** disabled state showed placeholder in editor but blank in preview — editor was not checking `state == "disabled"` before rendering placeholder; fixed. Fixed v0.0.15.13.
- **[CTkEntry]** widget kept keyboard focus after clicking elsewhere on canvas — `_setup_text_clipboard` now binds `<Button-1>` globally; non-text clicks call `root.after(1, root.focus_set)` to trigger CTk's `_entry_focus_out`. Fixed v0.0.15.20.
- **[CTkSegmentedButton]** segments became unresponsive after changing any property — CTk's `configure(values=...)` silently rebuilds all inner button widgets, invalidating old event bindings; workspace `_bind_widget_events` made idempotent via `_ws_bound_nid` flag, called after every configure. Fixed v0.0.15.18.
- **[CTkButton]** `text_hover_color` change reset CTk's hover background state — `widget.configure(text_color=...)` triggers `_draw()` which resets hover; fixed by writing directly to `widget._text_label.configure(fg=colour)`. Fixed v0.0.15.14.
- **[CTkComboBox]** crash on palette drop — `dropdown_width` (removed kwarg) was being passed to `CTkComboBox` constructor; added to `_NODE_ONLY_KEYS` for cleanup from old project files. Fixed v0.0.15.24.
- **[Image]** `image_color` ✕ button stayed active even when color was `None` — `_is_cleared` treated `None` and `"transparent"` as distinct; fixed by adding both to `_CLEARED_SENTINELS` frozenset. Fixed v0.0.15.24.
- **[CTkScrollableFrame]** children cannot be dropped inside — CTk renders the scrollable content on an internal canvas widget that is not exposed as a standard Tk master; container behavior deferred to roadmap.
- **[CTkTabview]** widgets cannot be dropped into individual tabs — tab content frames are internal CTk objects not exposed via the builder tree; deferred to roadmap.
- **[Widget Inspector]** `ttk.Style.theme_use("clam")` wrecked Object Tree + Properties panel styling — removed; named style configure used instead. Fixed v0.0.15.22.
