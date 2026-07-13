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
├── Variables (Global + Local)
├── Scripts (CTkScript classes in the top-level scripts/ folder)
├── Assets (images, fonts, icons)
└── Components (reusable widget bundles)
```

## Project

A **Project** is a folder on disk holding one or more **Pages**, plus shared assets. The folder layout:

```
MyProject/
├── project.json                    Multi-page metadata (page list, name, etc.)
├── scripts/                        Your CTkScript classes (you own this folder)
│   ├── counter.py                     class Counter(CTkScript)
│   └── services/
│       └── auth.py                    sub-package — class Auth(CTkScript)
└── assets/
    ├── pages/
    │   ├── login.ctkproj           Page 1
    │   ├── dashboard.ctkproj       Page 2
    │   └── settings.ctkproj
    ├── images/                     Shared image pool
    ├── fonts/                      Shared font files
    ├── icons/                      Lucide icons used in this project
    └── components/                 .ctkcomp library
        └── *.ctkcomp
```

The `scripts/` folder sits at the project root, **outside** `assets/`
(which holds media only). CTkMaker never writes into your script files —
it only AST-scans them for the attach + Function pickers and copies the
folder into the export.

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
- **Handlers** — event → method(s) on an attached CTkScript. See Event Handlers below.
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

- **Global** — visible to every window in **one page** (Main + Dialogs). Each page owns its own set; switching pages reloads a different set. Best for shared state inside a screen (form values, theme, signed-in flag). On export: created on the Main Window class of the page; Toplevels read via `self.master.var_X`. There is no cross-page scope — pages export as independent `.py` files.
- **Local** — visible only to widgets in one specific window. Lives on the Document. Best for per-window state (form field bindings, slider values, dialog-internal flags). On export: created on the owning class as `self.var_X`.

The Variables window (F11) shows both, separated by a blue **Global** tab and an orange **Local: \<doc\>** tab.

### Binding

Bind a property to a variable from the Properties panel:

1. Click the ◇ chip next to the property's value
2. Pick a variable from the bind menu (or "+ Create new global/local variable…")
3. The chip turns ◆ — colored blue (global) or orange (local)

Bound properties: `text` (Label), `initial_value` (Entry, Slider, ComboBox, OptionMenu), `initially_checked` (Switch, CheckBox), `segment_initial` (SegmentedButton). See [DATA_MODEL.md — BINDING_WIRINGS](DATA_MODEL.md#binding_wirings-table--variablespy163) for the full table.

Properties not in the binding table can still bind cosmetically — the widget gets the variable's current value at create time but won't auto-update when the variable changes.

### Multi-radio groups

The classic Tk pattern — multiple `CTkRadioButton` widgets sharing a single `IntVar` so only one can be selected at a time. CTkMaker: bind every radio's `variable` slot to the same variable; set each radio's `value` to a unique number. The exporter wires the rest.

## Scripts (CTkScript)

A **Script** is a Python class you write that subclasses `CTkScript`. You attach it to an object — one widget OR the whole window — and bind events to its methods. This is how you add behavior in CTkMaker.

### Where scripts live

A visible top-level `scripts/` folder at the project root (next to `assets/`, not inside it). You own this folder — CTkMaker never writes into your script files.

### Writing one

```python
from ctkmaker import CTkScript

class Counter(CTkScript):
    def on_start(self):
        self.count = 0

    def increment(self):
        self.count += 1
        self.widget.configure(text=str(self.count))
```

### Scope decides what the script sees (strict)

- Attach to a **widget** → the script knows only that widget via `self.widget`. It does NOT know the window. Reusable across widgets.
- Attach to the **window** → the script knows the window via `self.window`, so it can reach every widget on it (cross-widget / form logic).

You pick what to attach to; that alone decides scope — there is no "knows-window" toggle.

### Attaching + binding events

1. Select a widget (or the window) → Properties panel → **Scripts** group.
2. `+ Add Script` → create a new script or attach an existing one. `Edit [file.py]` opens it in your editor; `✕` detaches.
3. In the **Events** group, add an event and pick the script + a public method (Unity `OnClick` style). Press → that method runs.

The binding is saved in the project file (`.ctkproj`) — never written into your script. Handler methods take no forced parameters; read state via `self.widget` / `self.window`.

### Lifecycle

- `on_start(self)` — runs once after the object is built.
- `on_close(self)` — runs when a window script's window is closed.

### Script Variables (fields)

A script can declare **exposed fields** — a class-level `tk.Variable` annotation with no value:

```python
class Counter(CTkScript):
    score: tk.IntVar      # exposed field
    title: tk.StringVar
