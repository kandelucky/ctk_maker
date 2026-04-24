# CTk Visual Builder

A desktop visual designer for **CustomTkinter** — drag and drop widgets onto a canvas, edit their properties live, and export the result as clean runnable Python.

> **Status:** v0.0.18 — full widget core stable. CTkScrollableFrame and CTkTabview are now real containers (drop children straight inside, per-tab assignment for Tabview), and CTkComboBox / CTkOptionMenu ship a Toplevel-based scrollable dropdown that matches the parent width. Widget docs are being rewritten — see [docs/todo/done.md](docs/todo/done.md) for the per-version changelog in the meantime.

[![v0.0.18](docs/history/v0.0.18.png)](docs/history/v0.0.18.png)

## Features

### Canvas + editing
- Real CTk widgets rendered on a tk Canvas (preview = reality)
- Drag to move, resize via 8 handles, arrow-key nudge (1 px / 10 px with Shift)
- Nested containers — drop widgets inside `CTkFrame`, `CTkScrollableFrame`, or any tab of a `CTkTabview`
- Reparent by dragging a widget from one container to another, including across documents
- Multi-select from the Object Tree with sync'd workspace highlighting
- Zoom controls + dot grid, hand-tool pan, middle-mouse pan

### Multi-document canvas
- One `.ctkproj` holds a Main Window plus any number of Dialogs, all visible on the same canvas
- Per-document chrome (title bar, settings, close) with drag-to-move, active highlight, stacking when forms overlap
- `+ Add Dialog` on the workspace toolbar with preset picker (Alert / Compact / Medium / Settings / Wizard / Same as Main)
- Smart widget masking — widgets behind another form are hidden so the active form reads cleanly
- Cross-document widget drag

### Layout managers
- Every container carries a `layout_type`: `place` / `vbox` / `hbox` / `grid`
- `vbox` / `hbox` render children through real `pack()` on canvas
- `grid` renders children in real cells with drag-to-cell snap, palette-drop targeting, and auto-next-free-cell assignment
- Child layout controls collapse to a single `stretch` (fixed / fill / grow) or `grid_sticky`
- Canvas preview and exported runtime always match

### Window Settings
- Title, size, `fg_color` live preview, resizable, frameless
- Builder Grid: style (`none / dots / lines`), colour, spacing — design-time only
- Project name → Main Window title (Save As renames both)

### Properties panel
- Grouped sections with paired rows (X+Y, W+H, etc.)
- Modular editors: number, color, boolean, multiline, anchor, compound, enum, image, orientation, segment values
- Drag-scrub on number rows (Photoshop-style), Alt = fine-scrub
- Live color picker with eyedropper

### Full Undo / Redo
- **History panel** (`F9`) — live-updating stack view
- **Edit menu** with smart enable/disable
- Every mutation tracked: add, delete, move, resize, rename, paste, duplicate, z-order, reparent, visibility, lock
- Rapid sequences collapse into single undo steps

### Project lifecycle
- `.ctkproj` save / load (JSON, versioned)
- Recent files menu
- Code export to runnable Python
- Preview button (`Ctrl+R`) — spawns the exported file in a subprocess
- Dirty tracking + unsaved-changes prompt

### Inspectors
- **Object Tree** (`F8`) — hierarchical widget list with visibility/lock icons, search + filter, drag-to-reparent, multi-select
- **History** (`F9`) — undo / redo stack
- **Properties panel** — per-widget editors
- **Tools → Inspect CTk Widget…** — side-by-side comparison of every palette widget against the actual CTk constructor signature, flagging exposed / CTk-only / builder-helper rows

### Keyboard shortcuts

All shortcuts work with Latin and non-Latin keyboard layouts.

