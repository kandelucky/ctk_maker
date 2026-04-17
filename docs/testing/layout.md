# Area 2 — Layout managers

`place` / `vbox` / `hbox` / `grid` on containers + every child-layout knob (`stretch`, `grid_row/col/sticky`, `layout_spacing`).

## Test

### Manager swap
- [ ] Frame defaults to `place` — children use absolute x/y
- [ ] Swap to `vbox` — children stack top-down via real `pack()`
- [ ] Swap to `hbox` — children row left-to-right
- [ ] Swap to `grid` — children land in cells, default 2×2
- [ ] Swap back to `place` — x/y restored from stored values (or 0 if reset)
- [ ] Undo after swap — layout + children both revert

### vbox / hbox
- [ ] `layout_spacing` = 0 — children touch
- [ ] Increase spacing — gap applies evenly
- [ ] `stretch: fixed` — natural size
- [ ] `stretch: fill` — cross-axis fills
- [ ] `stretch: grow` — both axes fill + expand
- [ ] Mixed stretch siblings — grow children absorb extra space, fixed stay put
- [ ] Reorder children via Object Tree — visual order matches model after reorder

### Grid
- [ ] Pin `grid_rows` / `grid_cols` — cells re-size
- [ ] Default 2×2 — first 4 drops auto-fill cells row-major
- [ ] 5th drop beyond rows×cols — auto-wraps (reuses cell 0,0)
- [ ] `grid_sticky = ""` — child centered in cell
- [ ] `nsew` — fills cell
- [ ] `ns` / `ew` — axis fill
- [ ] `n` / `s` / `e` / `w` — edge-aligned
- [ ] Resize container — grid children re-center / re-fill
- [ ] Change `grid_rows` / `grid_cols` — existing children stay in their cells, wrap-around honored

### Drag-to-cell UX
- [ ] Drag grid child — blue outline on target cell during motion
- [ ] Release on empty cell — lands there
- [ ] Release on occupied cell — swaps / overlaps (document behavior)
- [ ] Drag outside parent — reparents, x/y resets to 0 for non-place parent
- [ ] Palette drop onto grid — lands at cursor cell

### Reparent between layouts
- [ ] place → vbox — x/y zeroed, child appended
- [ ] vbox → grid — stretch props dropped, lands at next free cell
- [ ] grid → place — grid_row/column dropped, x/y restored
- [ ] Cross-document reparent — layout kwargs refresh for new parent

### Nested containers
- [ ] Frame in Frame in Frame (3+ levels) — each level's `layout_type` independent
- [ ] Inner Frame resize respects outer Frame's layout
- [ ] Delete middle Frame — children cascade-delete
- [ ] Undo cascade-delete — entire subtree rebuilds with IDs preserved

## Refactor candidates

- [ ] `_grid_child_place_kwargs` sticky logic — 8 combinations with repetitive if-else; could table-drive
- [ ] `layout_overlay._stretch_to_pack_kwargs` + pack kwargs in `_child_manager_kwargs` — split or consolidate?
- [ ] `apply_child_manager` has three large branches (pack / grid / place) — extract per-manager sub-methods?
- [ ] Composite widget size handling duplicated across `on_widget_added` + `apply_child_manager`
- [ ] `_forget_current_manager` + re-apply pattern — could be a context manager

## Optimize candidates

- [ ] `rearrange_container_children` forget-all-repack — profile the two-pass cost on large containers
- [ ] Grid children use place + configure separately — could batch via `update_idletasks` deferred
- [ ] Layout swap triggers full redraw — minimal re-layout possible?
- [ ] Grid cell calculation uses float division then int cast — measurable or negligible?

## Findings

<!-- log layout-specific bugs here -->
