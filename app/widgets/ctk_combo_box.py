"""CTkComboBox widget descriptor.

An editable entry with a dropdown of predefined values. The user can
pick from the list or type a custom value.

Groups shown in the Properties panel, in order
(Content → Layout → Visual → Behavior):

    Values             — the dropdown items + the initially shown value
    Text               — font + style, alignment, text colors
    Geometry           — x/y, width/height
    Rectangle          — corner radius, optional border
    Main Colors        — field background, arrow button, arrow hover
    Dropdown Colors    — dropdown background, hover, text
    Dropdown Layout    — popup geometry + border
    Button Interaction — interactable + hover effect
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
        # Dropdown layout
        "dropdown_offset": 4,
        "dropdown_button_align": "center",
        "dropdown_max_visible": 8,
        "dropdown_corner_radius": 6,
        "dropdown_border_enabled": True,
        "dropdown_border_width": 1,
        "dropdown_border_color": "#3c3c3c",
        # Text content + style
        "font_family": None,
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
        # --- Values ------------------------------------------------------
        {"name": "values", "type": "segment_values", "label": "",
         "group": "Values", "row_label": "Values"},
        {"name": "initial_value", "type": "segment_initial", "label": "",
         "group": "Values", "row_label": "Initial Value"},

        # --- Text --------------------------------------------------------
        {"name": "font_family", "type": "font", "label": "",
         "group": "Text", "row_label": "Font"},

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

        # --- Dropdown Layout ---------------------------------------------
        {"name": "dropdown_offset", "type": "number", "label": "",
         "group": "Dropdown Layout", "row_label": "Offset",
         "min": 0, "max": 40},
        {"name": "dropdown_button_align", "type": "justify", "label": "",
         "group": "Dropdown Layout", "row_label": "Item Align"},
        {"name": "dropdown_max_visible", "type": "number", "label": "",
         "group": "Dropdown Layout", "row_label": "Max Visible",
         "min": 1, "max": 30},
        {"name": "dropdown_corner_radius", "type": "number", "label": "",
         "group": "Dropdown Layout", "row_label": "Corner Radius",
         "min": 0, "max": 30},
        {"name": "dropdown_border_enabled", "type": "boolean", "label": "",
         "group": "Dropdown Layout", "subgroup": "Border",
         "row_label": "Enabled"},
        {"name": "dropdown_border_width", "type": "number", "label": "",
         "group": "Dropdown Layout", "subgroup": "Border",
         "row_label": "Thickness", "min": 1, "max": 10,
         "disabled_when": lambda p: not p.get("dropdown_border_enabled")},
        {"name": "dropdown_border_color", "type": "color", "label": "",
         "group": "Dropdown Layout", "subgroup": "Border",
         "row_label": "Color",
         "disabled_when": lambda p: not p.get("dropdown_border_enabled")},

        # --- Button Interaction ------------------------------------------
        {"name": "button_enabled", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Interactable"},
        {"name": "hover", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Hover Effect"},
    ]

    _NODE_ONLY_KEYS = {
        "x", "y",
        "button_enabled", "border_enabled", "initial_value",
        # Dropdown popup is rendered by our ScrollableDropdown helper,
        # not by CTk — so these never reach CTkComboBox.configure().
        "dropdown_offset", "dropdown_button_align", "dropdown_max_visible",
        "dropdown_corner_radius", "dropdown_border_enabled",
        "dropdown_border_width", "dropdown_border_color",
        # Cleanup: dropdown_width was briefly added then removed
        # (not a valid CTkComboBox kwarg). Strip from old project files.
        "dropdown_width",
    }
    _FONT_KEYS = {
        "font_family",
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
        from app.core.fonts import resolve_effective_family
        family = resolve_effective_family(
            cls.type_name, properties.get("font_family"),
        )
        try:
            result["font"] = ctk.CTkFont(
                family=family,
                size=size, weight=weight, slant=slant,
                underline=underline, overstrike=overstrike,
            )
        except Exception:
            log_error("CTkComboBoxDescriptor.transform_properties font")

        return result

    @classmethod
    def _dropdown_kwargs(cls, properties: dict) -> dict:
        bw = int(properties.get("dropdown_border_width", 1))
        if not properties.get("dropdown_border_enabled", True):
            bw = 0
        return dict(
            fg_color=properties.get("dropdown_fg_color", "#2b2b2b"),
            text_color=properties.get("dropdown_text_color", "#dce4ee"),
            hover_color=properties.get("dropdown_hover_color", "#3a3a3a"),
            offset=int(properties.get("dropdown_offset", 4)),
            button_align=properties.get("dropdown_button_align", "center"),
            max_visible=int(properties.get("dropdown_max_visible", 8)),
            border_width=bw,
            border_color=properties.get(
                "dropdown_border_color", "#3c3c3c",
            ),
            corner_radius=int(
                properties.get("dropdown_corner_radius", 6),
            ),
        )

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        from app.widgets.scrollable_dropdown import ScrollableDropdown
        kwargs = cls.transform_properties(properties)
        if init_kwargs:
            kwargs.update(init_kwargs)
        widget = ctk.CTkComboBox(master, **kwargs)
        # Share the parent's resolved CTkFont so popup items pick up
        # the same family the cascade landed on for the field itself.
        widget._scrollable_dropdown = ScrollableDropdown(  # type: ignore[attr-defined]
            widget,
            font=getattr(widget, "_font", None),
            **cls._dropdown_kwargs(properties),
        )
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
        sd = getattr(widget, "_scrollable_dropdown", None)
        if sd is not None:
            # Re-pin the dropdown's font to whatever the parent now
            # holds — picks up cascade changes that came in through
            # configure(font=...).
            sd.configure_style(
                font=getattr(widget, "_font", None),
                **cls._dropdown_kwargs(properties),
            )

    @classmethod
    def export_state(cls, var_name: str, properties: dict) -> list[str]:
        initial = properties.get("initial_value")
        if not initial:
            return []
        return [f"{var_name}.set({str(initial)!r})"]
