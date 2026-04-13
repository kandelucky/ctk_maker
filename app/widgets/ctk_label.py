"""CTkLabel widget descriptor.

Declares the full schema the Properties panel uses to render editors
for a CTkLabel, plus the bridge that converts the builder's property
dict into the kwargs CTkLabel actually accepts.

Groups shown in the Properties panel, in order:

    Geometry        — x/y, width/height
    Text            — label, font style, alignment, wraplength, text colors
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor


class CTkLabelDescriptor(WidgetDescriptor):
    type_name = "CTkLabel"
    display_name = "Label"

    default_properties = {
        # Geometry
        "x": 120,
        "y": 120,
        "width": 100,
        "height": 28,
        # Text content + style
        "text": "CTkLabel",
        "font_size": 13,
        "font_bold": False,
        "font_italic": False,
        "font_underline": False,
        "font_overstrike": False,
        "font_autofit": False,
        "anchor": "center",
        "justify": "center",
        "wraplength": 0,
        "text_color": "#ffffff",
        "text_color_disabled": "#a0a0a0",
        # Implicit (not editable in schema). Both transparent so CTk
        # delegates rendering to its master-color detection. True widget
        # nesting arrives in Phase 6 — until then the label is always a
        # direct canvas child, so it will read the canvas background.
        "fg_color": "transparent",
        "bg_color": "transparent",
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

        # --- Text --------------------------------------------------------
        {"name": "text", "type": "multiline", "label": "Label",
         "group": "Text"},

        {"name": "font_size", "type": "number", "label": "",
         "group": "Text", "subgroup": "Style", "pair": "size_row",
         "row_label": "Size", "min": 6, "max": 96,
         "disabled_when": lambda p: bool(p.get("font_autofit", False))},
        {"name": "font_autofit", "type": "boolean", "label": "Best Fit",
         "group": "Text", "subgroup": "Style", "pair": "size_row"},

        {"name": "font_bold", "type": "boolean", "label": "Bold",
         "group": "Text", "subgroup": "Style", "pair": "style_row",
         "row_label": "Style"},
        {"name": "font_italic", "type": "boolean", "label": "Italic",
         "group": "Text", "subgroup": "Style", "pair": "style_row"},

        {"name": "font_underline", "type": "boolean", "label": "Underline",
         "group": "Text", "subgroup": "Style", "pair": "deco_row",
         "row_label": "Decoration"},
        {"name": "font_overstrike", "type": "boolean", "label": "Strike",
         "group": "Text", "subgroup": "Style", "pair": "deco_row"},

        {"name": "anchor", "type": "anchor", "label": "",
         "group": "Text", "subgroup": "Alignment", "row_label": "Anchor"},
        {"name": "justify", "type": "justify", "label": "",
         "group": "Text", "subgroup": "Alignment", "row_label": "Justify"},
        {"name": "wraplength", "type": "number", "label": "",
         "group": "Text", "subgroup": "Alignment",
         "row_label": "Wrap Length", "min": 0, "max": 2000},

        {"name": "text_color", "type": "color", "label": "",
         "group": "Text", "subgroup": "Color", "row_label": "Normal"},
        {"name": "text_color_disabled", "type": "color", "label": "",
         "group": "Text", "subgroup": "Color", "row_label": "Disabled"},
    ]

    derived_triggers = {"text", "width", "height", "font_bold", "font_autofit"}

    _NODE_ONLY_KEYS = {"x", "y"}
    _FONT_KEYS = {
        "font_size", "font_bold", "font_italic",
        "font_underline", "font_overstrike", "font_autofit",
    }

    # ==================================================================
    # Autofit (Best Fit) — derives font_size from width/height/text
    # ==================================================================
    @classmethod
    def compute_derived(cls, properties: dict) -> dict:
        result: dict = {}
        if not properties.get("font_autofit"):
            return result
        text = properties.get("text") or ""
        if not text:
            return result
        try:
            width = int(properties.get("width", 100))
            height = int(properties.get("height", 28))
        except (ValueError, TypeError):
            return result
        bold = bool(properties.get("font_bold", False))
        new_size = cls._compute_autofit_size(text, width, height, bold)
        if new_size > 0:
            result["font_size"] = new_size
        return result

    @classmethod
    def _compute_autofit_size(cls, text: str, width: int, height: int,
                              bold: bool) -> int:
        import tkinter.font as tkfont
        avail_w = max(10, width - 12)
        avail_h = max(10, height - 4)
        weight = "bold" if bold else "normal"
        lo, hi = 6, 96
        best = 6
        while lo <= hi:
            mid = (lo + hi) // 2
            try:
                f = tkfont.Font(size=mid, weight=weight)
                tw = f.measure(text)
                th = f.metrics("linespace")
            except Exception:
                return 13
            if tw <= avail_w and th <= avail_h:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    # ==================================================================
    # Builder → CTkLabel kwargs
    # ==================================================================
    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        result = {
            k: v for k, v in properties.items()
            if k not in cls._NODE_ONLY_KEYS and k not in cls._FONT_KEYS
        }

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
            log_error("CTkLabelDescriptor.transform_properties font")

        return result

    @classmethod
    def create_widget(cls, master, properties: dict):
        return ctk.CTkLabel(master, **cls.transform_properties(properties))
