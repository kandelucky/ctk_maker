"""CTkRichLabel widget descriptor.

A read-only label that renders Unity-style rich-text tags
(<b>, <i>, <u>, <color=...>, <size=N>, <bg=...>, <noparse>...).

The runtime widget lives in the ctkmaker-core fork at
``customtkinter/windows/widgets/ctk_rich_label.py`` so exports just
do ``ctk.CTkRichLabel(...)`` with no helper-folder bloat. See
``docs/plans/rich_text.md`` for the tag spec.

Groups shown in the Properties panel:

    Content      — rich text + parse toggle + wrap mode
    Text         — font family/size/style + base text color
    Geometry     — x/y + width/height
    Rectangle    — corner radius + optional border + inner padding
    Main Colors  — background
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor


class CTkRichLabelDescriptor(WidgetDescriptor):
    type_name = "CTkRichLabel"
    display_name = "Rich Label"
    is_ctk_class = True
    ctk_class_name = "CTkRichLabel"
    prefers_fill_in_layout = True

    default_properties = {
        # Geometry
        "x": 120,
        "y": 120,
        "width": 240,
        "height": 40,
        # Rectangle
        "corner_radius": 4,
        "border_enabled": False,
        "border_width": 1,
        "border_color": "#565b5e",
        "border_spacing": 3,
        # Content
        "text": "<b>Rich</b> <color=#50fa7b>Text</color>",
        "rich_text": True,
        "wrap": "word",
        # Main colors
        "fg_color": "transparent",
        # Text content + style
        "font_family": None,
        "font_size": 13,
        "font_bold": False,
        "font_italic": False,
        "font_underline": False,
        "font_overstrike": False,
        "text_color": "#dce4ee",
    }

    property_schema = [
        # --- Content -----------------------------------------------------
        {"name": "text", "type": "multiline", "label": "",
         "group": "Content", "row_label": "Rich Text"},
        {"name": "rich_text", "type": "boolean", "label": "",
         "group": "Content", "row_label": "Parse Tags"},
        {"name": "wrap", "type": "wrap", "label": "",
         "group": "Content", "row_label": "Wrap"},

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

        {"name": "text_color", "type": "color", "label": "",
         "group": "Text", "row_label": "Normal Text Color"},

        # --- Geometry ----------------------------------------------------
        {"name": "x", "type": "number", "label": "X",
         "group": "Geometry", "pair": "pos", "row_label": "Position"},
        {"name": "y", "type": "number", "label": "Y",
         "group": "Geometry", "pair": "pos"},
        {"name": "width", "type": "number", "label": "W",
         "group": "Geometry", "pair": "size", "row_label": "Size",
         "min": 30, "max": 4000},
        {"name": "height", "type": "number", "label": "H",
         "group": "Geometry", "pair": "size", "min": 20, "max": 4000},

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
        {"name": "border_color", "type": "color", "label": "",
         "group": "Rectangle", "subgroup": "Border",
         "row_label": "Color",
         "disabled_when": lambda p: not p.get("border_enabled")},
        {"name": "border_spacing", "type": "number", "label": "",
         "group": "Rectangle",
         "row_label": "Inner Padding", "min": 0, "max": 50},

        # --- Main Colors -------------------------------------------------
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Background",
         "clearable": True, "clear_value": "transparent"},
    ]

    _NODE_ONLY_KEYS = {"x", "y", "border_enabled", "text", "rich_text"}
    _FONT_KEYS = {
        "font_family",
        "font_size", "font_bold", "font_italic",
        "font_underline", "font_overstrike",
    }

    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        result = {
            k: v for k, v in properties.items()
            if k not in cls._NODE_ONLY_KEYS
            and k not in cls._FONT_KEYS
        }

        if not properties.get("border_enabled"):
            result["border_width"] = 0

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
            log_error("CTkRichLabelDescriptor.transform_properties font")

        return result

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        kwargs = cls.transform_properties(properties)
        kwargs["rich_text"] = bool(properties.get("rich_text", True))
        kwargs["text"] = str(properties.get("text") or "")
        if init_kwargs:
            kwargs.update(init_kwargs)
        return ctk.CTkRichLabel(master, **kwargs)

    @classmethod
    def apply_state(cls, widget, properties: dict) -> None:
        try:
            widget.set_rich_text_enabled(bool(properties.get("rich_text", True)))
            widget.set_text(str(properties.get("text") or ""))
        except Exception:
            log_error("CTkRichLabelDescriptor.apply_state set_text")

    @classmethod
    def export_state(cls, var_name: str, properties: dict) -> list[str]:
        # text + rich_text live in ``_NODE_ONLY_KEYS`` (CTkTextbox.configure
        # doesn't accept them), so the kwarg-emission loop strips them.
        # Re-emit as post-construction calls so the exported file actually
        # renders the user's rich text.
        lines: list[str] = []
        if not properties.get("rich_text", True):
            lines.append(f"{var_name}.set_rich_text_enabled(False)")
        text = str(properties.get("text") or "")
        if text:
            lines.append(f"{var_name}.set_text({text!r})")
        return lines
