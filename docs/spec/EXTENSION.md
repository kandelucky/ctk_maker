# CTkMaker — Extension Points

Where the system is designed to be extended. Three subsystems:

1. **Widget descriptors** — adding a new widget type
2. **Property editors** — adding a new schema property type
3. **Event registry** — adding handler events for a widget
4. **Components** — `.ctkcomp` import/export (user-facing extension, not code-level)

There is no plugin system or external hook mechanism — every extension lands as a Python source file in the existing tree.

## Widget descriptors

Each widget is one Python file in [app/widgets/](../../app/widgets/) with a `WidgetDescriptor` subclass. The descriptor declares:

- **Schema** — what properties exist, their types, defaults, ranges
- **Runtime hooks** — how to instantiate, how to apply state changes
- **Export hooks** — what to emit at code generation time
- **Container behavior** — whether it can hold children, where they live

### `WidgetDescriptor` base class — [app/widgets/base.py](../../app/widgets/base.py)

| Class attribute | Type | Default | Purpose |
|---|---|---|---|
| `type_name` | `str` | `""` | Registry key. Stored in `WidgetNode.widget_type`. |
| `display_name` | `str` | `""` | Palette label, Properties header. |
| `ctk_class_name` | `str` | `type_name` | Generated code emits `ctk.<ctk_class_name>(...)`. Override when builder name ≠ CTk class. |
| `default_properties` | `dict` | `{}` | Initial values for new widgets. Merged with `property_schema` defaults. |
| `property_schema` | `list[dict]` | `[]` | Per-property metadata: name, type, label, group, range, enum values, etc. Drives the Properties panel. |
| `is_container` | `bool` | `False` | True if the widget can host children (`CTkFrame`, `CTkTabview`, layout containers). |
| `is_ctk_class` | `bool` | `True` | False = inline class definition in exported file (e.g. `CircularProgress`). |
| `image_inline_kwarg` | `bool` | `True` | Auto-emit `image=CTkImage(...)` constructor kwarg. False for widgets whose CTk class rejects `image=`. |
| `multiline_list_keys` | `set[str]` | `set()` | Property keys whose editor stores newline-separated strings; exporter splits on `\n` to emit a list. |
| `init_only_keys` | `set[str]` | `set()` | Properties CTk accepts only at `__init__`; runtime change → destroy + recreate via `recreate_triggers`. |
| `prefers_fill_in_layout` | `bool` | `False` | Auto-fill hint — when dropped into vbox/hbox/grid, sets `stretch="fill"` / `grid_sticky="nsew"`. |

### Hooks — [app/widgets/base.py](../../app/widgets/base.py)

```python
@classmethod
def transform_properties(cls, properties: dict) -> dict
    # Builder props → CTk constructor kwargs. Strip _NODE_ONLY_KEYS,
    # rename keys, handle special encodings (font_*, state_disabled).

@classmethod
def create_widget(cls, master, properties: dict, init_kwargs=None) -> widget
    # Build the actual CTk widget. init_kwargs holds workspace-injected
    # extras (e.g. shared tk.IntVar for a radio group).

@classmethod
def apply_state(cls, widget, properties: dict) -> None
    # Runtime state that can't go through configure() — .set(value),
    # .select(), .insert(0, text). Called after create + after every
    # property change. Default no-op.

@classmethod
def on_prop_recreate(cls, prop_name: str, properties: dict) -> dict
    # Hook before destroy/recreate when a recreate_triggers prop changes.
    # Returns property overrides to commit before recreate (e.g. swap
    # width/height when flipping a progress bar's orientation).

@classmethod
def before_recreate(cls, node, widget, prop_name: str) -> None
    # Last-chance hook — migrate child state that depends on the soon-
    # to-be-destroyed widget. CTkTabview uses this to remap children's
    # parent_slot when a tab is renamed.

@classmethod
def child_master(cls, widget, child_node) -> tk.Misc
    # Where children attach. Defaults to the widget itself. CTkTabview
    # returns widget.tab(child.parent_slot); CTkScrollableFrame returns
    # the inner scroll surface.

@classmethod
def canvas_anchor(cls, widget) -> tk.Misc
    # Which widget the workspace embeds via canvas.create_window.
    # CTkScrollableFrame's outer wrapper, otherwise the widget itself.

@classmethod
def export_kwarg_overrides(cls, properties: dict) -> dict
    # Per-descriptor kwarg overrides for code generation. Replaces
    # raw values from properties (e.g. CTkSlider's number_of_steps=0
    # → None at export).

@classmethod
def export_state(cls, var_name: str, properties: dict) -> list[str]
    # Lines emitted AFTER constructor + .place(). Used for runtime
    # state mirroring apply_state — .set(...), .select(), .insert(0, ...).
```

