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
- [x] Click widget → selection highlight + property panel updates
- [x] Click empty canvas → deselects
- [x] Click chrome of non-active document → switches active doc + deselects
- [x] Ctrl+click toggles widget in / out of the selection set
- [x] Group drag — dragging any selected widget moves the whole group by the same delta
- [x] Multi-select via Object Tree Ctrl+click — workspace mirrors highlight
- [x] Locked widget: selectable but drag/resize/delete rejected (dialog, not silent)

### Delete
- [x] Delete key on selected → removes widget + subtree
- [x] Right-click → Delete menu entry works
- [x] Delete multi-selection
- [x] Undo restores entire subtree + children preserve IDs

### Zoom + pan
- [x] Status-bar slider / +/- / reset button
- [x] `Ctrl + mouse wheel` zooms toward cursor
- [x] Hand tool (H) → canvas drag pans
- [x] Middle-mouse pan without tool change
- [x] Widgets stay visually correct at 10% / 100% / 500%

### Edge cases
- [x] 100+ widget project stays responsive during drag
- [x] Rapid palette drops in succession (no lost widgets)
- [x] Drag a widget, then release over Object Tree / Properties panel — rejected cleanly

## Refactor + Optimize — files in scope

Every file touched during Area 1 testing. Refactor / optimize passes
walk this list top-to-bottom; decide what each needs when we get to it.

- [x] `app/core/project.py` — refactor: walker unify, `_resolve_target_document`, `_reorder_to` dedup. Optimize (ID cache) **deferred** — 160-widget benefit too small vs. complexity.
- [x] `app/core/commands.py` — refactor: `_restore_widget` helper dedups 4 snapshot-restore call sites (Add.redo / Delete.undo / DeleteMultiple.undo / BulkAdd.redo). Optimize: none — command paths are one-shot user actions, not hot.
- [x] `app/ui/main_window.py` — refactor: `build_bulk_add_entries` helper in commands.py replaces 6 duplicated snapshot-capture blocks across main_window / object_tree_window / workspace/core (~100 line dedup; document_id drift now impossible). Optimize: none — Edit-menu dispatchers aren't on a hot path.
- [ ] `app/ui/object_tree_window.py`
- [ ] `app/ui/palette.py`
- [ ] `app/ui/properties_panel_v2/panel.py`
- [ ] `app/ui/workspace/core.py`
- [ ] `app/ui/workspace/drag.py`
- [ ] `app/ui/workspace/chrome.py` — **O5 queued**: `drive_drag` coalesce. See note below.
- [ ] `app/ui/workspace/controls.py`
- [ ] `app/ui/workspace/widget_lifecycle.py`
- [ ] `app/ui/workspace/render.py`
- [ ] `app/ui/selection_controller.py`
- [ ] `app/ui/zoom_controller.py`

### O5 note — `chrome.drive_drag` coalesce via `after_idle`

