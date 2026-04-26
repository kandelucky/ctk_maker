"""Shape widget descriptor.

A pure-visual decoration element for backgrounds — rectangle / rounded
rectangle / circle (or pill, when width != height). Exports as a
``CTkFrame`` so the generated code stays on CTk's public API, but the
builder treats it as a leaf: no children can be dropped inside, no
layout manager rows on its property panel.

``shape_type`` drives ``corner_radius`` derivation:
    - ``rectangle`` → 0 (locked)
    - ``rounded``   → user-picked, slider 0..min(W,H)/2
    - ``circle``    → min(W,H)/2 (locked, auto-pill on non-square)

Default fill is a slate-indigo accent so a fresh drop is visually
distinct from CTkFrame's neutral ``#2b2b2b`` panel — the user can
spot at a glance whether a block is a real container or a Shape.
"""
import customtkinter as ctk

from app.widgets.base import WidgetDescriptor

SHAPE_RECTANGLE = "rectangle"
SHAPE_ROUNDED = "rounded"
SHAPE_CIRCLE = "circle"

DEFAULT_FG_COLOR = "#a2a2a2"


class ShapeDescriptor(WidgetDescriptor):
    type_name = "Shape"
    ctk_class_name = "CTkFrame"
    display_name = "Shape"
    is_container = False
    prefers_fill_in_layout = True

    default_properties = {
        # Geometry
        "x": 120,
        "y": 120,
        "width": 200,
        "height": 200,
        # Shape
        "shape_type": SHAPE_ROUNDED,
        "corner_radius": 12,
        # Border
        "border_enabled": False,
        "border_width": 1,
        "border_color": "#565b5e",
        # Main colors
        "fg_color": DEFAULT_FG_COLOR,
    }

    property_schema = [
        # --- Geometry ----------------------------------------------------
        {"name": "x", "type": "number", "label": "X",
         "group": "Geometry", "pair": "pos", "row_label": "Position"},
        {"name": "y", "type": "number", "label": "Y",
         "group": "Geometry", "pair": "pos"},

        {"name": "width", "type": "number", "label": "W",
         "group": "Geometry", "pair": "size", "row_label": "Size",
         "min": 8, "max": 4000},
        {"name": "height", "type": "number", "label": "H",
         "group": "Geometry", "pair": "size", "min": 8, "max": 4000},

        # --- Shape -------------------------------------------------------
        {"name": "shape_type", "type": "enum", "label": "",
         "group": "Shape", "row_label": "Type",
         "options": [
             {"value": SHAPE_RECTANGLE, "label": "Rectangle",
              "icon": "square"},
             {"value": SHAPE_ROUNDED, "label": "Rounded",
              "icon": "square-round-corner"},
             {"value": SHAPE_CIRCLE, "label": "Circle / Pill",
              "icon": "circle"},
         ]},
        # corner_radius is editable only for "rounded" — rectangle locks
        # it to 0, circle locks it to min(W,H)/2.
        {"name": "corner_radius", "type": "number", "label": "",
         "group": "Shape",
         "row_label": "Corner Radius", "min": 0,
         "max": lambda p: max(
             0,
             min(int(p.get("width", 0)), int(p.get("height", 0))) // 2,
         ),
         "disabled_when": lambda p: p.get("shape_type") != SHAPE_ROUNDED},

        # --- Border ------------------------------------------------------
        {"name": "border_enabled", "type": "boolean", "label": "",
         "group": "Border", "row_label": "Enabled"},
        {"name": "border_width", "type": "number", "label": "",
         "group": "Border", "row_label": "Thickness", "min": 1,
         "max": lambda p: max(
             1,
             min(int(p.get("width", 0)), int(p.get("height", 0))) // 2,
         ),
         "disabled_when": lambda p: not p.get("border_enabled")},
        {"name": "border_color", "type": "color", "label": "",
         "group": "Border", "row_label": "Color",
         "disabled_when": lambda p: not p.get("border_enabled")},

        # --- Main Colors -------------------------------------------------
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Fill",
         "clearable": True, "clear_value": "transparent"},
    ]

    _NODE_ONLY_KEYS = {
        "x", "y", "shape_type", "border_enabled",
    }

    derived_triggers = {"shape_type", "width", "height"}

    @classmethod
    def compute_derived(cls, properties: dict) -> dict:
        # Lock corner_radius to the shape mode so user-picked values on
        # Rounded don't leak into Rectangle / Circle when the type
        # toggles. Computed once per change — the dispatcher applies
        # the diff back onto the node, then re-renders.
        shape = properties.get("shape_type", SHAPE_ROUNDED)
        try:
            w = int(properties.get("width", 0))
            h = int(properties.get("height", 0))
        except (TypeError, ValueError):
            return {}
        out: dict = {}
        if shape == SHAPE_RECTANGLE:
            if int(properties.get("corner_radius", 0) or 0) != 0:
                out["corner_radius"] = 0
        elif shape == SHAPE_CIRCLE:
            target = max(0, min(w, h) // 2)
            if int(properties.get("corner_radius", -1) or -1) != target:
                out["corner_radius"] = target
        return out

    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        result = {
            k: v for k, v in properties.items()
            if k not in cls._NODE_ONLY_KEYS
        }
        # Border off → zero out the width so CTk doesn't paint a hairline.
        if not properties.get("border_enabled"):
            result["border_width"] = 0
        return result

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        kwargs = cls.transform_properties(properties)
        if init_kwargs:
            kwargs.update(init_kwargs)
        return ctk.CTkFrame(master, **kwargs)
