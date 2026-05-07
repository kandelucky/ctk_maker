"""CTkTextbox widget descriptor.

A multi-line text editor — CTkEntry's big brother. Inherits from
`tkinter.Text` so `.insert(index, text)` / `.delete(start, end)` /
`.get(start, end)` follow the Text widget's `"line.col"` index
conventions.

Groups shown in the Properties panel, in order
(Content → Layout → Visual → Behavior):

    Content            — initial text + scrollbar toggle
    Text               — font + style, text color
    Geometry           — x/y, width/height
    Rectangle          — corner radius, optional border, inner padding
    Main Colors        — background, scrollbar, scrollbar hover
    Button Interaction — interactable toggle
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor


class CTkTextboxDescriptor(WidgetDescriptor):
    type_name = "CTkTextbox"
    display_name = "Textbox"
    prefers_fill_in_layout = True

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
        "border_spacing": 3,
        # Content
        "initial_text": "",
        "wrap": "char",
        "activate_scrollbars": True,
        # Button Interaction
        "button_enabled": True,
        # Main colors
        "fg_color": "#1d1e1e",
        "scrollbar_button_color": "#696969",
        "scrollbar_button_hover_color": "#878787",
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
        {"name": "initial_text", "type": "multiline", "label": "",
         "group": "Content", "row_label": "Initial Text"},
        {"name": "wrap", "type": "wrap", "label": "",
         "group": "Content", "row_label": "Wrap"},
        {"name": "activate_scrollbars", "type": "boolean", "label": "",
         "group": "Content", "row_label": "Show Scrollbars"},

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
         "min": 50, "max": 4000},
        {"name": "height", "type": "number", "label": "H",
         "group": "Geometry", "pair": "size", "min": 30, "max": 4000},

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
         "group": "Main Colors", "row_label": "Background"},
        {"name": "scrollbar_button_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Scrollbar"},
        {"name": "scrollbar_button_hover_color", "type": "color",
         "label": "", "group": "Main Colors",
         "row_label": "Scrollbar Hover"},

        # --- Button Interaction ------------------------------------------
        {"name": "button_enabled", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Interactable"},
    ]

    _NODE_ONLY_KEYS = {
        "x", "y",
        "button_enabled", "border_enabled", "initial_text",
    }
    _FONT_KEYS = {
        "font_family",
        "font_size", "font_bold", "font_italic",
        "font_underline", "font_overstrike",
    }
    # CTkTextbox accepts `activate_scrollbars` only in __init__ —
    # configure(activate_scrollbars=…) raises ValueError. The editor
    # reinjects it at construction; changing it at runtime triggers a
    # full destroy + recreate via `recreate_triggers`.
    init_only_keys = {"activate_scrollbars"}
    recreate_triggers = frozenset({"activate_scrollbars"})

    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        result = {
            k: v for k, v in properties.items()
            if k not in cls._NODE_ONLY_KEYS
            and k not in cls._FONT_KEYS
            and k not in cls.init_only_keys
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
            log_error("CTkTextboxDescriptor.transform_properties font")

        return result

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        kwargs = cls.transform_properties(properties)
        # Reinject init-only kwargs (e.g. activate_scrollbars) that
        # `transform_properties` filters out for runtime configure.
        for key in cls.init_only_keys:
            if key in properties:
                kwargs[key] = properties[key]
        if init_kwargs:
            kwargs.update(init_kwargs)
        widget = ctk.CTkTextbox(master, **kwargs)
        cls.apply_state(widget, properties)
        return widget

    @classmethod
    def apply_state(cls, widget, properties: dict) -> None:
        # CTkTextbox doesn't take `state` in __init__ — flip via
        # configure. Temporarily go to "normal" so delete/insert work,
        # then restore whatever the user asked for.
        enabled = bool(properties.get("button_enabled", True))
        try:
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            initial = properties.get("initial_text") or ""
            if initial:
                widget.insert("1.0", str(initial))
        except Exception:
            log_error("CTkTextboxDescriptor.apply_state insert")
        finally:
            try:
                widget.configure(state="normal" if enabled else "disabled")
            except Exception:
                pass

    @classmethod
    def export_state(cls, var_name: str, properties: dict) -> list[str]:
        lines: list[str] = []
        initial = properties.get("initial_text") or ""
        if initial:
            lines.append(f'{var_name}.insert("1.0", {str(initial)!r})')
        if not properties.get("button_enabled", True):
            lines.append(f'{var_name}.configure(state="disabled")')
        return lines
