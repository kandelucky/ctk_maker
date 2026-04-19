# Area 2 — Layout managers

`place` / `vbox` / `hbox` / `grid` on containers + every child-layout knob (`stretch`, `grid_row/col/sticky`, `layout_spacing`).

## Test

### Manager swap
- [x] Frame defaults to `place` — children use absolute x/y
- [x] Swap to `vbox` — children stack top-down via real `pack()`
- [x] Swap to `hbox` — children row left-to-right
- [x] Swap to `grid` — children land in cells, default 2×2 *(fixed this session: `_redistribute_stacked_grid_children` in core.py distributes existing children across free cells on layout_type swap; grid auto-grows if N > rows×cols)*
- [x] Swap back to `place` — x/y restored from stored values (or 0 if reset)
- [x] Undo after swap — layout + children both revert

### vbox / hbox
- [x] `layout_spacing` = 0 — children touch
- [x] Increase spacing — gap applies evenly
- [x] `stretch: fixed` — natural size
- [x] `stretch: fill` — cross-axis fills
- [x] `stretch: grow` — both axes fill + expand
- [x] Mixed stretch siblings — grow children absorb extra space, fixed stay put
- [x] Reorder children via Object Tree — visual order matches model after reorder

### Grid
- [x] Pin `grid_rows` / `grid_cols` — cells re-size
- [x] Default 2×2 — first 4 drops auto-fill cells row-major
- [x] 5th drop beyond rows×cols — auto-wraps (reuses cell 0,0)
- [x] `grid_sticky = ""` — child centered in cell
- [x] `nsew` — fills cell
- [x] `ns` / `ew` — axis fill
- [x] `n` / `s` / `e` / `w` — edge-aligned
- [x] Resize container — grid children re-center / re-fill
- [x] Change `grid_rows` / `grid_cols` — existing children stay in their cells, wrap-around honored
- [x] Auto-grow on full grid — undo reverts grid dims + widget *(fixed this session — L2-2)*
- [x] Duplicate / paste into full grid — undo reverts grid dims + widgets *(fixed this session — L2-2)*

### Drag-to-cell UX
- [x] Drag grid child — blue outline on target cell during motion
- [x] Release on empty cell — lands there
- [x] Release on occupied cell — redirected to next free cell (no overlap; grows grid if full)
- [x] Drag outside parent — reparents, x/y resets to 0 for non-place parent
- [x] Palette drop onto grid — lands at cursor cell

### Reparent between layouts
- [x] place → vbox — via Copy + Paste as child; x/y zeroed, `stretch=grow` applied
- [x] vbox → grid — via Copy + Paste as child; stretch dropped, `grid_sticky=nsew` applied
- [x] grid → place — via Copy + Paste as child; grid_row/column dropped
- [x] Cross-document reparent — Object Tree Paste as child into a Dialog's container; layout kwargs refresh

> Note: direct drag from one container to another is blocked by design (WS-33); Object Tree's Copy + Paste as child is the supported reparent path between containers.

### Nested containers
- [x] Frame in Frame in Frame (3+ levels) — each level's `layout_type` independent
- [x] Inner Frame resize respects outer Frame's layout
- [x] Delete middle Frame — children cascade-delete
- [x] Undo cascade-delete — entire subtree rebuilds with IDs preserved *(fixed this session — L2-4)*

## Refactor candidates

- [x] `_grid_child_place_kwargs` sticky logic — extracted `_sticky_axis(has_lo, has_hi, avail_pos, avail_size, child_size)` helper; same table for both axes, called twice
- [x] `apply_child_manager` split into `_apply_pack_manager` / `_apply_grid_manager` / `_apply_place_manager` (+ `_apply_grow_equal_split`); top-level body is now a 25-line dispatcher instead of a 150-line if/elif tower
- [x] Composite widget size handling — `_composite_configure(widget, lw, lh, zoom)` and `_composite_place_size(lw, lh, zoom)` helpers; 4 inline call sites in `apply_child_manager` + `_place_nested` + `_place_top_level` collapse to one-liners

## Optimize candidates

- [ ] `rearrange_container_children` forget-all-repack — profile the two-pass cost on large containers
- [ ] Grid children use place + configure separately — could batch via `update_idletasks` deferred
- [ ] Layout swap triggers full redraw — minimal re-layout possible?
- [ ] Grid cell calculation uses float division then int cast — measurable or negligible?

## Findings

- **[L2-1]** Selection chrome dropped behind widgets after any widget delete
  *Steps:* create Frame + 3 Buttons → delete the Frame → create 3 new top-level Buttons → move Button1 on top of Button2 → click Button1 → selection rectangle appears BELOW Button2 instead of above. Same for handles and multi-select outlines. Affected every selection after the first widget delete in the session.
  *Root cause:* the selection-chrome frame pool (introduced in v0.0.15.6) lifted each chrome `tk.Frame` only at allocation time. Tk canvas embedded widgets have TWO stacking systems — canvas item z-order (`canvas.tag_raise`) AND widget sibling order (`frame.lift()`). The pool preserved the first via `tag_raise("selection_chrome")` but dropped the second because allocation-time `frame.lift()` didn't survive a subsequent widget add (which bumps tk sibling order).
  *Fix:* `_position_edges` / `_position_handles` / `_position_outline` call `frame.lift()` on every show. Matches the pre-pool behaviour where `_make_edge_frame` re-created the frame each draw (which had `lift()` as a side effect).

