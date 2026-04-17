# CTk Visual Builder

A desktop visual designer for **CustomTkinter** — drag and drop widgets onto a canvas, edit their properties live, and export the result as clean runnable Python.

> **Status:** v0.0.13 — active development. Phase 6.5 ships WYSIWYG grid rendering with drag-to-cell UX (cursor-cell snap + palette-drop targeting + auto-next-free-cell on widget add), plus runtime parity (`grid_rowconfigure` + `grid_columnconfigure` + `pack_propagate(False)` + `grid_propagate(False)` in the exporter). Phase 6.6 (post-6.5 polish) fixes grid centring via hand-computed `.place()` coords (CTkFrame's internal canvas was breaking tk's grid math) + `uniform="col"/"row"` in the export so empty cells stay equal-sized. The 1342-line `workspace/core.py` was further reduced to 998 lines by extracting `widget_lifecycle.py`.

[![v0.0.9](docs/history/v0.0.9.png)](docs/history/v0.0.9.png)

## Features

### Canvas + editing
- Real CTk widgets rendered on a tk Canvas (preview = reality)
- Drag to move, resize via 8 handles, arrow-key nudge (1 px / 10 px with Shift)
- Nested containers — drop widgets inside `CTkFrame`, composite widgets wired through `canvas_anchor`
- Reparent by dragging a widget from one container to another, including across documents
- Multi-select from the Object Tree with sync'd workspace highlighting
- Zoom controls + dot grid, hand-tool pan, middle-mouse pan
- Georgian keyboard fallback — `Ctrl+Z/Y/C/V/...` work regardless of layout

### Multi-document canvas
- One `.ctkproj` holds a `Main Window` (`ctk.CTk`) plus any number of `Dialogs` (`ctk.CTkToplevel`), all visible on the same canvas
- Per-document chrome (title bar, settings, close) with drag-to-move, active highlight, stacked correctly when forms overlap
- `+ Add Dialog` on the workspace toolbar (plus `Form → Add Dialog`) with preset picker (Alert / Compact / Medium / Settings / Wizard / Same as Main)
- Smart widget masking — widgets sitting behind another form are hidden automatically so the active form always reads cleanly
- Object Tree focused on the active document, with a bottom status strip showing which form is being edited
- Click the chrome ⚙ to open the Window settings for that document; ✕ closes dialogs (confirm prompt) or the whole project when pressed on the main window
- Undo / redo covers Add Dialog, Remove Dialog, chrome drag, and cross-document widget drag

### Window Settings
- Virtual `Window` node with a full property schema: title (name entry), size, `fg_color`, `resizable_x / y`, `frameless`
- Builder Grid group: style (`none / dots / lines`), colour, spacing — grid is design-time only, never emitted in the export
- Live preview — `fg_color` recolours the document rectangle the moment you change it
- Unified project name → Main Window title (Save As renames both in lockstep)

### Properties panel (v2)
- `ttk.Treeview` backbone with flicker-free persistent overlays
- Modular editor registry: number, color, boolean, multiline, anchor, compound, enum, image, orientation
- Drag-scrub on number rows (Photoshop-style), Alt = fine-scrub
- Live color picker with eyedropper, style preview (bold/italic/underline/strike)
- `disabled_when` lambdas that dim dependent rows in sync

### Full Undo / Redo
- **History panel** (`F9`) — live-updating stack view with current-state marker
- **Edit menu** with smart enable/disable based on selection, clipboard, history
- **Toolbar** undo/redo buttons with icon-tint state swap
- Every mutation tracked: add, delete (single + multi), move, resize, arrow nudge, property change, rename (inline + dialog), paste, duplicate, bring-to-front / send-to-back, reparent, visibility, lock
- Coalescing (0.6s window) collapses bursts of nudges and typing into single undo steps
- Drag-scrub suspension so slider live-preview commits as one entry on release

### Project lifecycle
- `.ctkproj` save / load (JSON, versioned)
- Recent files menu
- Code export to runnable Python (`.py` that executes and renders identically)
- Preview button (`Ctrl+R`) — spawns the exported file in a subprocess
- Dirty tracking + unsaved-changes prompt

### Inspectors
- **Object Tree** (`F8`) — hierarchical widget list with visibility/lock icons, search + filter, drag-to-reparent, multi-select copy/paste
- **History** (`F9`) — undo stack, current-state marker, redo stack
- **Properties panel** — per-widget schema-driven editors

