# Area 3 — Properties panel

Every editor type, drag-scrub, conditional rows (`disabled_when` / `hidden_when`), grouped sections.

## Test

### Editor types
- [x] **number** — typing, min/max clamp, dynamic max (e.g. corner_radius)
- [x] **color** — picker dialog, swatch preview
- [x] **color clear ✕** — clearable props commit clear_value on ✕ click; dimmed when already cleared (v0.0.15.9)
- [x] **color "transparent" → "none" display** — value cell shows "none" when stored value is "transparent" (v0.0.15.9)
- [x] **number ±1 spinner** — click step, hold auto-repeat, one undo per hold, min/max clamp (v0.0.15.7)
- [x] **boolean** — checkbox toggle
- [x] **string** — live commit on Enter / blur
- [x] **multiline** — textarea with newline preservation
- [x] **enum** — dropdown with icons (layout_type, stretch, grid_sticky, anchor)
- [x] **anchor** — 3×3 grid click-to-pick
- [x] **compound** — top / left / right / bottom
- [x] **image** — browse / clear, file dialog
- [!] **orientation** — CTkSlider orientation change broken (known bug); CTkProgressBar untested
- [ ] **font** — family / size / bold / italic / underline / strike / preview *(pending — dedicated font editor not built yet)*

### Drag-scrub
- [x] Drag on number label → value changes live
- [x] Alt = fine scrub (1px per unit)
- [x] Commit as single undo entry on release
- [x] Drag-scrub on W/H → widget resizes live
- [!] Escape mid-drag cancels back to original value — not implemented

### Conditional rows
- [x] `disabled_when` — dependent row dims (e.g. border_width when border_enabled=false)
- [x] `hidden_when` — dependent row vanishes (e.g. grid_rows on non-grid Frame)
- [x] Toggle condition → rows re-appear / re-enable in-place, no rebuild flicker
- [x] `layout_type` change rebuilds panel cleanly (Layout rows differ per manager)

### Grouped sections
- [x] Group headers render with section titles
- [x] Subgroups nested correctly (e.g. Character / Paragraph under Text)
- [x] Paired rows side-by-side (X+Y, W+H, Size+BestFit)
- [x] Padding / spacing consistent across widgets

### Selection / edit flow
- [x] Click widget → panel loads its schema in <100ms
- [x] Click different widget → panel rebuilds cleanly, no stale rows
- [x] Multi-select from Object Tree → panel shows common props? or clears?
- [x] Rename inline from Name field → Object Tree updates live
- [x] Property change → canvas updates immediately
- [x] Property change on hidden widget → model updates even though canvas skips

### Edge cases
- [x] Very long property list (40+ rows) — scroll works
- [x] Type invalid value (negative width, malformed hex) — rejects + restores
- [x] Eyedropper across monitors — picks correct pixel *(verify — feature lives in external `ctk-tint-color-picker` library)*
- [ ] Font preview with missing font — falls back gracefully *(pending font editor)*

## Refactor candidates

- [ ] `panel.py` size audit — 1272 lines in one file; schema walker, editor dispatch, chrome builder, commit path, pickers all live together. Candidate split: `panel_schema.py` (populate_schema + pair/group traversal) and `panel_commit.py` (commit_prop + editor lifecycle)
- [x] ~~Editor registry — dispatch is if-chain?~~ — already a dict lookup in `editors/__init__.py` (`_EDITORS[ptype]`). Outdated note.
- [ ] `_populate_schema` filtering — 70-line while-loop does group / subgroup / pair state-tracking + hidden filtering inline. Could split the pair-collect and group-transition logic into helper generators.
- [ ] `_is_hidden` / `_compute_disabled_states` API asymmetry — one returns `bool` per-prop, the other returns a dict for the whole schema. Unify: both compute per-prop, caller iterates.
- [x] ~~Overlay management dedupe~~ — `OverlayRegistry` + named placers already unify the chrome. Done.

## Optimize candidates

- [ ] `disabled_when` / `hidden_when` re-evaluates all lambdas on every keystroke — dep-map via `TrackingDict` to make it O(1) per change
- [ ] Full panel rebuild on `layout_type` change — could do surgical row add/remove
- [ ] Treeview row recreation during rebuild — profile flash / reflow

## Findings

- **[P3-1]** Drag-scrub `<->` cursor vanished after release when the mouse was still over the number-row label
  *Root cause:* `_on_release` left `_cursor_mode` at `"drag"`; next `<Motion>` short-circuited before re-applying `<->`.
  *Fix:* reset `_cursor_mode = ""` on release (v0.0.15.9).

- **[P3-2]** Object Tree right-click context menu rendered with embossed / double-shadowed text on Windows
  *Root cause:* (a) menu parented to `CTkFrame` instead of `winfo_toplevel()`; (b) `state="disabled"` triggers Windows native emboss regardless of flat style.
  *Fix:* reparent to `winfo_toplevel()`; replace `state="disabled"` with `foreground` colour swap (v0.0.15.9).

- **[P3-3]** Number editor had no bounds — x=9999 moved widget outside window
  *Fix:* `_clamp_to_container_bounds` in `_commit_prop` (v0.0.15.10).

- **[P3-4]** DPI mismatch — canvas document rectangle smaller than CTk widgets on 125% DPI display
  *Fix:* `canvas_scale = user_zoom × dpi_factor` in `zoom_controller`; all canvas drawing uses `canvas_scale` (v0.0.15.10).
