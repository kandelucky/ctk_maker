"""CTkCheckBox widget descriptor.

A labeled checkbox. The checkbox square and the text are rendered
side by side; CTk composes them automatically.

Groups shown in the Properties panel, in order:

    Geometry          — x/y, widget size
    Rectangle         — corner radius, optional border
    Checkbox          — the inner square's own width/height
    Button Interaction — interactable toggle, hover effect, initial state
    Main Colors       — fill (when checked), hover, check mark
    Text              — label, font + style, text colors
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor


class CTkCheckBoxDescriptor(WidgetDescriptor):
    type_name = "CTkCheckBox"
    display_name = "Check Box"

    default_properties = {
        # Geometry
        "x": 120,
        "y": 120,
        "width": 100,
        "height": 24,
        # Rectangle
        "corner_radius": 6,
        "border_enabled": True,
        "border_width": 3,
        "border_color": "#949A9F",
        # Checkbox box size
        "checkbox_width": 24,
        "checkbox_height": 24,
        # Button Interaction
        "button_enabled": True,
        "hover": True,
        "initially_checked": False,
        # Main colors
        "fg_color": "#1f6aa5",
        "hover_color": "#144870",
        "checkmark_color": "#e5e5e5",
        # Text content + style
        "text": "CTkCheckBox",
        "font_size": 13,
        "font_bold": False,
        "font_italic": False,
        "font_underline": False,
        "font_overstrike": False,
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
         "min": 20, "max": 2000},
        {"name": "height", "type": "number", "label": "H",
         "group": "Geometry", "pair": "size", "min": 10, "max": 2000},

        # --- Rectangle ---------------------------------------------------
        {"name": "corner_radius", "type": "number", "label": "",
         "group": "Rectangle",
         "row_label": "Corner Radius", "min": 0,
         "max": lambda p: max(
             0,
             min(int(p.get("checkbox_width", 0)),
                 int(p.get("checkbox_height", 0))) // 2,
         )},
        {"name": "border_enabled", "type": "boolean", "label": "",
         "group": "Rectangle", "subgroup": "Border",
         "row_label": "Enabled"},
        {"name": "border_width", "type": "number", "label": "",
         "group": "Rectangle", "subgroup": "Border",
         "row_label": "Thickness", "min": 1,
         "max": lambda p: max(
             1,
             min(int(p.get("checkbox_width", 0)),
                 int(p.get("checkbox_height", 0))) // 2,
         ),
         "disabled_when": lambda p: not p.get("border_enabled")},
        {"name": "border_color", "type": "color", "label": "",
         "group": "Rectangle", "subgroup": "Border",
         "row_label": "Color",
         "disabled_when": lambda p: not p.get("border_enabled")},

        # --- Checkbox size ----------------------------------------------
        {"name": "checkbox_width", "type": "number", "label": "W",
         "group": "Checkbox", "pair": "box_size", "row_label": "Box Size",
         "min": 10, "max": 200},
        {"name": "checkbox_height", "type": "number", "label": "H",
         "group": "Checkbox", "pair": "box_size",
         "min": 10, "max": 200},

        # --- Button Interaction ------------------------------------------
        {"name": "button_enabled", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Interactable"},
        {"name": "hover", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Hover Effect"},
        {"name": "initially_checked", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Initially Checked"},

        # --- Main Colors -------------------------------------------------
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Fill (Checked)"},
        {"name": "hover_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Hover",
         "disabled_when": lambda p: not p.get("hover")},
        {"name": "checkmark_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Check Mark"},

        # --- Text --------------------------------------------------------
        {"name": "text", "type": "multiline", "label": "",
         "group": "Text", "row_label": "Label"},

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

        {"name": "text_color", "type": "color", "label": "",
         "group": "Text", "row_label": "Normal Text Color"},
        {"name": "text_color_disabled", "type": "color", "label": "",
         "group": "Text", "row_label": "Disabled Text Color"},
    ]

    _NODE_ONLY_KEYS = {
        "x", "y",
        "button_enabled", "border_enabled", "initially_checked",
    }
    _FONT_KEYS = {
        "font_size", "font_bold", "font_italic",
        "font_underline", "font_overstrike",
    }

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
            log_error("CTkCheckBoxDescriptor.transform_properties font")

        return result

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        kwargs = cls.transform_properties(properties)
        if init_kwargs:
            kwargs.update(init_kwargs)
        widget = ctk.CTkCheckBox(master, **kwargs)
        cls.apply_state(widget, properties)
        return widget

    @classmethod
    def apply_state(cls, widget, properties: dict) -> None:
        try:
            if properties.get("initially_checked"):
                widget.select()
            else:
                widget.deselect()
        except Exception:
            log_error("CTkCheckBoxDescriptor.apply_state")

    @classmethod
    def export_state(cls, var_name: str, properties: dict) -> list[str]:
        if properties.get("initially_checked"):
            return [f"{var_name}.select()"]
        return []
