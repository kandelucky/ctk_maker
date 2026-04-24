"""CTkSlider widget descriptor.

A draggable value picker over a numeric range. Supports continuous
and stepped modes plus horizontal / vertical orientation. Matches
CTkProgressBar's approach — ``orientation`` is init-only, so flipping
it in the Inspector destroys + recreates the widget via
``recreate_triggers`` + ``on_prop_recreate`` (the latter swaps
width ↔ height so a 200×16 horizontal slider becomes a 16×200
vertical one).

Groups shown in the Properties panel, in order:

    Geometry           — x/y, width/height
    Rectangle          — track corner radius, button corner radius,
                         button length (pill-shaped when > 0),
                         optional border
    Value Range        — min, max, number of steps, initial value
    Orientation        — horizontal / vertical
    Button Interaction — interactable + hover effect
    Main Colors        — track, progress, button, button hover
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor


class CTkSliderDescriptor(WidgetDescriptor):
    type_name = "CTkSlider"
    display_name = "Slider"
    prefers_fill_in_layout = True

    default_properties = {
        # Geometry
        "x": 120,
        "y": 120,
        "width": 200,
        "height": 16,
        # Rectangle
        "corner_radius": 8,
        "button_corner_radius": 8,
        "button_length": 1,
        "border_enabled": False,
        "border_width": 6,
        "border_color": "#565b5e",
        # Value range
        "from_": 0,
        "to": 100,
        "number_of_steps": 0,
        "initial_value": 50,
        # Orientation
        "orientation": "horizontal",
        # Button Interaction
        "button_enabled": True,
        "hover": True,
        # Main colors
        "fg_color": "#4a4d50",
        "progress_color": "#aab0b5",
        "button_color": "#6366f1",
        "button_hover_color": "#4f46e5",
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
         "group": "Geometry", "pair": "size", "min": 8, "max": 2000},

        # --- Rectangle ---------------------------------------------------
        {"name": "corner_radius", "type": "number", "label": "",
         "group": "Rectangle",
         "row_label": "Track Radius", "min": 1, "max": 50},
        {"name": "button_corner_radius", "type": "number", "label": "",
         "group": "Rectangle",
         "row_label": "Button Radius", "min": 1, "max": 50},
        {"name": "button_length", "type": "number", "label": "",
         "group": "Rectangle",
         "row_label": "Button Length", "min": 1,
         "max": lambda p: max(1, int(p.get("width", 200)) // 2)},
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

        # --- Value Range -------------------------------------------------
        {"name": "from_", "type": "number", "label": "",
         "group": "Value Range", "row_label": "Min"},
        {"name": "to", "type": "number", "label": "",
         "group": "Value Range", "row_label": "Max"},
        {"name": "number_of_steps", "type": "number", "label": "",
         "group": "Value Range", "row_label": "Steps",
         "min": 0, "max": 1000},
        {"name": "initial_value", "type": "number", "label": "",
         "group": "Value Range", "row_label": "Initial Value"},

        # --- Orientation -------------------------------------------------
        {"name": "orientation", "type": "orientation", "label": "",
         "group": "Orientation", "row_label": "Orientation"},

        # --- Button Interaction ------------------------------------------
        {"name": "button_enabled", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Interactable"},
        {"name": "hover", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Hover Effect"},

        # --- Main Colors -------------------------------------------------
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Track"},
        {"name": "progress_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Progress"},
        {"name": "button_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Button"},
        {"name": "button_hover_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Button Hover",
         "disabled_when": lambda p: not p.get("hover")},
    ]

    _NODE_ONLY_KEYS = {
        "x", "y", "border_enabled", "initial_value", "button_enabled",
    }
    init_only_keys = {"orientation"}
    recreate_triggers = frozenset({"orientation"})

    # Greyed-out colour overrides applied when the slider is set to
    # disabled. CTk's own ``state="disabled"`` only blocks input; the
    # widget keeps its full-colour look, which makes "interactable"
    # off invisible at a glance. These match CTkButton's disabled
    # text shade so the dim feel is consistent across widgets.
    _DISABLED_TRACK = "#3a3a3a"
    _DISABLED_PROGRESS = "#5a5a5a"
    _DISABLED_BUTTON = "#6a6a6a"

    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        result = {
            k: v for k, v in properties.items()
            if k not in cls._NODE_ONLY_KEYS
            and k not in cls.init_only_keys
        }
        enabled = bool(properties.get("button_enabled", True))
        result["state"] = "normal" if enabled else "disabled"
        if not enabled:
            # Override the colour kwargs so CTk paints the slider in
            # a clearly disabled palette. button_hover_color stays in
            # sync with button_color so accidental hover doesn't
            # flash a fresher shade on the dimmed knob.
            result["fg_color"] = cls._DISABLED_TRACK
            result["progress_color"] = cls._DISABLED_PROGRESS
            result["button_color"] = cls._DISABLED_BUTTON
            result["button_hover_color"] = cls._DISABLED_BUTTON
        if not properties.get("border_enabled"):
            result["border_width"] = 0
        # Steps = 0 means "continuous" — pass None so CTk treats it
        # as unlimited steps.
        if int(properties.get("number_of_steps") or 0) <= 0:
            result["number_of_steps"] = None
        return result

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        # Init-only kwargs are filtered out of transform_properties so
        # configure() never sees them — reinject them here.
        kwargs = cls.transform_properties(properties)
        for key in cls.init_only_keys:
            if key in properties:
                kwargs[key] = properties[key]
        if init_kwargs:
            kwargs.update(init_kwargs)
        widget = ctk.CTkSlider(master, **kwargs)
        cls.apply_state(widget, properties)
        return widget

    @classmethod
    def on_prop_recreate(cls, prop_name: str, properties: dict) -> dict:
        # Flipping orientation swaps the widget's dimensions so a 200×16
        # horizontal slider becomes a 16×200 vertical slider.
        if prop_name != "orientation":
            return {}
        try:
            w = int(properties.get("width", 200) or 200)
            h = int(properties.get("height", 16) or 16)
        except (TypeError, ValueError):
            return {}
        return {"width": h, "height": w}

    @classmethod
    def apply_state(cls, widget, properties: dict) -> None:
        value = properties.get("initial_value")
        if value is None:
            return
        try:
            widget.set(float(value))
        except (TypeError, ValueError):
            log_error("CTkSliderDescriptor.apply_state set")

    @classmethod
    def export_kwarg_overrides(cls, properties: dict) -> dict:
        overrides: dict = {}
        # CTkSlider crashes with ZeroDivisionError when the user drags
        # it if `number_of_steps=0` is passed; the runtime replaces 0
        # with None in `transform_properties`, the exporter now does
        # the same so the generated code doesn't inherit the bug.
        try:
            steps = int(properties.get("number_of_steps") or 0)
        except (TypeError, ValueError):
            steps = 0
        if steps <= 0:
            overrides["number_of_steps"] = None
        # Mirror the runtime grey-out so the exported app shows the
        # same disabled palette the builder canvas does.
        if not properties.get("button_enabled", True):
            overrides["fg_color"] = cls._DISABLED_TRACK
            overrides["progress_color"] = cls._DISABLED_PROGRESS
            overrides["button_color"] = cls._DISABLED_BUTTON
            overrides["button_hover_color"] = cls._DISABLED_BUTTON
        return overrides

    @classmethod
    def export_state(cls, var_name: str, properties: dict) -> list[str]:
        value = properties.get("initial_value")
        if value is None:
            return []
        try:
            return [f"{var_name}.set({float(value)!r})"]
        except (TypeError, ValueError):
            return []
