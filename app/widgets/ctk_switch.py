"""CTkSwitch widget descriptor.

A toggle switch — like CTkCheckBox visually but rendered as an
iOS-style slider.

Groups shown in the Properties panel, in order:

    Geometry           — x/y, widget size
    Rectangle          — corner radius, button length
    Switch             — the inner toggle's own width/height
    Button Interaction — interactable, hover, initially on
    Main Colors        — track (off / on), knob, knob hover
    Text               — label, font + style, text colors
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor


class CTkSwitchDescriptor(WidgetDescriptor):
    type_name = "CTkSwitch"
    display_name = "Switch"

    default_properties = {
        # Geometry — small default so the widget auto-grows around
        # its content; otherwise the bg stays at the configured size
        # and looks misaligned when ``text_position`` moves the label.
        "x": 120,
        "y": 120,
        "width": 20,
        "height": 10,
        # Rectangle — default to half the switch_height for a
        # fully-rounded pill at the default 36×18. CTk's own default
        # is 1000 (force-pill at any size) but that confuses the
        # Inspector ("why is it 1000?"); 9 is the visually equivalent
        # honest value at the stock dimensions.
        "corner_radius": 9,
        "button_length": 0,
        # Switch box
        "switch_width": 36,
        "switch_height": 18,
        # Button Interaction
        "button_enabled": True,
        "hover": True,
        "initially_checked": False,
        # Main colors
        "fg_color": "#4a4d50",
        "progress_color": "#6366f1",
        "button_color": "#d5d9de",
        "button_hover_color": "#ffffff",
        # Text content + style
        "text": "CTkSwitch",
        "font_size": 13,
        "font_bold": False,
        "font_italic": False,
        "font_underline": False,
        "font_overstrike": False,
        "text_color": "#dce4ee",
        "text_color_disabled": "#737373",
        "text_position": "right",
        "text_spacing": 6,
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

        # --- Rectangle ---------------------------------------------------
        {"name": "corner_radius", "type": "number", "label": "",
         "group": "Rectangle",
         "row_label": "Corner Radius", "min": 0,
         "max": lambda p: max(
             0,
             min(int(p.get("switch_width", 0)),
                 int(p.get("switch_height", 0))) // 2,
         )},
        {"name": "button_length", "type": "number", "label": "",
         "group": "Rectangle",
         "row_label": "Button Length", "min": 0,
         "max": lambda p: max(0, int(p.get("switch_width", 36)))},

        # --- Switch box size ---------------------------------------------
        {"name": "switch_width", "type": "number", "label": "W",
         "group": "Switch", "pair": "switch_size",
         "row_label": "Switch Size", "min": 10, "max": 200},
        {"name": "switch_height", "type": "number", "label": "H",
         "group": "Switch", "pair": "switch_size",
         "min": 8, "max": 200},

        # --- Button Interaction ------------------------------------------
        {"name": "button_enabled", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Interactable"},
        {"name": "hover", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Hover Effect"},
        {"name": "initially_checked", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Initially On"},

        # --- Main Colors -------------------------------------------------
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Track (Off)"},
        {"name": "progress_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Track (On)"},
        {"name": "button_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Knob"},
        {"name": "button_hover_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Knob Hover",
         "disabled_when": lambda p: not p.get("hover")},

        # --- Text --------------------------------------------------------
        {"name": "text", "type": "multiline", "label": "",
         "group": "Text", "row_label": "Label"},

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
        {"name": "text_position", "type": "text_position", "label": "",
         "group": "Text", "row_label": "Text Position"},
        {"name": "text_spacing", "type": "number", "label": "",
         "group": "Text", "row_label": "Text Spacing",
         "min": 0, "max": 100},
    ]

    _NODE_ONLY_KEYS = {
        "x", "y",
        "button_enabled", "initially_checked",
        # builder-only — re-grids CTk's internal layout with a gap.
        "text_position", "text_spacing",
    }
    _FONT_KEYS = {
        "font_size", "font_bold", "font_italic",
        "font_underline", "font_overstrike",
    }

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
            log_error("CTkSwitchDescriptor.transform_properties font")

        return result

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        kwargs = cls.transform_properties(properties)
        if init_kwargs:
            kwargs.update(init_kwargs)
        widget = ctk.CTkSwitch(master, **kwargs)
        cls.apply_state(widget, properties)
        return widget

    @classmethod
    def apply_state(cls, widget, properties: dict) -> None:
        try:
            if properties.get("initially_checked"):
                widget.select()
            else:
                widget.deselect()
        except Exception:
            log_error("CTkSwitchDescriptor.apply_state")
        try:
            spacing = int(properties.get("text_spacing", 6) or 0)
        except (TypeError, ValueError):
            spacing = 6
        position = properties.get("text_position", "right") or "right"
        # Gate the re-grid: only run when position/spacing actually
        # change. Re-running grid_forget+grid on every property edit
        # disturbs CTk's internal cursor state on the inner canvas
        # and label, which the workspace selection chrome relies on.
        last_pos = getattr(widget, "_last_text_position", None)
        last_spacing = getattr(widget, "_last_text_spacing", None)
        if position == last_pos and spacing == last_spacing:
            return
        cls._reposition_text(widget, position, spacing)
        widget._last_text_position = position
        widget._last_text_spacing = spacing

    @classmethod
    def _reposition_text(
        cls, widget, position: str, spacing: int = 6,
    ) -> None:
        """Re-grid CTk's internal canvas + label so the label sits
        on the chosen side of the switch track. Same shape and reach
        as the CheckBox / RadioButton versions (CTk's CTkSwitch ships
        with the same internal grid layout).
        """
        canvas = getattr(widget, "_canvas", None)
        label = getattr(widget, "_text_label", None)
        bg = getattr(widget, "_bg_canvas", None)
        if canvas is None or label is None:
            return
        spacing = max(0, int(spacing))
        try:
            outer_cursor = str(widget.cget("cursor")) or ""
        except Exception:
            outer_cursor = ""
        try:
            canvas.grid_forget()
            label.grid_forget()
            if bg is not None:
                bg.grid_forget()
            if position == "left":
                if bg is not None:
                    bg.grid(row=0, column=0, columnspan=3, sticky="nswe")
                label.grid(row=0, column=0, sticky="e", padx=(0, spacing))
                canvas.grid(row=0, column=2, sticky="w")
                label["anchor"] = "e"
            elif position == "top":
                if bg is not None:
                    bg.grid(row=0, column=0, rowspan=3, columnspan=3,
                            sticky="nswe")
                label.grid(row=0, column=0, sticky="s", pady=(0, spacing))
                canvas.grid(row=2, column=0, sticky="n")
                label["anchor"] = "center"
            elif position == "bottom":
                if bg is not None:
                    bg.grid(row=0, column=0, rowspan=3, columnspan=3,
                            sticky="nswe")
                canvas.grid(row=0, column=0, sticky="s")
                label.grid(row=2, column=0, sticky="n", pady=(spacing, 0))
                label["anchor"] = "center"
            else:  # "right" — CTk default
                if bg is not None:
                    bg.grid(row=0, column=0, columnspan=3, sticky="nswe")
                canvas.grid(row=0, column=0, sticky="")
                label.grid(row=0, column=2, sticky="w", padx=(spacing, 0))
                label["anchor"] = "w"
        except Exception:
            log_error("CTkSwitchDescriptor._reposition_text")
            return
        propagate = outer_cursor or "hand2"
        for w in (canvas, label, bg):
            if w is None:
                continue
            try:
                w.configure(cursor=propagate)
            except Exception:
                pass

    @classmethod
    def export_state(cls, var_name: str, properties: dict) -> list[str]:
        lines: list[str] = []
        if properties.get("initially_checked"):
            lines.append(f"{var_name}.select()")
        position = properties.get("text_position", "right") or "right"
        try:
            spacing = int(properties.get("text_spacing", 6) or 6)
        except (TypeError, ValueError):
            spacing = 6
        if position != "right" or spacing != 6:
            lines.append(
                f'_align_text_label({var_name}, "{position}", {spacing})'
            )
        return lines
