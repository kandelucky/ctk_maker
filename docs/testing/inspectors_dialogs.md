# Area 8 — Inspectors & Dialogs

Object Tree (F8), History (F9), main-window chrome (menubar / toolbar / shortcuts), and every modal (Startup, New Project, Rename, Add Dialog picker, Window Settings, unsaved-changes prompts).

## Test

### Object Tree panel (F8)
- [x] Hierarchical widget list — parent / child indentation correct
- [x] Tree respects z-order (top of parent.children at the bottom, visually matches canvas stacking)
- [x] Expand / collapse via chevron
- [x] Search / filter field narrows the list in real time
- [x] Filter survives selection change (doesn't clear on click)
- [x] Row icons: widget type glyph + visibility (eye) + lock (padlock)
- [x] Click visibility icon → toggles `node.visible`, canvas reflects
- [x] Click lock icon → toggles `node.locked`, canvas rejects drag / resize
- [x] Click row → selects widget on canvas
- [x] Ctrl+click — multi-select (extended mode)
- [x] Shift+click — range select
- [x] Drag row onto another row → reparents (drop target becomes new parent)
- [x] Drag row between siblings → reorders z-order
- [x] Drag onto top-level → promotes to root
- [x] Right-click → context menu: Rename, Duplicate, Delete, Copy, Paste, Bring to Front, Send to Back
- [x] Inline rename (double-click name) — edit in place, Enter commits, Escape cancels
- [x] Container suffix: `[vbox]` / `[hbox]` / `[grid]` / `[place]`
- [x] Only active document's widgets visible
- [x] Bottom status strip shows active document name
- [x] Floating window variant (View → Object Tree) mirrors docked panel
- [x] Docked panel resize via PanedWindow sash

### History panel (F9)
- [x] F9 toggles visibility (floating) + docked in sidebar toggle
- [x] Live-updating stack — new entries append on every command
- [x] Current-state marker on correct row
- [x] Click undo entry → jumps to that state
- [x] Click redo entry (above current) → redoes to that state
- [x] Redo stack rows visibly differ (greyed)
- [x] Long history scrolls
- [x] Entry descriptions match the command
- [x] Coalesced rapid commands appear as single entries
- [x] History panel keeps focus on itself — doesn't steal canvas focus during active drag
- [x] Empty history — panel shows placeholder

### Main window menubar
- [x] **File** — New, New Untitled, Open, Save, Save As, Recent Files ▸, Export, Quit
- [x] **Edit** — Undo, Redo, Cut, Copy, Paste, Duplicate, Rename, Delete, Select All
- [x] **Form** — Preview, Preview Active Dialog, Add Dialog, Remove, Rename, Form Settings, Move Up/Down, All Forms
- [x] **Widget** — grouped cascades matching palette (Layouts/Containers/Buttons/Display/Selection/Input)
- [x] **Help** — Documentation, About (with library links)
- [x] Enabled / disabled state reflects selection, clipboard, history

### Toolbar
- [x] All icon buttons render at correct size, tinted
- [x] Buttons respect enabled / disabled state (Undo/Redo dim when empty)
- [x] Hover tooltip appears above cursor per button
- [x] Workspace bar: Preview Project / Preview Active Dialog icons with dim state

### Keyboard shortcuts
- [x] `Ctrl+Z` / `Ctrl+Y` — undo / redo
- [x] `Ctrl+S` / `Ctrl+Shift+S` — save / save as
- [x] `Ctrl+O` — open project
- [x] `Ctrl+N` — new project
- [x] `Ctrl+C` / `Ctrl+V` / `Ctrl+X` — copy / paste / cut
- [x] `Ctrl+D` — duplicate
- [x] `Delete` — remove selection
- [x] `Arrow keys` — 1px nudge
- [x] `Shift+arrow` — 10px nudge
- [x] `Ctrl+I` — rename selected (replaces F2)
- [x] `Ctrl+P` — preview active dialog
- [x] `Ctrl+M` — add dialog
- [x] `Ctrl+A` — select all (active document)
- [x] `Ctrl+Shift+I` — documentation
- [x] `F8` / `F9` — Object Tree / History toggles
- [x] `Escape` — deselect
- [x] `Ctrl+R` — preview project
- [x] `Ctrl+Q` — quit
- [x] `Ctrl+wheel` — zoom
- [x] Shortcuts work with non-Latin keyboard layouts (hardware keycode fallback)

### Startup dialog
- [x] Appears on first launch (no recent project)
- [x] Buttons: New, Open, Recent (list), Exit
- [x] Recent list filters missing / deleted files
- [x] Selecting a project dismisses dialog + loads workspace
- [x] Cancel / close → app quits

### New Project dialog
- [x] Fields: name, save path, default size
- [x] Validation: non-empty name, writable path
- [x] Cancel returns to startup / closes builder
- [x] Create → empty project opens in workspace

### Rename dialog
- [x] Triggered by Ctrl+I / right-click context menu / Form → Rename
- [x] Prefills current name
- [x] Commit applies + pushes RenameCommand
- [x] Cancel leaves state untouched

### Add Dialog preset picker
- [x] Opens on `+ Add Dialog` / Ctrl+M
- [x] Presets: Alert / Compact / Medium / Settings / Wizard / Same as Main
- [x] Selection → creates dialog + pushes AddDocumentCommand

### Unsaved-changes prompt
- [x] Triggered on New / Open when project dirty
- [x] Buttons: Save / Discard / Cancel
- [x] Save path: saves + proceeds
- [x] Discard: proceeds without save
- [x] Cancel: no-op

### Window Settings (per-document)
- [x] Opened via chrome ⚙ / Form → Form Settings / Ctrl+I on window node
- [x] Title field — syncs with project name on Main Window
- [x] Size: width / height inputs
- [x] `fg_color` — live preview on document rectangle
- [x] `resizable_x` / `resizable_y` — toggles
- [x] `frameless` — toggle; preview updates chrome
- [x] Builder Grid — style (`none` / `dots` / `lines`), colour, spacing; design-time only
- [x] `accent_color` — live preview on chrome, clear falls back to auto-derived hue

### Status bar
- [x] Zoom controls: slider + / - / reset
- [x] Zoom readout in %
- [x] Active document label (when multi-doc)
- [x] Font-scale warning when scaling breaks readability

### Theme toggle
- [!] Light / Dark switch hidden (View → Appearance Mode disabled) — see bugs.md
- [!] Canvas BG, chrome, panel BG, icon tints do not update on toggle
- [!] Persistence across sessions — not verified (toggle broken)

---

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

- **[Object Tree]** Filter dropdown showed widgets from all documents — fixed: scoped to active document only. v0.0.15.25
- **[Object Tree]** F2 inline rename didn't work — replaced with double-click inline Entry overlay + Ctrl+I shortcut. v0.0.15.25
- **[Object Tree]** Type column showed full type names (100px) — replaced with 2–3 letter initials (36px); CTkFrame layout-aware (VFr/HFr/GFr). v0.0.15.25
- **[Properties]** Name field turned white in disabled state on Windows — `disabledbackground` fix. v0.0.15.25
- **[Properties]** Type icon persisted after deselection — CTkLabel `_update_image` skips label update on None; bypass via `_label.configure(image="")`. v0.0.15.25
- **[Properties]** Right-click disabled items showed doubled text (Windows) — `state="disabled"` replaced with `foreground` colour trick. v0.0.15.25
- **[Shortcuts]** Ctrl+D (Duplicate) and Ctrl+X (Cut) missing — added with Georgian keycode fallback. v0.0.15.32
- **[Shortcuts]** F2 (Rename) never fired — removed; Ctrl+I added instead. v0.0.15.32
- **[Theme toggle]** Light/Dark/System toggle does not apply — deferred, hidden in View menu. Filed in bugs.md.
- **[Menu border]** White border on dropdown menus is OS-level (Windows native menu frame) — cannot be controlled via tkinter `bd`. Accepted limitation.