### Property schema entries

Each entry in `property_schema` is a dict:

```python
{
    "name": "fg_color",                 # storage key (also in default_properties)
    "type": "color",                    # editor type — see Property editors below
    "label": "Foreground Color",        # Properties panel display
    "group": "Colors",                  # collapsible section header
    "subgroup": "Background",           # nested heading (optional)

    # Type-specific:
    "min": 0, "max": 100, "step": 1,    # number
    "values": ["left", "right"],        # enum
    "supports_transparent": True,       # color
    "tk_init_kwarg": "textvariable",    # variable wiring (rare — driven by BINDING_WIRINGS)

    # Conditional:
    "disabled_when": {"button_enabled": False},   # gray out when condition true
    "hidden_when": {"is_circle": True},           # hide entire row

    # Recreate semantics:
    "recreate_triggers": True,          # full destroy/recreate on change

    # Variable binding compatibility:
    "ptype": "number",                  # falls back to type; consulted by compatible_var_types
}
```

### Adding a new widget — 3 steps

1. **Create the descriptor** at `app/widgets/<name>.py`:

```python
from app.widgets.base import WidgetDescriptor
import customtkinter as ctk

class CTkFooDescriptor(WidgetDescriptor):
    type_name = "CTkFoo"
    display_name = "Foo"
    ctk_class_name = "CTkFoo"
    default_properties = {
        "x": 0, "y": 0, "width": 100, "height": 30,
        "text": "Foo",
        "fg_color": "transparent",
    }
    property_schema = [
        {"name": "text", "type": "string", "label": "Text", "group": "Content"},
        {"name": "fg_color", "type": "color", "label": "Background", "group": "Colors"},
    ]

    @classmethod
    def create_widget(cls, master, properties, init_kwargs=None):
        kwargs = cls.transform_properties(properties)
        if init_kwargs:
            kwargs.update(init_kwargs)
        return ctk.CTkFoo(master, **kwargs)
```

2. **Register it** in [app/widgets/registry.py](../../app/widgets/registry.py):

```python
from app.widgets.ctk_foo import CTkFooDescriptor

_REGISTRY: dict[str, type[WidgetDescriptor]] = {
    ...
    CTkFooDescriptor.type_name: CTkFooDescriptor,
}
```

3. **(Optional) Add to event registry** at [app/widgets/event_registry.py](../../app/widgets/event_registry.py) if the widget has events:

```python
EVENT_REGISTRY["CTkFoo"] = [
    EventEntry("command", "on click", "click", "(self)", _COMMAND),
]
```

That's the whole extension. No registration in palette, no manual import in MainWindow, no Properties panel changes.

### Existing descriptors — [app/widgets/registry.py](../../app/widgets/registry.py)

20 descriptor classes. Three palette entries (Vertical Layout, Horizontal Layout, Grid Layout) share `CTkFrame` with different preset overrides — see [app/ui/palette.py:CATALOG](../../app/ui/palette.py) for the 21 palette entries that map onto these descriptors. One descriptor (`WindowDescriptor`) is not a real palette widget — it represents window-level properties.

