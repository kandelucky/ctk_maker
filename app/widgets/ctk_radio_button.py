"""CTkRadioButton widget descriptor.

A labeled radio button. Multiple radios that share a `variable`
form a group where only one can be selected at a time; in the
builder preview each radio is standalone and the grouping is
resolved during code export.

Groups shown in the Properties panel, in order:

    Geometry          — x/y, widget size
    Rectangle         — corner radius + border widths (unchecked/checked)
    Radio Button      — the inner dot's own width/height
    Button Interaction — interactable, hover, initial state
    Main Colors       — fill (when checked), hover
    Text              — label, font + style, text colors
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor


class CTkRadioButtonDescriptor(WidgetDescriptor):
    type_name = "CTkRadioButton"
    display_name = "Radio Button"

    default_properties = {
        # Geometry
        "x": 120,
        "y": 120,
        "width": 100,
        "height": 22,
        # Rectangle
        "corner_radius": 11,
        "border_width_unchecked": 3,
        "border_width_checked": 6,
        "border_color": "#949A9F",
        # Radio dot size
        "radiobutton_width": 22,
        "radiobutton_height": 22,
        # Button Interaction
        "button_enabled": True,
        "hover": True,
        "initially_checked": False,
        "group": "",
        # Main colors
        "fg_color": "#1f6aa5",
        "hover_color": "#144870",
        # Text content + style
        "text": "CTkRadioButton",
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
             min(int(p.get("radiobutton_width", 0)),
                 int(p.get("radiobutton_height", 0))) // 2,
         )},
        {"name": "border_width_unchecked", "type": "number", "label": "",
         "group": "Rectangle", "subgroup": "Border",
         "row_label": "Unchecked Width", "min": 0,
         "max": lambda p: max(
             1,
             min(int(p.get("radiobutton_width", 0)),
                 int(p.get("radiobutton_height", 0))) // 2,
         )},
        {"name": "border_width_checked", "type": "number", "label": "",
         "group": "Rectangle", "subgroup": "Border",
         "row_label": "Checked Width", "min": 0,
         "max": lambda p: max(
             1,
             min(int(p.get("radiobutton_width", 0)),
                 int(p.get("radiobutton_height", 0))) // 2,
         )},
        {"name": "border_color", "type": "color", "label": "",
         "group": "Rectangle", "subgroup": "Border",
         "row_label": "Color"},

        # --- Radio button box size --------------------------------------
        {"name": "radiobutton_width", "type": "number", "label": "W",
         "group": "Radio Button", "pair": "box_size",
         "row_label": "Box Size", "min": 10, "max": 200},
        {"name": "radiobutton_height", "type": "number", "label": "H",
         "group": "Radio Button", "pair": "box_size",
         "min": 10, "max": 200},

        # --- Button Interaction ------------------------------------------
        {"name": "button_enabled", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Interactable"},
        {"name": "hover", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Hover Effect"},
        {"name": "initially_checked", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Initially Checked"},
        {"name": "group", "type": "multiline", "label": "",
         "group": "Button Interaction", "row_label": "Group"},

        # --- Main Colors -------------------------------------------------
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Fill (Checked)"},
        {"name": "hover_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Hover",
         "disabled_when": lambda p: not p.get("hover")},

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
        "button_enabled", "initially_checked", "group",
    }
    _FONT_KEYS = {
        "font_size", "font_bold", "font_italic",
        "font_underline", "font_overstrike",
    }

    # Changing the group name requires a fresh widget because variable
    # + value are init-only kwargs.
    recreate_triggers = frozenset({"group"})

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
            log_error("CTkRadioButtonDescriptor.transform_properties font")

        return result

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        # `variable` + `value` come from the workspace via init_kwargs
        # when a group name is set — CTkRadioButton accepts them only
        # in __init__, not via `configure`.
        kwargs = cls.transform_properties(properties)
        if init_kwargs:
            kwargs.update(init_kwargs)
        widget = ctk.CTkRadioButton(master, **kwargs)
        cls.apply_state(widget, properties)
        return widget

    @classmethod
    def apply_state(cls, widget, properties: dict) -> None:
        # Group radios rely on the workspace syncing the shared
        # `tk.StringVar`; calling `.deselect()` here would clobber
        # another radio in the same group.
        in_group = bool(str(properties.get("group") or "").strip())
        try:
            if properties.get("initially_checked"):
                widget.select()
            elif not in_group:
                widget.deselect()
        except Exception:
            log_error("CTkRadioButtonDescriptor.apply_state")
