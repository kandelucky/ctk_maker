# CTkTabview

A tabbed container with a segmented-button-style tab bar across the
top. Each tab owns an inner CTkFrame for its content.

Wraps [`customtkinter.CTkTabview`](https://customtkinter.tomschimansky.com/documentation/widgets/tabview).
**Descriptor:** [`../../app/widgets/ctk_tabview.py`](../../app/widgets/ctk_tabview.py)

> **Status: partial.** The descriptor, schema, and registry entry are
> in place. The widget renders, the tab bar updates live when you
> edit the `Tab Names` list, and the exporter emits a `.add("name")`
> call per tab. **Dropping widgets into a specific tab is not yet
> supported** — `is_container = False` for now. To populate the tabs
> you hand-edit the exported file and use `tabview.tab("name")` as
> the master of each child widget. Tracked under Phase 6.8 in
> [TODO.md](../../TODO.md) together with CTkScrollableFrame.

## Geometry

| Row | Property | Default | Range |
|---|---|---|---|
| Position X / Y | `x` / `y` | 120 / 120 | — |
| Size W / H | `width` / `height` | 300 / 250 | 80–4000 / 60–4000 |

## Rectangle

| Row | Property | Default | Notes |
|---|---|---|---|
| Corner Radius | `corner_radius` | 6 | Max = `min(w, h) // 2` |
| Border › Enabled | `border_enabled` | False | Master toggle |
| Border › Thickness | `border_width` | 2 | Disabled when Enabled is off |
| Border › Color | `border_color` | `#565b5e` | Disabled when Enabled is off |

## Tabs

| Row | Property | Default | Notes |
|---|---|---|---|
| Tab Names | `tab_names` | `Tab 1\nTab 2\nTab 3` | One tab per line. Live diff: `apply_state` adds new names and deletes removed ones while you type. Exporter emits `{var}.add("{name}")` per non-empty line. |

## Button Interaction

| Row | Property | Default | Notes |
|---|---|---|---|
| Interactable | `button_enabled` | True | Off → CTk `state="disabled"` on the segmented button bar |

## Main Colors

| Row | Property | Default |
|---|---|---|
| Frame Background | `fg_color` | `#2b2b2b` |
| Tab Bar Background | `segmented_button_fg_color` | `#4a4d50` |
| Tab Selected | `segmented_button_selected_color` | `#1f6aa5` |
| Tab Selected Hover | `segmented_button_selected_hover_color` | `#144870` |
| Tab Unselected | `segmented_button_unselected_color` | `#4a4d50` |
| Tab Unselected Hover | `segmented_button_unselected_hover_color` | `#696969` |

## Text

| Row | Property | Default |
|---|---|---|
| Normal Text Color | `text_color` | `#dce4ee` |
| Disabled Text Color | `text_color_disabled` | `#737373` |

## Tips

- Renaming a tab today goes through a **delete + add** diff, so any
  hand-added content (once nesting lands) would be orphaned. Rename
  tabs rarely, or design the tab names upfront.
- The tab anchor / label font are not yet exposed — they default to
  CTk's theme values.
