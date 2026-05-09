# CTkMaker — Architecture

CTkMaker is a desktop visual designer for [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) (Python 3.10+, Windows-tested). Drag widgets onto a multi-document canvas, edit properties, attach event handlers, and export to runnable Python code.

This document is the entry point. Deeper detail in:

- [DATA_MODEL.md](DATA_MODEL.md) — persistent classes (Project, Document, WidgetNode, Variable, Reference)
- [EVENT_BUS.md](EVENT_BUS.md) — pub/sub topology
- [EXPORT.md](EXPORT.md) — `.ctkproj` → `.py` pipeline
- [EXTENSION.md](EXTENSION.md) — adding widgets, property editors, components
- [CONCEPTS.md](CONCEPTS.md) — user-facing concepts (Project / Page / Window / Variable / Reference / Handler / Component)
- [WIDGETS.md](WIDGETS.md) — every widget's properties, types, defaults, nuances
- [WINDOW_STYLE.md](WINDOW_STYLE.md) — `ManagedToplevel` base + `style.py` tokens for floating tool windows
- [AI_CHEATSHEET.md](AI_CHEATSHEET.md) — distilled quick reference for AI prompts

## Layers

Top-down. Each layer depends only on layers below it (with two documented exceptions — see [Layer notes](#layer-notes)).

| Layer | Path | Responsibility |
|---|---|---|
| **Entry** | [main.py](../../main.py) | CTk theme + appearance, crash handler, dark titlebar, instantiate `MainWindow`, `mainloop()` |
| **UI** | [app/ui/](../../app/ui/) | `MainWindow`, panels, dialogs, workspace canvas, properties inspector |
| **Model** | [app/core/](../../app/core/) | In-memory project state, event bus, undo/redo, autosave, settings |
| **Widgets** | [app/widgets/](../../app/widgets/) | Per-widget descriptors (schema, defaults, runtime, export rules) |
| **I/O** | [app/io/](../../app/io/) | Project save/load, code export, behavior file generation, component zip pack/unpack |

The PyPI package at [ctkmaker/](../../ctkmaker/) is a name-reservation stub. Runtime entry is always `python main.py`.

## Module map

### `app/core/` — model

| File | Class / role | Purpose |
|---|---|---|
| `project.py` | `Project` | Top-level container — documents, global variables, global object references, event bus, history. Public API contract. |
| `document.py` | `Document` | One window in a project (Main or Toplevel). Widget tree + window properties + local variables + local references. |
| `widget_node.py` | `WidgetNode` | Tree node — properties, children, handlers, group_id. |
| `variables.py` | `VariableEntry`, `make_var_token`, `BINDING_WIRINGS` | Tk `*Var` schema (`str` / `int` / `float` / `bool` / `color`) + `var:<uuid>` token system + property→Tk-kwarg binding map. Cosmetic bindings (no `BINDING_WIRINGS` entry — e.g. `fg_color`) are resolved as literals at build time and rebuilt by `workspace.core` on `variable_default_changed`; wired bindings update live via Tk's `textvariable` / `variable`. |
| `object_references.py` | `ObjectReferenceEntry` | Typed widget references for behavior code. |
| `event_bus.py` | `EventBus` | Pub/sub. Single instance per `Project`. |
| `history.py` | `History` | Undo/redo with coalesce window. |
| `commands.py` | `Command` subclasses | Every undo-able mutation goes through a `Command`. |
| `autosave.py` | autosave timer | Periodic snapshots to `.autosave/` sidecar. |
| `project_folder.py` | folder layout | Multi-page project scaffolding (`project.json`, `assets/pages/`, `assets/scripts/`). |
| `script_paths.py` | path helpers | `<project>/assets/scripts/<page>/<window>.py` resolution. |
| `component_paths.py` | path helpers | `<project>/components/*.ctkcomp` resolution. |
| `recent_files.py` | recent list | `~/.ctk_visual_builder/recent.json`. |
| `settings.py` | settings | `~/.ctk_visual_builder/settings.json` (theme, editor, panel state). |
| `paths.py`, `assets.py` | path / asset helpers | Project-relative asset resolution + token rewriting. |
| `fonts.py`, `colors.py` | runtime helpers | Font registration + color utilities. |
| `alignment.py`, `snap.py` | geometry | Multi-select alignment + snap-guide math. |
| `platform_compat.py` | OS shims | Win32-specific helpers (work-area query, etc.). |
| `screen.py` | DPI / monitor | Cached DPI factor (`get_dpi_factor`), primary monitor work-area + scale-aware `center_geometry`. Single source of truth for OS display metadata. CTk activates DPI awareness itself when `ctk.CTk` is instantiated. |
| `logger.py` | logging | `log_error` to `~/.ctk_visual_builder/logs/`. |

### `app/widgets/` — descriptors

21 widget descriptors (one file per type) registered via [registry.py](../../app/widgets/registry.py). Each declares schema, defaults, and runtime/export hooks. See [EXTENSION.md](EXTENSION.md) and [WIDGETS.md](WIDGETS.md).

### `app/ui/` — interface

| Group | Files | Purpose |
|---|---|---|
| **Main** | [main_window.py](../../app/ui/main_window.py), `main_menu.py`, `main_shortcuts.py`, `_main_window_host.py` | Root window — menu, toolbars, project tab strip, shortcut wiring. |
| **Workspace** | [workspace/](../../app/ui/workspace/) (`core.py`, `render.py`, `drag.py`, `widget_lifecycle.py`, `layout_overlay.py`, `chrome.py`, `controls.py`, `grid_drop_indicator.py`, `collapsed_tabs_bar.py`, `ghost_manager.py`) | Canvas — real CTk widgets via `Canvas.create_window`. `collapsed_tabs_bar.py` mounts a strip above the status bar listing minimised docs as click-to-restore chips. `ghost_manager.py` swaps an inactive doc's live widgets for a desaturated PIL screenshot on canvas (square-check icon on the chrome strip toggles it). |
| **Properties** | [properties_panel/](../../app/ui/properties_panel/) (`panel.py`, `panel_commit.py`, `panel_schema.py`, `editors/*.py`, `overlays.py`, `drag_scrub.py`, `type_icons.py`, `format_utils.py`, `constants.py`, `property_help.py`, `tooltip.py`) | ttk.Treeview-based inspector with overlay editor widgets + label-column hover tooltips. |
| **Floating panels** | `variables_window.py`, `object_tree_window.py`, `history_window.py`, `components_panel.py`, `console_window.py` | F11 / F8 / F10 docked panels + View → Console (in-app preview log). |
| **Tool windows** | `widget_inspector_window.py`, `transitions_demo_window.py`, `color_palette_window.py` | Tools menu. **Inspector** — widget schema (props + inherited methods) for any CTk class. **Transitions Demo** — 6 tabs (Button / Card / Text / Loaders / Popups / Toasts) with 25+ demos sharing one easing + duration control. Generate code exports a self-contained `.py` per demo (imports + easings + `Tween` engine + helpers + animation + `__main__` runner) via the `_assemble_module` builder; popups reuse a `_make_popup` preamble that includes the dark-titlebar `withdraw + deiconify` trick. **Color Palette** — designer reference: 15 named palettes (3 muted variants + black-mono + white-mono + 10 popular schemes — Material / Tailwind / Nord / Dracula / Gruvbox / Tokyo Night / Catppuccin / Solarized / Monokai / One Dark) × 9 colors. Click any swatch to copy hex. Window auto-fits content on first-ever open via `update_idletasks` + `winfo_reqheight` (hardcoded `default_size` is unreliable across DPI/font scaling); subsequent opens restore the user's last size as usual. |
| **Dialogs** | `startup_dialog.py`, `splash.py`, `export_dialog.py`, `new_project_form.py`, `font_picker_dialog.py`, `image_picker_dialog.py`, `lucide_icon_picker_dialog.py`, `bug_reporter.py`, `crash_dialog.py`, `handler_delete_dialogs.py`, 9× `component_*_dialog.py` | Modal flows. |
| **Helpers** | `dialogs.py`, `dialog_utils.py`, `icons.py`, `dark_titlebar.py`, `system_fonts.py` | Shared dialog scaffolding (`safe_grab_set`, `prepare_dialog`/`reveal_dialog` alpha-hide pair) + icon loader + Win32 dark titlebar + `ui_font` / `derive_ui_font` / `derive_mono_font` for cross-platform font kwargs (raw tk + ttk). |

### `app/io/` — persistence + export

| File | Purpose |
|---|---|
| `project_loader.py` | Load `.ctkproj` (v1→v2 migration on load). |
| `project_saver.py` | Save `.ctkproj`. |
| `code_exporter.py` | `.ctkproj` → runnable `.py` (per-window class). 3,242 lines — single-file by design currently; split planned post-v1.0. |
| `scripts.py` | Per-window behavior file generation + AST scan (`assets/scripts/<page>/<window>.py`). |
| `component_io.py`, `component_assets.py` | `.ctkcomp` zip pack/unpack with asset bundling. |

## Entry points

- [main.py:main()](../../main.py) — appearance mode, default color theme, font fallback for non-Latin scripts (Segoe UI on Windows), `_patch_ctk_toplevel_icon`, `install_dark_titlebar_persistence`, `MainWindow()`, crash handlers, `mainloop()`.
- [app/ui/main_window.py:MainWindow](../../app/ui/main_window.py) — instantiates a fresh `Project`, mounts UI, wires shortcuts, subscribes to events, optionally restores recent project.
- [app/core/project.py:Project()](../../app/core/project.py) — empty project ready for `add_widget` / `load_from_dict`.

## Lifecycle

### Startup

```
main.py
  → set_appearance_mode + theme
  → patch CTkToplevel icon
  → install dark titlebar persistence
  → MainWindow()
        → withdraw + alpha=0 (hidden until project loads)
        → SplashScreen (frameless logo + version + Loading...)
        → mount UI panels (toolbar, palette, properties, ...)
        → install shortcut bindings
        → after(120): _show_startup_dialog
              → StartupDialog (recent / new project picker)
              → on_ready callback destroys splash at reveal
              → user picks → MainWindow loads project → alpha=1
  → install crash handlers (sys.excepthook + Tk.report_callback_exception)
  → app.mainloop()
```

Every modal dialog (`ctk.CTkToplevel` and `tk.Toplevel` subclasses except crash_dialog) calls `prepare_dialog(self)` at the top of `__init__` (alpha=0) and `reveal_dialog(self)` after layout settles (force-paint + alpha=1). Centering paths that defer via `after(N, _center_on_parent)` call `reveal_dialog` at the end of the centering method so the window only becomes visible at its final position.

### Edit cycle

```
User input (canvas drag, panel edit, shortcut, menu)
  → UI handler builds a Command
  → Command.do() mutates Project (model)
  → Project.event_bus.publish(...) one or more events
  → UI subscribers re-render (workspace, properties panel, object tree, etc.)
  → History.push(Command) for undo/redo
```

### Save

```
Project.to_dict()
  → json.dump → .ctkproj
  + per-page assets/ folder kept in sync (image / font / icon / behavior file)
```

Multi-page projects: each page is a separate `.ctkproj` under `<project>/assets/pages/`, with shared assets in `<project>/assets/{images,fonts,icons,scripts,components}/` and a top-level `project.json`.

### Export

```
Project (+ optional doc filter)
  → app/io/code_exporter.py:export_project()
  → per-window Python class
  + import from assets/scripts/<page>/<window>.py
  + variable / handler / object-reference wiring
  → runnable .py file (caller writes to disk, optional .zip bundle)
```

See [EXPORT.md](EXPORT.md).

## Layer notes

Two documented exceptions to the strict layering:

1. **`app/core/autosave.py` and `app/core/project_folder.py` import from `app/io/project_saver.py`.** Autosave reuses the same serialization path as the disk save flow. `app/io/` here means *file I/O helpers*, not *upper layer*.
2. **`app/widgets/card.py` calls `app/io/code_exporter._path_for_export`** for image asset path resolution at export time. Stable contract; treat the function as semi-public.

## File-size landmarks

| File | Lines | Note |
|---|---|---|
| `app/io/code_exporter.py` | 3,242 | Single-file; split planned post-v1.0 |
| `app/ui/properties_panel/panel.py` | 2,135 | Panel base + tree management |
| `app/core/project.py` | 1,811 | God-class by design — public API surface |
| `app/ui/properties_panel/panel_schema.py` | 1,160 | Schema-to-tree population |
| `app/ui/properties_panel/panel_commit.py` | 993 | Commit pipeline |

These are intentionally large. Every one has a multi-paragraph module-level docstring explaining structure.

## Mixin pattern

`MainWindow(ShortcutsMixin, MenuMixin, ctk.CTk)` and `PropertiesPanel(CommitMixin, SchemaMixin, ctk.CTkFrame)` — the largest UI classes are composed across files via mixins. Look for the matching `*_mixin.py` / `_main_window_host.py` files when reading the main class.

## Runtime widget overrides

[`app/widgets/runtime/`](../../app/widgets/runtime/) — pure-Python subclasses of CTk widgets that work around CTk / Tk behaviors not reachable from the schema. Each module is standalone (no CTkMaker imports) so [`code_exporter`](../../app/io/code_exporter.py) inlines its source verbatim into generated `.py` files; the same fix applies to preview and exported scripts.

| Override | Fixes |
|---|---|
| [`CircleLabel._create_grid`](../../app/widgets/runtime/circle_label.py) | CTkLabel pads inner text by `min(corner_radius, height/2)` — full-circle / pill labels would squeeze the text. Override zeros corner_radius during grid layout only; the rounded shape draw still uses the real value. |
| [`CircleLabel.__init__`](../../app/widgets/runtime/circle_label.py) | Inner `CTkCanvas` defaults `takefocus=""`; Tk's heuristic admits it via Canvas's class-level key bindings, so `takefocus=True` labels need 2 Tab presses per move. Override sets `_canvas.configure(takefocus=0)` so only the inner `tk.Label` is in the cycle. Also seeds the unified-event-routing state (lazy hover/motion handler lists) and mirrors the inner cursor onto the outer canvas. |
| [`CircleLabel.bind`](../../app/widgets/runtime/circle_label.py) | Upstream `CTkLabel.bind` dual-routes to canvas + inner Label, so `<Enter>`/`<Leave>`/`<Configure>`/`<Map>` fire 2-3 times per logical transition. Override dispatches by event class — hover via state machine + `after_idle` debounce, geometry on outer Frame only (`tkinter.Misc.bind` to skip the dual-bind), focus/key on inner Label, click/wheel deduped by `event.time`. Internal handlers register lazily so zero-bind projects pay no runtime cost. **First instance of a generic event-routing problem affecting every CTk composite widget** — if it spreads to CTkButton/Switch/Slider, extract a shared `UnifiedBindMixin`. |
| [`CircleLabel.configure`](../../app/widgets/runtime/circle_label.py) | `cursor=` kwarg only updates the inner `tk.Label`, leaving the outer canvas's rounded-corner area on the default cursor. Override mirrors the new cursor to the canvas after each `configure(cursor=...)` so `hand2` covers the full label area. |
| [`CircleButton._create_grid`](../../app/widgets/runtime/circle_button.py) | Same corner_radius padding workaround as `CircleLabel`. The takefocus quirk + dual-bind event-routing issues apply here too — not yet patched (follow-up: extend `CircleLabel`'s unified router pattern). |
| [`CircularProgress`](../../app/widgets/runtime/circular_progress.py) | Custom ring-style progress widget — not present in `customtkinter`. |

The `Image` widget uses raw `ctk.CTkLabel` (no override), so the takefocus quirk reappears there if the user enables it.

## Conventions

- **Identifiers:** UUID strings for `WidgetNode.id`, `Document.id`, `VariableEntry.id`, `ObjectReferenceEntry.id`. Stable across save/load.
- **Tokens:** `var:<uuid>` for variable bindings in property values. Resolved at runtime + export.
- **Asset references:** `asset:<kind>/<filename>` (e.g. `asset:icons/save.png`). Resolved against the active project folder.
- **Names vs IDs:** Display names are user-mutable and not unique. IDs are stable. Generated code uses sanitized names; collisions resolved with `<type>_<N>` fallback.
- **Schema versioning:** `.ctkproj` carries `"version"` field. v1 → v2 migration runs on load. Future migrations chain on top.

## Per-user state

Lives in `~/.ctk_visual_builder/` (path NOT renamed during the v0.18.3 product rename, intentional — preserves existing settings):

- `settings.json` — theme, editor preference, panel state
- `recent.json` — recent project paths
- `logs/` — `log_error` output (one file per session)
