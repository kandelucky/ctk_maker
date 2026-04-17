# Area 6 — Multi-document canvas

Main Window + N Dialogs, per-document chrome, drag-to-move, cross-document widget drag, widget masking for overlapping forms.

## Test

### Document lifecycle
- [ ] New project — one Main Window, no Dialogs
- [ ] `+ Add Dialog` toolbar button — preset picker appears
- [ ] Each preset (Alert / Compact / Medium / Settings / Wizard / Same as Main) — creates dialog with matching size + widgets
- [ ] Delete dialog via chrome `✕` — confirm prompt, then removed
- [ ] Delete Main Window `✕` — closes project (prompts for unsaved changes)
- [ ] Undo Add Dialog — dialog gone
- [ ] Undo Delete Dialog — dialog + all widgets restored

### Chrome
- [ ] Drag chrome title bar → moves document on canvas
- [ ] Drag is reversible via undo
- [ ] Click ⚙ → opens Window Settings for that document
- [ ] Click chrome (not ⚙/✕) → switches active document + deselects widget
- [ ] Active document highlighted (border / background tint)
- [ ] Forms overlap → correct z-order via stacking

### Chrome accent color
- [ ] Every document gets a distinct title-bar colour (auto-derived from UUID via golden-ratio hue)
- [ ] Same document keeps its colour across save / load (deterministic from UUID)
- [ ] User-picked `color` in Window Settings overrides the auto-colour
- [ ] Clear user `color` → falls back to auto-derived
- [ ] Colour visible / readable on dark theme

### Document z-order
- [ ] `chevrons-up` button (Bring to Front) — document renders on top
- [ ] Bring-to-front activates the document (active = top)
- [ ] `chevrons-down` button (Send to Back) — document renders behind others
- [ ] Send-to-back of the active document → promotes next topmost to active
- [ ] Z-order changes survive save / load
- [ ] Z-order changes covered by undo / redo

### Widget masking
- [ ] Widget behind another form — hidden from canvas view
- [ ] Bring that form forward (drag) — widget re-appears
- [ ] Cannot click a masked widget (blocked by covering form)
- [ ] Object Tree still shows masked widgets (masking is visual, not logical)

### Cross-document drag
- [ ] Drag widget from Main Window → Dialog — reparents, lands in target
- [ ] Drag widget from Dialog → Main Window — reparents correctly
- [ ] Drag widget Dialog A → Dialog B
- [ ] Logical x/y recalculated against new document's canvas_x/y offset
- [ ] Undo reverses: widget returns to original document at original x/y

### Object Tree
- [ ] Shows only active document's widgets
- [ ] Switching active document refreshes tree
- [ ] Status strip at bottom shows "Editing: <document name>"
- [ ] Floating Object Tree window mirrors docked panel

### Export
- [ ] Single-document project → one `.py` with one class
- [ ] Multi-document project → one `.py` with N classes (CTk + N × CTkToplevel)
- [ ] Class names derived from document names (sanitised)
- [ ] Inter-document references (if any) — document or omit
- [ ] Exported multi-class runs, main window shows, dialogs openable?

### Edge cases
- [ ] 10+ dialogs — performance, canvas scroll / fit
- [ ] Two documents at same canvas coords — z-order handled
- [ ] Rename active document → chrome updates, Object Tree updates
- [ ] Delete last dialog → only Main Window remains, no crash

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
