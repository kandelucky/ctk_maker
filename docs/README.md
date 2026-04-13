# CTk Visual Builder — Documentation

Welcome to the **CTk Visual Builder** documentation. This is a drag-and-drop
visual designer for [CustomTkinter](https://customtkinter.tomschimansky.com/)
that exports clean Python code.

## Quick links

- **Project README:** [../README.md](../README.md)
- **Roadmap / TODO:** [../TODO.md](../TODO.md)
- **Source tree:** [../app/](../app/)

## Sections

### Widgets

Per-widget reference for every CTk widget supported by the builder.
Each page describes the property schema the builder renders in the
Properties panel, the default values, and how the descriptor translates
schema props into the actual CTkButton (or other) constructor kwargs.

→ [Widget catalog](widgets/README.md)

### Design direction

We explicitly clone the UX of **Qt Designer (classic)** — not Qt Design
Studio — because Qt Designer is widget-based (matching CTk's model),
battle-tested, and familiar to Python developers via PyQt. The full
mapping of Qt Designer features to our phases lives in
[../TODO.md](../TODO.md) under **Reference: Qt Designer**.

### Icons

The builder uses [Lucide](https://lucide.dev) (MIT) for all internal UI
icons. Fixed parameters for consistency:

- Size: **16 × 16** px
- Stroke width: **2** (Lucide default)
- Color: **#888888** (matches group header gray)
- Format: PNG with RGBA

Downloaded icons live in [`../app/assets/icons/`](../app/assets/icons/).
The loader is [`../app/ui/icons.py`](../app/ui/icons.py).

## Project overview

### Architecture

- **MVC + Command pattern** — model in `app/core/`, views in `app/ui/`,
  widgets in `app/widgets/`
- **Widget Registry pattern** — each CTk widget has a single descriptor
  file that declares: type name, default properties, property schema
  (for the Properties panel), and `transform_properties` (to convert
  schema props → CTk constructor kwargs). Adding a new widget = one
  new file, no core changes.
- **Event bus** (pub/sub) — decouples Model → View updates
- **Real CTk widgets on tkinter Canvas** via `create_window` —
  **preview = reality**. Whatever you see in the workspace is exactly
  what the exported code will render.
- **JSON save format** with `"version": 1` field for forward migration
  (Phase 2)

### Panels

- **Palette** (left) — drag widgets onto the workspace
- **Workspace** (center) — tkinter Canvas with real CTk widgets rendered
  via `create_window`; selection, drag, resize, keyboard nudge
- **Properties** (right) — schema-driven editor for the selected widget

### Key libraries

| Library | Purpose |
|---|---|
| [customtkinter](https://customtkinter.tomschimansky.com/) | All rendered widgets in the workspace |
| [Pillow](https://pillow.readthedocs.io/) | Image loading for `CTkImage` |
| [ctk-tint-color-picker](https://pypi.org/project/ctk-tint-color-picker/) | Color picker dialog (Photoshop-style) |
| [Lucide Icons](https://lucide.dev/) | UI icons |

## Status

**Phase 1 complete.** Core interactions, Properties panel polish, and
CTkButton descriptor fully implemented and documented. Phase 2 (Toolbar
+ Save/Load + Python export) is next.

Check [TODO.md](../TODO.md) for the detailed roadmap.