### Widgets (14 of 15 implemented)
`CTkButton`, `CTkLabel`, `CTkFrame`, `CTkEntry`, `CTkCheckBox`, `CTkRadioButton`, `CTkComboBox`, `CTkOptionMenu`, `CTkSlider`, `CTkProgressBar`, `CTkSegmentedButton`, `CTkSwitch`, `CTkTextbox`, plus a builder-specific `Image` descriptor that wraps `CTkLabel` with a `CTkImage` and ships a default PNG so a fresh drop is immediately visible. `CTkScrollableFrame` and `CTkTabview` render with every colour / label / scrollbar / tab-name property but their nested-children path is still partial — see [widget docs](docs/widgets/README.md).

## Tech stack

- **Python 3.12+** (tested on 3.14)
- **CustomTkinter** 5.2.2+
- **Pillow** (icon tinting, transparent PNGs)
- **ctk-tint-color-picker** (color picker dialog — spun off as a separate PyPI package)
- `tkinter` Canvas + `ttk.Treeview` for the inspector tables

## Project layout

```
ctk_visual_builder/
├── main.py                           # entry point
├── requirements.txt
├── docs/
│   ├── widgets/                      # per-widget reference pages
│   └── history/                      # version screenshots
└── app/
    ├── core/                         # pure model, no UI deps
    │   ├── event_bus.py              # pub/sub
    │   ├── widget_node.py            # widget node + JSON serialization
    │   ├── document.py                # Document dataclass (per-form state)
    │   ├── project.py                # project state + documents + clipboard
    │   ├── commands.py               # undo/redo command classes
    │   └── history.py                # history stack with coalescing
    ├── io/
    │   ├── project_loader.py         # .ctkproj → Project
    │   ├── project_saver.py          # Project → .ctkproj
    │   └── code_exporter.py          # Project → runnable .py
    ├── widgets/                      # one descriptor per CTk widget
    │   ├── base.py                   # WidgetDescriptor base
    │   ├── registry.py
    │   └── ctk_*.py                  # 15 descriptors
    └── ui/
        ├── main_window.py            # menubar + three-panel layout
        ├── toolbar.py                # icon-only top toolbar
        ├── palette.py                # left — widget palette
        ├── workspace/                # center — canvas + drag/resize/events (6-file package)
        │   ├── core.py               # Workspace facade + property-change router
        │   ├── widget_lifecycle.py   # widget_added / removed / reparented handlers
        │   ├── drag.py               # drag / drop / grid-cell snap
        │   ├── layout_overlay.py     # geometry manager wiring for nested children
        │   ├── render.py             # canvas redraw (document rects + chrome)
        │   └── __init__.py           # re-exports
        ├── selection_controller.py   # selection chrome + resize handles
        ├── zoom_controller.py        # zoom math + status-bar controls
        ├── properties_panel_v2/      # right — Treeview-based property editor
        │   ├── panel.py
        │   ├── drag_scrub.py         # horizontal number scrubber
        │   ├── editors/              # per-type inline editors
        │   ├── overlays.py           # persistent color / image / enum chrome
        │   └── format_utils.py
        ├── object_tree_window.py     # F8 — hierarchical inspector
        ├── history_window.py         # F9 — undo/redo stack view
        ├── dialogs.py                # New project, Rename, etc.
        ├── startup_dialog.py
        └── icons.py                  # Lucide PNG loader with color tinting
```

## Architecture

- **Model / View split** — `app/core` is pure data with an `EventBus` pub/sub. `app/ui` subscribes to `widget_added`, `widget_removed`, `selection_changed`, `property_changed`, `widget_reparented`, `widget_z_changed`, `history_changed`, etc.
- **Widget Registry** — adding a new CTk widget = one new descriptor file (subclass `WidgetDescriptor`), import + register. No other files change. The properties panel, code exporter, palette, and object tree all read the registry dynamically. See [`docs/widgets/adding-new-widget.md`](docs/widgets/adding-new-widget.md).
- **Command pattern** — mutations are applied at call sites and then pushed to `project.history` as `Command` objects. Each command knows how to `undo` / `redo` itself. Widget IDs stay stable across delete + undo so every observer's references survive.
- **Coalescing** — `Command.merge_into()` with a 0.6 s time window absorbs rapid sequences into single entries (arrow nudges, inline-rename typing, drag-scrub moves).
- **Composite widget anchoring** — `CTkScrollableFrame` and similar widgets expose an outer container via `canvas_anchor()` that the workspace uses for canvas embedding, event binding, and selection bbox, while the inner widget is what properties configure.
- **Real CTk widgets on Canvas** via `canvas.create_window()` — no fake rendering layer. What you see is what will export.

