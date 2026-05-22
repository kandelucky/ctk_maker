# CTkMaker — Data Model

Persistent classes and their on-disk shape. Everything here lives in [app/core/](../../app/core/) and round-trips through `to_dict` / `from_dict` for save/load.

## Hierarchy

```
Project                           (top container, in-memory only)
├── documents: list[Document]
│   └── root_widgets: list[WidgetNode]
│       └── children: list[WidgetNode]
│           └── ... (recursive tree)
│       (each WidgetNode also has handlers: dict[event → list[method_name]])
│   ├── local_variables: list[VariableEntry]      (scope="local")
│   └── local_object_references: list[ObjectReferenceEntry]  (scope="local")
├── variables: list[VariableEntry]                (scope="global", page-scoped — active page only)
├── object_references: list[ObjectReferenceEntry] (scope="global", page-scoped — active page only)
├── font_defaults: dict[str, str]
├── system_fonts: list[str]
├── pages: list[dict]                             (multi-page projects)
└── (event_bus, history, name, path — runtime only)
```

Identity is by UUID at every level. Names are user-mutable display strings; bindings/references resolve through IDs.

## Project — [app/core/project.py:192](../../app/core/project.py#L192)

Top-level container. Single instance per loaded project. 1,811 lines, ~79 methods — the public API contract.

### Persistent fields (round-trip via [project_saver.py](../../app/io/project_saver.py) / [project_loader.py](../../app/io/project_loader.py))

| Field | Type | Purpose |
|---|---|---|
| `name` | `str` | Display name. Defaults to `"Untitled"`. |
| `documents` | `list[Document]` | Window list. Always at least one (Main Window). |
| `active_document_id` | `str` | Which document the canvas is focused on. |
| `variables` | `list[VariableEntry]` | Page-scoped shared variables (active page only). Stored in each page's `.ctkproj`, not in `project.json`. |
| `object_references` | `list[ObjectReferenceEntry]` | Page-scoped window/dialog references (active page only). Stored in each page's `.ctkproj`, not in `project.json`. |
| `font_defaults` | `dict[str, str]` | `{"_all": "Inter", "CTkButton": "Roboto", ...}` cascade. |
| `system_fonts` | `list[str]` | OS fonts user added to the project palette. |
| `folder_path` | `str \| None` | Multi-page project root. `None` for single-file projects. |
| `pages` | `list[dict]` | Multi-page metadata: `[{id, file, name}, ...]`. |
| `active_page_id` | `str \| None` | Currently-loaded page ID. |

### Runtime-only fields

| Field | Type | Purpose |
|---|---|---|
| `event_bus` | `EventBus` | Pub/sub instance. See [EVENT_BUS.md](EVENT_BUS.md). |
| `history` | `History` | Undo/redo stack. |
| `selected_id` | `str \| None` | Primary selection (resize / properties). |
| `selected_ids` | `set[str]` | Multi-selection set. Empty in single-select mode. |
| `clipboard` | `list[dict]` | In-memory copy/paste buffer (`WidgetNode.to_dict()` snapshots). |
| `_id_index` | `dict[str, WidgetNode]` | O(1) widget lookup. Maintained on add/remove/reparent. |
| `_doc_index` | `dict[str, Document]` | O(1) document lookup. |
| `_tk_vars` | `dict[str, tk.Variable]` | Lazy cache of live Tk variable instances by `VariableEntry.id`. |
| `_window_proxy` | `_WindowProxy` | Virtual node for "Window" selection — see Sentinels. |

### Key methods

Tree mutations (all publish events — see [EVENT_BUS.md](EVENT_BUS.md)):

```python
add_widget(node, parent_id=None, document_id=None) → WidgetNode
remove_widget(widget_id) → None
reparent(widget_id, new_parent_id, ...) → None
duplicate_widget(widget_id) → WidgetNode
bring_to_front(widget_id) / send_to_back(widget_id) → None
update_property(widget_id, prop_name, value) → None
rename_widget(widget_id, new_name) → None
```

Selection:

```python
select_widget(widget_id | None) → None
set_multi_selection(ids: set[str]) → None
```

Lookups:

