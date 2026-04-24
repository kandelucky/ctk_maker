"""CTkProgressBar widget descriptor.

A pure decoration bar that shows fractional progress between 0 and 1.
No interaction — the builder treats it as a static preview of the
final progress value.

Groups shown in the Properties panel, in order:

    Geometry     — x/y, width/height
    Rectangle    — corner radius, optional border
    Progress     — orientation + the initial fill ratio (0–1)
    Main Colors  — track background, progress fill
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor


class CTkProgressBarDescriptor(WidgetDescriptor):
    type_name = "CTkProgressBar"
    display_name = "Progress Bar"
    prefers_fill_in_layout = True

    default_properties = {
        # Geometry
        "x": 120,
        "y": 120,
        "width": 200,
        "height": 16,
        # Rectangle
        "corner_radius": 8,
        "border_enabled": False,
        "border_width": 2,
        "border_color": "#7a7a7a",
        # Progress
        "orientation": "horizontal",
        "initial_percent": 50,
        # Main colors
        "fg_color": "#4a4d50",
        "progress_color": "#6366f1",
    }

    property_schema = [
        # --- Geometry ----------------------------------------------------
        {"name": "x", "type": "number", "label": "X",
         "group": "Geometry", "pair": "pos", "row_label": "Position"},
        {"name": "y", "type": "number", "label": "Y",
         "group": "Geometry", "pair": "pos"},

        {"name": "width", "type": "number", "label": "W",
         "group": "Geometry", "pair": "size", "row_label": "Size",
         "min": 10, "max": 2000},
        {"name": "height", "type": "number", "label": "H",
         "group": "Geometry", "pair": "size", "min": 4, "max": 2000},

        # --- Rectangle ---------------------------------------------------
        {"name": "corner_radius", "type": "number", "label": "",
         "group": "Rectangle",
         "row_label": "Corner Radius", "min": 1, "max": 50},
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

        # --- Progress ----------------------------------------------------
        {"name": "orientation", "type": "orientation", "label": "",
         "group": "Progress", "row_label": "Orientation"},
        {"name": "initial_percent", "type": "number", "label": "",
         "group": "Progress", "row_label": "Progress %",
         "min": 0, "max": 100},

        # --- Main Colors -------------------------------------------------
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Track Background"},
        {"name": "progress_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Progress Fill"},
    ]

    _NODE_ONLY_KEYS = {
        "x", "y", "border_enabled", "initial_percent",
    }
    # CTkProgressBar accepts `orientation` only in __init__ — it's not
    # a valid `configure` kwarg. The workspace destroys and recreates
    # the widget whenever it changes (see recreate_triggers). The
    # exporter still emits it because exported code builds the widget
    # via __init__.
    init_only_keys = {"orientation"}
    recreate_triggers = frozenset({"orientation"})

    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        result = {
            k: v for k, v in properties.items()
            if k not in cls._NODE_ONLY_KEYS
            and k not in cls.init_only_keys
        }
        if not properties.get("border_enabled"):
            result["border_width"] = 0
        # Builder always renders a static preview — determinate mode.
        result["mode"] = "determinate"
        return result

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        # Init-only kwargs are filtered out of `transform_properties`
        # so `configure(...)` never sees them — reinject them here for
        # the constructor.
        kwargs = cls.transform_properties(properties)
        for key in cls.init_only_keys:
            if key in properties:
                kwargs[key] = properties[key]
        if init_kwargs:
            kwargs.update(init_kwargs)
        widget = ctk.CTkProgressBar(master, **kwargs)
        cls.apply_state(widget, properties)
        return widget

    @classmethod
    def apply_state(cls, widget, properties: dict) -> None:
        try:
            pct = int(properties.get("initial_percent", 50) or 0)
        except (TypeError, ValueError):
            pct = 0
        pct = max(0, min(100, pct))
        try:
            widget.set(pct / 100.0)
        except Exception:
            log_error("CTkProgressBarDescriptor.apply_state set")

    @classmethod
    def on_prop_recreate(cls, prop_name: str, properties: dict) -> dict:
        # Flipping orientation swaps the widget's dimensions so a 200×16
        # horizontal bar becomes a 16×200 vertical bar.
        if prop_name != "orientation":
            return {}
        try:
            w = int(properties.get("width", 200) or 200)
            h = int(properties.get("height", 16) or 16)
        except (TypeError, ValueError):
            return {}
        return {"width": h, "height": w}

    @classmethod
    def export_state(cls, var_name: str, properties: dict) -> list[str]:
        try:
            pct = int(properties.get("initial_percent", 50) or 0)
        except (TypeError, ValueError):
            return []
        pct = max(0, min(100, pct))
        return [f"{var_name}.set({pct / 100.0!r})"]