| Type name | File | Display | Container | Notes |
|---|---|---|---|---|
| `Window` | `window_descriptor.py` | — | — | Document metadata, not a palette widget |
| `CTkButton` | `ctk_button.py` | Button | | Custom `CircleButton` shape support |
| `CTkLabel` | `ctk_label.py` | Label | | Image + text composition |
| `CTkEntry` | `ctk_entry.py` | Entry | | textvariable binding |
| `CTkTextbox` | `ctk_textbox.py` | Textbox | | Multiline |
| `CTkCheckBox` | `ctk_check_box.py` | Check Box | | variable binding |
| `CTkSwitch` | `ctk_switch.py` | Switch | | variable binding |
| `CTkRadioButton` | `ctk_radio_button.py` | Radio Button | | Group wiring via shared variable |
| `CTkSegmentedButton` | `ctk_segmented_button.py` | Segmented Button | | variable binding |
| `CTkSlider` | `ctk_slider.py` | Slider | | variable binding |
| `CTkProgressBar` | `ctk_progress_bar.py` | Progress Bar | | Orient toggle = recreate |
| `CTkComboBox` | `ctk_combo_box.py` | Combo Box | | Editable + scrollable dropdown |
| `CTkOptionMenu` | `ctk_option_menu.py` | Option Menu | | Scrollable dropdown |
| `CTkFrame` | `ctk_frame.py` | Frame | ✓ | Plain container |
| `CTkScrollableFrame` | `ctk_scrollable_frame.py` | Scrollable Frame | ✓ | Composite — outer wrapper + inner scroll |
| `CTkTabview` | `ctk_tabview.py` | Tab View | ✓ | Children carry `parent_slot` (tab name) |
| `Image` | `image.py` | Image | | Builder composite — exports as `CTkLabel(text="", image=...)` |
| `Card` | `card.py` | Card | ✓ | Rectangle / rounded / circle + embedded image |
| `CircularProgress` | `circular_progress.py` | Circular Progress | | Custom class — inlined into export, not from `customtkinter` |

Plus `scrollable_dropdown.py` — a runtime helper sidecar-copied next to exports that use `CTkComboBox` / `CTkOptionMenu`.

### Layout containers

`CTkFrame` and the layout-aware containers are configured via [app/widgets/layout_schema.py](../../app/widgets/layout_schema.py):

```python
DEFAULT_LAYOUT_TYPE = "place"               # "place" | "vbox" | "hbox" | "grid"

LAYOUT_DEFAULTS = {
    "vbox": { ... pack defaults ... },
    "hbox": { ... },
    "grid": { ... },
}

LAYOUT_CONTAINER_DEFAULTS = {
    "vbox": { ... container-side defaults ... },
}

LAYOUT_NODE_ONLY_KEYS = { ... keys not passed to CTk ... }
```

The Properties panel reads these to build the Layout group when the parent's `layout_type` is non-`place`.

## Property editors

Per-row UI for the Properties panel. One file per editor type at [app/ui/properties_panel/editors/](../../app/ui/properties_panel/editors/).

### Editor base class — [editors/base.py](../../app/ui/properties_panel/editors/base.py)

```python
class Editor:
    def populate(self, panel, iid, pname, prop, value) -> None:
        # Attach overlays for this row after the tree item exists.

    def refresh(self, panel, iid, pname, prop, value) -> None:
        # Update overlay appearance after value changes.

    def set_disabled(self, panel, iid, pname, prop, disabled) -> None:
        # Sync overlay colors with disabled_when state.

    def on_single_click(self, panel, pname, prop) -> bool:
        # Return True if handled; False falls through.

    def on_double_click(self, panel, pname, prop, event) -> bool:
        # Return True if handled.
```

All methods default to no-op. Concrete editors override only what they need.

### Existing editors

