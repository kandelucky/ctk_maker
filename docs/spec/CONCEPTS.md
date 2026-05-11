# CTkMaker — Concepts

User-facing concepts. What things are called, how they nest, what file each one ends up in.

For the implementation behind these concepts, see [DATA_MODEL.md](DATA_MODEL.md). For the export pipeline, see [EXPORT.md](EXPORT.md). For schema-level widget reference, see [WIDGETS.md](WIDGETS.md).

## Overview

```
Project
├── Page (one or more)
│   └── Window (one Main + zero or more Dialogs per page)
│       └── Widget (nested tree)
│
├── Variables (Global)
├── Object References (Global)
├── Assets (images, fonts, icons, scripts, components)
├── Behavior files (one .py per Window — hand-written code)
└── Components (reusable widget bundles)
```

## Project

A **Project** is a folder on disk holding one or more **Pages**, plus shared assets. The folder layout:

```
MyProject/
├── project.json                    Multi-page metadata (page list, name, etc.)
└── assets/
    ├── pages/
    │   ├── login.ctkproj           Page 1
    │   ├── dashboard.ctkproj       Page 2
    │   └── settings.ctkproj
    ├── images/                     Shared image pool
    ├── fonts/                      Shared font files
    ├── icons/                      Lucide icons used in this project
    ├── scripts/                    Per-window behavior files (one folder per page)
    │   ├── login/
    │   │   └── login.py
    │   └── dashboard/
    │       └── dashboard.py
    └── components/                 .ctkcomp library
        └── *.ctkcomp
```

**Single-file projects** (legacy) skip the folder — the whole project is one `.ctkproj` file with no shared assets. New projects always use the folder layout.

## Page

A **Page** is one `.ctkproj` file inside `assets/pages/`. Pages share the project's asset pool (images, fonts, icons) but are independent designs — switching pages closes one and opens the other.

A page typically represents one screen or one feature of an app: `login`, `signup`, `settings`, `dashboard`, `splash`, etc. Pages don't navigate between each other at runtime — that's handled by the user's behavior code or by exporting each page as its own `.py`.

## Window

A **Window** is a Tk window inside a Page. Two kinds:

- **Main Window** — every page has exactly one. Becomes a `class X(ctk.CTk)` in the export. The program's entry point.
- **Dialog** — zero or more per page. Each becomes a `class Y(ctk.CTkToplevel)`. Opened from the Main Window's behavior code via `Y(self)`.

The canvas shows all of a page's windows side-by-side — you design the dialog and the main window in the same view. Switch focus by clicking the window's chrome.

Window properties:

| Property | Effect at runtime | Builder-only? |
|---|---|---|
| `width` / `height` | `geometry("WxH")` | No |
| `fg_color` | window background | No |
| `resizable_x` / `resizable_y` | `resizable(...)` | No |
| `frameless` | `overrideredirect(True)` | No |
| `layout_type` | `place` / `vbox` / `hbox` / `grid` for the window's direct children | No |
| `grid_style`, `grid_color`, `grid_spacing` | design-time grid display | Yes — never exported |
| `alignment_lines_enabled`, `snap_enabled` | drag-time guides | Yes — never exported |

## Widget

A **Widget** is one CTk control on the canvas. Widgets nest into a tree — a `CTkFrame` can hold a `CTkLabel` and three `CTkButton`s; a `CTkTabview` holds children inside named tabs.

Each widget has:

- **Type** — `CTkButton`, `CTkLabel`, `Card`, etc. Drives the property schema.
- **Name** — user-facing label. When valid as a Python identifier, the export uses it as the widget's variable name (`self.<name>`). Otherwise falls back to `<lowercase_type>_<N>`.
- **Position + size** — `x`, `y`, `width`, `height` in pixels (when the parent is `place`-type).
- **Properties** — schema-keyed values (text, fg_color, font, image, etc.). See [WIDGETS.md](WIDGETS.md).
- **Children** — direct children in the tree. Containers only.
- **Handlers** — event → method name(s) on the window's behavior class. See Event Handlers below.
- **Description** — plain-language note. Emitted as Python comments above the widget at export, for AI use.
- **Visibility / Lock / Group** — design-time only. Never exported.

The canvas renders widgets via the same CTk classes the export uses — what you see is what you get.

### Containers

Widgets where `is_container=True` can hold children:

- `CTkFrame` — generic container
- `CTkScrollableFrame` — scrollable container
- `CTkTabview` — children carry a tab name (`parent_slot`)
- `Card` — styled rectangle/rounded/circle container

Containers can also use **layout managers**: `place` (absolute), `vbox` (vertical pack), `hbox` (horizontal pack), `grid` (cells). The layout type controls how the container's direct children are positioned at runtime.

## Variables

A **Variable** is a named, typed shared value (`str` / `int` / `float` / `bool` / `color`). Multiple widgets can bind to the same variable — when one updates the variable, every other bound widget sees the change at runtime.

