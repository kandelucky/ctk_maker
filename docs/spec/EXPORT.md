# CTkMaker — Export Pipeline

How a `.ctkproj` becomes a runnable `.py`. Lives in [app/io/code_exporter.py](../../app/io/code_exporter.py) (3,242 lines, single file by design through v1.0) plus [app/io/scripts.py](../../app/io/scripts.py) for the per-window behavior file machinery.

## Entry points

### `export_project` — [code_exporter.py:974](../../app/io/code_exporter.py#L974)

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

### `generate_code` — [code_exporter.py:1148](../../app/io/code_exporter.py#L1148)

Pure code generation — returns the source as a string. No disk side-effects. Calls `_generate_code_inner` ([:1224](../../app/io/code_exporter.py#L1224)) which orchestrates per-document emission.

## Output structure

One class per document. Single file holds them all. Layout:

```python
#!/usr/bin/env python3
# (CTkMaker header + version stamp)

import customtkinter as ctk
import tkinter as tk
from PIL import Image
from pathlib import Path

# Phase 2 — behavior file imports (one per doc with handlers)
from assets.scripts.<page_slug>.<window_slug> import <WindowName>Page

# Optional helpers (only when used)
from scrollable_dropdown import ScrollableDropdown

# Main window class — the first non-toplevel document
class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window metadata
        self.title("...")
        self.geometry("800x600")
        self.resizable(True, True)

        # Phase 1 — global variables (only on the main window class)
        self.var_username = tk.StringVar(value="")
        self.var_count = tk.IntVar(value=0)

        # Phase 2 — instantiate behavior class
        self._behavior = MainWindowPage()

        # Build UI
        self._build_ui()

        # Phase 2 — wire setup hook
        self._behavior.setup(self)

        # Object References — typed slots on behavior class
        self._behavior.submit_btn = self.button_submit
        self._behavior.username_entry = self.entry_username

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
            command=self._behavior.on_submit,  # Phase 2 — single-method
        )
        self.button_submit.place(x=20, y=60, width=100, height=32)

# Toplevel classes — every is_toplevel=True document
class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master=None):
        super().__init__(master)
        # ... (same shape; globals reach via self.master.var_X)

if __name__ == "__main__":
    import sys
    ctk.set_appearance_mode("dark")
    if sys.platform == "win32":
        ctk.ThemeManager.theme["CTkFont"]["family"] = "Segoe UI"
    app = MainWindow()
    app.mainloop()
```

The Windows-only theme patch mirrors [main.py:main()](../../main.py)'s startup. CTk ships only `Roboto-Regular.ttf` and `Roboto-Medium.ttf` — there is no `Roboto-Bold.ttf`, so `CTkFont(weight="bold")` silently falls back to a synthetic bold that is barely visible at large font sizes. Roboto on Windows also lacks coverage for many non-Latin scripts. Patching `theme["CTkFont"]["family"]` to Segoe UI fixes both. macOS (`SF Display`) and Linux (Roboto) are left at the CTk default — Linux currently inherits the same Roboto-bold limitation as the editor itself.

## Per-class structure

| Section | When emitted | Source |
|---|---|---|
| `super().__init__()` | always | required |
| `title` / `geometry` / `resizable` / `frameless` | always | from `Document.window_properties` |
| Phase 1 variable instantiation | only if class owns variables | page-globals on main window class only (this page's set); locals on owning class |
| `self._behavior = <WindowName>Page()` | only if doc has handlers OR object refs | Phase 2 |
| `self._build_ui()` call | always | constructs widget tree |
| `self._behavior.setup(self)` | only if behavior class exists | Phase 2 setup hook |
| Object reference assignments | only if doc has refs | `self._behavior.<ref> = self.<widget>` |

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

Properties bound to a variable token (`var:<uuid>`) emit as constructor kwargs per the [BINDING_WIRINGS table](DATA_MODEL.md#binding_wirings-table--variablespy163):

```python
self.label_status = ctk.CTkLabel(
    self,
    text="...",
    textvariable=self.var_status,    # was a var:<uuid> token
)
```

Build helpers:

- `_build_global_var_attrs(project)` — [:817](../../app/io/code_exporter.py#L817) — stable per-project map `{var_id → "var_<name>"}`
- `_build_class_var_map(project, doc, force_main)` — [:841](../../app/io/code_exporter.py#L841) — per-class context. Returns `{var_id → "self.var_X" | "self.master.var_X"}`
- `_emit_class_variables(project, doc, force_main)` — [:911](../../app/io/code_exporter.py#L911) — emits the `self.var_X = ...` lines

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

### Phase 2 — Event handlers + behavior files

Per-window behavior file at `<project>/assets/scripts/<page_slug>/<window_slug>.py` holds the user's hand-written method bodies:

```python
# assets/scripts/main_window/main_window.py
class MainWindowPage:
    def setup(self, window):
        # Optional — runs once after _build_ui()
        ...

    def on_submit(self):
        # Hand-written body
        ...
```

Exporter emits the import + instantiation + setup call:

```python
from assets.scripts.main_window.main_window import MainWindowPage

class MainWindow(ctk.CTk):
    def __init__(self):
        ...
        self._behavior = MainWindowPage()
        self._build_ui()
        self._behavior.setup(self)
```

Widget handlers wire as constructor kwargs (single method) or `lambda` chains (multi-method):

```python
# Single method on "command" event
command=self._behavior.on_submit

# Multiple methods — fan-out via lambda
command=lambda: (self._behavior.validate(), self._behavior.on_submit())

# Tk bind-style — repeated .bind(seq, fn, add="+")
self.entry_email.bind("<Return>", self._behavior.on_email_enter, add="+")
```

Helpers:

- `_emit_handler_lines(...)` — [:1580](../../app/io/code_exporter.py#L1580)
- `_format_method_chain(methods)` — [:1636](../../app/io/code_exporter.py#L1636) — multi-method lambda body
- `_doc_has_handlers(doc)` / `_node_has_handlers(node)` / `_doc_needs_behavior(doc)` — [:1648-1669](../../app/io/code_exporter.py#L1648)
- `_scan_behavior_methods_for_export(project)` — [:1497](../../app/io/code_exporter.py#L1497) — AST scan; populates `_BEHAVIOR_METHODS_BY_DOC_ID`
- `_filter_handlers_to_existing_methods(...)` — [:1527](../../app/io/code_exporter.py#L1527) — drop handler entries pointing at a missing `def`

### Phase 3 — Object References

Typed `self.<name>: <Type>` slots in the behavior class let handler code reach widgets / windows by name:

```python
# In behavior file (declared via Properties panel ◆ toggle):
class MainWindowPage:
    submit_btn: ref[CTkButton] = ref()
    username_entry: ref[CTkEntry] = ref()
```

Exporter emits the assignments after `_build_ui()`:

```python
self._build_ui()
self._behavior.setup(self)
self._behavior.submit_btn = self.button_submit
self._behavior.username_entry = self.entry_username
```

Cross-window refs (target = `Window` / `Dialog`) live on `Project.object_references`. The exporter resolves the target document's class symbol via `_DOC_ID_TO_CLASS`.

**Name match is verbatim.** `self._behavior.<entry.name>` is assigned with no fuzzy match, suffix-stripping, or normalisation. If the Properties-panel ref says `counter_label_ref` but the behavior class has `counter_label: ref[CTkLabel]`, the runtime sets `self._behavior.counter_label_ref` (the GUI name) and the user's `self.counter_label` access raises `AttributeError` at the first widget interaction. Both ends must match exactly.

Auto-stub paths keep the two in sync on the GUI side: `panel.py:_maybe_write_ref_annotation` writes the annotation when a ref is created, `_maybe_delete_ref_annotation` strips it on remove, and `variables_window.py:_maybe_rename_annotation` propagates renames. Manual edits to the behavior file bypass these — `_scan_ref_annotations_for_export` walks every doc at the top of `generate_code` and populates `_REF_ANNOTATION_ISSUES` with `(doc_name, kind, ref_name, detail)` rows so launchers can warn the user.

Issue kinds:

| Kind | Meaning |
|---|---|
| `missing_annotation` | A Properties-panel local ref has no matching `<name>: ref[<Type>]` line in the behavior class. |
| `orphan_annotation` | A `ref[<Type>]` annotation has no matching ref in `doc.local_object_references` or `project.object_references`. |
| `type_mismatch` | Both sides exist but the annotation's type disagrees with the ref's `target_type`. |

Read via `get_ref_annotation_issues()`. F5 preview asks the user via `_confirm_ref_annotation_issues`; export + quick export show a `messagebox.showwarning` after a successful write.

Helpers:

- `_emit_object_reference_lines(...)` — [:1875](../../app/io/code_exporter.py#L1875)
- `_behavior_class_for_doc(doc)` — [:1920](../../app/io/code_exporter.py#L1920)
- `_scan_ref_annotations_for_export(project)` / `get_ref_annotation_issues()` — annotation-vs-model diff

## Per-widget construction

Each widget's emit goes through:

1. **Resolve var bindings** — [variables.py:191](../../app/core/variables.py#L191) `resolve_bindings(project, widget_type, properties)`. Returns `(cleaned_props, extra_kwargs)`.
2. **Descriptor-controlled transformation** — `descriptor.transform_properties(cleaned)` strips `_NODE_ONLY_KEYS`, maps builder-side keys to CTk constructor kwargs.
3. **Special handling**:
   - `state` ← `button_enabled` / `state_disabled` toggles
   - `font` ← `font_*` keys → `ctk.CTkFont(family=..., size=..., weight=..., slant=..., underline=..., overstrike=...)`
   - `image` path → `ctk.CTkImage(light_image=Image.open(...), dark_image=...)`
   - `state` post-construct → `widget.set(initial)`, `widget.select()`, etc. via `descriptor.export_state(...)`
4. **Default-skip** — kwargs that match the CTk constructor's default are dropped to keep the output compact. See `_kwarg_matches_defaults` ([:495](../../app/io/code_exporter.py#L495)) and `_ctk_constructor_defaults` ([:466](../../app/io/code_exporter.py#L466)).

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

Shrink floor: `grow` siblings shrink down to text + icon + chrome padding before clipping; `fixed` siblings keep their nominal size. Pack-balance helper (`_project_needs_pack_balance`) emits filler frames when needed so `grow` distribution stays consistent at runtime. The `prefers_fill_in_layout` descriptor flag (see [EXTENSION.md](EXTENSION.md)) auto-picks `fill` for widgets that should default to filling — Frame, Label, Button — when dropped into a flex container. Project loader infers `stretch` for legacy projects from sibling layout: see [project_loader.py:584](../../app/io/project_loader.py#L584).

## Module-level state

The exporter uses module-level globals as a per-export context (alternative to threading the project through every helper). Set at the top of `export_project` / `generate_code` and cleared at the end:

| Name | Purpose |
|---|---|
| `_CURRENT_PROJECT_PATH` | Active project disk path — for `_path_for_export` (image asset rewrites) |
| `_EXPORT_PROJECT` | Active `Project` reference — for descriptor helpers that need it |
| `_BEHAVIOR_METHODS_BY_DOC_ID` | `{doc_id → set of method names}` from AST scan |
| `_MISSING_BEHAVIOR_METHODS` | List of `(doc_name, method_name)` whose `def` couldn't be resolved |
| `_GLOBAL_VAR_ATTR` | `{var_id → "var_<name>"}` for all global variables |
| `_VAR_ID_TO_ATTR` | `{var_id → "self.var_X" | "self.master.var_X"}` for current class — swapped per `_emit_class` |
| `_DOC_ID_TO_CLASS` | `{doc_id → generated class name}` for object reference target resolution |
| `_VAR_NAME_FALLBACKS` | Warnings when user-set names were rewritten (duplicates, reserved, invalid) |

The pattern is intentional — the export call tree is deep, threading every context arg would 10× the parameter count without making the flow clearer.

## Behavior file machinery — `app/io/scripts.py`

[scripts.py](../../app/io/scripts.py) handles the per-window `.py` file lifecycle.

### Skeleton creation

```python
load_or_create_behavior_file(project_path, page_slug, window_slug, class_name, ...) → Path
```

Called eagerly on `document_added` (so a fresh dialog gets its file before any handler is attached). Creates parent directories + `__init__.py` chain (`assets/scripts/__init__.py` + `assets/scripts/<page>/__init__.py`) for namespace package import.

### AST-driven introspection

| Function | What it returns |
|---|---|
| `parse_handler_methods(file_path, class_name) → set[str]` | Method names defined on the behavior class. Used by exporter to filter out handler entries with no matching `def`. |
| `parse_object_reference_fields(file_path, class_name) → list[FieldSpec]` | `ref[Type] = ref()` annotations — Object Reference slots. |
| `existing_object_reference_names(...)` | Dedupe helper. |

### Mutation

Done via text manipulation (preserves blank lines, comments, formatting):

| Function | Purpose |
|---|---|
| `add_handler_stub(...)` | Append a new `def method_name(self):` skeleton when the user attaches a handler that doesn't exist yet. |
| `add_object_reference_annotation(...)` | Insert a `ref[Type] = ref()` class field. |
| `delete_object_reference_annotation(...)` | Remove same. Warns the caller if the field is referenced by a method body. |
| `delete_method_from_file(...)` | Remove a `def method` block when the user un-binds + chooses delete. |
| `rename_behavior_file_and_class(...)` | When the document is renamed: rename the file AND the class. |
| `recycle_behavior_file(...)` | On document delete (default): send to Recycle Bin via `Send2Trash`. |
| `save_behavior_file_copy(...)` | On document delete (alternative): copy to `<project>/assets/scripts_archive/`. |

### `ref` runtime helper — [scripts.py:636](../../app/io/scripts.py#L636)

The exported behavior file imports a tiny generic descriptor so `ref[CTkButton] = ref()` works without external dependencies:

```python
from typing import Generic, TypeVar
T = TypeVar("T")

class ref(Generic[T]):
    """Typed slot — populated by the host class's __init__ after _build_ui()."""
    ...
```

`ensure_runtime_helpers(...)` injects this into the behavior file the first time an Object Reference is added to a doc that doesn't already have it.

## Asset copying

`export_project` copies `<project>/assets/` next to the output file:

- Default — full copy (`shutil.copytree(..., dirs_exist_ok=True)`)
- With `asset_filter` — only the listed asset files (per-page exports). Behavior subtree is copied separately via `_copy_behavior_assets_for_filter` ([:1692](../../app/io/code_exporter.py#L1692)) so `from assets.scripts.<page>.<window> import <Class>Page` resolves.
- ScrollableDropdown helper — sidecar-copied next to the export when any `CTkComboBox` / `CTkOptionMenu` is present.

## Variable name resolution

Widget-level emit needs each widget's Python attribute name. Resolved at:

```python
_resolve_var_names(doc) → dict[widget_id → "var_name"]      # [:1768]
_build_id_to_var_name(doc) → dict[widget_id → "var_name"]   # [:1865]
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
| `_emit_auto_trace_bindings(...)` — [:751](../../app/io/code_exporter.py#L751) | Wire `Variable.trace_add("write", _update)` for properties bound to a non-textvariable variable (cosmetic bindings). Routes font composites through `_bind_var_to_font`; other CTk-native cosmetic keys through `_bind_var_to_widget`. |
| `_collect_radio_groups(...)` — [:1939](../../app/io/code_exporter.py#L1939) | Cluster `CTkRadioButton` widgets sharing a variable into one group for correct `value=` emission. |
| `_resolve_var_tokens_to_values(...)` — [:790](../../app/io/code_exporter.py#L790) | Replace `var:<uuid>` tokens with the variable's current literal value (for tokens not in `BINDING_WIRINGS`). |
| `_format_var_value_lit(v)` — [:880](../../app/io/code_exporter.py#L880) | Coerce a string-form variable default into a Python literal of the right type. |
| `_preview_screenshot_lines(target)` — [:343](../../app/io/code_exporter.py#L343) | F12 floater + orange ring template, expanded inline when `inject_preview_screenshot=True`. |

## Error reporting back to the UI

The export reports issues via two module-level lists (read by the UI after `export_project` returns):

| Function | Returns |
|---|---|
| `get_missing_behavior_methods()` — [:1557](../../app/io/code_exporter.py#L1557) | `list[(doc_name, method_name)]` — handlers that point at a `def` that doesn't exist in the behavior file |
| `get_var_name_fallbacks()` — [:1567](../../app/io/code_exporter.py#L1567) | `list[(doc_name, widget_label, requested_name, actual_name)]` — names that had to be rewritten |

UI surfaces these in a post-export status toast / dialog so the user knows what to fix in their behavior file.

## What does NOT export

- **Builder-only state** — `WidgetNode.visible`, `locked`, `group_id`, `description` (when `include_descriptions=False`)
- **Window grid + snap settings** — `grid_style`, `grid_color`, `grid_spacing`, `alignment_lines_enabled`, `snap_enabled`
- **Selection / clipboard / history** — runtime-only
- **Components** — `.ctkcomp` files in `<project>/components/` are dev-time only; the exported `.py` only contains widgets that are actually placed
- **Group membership** — `group_id` is a builder organization tag; generated Python sees only individual widgets
