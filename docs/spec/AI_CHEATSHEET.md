# CTkMaker — AI Cheatsheet

Distilled reference for prompting an AI to work with a CTkMaker project. Paste into an AI chat as a system message, then describe what you want built.

For full reference: [CONCEPTS.md](CONCEPTS.md), [WIDGETS.md](WIDGETS.md), [DATA_MODEL.md](DATA_MODEL.md), [EXPORT.md](EXPORT.md).

## What CTkMaker is

A visual designer for [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) Python GUIs. Users drag widgets onto a canvas, edit properties, attach event handlers, and export to runnable `.py` code. Visual design lives in `.ctkproj` files; behavior lives in hand-written Python alongside.

## Project layout

```
MyProject/
├── project.json                          page list, project name
└── assets/
    ├── pages/<page>.ctkproj              per-page design (one window or more)
    ├── images/, fonts/, icons/           shared assets
    ├── scripts/<page>/<window>.py        hand-written behavior, one class per window
    └── components/*.ctkcomp              reusable widget bundles (zip)
```

A **Page** is one `.ctkproj` (one screen — login, dashboard, settings, ...).
A **Window** lives inside a page — exactly one Main Window (`ctk.CTk`) plus zero or more Dialogs (`ctk.CTkToplevel`).

## Hierarchy

```
Project → has → Pages → has → Windows → has → Widgets (nested tree)
                                          → has → Variables (local)
                                          → has → Object References (local)
       → has → Variables (global)
       → has → Object References (global, target = Window/Dialog)
```

## Widgets — quick list

21 palette widgets across 5 groups (Display, Controls, Containers, Layouts, Indicators). See [WIDGETS.md](WIDGETS.md) for full property tables.

| Widget | Use for |
|---|---|
| `CTkButton` | Click action |
| `CTkLabel` | Static text + optional image |
| `CTkEntry` | Single-line text input |
| `CTkTextbox` | Multi-line text |
| `CTkCheckBox`, `CTkSwitch`, `CTkRadioButton` | Boolean / choice |
| `CTkSegmentedButton` | Multi-state choice |
| `CTkSlider` | Numeric drag |
| `CTkProgressBar`, `CircularProgress` | Visual progress |
| `CTkComboBox`, `CTkOptionMenu` | Dropdown |
| `CTkFrame`, `CTkScrollableFrame`, `CTkTabview` | Containers |
| `Card` | Styled container (rounded / circle, with embedded image) |
| `Image` | Image as a label |

## Common widget properties

Every widget has: `x`, `y`, `width`, `height` (in pixels — for `place` layout), `name` (used as the variable name in export when valid identifier). Then type-specific:

| Widget | Key property | Common extras |
|---|---|---|
| Button | `text`, `command` | `fg_color`, `hover_color`, `corner_radius`, `image`, `compound` |
| Label | `text` | `font_*`, `text_color` / `text_color_disabled`, `corner_radius`, `image` / `compound`, `anchor`, `padx` / `pady`, `label_enabled`, `cursor`, `takefocus`, `fg_color` / `bg_color` |
| Entry | `placeholder_text`, `initial_value` | `font_*`, `width`, `show` (password) |
| Textbox | `initial_value` | `wrap`, font props |
| Slider | `from_`, `to`, `initial_value` | `orientation`, `number_of_steps` |
| Switch / CheckBox | `text`, `initially_checked` | `onvalue`, `offvalue` |
| Card | (no children kwargs) | `shape` (rectangle/rounded/circle), `image` |

## Layout

Each window's direct children use one **layout type**:

- `place` (default) — absolute `x, y, width, height` per child
- `vbox` — vertical pack
- `hbox` — horizontal pack
- `grid` — `row`, `column`, `sticky`

Nesting: a `CTkFrame` can have its own layout type for its children, independent of the window's. **Limitation:** layout-in-layout depth is currently 1 — a frame inside a vbox can't itself be a vbox. Use `place` inside layout containers.

## Variables (shared state)

Two scopes:

