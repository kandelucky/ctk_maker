"""Gate-mapping constants for the auto-trace bindings pipeline.

The actual bind-helper bodies (``bind_var_to_widget`` /
``bind_var_to_font`` / ``balance_pack`` etc.) moved into the
``ctkmaker-core`` fork at 5.4.17 — exports import them from
``customtkinter`` and call them directly, instead of CTkMaker inlining
the source. This file is now just the small set of property-key
classifications the exporter still needs at code-generation time to
decide which fork helper to emit a call to.
"""

from __future__ import annotations


# Maker-only composite property keys that the font helper handles —
# maps each property to the corresponding CTkFont kwarg name. Used to
# recognise font composites and emit ``ctk.bind_var_to_font`` calls
# instead of the (broken-for-them) ``ctk.bind_var_to_widget`` path.
_FONT_COMPOSITE_TO_ATTR = {
    "font_bold": "weight",
    "font_italic": "slant",
    "font_size": "size",
    "font_family": "family",
    "font_underline": "underline",
    "font_overstrike": "overstrike",
}

# Image-related Maker-only composites that, when var-bound, drive a
# live update on the widget's native image kwargs / its CTkImage.
_IMAGE_REBUILD_KEYS = frozenset({
    "image", "image_width", "image_height", "preserve_aspect",
    "image_color", "image_color_disabled",
})

# Phase 3 — geometry composites driven through ``place_configure``.
_PLACE_COORD_KEYS = frozenset({"x", "y"})

# Maker-only bool composites that translate to CTk's ``state`` kwarg.
# ``label_enabled`` has its own rebuilder (``bind_var_to_label_enabled``)
# because Tk Label's native disabled rendering paints a stipple wash
# over the image.
_STATE_COMPOSITE_KEYS = frozenset({"button_enabled"})
