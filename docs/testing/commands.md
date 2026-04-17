# Area 4 — Commands (undo / redo)

Every mutation pushed to `project.history`; each command reversible with ID stability across undo.

## Test

### Command classes (each must undo + redo cleanly)
- [ ] **AddWidgetCommand** — palette drop, clipboard paste, duplicate
- [ ] **DeleteWidgetCommand** — single, multi-select, cascade-delete with children
- [ ] **MoveCommand** — drag, arrow-nudge
- [ ] **ResizeCommand** — 8-handle, W/H drag-scrub
- [ ] **ChangePropertyCommand** — every editor type
- [ ] **MultiChangePropertyCommand** — multi-row edits (e.g. pair rows)
- [ ] **ReparentCommand** — drag into container, cross-document
- [ ] **ZOrderCommand** — bring-to-front, send-to-back, reorder
- [ ] **RenameCommand** — inline + dialog
- [ ] **BulkAddCommand** — paste / duplicate multi-widget selections
- [ ] **AddDocumentCommand** / **DeleteDocumentCommand** / **MoveDocumentCommand** — dialog lifecycle
- [ ] **VisibilityCommand** / **LockCommand** — toggles
- [ ] **TogglePropertyCommand** (if it exists) — sanity check

### ID stability
- [ ] Delete widget → undo → same widget ID
- [ ] Selection survives undo (re-selects same ID)
- [ ] Object Tree references stay valid
- [ ] Properties panel re-binds on undo

### Coalescing (0.6s window)
- [ ] Rapid arrow-nudges → one undo entry
- [ ] Inline rename typing → one undo entry
- [ ] Drag-scrub → one undo entry on release
- [ ] Pause > 0.6s mid-burst → splits into two undo entries
- [ ] Switching widgets mid-burst doesn't coalesce cross-widget

### Redo clearing
- [ ] Undo → do new action → redo stack clears (can't re-apply old redo)
- [ ] Redo after undo → state identical to pre-undo
- [ ] Long undo chain (50+) — history panel shows all, scrolls

### History panel (F9)
- [ ] Shows live-updating list
- [ ] Current state marker on correct entry
- [ ] Click entry jumps to that point
- [ ] Redo stack greyed but visible
- [ ] Panel coexists with main window (doesn't steal focus during drag)

### Edge cases
- [ ] Undo at history start — no-op, no crash
- [ ] Redo at history end — no-op
- [ ] Ctrl+Z vs Edit menu vs toolbar — all three invoke same path
- [ ] Undo during drag — disabled or queued?
- [ ] Delete an ancestor → undo → full subtree rebuilt with original IDs + properties

## Refactor candidates

- [ ] Command class API — `undo` / `redo` / `merge_into` signatures consistent across all?
- [ ] Command descriptions — lower / Title case consistent?
- [ ] Snapshot serialization (`to_dict`) vs live references — every command use same pattern?
- [ ] `merge_into` default implementation (return False) — can it live on the base class only?
- [ ] Duplication between `AddWidgetCommand` and `BulkAddCommand`?

## Optimize candidates

- [ ] Command snapshot size for large subtrees — deep-copy vs structural sharing
- [ ] History list UI — rebuild vs incremental on push
- [ ] Coalescing window check uses `time.monotonic()` per push — cheap but profile

## Findings

<!-- undo/redo bugs here -->
