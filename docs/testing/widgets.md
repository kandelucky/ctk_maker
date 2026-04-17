# Area 7 — Widgets (14 + 1)

Per-widget sanity sweep. For each, run the **same checklist**: drop, edit every property, save/load round-trip, export + run.

## Per-widget checklist (template)

For each widget in the list below, verify:

- [ ] Palette drop → widget visible with descriptor defaults
- [ ] Every property in the schema edits live (no crash, canvas updates)
- [ ] `disabled_when` / `hidden_when` lambdas fire correctly on their triggers
- [ ] `transform_properties` produces the right CTk kwargs
- [ ] `apply_state` (if any) reflects on canvas widget
- [ ] Save project → load → widget state identical
- [ ] Export → runnable `.py` → visual match with canvas
- [ ] Undo / redo every property change

## Widgets

### Simple
- [ ] `CTkButton` — text, command (exported placeholder), fg_color, hover_color, image, compound, anchor
- [ ] `CTkLabel` — text, font, text_color, anchor, image, compound
- [ ] `CTkEntry` — placeholder, text, text_color, password char, justify
- [ ] `CTkTextbox` — multiline text, wrap, font, activate_scrollbars

### Selection
- [ ] `CTkCheckBox` — text, checkbox_width/height, state
- [ ] `CTkRadioButton` — text, group (shared var), value, selection state
- [ ] `CTkSwitch` — text, state
- [ ] `CTkSegmentedButton` — values list, selected_value, dynamic options

### Input
- [ ] `CTkSlider` — from_, to, number_of_steps, orientation (init-only recreate trigger)
- [ ] `CTkProgressBar` — progress value, mode (determinate/indeterminate), orientation
- [ ] `CTkComboBox` — values list, selected, editable
- [ ] `CTkOptionMenu` — values list, selected
- [ ] `CTkEntry` already covered above

### Containers (partial — see layout.md for in-depth)
- [ ] `CTkFrame` — layout_type, spacing, border, fg_color, nested children
- [ ] `CTkScrollableFrame` — **KNOWN: nested-children path partial**, verify what works, file remaining gaps
- [ ] `CTkTabview` — **KNOWN: tabs yes, children-per-tab no**, verify current state

### Display
- [ ] `Image` (builder composite) — file path, preserve_aspect, tint, default placeholder on empty path

## Widget-specific surprises to verify

- [ ] `CTkRadioButton` shared `group` — multiple buttons with same group coordinate
- [ ] `CTkSlider` orientation change — recreate_trigger fires, w/h swap
- [ ] `CTkProgressBar` mode change — handles determinate/indeterminate switch
- [ ] `CTkComboBox` editable mode — user-typed value preserved on export
- [ ] `Image` missing file — shows placeholder, doesn't crash
- [ ] `CTkButton` `command` property — exporter emits `command=None` or omits?
- [ ] `CTkLabel` with `image=` only (no text) — compound ignored gracefully
- [ ] Font changes across multiple widgets — global font state isolated?

## Refactor candidates

- [ ] 15 descriptor files — scan for duplicate patterns (geometry group, main colors group, border subgroup)
- [ ] Mixin or base-class extension for common schema blocks
- [ ] `_NODE_ONLY_KEYS` per descriptor — overlap with `LAYOUT_NODE_ONLY_KEYS`?
- [ ] `transform_properties` boilerplate — central helper for the layout-key strip?
- [ ] `recreate_triggers` + `derived_triggers` — few widgets use them; API clear?

## Optimize candidates

- [ ] Widget cold creation (descriptor → CTk constructor) — dominated by CTk or our code?
- [ ] Font construction (`CTkFont(...)`) on every property change — cache per family+size?
- [ ] Image loading (`CTkImage(...)`) — cached or reloaded on every redraw?

## Findings

<!-- per-widget bugs here; prefix with widget name, e.g.:
     - **[CTkSlider]** orientation flip clears current value
-->