```python
get_widget(widget_id) → WidgetNode | None
iter_all_widgets() → Iterator[WidgetNode]   # DFS, top-down
find_document_for_widget(widget_id) → Document | None
```

Documents:

```python
active_document → Document    # property
set_active_document(document_id) → None
get_document(document_id) → Document | None
add_document(...), remove_document(...), bring_document_to_front/back(...)
```

Variables (Phase 1 + 1.5):

```python
add_variable(entry, scope, document_id=None) → None
remove_variable(var_id) → None
get_tk_var(var_id) → tk.Variable | None              # lazy-creates on first call
get_variable_scope(var_id) → "global" | "local" | None
find_document_for_variable(var_id) → Document | None
migrate_local_var_bindings(node, target_doc) → int   # cross-doc copy
```

Object references (Phase 3 / v1.10.8):

```python
add_object_reference(entry) → None
remove_object_reference(ref_id) → None
```

Lifecycle:

```python
clear() → None    # reset to empty single-document state
to_dict() / from_dict(...) → ...   # save/load (driven by io/project_saver,loader)
```

## Document — [app/core/document.py:49](../../app/core/document.py#L49)

One window inside a project (Main Window or Toplevel). 207 lines.

### Persistent fields

| Field | Type | Default | Purpose |
|---|---|---|---|
| `id` | `str` | UUID | Stable identity. |
| `name` | `str` | `"Main Window"` | Display name. Drives the exported class name (sanitized). |
| `color` | `str \| None` | `None` | User-picked accent. `None` = palette cycle. |
| `width` / `height` | `int` | `800` × `600` | Window size at design-time and export-time. |
| `canvas_x` / `canvas_y` | `int` | `0` × `0` | Where the document sits on the shared workspace canvas. |
| `is_toplevel` | `bool` | `False` | `False` → `class X(ctk.CTk)`. `True` → `ctk.CTkToplevel`. |
| `collapsed` | `bool` | `False` | Builder-only — when `True` the doc is hidden from the canvas (no rect / chrome / widget render) and surfaces as a chip on the bottom tab strip. Persisted; widgets are lazy-built on expand. |
| `ghosted` | `bool` | `False` | Builder-only — when `True` the doc's live widgets are destroyed and replaced with a desaturated PIL screenshot at the same `canvas_x` / `canvas_y`. Persisted; restored post-load via the in-memory `_pending_ghost` flag once widgets exist (legacy path) or directly from `ghost_image` when present. |
| `ghost_image` | `str` (base64 PNG) | absent | Persisted screenshot for a ghosted doc. Encoded on save when `ghosted=True` and `Document._cached_ghost_pil` is populated. Inflated on load into `_cached_ghost_pil`; `GhostManager.freeze_from_cache` places it verbatim — no `ImageGrab` race against the startup paint. Absent for legacy projects or live docs. |
| `window_properties` | `dict` | `DEFAULT_WINDOW_PROPERTIES` | Window-level config. See below. |
| `root_widgets` | `list[WidgetNode]` | `[]` | Top-level widget tree for this document. |
| `description` | `str` | `""` | AI-bridge plain-language description (emitted as code comments). |
| `local_variables` | `list[VariableEntry]` | `[]` | Per-document variables (scope="local"). |
| `local_object_references` | `list[ObjectReferenceEntry]` | `[]` | Per-document widget references. |
| `name_counters` | `dict[str, int]` | `{}` | Per-doc auto-naming counter. `{"CTkButton": 3, ...}`. |
| `attached_scripts` | `list[str]` | `[]` | **v1.38 (legacy).** Library-script paths (page-folder-relative) bound to this window. Drives event-picker scope + behavior-file imports at export. Behavior file is implicitly attached and stays out of this list. |
| `attached_components` | `list[dict]` | `[]` | **v1.42+ (CTkScript model).** Window-scope scripts attached to this document — each `{"script": <scripts/-relative path>, "class": <ClassName>}`. Instantiated at export with `self.window` injected (the script can reach all widgets). See [script_optimization.md](../plans/script_optimization.md). |

### `window_properties` schema — [document.py:26](../../app/core/document.py#L26)

