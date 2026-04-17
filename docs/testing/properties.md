# Area 3 — Properties panel

Every editor type, drag-scrub, conditional rows (`disabled_when` / `hidden_when`), grouped sections.

## Test

### Editor types
- [ ] **number** — typing, min/max clamp, dynamic max (e.g. corner_radius)
- [ ] **color** — type hex, picker dialog, eyedropper, swatch preview
- [ ] **boolean** — checkbox toggle
- [ ] **string** — live commit on Enter / blur
- [ ] **multiline** — textarea with newline preservation
- [ ] **enum** — dropdown with icons (layout_type, stretch, grid_sticky, anchor)
- [ ] **anchor** — 3×3 grid click-to-pick
- [ ] **compound** — top / left / right / bottom
- [ ] **image** — browse / clear, file dialog
- [ ] **orientation** — horizontal / vertical (slider, progress)
- [ ] **font** — family / size / bold / italic / underline / strike / preview

### Drag-scrub
- [ ] Drag on number label → value changes live
- [ ] Alt = fine scrub (1px per unit)
- [ ] Commit as single undo entry on release
- [ ] Drag-scrub on W/H → widget resizes live
- [ ] Escape mid-drag cancels back to original value

### Conditional rows
- [ ] `disabled_when` — dependent row dims (e.g. border_width when border_enabled=false)
- [ ] `hidden_when` — dependent row vanishes (e.g. grid_rows on non-grid Frame)
- [ ] Toggle condition → rows re-appear / re-enable in-place, no rebuild flicker
- [ ] `layout_type` change rebuilds panel cleanly (Layout rows differ per manager)

### Grouped sections
- [ ] Group headers render with section titles
- [ ] Subgroups nested correctly (e.g. Character / Paragraph under Text)
- [ ] Paired rows side-by-side (X+Y, W+H, Size+BestFit)
- [ ] Padding / spacing consistent across widgets

### Selection / edit flow
- [ ] Click widget → panel loads its schema in <100ms
- [ ] Click different widget → panel rebuilds cleanly, no stale rows
- [ ] Multi-select from Object Tree → panel shows common props? or clears?
- [ ] Rename inline from Name field → Object Tree updates live
- [ ] Property change → canvas updates immediately
- [ ] Property change on hidden widget → model updates even though canvas skips

### Edge cases
- [ ] Very long property list (40+ rows) — scroll works
- [ ] Type invalid value (negative width, malformed hex) — rejects + restores
- [ ] Eyedropper across monitors — picks correct pixel
- [ ] Font preview with missing font — falls back gracefully

## Refactor candidates

- [ ] `panel.py` size audit — schema walker + editor dispatch in one file?
- [ ] Editor registry — each editor is a class, but dispatch is if-chain?
- [ ] `_populate_schema` filtering — conditional logic bundled or split?
- [ ] `_is_disabled` / `_is_hidden` helpers — consistent API?
- [ ] Overlay management (color / image / enum persistent chrome) — deduplicate

## Optimize candidates

- [ ] `disabled_when` / `hidden_when` re-evaluates all lambdas on every keystroke — dep-map via `TrackingDict` to make it O(1) per change
- [ ] Full panel rebuild on `layout_type` change — could do surgical row add/remove
- [ ] Treeview row recreation during rebuild — profile flash / reflow

## Findings

<!-- log properties-panel bugs here -->
