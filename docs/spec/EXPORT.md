# CTkMaker — Export Pipeline

How a `.ctkproj` becomes a runnable `.py`. Lives in [app/io/code_exporter/](../../app/io/code_exporter/) plus [app/io/scripts/](../../app/io/scripts/) for CTkScript scanning.

## Entry points

### `export_project` — [code_exporter/\_\_init\_\_.py:880](../../app/io/code_exporter/__init__.py#L880)

```python
export_project(
    project: Project,
    path: str | Path,
    preview_dialog_id: str | None = None,    # show preview floater on this dialog
    single_document_id: str | None = None,   # export one doc instead of all
    as_zip: bool = False,                    # bundle .py + assets/ into .zip
    asset_filter: set[Path] | None = None,   # subset of assets to copy
    inject_preview_screenshot: bool = False, # F12 floater for preview runs
    include_descriptions: bool = True,       # emit Phase 0 description comments
) -> None
```

Top-level entry. Three jobs:

1. Call `generate_code(...)` to build the source string.
2. Write that string to `path` (UTF-8).
3. Copy `<project>/assets/` next to the output file so `asset:images/...` references resolve at runtime.

When `as_zip=True`: runs the same flow into a tempdir, then zips into a `.zip` archive next to `path`.

### `generate_code` — [code_exporter/\_\_init\_\_.py:1087](../../app/io/code_exporter/__init__.py#L1087)