Real-world evidence: 160 widgets on a form → dragging the doc chrome
"got a bit heavy". Current `chrome.drive_drag` ([chrome.py:504](../../app/ui/workspace/chrome.py#L504))
runs `_redraw_document()` + `zoom.apply_all()` + `selection.update()`
per motion event. At ~100 motions/sec × 160 widgets = 16,000
`place_configure()` Tk calls/sec.

**Fix plan when we get to `chrome.py`:**
- Keep `doc.canvas_x` / `canvas_y` updates synchronous (coord state
  stays accurate for every motion).
- Defer render via `after_idle(_flush_drag_render)`; guard with a
  `drag["pending"]` flag so multiple motions coalesce into one render.
- `end_drag` runs a final flush so the release frame is always
  up-to-date.

**Verify:** chrome-drag smoothness at 1 / 10 / 100 / 160 widgets;
widget positions correct on release; regular (non-chrome) widget
drag unchanged.

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

- **[WS-9]** Ghost selection chrome lingered at pre-drag position
  *Steps:* select a widget, drag it
  *Expected:* chrome follows the widget
  *Observed:* chrome appeared at the new position but a second outline remained at the old spot for the duration of the drag
  *Fix:* every chrome canvas item now carries a shared ``selection_chrome`` tag; ``clear`` sweeps the tag in one call and drag motion uses ``canvas.move`` against per-widget tags so stale items can't be left behind

- **[WS-10]** Delete key on a locked widget was silent
  *Steps:* lock a widget, select it on canvas, press Delete
  *Expected:* visible reason
  *Observed:* bell sound only, easy to miss
  *Fix:* show ``messagebox.showinfo`` explaining the widget is locked and how to unlock

- **[WS-11]** Object Tree bypassed the lock
  *Steps:* lock a widget, right-click → Delete in the Object Tree, or drag its row onto another parent
  *Expected:* tree honours the same lock as canvas
  *Observed:* both operations went through
  *Fix:* ``_delete_widget`` and ``_on_drag_start`` in ``ObjectTreePanel`` now early-return / dialog for locked widgets

- **[WS-12]** Locked widget's chrome tracked the drag in a multi-selection
  *Steps:* Ctrl+click an unlocked widget A and a locked widget C, drag A
  *Expected:* A + A's chrome move, C + C's chrome stay
  *Observed:* A and C's chrome both followed the cursor while C itself stayed put — chrome snapped back on release
  *Fix:* every chrome item also gets a per-widget tag (``chrome_wid_<id>``); drag motion calls ``canvas.move`` only for tags of widgets actually in ``group_starts``, so locked / layout-managed siblings keep their chrome pinned

- **[WS-13]** Tree drag reparent dropped widget at a strange position
  *Fix:* `_reset_position_for_tree_reparent` in `ObjectTreePanel` — cascade offset (10, 10 +20 per occupied slot) when the new parent is place-layout; pack/grid parents leave x/y untouched

- **[WS-14]** Tree drag reparent wasn't undoable
  *Fix:* `_on_drag_release` now captures old/new parent, index, x/y, document_id and pushes a `ReparentCommand`

- **[WS-15]** Multi-select Delete worked only for one widget
  *Fix:* `workspace._on_delete` walks `selected_ids`, skips descendants of a selected ancestor, bundles into a `DeleteMultipleCommand`; canvas right-click menu preserves multi when the clicked widget is in the selection

- **[WS-16]** Undo of cross-doc delete piled every restored widget back into the active doc
  *Fix:* `DeleteWidgetCommand` + `DeleteMultipleCommand` carry per-entry `document_id`; `project.add_widget` takes a `document_id` for top-level placement

- **[WS-17]** Redo of cross-doc add (palette drop / paste / duplicate) piled widgets into the active doc
  *Fix:* `AddWidgetCommand` + `BulkAddCommand` carry `document_id`; same `project.add_widget(document_id=...)` path

- **[WS-18]** Cross-doc drag move couldn't be undone
  *Fix:* `project.reparent(document_id=...)` for top-level targets; `ReparentCommand` gains `old_document_id` + `new_document_id`

- **[WS-19]** Document accent colors collided visually between forms
  *Fix:* hue now `doc_index * golden_ratio_conjugate` — guaranteed max separation for small N, instead of per-UUID hash which could land two docs on near-same hue

- **[WS-20]** Left-click on empty area of a non-active document didn't activate it
  *Fix:* `_on_canvas_click` detects the doc under the cursor and sets it active before the deselect

- **[WS-21]** Window Settings couldn't be opened from the chrome gear icon in Select tool
  *Steps:* switch to Select tool, click the settings icon on a form's title chrome
  *Expected:* Window Settings opens in the Properties panel — they describe the whole form, not a single widget, so tool mode shouldn't matter
  *Observed:* Properties panel stayed collapsed to chrome-only (the Select-mode skip path didn't carve out WINDOW_ID)
  *Fix:* `PropertiesPanel._rebuild` allows the full panel rebuild when `tool == "select"` AND `node.id == WINDOW_ID`. Hand tool stays strict — pure canvas panner, does nothing else

- **[WS-22]** Dragging a document to a new canvas position, then undo — doc returned, widgets stayed at the moved offset
  *Steps:* move a form's chrome to another spot on the canvas, press Ctrl+Z
  *Expected:* both form rectangle and every widget inside return to the original position
  *Observed:* doc rectangle returned, but widgets stayed at the dragged offset — they use `canvas.create_window` at `logical_to_canvas(x, y, document=doc)` and needed re-placement
  *Fix:* `MoveDocumentCommand._apply` publishes a new `document_position_changed(doc_id)` event; workspace subscribes and replays the live-drag sequence (redraw + `zoom.apply_all()` + selection update)

- **[WS-23]** Ctrl+C / Ctrl+V didn't work on the canvas, only inside the Object Tree
  *Steps:* select a widget on the canvas, press Ctrl+C → nothing happens
  *Expected:* widget copies regardless of which panel has focus
  *Observed:* `Control-c` / `Control-v` were only bound at the Object Tree level; canvas had no handler, so the shortcut silently did nothing
  *Fix:* added `self.bind("<Control-c>"/"<Control-v>"/"<<Copy>>"/"<<Paste>>")` on `MainWindow` with an Entry/Text focus skip so native text copy/paste still runs when the user is typing in a property editor

- **[WS-24]** Georgian / non-Latin keyboard layouts broke the clipboard shortcuts
  *Steps:* switch keyboard to Georgian, press Ctrl+C on a selected widget
  *Expected:* widget copies — the fallback path exists (`_on_control_keypress` detects VK 67 / 86 and emits `<<Copy>>` / `<<Paste>>`)
  *Observed:* the virtual events fired but no-one was listening at the main-window level, so they disappeared
  *Fix:* same bindings as WS-23 cover `<<Copy>>` / `<<Paste>>` — the non-Latin path now lands in the project-level handlers

- **[WS-25]** Paste cascade stacked clones on top of the last paste
  *Steps:* Ctrl+V five times in a row
  *Expected:* five visible copies, each in its own slot
  *Observed:* every clone landed at `original_xy + 20` — after the second paste they all overlapped at the same slot
  *Fix:* `Project.paste_from_clipboard` now builds a `sibling_occupancy` set from the target's children and steps through `(nx, ny) += (20, 20)` until a free slot is found, matching the palette-drop cascade

- **[WS-26]** Pasting into a Frame (container) landed the clone in a "strange" position
  *Steps:* copy a top-level widget sitting at e.g. (200, 300), paste it into a 300 × 200 Frame
  *Expected:* clone visible inside the Frame near its top-left
  *Observed:* clone preserved its original top-level coords, ending up partially or fully outside the Frame's bounds
  *Fix:* container pastes now start cascade from `(10, 10)` inside the parent and fill sibling_occupancy from `parent.children`, so the original source coord space is discarded at paste time
