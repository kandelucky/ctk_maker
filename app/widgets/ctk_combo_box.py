"""CTkComboBox widget descriptor.

An editable entry with a dropdown of predefined values. The user can
pick from the list or type a custom value.

Groups shown in the Properties panel, in order:

    Geometry           — x/y, width/height
    Rectangle          — corner radius, optional border
    Values             — the dropdown items + the initially shown value
    Button Interaction — interactable + hover effect
    Main Colors        — field background, arrow button, arrow hover
    Dropdown Colors    — dropdown background, hover, text
    Text               — font + style, alignment, text colors
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor


class CTkComboBoxDescriptor(WidgetDescriptor):
    type_name = "CTkComboBox"
    display_name = "Combo Box"

    default_properties = {
        # Geometry
        "x": 120,
        "y": 120,
        "width": 140,
        "height": 28,
        # Rectangle
        "corner_radius": 6,
        "border_enabled": True,
        "border_width": 2,
        "border_color": "#565b5e",
        # Values
        "values": "Option 1\nOption 2\nOption 3",
        "initial_value": "Option 1",
        # Button Interaction
        "button_enabled": True,
        "hover": True,
        # Main colors
        "fg_color": "#343638",
        "button_color": "#565b5e",
        "button_hover_color": "#7a848d",
        # Dropdown colors
        "dropdown_fg_color": "#2b2b2b",
        "dropdown_hover_color": "#3a3a3a",
        "dropdown_text_color": "#dce4ee",
        # Text content + style
        "font_size": 13,
        "font_bold": False,
        "font_italic": False,
        "font_underline": False,
        "font_overstrike": False,
        "justify": "left",
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
         "min": 40, "max": 2000},
        {"name": "height", "type": "number", "label": "H",
         "group": "Geometry", "pair": "size", "min": 20, "max": 2000},

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
         "row_label": "Thickness", "min": 1,
         "max": lambda p: max(
             1,
             min(int(p.get("width", 0)), int(p.get("height", 0))) // 2,
         ),
         "disabled_when": lambda p: not p.get("border_enabled")},
        {"name": "border_color", "type": "color", "label": "",
         "group": "Rectangle", "subgroup": "Border",
         "row_label": "Color",
         "disabled_when": lambda p: not p.get("border_enabled")},

        # --- Values ------------------------------------------------------
        {"name": "values", "type": "segment_values", "label": "",
         "group": "Values", "row_label": "Values"},
        {"name": "initial_value", "type": "segment_initial", "label": "",
         "group": "Values", "row_label": "Initial Value"},

        # --- Button Interaction ------------------------------------------
        {"name": "button_enabled", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Interactable"},
        {"name": "hover", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Hover Effect"},

        # --- Main Colors -------------------------------------------------
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Field Background"},
        {"name": "button_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Arrow Button"},
        {"name": "button_hover_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Arrow Hover",
         "disabled_when": lambda p: not p.get("hover")},

        # --- Dropdown Colors ---------------------------------------------
        {"name": "dropdown_fg_color", "type": "color", "label": "",
         "group": "Dropdown Colors", "row_label": "Background"},
        {"name": "dropdown_hover_color", "type": "color", "label": "",
         "group": "Dropdown Colors", "row_label": "Hover"},
        {"name": "dropdown_text_color", "type": "color", "label": "",
         "group": "Dropdown Colors", "row_label": "Text"},

        # --- Text --------------------------------------------------------
        {"name": "font_size", "type": "number", "label": "",
         "group": "Text", "row_label": "Size", "min": 6, "max": 96},

        {"name": "font_bold", "type": "boolean", "label": "",
         "group": "Text", "subgroup": "Style", "row_label": "Bold"},
        {"name": "font_italic", "type": "boolean", "label": "",
         "group": "Text", "subgroup": "Style", "row_label": "Italic"},
        {"name": "font_underline", "type": "boolean", "label": "",
         "group": "Text", "subgroup": "Style", "row_label": "Underline"},
        {"name": "font_overstrike", "type": "boolean", "label": "",
         "group": "Text", "subgroup": "Style", "row_label": "Strike"},

        {"name": "justify", "type": "justify", "label": "",
         "group": "Text", "row_label": "Text Align"},

        {"name": "text_color", "type": "color", "label": "",
         "group": "Text", "row_label": "Normal Text Color"},
        {"name": "text_color_disabled", "type": "color", "label": "",
         "group": "Text", "row_label": "Disabled Text Color"},
    ]

    _NODE_ONLY_KEYS = {
        "x", "y",
        "button_enabled", "border_enabled", "initial_value",
        # Cleanup: dropdown_width was briefly added then removed
        # (not a valid CTkComboBox kwarg). Strip from old project files.
        "dropdown_width",
    }
    _FONT_KEYS = {
        "font_size", "font_bold", "font_italic",
        "font_underline", "font_overstrike",
    }
    multiline_list_keys = {"values"}

    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        result = {
            k: v for k, v in properties.items()
            if k not in cls._NODE_ONLY_KEYS and k not in cls._FONT_KEYS
        }

        result["state"] = (
            "normal" if properties.get("button_enabled", True)
            else "disabled"
        )

        if not properties.get("border_enabled"):
            result["border_width"] = 0

        # Split multiline "values" string into a list of non-empty lines.
        raw_values = properties.get("values") or ""
        result["values"] = [
            line for line in str(raw_values).splitlines() if line.strip()
        ] or [""]


        try:
            size = int(properties.get("font_size") or 13)
        except (ValueError, TypeError):
            size = 13
        weight = "bold" if properties.get("font_bold") else "normal"
        slant = "italic" if properties.get("font_italic") else "roman"
        underline = bool(properties.get("font_underline"))
        overstrike = bool(properties.get("font_overstrike"))
        try:
            result["font"] = ctk.CTkFont(
                size=size, weight=weight, slant=slant,
                underline=underline, overstrike=overstrike,
            )
        except Exception:
            log_error("CTkComboBoxDescriptor.transform_properties font")

        return result

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        kwargs = cls.transform_properties(properties)
        if init_kwargs:
            kwargs.update(init_kwargs)
        widget = ctk.CTkComboBox(master, **kwargs)
        cls.apply_state(widget, properties)
        return widget

    @classmethod
    def apply_state(cls, widget, properties: dict) -> None:
        initial = properties.get("initial_value")
        if initial:
            try:
                widget.set(str(initial))
            except Exception:
                log_error("CTkComboBoxDescriptor.apply_state set")

    @classmethod
    def export_state(cls, var_name: str, properties: dict) -> list[str]:
        initial = properties.get("initial_value")
        if not initial:
            return []
        return [f"{var_name}.set({str(initial)!r})"]
