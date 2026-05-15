"""CTkButton widget descriptor — Unity ColorBlock model.

Replaces the per-state colour fields (``fg_color``, ``fg_color_disabled``,
``hover_color``, ``text_color_hover``, ``text_color_disabled``,
``image_color_disabled``, ``border_color_disabled``) with a single base
colour plus three Unity-style tints. The full per-state palette is derived
at render time via ``ctk.derive_state_colors`` (ctkmaker-core >= 5.4.20)
and handed to CTkButton's per-state kwargs (``fg_color``, ``hover_color``,
``pressed_color``, ``fg_color_disabled``).

Groups shown in the Properties panel, in order — visual identity first
(``Color States`` → ``Button Interaction`` → content → layout). The
visual-first ordering optimises for a styling-heavy workflow: state
colours are what the user touches most often, so they sit at the top.
``Color States`` is button-specific — non-interactive widgets like Label
keep the conventional ``Content → Layout → Visual → Behavior`` order.

    Color States        — normal + 3 tints + disabled fade
    Button Interaction  — interactable, hover effect
    Text                — label, font style, alignment, text colour
    Icon                — image picker, size, tint, compound, preserve aspect
    Geometry            — x/y, width/height
    Rectangle           — corner radius, border (thickness + colour)
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor


# Unity Inspector defaults for the tint multipliers.
_DEFAULT_NORMAL = "#6366f1"
_DEFAULT_HOVER_TINT = "#f5f5f5"
_DEFAULT_PRESSED_TINT = "#c8c8c8"
_DEFAULT_DISABLED_TINT = "#c8c8c8"
# Surface colour to blend toward when ``disabled_fade`` is on. CTkMaker
# always renders on the dark workspace; if we ever support per-document
# light mode we'll need to plumb the parent's bg in here.
_SURFACE = "#252525"


class CTkButtonDescriptor(WidgetDescriptor):
    type_name = "CTkButton"
    display_name = "Button"
    prefers_fill_in_layout = True

    default_properties = {
        # Geometry
        "x": 120,
        "y": 120,
        "width": 140,
        "height": 32,
        # Rectangle
        "corner_radius": 6,
        "border_enabled": False,
        "border_width": 1,
        "border_color": "#efefef",
        "border_spacing": 2,
        # Button Interaction
        "button_enabled": True,
        "hover": True,
        # Color (Unity ColorBlock — one base + three tints)
        "normal_color": _DEFAULT_NORMAL,
        "hover_tint": _DEFAULT_HOVER_TINT,
        "pressed_tint": _DEFAULT_PRESSED_TINT,
        "disabled_tint": _DEFAULT_DISABLED_TINT,
        "disabled_fade": True,
        # Text content + style
        "text": "CTkButton",
        "font_family": None,
        "font_size": 13,
        "font_autofit": False,
        "font_bold": False,
        "font_italic": False,
        "font_underline": False,
        "font_overstrike": False,
        "anchor": "center",
        "text_color": "#ffffff",
        # Image
        "image": None,
        "image_color": None,
        "image_width": 20,
        "image_height": 20,
        "compound": "left",
        "preserve_aspect": False,
    }

    property_schema = [
        # --- Color (Unity ColorBlock) -----------------------------------
        # ``Normal`` is the actual button colour; the three tints multiply
        # onto it to produce hover / pressed / disabled. ``Disabled Fade``
        # additionally blends the disabled state (bg + text + icon + border)
        # toward the workspace surface so the dim effect is visible without
        # users having to hand-pick a separate disabled palette.
        {"name": "normal_color", "type": "color", "label": "",
         "group": "Color States", "row_label": "Normal"},
        {"name": "hover_tint", "type": "color", "label": "",
         "group": "Color States", "row_label": "Hover Tint"},
        {"name": "pressed_tint", "type": "color", "label": "",
         "group": "Color States", "row_label": "Pressed Tint"},
        {"name": "disabled_tint", "type": "color", "label": "",
         "group": "Color States", "row_label": "Disabled Tint"},
        {"name": "disabled_fade", "type": "boolean", "label": "",
         "group": "Color States", "row_label": "Disabled Fade"},

        # --- Button Interaction ------------------------------------------
        {"name": "button_enabled", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Interactable"},
        {"name": "hover", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Hover Effect"},

        # --- Text --------------------------------------------------------
        {"name": "text", "type": "multiline", "label": "",
         "group": "Text", "row_label": "Label"},

        {"name": "font_family", "type": "font", "label": "",
         "group": "Text", "row_label": "Font"},

        {"name": "font_size", "type": "number", "label": "",
         "group": "Text", "row_label": "Size", "min": 6, "max": 96,
         "disabled_when": lambda p: bool(p.get("font_autofit", False))},
        {"name": "font_autofit", "type": "boolean", "label": "",
         "group": "Text", "row_label": "Auto Fit"},

        {"name": "font_bold", "type": "boolean", "label": "",
         "group": "Text", "subgroup": "Style", "row_label": "Bold"},
        {"name": "font_italic", "type": "boolean", "label": "",
         "group": "Text", "subgroup": "Style", "row_label": "Italic"},
        {"name": "font_underline", "type": "boolean", "label": "",
         "group": "Text", "subgroup": "Style", "row_label": "Underline"},
        {"name": "font_overstrike", "type": "boolean", "label": "",
         "group": "Text", "subgroup": "Style", "row_label": "Strike"},

        {"name": "anchor", "type": "anchor", "label": "",
         "group": "Text", "row_label": "Alignment"},

        {"name": "text_color", "type": "color", "label": "",
         "group": "Text", "row_label": "Text Color"},

        # --- Icon --------------------------------------------------------
        {"name": "image", "type": "image", "label": "",
         "group": "Icon", "row_label": "Icon"},
        {"name": "image_color", "type": "color", "label": "",
         "group": "Icon", "row_label": "Icon Color",
         "clearable": True, "clear_value": "transparent",
         "disabled_when": lambda p: not p.get("image")},
        {"name": "image_width", "type": "number", "label": "W",
         "group": "Icon",
         "pair": "img_size", "row_label": "Icon Size",
         "min": 4, "max": 512,
         "disabled_when": lambda p: not p.get("image")},
        {"name": "image_height", "type": "number", "label": "H",
         "group": "Icon",
         "pair": "img_size", "min": 4, "max": 512,
         "disabled_when": lambda p: not p.get("image")},
        {"name": "compound", "type": "compound", "label": "",
         "group": "Icon", "row_label": "Icon Side",
         "disabled_when": lambda p: not p.get("image")},
        {"name": "preserve_aspect", "type": "boolean", "label": "",
         "group": "Icon", "row_label": "Preserve Aspect",
         "disabled_when": lambda p: not p.get("image")},

        # --- Geometry ----------------------------------------------------
        {"name": "x", "type": "number", "label": "X",
         "group": "Geometry", "pair": "pos", "row_label": "Position"},
        {"name": "y", "type": "number", "label": "Y",
         "group": "Geometry", "pair": "pos"},

        {"name": "width", "type": "number", "label": "W",
         "group": "Geometry", "pair": "size", "row_label": "Size",
         "min": 20, "max": 2000},
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
        {"name": "border_spacing", "type": "number", "label": "",
         "group": "Rectangle",
         "row_label": "Inner Padding", "min": 0, "max": 20},
    ]

    # Schema props that are NOT passed as CTkButton kwargs directly.
    # They live only in the node, or are consumed to build derived CTk
    # kwargs (the four state colours, font, state, image).
    _NODE_ONLY_KEYS = {
        "x", "y", "image_width", "image_height",
        "button_enabled", "border_enabled",
        "preserve_aspect", "image_color",
        # Unity tint inputs are consumed by transform_properties() →
        # CTkButton's per-state kwargs. None of these names are valid
        # CTkButton kwargs themselves.
        "normal_color", "hover_tint", "pressed_tint", "disabled_tint",
        "disabled_fade",
        # Legacy fields that may linger in old project files; never
        # passed to CTkButton.
        "state_disabled",
        "fg_color_disabled", "hover_color",
        "text_color_disabled", "text_color_hover",
        "text_hover", "text_hover_color",
        "image_color_disabled", "border_color_disabled",
    }

    _FONT_KEYS = {
        "font_family",
        "font_size", "font_bold", "font_italic",
        "font_underline", "font_overstrike",
    }

    # ==================================================================
    # Builder → CTkButton kwargs
    # ==================================================================
    @classmethod
    def _derive_palette(cls, properties: dict) -> dict:
        """Compute the four-state bg palette + disabled fade for text /
        image / border. Returned dict has ``fg_color``, ``hover_color``,
        ``pressed_color``, ``fg_color_disabled``, and (when fade is on)
        ``text_color_disabled``, ``image_color_disabled``,
        ``border_color_disabled``."""
        normal = properties.get("normal_color") or _DEFAULT_NORMAL
        hover_tint = properties.get("hover_tint") or _DEFAULT_HOVER_TINT
        pressed_tint = properties.get("pressed_tint") or _DEFAULT_PRESSED_TINT
        disabled_tint = properties.get("disabled_tint") or _DEFAULT_DISABLED_TINT
        disabled_fade = bool(properties.get("disabled_fade", False))

        palette = ctk.derive_state_colors(
            normal=normal,
            hover_tint=hover_tint,
            pressed_tint=pressed_tint,
            disabled_tint=disabled_tint,
            multiplier=1.0,
            disabled_fade=disabled_fade,
            surface=_SURFACE,
        )

        derived = {
            "fg_color": palette["normal"],
            "hover_color": palette["hover"],
            "pressed_color": palette["pressed"],
            "fg_color_disabled": palette["disabled"],
        }

        # Disabled fade also dims text / icon / border when enabled. Fork's
        # CTkButton ``*_disabled`` kwargs accept None (auto-derive); we only
        # set them explicitly when fade is on.
        if disabled_fade:
            text_color = properties.get("text_color") or "#ffffff"
            derived["text_color_disabled"] = ctk.fade_color(text_color, 0.4, _SURFACE)

            image_color = properties.get("image_color")
            if image_color and image_color != "transparent":
                derived["image_color_disabled"] = ctk.fade_color(image_color, 0.4, _SURFACE)

            border_color = properties.get("border_color") or "#efefef"
            derived["border_color_disabled"] = ctk.fade_color(border_color, 0.5, _SURFACE)

        return derived

    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        """Translate the builder's property dict into CTkButton kwargs.

        - Strips builder-only keys (x/y, image_*, button_enabled, …,
          plus all Unity inputs that have no CTkButton equivalent).
        - ``button_enabled`` bool → CTk ``state="normal"/"disabled"``.
        - ``border_enabled`` False → forces ``border_width=0``.
        - Builds a CTkFont from the font_* family.
        - Loads ``image`` path into a CTkImage sized by image_width/height.
        - Derives the four-state bg palette via ``ctk.derive_state_colors``
          (ctkmaker-core >= 5.4.20) and applies it to the per-state CTk
          kwargs. Also applies an optional disabled fade to text / icon /
          border when ``disabled_fade`` is on.
        """
        result = {
            k: v for k, v in properties.items()
            if k not in cls._NODE_ONLY_KEYS and k not in cls._FONT_KEYS
        }

        # Always-on: the fork's native pill / full-circle layout fix.
        result["full_circle"] = True

        result["state"] = (
            "normal" if properties.get("button_enabled", True)
            else "disabled"
        )

        # Border off → zero the width so CTk draws no outline.
        if not properties.get("border_enabled"):
            result["border_width"] = 0

        # Derived per-state palette
        result.update(cls._derive_palette(properties))

        # Cleared image_color comes through as "" or "transparent"; the
        # CTkButton kwarg treats only None as "unset".
        image_color = properties.get("image_color")
        if image_color and image_color != "transparent":
            result["image_color"] = image_color

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
            log_error("CTkButtonDescriptor.transform_properties font")

        if "image" in result:
            result["image"] = cls._build_image(properties, result["image"])

        return result

    @classmethod
    def _build_image(cls, properties: dict, image_path):
        if not image_path:
            return None
        try:
            from PIL import Image
            img = Image.open(image_path)
            iw = int(properties.get("image_width", 20) or 20)
            ih = int(properties.get("image_height", 20) or 20)
            return ctk.CTkImage(
                light_image=img, dark_image=img, size=(iw, ih),
                preserve_aspect=bool(properties.get("preserve_aspect")),
            )
        except Exception:
            log_error("CTkButtonDescriptor.transform_properties image")
            return None

    @classmethod
    def export_kwarg_overrides(cls, properties: dict) -> dict:
        """Derived kwargs for the exported constructor call (mirrors
        ``transform_properties``, since the exporter builds from raw
        properties):

        - ``full_circle``: always True.
        - Four-state bg palette: ``fg_color``, ``hover_color``,
          ``pressed_color``, ``fg_color_disabled`` — pre-computed so the
          exported ``.py`` doesn't need to import the colour math at
          runtime; the values are frozen at export time.
        - Disabled fade for text / icon / border when toggled on.
        """
        overrides = {"full_circle": True}
        overrides.update(cls._derive_palette(properties))
        return overrides

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        kwargs = cls.transform_properties(properties)
        if init_kwargs:
            kwargs.update(init_kwargs)
        return ctk.CTkButton(master, **kwargs)
