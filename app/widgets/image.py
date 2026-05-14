"""Image widget descriptor.

A dedicated image display widget — CTk doesn't ship one, so the
builder composes it from a ``CTkLabel(text="", image=CTkImage(...))``.
The exporter emits a CTkLabel so the generated code stays on CTk's
public API.

Groups shown in the Properties panel, in order
(Content → Layout → Visual):

    Image       — file path, preserve aspect
    Tint        — optional normal colour overlay (icon-style tint)
    Geometry    — x/y, width/height (= widget bounding box; with
                  preserve_aspect on the image is contain-fit + centred,
                  with it off the image stretches to fill)
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
        "preserve_aspect": False,
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
         "min": 4, "max": 4000},

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
            # image_color tints the CTkLabel's image widget-side (fork
            # >= 5.4.5). "transparent" is the colour-editor's cleared
            # sentinel — normalise it to None (no tint).
            color = properties.get("image_color")
            result["image_color"] = (
                color if color and color != "transparent" else None
            )
        else:
            # Explicit clear so undo/redo cycles that remove the
            # image also strip the CTkImage from the CTkLabel.
            result["image"] = None
            result["image_color"] = None
        return result

    @classmethod
    def _build_image(cls, properties: dict, image_path: str):
        # The descriptor only loads the PNG and hands the box size +
        # preserve_aspect flag to CTkImage — native contain-fit
        # (preserve_aspect) and native tint (image_color, applied
        # widget-side in transform_properties) live in the fork
        # (>= 5.4.4), so the old PIL recolour / aspect math is gone.
        # Fitting lives in CTkImage so resize-handle drags — which write
        # width and height in two separate `update_property` calls —
        # stay aspect-preserved on every tick without a derive-height race.
        try:
            from PIL import Image
            img = Image.open(image_path)
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            box_w = int(properties.get("width", 128) or 128)
            box_h = int(properties.get("height", 128) or 128)
            return ctk.CTkImage(
                light_image=img, dark_image=img, size=(box_w, box_h),
                preserve_aspect=bool(properties.get("preserve_aspect")),
            )
        except Exception:
            log_error("ImageDescriptor._build_image")
            return None

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        kwargs = cls.transform_properties(properties)
        if init_kwargs:
            kwargs.update(init_kwargs)
        return ctk.CTkLabel(master, **kwargs)
