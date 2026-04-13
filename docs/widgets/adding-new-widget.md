# Adding a New Widget

> Step-by-step: add a new CTk widget type to the builder.

## The one-file rule

Adding a new widget is a single new file in [app/widgets/](../../app/widgets/).
No changes to `core/`, `ui/`, or `io/` are required — the registry picks it up.

## Steps

### 1. Create the descriptor file

TODO: Create `app/widgets/ctk_<name>.py`. Subclass `WidgetDescriptor` from
[base.py](../../app/widgets/base.py).

### 2. Declare the type name

TODO: `type_name = "CTkFoo"` — this is the string stored in the project file
and shown in the palette.

### 3. Define default properties

TODO: The property dict used when the user drops a new instance on the canvas.

### 4. Declare the property schema

TODO: The schema the Properties panel renders. Document each supported field
kind (string, int, float, color, enum, bool, font, image).

### 5. Implement `transform_properties`

TODO: Convert schema properties → CTk constructor kwargs. This is the single
place where the builder's property model meets CTk's real API.

### 6. Register

TODO: If the registry auto-discovers files, no action needed. Otherwise add
an import line in [registry.py](../../app/widgets/registry.py).

### 7. Add palette metadata

TODO: Display name, icon, category, tooltip.

### 8. Write the doc page

TODO: Add `docs/widgets/ctk_<name>.md` following the same structure as
[ctk_button.md](ctk_button.md), and list it in
[widgets/README.md](README.md).

## Checklist

- [ ] Descriptor file created
- [ ] `type_name` unique
- [ ] Defaults produce a visible widget on drop
- [ ] Every schema field has an editor
- [ ] `transform_properties` returns valid CTk kwargs
- [ ] Palette icon and label set
- [ ] Doc page added and linked in the catalog
- [ ] Round-trip save/load tested
- [ ] Code export tested

## See also

- [CTk Button](ctk_button.md) — the reference implementation
- [Code Generation](../architecture/code-generation.md)
