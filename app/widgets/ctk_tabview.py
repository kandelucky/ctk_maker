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
    # Not a builder-side container yet — children can't be dropped into
    # a specific tab. Revisit when the composite-widget integration
    # story lands (see TODO.md).
    is_container = False

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
        # Button Interaction
        "button_enabled": True,
        # Main colors
        "fg_color": "#2b2b2b",
        "segmented_button_fg_color": "#4a4d50",
        "segmented_button_selected_color": "#1f6aa5",
        "segmented_button_selected_hover_color": "#144870",
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
        {"name": "tab_names", "type": "multiline", "label": "",
         "group": "Tabs", "row_label": "Tab Names"},

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
        return result

    @classmethod
    def _parse_tab_names(cls, properties: dict) -> list[str]:
        raw = properties.get("tab_names") or ""
        return [
            line.strip() for line in str(raw).splitlines() if line.strip()
        ]

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
        """
        desired = cls._parse_tab_names(properties) or ["Tab 1"]
        try:
            existing = list(getattr(widget, "_name_list", []) or [])
        except Exception:
            existing = []
        # Remove tabs that are no longer in `desired`.
        for name in list(existing):
            if name not in desired:
                try:
                    widget.delete(name)
                except Exception:
                    log_error(
                        f"CTkTabviewDescriptor.apply_state delete {name!r}",
                    )
        # Add tabs that didn't exist yet, in the user-declared order.
        current = list(getattr(widget, "_name_list", []) or [])
        for name in desired:
            if name not in current:
                try:
                    widget.add(name)
                except Exception:
                    log_error(
                        f"CTkTabviewDescriptor.apply_state add {name!r}",
                    )

    @classmethod
    def export_state(cls, var_name: str, properties: dict) -> list[str]:
        return [
            f"{var_name}.add({name!r})"
            for name in cls._parse_tab_names(properties)
        ]
