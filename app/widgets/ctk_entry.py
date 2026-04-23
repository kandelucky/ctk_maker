"""CTkEntry widget descriptor.

A single-line text input with an optional placeholder hint.

Groups shown in the Properties panel, in order:

    Geometry           — x/y, width/height
    Rectangle          — corner radius, optional border
    Content            — placeholder + initial text
    Button Interaction — interactable toggle
    Main Colors        — field background
    Text               — font + style, text + placeholder colors
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor


class CTkEntryDescriptor(WidgetDescriptor):
    type_name = "CTkEntry"
    display_name = "Entry"
    prefers_fill_in_layout = True

    default_properties = {
        # Geometry
        "x": 120,
        "y": 120,
        "width": 140,
        "height": 28,
        # Rectangle
        "corner_radius": 6,
        "border_enabled": True,
        "border_width": 2,
        "border_color": "#565b5e",
        # Content
        "placeholder_text": "Enter text…",
        "initial_value": "",
        "password": False,
        # Button Interaction
        "button_enabled": True,
        "readonly": False,
        # Main colors
        "fg_color": "#343638",
        # Text content + style
        "font_size": 13,
        "font_bold": False,
        "font_italic": False,
        "font_underline": False,
        "font_overstrike": False,
        "text_color": "#dce4ee",
        "placeholder_text_color": "#9ea0a2",
        "justify": "left",
    }

    property_schema = [
        # --- Geometry ----------------------------------------------------
        {"name": "x", "type": "number", "label": "X",
         "group": "Geometry", "pair": "pos", "row_label": "Position"},
        {"name": "y", "type": "number", "label": "Y",
         "group": "Geometry", "pair": "pos"},

        {"name": "width", "type": "number", "label": "W",
         "group": "Geometry", "pair": "size", "row_label": "Size",
         "min": 40, "max": 2000},
        {"name": "height", "type": "number", "label": "H",
         "group": "Geometry", "pair": "size", "min": 20, "max": 2000},

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
         "row_label": "Thickness", "min": 1,
         "max": lambda p: max(
             1,
             min(int(p.get("width", 0)), int(p.get("height", 0))) // 2,
         ),
         "disabled_when": lambda p: not p.get("border_enabled")},
        {"name": "border_color", "type": "color", "label": "",
         "group": "Rectangle", "subgroup": "Border",
         "row_label": "Color",
         "disabled_when": lambda p: not p.get("border_enabled")},

        # --- Content -----------------------------------------------------
        {"name": "placeholder_text", "type": "multiline", "label": "",
         "group": "Content", "row_label": "Placeholder"},
        {"name": "initial_value", "type": "multiline", "label": "",
         "group": "Content", "row_label": "Initial Text"},
        {"name": "password", "type": "boolean", "label": "",
         "group": "Content", "row_label": "Password"},

        # --- Button Interaction ------------------------------------------
        {"name": "button_enabled", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Interactable",
         "disabled_when": lambda p: bool(p.get("readonly"))},
        {"name": "readonly", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Read-only"},

        # --- Main Colors -------------------------------------------------
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Field Background"},

        # --- Text --------------------------------------------------------
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

        {"name": "justify", "type": "justify", "label": "",
         "group": "Text", "row_label": "Text Align"},

        {"name": "text_color", "type": "color", "label": "",
         "group": "Text", "row_label": "Normal Text Color"},
        {"name": "placeholder_text_color", "type": "color", "label": "",
         "group": "Text", "row_label": "Placeholder Color"},
    ]

    _NODE_ONLY_KEYS = {
        "x", "y",
        "button_enabled", "readonly",
        "border_enabled", "initial_value",
        "password",  # maps to CTk's `show` below
    }
    _FONT_KEYS = {
        "font_size", "font_bold", "font_italic",
        "font_underline", "font_overstrike",
    }

    # Greyed-out palette for state="disabled". CTk's own disabled
    # state only blocks input; the field keeps its full colour
    # scheme, so an Entry with existing text looks identical to an
    # enabled one. These overrides make the disabled state readable
    # at a glance. Readonly stays styled like a normal field
    # (expected behaviour — the user should still be able to read
    # and select the text copy-wise).
    _DISABLED_FG = "#2a2a2a"
    _DISABLED_TEXT = "#606060"
    _DISABLED_BORDER = "#444444"

    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        result = {
            k: v for k, v in properties.items()
            if k not in cls._NODE_ONLY_KEYS and k not in cls._FONT_KEYS
        }

        # State priority: readonly wins over disabled, both override
        # the default normal.
        if properties.get("readonly"):
            result["state"] = "readonly"
        elif not properties.get("button_enabled", True):
            result["state"] = "disabled"
        else:
            result["state"] = "normal"

        # Password masking: builder-side `password` boolean → CTk
        # `show="•"` (standard bullet across platforms). ALWAYS emit
        # the key so toggling password off actually clears CTk's
        # previously-set `show` — configure() doesn't unset what isn't
        # passed.
        result["show"] = "•" if properties.get("password") else ""

        if not properties.get("border_enabled"):
            result["border_width"] = 0

        # Dim the Entry when state=disabled so the user can tell at
        # a glance that it's not editable. Keep readonly looking
        # normal — it's supposed to read like a regular field that
        # just happens to be locked from typing.
        if result.get("state") == "disabled":
            result["fg_color"] = cls._DISABLED_FG
            result["text_color"] = cls._DISABLED_TEXT
            if properties.get("border_enabled"):
                result["border_color"] = cls._DISABLED_BORDER

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
            log_error("CTkEntryDescriptor.transform_properties font")

        return result

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        kwargs = cls.transform_properties(properties)
        if init_kwargs:
            kwargs.update(init_kwargs)
        widget = ctk.CTkEntry(master, **kwargs)
        cls.apply_state(widget, properties)
        return widget

    @classmethod
    def apply_state(cls, widget, properties: dict) -> None:
        # CTk's placeholder is literally the entry's text styled with
        # placeholder_text_color, gated by the internal
        # `_placeholder_text_active` flag. Touching the widget without
        # respecting that flag either wipes the placeholder (and never
        # re-arms) or leaves stale user text when the field is cleared.
        #
        # Disabled caveat: tkinter's Entry silently drops `insert()`
        # when state=disabled, so CTk cannot actually show its
        # placeholder on a disabled entry at runtime. We mirror that
        # here — no placeholder on canvas when the field is disabled,
        # so WYSIWYG matches preview. Read-only entries accept
        # programmatic insert, so placeholder is fine there.
        initial = properties.get("initial_value") or ""
        placeholder_active = bool(
            getattr(widget, "_placeholder_text_active", False),
        )
        current_state = str(widget.cget("state"))
        needs_flip = current_state in ("disabled", "readonly")
        is_disabled = current_state == "disabled"
        if not initial and placeholder_active and not is_disabled:
            return
        try:
            if needs_flip:
                widget.configure(state="normal")
            if placeholder_active:
                try:
                    widget._deactivate_placeholder()
                except Exception:
                    pass
            widget.delete(0, "end")
            if initial:
                widget.insert(0, str(initial))
            elif not is_disabled:
                try:
                    widget._activate_placeholder()
                except Exception:
                    pass
        except Exception:
            log_error("CTkEntryDescriptor.apply_state insert")
        finally:
            if needs_flip:
                try:
                    widget.configure(state=current_state)
                except Exception:
                    pass

    @classmethod
    def export_kwarg_overrides(cls, properties: dict) -> dict:
        # Mirror the runtime disabled palette so the exported app
        # renders the same dimmed look the builder canvas shows.
        readonly = bool(properties.get("readonly"))
        disabled = (
            not readonly
            and not properties.get("button_enabled", True)
        )
        if not disabled:
            return {}
        overrides = {
            "fg_color": cls._DISABLED_FG,
            "text_color": cls._DISABLED_TEXT,
        }
        if properties.get("border_enabled"):
            overrides["border_color"] = cls._DISABLED_BORDER
        return overrides

    @classmethod
    def export_state(cls, var_name: str, properties: dict) -> list[str]:
        initial = properties.get("initial_value") or ""
        if not initial:
            return []
        # tkinter.Entry silently drops insert() when state is disabled
        # or readonly, so we flip to normal, insert, then restore.
        if properties.get("readonly"):
            target_state = "readonly"
        elif not properties.get("button_enabled", True):
            target_state = "disabled"
        else:
            target_state = "normal"
        if target_state == "normal":
            return [f"{var_name}.insert(0, {str(initial)!r})"]
        return [
            f'{var_name}.configure(state="normal")',
            f"{var_name}.insert(0, {str(initial)!r})",
            f'{var_name}.configure(state="{target_state}")',
        ]
