# Area 6 — Multi-document canvas

Main Window + N Dialogs, per-document chrome, drag-to-move, cross-document widget drag, widget masking for overlapping forms.

## Test

### Document lifecycle
- [x] New project — one Main Window, no Dialogs
- [x] `+ Add Dialog` toolbar button — preset picker appears
- [x] Each preset (Alert / Compact / Medium / Settings / Wizard / Same as Main) — creates dialog with matching size + widgets
- [x] Delete dialog via chrome `✕` — confirm prompt, then removed
- [x] Delete Main Window `✕` — closes project (prompts for unsaved changes)
- [x] Undo Add Dialog — dialog gone
- [x] Undo Delete Dialog — dialog + all widgets restored

### Chrome
- [x] Drag chrome title bar → moves document on canvas
- [x] Drag is reversible via undo
- [x] Click ⚙ → opens Window Settings for that document
- [x] Click chrome (not ⚙/✕) → switches active document + deselects widget
- [x] Active document highlighted (border / background tint)
- [x] Forms overlap → correct z-order via stacking

### Chrome accent color
- [x] Every document gets a distinct title-bar colour (auto-derived from UUID via golden-ratio hue)
- [x] Same document keeps its colour across save / load (deterministic from UUID)
- [x] User-picked `color` in Window Settings overrides the auto-colour
- [x] Clear user `color` → falls back to auto-derived
- [x] Colour visible / readable on dark theme

### Document z-order
- [x] `chevrons-up` button (Bring to Front) — document renders on top
- [x] Bring-to-front activates the document (active = top)
- [x] `chevrons-down` button (Send to Back) — document renders behind others
- [x] Send-to-back of the active document → promotes next topmost to active (v0.0.15.18 fix: also works for doc at index 0 when it's the active one)
- [x] Z-order changes survive save / load
- [x] Z-order changes covered by undo / redo

### Widget masking
- [x] Widget behind another form — hidden from canvas view
- [x] Bring that form forward (drag) — widget re-appears
- [x] Cannot click a masked widget (blocked by covering form)
- [x] Object Tree still shows masked widgets within the active document (masking is visual, not logical)

### Cross-document drag
- [x] Drag widget from Main Window → Dialog — reparents, lands in target
- [x] Drag widget from Dialog → Main Window — reparents correctly
- [x] Drag widget Dialog A → Dialog B
- [x] Logical x/y recalculated against new document's canvas_x/y offset
- [x] Undo reverses: widget returns to original document at original x/y

### Object Tree
- [x] Shows only active document's widgets
- [x] Switching active document refreshes tree
- [x] Status strip at bottom shows "Editing: <document name>"
- [x] Floating Object Tree window mirrors docked panel

### Export
- [x] Single-document project → one `.py` with one class
- [x] Multi-document project → one `.py` with N classes (CTk + N × CTkToplevel)
- [x] Class names derived from document names (sanitised)
- [x] Inter-document references — not a builder feature; exported file leaves dialog instantiation commented for the user to wire
- [x] Exported multi-class runs, main window shows, dialogs openable via uncommenting the `# var = Class(app)` lines

### Edge cases
- [x] 10+ dialogs — performance, canvas scroll / fit
- [x] Two documents at same canvas coords — z-order handled
- [x] Rename active document → chrome updates, Object Tree updates
- [x] Delete last dialog → only Main Window remains, no crash

## Findings

- **[P6-1]** Main Window couldn't be sent to back when active — it sat at docs list index 0 so the chrome's Send-to-Back button was hidden, but `active=top` render sort meant the window was visually on top of every other doc. User had no way to reveal a Dialog hidden behind an active-main-window.
  *Fix:* `send_document_to_back` now also accepts "index 0 but active" — promotes the next topmost to active instead of reordering. Chrome `can_to_back` mirrors: shown when doc is active OR not at index 0. (v0.0.15.18)

- **[P6-2]** `AddDialogSizeDialog` silently rejected huge / negative sizes via `bell()` only — no feedback about the max range.
  *Fix:* clamp to 100–4000 and show a warning dialog naming the range. (v0.0.15.18)

- **[P6-3]** No way to export just one Dialog — File → Export emitted the whole project, which is useless when copy-pasting a dialog into another app.
  *Fix:* new single-document export path (`generate_code(single_document_id=...)`) that emits just the requested doc as a standalone `ctk.CTk` subclass. Triggered via File → Export Active Document... and the per-dialog Export icon in the chrome. (v0.0.15.18)

## Refactor candidates

- [ ] `chrome.py` — render + drag + settings + close in one file; split if dense
- [ ] Document-specific state — lives on Project or Document dataclass?
- [ ] Widget masking logic — how coupled to chrome?
- [ ] `canvas_x` / `canvas_y` propagation — clear path from Document → ZoomController → widget?

## Optimize candidates

- [ ] Redraw of non-active documents — cache their widget rects, skip until needed?
- [ ] Masking recalculation on every drag — event-driven vs per-frame?
- [ ] Add Dialog cold start — widgets created synchronously; defer?

## Findings

<!-- multi-doc bugs here -->
