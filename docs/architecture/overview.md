# Architecture Overview

> The four layers of CTk Visual Builder and how they talk to each other.

## Layers

```
┌─────────────────────────────────────────────────┐
│  app/ui/       Views — main window, panels      │
├─────────────────────────────────────────────────┤
│  app/widgets/  Widget descriptors (registry)    │
├─────────────────────────────────────────────────┤
│  app/core/     Model, event bus, project state  │
├─────────────────────────────────────────────────┤
│  app/io/       Load, save, export               │
└─────────────────────────────────────────────────┘
```

## `app/core/` — the model

TODO: Describe each module.

- [event_bus.py](../../app/core/event_bus.py) — pub/sub
- [project.py](../../app/core/project.py) — project object
- [widget_node.py](../../app/core/widget_node.py) — tree node
- [settings.py](../../app/core/settings.py) — user settings
- [recent_files.py](../../app/core/recent_files.py) — recents
- [logger.py](../../app/core/logger.py) — logging

## `app/ui/` — the views

TODO: Main window composes the toolbar, palette, workspace, and properties
panel. They communicate via the event bus, not direct references.

## `app/widgets/` — the registry

TODO: Every supported CTk widget has a single descriptor file.
The [registry](../../app/widgets/registry.py) discovers them.
Adding a new widget = one new file, no core changes.

## `app/io/` — persistence

TODO: Loader, saver, code exporter are kept free of UI imports so they can
be unit-tested headlessly.

## Design principles

- **Preview = reality** — real CTk widgets on a tkinter Canvas via `create_window`
- **Schema-driven Properties panel** — zero per-widget UI code
- **Forward-compatible save format** — `"version"` field from day one
- **MVC + Command** (commands TODO in Phase 2)
