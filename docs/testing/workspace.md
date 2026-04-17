# Area 1 — Workspace core

Canvas drag / drop / resize / select / keyboard / delete — the core interactions every user hits first.

## Test

### Palette → Canvas drop
- [x] Drop each widget type (button, label, frame, entry, checkbox, radio, combo, option, slider, progress, segmented, switch, textbox, image) onto an empty Main Window
- [x] Drop into a place Frame — lands at cursor position
- [x] Drop into a vbox / hbox Frame — appends at end
- [x] Drop into a grid Frame — lands at cursor cell
- [x] Drop onto canvas outside any document — rejected with red ghost feedback *(fixed this session, see findings)*
- [x] Click (no drag) in palette → adds widget with cascade offset *(enhanced this session)*

### Move
- [x] Drag place widget — live preview + commit on release
- [x] Drag pack child — skips phantom x/y writes (Object Tree shouldn't flicker), ghost follows cursor
- [x] Drag grid child — cell outline appears, snaps to cell under cursor, selection handles follow
- [x] Drag widget outside any form — rejected (snap back)
- [x] Drag from container to "wrong" place — extracts to source form at cursor position
- [x] Drag into nested Frame — reparents (top-level widgets only; container children extract instead)

### Resize
- [x] 8 handles (N/S/E/W + NE/NW/SE/SW) all work
- [x] Min size enforced (can't resize below widget's min dimensions)
- [x] Resize container with children — children re-layout (grid), stay place-anchored (place), pack re-flows
- [x] Resize during drag-scrub on W/H property — single undo entry on release

### Arrow-key nudge
- [x] Selected widget → arrow = 1px, Shift+arrow = 10px
- [x] Rapid bursts coalesce into single undo step (≤0.6s window)
- [x] Nudge respects locked widgets (no-op)

### Select
- [ ] Click widget → selection highlight + property panel updates
- [ ] Click empty canvas → deselects
- [ ] Click chrome of non-active document → switches active doc + deselects
- [ ] Multi-select via Object Tree Ctrl+click — workspace mirrors highlight
- [ ] Locked widget: selectable but drag/resize/delete rejected

### Delete
- [ ] Delete key on selected → removes widget + subtree
- [ ] Right-click → Delete menu entry works
- [ ] Delete multi-selection
- [ ] Undo restores entire subtree + children preserve IDs

### Zoom + pan
- [ ] Status-bar slider / +/- / reset button
- [ ] `Ctrl + mouse wheel` zooms toward cursor
- [ ] Hand tool (H) → canvas drag pans
- [ ] Middle-mouse pan without tool change
- [ ] Widgets stay visually correct at 10% / 100% / 500%

### Edge cases
- [ ] 100+ widget project stays responsive during drag
- [ ] Rapid palette drops in succession (no lost widgets)
- [ ] Drag a widget, then release over Object Tree / Properties panel — rejected cleanly

## Refactor candidates

- [ ] `core.py` (998 lines) — `_on_property_changed` routing switch is long, could extract into handler map
- [ ] `drag.py` size audit — is the `_maybe_grid_drop` / `_maybe_reparent_dragged` split clean or overlapping?
- [ ] `_build_canvas` assembles 5+ sidecar managers — could reduce to a single `_wire_managers` helper
- [ ] `WorkspaceControls` vs `ChromeManager` vs `ZoomController` — boundaries clear or blurry?
- [ ] Re-export block (`_child_manager_kwargs`, `_forget_current_manager` as `# noqa: F401`) — still needed by tests?

## Optimize candidates

- [ ] Selection redraw fires on every motion event during drag — debounce to next-frame
- [ ] `_schedule_selection_redraw` already exists — check if all call sites use it vs direct `selection.draw()`
- [ ] Zoom rerender: `apply_to_widget` runs per-widget; could batch per document
- [ ] Canvas `create_window` + `widget.configure(width, height)` — measure which dominates during palette drop
- [ ] Drag with 50+ siblings — profile motion handler

## Findings

- **[WS-1]** Drop outside any document silently landed widget on active form
  *Steps:* multi-document project, drag palette widget to empty canvas area between forms, release
  *Expected:* drop rejected
  *Observed:* widget added to active form at unexpected coords
  *Fix:* `_on_palette_drop` now returns early when cursor is outside every document
  *Also added:* palette drag ghost tints red when cursor is outside valid target (visual feedback before release)

- **[WS-2]** Palette click (no drag) stacked widgets at identical default x/y
  *Steps:* click same palette entry multiple times
  *Expected:* widgets visually distinct
  *Observed:* each click added a widget exactly on top of the previous one
  *Fix:* cascade offset — `_add_widget_default` bumps x/y by +20/+20 until an unoccupied slot among root widgets is found

- **[WS-3]** Drag over empty canvas persisted the out-of-bounds x/y
  *Steps:* drag a place widget past the form boundary, release on empty canvas
  *Expected:* widget snaps back to its pre-drag position
  *Observed:* widget stayed at the out-of-bounds x/y
  *Fix:* `on_release` snaps x/y back to drag start when cursor is over no container AND no document

- **[WS-4]** Container children could reparent directly between unrelated containers / documents
  *Steps:* drag a widget from vbox Frame A to grid Frame B (or to another Dialog)
  *Expected:* move should be explicit — one drag to extract, another to place
  *Observed:* widget silently hopped to the new container with coords reset, hard to reason about
  *Fix:* `_maybe_extract_from_container` — container children always extract to the source document's root at the cursor position (falls back to cascade default when released outside the source form)

- **[WS-5]** Selecting a widget in a non-active document didn't activate that document
  *Steps:* have two forms open, work in form B, click a widget inside form A's chrome
  *Expected:* form A becomes active so drag coords compute against its offset
  *Observed:* form B stayed active, drags landed at the wrong offset
  *Fix:* `on_press` calls `set_active_document` before `select_widget` when the click's owning doc isn't current

- **[WS-6]** Pack / grid children drags had no visible feedback
  *Steps:* drag a Button inside a vbox / hbox / grid Frame
  *Expected:* something follows the cursor so you know the gesture is live
  *Observed:* widget stayed put until release (place children follow naturally via x/y writes)
  *Fix:* small `tk.Toplevel` label (same pattern as palette drag) tracks the cursor during drag and tears down on release

- **[WS-7]** Fully-covered containers were unreachable from the canvas
  *Steps:* drop a Frame with children that fill every pixel, try to select the Frame by clicking on it
  *Expected:* some path to select the container without Object Tree
  *Observed:* clicks went straight to the deepest child, container never selectable
  *Fix:* Unity-style drill-down — first click on a hierarchy selects the outermost ancestor; subsequent clicks descend. Shared-scope shortcut: sibling clicks inside an already-entered container select the sibling directly

- **[WS-8]** Grid cell move left selection handles at the old cell
  *Steps:* drag a grid child from cell (0,0) to cell (1,1)
  *Expected:* handles follow to (1,1)
  *Observed:* widget jumped but handles stayed at (0,0) until the next interaction
  *Fix:* `after_idle(selection.draw)` at the end of `on_release` — grid / pack moves don't mutate x/y so the property-change redraw path fired before tk settled the geometry