- **Global** — visible to every window in every page. On Project. Use for app-wide state.
- **Local** — visible only to widgets in one window. On Document. Use for window-internal state.

Five types: `str`, `int`, `float`, `bool`, `color` → backed by `tk.StringVar`, `IntVar`, `DoubleVar`, `BooleanVar`, `StringVar`. `color` stores a hex string (`#rrggbb` / `#rgb`) and edits via swatch + picker; the bind-picker on color properties (`fg_color`, `text_color`, `border_color`, …) lists `color` and `str` variables.

Bind from the Properties panel — click the ◇ chip next to a property.

**Auto-wired bindings** (sync live):

| Widget | Property | Wires to |
|---|---|---|
| `CTkLabel` | `text` | `textvariable=` |
| `CTkEntry` | `initial_value` | `textvariable=` |
| `CTkSlider` | `initial_value` | `variable=` |
| `CTkSwitch` | `initially_checked` | `variable=` |
| `CTkCheckBox` | `initially_checked` | `variable=` |
| `CTkSegmentedButton` | `segment_initial` | `variable=` |
| `CTkOptionMenu` | `initial_value` | `variable=` |
| `CTkComboBox` | `initial_value` | `variable=` |

Other properties can bind cosmetically but won't auto-update.

In exported code:

```python
class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        # Globals (only on Main Window class):
        self.var_username = tk.StringVar(value="")
        # Locals on this class:
        self.var_count = tk.IntVar(value=0)
        ...

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, master=None):
        super().__init__(master)
        # Globals reach via self.master:
        self.label.configure(textvariable=self.master.var_username)
```

## Event handlers

Bind a method to a widget event from the Properties panel **Events** group:

- **`command`** — click / change events: Button, Switch, CheckBox, RadioButton, Slider, ComboBox, OptionMenu, SegmentedButton.
- **`bind:<sequence>`** — Tk bind events:
  - **Entry / Textbox** — `<Return>`, `<KeyRelease>`, `<FocusOut>`.
  - **Label** — 16 events split into 5 default + 11 advanced. Default (flat list): `<Button-1>` / `<Double-Button-1>` / `<Enter>` / `<Leave>` / `<MouseWheel>`. Advanced (collapsible "Advanced" sub-section in cascade + panel): `<Button-2>` / `<Button-3>` / `<ButtonRelease-1>` / `<Motion>` / `<Configure>` / `<Map>` / `<Unmap>` / `<FocusIn>` / `<FocusOut>` / `<KeyPress>` / `<KeyRelease>`. Focus / key events require `takefocus=True`. CTkLabel routes binds onto both inner canvas and inner Tk Label so the rounded-corner area is also clickable. `<Motion>` and `<Configure>` fire at 60+ Hz — keep handlers cheap.

Methods live in a per-window behavior file at `<project>/assets/scripts/<page>/<window>.py`:

```python
# assets/scripts/login/login.py
class LoginPage:
    def setup(self, window):
        # Optional — called once after _build_ui().
        pass

    def on_submit(self):
        # Hand-written body. Triggered by button "command" handler.
        pass
```

Exported code wires it:

```python
class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self._behavior = LoginPage()
        self._build_ui()
        self._behavior.setup(self)

    def _build_ui(self):
        self.button_submit = ctk.CTkButton(
            self, text="Submit",
            command=self._behavior.on_submit,
        )
```

Multi-method binding fans out via `lambda` for `command`-style or repeated `.bind(seq, fn, add="+")` for bind-style.

## Object References

Typed slots on the behavior class for clean widget access:

```python
# In assets/scripts/login/login.py
from typing import Generic, TypeVar
T = TypeVar("T")
class ref(Generic[T]): ...

class LoginPage:
    username_entry: ref[CTkEntry] = ref()
    submit_btn: ref[CTkButton] = ref()

    def on_submit(self):
        text = self.username_entry.get()
```

Exported `__init__` populates them after `_build_ui()`:

```python
self._build_ui()
self._behavior.setup(self)
self._behavior.username_entry = self.entry_username
self._behavior.submit_btn = self.button_submit
```

Two scopes (mirror Variables):