```

In the Properties panel each attached script gets its own **`ClassName (Script)`** group (Unity-Inspector style) listing those fields. Per field you either:

- **type an inline value** (box / checkbox / colour swatch) — a fresh `tk.Variable` just for this object, or
- **🔗 link a project variable** (type-filtered: globals + this window's locals) — the *shared* `tk.Variable`, so widgets bound to it stay in sync. A `str` field also accepts `color` variables (both ride on `StringVar`).

The binding is stored in `.ctkproj` by variable **UUID** (rename-safe), never in your script. At export each field is set before `on_start`: `self.score = self.var_hp` (bound), `tk.IntVar(value=5)` (inline), or `tk.IntVar()` (unset). `on_start` can read / write / `trace_add` them as live tk Variables.

### Export

Self-contained: the `CTkScript` base is inlined as `ctkmaker.py` and your `scripts/` folder is copied next to the exported window — the exported app needs no CTkMaker install.

## Event Handlers

A widget **Handler** is a CTkScript method invoked when the user interacts with the widget — bound Unity `OnClick`-style by picking the attached script's method (no forced parameters; read state via `self.widget` / `self.window`).

Two event styles:

- **`"command"`** — click-style. Single callback bound via constructor kwarg (`command=...`). Used by Button, Switch, CheckBox, RadioButton, Slider, ComboBox, OptionMenu, SegmentedButton.
- **`"bind:<sequence>"`** — Tk bind. Bound post-construction via `widget.bind(seq, fn, add="+")`. Used for Entry's `<Return>`, key/mouse events on Textboxes, etc.

A widget can have multiple handlers per event (they fan out via lambda chain or repeated `.bind` with `add="+"`).

### Attaching a handler

1. Select the widget (or the window) on the canvas.
2. Properties panel → **Scripts** group → attach a CTkScript (see [Scripts](#scripts-ctkscript) above).
3. Properties panel → **Events** group (below the Behavior cluster, near the bottom) → click `[+]` on an event → pick the script + a public method.

The binding is stored in the `.ctkproj` (never written into your script). The exporter wires the rest:

```python
self.button_submit = ctk.CTkButton(
    self,
    text="Submit",
    command=self._script_0.on_submit,    # ← wired automatically
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

## Per-window vs page-wide — quick lookup

| Thing | Lives on | Visible to |
|---|---|---|
| Widget | Document | Its own document |
| Local Variable | Document | All widgets in that document |
| Global Variable | Page | Every widget in every document of **that one page** |
| Handler | WidgetNode | A method on an attached CTkScript |
| Script | `<project>/scripts/*.py` | Attached per object (widget or window) |
| Component | `<project>/components/*.ctkcomp` | All projects (after import) |
| Asset | `<project>/assets/{images,fonts,icons}/` | Every page in this project |

## Builder workspace

UX layered on top of the model — runtime-only, never persisted to the export.

### Selection

- **Single click** sets the primary selection. **Marquee** — drag a rectangle on empty canvas to add to the selection.
- **Groups (Ctrl+G / Ctrl+Shift+G)** bind a same-parent selection together. Clicking any member targets the whole group; a fast follow-up click drills to one member. Object Tree shows them as a virtual `◆ Group (n)` parent with members nested in soft orange. Group invariant lives in [SelectionController](../../app/ui/selection_controller.py).
- **Edit tool + click on the focused window's empty area** (chrome bg or body, no widget under the cursor) opens that window's Properties panel — same destination as the ⚙ icon. The click must land on the window that's already focused: clicking a non-focused window only focuses it (and exits ghost mode if it's ghosted) per the two-step rule. Drag-past-`DRAG_THRESHOLD` still kicks off a marquee / move gesture instead.