Pure code generation — returns the source as a string. No disk side-effects. Calls `_generate_code_inner` ([:1151](../../app/io/code_exporter/__init__.py#L1151)) which orchestrates per-document emission.

## Output structure

One class per document. Single file holds them all. Layout:

```python
#!/usr/bin/env python3
# (CTkMaker header + version stamp)

import customtkinter as ctk
import tkinter as tk
from PIL import Image
from pathlib import Path

# CTkScript components — one import per distinct attached class
from scripts.counter import Counter

# Optional helpers (only when used)
from scrollable_dropdown import ScrollableDropdown

# Main window class — the first non-toplevel document
class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Only when the project ships custom fonts (assets/fonts/):
        # registered once against the Tk root; Toplevels share it.
        ctk.register_project_fonts(
            self, Path(__file__).resolve().parent / "assets" / "fonts")

        # Window metadata
        self.title("...")
        self.geometry("800x600")
        self.resizable(True, True)

        # Phase 1 — global variables (only on the main window class)
        self.var_username = tk.StringVar(value="")
        self.var_count = tk.IntVar(value=0)

        # CTkScript components — instantiate before _build_ui()
        self._script_0 = Counter()

        # Build UI
        self._build_ui()

        # CTkScript — inject scope, run on_start, wire on_close
        self._script_0.window = self
        self._script_0.on_start()
        self.protocol(
            "WM_DELETE_WINDOW",
            lambda: (self._script_0.on_close(), self.destroy()),
        )

    def _build_ui(self):
        self.label_title = ctk.CTkLabel(
            self,
            text="...",
            font=ctk.CTkFont(family="Inter", size=14),
            textvariable=self.var_username,   # Phase 1 binding
        )
        self.label_title.place(x=20, y=20, width=200, height=24)

        self.button_submit = ctk.CTkButton(
            self,
            text="Submit",
            command=self._script_0.on_submit,  # script_call binding
        )
        self.button_submit.place(x=20, y=60, width=100, height=32)

# Toplevel classes — every is_toplevel=True document
class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master=None):
        super().__init__(master)
        # ... (same shape; globals reach via self.master.var_X)

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    app = MainWindow()
    # settings_dialog = SettingsDialog(app)  # open the 'Settings Dialog' dialog
    app.mainloop()
```

Toplevel constructor lines are emitted commented-out so the user can copy them into an event handler. Font handling is fork-side: when the project has custom fonts, the main class calls `ctk.register_project_fonts(...)` (ctkmaker-core API) right after `super().__init__()` — no theme patching in the generated file. A dialog-only preview (`single_document_id` on a Toplevel) instead builds a hidden `ctk.CTk()` host, registers fonts against it, and mirrors the page globals onto the host before `wait_window`.

## Per-class structure

| Section | When emitted | Source |
|---|---|---|
| `super().__init__()` | always | required |
| `ctk.register_project_fonts(...)` | only if project has custom fonts; main (non-toplevel) class only | fork-side font registration against the Tk root |
| `title` / `geometry` / `resizable` / `frameless` | always | title from `Document.name` — except a main window still named `DEFAULT_MAIN_WINDOW_NAME`, which gets `project.name`; rest from `Document.window_properties` |
| Phase 1 variable instantiation | only if class owns variables | page-globals on main window class only (this page's set); locals on owning class |
| `self._script_N = <Class>()` | only if doc has attached components | one per attached CTkScript |
| `self._build_ui()` call | always | constructs widget tree |
| scope inject + `on_start()` + `on_close` wiring | only if doc has attached components | `self._script_N.window`/`.widget`, then `on_start()`, `WM_DELETE_WINDOW → on_close()` |

## Phase contributions

The export pipeline grew over phases. Each contributes specific code:

### Phase 0 — Widget descriptions (AI bridge)

When `include_descriptions=True` and a `WidgetNode.description` is non-empty, emit Python comments above the widget's constructor call:

```python
# When clicked, validates the email field and submits the form.
self.button_submit = ctk.CTkButton(
    self,
    ...
)
```

`Document.description` emits as a comment above the `class X(...):` line.

### Phase 1 — Variables

Walks `Project.variables` (globals) + each `Document.local_variables`. For each:

```python
self.var_<name> = tk.StringVar(value="default")    # str
self.var_<name> = tk.IntVar(value=0)               # int
self.var_<name> = tk.DoubleVar(value=0.0)          # float
self.var_<name> = tk.BooleanVar(value=False)       # bool
```

Properties bound to a variable token (`var:<uuid>`) emit as constructor kwargs per the [BINDING_WIRINGS table](DATA_MODEL.md#binding_wirings-table--variablespy235):

```python
self.label_status = ctk.CTkLabel(
    self,
    text="...",
    textvariable=self.var_status,    # was a var:<uuid> token
)
```

Build helpers:

- `_build_global_var_attrs(project)` — [:696](../../app/io/code_exporter/__init__.py#L696) — stable per-project map `{var_id → "var_<name>"}`
- `_build_class_var_map(project, doc, force_main)` — [:720](../../app/io/code_exporter/__init__.py#L720) — per-class context. Returns `{var_id → "self.var_X" | "self.master.var_X"}`
- `_emit_class_variables(project, doc, force_main)` — [:790](../../app/io/code_exporter/__init__.py#L790) — emits the `self.var_X = ...` lines

### Phase 1.5 — Global vs local scope split

Globals are page-scoped — `project.variables` holds the active page's set. They live on the **main window class only** of the page being exported. Toplevels in the same page read them via `self.master.var_X`:

```python
class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.var_theme = tk.StringVar(value="dark")    # global

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master=None):
        super().__init__(master)
        # No var_theme = ... line here — read from master:
        self.combo_theme = ctk.CTkComboBox(
            self, variable=self.master.var_theme,
        )
```

Locals live on the owning class as `self.var_X` regardless of main/toplevel.

When `single_document_id` exports a single Toplevel as a standalone `.py`, `force_main=True` flattens that doc's globals into locals so it runs without a parent.

### Phase 2 — Event handlers (CTkScript)

The scripting model attaches user `CTkScript` subclasses to widgets or the window via `attached_components` (see [DATA_MODEL.md](DATA_MODEL.md)) and binds events through `script_call` handler entries. Scripts live in the top-level `<project>/scripts/` folder (outside `assets/`). The exported build is **self-contained**: the `CTkScript` base is inlined as a `ctkmaker.py` sidecar and the `scripts/` folder is copied next to the exported window — no `pip install` of CTkMaker needed at runtime.

Per attached object the exporter instantiates the script, injects its scope, and runs lifecycle hooks:

```python
from scripts.counter import Counter        # one import per distinct class

class MainWindow(ctk.CTk):
    def __init__(self):
        ...
        self._script_0 = Counter()           # one per attached component
        self._build_ui()
        self._script_0.window = self          # window-attach → self.window
        # (a widget-attach injects self._script_0.widget = self.<var> instead)
        self._script_0.score = self.var_hp               # field → bound variable
        self._script_0.title = tk.StringVar(value="Hi")  # … or inline value
        self._script_0.label = tk.StringVar()            # … or tk default (unset)
        self._script_0.on_start()
        self.protocol(
            "WM_DELETE_WINDOW",
            lambda: (self._script_0.on_close(), self.destroy()),
        )
```

`script_call` event entries resolve to a bare method reference, wired exactly like other entries (constructor kwarg for a lone entry, `lambda` chain otherwise):

```python
# command event → script_call on a window component
command=self._script_0.increment

# Tk bind → wrapped to swallow the event arg
self.btn.bind("<Button-1>", lambda e: self._script_0.increment(), add="+")
```

Helpers:

- `_collect_doc_components(doc, id_to_var)` — stable component records (`{var, scope, target, script, class, owner_id, var_bindings, field_values, fields}`); window components first, then widgets in DFS. `fields` is the class's exposed `[(name, var_type)]` (AST), so the exporter can inject every field.
- `_resolve_component_var(records, owner_id, class_name, scope=None)` — instance var for a `script_call`. When the entry carries `scope` (`"widget"` / `"window"`), that scope is matched directly; legacy entries without scope fall back to: owning widget's component wins, else a window component. `None` → the binding is dropped.
- `_emit_component_init_lines` / `_emit_component_post_lines` / `_emit_component_close_lines` — instantiation before `_build_ui()`; after it: scope injection + **field injection** (each exposed field → bound `self.var_X`, inline `tk.<Type>Var(value=…)`, or `tk.<Type>Var()` default — a stale binding falls back to default) + `on_start()`; `on_close()` on `WM_DELETE_WINDOW`. `_field_value_literal` coerces an inline string to its tk type.
- `_format_script_call(entry, records, owner_id)` — `self._script_N.<method>`, or `None` when unresolved.
- `_ctkscript_base_source()` / `_project_uses_components()` — the inlined `ctkmaker.py` base + the gate that copies `scripts/` and writes the sidecar **only** when components exist (component-less exports stay byte-identical).

## Per-widget construction

Each widget's emit goes through:

1. **Resolve var bindings** — [variables.py:269](../../app/core/variables.py#L269) `resolve_bindings(project, widget_type, properties)`. Returns `(cleaned_props, extra_kwargs)`.
2. **Descriptor-controlled transformation** — `descriptor.transform_properties(cleaned)` strips `_NODE_ONLY_KEYS`, maps builder-side keys to CTk constructor kwargs.
3. **Special handling**:
   - `state` ← `button_enabled` / `state_disabled` toggles
   - `font` ← `font_*` keys → `ctk.CTkFont(family=..., size=..., weight=..., slant=..., underline=..., overstrike=...)`
   - `image` path → `ctk.CTkImage(light_image=Image.open(...), dark_image=...)`
   - `state` post-construct → `widget.set(initial)`, `widget.select()`, etc. via `descriptor.export_state(...)`
4. **Default-skip** — kwargs that match the CTk constructor's default are dropped to keep the output compact. See `_kwarg_matches_defaults` ([ctk_defaults.py:53](../../app/io/code_exporter/ctk_defaults.py#L53)) and `_ctk_constructor_defaults` ([ctk_defaults.py:24](../../app/io/code_exporter/ctk_defaults.py#L24)).

## Layout managers

`Document.window_properties["layout_type"]` ∈ `{"place", "vbox", "hbox", "grid"}`. Each maps to a different positioning emit:

| Layout | Per-widget call | Notes |
|---|---|---|
| `place` | `widget.place(x=..., y=..., width=..., height=...)` | Default. Absolute positioning. |
| `vbox` / `hbox` | `widget.pack(side=..., fill=..., expand=..., padx=..., pady=...)` | Pack-balance helper emitted when needed (`_project_needs_pack_balance`). |
| `grid` | `widget.grid(row=..., column=..., sticky=..., padx=..., pady=...)` | `grid_effective_dims` resolves rowspan/colspan. |

Schema in [app/widgets/layout_schema.py](../../app/widgets/layout_schema.py).

### Flex layout (vbox / hbox)

Each child of a `vbox` / `hbox` parent carries a `stretch` mode (per-child property, default `"fixed"`):

| Mode | Main axis | Cross axis |
|---|---|---|
| `fixed` | nominal `width` / `height` | nominal |
| `fill` | nominal | fills container |
| `grow` | shares remaining space among `grow` siblings | fills container |

Shrink floor: `grow` siblings shrink down to text + icon + chrome padding before clipping; `fixed` siblings keep their nominal size. Pack-balance helper (`_project_needs_pack_balance`) emits filler frames when needed so `grow` distribution stays consistent at runtime. The `prefers_fill_in_layout` descriptor flag (see [EXTENSION.md](EXTENSION.md)) auto-picks `fill` for widgets that should default to filling — Frame, Label, Button — when dropped into a flex container. Project loader infers `stretch` for legacy projects from sibling layout: see `_migrate_child_pack_to_stretch` — [project_loader.py:615](../../app/io/project_loader.py#L615).

## Module-level state

The exporter uses module-level globals as a per-export context (alternative to threading the project through every helper). Set at the top of `export_project` / `generate_code` and cleared at the end:

| Name | Purpose |
|---|---|
| `_CURRENT_PROJECT_PATH` | Active project disk path — for `_path_for_export` (image asset rewrites) |
| `_EXPORT_PROJECT` | Active `Project` reference — for descriptor helpers that need it |
| `_GLOBAL_VAR_ATTR` | `{var_id → "var_<name>"}` for all global variables |
| `_VAR_ID_TO_ATTR` | `{var_id → "self.var_X" | "self.master.var_X"}` for current class — swapped per `_emit_class` |
| `_VAR_NAME_FALLBACKS` | Warnings when user-set names were rewritten (duplicates, reserved, invalid) |

The pattern is intentional — the export call tree is deep, threading every context arg would 10× the parameter count without making the flow clearer.

## CTkScript scanning — `app/io/scripts/`

[app/io/scripts/](../../app/io/scripts/) handles read-only inspection of the user's `scripts/` folder (CTkMaker never imports user scripts — it only AST-parses them) plus creating new ones.

| Function | What it does |
|---|---|
| `parse_ctkscript_classes(file_path) → list[str]` | Names of every top-level `CTkScript` subclass in a file. Feeds the attach picker. |
| `find_attachable_scripts(scripts_dir) → list[(rel_path, class)]` | Walk `scripts/` for attachable classes. |
| `parse_handler_methods(file_path, class_name) → list[str]` | Method names on a class. Feeds the Function picker. |
| `create_user_script(scripts_dir, class_name) → (rel, class)` | Write a new `<snake>.py` CTkScript skeleton (auto-suffixed on collision). |
| `normalize_class_name(raw) → str` | Any input style → PascalCase class name (`foo bar` → `FooBar`); `""` when unusable. Feeds the New-script dialog. |
| `class_name_to_filename(class_name) → str` | `ClickCounter` → `click_counter`; shared by `create_user_script` and the dialog's live preview. |
| `iter_script_call_targets` / `resolve_script_component` | Which attached component a `script_call` binds to (shared by panel + pickers). |
| `launch_editor` / `resolve_project_root_for_editor` | Open a script file in the user's editor. |

## Asset copying

`export_project` copies `<project>/assets/` next to the output file, and (when any CTkScript component is attached) the top-level `scripts/` folder plus a `ctkmaker.py` sidecar:

- Default — full `assets/` copy (`shutil.copytree(..., dirs_exist_ok=True)`)
- With `asset_filter` — only the listed asset files (per-page exports).
- CTkScript bundle — `_project_uses_components` gates copying `<project>/scripts/` next to the output, writing the inlined `ctkmaker.py` base, and seeding package markers via `write_package_markers_in` so `from scripts.<mod> import <Class>` resolves on any Python. Component-less exports skip all of this (byte-identical output).
- ScrollableDropdown helper — sidecar-copied next to the export when any `CTkComboBox` / `CTkOptionMenu` is present.

## Variable name resolution

Widget-level emit needs each widget's Python attribute name. Resolved at:

```python
_resolve_var_names(doc) → dict[widget_id → "var_name"]      # per-doc DFS map
```

Pipeline:

1. Use `WidgetNode.name` if it's a valid identifier + non-keyword + non-reserved.
2. Otherwise fall back to `<lowercase_widget_type>_<N>` (per-doc counter).
3. Detect duplicates → suffix `_2`, `_3`, ...
4. Collect every fallback in `_VAR_NAME_FALLBACKS` so the user can be warned.

## Composite live bindings

Maker-only composite property keys can't be passed straight to CTk's `configure(...)` — Maker decomposes them at construction time. The auto-trace path emits per-composite rebuilders that update the widget in place when the bound variable changes, so `self.var_X.set(...)` works the same way for these as it does for native CTk kwargs.

**Phase 1 (v1.28.4 + v1.28.6):** font composites.

| Property | Variable type | Helper | Effect |
|---|---|---|---|
| `font_bold` | `bool` | `_bind_var_to_font(var, widget, "weight")` | Rebuilds `CTkFont` with `weight="bold"` / `"normal"`, other attributes preserved |
| `font_italic` | `bool` | `_bind_var_to_font(var, widget, "slant")` | `slant="italic"` / `"roman"` |
| `font_size` | `int` | `_bind_var_to_font(var, widget, "size")` | New font with the requested size |
| `font_family` | `str` | `_bind_var_to_font(var, widget, "family")` | New font with the requested family |
| `font_underline` | `bool` | `_bind_var_to_font(var, widget, "underline")` | Toggles underline |
| `font_overstrike` | `bool` | `_bind_var_to_font(var, widget, "overstrike")` | Toggles strikethrough |

**Phase 2a:** ``button_enabled`` (state).

| Property | Variable type | Helper | Effect |
|---|---|---|---|
| `button_enabled` | `bool` | `_bind_var_to_state(var, widget)` | `widget.configure(state="normal"/"disabled")`. Applies to every CTk widget that exposes `state=` — Button, Entry, ComboBox, OptionMenu, Switch, CheckBox, RadioButton, Slider, SegmentedButton, Textbox. |

**Phase 2b:** ``label_enabled`` (CTkLabel text-color swap).

| Property | Variable type | Helper | Effect |
|---|---|---|---|
| `label_enabled` | `bool` | `_bind_var_to_label_enabled(var, widget, color_on, color_off)` | Swaps `text_color` between the construction-time `text_color` and `text_color_disabled` values. Both colors are captured as literals at emit time so the helper can restore the original on re-enable. Tk Label's native `state="disabled"` paints a stipple wash over `image=`, so we use manual color swap instead. |

**Phase 2c–e:** font-shape + image composites.

| Property | Variable type | Helper | Effect |
|---|---|---|---|
| `font_wrap` (CTkLabel) | `bool` | `_bind_var_to_font_wrap(var, widget)` | True → wraplength derived from widget's current width; False → wraplength=0 (no wrap). |
| `font_autofit` (CTkLabel) | `bool` | `_bind_var_to_font_autofit(var, widget, size_off)` | True → binary-search the largest font size that fits current text inside current width × height; False → restore original `size_off`. Inlines a port of `_compute_autofit_size` into the export. |
| `image_color` (CTkLabel / CTkButton / Image) | `color` / `str` | `_bind_var_to_image_color_state(var, widget, "color")` | Updates `_maker_image_state["color"]` and triggers `_rebuild_image_for_widget`. Picks `color_disabled` instead when `enabled` is False (see Phase 4a). |

**Phase 3:** geometry + image rebuilders.

| Property | Variable type | Helper | Effect |
|---|---|---|---|
| `x` / `y` | `int` / `float` | `_bind_var_to_place_coord(var, widget, axis)` | `widget.place_configure(x=…)` / `place_configure(y=…)`. No-op for widgets not on place layout. |
| `image` (path) | `str` | `_bind_var_to_image_path(var, widget)` | Reloads image from the new path via PIL + CTkImage; preserves width / height / color / aspect from `_maker_image_state`. |
| `image_width` / `image_height` | `int` / `float` | `_bind_var_to_image_size(var, widget, axis)` | Rebuilds CTkImage with new dimension; other axis from `_maker_image_state`. |
| `preserve_aspect` | `bool` | `_bind_var_to_preserve_aspect(var, widget)` | Toggles between aspect-fit (scaled to contain) and stretch-to-fit modes. |

All image rebuilders share `_maker_image_state` — a dict initialised on the widget when any image-related binding is present (including `label_enabled` / `button_enabled` on a widget that has an image). Keys: `path` / `width` / `height` / `color` / `color_disabled` / `enabled` / `aspect`. Each helper updates one key, then calls `_rebuild_image_for_widget`. The rebuild picks `color_disabled` when `enabled` is False (and a disabled color is set), else `color`.

**Phase 4a:** `image_color_disabled` + enabled coordination.

| Property | Variable type | Helper | Effect |
|---|---|---|---|
| `image_color_disabled` (CTkLabel / CTkButton / Image) | `color` / `str` | `_bind_var_to_image_color_state(var, widget, "color_disabled")` | Updates `_maker_image_state["color_disabled"]` and triggers rebuild. Visible only when the widget's `enabled` state is False — coordinated automatically with `_bind_var_to_label_enabled` and `_bind_var_to_state` (both extend to sync `_maker_image_state["enabled"]` when the widget has an image). |

Phase 4b (planned): `dropdown_*` (CTkOptionMenu / CTkComboBox dropdown styling — niche; may be skipped if fork plan supersedes).

## Special-case helpers

| Helper | Purpose |
|---|---|
| `_emit_auto_trace_bindings(...)` — [:431](../../app/io/code_exporter/__init__.py#L431) | Wire `Variable.trace_add("write", _update)` for properties bound to a non-textvariable variable (cosmetic bindings). Routes font composites through `_bind_var_to_font`; other CTk-native cosmetic keys through `_bind_var_to_widget`. |
| `_collect_radio_groups(...)` — [:1840](../../app/io/code_exporter/__init__.py#L1840) | Cluster `CTkRadioButton` widgets sharing a variable into one group for correct `value=` emission. |
| `_resolve_var_tokens_to_values(...)` — [:640](../../app/io/code_exporter/__init__.py#L640) | Replace `var:<uuid>` tokens with the variable's current literal value (for tokens not in `BINDING_WIRINGS`). |
| `_format_var_value_lit(v)` — [:759](../../app/io/code_exporter/__init__.py#L759) | Coerce a string-form variable default into a Python literal of the right type. |
| `_preview_screenshot_lines(target)` — [preview_screenshot.py:350](../../app/io/code_exporter/preview_screenshot.py#L350) | F12 floater + orange ring template, expanded inline when `inject_preview_screenshot=True`. |

## Error reporting back to the UI

`export_project` reports issues via:

| Mechanism | Trigger | Notes |
|---|---|---|
| `get_var_name_fallbacks()` | User-set widget name had to be rewritten | Returns `list[(doc_name, widget_label, requested_name, actual_name)]`. UI surfaces in a post-export status toast / dialog. A `script_call` whose component/method no longer resolves is dropped silently at emission (the panel already shows it red). |

## What does NOT export

- **Builder-only state** — `WidgetNode.visible`, `locked`, `group_id`, `description` (when `include_descriptions=False`)
- **Window grid + snap settings** — `grid_style`, `grid_color`, `grid_spacing`, `alignment_lines_enabled`, `snap_enabled`
- **Selection / clipboard / history** — runtime-only
- **Components** — `.ctkcomp` files in `<project>/components/` are dev-time only; the exported `.py` only contains widgets that are actually placed
- **Group membership** — `group_id` is a builder organization tag; generated Python sees only individual widgets
