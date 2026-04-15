# Adding a New Widget

> Step-by-step: add a new CTk widget type to the builder.

## The one-file-plus-two rule

Adding a new widget is a single new file in [app/widgets/](../../app/widgets/) plus two tiny edits:

1. One import + one registry entry in [registry.py](../../app/widgets/registry.py)
2. One palette entry in [palette.py](../../app/ui/palette.py) `CATALOG` (only if you want it to show as an "implemented" row instead of a dimmed placeholder)

## Steps

### 1. Create `app/widgets/ctk_<name>.py`

Subclass `WidgetDescriptor` from [base.py](../../app/widgets/base.py). Name the class `CTk<Name>Descriptor`.

### 2. Declare the type name

```python
type_name = "CTkFoo"       # matches the CTk class name, stored in .ctkproj
display_name = "Foo"       # shown in the palette, Object Tree, code export comments
is_container = False       # True for CTkFrame-like containers that accept drops
```

### 3. Fill `default_properties`

The dict used whenever the user drops a new instance on the canvas. Every property you mention in the schema must have a default here — otherwise the Properties panel will crash on first display.

### 4. Write `property_schema`

A flat list of dicts. Each dict is one editor row. Common fields:

| Key | Type | Notes |
|---|---|---|
| `name` | str | Property key (must exist in `default_properties`) |
| `type` | str | Editor kind: `number`, `color`, `boolean`, `multiline`, `orientation`, `justify`, `anchor`, `compound` |
| `label` | str | Inline sub-label (leave `""` to hide) |
| `group` | str | Section header in the panel |
| `subgroup` | str | Optional second-level header inside a group |
| `row_label` | str | The full-width label for the row; set on the first pair item |
| `pair` | str | Mark two fields with the same pair id to stack them side by side |
| `min` / `max` | int or `lambda p: int` | Clamp for number editors; lambdas can read other props |
| `disabled_when` | `lambda p: bool` | Returns True to grey the editor out |

See [ctk_button.py](../../app/widgets/ctk_button.py) for a fully worked property schema.

### 5. Filter keys that should not reach CTk

```python
_NODE_ONLY_KEYS = {"x", "y", "border_enabled", "initial_value"}
```

`x` / `y` go to `place()`, not the constructor. `border_enabled` is our master toggle — when off we zero out `border_width` in `transform_properties`. `initial_value` is pushed via `apply_state` after construction (CTk Entry / ComboBox / OptionMenu) or swapped into `initially_checked` (CheckBox / RadioButton).

```python
_FONT_KEYS = {
    "font_size", "font_bold", "font_italic",
    "font_underline", "font_overstrike",
}
```

Builder-side text styling. `transform_properties` collapses them into a `CTkFont(...)` object.

```python
init_only_keys = {"orientation"}
```

Properties CTk accepts in `__init__` but rejects from `configure(...)` (e.g. `CTkProgressBar.orientation`, `CTkScrollableFrame.orientation`). The editor filters them out of configure kwargs and reinjects them when creating the widget; the exporter still emits them because exported code always builds via `__init__`.

```python
multiline_list_keys = {"values"}
```

Properties stored as newline-separated strings in the editor (multiline text box) but handed to CTk as Python lists at runtime (e.g. `CTkComboBox.values`, `CTkOptionMenu.values`, `CTkSegmentedButton.values`). The exporter splits on `\n` when emitting the Python source.

### 6. Implement `transform_properties`

```python
@classmethod
def transform_properties(cls, properties: dict) -> dict:
    result = {
        k: v for k, v in properties.items()
        if k not in cls._NODE_ONLY_KEYS
        and k not in cls._FONT_KEYS
        and k not in cls.init_only_keys
    }
    # Border off → zero the width
    if not properties.get("border_enabled"):
        result["border_width"] = 0
    # Button enabled → CTk state string
    result["state"] = (
        "normal" if properties.get("button_enabled", True) else "disabled"
    )
    # Build the font
    result["font"] = ctk.CTkFont(...)
    return result
```

This is the one place where the builder's property model meets CTk's real API.

### 7. Implement `create_widget`

```python
@classmethod
def create_widget(cls, master, properties: dict, init_kwargs=None):
    kwargs = cls.transform_properties(properties)
    for key in cls.init_only_keys:
        if key in properties:
            kwargs[key] = properties[key]
    if init_kwargs:
        kwargs.update(init_kwargs)
    widget = ctk.CTkFoo(master, **kwargs)
    cls.apply_state(widget, properties)
    return widget
```

The `init_kwargs` parameter lets the workspace inject values the descriptor can't know about at creation time — e.g. a shared `tk.StringVar` for a radio button group. See [ctk_radio_button.py](../../app/widgets/ctk_radio_button.py).

### 8. Optional: `apply_state`

Runtime state that doesn't go through `configure(...)`:

```python
@classmethod
def apply_state(cls, widget, properties: dict) -> None:
    if properties.get("initially_checked"):
        widget.select()
    else:
        widget.deselect()
```

Called after `create_widget` **and** after every property change, so it's idempotent.

### 9. Optional: `recreate_triggers` + `on_prop_recreate`

If a property is init-only (see step 5) and the user changes it in the Properties panel, the workspace destroys and rebuilds the widget. `on_prop_recreate` lets the descriptor commit derived overrides before the rebuild — e.g. CTkProgressBar swaps `width`↔`height` when orientation flips:

```python
recreate_triggers = frozenset({"orientation"})

@classmethod
def on_prop_recreate(cls, prop_name: str, properties: dict) -> dict:
    if prop_name != "orientation":
        return {}
    return {
        "width": properties["height"],
        "height": properties["width"],
    }
```

### 10. Register

Add one import and one dict entry to [app/widgets/registry.py](../../app/widgets/registry.py):

```python
from app.widgets.ctk_foo import CTkFooDescriptor

_REGISTRY = {
    ...
    CTkFooDescriptor.type_name: CTkFooDescriptor,
}
```

### 11. Add palette entry

In [app/ui/palette.py](../../app/ui/palette.py), find the matching `WidgetGroup` and add a `WidgetEntry`:

```python
WidgetGroup("Inputs", (
    ...
    WidgetEntry("CTkFoo", "Foo", "sliders-horizontal"),  # icon from lucide.dev
)),
```

The third argument is a Lucide icon name — the corresponding PNG must exist in `app/assets/icons/`.

### 12. Document

Add `docs/widgets/ctk_<name>.md` following the structure of [ctk_button.md](ctk_button.md) — one table per property group, minimal prose. Flip the row in [widgets/README.md](README.md) from ⬜ to ✅.

## Checklist

- [ ] Descriptor file created
- [ ] `type_name` matches the CTk class name
- [ ] Defaults produce a visible widget on drop
- [ ] Every schema row's `name` exists in `default_properties`
- [ ] `transform_properties` returns valid CTk kwargs (test: `ctk.CTkFoo(**result)` runs clean)
- [ ] `_NODE_ONLY_KEYS` / `init_only_keys` / `multiline_list_keys` set correctly
- [ ] Registry import + dict entry added
- [ ] Palette `WidgetEntry` added with a Lucide icon that exists locally
- [ ] Doc page added and linked in the catalog
- [ ] Round-trip save/load tested
- [ ] Code export tested — the exported `.py` runs and renders identically

## See also

- [CTk Button](ctk_button.md) — the reference implementation
- [Code Generation](../architecture/code-generation.md)