### Drag and snap

- While dragging a widget, **cyan smart-guide lines** snap its edges and centre to siblings and to the container. Hold **Alt** to bypass.
- Drag-reparent works **across windows** on the shared canvas. When the moved widget carries local-variable bindings, a **migration dialog** asks whether to preserve them on the new doc — see `migrate_local_var_bindings` and the `local_variables_migrated` event.

### Preview

- **Ctrl+R / F5** runs the project as a real CTk app — exporter writes a temp `.py` and launches a `python` subprocess. **Ctrl+P** previews only the active doc (main window or single dialog).
- **F12** floating Screenshot button captures the client area as PNG. The button itself is injected via `inject_preview_screenshot=True` (see [EXPORT.md](EXPORT.md)).
- **View → Console** tails preview stdout/stderr inline; toolbar checkbox optionally auto-clears on each preview start (persisted setting). **Ctrl+F** (or the toolbar 🔍 button) opens a slide-in search bar.

### Window visibility

- **Window → Visibility** menu (or chrome chevron-down) **minimizes** a doc to a chip on the bottom tab strip — click the chip to restore. Persisted as [`Document.collapsed`](../../app/core/document.py).
- Every doc carries a **ghost statusbar** along its bottom edge — `● Live  —  click to ghost` (neutral grey) or `● GHOST  —  click to restore live widgets` (bright carrot). Click the strip *or* the desaturated PIL screenshot to flip state. Frees Tk resources without losing visual context; persisted as `Document.ghosted` + base64 PNG in `ghost_image`. Drawn in [render.py](../../app/ui/workspace/render.py) `_draw_ghost_statusbar`; freeze/unfreeze in [ghost_manager.py](../../app/ui/workspace/ghost_manager.py).
- **Two-step click rule** — clicking a ghosted doc (statusbar or screenshot) only focuses it on the first click; a second click on the same now-active ghost actually unghosts. Live → ghost stays one-click since the operation is cheap and is the action the user typically wants. Prevents a stray click while panning from rebuilding every widget in the doc.
- **Screenshot persistence** — every fresh capture is cached on `Document._cached_ghost_pil`. Toggling ghost ON triggers an immediate `save_project` ([main_files.py](../../app/ui/main_files.py) `FilesMixin._on_ghost_toggled_save`, reachable on `MainWindow`) so the base64 PNG lands in `.ctkproj` without waiting for autosave. Next load reads it back and `GhostManager.freeze_from_cache` places it verbatim — the user sees the exact image they left behind instead of whatever pixels happened to sit at those coords during startup.
- **Live-window lag hint** — when 2+ live (non-ghost, non-collapsed, **non-empty**) docs share the canvas, the bottom zoom bar shows an `N live windows — click the ● Live strip to ghost` label next to the percentage. Empty docs (no `root_widgets`) cost nothing in `apply_all` and would freeze to indistinguishable empty screenshots, so they sit outside the count. Three escalating tiers: **2 docs** → muted-grey `ⓘ` (informational), **3–9** → amber `⚠` (warning), **10+** → red `⚠` (danger). Pure state-based, no timing heuristics — appears at project load too, not just after user adds a doc. Label itself is clickable (`hand2` cursor) and fires a bulk-ghost batch over every live doc. Progress is reported **inside the same label** (`Ghosting N / M — doc_name (Esc to cancel)`) — no modal overlay, because an overlay would land in every screenshot (`ImageGrab` reads on-screen pixels). Esc cancels via a permanently-installed `bind_all` guarded by a module-level active-batch list. Restores the original active doc when done; one-bad-doc failures are logged and skipped, never abort the batch. Implemented in [bulk_ghost.py](../../app/ui/workspace/bulk_ghost.py); the label takeover is coordinated via `ZoomController.begin_batch` / `set_batch_text` / `end_batch`. Implemented in [zoom_controller.py](../../app/ui/zoom_controller.py) `refresh_ghost_hint`.

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