## Install

```bash
git clone https://github.com/kandelucky/ctk_visual_builder.git
cd ctk_visual_builder
pip install -r requirements.txt
python main.py
```

## Documentation

- [Widget reference](docs/widgets/README.md) — one page per CTk widget with property tables
- [Adding a new widget](docs/widgets/adding-new-widget.md) — 12-step guide
- [Version history](docs/history/README.md) — screenshots per release

## Roadmap

### Done
- [x] Three-panel layout + toolbar
- [x] Drag to move / resize / arrow nudge
- [x] Widget palette with drag + click to add
- [x] Properties panel v2 (Treeview-based, modular editors, drag-scrub)
- [x] Object Tree inspector with hierarchy, drag-to-reparent, multi-select
- [x] Save / Load (`.ctkproj` — v1 + v2) + recent files
- [x] Code export to runnable Python (multi-class for multi-document projects)
- [x] Live preview (`Ctrl+R`)
- [x] 14 of 15 widget descriptors (Image included)
- [x] Full Undo / Redo with History panel
- [x] Edit menu + Ctrl+Z / Ctrl+Y (Georgian keyboard support)
- [x] Copy / Paste / Duplicate / Bring-to-Front / Send-to-Back
- [x] Reparent via drag into container — including across documents
- [x] Visibility / Lock toggles
- [x] Light / Dark theme toggle
- [x] **Window Settings** — title, size, `fg_color` live preview, resizable, frameless, builder grid (style / colour / spacing)
- [x] **Multi-document canvas** — main window + N dialogs in one project, per-form chrome, drag-to-move, active highlight, smart mask for overlapping forms, AddDialog preset picker, cross-document widget drag, `AddDocument` / `DeleteDocument` / `MoveDocument` undo entries
- [x] **Layout managers (stage 1 + 2 + 6.3 split)** — every container (Window, Frame, ScrollableFrame) carries `layout_type` ∈ `place / vbox / hbox / grid` (Qt Designer style — `pack` was split into Vertical / Horizontal for cleaner UX); child widgets gain parent-driven `pack_*` / `grid_*` rows in Properties; code exporter emits the matching `.place()` / `.pack(side="top"/"left")` / `.grid()` call; Properties panel dropdown renders each option with its Lucide icon (`crosshair` / `rows-3` / `columns-3` / `grid-3x3`); canvas shows chrome title suffix, container badges and dashed grid-cell overlays; Object Tree marks containers with `[vbox]` / `[hbox]` / `[grid]`; legacy `pack` projects auto-migrate to `vbox` / `hbox` on load
- [x] **Phase 6.4 — Stage 3.1 WYSIWYG + Layout presets** — vbox / hbox Frames now render children with real `pack()` on canvas (no more place-vs-export gap); Palette gains a `Layouts` category with `Vertical Layout` / `Horizontal Layout` / `Grid Layout` presets; child layout rows collapse to a single `stretch` enum (`fixed` / `fill` / `grow`); container gains `layout_spacing`; `pack_propagate(False)` applied to every container so Frames keep their size
- [x] **Phase 6.5 — Grid WYSIWYG + drag-to-cell + runtime parity** — grid Frames render children into real cells on canvas; user pins grid size via `grid_rows` / `grid_cols` (default 2×2, no auto-grow); drag snaps to the cell under the cursor (light-blue outline during drag); palette drops land at the cursor cell; fresh widgets auto-assign to the next free cell; `grid_rowconfigure(weight=1)` + `grid_columnconfigure(weight=1)` + `pack_propagate(False)` + `grid_propagate(False)` emitted at export
- [x] **Phase 6.6 — Grid place-based centring + workspace refactor** — canvas preview for grid children switches from tk `.grid()` to hand-computed `.place()` coords (CTkFrame's internal canvas broke native grid centring); exporter adds `uniform="col"/"row"` so empty cells stay the same size as occupied ones; `Window` drops `layout_type` (absolute positioning only); `WidgetLifecycle` extracted from `workspace/core.py` (-26%)

### Next
- [ ] Remaining widget — `CTkScrollableFrame` + `CTkTabview` nested-children path (composite widget integration)
- [ ] Alignment tools — align left/right/center + distribute (Phase 7)
- [ ] Polish — marquee selection, snap-to-grid, alignment guides, asset manager
- [ ] Advanced — custom user widgets, variables panel, event handlers, templates, plugin system

## License

MIT