| Shortcut | Action |
|---|---|
| `Ctrl+N` | New project (dialog) |
| `Ctrl+O` | Open project |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save As |
| `Ctrl+Q` | Quit |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Ctrl+C` | Copy selected |
| `Ctrl+V` | Paste |
| `Ctrl+X` | Cut |
| `Ctrl+D` | Duplicate |
| `Ctrl+I` | Rename selected |
| `Ctrl+A` | Select all (active document) |
| `Delete` | Delete selected |
| `Arrow keys` | Nudge 1 px |
| `Shift+Arrow` | Nudge 10 px |
| `Ctrl+R` | Preview whole project |
| `Ctrl+P` | Preview active dialog |
| `Ctrl+M` | Add Dialog |
| `Ctrl+Shift+I` | Documentation |
| `F8` | Toggle Object Tree (floating) |
| `F9` | Toggle History (floating) |
| `Escape` | Deselect |
| `Ctrl+Wheel` | Zoom in / out |

### Run Python Script
- File menu + toolbar entry (`tv-minimal-play` icon) launches any `.py` / `.pyw` as a subprocess — quick way to test exported builds without leaving the builder. Last-used directory persists.

### Widgets (19 palette entries)
12 leaf widgets — `CTkButton`, `CTkLabel`, `CTkEntry`, `CTkTextbox`, `CTkCheckBox`, `CTkRadioButton`, `CTkSwitch`, `CTkSegmentedButton`, `CTkSlider`, `CTkProgressBar`, `CTkComboBox`, `CTkOptionMenu` — plus 4 layout-preset Frames (`place` / `vbox` / `hbox` / `grid`), 2 nested-children containers (`CTkScrollableFrame`, `CTkTabview`), and an `Image` composite (`CTkLabel + CTkImage`).

## Tech stack

- **Python 3.12+** (tested on 3.14)
- **CustomTkinter** 5.2.2+
- **Pillow** (icon tinting)
- **ctk-tint-color-picker** (color picker dialog)

## Install

```bash
git clone https://github.com/kandelucky/ctk_visual_builder.git
cd ctk_visual_builder
pip install -r requirements.txt
python main.py
```

## Documentation

Widget documentation is being rewritten. The [per-version changelog](docs/todo/done.md) is the most up-to-date reference until the new docs land.

## Roadmap

### Done
- [x] Three-panel layout + toolbar
- [x] Drag to move / resize / arrow nudge
- [x] Widget palette with drag + click to add
- [x] Properties panel (Treeview-based, modular editors, drag-scrub)
- [x] Object Tree inspector with hierarchy, drag-to-reparent, multi-select
- [x] Save / Load + recent files
- [x] Code export to runnable Python
- [x] Live preview (`Ctrl+R`)
- [x] All 19 widget descriptors (12 leaf + 4 frame variants + 2 containers + Image)
- [x] Full Undo / Redo with History panel
- [x] Copy / Paste / Duplicate / Bring-to-Front / Send-to-Back
- [x] Reparent via drag — including across documents
- [x] Visibility / Lock toggles
- [x] Light / Dark theme toggle
- [x] Window Settings — title, size, fg_color, resizable, frameless, builder grid
- [x] Multi-document canvas — Main Window + N Dialogs per project
- [x] Layout managers — `place` / `vbox` / `hbox` / `grid` with WYSIWYG canvas rendering
- [x] Grid drag-to-cell + cursor-cell snap + auto-next-free-cell assignment
- [x] **Select / Edit tool split** — Edit mode shows resize handles and rebuilds the Properties panel on every selection; Select mode stays lightweight (chrome only) for fast pick-and-move work
- [x] **Multi-select** — `Ctrl`+click toggles a widget in / out of the selection; click-and-drag any selected widget moves the whole group (same delta for every place-managed widget, including across documents)
- [x] **Unity-style drill-down selection** — the first click on a nested hierarchy lands on the outermost container, subsequent clicks descend one level; sibling clicks inside an already-entered container select directly
- [x] **Drag safety** — drops outside a document are rejected with red-tinted ghost feedback; container children extract-only (dropping one elsewhere hops to the source document's root at the cursor, not to another container)
- [x] **Inspectors & Dialogs (Area 8)** — Object Tree + History panels docked, Form menu redesign, About dialog, per-dialog Preview, 7 keyboard shortcuts
- [x] **CTkScrollableFrame + CTkTabview as real containers** — drop children directly inside, per-tab `parent_slot` for Tabview (drag / reparent / undo all preserve it), Tab Bar Position + Align controls
- [x] **Scrollable dropdown popup** for `CTkComboBox` + `CTkOptionMenu` — Toplevel-based popup that matches the parent width, scrolls past `max_visible` items, configurable border / radius / item align / offset; OptionMenu also gains a two-click selection model in the builder

### Next
- [ ] Portable assets — package fonts / icons / images alongside `.ctkproj`
- [ ] Alignment tools — align left/right/center + distribute
- [ ] Marquee selection, snap-to-grid, alignment guides, asset manager
- [ ] Custom user widgets, variables panel, event handlers, templates, plugin system
- [ ] Distribution — PyInstaller bundles, Windows + macOS installers, auto-updater

## License

MIT