```python
{
    "fg_color": "transparent",          # window background
    "resizable_x": True,                # exported as resizable(True, ...)
    "resizable_y": True,
    "frameless": False,                 # overrideredirect(True) when True
    "grid_style": "dots",               # builder-only — never exported
    "grid_color": "#555555",            # builder-only
    "grid_spacing": 20,                 # builder-only
    "layout_type": "place",             # "place" | "vbox" | "hbox" | "grid"
    "alignment_lines_enabled": True,    # builder-only — snap guides
    "snap_enabled": True,               # builder-only
}
```

`grid_*`, `alignment_lines_enabled`, `snap_enabled` are design-time only — never reach the exported `.py`.

## WidgetNode — [app/core/widget_node.py:12](../../app/core/widget_node.py#L12)

Tree node — one widget on the canvas. 129 lines.

### Fields

| Field | Type | Default | Purpose |
|---|---|---|---|
| `id` | `str` | UUID | Stable identity. |
| `name` | `str` | `""` | User-facing name. Drives generated variable name in export (sanitized). |
| `widget_type` | `str` | required | `"CTkButton"`, `"CTkLabel"`, `"Card"`, etc. Must match a registered descriptor. |
| `properties` | `dict` | `{}` | Schema-keyed property values. See [WIDGETS.md](WIDGETS.md). |
| `children` | `list[WidgetNode]` | `[]` | Direct children (recursive tree). |
| `parent` | `WidgetNode \| None` | `None` | Back-reference. Not serialized — rebuilt on load. |
| `parent_slot` | `str \| None` | `None` | Sub-master name. Currently only used by `CTkTabview` (tab name). |
| `visible` | `bool` | `True` | Builder-only render skip. Hidden nodes still save and export. |
| `locked` | `bool` | `False` | Builder-only edit lock. Cascades through descendants. |
| `group_id` | `str \| None` | `None` | Group membership (Ctrl+G). Skipped from export. |
| `description` | `str` | `""` | AI-bridge — emitted as comment above the widget's constructor. |
| `handlers` | `dict[str, list]` | `{}` | **Phase 2.** Event → ordered list of handler entries. Each entry is a `script_call` dict (CTkScript model, current), or a method-name string / `ref_call` / `library_call` dict (legacy) — see schema below. |
| `attached_components` | `list[dict]` | `[]` | **v1.42+ (CTkScript model).** Scripts attached to this widget — each `{"script": <scripts/-relative path>, "class": <ClassName>}`. Instantiated at export with `self.widget` injected (widget scope — does **not** know the window). See [script_optimization.md](../plans/script_optimization.md). |

### `handlers` schema

Keys are event identifiers:

- `"command"` — click-style (Button, Switch, CheckBox, Slider, OptionMenu, ComboBox, SegmentedButton)
- `"bind:<sequence>"` — Tk bind (`"bind:<Button-1>"`, `"bind:<Return>"`, etc.)

Values are ordered lists of handler **entries**. Empty list = unbound. Multi-entry binding fans out via `lambda` chain (constructor kwarg) or repeated `.bind(seq, fn, add="+")` (Tk bind).

Each entry is one of:

| Shape | Meaning |
|---|---|
| `str` (non-empty) | Method name on the window's behavior class. The exporter resolves it to `self._behavior.<name>`. The file is the user's source of truth: no auto-stub creation, no auto-delete on unbind — the Function picker only lists `def`s actually present in the file. |
| `str` (empty `""`) | Page Script target picked, function not chosen yet. The Properties panel renders this with the Function row showing `Pick function…`; the exporter filters it out and emits a Console warning (`Method not found: ''`). |
| `dict` with `{"kind": "ref_call", "ref": <ref_name>, "method": <method_name>, "args": [...]}` | Direct widget-to-widget call routed through an Object Reference (v3). `args` is a list of `{"name": str, "type": "str"\|"int"\|"float"\|"bool", "value": Any, "kwarg": bool}` dicts. Method must be in [`WIDGET_ACTION_METHODS`](../../app/widgets/action_registry.py) for the referenced widget's type — out-of-allowlist entries get dropped at export with the same warning surface as missing behavior methods. Empty `method` = ref picked, function not chosen yet (same pending state as the empty-string page entry). |
| `dict` with `{"kind": "library_call", "script": <page_folder_relative_path>, "method": <function_name>, "args": [...]}` | Module-level function call into an attached library script (v1.38). `script` must appear in the owning Document's `attached_scripts` list. `method` must be a public top-level `def` in that file (signature filtered same as page methods). Exports as `<module>.<func>(...)` — module name = basename stripped of `.py`, kept in scope by the generated file's `from assets.scripts.<page>[.<sub>] import <module>` line. Empty `method` = library script picked, function not chosen yet. |
| `dict` with `{"kind": "script_call", "class": <ClassName>, "method": <method_name>}` | **CTkScript model (current).** Call a public method on a CTkScript component attached to this widget (its own scope), or to the owning window (fallback). `class` must match an entry in this widget's or the window's `attached_components`; the script path is resolved from there at export. Exports as `self._script_N.<method>()`. Bindings that no longer resolve (script detached after wiring) render red in the panel and are dropped at export. Empty `method` = component picked, function not chosen yet. |

