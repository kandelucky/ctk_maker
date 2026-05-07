"""Image widget descriptor.

A dedicated image display widget — CTk doesn't ship one, so the
builder composes it from a ``CTkLabel(text="", image=CTkImage(...))``.
The exporter emits a CTkLabel so the generated code stays on CTk's
public API.

Groups shown in the Properties panel, in order
(Content → Layout → Visual):

    Image       — file path, preserve aspect
    Tint        — optional normal colour overlay (icon-style tint)
    Geometry    — x/y, width/height (= image pixel size)
    Main Colors — background colour (transparent by default)
"""
from pathlib import Path

import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor

PLACEHOLDER_COLOR = "#444444"
DEFAULT_IMAGE_PATH = str(
    Path(__file__).resolve().parent.parent
    / "assets" / "defaults" / "image.png"
)


class ImageDescriptor(WidgetDescriptor):
    type_name = "Image"
    ctk_class_name = "CTkLabel"
    display_name = "Image"
    prefers_fill_in_layout = True

    default_properties = {
        # Geometry
        "x": 120,
        "y": 120,
        "width": 128,
        "height": 128,
        # Image — bundled sample so a fresh drop shows something.
        "image": DEFAULT_IMAGE_PATH,
        "preserve_aspect": True,
        # Tint
        "image_color": None,
        # Main colors
        "fg_color": "transparent",
        # Wrapped CTkLabel must not show its default text.
        "text": "",
    }

    property_schema = [
        # --- Image -------------------------------------------------------
        {"name": "image", "type": "image", "label": "",
         "group": "Image", "row_label": "Image"},
        {"name": "preserve_aspect", "type": "boolean", "label": "",
         "group": "Image", "row_label": "Preserve Aspect",
         "disabled_when": lambda p: not p.get("image")},

        # --- Tint --------------------------------------------------------
        # Only Normal tint — CTkLabel has no disabled state, so
        # ``image_color_disabled`` from the CTkButton descriptor pattern
        # would be dead on Image. Dropped to avoid a misleading Inspector
        # knob that did nothing.
        {"name": "image_color", "type": "color", "label": "",
         "group": "Tint", "row_label": "Normal Color",
         "clearable": True, "clear_value": "transparent",
         "disabled_when": lambda p: not p.get("image")},

        # --- Geometry ----------------------------------------------------
        {"name": "x", "type": "number", "label": "X",
         "group": "Geometry", "pair": "pos", "row_label": "Position"},
        {"name": "y", "type": "number", "label": "Y",
         "group": "Geometry", "pair": "pos"},

        {"name": "width", "type": "number", "label": "W",
         "group": "Geometry", "pair": "size", "row_label": "Size",
         "min": 4, "max": 4000},
        {"name": "height", "type": "number", "label": "H",
         "group": "Geometry", "pair": "size",
         "min": 4, "max": 4000,
         "disabled_when": lambda p: bool(p.get("preserve_aspect"))},

        # --- Main Colors -------------------------------------------------
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Background",
         "clearable": True, "clear_value": "transparent"},
    ]

    _NODE_ONLY_KEYS = {
        "x", "y",
        "image", "image_color",
        "preserve_aspect",
    }

    _aspect_cache: dict[str, float] = {}
    derived_triggers = {"image", "width", "preserve_aspect"}

    # ------------------------------------------------------------------
    # Derived geometry (preserve_aspect)
    # ------------------------------------------------------------------
    @classmethod
    def compute_derived(cls, properties: dict) -> dict:
        if not properties.get("preserve_aspect"):
            return {}
        image_path = properties.get("image")
        if not image_path:
            return {}
        ratio = cls._aspect_ratio(image_path)
        if ratio is None or ratio <= 0:
            return {}
        try:
            width = int(properties.get("width", 128))
        except (TypeError, ValueError):
            return {}
        new_h = max(4, int(round(width / ratio)))
        if int(properties.get("height", 0) or 0) != new_h:
            return {"height": new_h}
        return {}

    @classmethod
    def _aspect_ratio(cls, image_path: str) -> float | None:
        if image_path in cls._aspect_cache:
            return cls._aspect_cache[image_path]
        try:
            from PIL import Image as PILImage
            with PILImage.open(image_path) as im:
                w, h = im.size
            ratio = w / h if h else None
        except Exception:
            ratio = None
        if ratio is not None:
            cls._aspect_cache[image_path] = ratio
        return ratio

    # ------------------------------------------------------------------
    # Property → CTkLabel kwargs
    # ------------------------------------------------------------------
    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        result = {
            k: v for k, v in properties.items()
            if k not in cls._NODE_ONLY_KEYS
        }
        # text="" — the wrapped CTkLabel is image-only.
        result["text"] = ""

        # Placeholder fill: when no image is set AND the user hasn't
        # chosen a background, show a grey square so the widget
        # isn't invisible in the builder.
        if not properties.get("image"):
            if result.get("fg_color") in (None, "transparent"):
                result["fg_color"] = PLACEHOLDER_COLOR

        image_path = properties.get("image")
        if image_path:
            result["image"] = cls._build_image(properties, image_path)
        else:
            # Explicit clear so undo/redo cycles that remove the
            # image also strip the CTkImage from the CTkLabel.
            result["image"] = None
        return result

    @classmethod
    def _build_image(cls, properties: dict, image_path: str):
        try:
            from PIL import Image
            img = Image.open(image_path)
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            color = properties.get("image_color")
            if color:
                img = cls._tint_image(img, color)
            iw = int(properties.get("width", 128) or 128)
            ih = int(properties.get("height", 128) or 128)
            return ctk.CTkImage(
                light_image=img, dark_image=img, size=(iw, ih),
            )
        except Exception:
            log_error("ImageDescriptor._build_image")
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
        return ctk.CTkLabel(master, **kwargs)
