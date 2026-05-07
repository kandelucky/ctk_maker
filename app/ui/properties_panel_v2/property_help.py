"""Per-property + per-parent-row help text for Properties panel tooltips.

Two dicts:

- ``PROPERTY_HELP`` — keyed by schema property ``name`` (renders on
  ``p:<name>`` rows).
- ``ROW_HELP`` — keyed by full tree iid for collapsible parent rows
  (``pair:<name>`` virtual numeric pairs, ``g:<group>/<subgroup>``
  schema subgroups).

Each entry has a short description and an optional warning that flags
side-effects, conflicts, or ranges the user can't see from the UI.

V1 scope: CTkLabel only. Other widgets fall back to no tooltip.
"""

from __future__ import annotations


ROW_HELP: dict[str, dict[str, str]] = {
    # --- Pair virtual parent rows ------------------------------------
    "pair:pos": {
        "description": (
            "Horizontal and vertical position of the widget in pixels, "
            "measured from the parent's top-left corner. Used in "
            "absolute (place) layout."
        ),
    },
    "pair:size": {
        "description": (
            "Widget width and height in pixels. Acts as a hint when "
            "the parent uses pack/grid; the layout manager may resize."
        ),
    },
    "pair:pad": {
        "description": (
            "Horizontal and vertical inner padding before the text + "
            "icon block. Italic fonts may clip at padx=0 — bump to 4+."
        ),
    },
    "pair:img_size": {
        "description": (
            "Icon width and height in pixels."
        ),
        "warning": (
            "Height is locked to the icon's native aspect ratio when "
            "Preserve Aspect is on."
        ),
    },

    # --- Schema subgroups --------------------------------------------
    "g:Text/Style": {
        "description": (
            "Bold, italic, underline, and strike-through decorations. "
            "Combined into one row preview since they read as one "
            "visual style."
        ),
    },
    "g:Text/Wrap": {
        "description": (
            "Word-wrapping behavior — toggle and maximum line width "
            "before text breaks to the next line."
        ),
    },
}


PROPERTY_HELP: dict[str, dict[str, str]] = {
    # --- Geometry ----------------------------------------------------
    "x": {
        "description": (
            "Horizontal position in pixels from the parent's top-left "
            "corner. Used in absolute (place) layout."
        ),
    },
    "y": {
        "description": (
            "Vertical position in pixels from the parent's top-left "
            "corner. Used in absolute (place) layout."
        ),
    },
    "width": {
        "description": (
            "Widget width in pixels. Acts as a hint when the parent "
            "uses pack/grid; the layout manager may resize."
        ),
    },
    "height": {
        "description": (
            "Widget height in pixels. Acts as a hint when the parent "
            "uses pack/grid; the layout manager may resize."
        ),
    },

    # --- Rectangle ---------------------------------------------------
    "corner_radius": {
        "description": (
            "Rounds the widget's corners by this many pixels. "
            "Set to 0 for sharp corners."
        ),
        "warning": (
            "CTk caps the visible radius at min(width, height) / 2."
        ),
    },

    # --- Alignment ---------------------------------------------------
    "anchor": {
        "description": (
            "Position of the text + icon block inside the widget."
        ),
    },
    "padx": {
        "description": (
            "Horizontal padding inside the widget before the text "
            "block. Italic fonts may clip at padx=0 — bump to 4+."
        ),
    },
    "pady": {
        "description": (
            "Vertical padding inside the widget before the text block."
        ),
    },

    # --- Interaction -------------------------------------------------
    "label_enabled": {
        "description": (
            "When off, the label renders dimmed using Disabled Text "
            "Color and Disabled Icon Color."
        ),
    },
    "cursor": {
        "description": (
            "Mouse cursor shape when hovering this widget."
        ),
    },
    "takefocus": {
        "description": (
            "Allow the widget to receive keyboard focus via Tab "
            "traversal. Labels rarely need this."
        ),
    },

    # --- Main Colors -------------------------------------------------
    "fg_color": {
        "description": (
            "Filled body color of the label. Set to transparent to "
            "inherit the parent's fill."
        ),
    },
    "bg_color": {
        "description": (
            "Anti-aliasing layer behind the rounded corners. Usually "
            "transparent so CTk auto-derives it from the parent."
        ),
    },

    # --- Text --------------------------------------------------------
    "text": {
        "description": (
            "Label content. Multi-line: separate lines with newlines."
        ),
    },
    "font_family": {
        "description": (
            "Font family name. Empty = inherit from the active theme."
        ),
    },
    "font_size": {
        "description": "Font size in pixels.",
        "warning": (
            "Ignored while Best Fit is on — autofit drives the size."
        ),
    },
    "font_autofit": {
        "description": (
            "Auto-shrink the font so the text fits within the widget "
            "bounds."
        ),
        "warning": (
            "Overrides the manual Size value while enabled."
        ),
    },
    "font_bold": {
        "description": "Render the text in bold weight.",
    },
    "font_italic": {
        "description": "Render the text in italic style.",
    },
    "font_underline": {
        "description": "Underline the text.",
    },
    "font_overstrike": {
        "description": "Strike through the text.",
    },
    "justify": {
        "description": (
            "Horizontal alignment for multi-line text. Single-line "
            "text is governed by Anchor."
        ),
    },
    "font_wrap": {
        "description": (
            "Enable word wrapping when the text is wider than the "
            "wrap length."
        ),
    },
    "wraplength": {
        "description": (
            "Maximum line width before text wraps to the next line. "
            "0 = wrap at the widget's current width."
        ),
        "warning": "Ignored while Wrap is disabled.",
    },
    "text_color": {
        "description": "Text color when the label is enabled.",
    },
    "text_color_disabled": {
        "description": (
            "Text color used when the label is disabled."
        ),
    },

    # --- Icon --------------------------------------------------------
    "image": {
        "description": (
            "PNG/icon shown alongside or instead of the text."
        ),
    },
    "image_color": {
        "description": (
            "Tint applied to the icon — replaces RGB, keeps alpha. "
            "Empty leaves the icon's native colors."
        ),
        "warning": "Has no effect when no image is set.",
    },
    "image_color_disabled": {
        "description": (
            "Tint applied to the icon when the label is disabled."
        ),
        "warning": "Has no effect when no image is set.",
    },
    "image_width": {
        "description": "Icon width in pixels.",
        "warning": "Has no effect when no image is set.",
    },
    "image_height": {
        "description": "Icon height in pixels.",
        "warning": (
            "Ignored when Preserve Aspect is on (height derives "
            "from width) or when no image is set."
        ),
    },
    "compound": {
        "description": (
            "Position of the icon relative to the text."
        ),
        "warning": "Has no effect when no image is set.",
    },
    "preserve_aspect": {
        "description": (
            "Lock the icon's height to its native aspect ratio. "
            "Height becomes derived from width."
        ),
        "warning": "Has no effect when no image is set.",
    },
}
