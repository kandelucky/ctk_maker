"""CTkButton widget descriptor.

Declares the full schema the Properties panel uses to render editors
for a CTkButton, plus the bridge that converts the builder's
property dict into the kwargs CTkButton actually accepts
(`transform_properties`).

Groups shown in the Properties panel, in order
(Content → Layout → Visual → Behavior):

    Text                — label, font style, alignment, text colors
    Icon                — image picker, size, tint, compound, preserve aspect
    Geometry            — x/y, width/height
    Rectangle           — corner radius, border (thickness + color)
    Main Colors         — background, hover
    Button Interaction  — interactable, hover effect
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor


class CTkButtonDescriptor(WidgetDescriptor):
    type_name = "CTkButton"
    display_name = "Button"
    prefers_fill_in_layout = True
    # ``full_circle=True`` is passed unconditionally (see
    # ``transform_properties`` / ``export_kwarg_overrides``). CTkButton's
    # ``_create_grid`` reserves ``corner_radius`` worth of space on the
    # outer columns, which makes full-circle / pill buttons with text
    # overflow their nominal frame size. The fork's native ``full_circle``
    # kwarg (ctkmaker-core >= 5.4.12) lifts that reservation — superseding
    # the old inlined ``CircleButton`` override, so this descriptor maps
    # 1:1 onto a plain ``ctk.CTkButton``.

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
        "border_color": "#565b5e",
        "border_color_disabled": None,
        "border_spacing": 2,
        # Button Interaction
        "button_enabled": True,
        # Main colors
        "fg_color": "#6366f1",
        "fg_color_disabled": None,
        "hover": True,
        "hover_color": "#4f46e5",
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
        "text_color_disabled": "#a0a0a0",
        "text_hover": False,
        "text_hover_color": "#b2b2b2",
        # Image
        "image": None,
        "image_color": None,
        "image_color_disabled": None,
        "image_width": 20,
        "image_height": 20,
        "compound": "left",
        "preserve_aspect": False,
    }

    property_schema = [
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
         "group": "Text", "row_label": "Normal Text Color"},
        {"name": "text_color_disabled", "type": "color", "label": "",
         "group": "Text", "row_label": "Disabled Text Color"},
        {"name": "text_hover", "type": "boolean", "label": "",
         "group": "Text", "row_label": "Hover Color Effect"},
        {"name": "text_hover_color", "type": "color", "label": "",
         "group": "Text", "row_label": "Hover Color",
         "disabled_when": lambda p: not p.get("text_hover")},

        # --- Icon --------------------------------------------------------
        {"name": "image", "type": "image", "label": "",
         "group": "Icon", "row_label": "Icon"},
        {"name": "image_color", "type": "color", "label": "",
         "group": "Icon", "row_label": "Normal Color",
         "clearable": True, "clear_value": "transparent",
         "disabled_when": lambda p: not p.get("image")},
        {"name": "image_color_disabled", "type": "color", "label": "",
         "group": "Icon", "row_label": "Disabled Color",
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
        {"name": "border_color_disabled", "type": "color", "label": "",
         "group": "Rectangle", "subgroup": "Border",
         "row_label": "Disabled Color", "clearable": True,
         "disabled_when": lambda p: not p.get("border_enabled")},
        {"name": "border_spacing", "type": "number", "label": "",
         "group": "Rectangle",
         "row_label": "Inner Padding", "min": 0, "max": 20},

        # --- Main Colors -------------------------------------------------
        # Clearable — icon-only buttons usually want a transparent
        # background that picks up the parent's fill.
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Background",
         "clearable": True, "clear_value": "transparent"},
        {"name": "fg_color_disabled", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Disabled Background",
         "clearable": True},
        {"name": "hover_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Hover Color",
         "disabled_when": lambda p: not p.get("hover", True)},

        # --- Button Interaction ------------------------------------------
        {"name": "button_enabled", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Interactable"},
        {"name": "hover", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Hover Effect"},
    ]

    # Schema props that are NOT passed as kwargs to CTkButton directly.
    # They live only in the node (builder side), or are consumed to build
    # derived CTk kwargs (font, state, image).
    _NODE_ONLY_KEYS = {
        "x", "y", "image_width", "image_height",
        "button_enabled", "border_enabled",
        "preserve_aspect", "image_color", "image_color_disabled",
        # text_hover (toggle) + text_hover_color are consumed by
        # transform_properties() into the native text_color_hover
        # kwarg — the raw keys themselves are never CTkButton kwargs.
        "text_hover", "text_hover_color",
        # Legacy: migrated to button_enabled but may still appear in
        # old project files; never passed to CTkButton.
        "state_disabled",
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
    def transform_properties(cls, properties: dict) -> dict:
        """Translate the builder's property dict into CTkButton kwargs.

        - Strips builder-only keys (x/y, image_*, button_enabled, …).
        - `button_enabled` bool → CTk `state="normal"/"disabled"`.
        - `border_enabled` False → forces `border_width=0`.
        - Builds a CTkFont from the font_* family.
        - Loads `image` path into a CTkImage sized by image_width/height
          with an optional tint from `image_color` (or disabled tint).
        """
        result = {
            k: v for k, v in properties.items()
            if k not in cls._NODE_ONLY_KEYS and k not in cls._FONT_KEYS
        }

        # Cleared colour-editor values arrive as "" / "transparent"; the
        # *_disabled / image_* kwargs all treat that as "unset" (None).
        def _active(c):
            return c if c and c != "transparent" else None

        # Always-on: the fork's native pill / full-circle layout fix
        # (ctkmaker-core >= 5.4.12), replacing the old CircleButton crutch.
        result["full_circle"] = True

        result["state"] = (
            "normal" if properties.get("button_enabled", True)
            else "disabled"
        )

        # Disabled-state background / border → CTk's *_disabled kwargs
        # (fork >= 5.4.6). Cleared colour → None → the fork auto-derives a
        # dimmed shade from the enabled colour; an explicit colour is used
        # verbatim. (text_color_disabled stays a plain always-set prop.)
        result["fg_color_disabled"] = _active(properties.get("fg_color_disabled"))
        result["border_color_disabled"] = _active(
            properties.get("border_color_disabled")
        )

        # text_hover (toggle) + text_hover_color → CTkButton's native
        # text_color_hover kwarg (fork >= 5.4.1). None when the toggle
        # is off, so the button keeps its plain text_color on hover.
        result["text_color_hover"] = (
            properties.get("text_hover_color")
            if properties.get("text_hover") else None
        )

        # Border off → zero the width so CTk draws no outline.
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
            log_error("CTkButtonDescriptor.transform_properties font")

        if "image" in result:
            result["image"] = cls._build_image(properties, result["image"])
            # image_color / image_color_disabled tint the button's image
            # widget-side (fork >= 5.4.5); CTkButton swaps between them
            # off the state= kwarg set above. "transparent" is the
            # colour-editor's cleared sentinel — _active normalises it to
            # None so CTkButton's _check_color_type doesn't reject it.
            result["image_color"] = _active(properties.get("image_color"))
            result["image_color_disabled"] = _active(
                properties.get("image_color_disabled")
            )

        return result

    @classmethod
    def _build_image(cls, properties: dict, image_path):
        # The descriptor only loads the PNG and hands the icon box size
        # + preserve_aspect flag to CTkImage — native contain-fit and
        # native tint (image_color / image_color_disabled, applied
        # widget-side in transform_properties) live in the fork
        # (>= 5.4.4). Render-time so saved-state mismatches and live
        # edits both render correctly without an OFF→ON toggle.
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
        transform_properties(), since the exporter builds from raw
        properties):

        - full_circle: always True — the fork's native pill / full-circle
          layout fix (ctkmaker-core >= 5.4.12), replacing the old inlined
          CircleButton override.
        - text_color_hover: emitted only when the text_hover toggle is on
          and a colour is set — otherwise CTkButton's None default holds.
        """
        overrides = {"full_circle": True}
        if properties.get("text_hover") and properties.get("text_hover_color"):
            overrides["text_color_hover"] = properties["text_hover_color"]
        return overrides

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        kwargs = cls.transform_properties(properties)
        if init_kwargs:
            kwargs.update(init_kwargs)
        return ctk.CTkButton(master, **kwargs)