> **Legacy vs current.** The page-method string, `ref_call`, and `library_call` shapes — plus the behavior file and Object References — are the **legacy** model. The **current** model is `script_call` + `attached_components` (CTkScript). Both coexist until the legacy machinery is retired — see [script_optimization.md](../plans/script_optimization.md).

The legacy behavior file lives at `<project>/assets/scripts/<page_slug>/<window_slug>.py`. CTkScript scripts live in the top-level `<project>/scripts/` folder (outside `assets/`).

**Pending UI rows are NOT stored here.** The Unity-style "Add target" placeholder (outer `[+]` click on the event header before any target is picked) lives in `PropertiesPanel._pending_event_rows`, scoped per `(widget_id, event_key)`. Pending rows clear when the user switches widget — they exist only as transient editing state, not as model data. As soon as the user picks a target, the entry commits to ``handlers`` (with empty method, since the Function picker is a separate step).

### Backwards-compat — type renames

[widget_node.py:7](../../app/core/widget_node.py#L7):

```python
_WIDGET_TYPE_RENAMES = {
    "Shape": "Card",   # 2026-04-27
}
```

Loader silently maps old names to current ones.

### Backwards-compat — handler shape

`from_dict` accepts three shapes:

- v1: `{event: "method"}` (single string) — wrapped into a one-element list at load.
- v2: `{event: ["m1", "m2"]}` (multi-method list of strings).
- v3: `{event: ["m1", {"kind": "ref_call", ...}]}` (mixed list — string entries are page methods, dict entries are widget-to-widget calls via Object Reference).

Dict entries without `"kind": "ref_call"` are dropped at load to keep the live model strict.

## VariableEntry — [app/core/variables.py:31](../../app/core/variables.py#L31)

Phase 1 / 1.5. Dataclass.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `id` | `str` | UUID | Stable. Referenced by `var:<uuid>` tokens. |
| `name` | `str` | `""` | Display name. Sanitized for export — see [variables.py:242](../../app/core/variables.py#L242). |
| `type` | `"str" \| "int" \| "float" \| "bool" \| "color"` | `"str"` | Maps to `tk.StringVar` / `IntVar` / `DoubleVar` / `BooleanVar`. `color` reuses `StringVar` — the type tag only changes the editor surface (swatch + picker) and bind-picker filtering for color-typed properties. |
| `default` | `str` | `""` | String form of initial value. Coerced at runtime. For `color`, must be `#rgb` / `#rrggbb`; invalid input falls back to `#000000`. |
| `scope` | `"global" \| "local"` | `"global"` | Lives on `Project.variables` (global — page-scoped, active page only) or `Document.local_variables` (local). |

### Tokens

A widget property bound to a variable holds the string `"var:<uuid>"`:

```python
make_var_token(var_id) → "var:<uuid>"
is_var_token(value) → bool
parse_var_token(value) → str | None    # returns the UUID, or None
```

### Runtime resolution — [variables.py:191](../../app/core/variables.py#L191)

`resolve_bindings(project, widget_type, properties)` walks a property dict:

1. For tokens whose `(widget_type, prop_name)` is in `BINDING_WIRINGS` → strip the property, emit `{tk_kwarg: tk.Variable}` so the descriptor passes the live variable to CTk's constructor.
2. For tokens without a wiring entry (cosmetic bindings — e.g. `fg_color`) → replace token with current literal value.
3. For tokens pointing at a deleted variable → strip the property; descriptor falls back to its default.

### `BINDING_WIRINGS` table — [variables.py:163](../../app/core/variables.py#L163)

```python
{
    ("CTkLabel", "text"):                  "textvariable",
    ("CTkEntry", "initial_value"):         "textvariable",
    ("CTkSlider", "initial_value"):        "variable",
    ("CTkSwitch", "initially_checked"):    "variable",
    ("CTkCheckBox", "initially_checked"):  "variable",
    ("CTkSegmentedButton", "segment_initial"): "variable",
    ("CTkOptionMenu", "initial_value"):    "variable",
    ("CTkComboBox", "initial_value"):      "variable",
}
```

Properties in this table get live two-way / one-way Tk syncing for free. Properties NOT in this table can still be bound; they just snapshot the variable's current value at create time.

### Variable type ↔ property type compatibility — [variables.py:175](../../app/core/variables.py#L175)

```python
_PTYPE_VAR_COMPAT = {
    "boolean": ("bool", "int"),
    "number":  ("int", "float"),
}
# default: ("str",)
```

The Properties panel uses this to decide which variables to offer in the bind menu for a given property.

### Type short labels — [variables.py:36](../../app/core/variables.py#L36)

`VAR_TYPE_SHORT` maps each variable type to a 3-letter chip the Window Properties panel renders next to the variable's name (mirrors `TYPE_SHORT_LABELS` for widget refs):

```python
"str" → "str"     "int" → "int"     "float" → "flt"
"bool" → "bol"    "color" → "col"
```

Color rows additionally get a hue swatch in the value column next to the hex code.

## ObjectReferenceEntry — [app/core/object_references.py:73](../../app/core/object_references.py#L73)

v1.10.8. Replaces "Behavior Fields". Dataclass.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `id` | `str` | UUID | Stable. |
| `name` | `str` | `""` | Python identifier. Validated — see below. |
| `target_type` | `str` | `"CTkLabel"` | What kind of widget/window this slot points at. |
| `scope` | `"global" \| "local"` | `"local"` | See scope rules. |
| `target_id` | `str` | `""` | `Document.id` (global) or `WidgetNode.id` (local). `""` = unbound. |

### Scope rules — [object_references.py:113](../../app/core/object_references.py#L113)

```python
required_scope_for(target_type) → "global" | "local"

# target_type in ("Window", "Dialog") → must be global
# anything else → must be local
```

Documents are referenced globally (they exist for the whole program lifetime). Inner widgets are local — they belong to one document, so cross-document refs would be phantoms.

### Name validation — [object_references.py:122](../../app/core/object_references.py#L122)

`is_valid_python_identifier(name)`:

- Must be `str.isidentifier()`
- Must not be a Python keyword

Generated code uses `self.<name>` directly — no sanitization at export.

### Suggestion — [object_references.py:137](../../app/core/object_references.py#L137)

`suggest_ref_name(target_label, target_type, existing_names)` produces a default identifier:

1. Use widget's user-facing name if it's already a valid identifier.
2. Else fall back to `<lowercase_type>_ref` (with `CTk` prefix stripped — `CTkButton` → `button_ref`).
3. Suffix `_2` / `_3` / ... if the chosen base collides.

### Type short labels — [object_references.py:41](../../app/core/object_references.py#L41)

`TYPE_SHORT_LABELS` maps full type names to 3-letter abbreviations for display in narrow columns:

```python
"CTkButton" → "Btn"     "CTkLabel" → "Lbl"     "Window" → "Win"
"CTkSlider" → "Sld"     "Card" → "Crd"         "Dialog" → "Dlg"
# ... 21 entries total
```

## Save format

JSON, schema version 2. Two layouts:

### Multi-page project (default for new projects)

`<project>/project.json` — project-level metadata, single source of truth:

```json
{
    "version": 1,
    "name": "MyProject",
    "active_page": "<page-uuid>",
    "pages": [
        { "id": "<page-uuid>", "file": "main.ctkproj", "name": "Main" },
        ...
    ],
    "font_defaults": { "_all": "Inter", "CTkButton": "Roboto" },
    "system_fonts": [ "Segoe UI" ]
}
```

`<project>/assets/pages/<page_slug>.ctkproj` — one per page, page-level fields:

```json
{
    "version": 2,
    "active_document": "<doc-uuid>",
    "documents": [
        {
            "id": "<doc-uuid>",
            "name": "Main Window",
            "is_toplevel": false,
            "width": 800, "height": 600,
            "canvas_x": 0, "canvas_y": 0,
            "color": null,
            "window_properties": { ... },
            "widgets": [ <WidgetNode.to_dict()>, ... ],
            "name_counters": { "CTkButton": 3 },
            "description": "",
            "local_variables": [ ... ],
            "local_object_references": [ ... ]
        }
    ],
    "variables": [ <VariableEntry.to_dict()>, ... ],
    "object_references": [ <ObjectReferenceEntry.to_dict()>, ... ]
}
```

Variables and object references are **page-scoped** — each page's `.ctkproj` owns its own set. Truly project-level fields (`name`, `font_defaults`, `system_fonts`) stay in `project.json`. Pages don't share variables at runtime; they export as independent `.py` files.

Legacy migration: projects whose `project.json` still has `variables` / `object_references` from the old project-wide scheme — those values flow into the active page on first load; the next save writes them into the page `.ctkproj` and drops the legacy `project.json` copies. Non-active pages don't receive the legacy globals.

Shared assets live in `<project>/assets/{images,fonts,icons,scripts,components}/`.

### Legacy single-file project

A lone `.ctkproj` with no `project.json`. Carries everything in one file:

```json
{
    "version": 2,
    "name": "MyProject",
    "active_document": "<doc-uuid>",
    "documents": [ ... ],
    "variables": [ ... ],
    "object_references": [ ... ],
    "font_defaults": { ... },
    "system_fonts": [ ... ]
}
```

The saver keeps writing the project-level fields when `Project.folder_path is None` so single-file projects round-trip without losing metadata.

### Migration

- **v1 → v2** runs on load in `project_loader.py`.
- Legacy `behavior_field_values` JSON entries (pre-v1.10.8) → migrated to `local_object_references` directly inside `Document.from_dict`. Target type defaults to `CTkLabel` (legacy JSON didn't carry type info). Next save drops the field naturally.
- Widget type renames (e.g. `Shape` → `Card`) applied silently at `WidgetNode.from_dict`.
- Handler shape `{event: "method"}` (v1 single-string) wrapped to `{event: ["method"]}` at load.

## Sentinels and constants

| Constant | Where | Value | Purpose |
|---|---|---|---|
| `WINDOW_ID` | [project.py:60](../../app/core/project.py#L60) | `"__window__"` | Sentinel ID for the virtual "Window" node — selected when the user clicks the document chrome. Routes property reads through `Project.window_properties`. |
| `VAR_TOKEN_PREFIX` | [variables.py:28](../../app/core/variables.py#L28) | `"var:"` | Prefix for variable binding tokens. |
| `DEFAULT_DOCUMENT_WIDTH` / `_HEIGHT` | [document.py:23](../../app/core/document.py#L23) | `800` / `600` | New-document defaults. |
| `DEFAULT_WINDOW_PROPERTIES` | [document.py:26](../../app/core/document.py#L26) | dict | Fresh-document `window_properties`. |
| `DOCUMENT_TARGET_TYPES` | [object_references.py:36](../../app/core/object_references.py#L36) | `("Window", "Dialog")` | Which target types must use `scope="global"`. |

## What's NOT a class

**Handlers** are not a separate class — they live as `WidgetNode.handlers: dict[str, list[str]]`. Method names are strings; the actual `def`s live in the per-window behavior file at `<project>/assets/scripts/<page>/<window>.py`. Behavior file generation, AST scanning, and stub creation live in [app/io/scripts.py](../../app/io/scripts.py).

**Components** (`.ctkcomp`) are zip bundles, not in-memory model classes. Pack/unpack lives in [app/io/component_io.py](../../app/io/component_io.py); the bundle contains a `component.json` manifest plus a copy of the relevant assets.

**Selection groups** are not a separate class — `WidgetNode.group_id` is a string tag. All widgets sharing a tag select / drag / delete together. Skipped from code export.
