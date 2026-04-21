# Area 4 — Commands (undo / redo)

Every mutation pushed to `project.history`; each command reversible with ID stability across undo.

## Test

### Command classes (each must undo + redo cleanly)
- [x] **AddWidgetCommand** — palette drop, clipboard paste, duplicate (right-click menu, no Ctrl+D shortcut)
- [x] **DeleteWidgetCommand** — single, multi-select, cascade-delete with children
- [x] **MoveCommand** — drag, arrow-nudge
- [x] **ResizeCommand** — 8-handle, W/H drag-scrub
- [x] **ChangePropertyCommand** — every editor type
- [x] **MultiChangePropertyCommand** — multi-row edits (e.g. pair rows)
- [x] **ReparentCommand** — drag into container, cross-document
- [x] **ZOrderCommand** — bring-to-front, send-to-back, reorder
- [x] **RenameCommand** — inline + dialog
- [x] **BulkAddCommand** — paste / duplicate multi-widget selections
- [x] **AddDocumentCommand** / **DeleteDocumentCommand** / **MoveDocumentCommand** — dialog lifecycle
- [x] **VisibilityCommand** / **LockCommand** — toggles
- [ ] **TogglePropertyCommand** (if it exists) — sanity check

### ID stability
- [x] Delete widget → undo → same widget ID
- [x] Selection survives undo (re-selects same ID)
- [x] Object Tree references stay valid
- [x] Properties panel re-binds on undo

### Coalescing (0.6s window)
- [x] Rapid arrow-nudges → one undo entry
- [x] Inline rename typing → one undo entry
- [x] Drag-scrub → one undo entry on release
- [x] Pause > 0.6s mid-burst → splits into two undo entries
- [x] Switching widgets mid-burst doesn't coalesce cross-widget

### Redo clearing
- [x] Undo → do new action → redo stack clears (can't re-apply old redo)
- [x] Redo after undo → state identical to pre-undo
- [x] Long undo chain (50+) — history panel shows all, scrolls (MAX_DEPTH=200)

### History panel (F9)
- [x] Shows live-updating list
- [x] Current state marker on correct entry
- [!] Click entry jumps to that point — multi-step jump not implemented (in roadmap)
- [x] Redo stack greyed but visible
- [x] Panel coexists with main window (doesn't steal focus during drag)

### Edge cases
- [x] Undo at history start — no-op, no crash
- [x] Redo at history end — no-op
- [x] Ctrl+Z vs Edit menu vs toolbar — all three invoke same path
- [x] Undo during drag — cancels drag back to original position (matches Escape)
- [x] Delete an ancestor → undo → full subtree rebuilt with original IDs + properties
- [x] **Rapid undo/redo grid reparent (legacy)** — not reproduced. May have been fixed by v0.0.15.7 auto-grow undo tracking + v0.0.15.12 panel split.

### Findings

- **[C4-1]** Holding Ctrl+Z (OS auto-repeat) ripped through the entire undo history in a blur
  *Fix:* added `_undo_key_held` / `_redo_key_held` flags on `<KeyPress-z/y>`, cleared on `<KeyRelease>` — one press = one undo (v0.0.15.15).

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