- **Local** — points at a widget. Lives on Document.
- **Global** — points at a `Window` or `Dialog`. Lives on Project. Lets one window reach another.

Names must be valid Python identifiers (used directly as `self.<name>`). Annotation name = Properties-panel ref name verbatim — export warns on mismatch.

## Save format

`.ctkproj` is JSON, schema version 2. Top-level shape:

```json
{
    "version": 2,
    "name": "ProjectName",
    "active_document": "<doc-uuid>",
    "documents": [
        {
            "id": "<doc-uuid>",
            "name": "Main Window",
            "is_toplevel": false,
            "width": 800, "height": 600,
            "window_properties": {
                "fg_color": "transparent",
                "resizable_x": true, "resizable_y": true,
                "layout_type": "place"
            },
            "widgets": [ ...WidgetNode tree... ],
            "local_variables": [ ... ],
            "local_object_references": [ ... ]
        }
    ],
    "variables": [ <global vars> ],
    "object_references": [ <global refs> ]
}
```

A `WidgetNode`:

```json
{
    "id": "<widget-uuid>",
    "name": "submit_btn",
    "widget_type": "CTkButton",
    "properties": {
        "x": 20, "y": 60, "width": 100, "height": 32,
        "text": "Submit",
        "fg_color": "#6366f1"
    },
    "children": [],
    "handlers": {"command": ["on_submit"]}
}
```

Variable bindings: a property value `"var:<uuid>"` references a `VariableEntry` by ID.

## Asset references

`asset:<kind>/<filename>` tokens in property values:

- `asset:images/avatar.png`
- `asset:fonts/Inter-Regular.ttf`
- `asset:icons/save.png`

The runtime resolves them against the project folder. The exporter copies the assets next to the output `.py`.

## Don't-do list

- **Don't reference widgets across documents** — their variables are scoped. Cross-doc widget access must go through Object References (which only work for `Window` / `Dialog` targets at the document level, not for inner widgets).
- **Don't put behavior code in the `.ctkproj`** — bodies live in `assets/scripts/<page>/<window>.py`. The `.ctkproj` only stores the binding (event → method name).
- **Don't nest layout containers** — current limitation (one layout-deep). A vbox inside an hbox doesn't work; use `place` inside the inner one.
- **Don't hand-edit auto-generated `_build_ui()`** — re-export overwrites it. Customizations go in the behavior file, in `setup(self, window)` or in handler methods.
- **Don't rename widgets to non-identifiers if you have handlers wired to them** — exported code uses widget names as Python attribute names. Invalid names get sanitized fallbacks.

## Quick "build me" prompt template

```
Build a CTkMaker project for a [Login | Dashboard | ...] page.

Requirements:
- Window size: 400x500
- Widgets: <list>
- Variables: <names + types>
- Behavior: when user [clicks submit | toggles theme | ...], do X.

Constraints:
- Use the property schemas in WIDGETS.md
- Layout: place (absolute) for top-level
- Reference style: prefer Object References for handler code
- Keep behavior bodies short — focus on wiring + state changes

Output:
1. The `.ctkproj` content (JSON, version 2)
2. The behavior file (.py at assets/scripts/<page>/<window>.py)
3. Any Lucide icon names I need to download to assets/icons/
```

## Common patterns

**Login form:**
- 2 `CTkEntry` (username + password with `show="*"`)
- 1 `CTkButton` for submit
- 2 `tk.StringVar` (local) bound to entries
- Behavior: `on_submit` reads vars, validates, navigates

**Stat dashboard tile:**
- 1 `Card` (rounded shape) as outer container
- 1 `CTkLabel` for title
- 1 `CircularProgress` or `CTkProgressBar` for value
- 1 `CTkLabel` for subtitle/footer
- Bind progress to a local `IntVar`

**Theme toggle:**
- 1 `CTkSwitch` bound to a global `BooleanVar` `var_dark_mode`
- Multiple windows read the var via `self.master.var_dark_mode`
- Behavior `on_toggle` calls `ctk.set_appearance_mode(...)` based on var value
