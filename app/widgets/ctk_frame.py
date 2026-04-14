"""CTkFrame widget descriptor.

A plain rounded container with optional border. No text, no font, no
state — the simplest CTk widget.

Groups shown in the Properties panel, in order:

    Geometry    — x/y, width/height
    Rectangle   — corner radius, border (thickness + color)
    Main Colors — background
"""
import customtkinter as ctk

from app.widgets.base import WidgetDescriptor


class CTkFrameDescriptor(WidgetDescriptor):
    type_name = "CTkFrame"
    display_name = "Frame"
    is_container = True

    default_properties = {
        # Geometry
        "x": 120,
        "y": 120,
        "width": 200,
        "height": 150,
        # Rectangle
        "corner_radius": 6,
        "border_width": 0,
        "border_color": "#565b5e",
        # Main colors
        "fg_color": "#2b2b2b",
    }

    property_schema = [
        # --- Geometry ----------------------------------------------------
        {"name": "x", "type": "number", "label": "X",
         "group": "Geometry", "pair": "pos", "row_label": "Position"},
        {"name": "y", "type": "number", "label": "Y",
         "group": "Geometry", "pair": "pos"},

        {"name": "width", "type": "number", "label": "W",
         "group": "Geometry", "pair": "size", "row_label": "Size",
         "min": 20, "max": 4000},
        {"name": "height", "type": "number", "label": "H",
         "group": "Geometry", "pair": "size", "min": 20, "max": 4000},

        # --- Rectangle ---------------------------------------------------
        {"name": "corner_radius", "type": "number", "label": "",
         "group": "Rectangle", "subgroup": "Corners",
         "row_label": "Roundness", "min": 0,
         "max": lambda p: max(
             0,
             min(int(p.get("width", 0)), int(p.get("height", 0))) // 2,
         )},
        {"name": "border_width", "type": "number", "label": "",
         "group": "Rectangle", "subgroup": "Border",
         "row_label": "Thickness", "min": 0,
         "max": lambda p: max(
             0,
             min(int(p.get("width", 0)), int(p.get("height", 0))) // 2,
         )},
        {"name": "border_color", "type": "color", "label": "",
         "group": "Rectangle", "subgroup": "Border",
         "row_label": "Color"},

        # --- Main Colors -------------------------------------------------
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Background"},
    ]

    _NODE_ONLY_KEYS = {"x", "y"}

    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        return {
            k: v for k, v in properties.items()
            if k not in cls._NODE_ONLY_KEYS
        }

    @classmethod
    def create_widget(cls, master, properties: dict):
        return ctk.CTkFrame(master, **cls.transform_properties(properties))