| File | Schema `type` value | Purpose |
|---|---|---|
| `boolean.py` | `"boolean"` | Toggle switch (in the tree value column). |
| `color.py` | `"color"` | Color swatch + click → ColorPickerDialog + eyedropper. |
| `enum.py` | `"enum"` | Dropdown with `values` from schema. Supports `image_per_value` for visual choices. |
| `font.py` | `"font"` | Font family + size + bold/italic/underline/overstrike toggles. Paired family + size editor. |
| `image.py` | `"image"` | Asset picker — browse images / paste / Lucide icon picker / clear. |
| `multiline.py` | `"multiline"` | Textbox overlay for newline-separated strings. |
| `number.py` | `"number"` | Number entry + drag-scrub on the value column. |
| `segment_values.py` | `"segment_values"` | List editor for `CTkSegmentedButton.values` — add/remove/reorder. |
| `unit.py` | `"unit"` | Number + unit suffix dropdown (e.g. CircularProgress text suffix). |

### Adding a new property editor

1. Create `app/ui/properties_panel/editors/<name>.py` with an `Editor` subclass.
2. Register the type → editor mapping in `app/ui/properties_panel/panel.py` (look for the `_EDITORS` dict initialization).
3. Use `"type": "<name>"` in any widget descriptor's `property_schema`.

### Overlay registry

Editors that need persistent on-row widgets (color swatches, drag-scrub overlays) register them via the panel's overlay tracking dicts in `properties_panel/overlays.py`. The panel handles repositioning on scroll / tree refresh.

## Property tooltips

Hovering over a row's label column (`#0`) for ~750 ms surfaces a dark popup with a description and an optional ⚠ warning. Content lives in `properties_panel/property_help.py`:

- `PROPERTY_HELP[<pname>]` — for `p:<pname>` rows.
- `ROW_HELP["pair:<name>"]` — for virtual numeric pairs (Position, Size, …).
- `ROW_HELP["g:<group>/<sub>"]` — for schema subgroups (e.g. `Text/Style`).

Event-header rows (`events:e:N`) source from `EventEntry.description` + `EventEntry.warning` in [`app/widgets/event_registry.py`](../../app/widgets/event_registry.py) — no per-event entries needed in `property_help.py`. Description falls back to the capitalised `label` when empty.

V1 scope is CTkLabel; other widgets fall back to no tooltip (event rows excepted — they work for every widget). Adding entries for another widget = filling more keys in the same two dicts.

## Event registry

[app/widgets/event_registry.py](../../app/widgets/event_registry.py) — Phase 2 — defines what events each widget can have handlers for.

### `EventEntry` schema

```python
@dataclass(frozen=True)
class EventEntry:
    key: str           # WidgetNode.handlers key — "command" or "bind:<seq>"
    label: str         # human-readable: "on click", "on Return"
    verb: str          # method name suffix: on_<widget>_<verb>
    signature: str     # "(self)" or "(self, value)" or "(self, event=None)"
    wiring_kind: str   # "command" → constructor kwarg
                       # "bind"    → post-construction widget.bind(seq, fn, add="+")
    warning: str = ""  # optional caveat shown alongside the event in
                       # cascades / docs — e.g. "fires at 60+ Hz" or
                       # "requires takefocus=True". Default empty.
    advanced: bool = False  # when True, the entry renders inside a
                            # collapsible "Advanced" sub-section in
                            # the right-click cascade and Properties
                            # panel instead of the flat default list.
                            # Used to keep the surface short for
                            # widgets with many bind events
                            # (CTkLabel: 5 default + 11 advanced).
    description: str = ""   # one-line "what does this event do" —
                            # surfaced in the Properties panel hover
                            # tooltip on event-header rows. Empty
                            # falls back to the capitalised label.
```

`events_partitioned(widget_type)` returns `(default, advanced)` in registration order — the cascade builder ([app/ui/workspace/core.py](../../app/ui/workspace/core.py)) and the Properties panel ([app/ui/properties_panel/panel_schema.py](../../app/ui/properties_panel/panel_schema.py)) both call it so they stay in sync without re-implementing the partition.

### Existing entries — [event_registry.py:41](../../app/widgets/event_registry.py#L41)