- **[L2-2]** Grid auto-grow not tracked in undo history
  *Steps:* Grid Frame 2×2 (default) → drop 4 Buttons (fills grid) → drop 5th Button → grid auto-grows to 3×2 → Ctrl+Z → widget removed but grid stays 3×2 (wrong). Same bug for duplicate / copy-paste into a full grid.
  *Root cause:* `_auto_assign_grid_cell` in `widget_lifecycle.py`, `_maybe_grid_drop` in `drag.py`, and `BulkAddCommand` (duplicate / paste) each applied grid dim growth via direct `project.update_property(parent_id, "grid_rows", N)` calls outside the command system. The main `AddWidgetCommand` / `ReparentCommand` / `BulkAddCommand` captured the widget but not the parent's dim change, leaving orphaned state that undo couldn't revert.
  *Fix:* Extended `AddWidgetCommand`, `ReparentCommand`, `MultiChangePropertyCommand`, and `BulkAddCommand` with an optional `parent_dim_changes = (container_id, {prop: (before, after)})` field. `_auto_assign_grid_cell` stashes the change on the node as `_pending_parent_dim_changes`; each call site harvests the stash and threads it into the command. Undo reverts dims after the widget unwind; redo re-applies dims (where the event handler doesn't naturally re-grow). `build_bulk_add_entries` expanded to 5-tuples so duplicate / paste capture the stash too.

- **[L2-3]** `self.drag_controller._grid_cell_at` dead call in `_on_palette_drop`
  *Steps:* Palette drag-drop onto a grid Frame → `AttributeError: '_grid_cell_at'` (method doesn't exist on `DragController`). Latent bug from a rename during the grid-drop indicator extraction — only surfaced while tracing L2-2.
  *Fix:* Swapped to `self.drag_controller._grid_indicator.cell_at(...)` — same semantics (cursor → clamped row/col) and the real method that other drag paths use.

- **[L2-4]** Cascade-delete undo restored only the root, lost every descendant
  *Steps:* Frame with N children → Delete the Frame → Ctrl+Z → Frame reappeared empty; every child stayed missing. Same for Layout / Grid Frames + their children, and any nested 3+ level subtree.
  *Root cause:* `_restore_widget` in `commands.py` (shared by Add.redo / Delete.undo / DeleteMultiple.undo / BulkAdd.redo) called `project.add_widget(node)` once for the root snapshot. `WidgetNode.from_dict` rebuilds the full tree, but `project.add_widget` only fires `widget_added` for the root — descendants stayed in the model with no tk widget view ever created. Workspace's `on_widget_added` handler never saw them, so the canvas showed an empty Frame even though the data was there.
  *Fix:* New `_add_subtree_recursive` helper detaches children, adds the root, then recurses for each descendant — same pattern `project_loader._add_recursive` and `project._paste_recursive` already use. Routed `_restore_widget` through it. Add / Delete / DeleteMultiple / BulkAdd all benefit; nested undo now restores the full hierarchy.

- **[L2-5]** Container duplicate dropped every child
  *Steps:* Frame with N buttons → right-click → Duplicate → clone landed empty. Same for Grid / Layout containers.
  *Root cause:* `Project.duplicate_widget` cloned only the root: `WidgetNode(widget_type=node.widget_type, properties=...)` and called `add_widget(clone, parent_id=...)`. Children were never read from the source.
  *Fix:* Switched to the same `_clone_with_fresh_ids(node.to_dict())` deep-clone that paste uses, then `_paste_recursive(clone, parent_id)` so every descendant gets fresh IDs + its own `widget_added` event. Optional `force_top_level` arg added for the Object Tree's "Duplicate in window" variant.

- **[L2-6]** Layout-in-layout nesting blocked on drag but allowed on paste
  *Steps:* Vertical Layout in clipboard → right-click on a Grid Frame → Paste → the Layout container nested inside the Grid (rendering broke the same way WS-33 originally did). Drag-into-layout was already blocked but copy-paste sneaked through.
  *Fix:* `Project.paste_from_clipboard` now checks the target parent: if it's a layout container AND any clipboard entry is itself a layout container, the paste falls through to top-level instead of nesting. Mirrors the drag/drop guard so both input paths agree.

- **[L2-7]** Right-click on a container jumped to the deepest widget instead of drilling
  *Steps:* Frame > Frame > Button → left-click drilled outer→inner→leaf as expected; right-click jumped straight to the Button regardless of current selection scope. Context menu acted on a different layer than the user had drilled to.
  *Fix:* `_on_widget_right_click` now routes the clicked nid through `drag_controller._resolve_click_target` — the same drill-down resolver left-click uses. Right-click on a child first picks the outermost ancestor; subsequent right-clicks descend, matching left-click behaviour.
