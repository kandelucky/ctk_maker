# Area 8 — Inspectors & Dialogs

Object Tree (F8), History (F9), main-window chrome (menubar / toolbar / shortcuts), and every modal (Startup, New Project, Rename, Add Dialog picker, Window Settings, unsaved-changes prompts).

## Test

### Object Tree panel (F8)
- [ ] Hierarchical widget list — parent / child indentation correct
- [ ] Tree respects z-order (top of parent.children at the bottom, visually matches canvas stacking)
- [ ] Expand / collapse via chevron
- [ ] Search / filter field narrows the list in real time
- [ ] Filter survives selection change (doesn't clear on click)
- [ ] Row icons: widget type glyph + visibility (eye) + lock (padlock)
- [ ] Click visibility icon → toggles `node.visible`, canvas reflects
- [ ] Click lock icon → toggles `node.locked`, canvas rejects drag / resize
- [ ] Click row → selects widget on canvas
- [ ] Ctrl+click — multi-select (extended mode)
- [ ] Shift+click — range select
- [ ] Drag row onto another row → reparents (drop target becomes new parent)
- [ ] Drag row between siblings → reorders z-order
- [ ] Drag onto top-level → promotes to root
- [ ] Right-click → context menu: Rename, Duplicate, Delete, Copy, Paste, Bring to Front, Send to Back
- [ ] Inline rename (F2 or double-click name) — edit in place, Enter commits, Escape cancels
- [ ] Container suffix: `[vbox]` / `[hbox]` / `[grid]` / `[place]`
- [ ] Only active document's widgets visible
- [ ] Bottom status strip shows active document name
- [ ] Floating window variant (View → Object Tree) mirrors docked panel
- [ ] Docked panel resize via PanedWindow sash

### History panel (F9)
- [ ] F9 toggles visibility
- [ ] Live-updating stack — new entries append on every command
- [ ] Current-state marker on correct row
- [ ] Click undo entry → jumps to that state
- [ ] Click redo entry (above current) → redoes to that state
- [ ] Redo stack rows visibly differ (greyed / italicised)
- [ ] Long history scrolls
- [ ] Entry descriptions match the command (e.g. "Move Button", "Delete Frame")
- [ ] Coalesced rapid commands appear as single entries
- [ ] History panel keeps focus on itself — doesn't steal canvas focus during active drag
- [ ] Empty history — panel shows placeholder / zero state

### Main window menubar
- [ ] **File** — New, Open, Save, Save As, Recent Files ▸, Export, Exit
- [ ] **Edit** — Undo, Redo, Cut, Copy, Paste, Duplicate, Delete, Select All
- [ ] **View** — Object Tree, History, theme toggle, status bar
- [ ] **Form** — Add Dialog, Delete Dialog, Rename Dialog
- [ ] **Help** — Documentation link, About
- [ ] Enabled / disabled state reflects selection, clipboard, history

### Toolbar
- [ ] All icon buttons render at correct size (16px, tinted)
- [ ] Buttons respect menubar enabled / disabled state
- [ ] Hover tooltip per button
- [ ] Add Dialog button opens preset picker

### Keyboard shortcuts
- [ ] `Ctrl+Z` / `Ctrl+Y` — undo / redo
- [ ] `Ctrl+S` / `Ctrl+Shift+S` — save / save as
- [ ] `Ctrl+O` — open project
- [ ] `Ctrl+N` — new project
- [ ] `Ctrl+C` / `Ctrl+V` / `Ctrl+X` — copy / paste / cut
- [ ] `Ctrl+D` — duplicate
- [ ] `Delete` — remove selection
- [ ] `Arrow keys` — 1px nudge
- [ ] `Shift+arrow` — 10px nudge
- [ ] `F2` — rename selected
- [ ] `F8` / `F9` — Object Tree / History toggles
- [ ] `Escape` — deselect
- [ ] `Ctrl+R` — preview (spawn exported .py)
- [ ] `Ctrl+wheel` — zoom
- [ ] Shortcuts work with Georgian keyboard layout too (legacy workaround)

### Startup dialog
- [ ] Appears on first launch (no recent project)
- [ ] Buttons: New, Open, Recent (list), Exit
- [ ] Recent list filters missing / deleted files
- [ ] Selecting a project dismisses dialog + loads workspace
- [ ] Cancel / close → app quits

### New Project dialog
- [ ] Fields: name, save path, maybe default size
- [ ] Validation: non-empty name, writable path
- [ ] Cancel returns to startup / closes builder
- [ ] Create → empty project opens in workspace

### Rename dialog
- [ ] Triggered by F2 / context menu / Form menu
- [ ] Prefills current name
- [ ] Commit applies + pushes RenameCommand
- [ ] Cancel leaves state untouched

### Add Dialog preset picker
- [ ] Opens on `+ Add Dialog` click
- [ ] Presets: Alert / Compact / Medium / Settings / Wizard / Same as Main
- [ ] Preview / preset description visible
- [ ] Selection → creates dialog + pushes AddDocumentCommand

### Unsaved-changes prompt
- [ ] Triggered on Close / New / Open when project dirty
- [ ] Buttons: Save / Discard / Cancel
- [ ] Save path: saves + proceeds
- [ ] Discard: proceeds without save
- [ ] Cancel: no-op

### Window Settings (per-document)
- [ ] Opened via chrome ⚙ on any document
- [ ] Title field — syncs with project name on Main Window
- [ ] Size: width / height sliders / number inputs
- [ ] `fg_color` — live preview on document rectangle
- [ ] `resizable_x` / `resizable_y` — toggles
- [ ] `frameless` — toggle; preview updates chrome
- [ ] Builder Grid — style (`none` / `dots` / `lines`), colour, spacing; design-time only, not exported
- [ ] `accent_color` (optional override for chrome tint) — live preview on chrome, clear falls back to auto-derived hue

### Status bar
- [ ] Zoom controls: slider + / - / reset
- [ ] Zoom readout in %
- [ ] Active document label (when multi-doc)
- [ ] Font-scale warning when scaling breaks readability

### Theme toggle
- [ ] Light / Dark switch (menu or toolbar)
- [ ] Switches canvas BG, chrome, panel BG, icon tints
- [ ] Persists across sessions

## Refactor candidates

- [ ] `object_tree_window.py` + `ObjectTreePanel` — drag-to-reparent logic complexity; extract to helper?
- [ ] Context menu definition — scattered across panels or centralised?
- [ ] Menubar / toolbar — are handlers consistent with keyboard shortcut handlers?
- [ ] Dialog classes — common base for modal pattern (center on parent, transient, destroy on escape)?
- [ ] Window Settings — properties panel reuse or custom?

## Optimize candidates

- [ ] Object Tree rebuild on every `widget_added` / `widget_removed` — partial update possible?
- [ ] Filter re-evaluates whole tree on every keystroke — debounce?
- [ ] History panel rebuild on every push — incremental row add?
- [ ] Theme swap — how many widgets reconfigure? Batch?

## Findings

<!-- inspector / dialog bugs here -->