```python
EVENT_REGISTRY = {
    "CTkButton":          [EventEntry("command", "on click",  ...)],
    "CTkSwitch":          [EventEntry("command", "on toggle", ...)],
    "CTkCheckBox":        [EventEntry("command", "on toggle", ...)],
    "CTkRadioButton":     [EventEntry("command", "on select", ...)],
    "CTkSlider":          [EventEntry("command", "on change", ...)],
    "CTkSegmentedButton": [EventEntry("command", "on select", ...)],
    "CTkComboBox":        [EventEntry("command", "on select", ...)],
    "CTkOptionMenu":      [EventEntry("command", "on select", ...)],
    "CTkEntry":           [EventEntry("bind:<Return>", "on Return", ...)],
    "CTkTextbox":         [EventEntry("bind:<KeyRelease>", ...)],
    "CTkLabel":           [EventEntry("bind:<Button-1>", "on click", ...),
                           # 16 bind events total — mouse buttons,
                           # motion / wheel, lifecycle, focus / keyboard
                          ],
}
```

CTkLabel uses bind-style events exclusively (no `command=` constructor kwarg in standard CTkLabel). Six of its 16 events carry `warning` strings — `<Motion>` / `<Configure>` for high-frequency firing, and `<FocusIn>` / `<FocusOut>` / `<KeyPress>` / `<KeyRelease>` for the `takefocus=True` requirement.

### Adding events for a new widget

Extend the `EVENT_REGISTRY` dict. The Properties panel "Events" group reads it to populate the dropdown of available events when the user clicks `[+]`.

## Components — `.ctkcomp`

User-facing extension. Components are zip bundles with a `component.json` manifest plus a copy of the relevant assets. Pack/unpack lives in [app/io/component_io.py](../../app/io/component_io.py).

### Bundle structure

```
my_component.ctkcomp     (zip file)
├── component.json       (manifest — name, author, license, version, ...)
├── widgets.json         (WidgetNode tree snapshot)
├── variables.json       (optional — bundled variable declarations)
├── assets/              (only the assets this component references)
│   ├── images/
│   ├── fonts/
│   └── icons/
└── thumbnail.png        (optional — preview)
```

### Save flow — [component_io.py](../../app/io/component_io.py)

```python
save_fragment(target_path, name, nodes, project, source_window_id)
```

1. Snapshot nodes → dicts (`WidgetNode.to_dict()` recursive)
2. Collect asset references from properties (image tokens, font families)
3. Bundle variables (local + global, demoted to local on insert)
4. Zip into `.ctkcomp` with `component.json` manifest

### Load flow

```python
load_fragment(ctkcomp_path) → (nodes, variables, assets)
```

1. Unzip, read `component.json`
2. Re-UUID widget nodes + variables (avoid collisions with target project)
3. Rewrite asset tokens to new project paths
4. Return for caller to insert via `Project.add_widget(...)`

### Publish flow — [app/ui/component_publish_form_dialog.py](../../app/ui/component_publish_form_dialog.py)

Multi-step dialog cascade:
1. `component_save_dialog.py` — pick widgets, name the component
2. `component_export_choice_dialog.py` — local save vs publish to community
3. `component_publish_form_dialog.py` — author, category, description, MIT license agreement
4. Output: `.ctkproj_signed.zip` for the user to attach to a Community Hub Discussion post

## What's NOT extensible without code changes

- **Project save format** — versioned schema; new fields require migration code in `project_loader.py`.
- **Event bus channels** — adding a new channel requires both publisher and subscriber code.
- **Layout managers** — `place` / `vbox` / `hbox` / `grid` are hard-coded in [layout_schema.py](../../app/widgets/layout_schema.py); adding a new layout type requires exporter + workspace updates.
- **Asset kinds** — `images` / `fonts` / `icons` paths are hard-coded; a new asset kind needs path helper + token grammar updates.
- **Variable types** — `str` / `int` / `float` / `bool` / `color`. `color` is `StringVar`-backed (hex string at runtime) — the type only changes the Variables-window editor surface and bind-picker filtering, so it didn't need new `BINDING_WIRINGS` entries. Adding a genuinely new Tk-var-class type would still need `BINDING_WIRINGS` plus runtime + export coverage.
