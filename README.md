# CTk Visual Builder

A desktop visual designer for **CustomTkinter** — drag and drop widgets onto a canvas, edit their properties live, and export the result as clean runnable Python.

> **Status:** v0.0.8 — active development. Phase 4 (Undo/Redo) complete. 13 of 15 widget descriptors shipped, drag + resize + nested containers, full history, code export, and live preview all working.

[![v0.0.8](docs/history/v0.0.8.png)](docs/history/v0.0.8.png)

## Features

### Canvas + editing
- Real CTk widgets rendered on a tk Canvas (preview = reality)
- Drag to move, resize via 8 handles, arrow-key nudge (1 px / 10 px with Shift)
- Nested containers — drop widgets inside `CTkFrame`, composite widgets wired through `canvas_anchor`
- Reparent by dragging a widget from one container to another
- Multi-select from the Object Tree with sync'd workspace highlighting
- Zoom controls + dot grid, hand-tool pan, middle-mouse pan
- Georgian keyboard fallback — `Ctrl+Z/Y/C/V/...` work regardless of layout

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

### Widgets (13 of 15 implemented)
`CTkButton`, `CTkLabel`, `CTkFrame`, `CTkEntry`, `CTkCheckBox`, `CTkRadioButton`, `CTkComboBox`, `CTkOptionMenu`, `CTkSlider`, `CTkProgressBar`, `CTkSegmentedButton`, `CTkSwitch`, `CTkTextbox`, plus partial `CTkScrollableFrame` and `CTkTabview` (render + all style properties work, nesting children is limited — see [widget docs](docs/widgets/README.md)).

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
    │   ├── widget_node.py            # node + JSON serialization
    │   ├── project.py                # project state + selection + clipboard
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
        ├── workspace.py              # center — canvas + drag/resize/events
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
- [x] Save / Load (`.ctkproj`) + recent files
- [x] Code export to runnable Python
- [x] Live preview (`Ctrl+R`)
- [x] 13 of 15 widget descriptors
- [x] Full Undo / Redo with History panel
- [x] Edit menu + Ctrl+Z / Ctrl+Y (Georgian keyboard support)
- [x] Copy / Paste / Duplicate / Bring-to-Front / Send-to-Back
- [x] Reparent via drag into container
- [x] Visibility / Lock toggles
- [x] Light / Dark theme toggle

### Next
- [ ] Remaining widgets — `CTkScrollableFrame` + `CTkTabview` nesting (composite widget integration)
- [ ] Window Settings panel (title, size, frameless, resizable, bg_color, appearance_mode)
- [ ] Layout managers — `place` / `pack` / `grid` per widget with visual indicator
- [ ] Polish — marquee selection, snap-to-grid, alignment guides, asset manager
- [ ] Advanced — custom user widgets, variables panel, event handlers, templates, plugin system

## License

MIT
