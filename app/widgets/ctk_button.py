"""CTkButton widget descriptor.

Declares the full schema the Properties panel uses to render editors
for a CTkButton, plus the bridge that converts the builder's
property dict into the kwargs CTkButton actually accepts
(`transform_properties`).

Groups shown in the Properties panel, in order:

    Geometry        — x/y, width/height
    Rectangle       — corner radius, border (thickness + color)
    State           — disabled flag
    Main Colors     — background, hover
    Text            — label, font style, alignment, text colors
    Image & Alignment — image picker, image size, compound
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor


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
        "border_color": "#565b5e",
        "border_spacing": 2,
        # Button Interaction
        "button_enabled": True,
        # Main colors
        "fg_color": "#1f6aa5",
        "hover": True,
        "hover_color": "#144870",
        # Text content + style
        "text": "CTkButton",
        "font_size": 13,
        "font_autofit": False,
        "font_bold": False,
        "font_italic": False,
        "font_underline": False,
        "font_overstrike": False,
        "anchor": "center",
        "text_color": "#ffffff",
        "text_color_disabled": "#a0a0a0",
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

        # --- Button Interaction ------------------------------------------
        {"name": "button_enabled", "type": "boolean", "label": "",
         "group": "Button Interaction", "row_label": "Interactable"},

        # --- Main Colors -------------------------------------------------
        # Clearable — icon-only buttons usually want a transparent
        # background that picks up the parent's fill.
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Background",
         "clearable": True, "clear_value": "transparent"},
        {"name": "hover", "type": "boolean", "label": "",
         "group": "Main Colors", "row_label": "Hover"},
        {"name": "hover_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Hover Color",
         "disabled_when": lambda p: not p.get("hover", True)},

        # --- Text --------------------------------------------------------
        {"name": "text", "type": "multiline", "label": "",
         "group": "Text", "row_label": "Label"},

        {"name": "font_size", "type": "number", "label": "",
         "group": "Text", "row_label": "Size", "min": 6, "max": 96,
         "disabled_when": lambda p: bool(p.get("font_autofit", False))},
        {"name": "font_autofit", "type": "boolean", "label": "",
         "group": "Text", "row_label": "Best Fit"},

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

        # --- Image & Alignment -------------------------------------------
        {"name": "image", "type": "image", "label": "",
         "group": "Image & Alignment", "row_label": "Image"},
        {"name": "image_color", "type": "color", "label": "",
         "group": "Image & Alignment", "row_label": "Normal Color",
         "clearable": True, "clear_value": None,
         "disabled_when": lambda p: not p.get("image")},
        {"name": "image_color_disabled", "type": "color", "label": "",
         "group": "Image & Alignment", "row_label": "Disabled Color",
         "clearable": True, "clear_value": None,
         "disabled_when": lambda p: not p.get("image")},
        {"name": "image_width", "type": "number", "label": "W",
         "group": "Image & Alignment",
         "pair": "img_size", "row_label": "Icon Size",
         "min": 4, "max": 512,
         "disabled_when": lambda p: not p.get("image")},
        {"name": "image_height", "type": "number", "label": "H",
         "group": "Image & Alignment",
         "pair": "img_size", "min": 4, "max": 512,
         "disabled_when": lambda p: (
             not p.get("image") or bool(p.get("preserve_aspect")))},
        {"name": "compound", "type": "compound", "label": "",
         "group": "Image & Alignment", "row_label": "Icon Side",
         "disabled_when": lambda p: not p.get("image")},
        {"name": "preserve_aspect", "type": "boolean", "label": "",
         "group": "Image & Alignment", "row_label": "Preserve Aspect",
         "disabled_when": lambda p: not p.get("image")},
    ]

    # Properties whose change should re-run `compute_derived` to update
    # derived props (font_size via autofit, image_height via preserve_aspect).
    derived_triggers = {
        "text", "width", "height", "font_bold", "font_autofit",
        "image", "image_width", "preserve_aspect",
    }

    # Schema props that are NOT passed as kwargs to CTkButton directly.
    # They live only in the node (builder side), or are consumed to build
    # derived CTk kwargs (font, state, image).
    _NODE_ONLY_KEYS = {
        "x", "y", "image_width", "image_height",
        "button_enabled", "border_enabled",
        "preserve_aspect", "image_color", "image_color_disabled",
        # Legacy: migrated to button_enabled but may still appear in
        # old project files; never passed to CTkButton.
        "state_disabled",
    }

    # Cache of image path -> native aspect ratio (width / height).
    _aspect_cache: dict[str, float] = {}
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

        # --- Autofit font size ----------------------------------------
        if properties.get("font_autofit"):
            text = properties.get("text") or ""
            if text:
                try:
                    width = int(properties.get("width", 140))
                    height = int(properties.get("height", 32))
                    bold = bool(properties.get("font_bold", False))
                    new_size = cls._compute_autofit_size(
                        text, width, height, bold,
                    )
                    if new_size > 0:
                        result["font_size"] = new_size
                except (ValueError, TypeError):
                    pass

        # --- Preserve aspect: derive image_height from image_width ----
        if properties.get("preserve_aspect") and properties.get("image"):
            aspect = cls._native_aspect(properties["image"])
            if aspect:
                try:
                    w = int(properties.get("image_width") or 20)
                    result["image_height"] = max(1, round(w / aspect))
                except (ValueError, TypeError):
                    pass

        return result

    @classmethod
    def _native_aspect(cls, path: str) -> float | None:
        """Return native width/height ratio of the image at `path`."""
        if not path:
            return None
        if path in cls._aspect_cache:
            return cls._aspect_cache[path]
        try:
            from PIL import Image
            with Image.open(path) as img:
                w, h = img.size
            if h == 0:
                return None
            aspect = w / h
            cls._aspect_cache[path] = aspect
            return aspect
        except Exception:
            return None

    @classmethod
    def _compute_autofit_size(cls, text: str, width: int, height: int,
                              bold: bool) -> int:
        """Binary-search the largest font size whose rendered text fits."""
        import tkinter.font as tkfont
        avail_w = max(10, width - 20)
        avail_h = max(10, height - 8)
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

        result["state"] = (
            "normal" if properties.get("button_enabled", True)
            else "disabled"
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
        try:
            result["font"] = ctk.CTkFont(
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
            if not properties.get("button_enabled", True):
                color = (
                    properties.get("image_color_disabled")
                    or properties.get("image_color")
                )
            else:
                color = properties.get("image_color")
            if color:
                img = cls._tint_image(img, color)
            iw = int(properties.get("image_width", 20) or 20)
            ih = int(properties.get("image_height", 20) or 20)
            return ctk.CTkImage(
                light_image=img, dark_image=img, size=(iw, ih),
            )
        except Exception:
            log_error("CTkButtonDescriptor.transform_properties image")
            return None

    @classmethod
    def _tint_image(cls, img, hex_color: str):
        """Icon-style tint: replace RGB with hex_color, keep alpha."""
        from PIL import Image
        try:
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
        except (ValueError, IndexError, TypeError):
            return img
        rgba = img.convert("RGBA")
        alpha = rgba.split()[-1]
        tinted = Image.new("RGBA", rgba.size, (r, g, b, 0))
        tinted.putalpha(alpha)
        return tinted

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        kwargs = cls.transform_properties(properties)
        if init_kwargs:
            kwargs.update(init_kwargs)
        return ctk.CTkButton(master, **kwargs)
