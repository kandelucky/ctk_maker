"""CTkTabview widget descriptor.

A tabbed container with a segmented-button-style tab bar across the
top. Each tab holds an inner CTkFrame for content.

Groups shown in the Properties panel, in order:

    Geometry           — x/y, width/height
    Rectangle          — corner radius + optional border
    Tabs               — tab names (multiline, one per line)
    Button Interaction — interactable toggle
    Main Colors        — frame background + segmented button colors
    Text               — tab button text colors

Nesting children into specific tabs is NOT supported yet — the
builder renders the widget as a preview of the final tab bar + empty
tab frames. Post-export, hand-wire child widgets inside each
`tabview.tab("name")` block.
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor


class CTkTabviewDescriptor(WidgetDescriptor):
    type_name = "CTkTabview"
    display_name = "Tabview"
    prefers_fill_in_layout = True
    # Children drop into the currently-active tab; `parent_slot` on the
    # child node holds the tab name. `child_master` below resolves the
    # real tk master (`widget.tab(slot)`) so CTk places the child inside
    # the tab's inner frame rather than the tabview itself.
    is_container = True
    # Tab rename destroys the old tab frame in CTk — children with a
    # stale `parent_slot` would be orphaned. Full destroy + rebuild
    # via the workspace's recreate path, with `before_recreate`
    # migrating children's slots first.
    recreate_triggers = frozenset({"tab_names"})

    default_properties = {
        # Geometry
        "x": 120,
        "y": 120,
        "width": 300,
        "height": 250,
        # Rectangle
        "corner_radius": 6,
        "border_enabled": False,
        "border_width": 2,
        "border_color": "#565b5e",
        # Tabs
        "tab_names": "Tab 1\nTab 2\nTab 3",
        "initial_tab": "Tab 1",
        "tab_position": "top",
        "tab_anchor": "center",
        # Button Interaction
        "button_enabled": True,
        # Main colors
        "fg_color": "#2b2b2b",
        "segmented_button_fg_color": "#4a4d50",
        "segmented_button_selected_color": "#6366f1",
        "segmented_button_selected_hover_color": "#4f46e5",
        "segmented_button_unselected_color": "#4a4d50",
        "segmented_button_unselected_hover_color": "#696969",
        # Text
        "text_color": "#dce4ee",
        "text_color_disabled": "#737373",
    }

    property_schema = [
        # --- Geometry ----------------------------------------------------
        {"name": "x", "type": "number", "label": "X",
         "group": "Geometry", "pair": "pos", "row_label": "Position"},
        {"name": "y", "type": "number", "label": "Y",
         "group": "Geometry", "pair": "pos"},

        {"name": "width", "type": "number", "label": "W",
         "group": "Geometry", "pair": "size", "row_label": "Size",
         "min": 80, "max": 4000},
        {"name": "height", "type": "number", "label": "H",
         "group": "Geometry", "pair": "size", "min": 60, "max": 4000},

        # --- Rectangle ---------------------------------------------------
        {"name": "corner_radius", "type": "number", "label": "",
         "group": "Rectangle",
         "row_label": "Corner Radius", "min": 0,
         "max": lambda p: max(
             0,
             min(int(p.get("width", 0)), int(p.get("height", 0))) // 2,
         )},
        {"name": "border_enabled", "type": "boolean", "label": "",
         "group": "Rectangle", "subgroup": "Border",
         "row_label": "Enabled"},
        {"name": "border_width", "type": "number", "label": "",
         "group": "Rectangle", "subgroup": "Border",
         "row_label": "Thickness", "min": 1, "max": 20,
         "disabled_when": lambda p: not p.get("border_enabled")},
        {"name": "border_color", "type": "color", "label": "",
         "group": "Rectangle", "subgroup": "Border",
         "row_label": "Color",
         "disabled_when": lambda p: not p.get("border_enabled")},

        # --- Tabs --------------------------------------------------------
        {"name": "tab_names", "type": "segment_values", "label": "",
         "group": "Tabs", "row_label": "Tab Names"},
        {"name": "initial_tab", "type": "segment_initial", "label": "",
         "group": "Tabs", "row_label": "Initial Tab"},
        {"name": "tab_position", "type": "tab_bar_position", "label": "",
         "group": "Tabs", "row_label": "Tab Bar Position"},
        {"name": "tab_anchor", "type": "tab_bar_align", "label": "",
         "group": "Tabs", "row_label": "Tab Bar Align"},

        # --- Button Interaction ------------------------------------------
        {"name": "button_enabled", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Interactable"},

        # --- Main Colors -------------------------------------------------
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Frame Background"},
        {"name": "segmented_button_fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Tab Bar Background"},
        {"name": "segmented_button_selected_color", "type": "color",
         "label": "", "group": "Main Colors",
         "row_label": "Tab Selected"},
        {"name": "segmented_button_selected_hover_color", "type": "color",
         "label": "", "group": "Main Colors",
         "row_label": "Tab Selected Hover"},
        {"name": "segmented_button_unselected_color", "type": "color",
         "label": "", "group": "Main Colors",
         "row_label": "Tab Unselected"},
        {"name": "segmented_button_unselected_hover_color", "type": "color",
         "label": "", "group": "Main Colors",
         "row_label": "Tab Unselected Hover"},

        # --- Text --------------------------------------------------------
        {"name": "text_color", "type": "color", "label": "",
         "group": "Text", "row_label": "Normal Text Color"},
        {"name": "text_color_disabled", "type": "color", "label": "",
         "group": "Text", "row_label": "Disabled Text Color"},
    ]

    _NODE_ONLY_KEYS = {
        "x", "y", "border_enabled", "tab_names", "button_enabled",
        "initial_tab", "tab_anchor", "tab_position",
    }

    # (position, align) → CTk anchor value. `stretch` keeps the base
    # anchor (center / s) and is re-gridded with sticky="nsew" via
    # `_apply_tab_stretch` after widget creation.
    _TAB_ANCHOR_MAP = {
        ("top", "left"):     "nw",
        ("top", "center"):   "center",
        ("top", "right"):    "ne",
        ("top", "stretch"):  "center",
        ("bottom", "left"):    "sw",
        ("bottom", "center"):  "s",
        ("bottom", "right"):   "se",
        ("bottom", "stretch"): "s",
    }

    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        result = {
            k: v for k, v in properties.items()
            if k not in cls._NODE_ONLY_KEYS
        }
        result["state"] = (
            "normal" if properties.get("button_enabled", True)
            else "disabled"
        )
        if not properties.get("border_enabled"):
            result["border_width"] = 0
        position = properties.get("tab_position", "top")
        align = properties.get("tab_anchor", "center")
        result["anchor"] = cls._TAB_ANCHOR_MAP.get(
            (position, align), "center",
        )
        return result

    @classmethod
    def _apply_tab_stretch(cls, widget, stretched: bool) -> None:
        """Re-grid the internal ``_segmented_button`` with
        ``sticky="nsew"`` when stretched; otherwise hand control back
        to CTk's own ``_set_grid_segmented_button`` so the sticky
        matches the current anchor (``ns`` / ``nsw`` / ``nse`` for
        center / left / right). Without this bypass, setting ``ns``
        blindly would overwrite the alignment-specific stickies and
        leave left/right align visually identical to center.
        """
        sb = getattr(widget, "_segmented_button", None)
        if sb is None:
            return
        if stretched:
            try:
                info = sb.grid_info()
            except Exception:
                info = {}
            try:
                sb.grid(
                    row=info.get("row", 1),
                    column=info.get("column", 0),
                    rowspan=info.get("rowspan", 2),
                    columnspan=info.get("columnspan", 1),
                    padx=info.get("padx", 0),
                    sticky="nsew",
                )
            except Exception:
                pass
            return
        restore = getattr(widget, "_set_grid_segmented_button", None)
        if restore is not None:
            try:
                restore()
            except Exception:
                pass

    @classmethod
    def _parse_tab_names(cls, properties: dict) -> list[str]:
        raw = properties.get("tab_names") or ""
        return [
            line.strip() for line in str(raw).splitlines() if line.strip()
        ]

    @classmethod
    def before_recreate(cls, node, widget, prop_name: str) -> None:
        """Remap children's ``parent_slot`` before a ``tab_names``
        change destroys + rebuilds the tabview. Detects a single-tab
        rename (one name removed, one added) and migrates children
        from the old name to the new; otherwise, stale slots fall
        back to the first tab so no child ends up orphaned.
        """
        if prop_name != "tab_names":
            return
        old_names = list(getattr(widget, "_name_list", []) or [])
        new_names = cls._parse_tab_names(node.properties) or ["Tab 1"]
        removed = [n for n in old_names if n not in new_names]
        added = [n for n in new_names if n not in old_names]
        rename_map: dict[str, str] = {}
        if len(removed) == 1 and len(added) == 1:
            rename_map[removed[0]] = added[0]
        for child in node.children:
            slot = getattr(child, "parent_slot", None)
            if slot in rename_map:
                child.parent_slot = rename_map[slot]
            elif slot not in new_names:
                child.parent_slot = new_names[0]

    @classmethod
    def child_master(cls, widget, child_node):
        """Children live inside `widget.tab(parent_slot)` — the inner
        CTkFrame that CTk creates per tab. Falls back to the first tab
        if `parent_slot` is missing or no longer present (e.g. tab was
        renamed). Never returns the tabview itself: placing a child
        directly on the tabview would render it on top of the tab bar
        and escape tab-switch visibility gating.
        """
        names = list(getattr(widget, "_name_list", []) or [])
        if not names:
            return widget
        slot = getattr(child_node, "parent_slot", None)
        if slot and slot in names:
            try:
                return widget.tab(slot)
            except Exception:
                pass
        try:
            return widget.tab(names[0])
        except Exception:
            return widget

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        kwargs = cls.transform_properties(properties)
        if init_kwargs:
            kwargs.update(init_kwargs)
        widget = ctk.CTkTabview(master, **kwargs)
        cls.apply_state(widget, properties)
        return widget

    @classmethod
    def apply_state(cls, widget, properties: dict) -> None:
        """Sync the widget's tabs with the `tab_names` property.

        Diffs the desired list against `widget._name_list` so live
        edits to the Tab Names property add/remove only what changed.
        Sets the active tab to `initial_tab` when provided.
        """
        desired = cls._parse_tab_names(properties) or ["Tab 1"]
        try:
            existing = list(getattr(widget, "_name_list", []) or [])
        except Exception:
            existing = []
        for name in list(existing):
            if name not in desired:
                try:
                    widget.delete(name)
                except Exception:
                    log_error(
                        f"CTkTabviewDescriptor.apply_state delete {name!r}",
                    )
        current = list(getattr(widget, "_name_list", []) or [])
        for name in desired:
            if name not in current:
                try:
                    widget.add(name)
                except Exception:
                    log_error(
                        f"CTkTabviewDescriptor.apply_state add {name!r}",
                    )
        initial = (properties.get("initial_tab") or "").strip()
        if initial and initial in desired:
            try:
                widget.set(initial)
            except Exception:
                pass
        cls._apply_tab_stretch(
            widget, properties.get("tab_anchor") == "stretch",
        )
        # CTk bug workaround: `configure(anchor=...)` only re-grids the
        # segmented button — it skips `_set_grid_canvas` and
        # `_set_grid_current_tab`, so after a top→bottom flip the
        # canvas + active tab stay in the top-layout rows. Call them
        # explicitly here so a live anchor change actually moves the
        # tab bar to the chosen side.
        for method_name in (
            "_set_grid_canvas", "_set_grid_current_tab",
        ):
            fn = getattr(widget, method_name, None)
            if fn is not None:
                try:
                    fn()
                except Exception:
                    pass

    @classmethod
    def export_state(cls, var_name: str, properties: dict) -> list[str]:
        lines = [
            f"{var_name}.add({name!r})"
            for name in cls._parse_tab_names(properties)
        ]
        initial = (properties.get("initial_tab") or "").strip()
        if initial and initial in cls._parse_tab_names(properties):
            lines.append(f"{var_name}.set({initial!r})")
        if properties.get("tab_anchor") == "stretch":
            # Re-grid the internal segmented button with sticky="nsew"
            # so the tab buttons fill the full bar width. The segmented
            # button already weights its columns per tab, so stretching
            # the container distributes buttons evenly.
            lines.append(
                f'{var_name}._segmented_button.grid('
                f'row=1, rowspan=2, column=0, sticky="nsew")',
            )
        return lines