In Tk terms: variables are `tk.StringVar` / `IntVar` / `DoubleVar` / `BooleanVar` instances. Widgets bind via `textvariable=` or `variable=` constructor kwargs. CTkMaker handles the wiring automatically. The `color` type is `StringVar`-backed (hex `#rrggbb` / `#rgb`) — the type tag only changes the editor surface (swatch + picker in the Variables window) and the bind-picker filter that decides which variables show up on color properties.

### Global vs Local scope

Two scopes:

- **Global** — visible to every window in every page. Lives on the Project. Best for shared app-wide state (current user, theme, language, signed-in flag). On export: created on the Main Window class; Toplevels read via `self.master.var_X`.
- **Local** — visible only to widgets in one specific window. Lives on the Document. Best for per-window state (form field bindings, slider values, dialog-internal flags). On export: created on the owning class as `self.var_X`.

The Variables window (F11) shows both, separated by a blue **Global** tab and an orange **Local: \<doc\>** tab.

### Binding

Bind a property to a variable from the Properties panel:

1. Click the ◇ chip next to the property's value
2. Pick a variable from the bind menu (or "+ Create new global/local variable…")
3. The chip turns ◆ — colored blue (global) or orange (local)

Bound properties: `text` (Label), `initial_value` (Entry, Slider, ComboBox, OptionMenu), `initially_checked` (Switch, CheckBox), `segment_initial` (SegmentedButton). See [DATA_MODEL.md — BINDING_WIRINGS](DATA_MODEL.md#binding_wirings-table--variablespy163) for the full table.

Properties not in the binding table can still bind cosmetically — the widget gets the variable's current value at create time but won't auto-update when the variable changes. (Bigger plumbing arrives with the visual scripting Phase 5.)

### Multi-radio groups

The classic Tk pattern — multiple `CTkRadioButton` widgets sharing a single `IntVar` so only one can be selected at a time. CTkMaker: bind every radio's `variable` slot to the same variable; set each radio's `value` to a unique number. The exporter wires the rest.

## Object References

An **Object Reference** is a typed pointer slot on a window's behavior class — a way for hand-written behavior code to reach a widget by name without manual lookup.

Two scopes (mirroring Variables):

- **Global** — points at a `Window` or `Dialog`. Only valid for top-level documents. Lives on the Project. Lets one window's behavior reach another window.
- **Local** — points at a widget inside one specific window. Lives on the Document.

### Why

Without references, behavior code reaches widgets via attribute access:

```python
def on_submit(self):
    text = self.window.entry_username.get()    # window is the host CTk class
```

That works but couples your code to the widget's internal name. Object References give you a typed slot:

```python
class LoginPage:
    username_entry: ref[CTkEntry] = ref()
    submit_btn: ref[CTkButton] = ref()

    def on_submit(self):
        text = self.username_entry.get()       # cleaner; type-checked in IDEs
```

The exporter emits `self._behavior.username_entry = self.entry_username` after `_build_ui()`, so the slot is populated by the time `setup()` runs.

### Creating

From the Properties panel: click the **+** button next to a widget's name in the Properties header. The Variables window's Object References tab (F11) shows them all and lets you rename / re-target.

For window-level references: Window / Dialog panel has a global toggle in the Properties header.

Name match is verbatim — the `ref[<Type>]` annotation name in the behavior file must equal the Properties-panel ref name exactly. CTkMaker keeps the annotation in sync on create / rename / delete; if you edit the behavior file by hand and drift, the next export warns before the runtime hits `AttributeError`.

## Event Handlers

A widget **Handler** is a method on the window's behavior class invoked when the user interacts with the widget.

Two event styles:

- **`"command"`** — click-style. Single callback bound via constructor kwarg (`command=...`). Used by Button, Switch, CheckBox, RadioButton, Slider, ComboBox, OptionMenu, SegmentedButton.
- **`"bind:<sequence>"`** — Tk bind. Bound post-construction via `widget.bind(seq, fn, add="+")`. Used for Entry's `<Return>`, key/mouse events on Textboxes, etc.

A widget can have multiple handlers per event (they fan out via lambda chain or repeated `.bind` with `add="+"`).

### Behavior file

Hand-written method bodies live at:

```
<project>/assets/scripts/<page_slug>/<window_slug>.py
```

with one class per window:

```python
# assets/scripts/login/login.py
from typing import Generic, TypeVar
T = TypeVar("T")
class ref(Generic[T]):
    """Typed slot — populated by host class after _build_ui()."""

class LoginPage:
    username_entry: ref[CTkEntry] = ref()    # Object Reference

    def setup(self, window):
        # Optional — runs once after the window's _build_ui()
        ...

    def on_submit(self):
        # Hand-written body
        text = self.username_entry.get()
        ...
```

The file is created automatically when you create the window. Methods are added as stubs when you bind a handler; you fill the body in your editor of choice (Settings → Editor lets you pick VS Code / Notepad++ / IDLE).

### Attaching a handler

1. Select the widget on the canvas
2. Properties panel → **Events** group (below the Behavior cluster, near the bottom)
3. Click `[+]` on an event → enter or pick a method name
4. Open in editor (F7 or double-click) to write the body

The exporter wires the rest:

```python
self.button_submit = ctk.CTkButton(
    self,
    text="Submit",
    command=self._behavior.on_submit,    # ← wired automatically
)
```

## Assets

Files referenced by widgets but stored separately:

- **Images** — `<project>/assets/images/`. Referenced in property values as `asset:images/<filename>.png`.
- **Fonts** — `<project>/assets/fonts/`. Imported via Font Picker. System fonts can also be added to the project's font palette.
- **Icons** — `<project>/assets/icons/`. Lucide PNGs picked via the Icon Picker dialog (1700+ available).

Asset references in properties always use the `asset:<kind>/<filename>` token. The runtime + export both resolve relative to the project folder.

When you export, the entire `assets/` folder is copied next to the output `.py` so the relative tokens still resolve.

## Components

A **Component** is a reusable widget bundle saved as a `.ctkcomp` zip file. Use it like a stamp: design once, drop into many projects.

### What's in a component

- The widget tree (one or more widgets — they share a virtual parent so multi-widget fragments stay together)
- Bundled variables (local + global, demoted to local on insert)
- Referenced assets (only those used by the widgets, not the whole asset pool)
- Manifest with name, author, license, version, category

### Saving + inserting

- **Save** — select widgets on the canvas, right-click → "Save as Component". Lives in `<project>/components/`.
- **Insert** — Palette's Components tab → drag onto canvas. UUIDs are regenerated; variable name conflicts surface a Rename / Skip dialog.

A whole window can be saved too; dropping a window component spawns a fresh Toplevel.

### Community Hub

[kandelucky.github.io/ctkmaker-hub](https://kandelucky.github.io/ctkmaker-hub/) — public component library. Browse cards by category, click to preview, download `.ctkcomp.zip`, drop into your project.

To share: **Publish to Community** → MIT agreement form → post in the repo's [Components Discussion](https://github.com/kandelucky/ctk_maker/discussions/new?category=components). A sync workflow picks it up within ~30 minutes.

## Per-window vs project-wide — quick lookup

| Thing | Lives on | Visible to |
|---|---|---|
| Widget | Document | Its own document |
| Local Variable | Document | All widgets in that document |
| Local Object Reference | Document | The behavior file of that document |
| Global Variable | Project | Every widget in every document of every page |
| Global Object Reference | Project | Every behavior file (cross-window references) |
| Handler | WidgetNode | One method on the window's behavior class |
| Behavior file | `assets/scripts/<page>/<window>.py` | One class per window |
| Component | `<project>/components/*.ctkcomp` | All projects (after import) |
| Asset | `<project>/assets/{images,fonts,icons}/` | Every page in this project |

## Builder workspace

UX layered on top of the model — runtime-only, never persisted to the export.

### Selection

- **Single click** sets the primary selection. **Marquee** — drag a rectangle on empty canvas to add to the selection.
- **Groups (Ctrl+G / Ctrl+Shift+G)** bind a same-parent selection together. Clicking any member targets the whole group; a fast follow-up click drills to one member. Object Tree shows them as a virtual `◆ Group (n)` parent with members nested in soft orange. Group invariant lives in [SelectionController](../../app/ui/selection_controller.py).

### Drag and snap

- While dragging a widget, **cyan smart-guide lines** snap its edges and centre to siblings and to the container. Hold **Alt** to bypass.
- Drag-reparent works **across windows** on the shared canvas. When the moved widget carries local-variable bindings, a **migration dialog** asks whether to preserve them on the new doc — see `migrate_local_var_bindings` and the `local_variables_migrated` event.

### Preview

- **Ctrl+R / F5** runs the project as a real CTk app — exporter writes a temp `.py` and launches a `python` subprocess. **Ctrl+P** previews only the active doc (main window or single dialog).
- **F12** floating Screenshot button captures the client area as PNG. The button itself is injected via `inject_preview_screenshot=True` (see [EXPORT.md](EXPORT.md)).
- **View → Console** tails preview stdout/stderr inline; toolbar checkbox optionally auto-clears on each preview start (persisted setting). **Ctrl+F** (or the toolbar 🔍 button) opens a slide-in search bar.

### Window visibility

- **Window → Visibility** menu (or chrome chevron-down) **minimizes** a doc to a chip on the bottom tab strip — click the chip to restore. Persisted as [`Document.collapsed`](../../app/core/document.py).
- The square-check chrome icon toggles **Ghost mode** — live widgets are replaced by a desaturated PIL screenshot at the same canvas position. Frees Tk resources without losing visual context. Persisted as `Document.ghosted`.

## What's design-time only

Things you see in the builder that **don't** survive into the exported `.py`:

- Visibility flag (`visible=False` → still exports)
- Lock flag (`locked=True` → still exports, just rejects edits in the builder)
- Group ID (Ctrl+G — selection grouping)
- Widget descriptions (unless `include_descriptions=True` at export, where they emit as comments)
- Window grid + snap settings
- Component library (only widget instances on the canvas export)
- Recent files / autosave / undo history

## What's required for a window to export

Minimum viable export:

- The window has a name (defaults to `"Main Window"` — exports as `MainWindow` class)
- At least one widget OR a window the user wants to launch as-is

Without any widgets, the export still produces a runnable `.py` — just an empty CTk window with the configured size + title.
