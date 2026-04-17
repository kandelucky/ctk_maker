"""Window (virtual) descriptor — drives the Properties panel schema
for the top-level CTk window. Not a real widget: there's no
``create_widget``, no rendering. Everything routes through
``Project.update_property(WINDOW_ID, …)`` which feeds the
``window_properties`` dict and the document geometry.
"""
from __future__ import annotations

from app.core.project import WINDOW_ID, DEFAULT_WINDOW_PROPERTIES
from app.widgets.base import WidgetDescriptor


class WindowDescriptor(WidgetDescriptor):
    type_name = WINDOW_ID
    ctk_class_name = "CTk"
    display_name = "Window"
    is_container = False

    # Window is a pure absolute-positioning surface — Qt Designer
    # applies layouts to inner containers (QWidget / QGroupBox),
    # never to the top-level window, and we follow the same rule.
    # Users get alignment tools on the canvas (Phase 7) instead.
    default_properties = {
        **DEFAULT_WINDOW_PROPERTIES,
        "width": 800,
        "height": 600,
    }

    property_schema = [
        {"name": "width", "type": "number", "label": "W",
         "group": "Geometry", "pair": "size", "row_label": "Size",
         "min": 100, "max": 4000},
        {"name": "height", "type": "number", "label": "H",
         "group": "Geometry", "pair": "size",
         "min": 100, "max": 4000},

        {"name": "resizable_x", "type": "boolean", "label": "",
         "group": "Behaviour", "row_label": "Resizable X"},
        {"name": "resizable_y", "type": "boolean", "label": "",
         "group": "Behaviour", "row_label": "Resizable Y"},
        {"name": "frameless", "type": "boolean", "label": "",
         "group": "Behaviour", "row_label": "Frameless"},

        {"name": "grid_style", "type": "grid_style", "label": "",
         "group": "Builder Grid", "row_label": "Style"},
        {"name": "grid_color", "type": "color", "label": "",
         "group": "Builder Grid", "row_label": "Colour",
         "disabled_when": lambda p: p.get("grid_style") == "none"},
        {"name": "grid_spacing", "type": "number", "label": "",
         "group": "Builder Grid", "row_label": "Spacing",
         "min": 4, "max": 200,
         "disabled_when": lambda p: p.get("grid_style") == "none"},

        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Background"},
    ]

    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        # Window is virtual — no CTk widget to configure.
        return {}

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        raise NotImplementedError(
            "WindowDescriptor is virtual — Project holds the state, "
            "no widget is ever created."
        )
