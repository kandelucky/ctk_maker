# Widget Catalog

Every CTk widget type supported by the builder has a single descriptor
file in [`app/widgets/`](../../app/widgets/) plus a documentation page
here. The descriptor declares the property schema the Properties panel
renders; the doc page explains it in plain language.

## Legend

- ✅ Descriptor implemented + documented
- 🏗️ Descriptor implemented, docs pending
- ⬜ Not yet started

## Widgets

| # | Widget | Status | Docs |
|---|---|---|---|
| 1 | **CTkButton** | ✅ | [ctk_button.md](ctk_button.md) |
| 2 | CTkLabel | ⬜ | — |
| 3 | CTkFrame | ⬜ | — |
| 4 | CTkEntry | ⬜ | — |
| 5 | CTkSlider | ⬜ | — |
| 6 | CTkSwitch | ⬜ | — |
| 7 | CTkProgressBar | ⬜ | — |
| 8 | CTkComboBox | ⬜ | — |
| 9 | CTkOptionMenu | ⬜ | — |
| 10 | CTkSegmentedButton | ⬜ | — |
| 11 | CTkCheckBox | ⬜ | — |
| 12 | CTkRadioButton | ⬜ | — |
| 13 | CTkTextbox | ⬜ | — |
| 14 | CTkScrollableFrame | ⬜ | — |
| 15 | CTkTabview | ⬜ | — |

Phase 3 ([TODO.md](../../TODO.md)) tracks the 14 remaining descriptors.

## Descriptor anatomy

Every descriptor subclasses [`WidgetDescriptor`](../../app/widgets/base.py)
and declares:

| Field | Type | Purpose |
|---|---|---|
| `type_name` | `str` | CTk class name — matches the Python widget |
| `display_name` | `str` | Human-readable name shown in the Palette |
| `default_properties` | `dict` | Initial property values for new instances |
| `property_schema` | `list[dict]` | Properties panel layout (groups, subgroups, pairs, editor types) |
| `derived_triggers` | `set[str]` | Props whose change re-runs `compute_derived` (e.g. autofit recomputation) |
| `_NODE_ONLY_KEYS` | `set[str]` | Builder-only props that must NOT reach CTk constructor |
| `_FONT_KEYS` | `set[str]` | Props consumed to build a `CTkFont` |

And two class methods:

| Method | Purpose |
|---|---|
| `transform_properties(props)` | Converts schema props → CTk constructor kwargs (strips node-only keys, builds `CTkFont`, loads `CTkImage`, maps booleans to CTk state strings) |
| `create_widget(master, props)` | Instantiates the CTk widget; usually just `CTkButton(master, **cls.transform_properties(props))` |

Optional method:

| Method | Purpose |
|---|---|
| `compute_derived(props)` | Runs on any prop in `derived_triggers` to compute derived values (e.g. `font_size` via Best Fit binary search) |

## Schema cookbook

### Basic number editor

```python
{"name": "width", "type": "number", "label": "W",
 "group": "Geometry", "pair": "size", "row_label": "Size",
 "min": 20, "max": 2000}
```

- **Row layout:** `Size    W [140]    H [32]` — paired numeric row
- **Drag-scrub** on the `W`/`H` mini-labels
- `row_label` on the FIRST item of the pair becomes the row header
- `min`/`max` may be ints or `lambda props: int`

### Color swatch

```python
{"name": "fg_color", "type": "color", "label": "",
 "group": "Main Colors", "row_label": "Background"}
```

- **Row layout:** `Background    [████]` — full-width flat swatch
- Click opens the Photoshop-style color picker dialog
- Empty `label` hides the inline sub-label (the `row_label` is the only label)

### Boolean with label-left checkbox

```python
{"name": "font_autofit", "type": "boolean", "label": "Best Fit",
 "group": "Text", "subgroup": "Style", "pair": "size_row"}
```

- In mixed rows, a `label` text becomes a sub-label *before* the checkbox
- Sub-label color toggles between bright (checked) and dim (unchecked)
- Checkbox itself has no built-in text

### Dropdown (anchor / compound)

```python
{"name": "anchor", "type": "anchor", "label": "",
 "group": "Text", "subgroup": "Alignment", "row_label": "Align"}
```

- `anchor` → 9-position alignment dropdown ("Top Left" … "Bottom Right")
- `compound` → image position dropdown ("top"/"left"/"right"/"bottom")

### disabled_when

```python
{"name": "font_size", "type": "number", "label": "",
 ...
 "disabled_when": lambda p: bool(p.get("font_autofit", False))}
```

- Lambda receives the full property dict
- Returns `True` to grey out the editor
- The Properties panel auto-detects changes in disabled state and
  re-renders affected editors on the next property change

See [ctk_button.md](ctk_button.md) for a complete worked example.
