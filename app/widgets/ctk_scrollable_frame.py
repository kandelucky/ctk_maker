"""CTkScrollableFrame widget descriptor.

A scrollable container frame with an optional header label. The
scroll direction is chosen at construction time (horizontal or
vertical) — changing it triggers a fresh widget.

Groups shown in the Properties panel, in order:

    Geometry     — x/y, width/height
    Rectangle    — corner radius, optional border
    Label        — header text, alignment, colors
    Scrollbar    — orientation (init-only) + track / thumb colors
    Main Colors  — frame background
"""
import customtkinter as ctk

from app.widgets.base import WidgetDescriptor
from app.widgets.layout_schema import (
    DEFAULT_LAYOUT_TYPE, LAYOUT_TYPE_ROW,
)


# builder label_text_align → CTkScrollableFrame label_anchor
_LABEL_ALIGN_TO_ANCHOR = {"left": "w", "center": "center", "right": "e"}


class CTkScrollableFrameDescriptor(WidgetDescriptor):
    type_name = "CTkScrollableFrame"
    display_name = "Scrollable Frame"
    is_container = True

    default_properties = {
        # Geometry
        "x": 120,
        "y": 120,
        "width": 200,
        "height": 200,
        # Rectangle
        "corner_radius": 6,
        "border_enabled": False,
        "border_width": 1,
        "border_color": "#565b5e",
        # Label
        "label_text": "",
        "label_text_align": "center",
        "label_fg_color": "#3a3a3a",
        "label_text_color": "#dce4ee",
        # Scrollbar
        "orientation": "vertical",
        "scrollbar_fg_color": "#1a1a1a",
        "scrollbar_button_color": "#3a3a3a",
        "scrollbar_button_hover_color": "#4a4a4a",
        # Main colors
        "fg_color": "#2b2b2b",
        # Layout — geometry manager used for THIS frame's children
        # at export time. Editor canvas always uses absolute placement.
        "layout_type": DEFAULT_LAYOUT_TYPE,
    }

    property_schema = [
        # --- Geometry ----------------------------------------------------
        {"name": "x", "type": "number", "label": "X",
         "group": "Geometry", "pair": "pos", "row_label": "Position"},
        {"name": "y", "type": "number", "label": "Y",
         "group": "Geometry", "pair": "pos"},

        {"name": "width", "type": "number", "label": "W",
         "group": "Geometry", "pair": "size", "row_label": "Size",
         "min": 50, "max": 4000},
        {"name": "height", "type": "number", "label": "H",
         "group": "Geometry", "pair": "size", "min": 50, "max": 4000},

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
         "row_label": "Thickness", "min": 1, "max": 50,
         "disabled_when": lambda p: not p.get("border_enabled")},
        {"name": "border_color", "type": "color", "label": "",
         "group": "Rectangle", "subgroup": "Border",
         "row_label": "Color",
         "disabled_when": lambda p: not p.get("border_enabled")},

        # --- Label -------------------------------------------------------
        {"name": "label_text", "type": "multiline", "label": "",
         "group": "Label", "row_label": "Label Text"},
        {"name": "label_text_align", "type": "justify", "label": "",
         "group": "Label", "row_label": "Label Align"},
        {"name": "label_fg_color", "type": "color", "label": "",
         "group": "Label", "row_label": "Label Background"},
        {"name": "label_text_color", "type": "color", "label": "",
         "group": "Label", "row_label": "Label Text Color"},

        # --- Scrollbar ---------------------------------------------------
        {"name": "orientation", "type": "orientation", "label": "",
         "group": "Scrollbar", "row_label": "Orientation"},
        {"name": "scrollbar_fg_color", "type": "color", "label": "",
         "group": "Scrollbar", "row_label": "Track"},
        {"name": "scrollbar_button_color", "type": "color", "label": "",
         "group": "Scrollbar", "row_label": "Thumb"},
        {"name": "scrollbar_button_hover_color", "type": "color", "label": "",
         "group": "Scrollbar", "row_label": "Thumb Hover"},

        # --- Main Colors -------------------------------------------------
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Frame Background"},

        # --- Layout (children manager) -----------------------------------
        LAYOUT_TYPE_ROW,
    ]

    _NODE_ONLY_KEYS = {
        "x", "y", "border_enabled", "label_text_align", "layout_type",
    }
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
        # Builder-side label_text_align → CTk label_anchor.
        result["label_anchor"] = _LABEL_ALIGN_TO_ANCHOR.get(
            properties.get("label_text_align", "center"), "center",
        )
        return result

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        # Re-inject init-only kwargs (e.g. orientation) for the
        # constructor.
        kwargs = cls.transform_properties(properties)
        for key in cls.init_only_keys:
            if key in properties:
                kwargs[key] = properties[key]
        if init_kwargs:
            kwargs.update(init_kwargs)
        return ctk.CTkScrollableFrame(master, **kwargs)

    @classmethod
    def canvas_anchor(cls, widget):
        # CTkScrollableFrame lives inside its own outer CTkFrame
        # (`_parent_frame`) — that's the widget the canvas must embed.
        return getattr(widget, "_parent_frame", widget)
