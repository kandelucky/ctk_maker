"""CTkSegmentedButton widget descriptor.

A row of mutually-exclusive buttons, like a Mac-style segmented
control or a tab bar. The "selected" segment is highlighted.

Groups shown in the Properties panel, in order:

    Geometry           — x/y, width/height
    Rectangle          — corner radius + optional border
    Values             — segments (one per line) + initial selection
    Button Interaction — interactable toggle
    Main Colors        — outer bg + selected / unselected / hover tints
    Text               — font + style, text colors
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor


class CTkSegmentedButtonDescriptor(WidgetDescriptor):
    type_name = "CTkSegmentedButton"
    display_name = "Segmented Button"
    prefers_fill_in_layout = True

    default_properties = {
        # Geometry
        "x": 120,
        "y": 120,
        "width": 240,
        "height": 32,
        # Rectangle
        "corner_radius": 6,
        "border_enabled": False,
        "border_width": 2,
        # Values
        "values": "First\nSecond\nThird",
        "initial_value": "First",
        # Button Interaction
        "button_enabled": True,
        # Main colors
        "fg_color": "#4a4d50",
        "selected_color": "#6366f1",
        "selected_hover_color": "#4f46e5",
        "unselected_color": "#4a4d50",
        "unselected_hover_color": "#696969",
        # Text content + style
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
         "min": 60, "max": 2000},
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
         "row_label": "Thickness", "min": 1, "max": 20,
         "disabled_when": lambda p: not p.get("border_enabled")},

        # --- Values ------------------------------------------------------
        # Custom editor: the value cell + ✎ button both open a +/-
        # table dialog instead of the generic multiline text editor.
        {"name": "values", "type": "segment_values", "label": "",
         "group": "Values", "row_label": "Values"},
        # Dynamic dropdown — options come from the current ``values``
        # list, not a hardcoded enum. Stored as the segment text
        # (same shape the old multiline editor produced).
        {"name": "initial_value", "type": "segment_initial", "label": "",
         "group": "Values", "row_label": "Initial Value"},

        # --- Button Interaction ------------------------------------------
        {"name": "button_enabled", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Interactable"},

        # --- Main Colors -------------------------------------------------
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Outer Background"},
        {"name": "selected_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Selected"},
        {"name": "selected_hover_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Selected Hover"},
        {"name": "unselected_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Unselected"},
        {"name": "unselected_hover_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Unselected Hover"},

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

        {"name": "text_color", "type": "color", "label": "",
         "group": "Text", "row_label": "Normal Text Color"},
        {"name": "text_color_disabled", "type": "color", "label": "",
         "group": "Text", "row_label": "Disabled Text Color"},
    ]

    _NODE_ONLY_KEYS = {
        "x", "y",
        "button_enabled", "border_enabled", "initial_value",
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

        # Builder width controls total width — turn off CTk's grow-to-fit.
        result["dynamic_resizing"] = False

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
            log_error(
                "CTkSegmentedButtonDescriptor.transform_properties font",
            )

        return result

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        kwargs = cls.transform_properties(properties)
        if init_kwargs:
            kwargs.update(init_kwargs)
        widget = ctk.CTkSegmentedButton(master, **kwargs)
        cls.apply_state(widget, properties)
        return widget

    @classmethod
    def apply_state(cls, widget, properties: dict) -> None:
        initial = properties.get("initial_value")
        if not initial:
            return
        # Only preselect if the value is in the current list of
        # segments — otherwise CTk silently leaves it as "".
        try:
            values = list(widget.cget("values") or [])
            if str(initial) in values:
                widget.set(str(initial))
        except Exception:
            log_error("CTkSegmentedButtonDescriptor.apply_state set")

    @classmethod
    def export_state(cls, var_name: str, properties: dict) -> list[str]:
        initial = properties.get("initial_value")
        if not initial:
            return []
        return [f"{var_name}.set({str(initial)!r})"]
