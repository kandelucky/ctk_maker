"""CircularProgress widget descriptor.

A custom (non-CTk) widget — pure tk.Canvas with arc draws for the
ring and an optional centered text. The runtime class lives at
``app/widgets/runtime/circular_progress.py`` so the exporter can
inline its source verbatim into generated `.py` files; the builder
canvas imports it directly for live rendering.

Groups shown in the Properties panel, in order:

    Geometry     — x/y, square width/height
    Ring         — track thickness
    Progress     — initial percent (0–100)
    Main Colors  — track + progress fill
    Text         — optional centered % readout (format, font, color)
"""
from app.widgets.base import WidgetDescriptor
from app.widgets.runtime.circular_progress import CircularProgress

# Constructor kwargs the runtime class accepts. Keep in sync with
# ``CircularProgress.__init__``.
_RUNTIME_KWARGS = {
    "width", "height",
    "fg_color", "progress_color",
    "thickness", "initial_percent",
    "show_text", "text_format",
    "text_color", "font_size", "font_bold",
}


class CircularProgressDescriptor(WidgetDescriptor):
    type_name = "CircularProgress"
    # No CTk class. The exporter inlines the runtime source instead
    # of emitting `ctk.CircularProgress(...)`.
    ctk_class_name = "CircularProgress"
    is_ctk_class = False
    display_name = "Circular Progress"
    is_container = False
    prefers_fill_in_layout = False
    image_inline_kwarg = False
    # x / y are placement, never CTk constructor kwargs — without
    # this filter the exporter pipes them into the call and the
    # generated `.py` raises ``TypeError: unexpected keyword 'x'``.
    _NODE_ONLY_KEYS = {"x", "y"}

    default_properties = {
        # Geometry — square default; user can break the square in
        # the Inspector by editing W or H independently.
        "x": 120,
        "y": 120,
        "width": 120,
        "height": 120,
        # Ring
        "thickness": 12,
        # Progress
        "initial_percent": 50,
        # Main colors (CTk defaults — match CTkProgressBar)
        "fg_color": "#4a4d50",
        "progress_color": "#6366f1",
        # Text
        "show_text": True,
        "text_format": "{percent}%",
        "text_color": "#ffffff",
        "font_size": 18,
        "font_bold": True,
    }

    property_schema = [
        # --- Geometry ----------------------------------------------------
        {"name": "x", "type": "number", "label": "X",
         "group": "Geometry", "pair": "pos", "row_label": "Position"},
        {"name": "y", "type": "number", "label": "Y",
         "group": "Geometry", "pair": "pos"},
        {"name": "width", "type": "number", "label": "W",
         "group": "Geometry", "pair": "size", "row_label": "Size",
         "min": 40, "max": 1000},
        {"name": "height", "type": "number", "label": "H",
         "group": "Geometry", "pair": "size", "min": 40, "max": 1000},

        # --- Ring --------------------------------------------------------
        {"name": "thickness", "type": "number", "label": "",
         "group": "Ring", "row_label": "Thickness",
         "min": 1, "max": 60},

        # --- Progress ----------------------------------------------------
        {"name": "initial_percent", "type": "number", "label": "",
         "group": "Progress", "row_label": "Percent",
         "min": 0, "max": 100},

        # --- Main Colors -------------------------------------------------
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Track"},
        {"name": "progress_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Progress"},

        # --- Text --------------------------------------------------------
        {"name": "show_text", "type": "boolean", "label": "",
         "group": "Text", "row_label": "Show"},
        {"name": "text_format", "type": "multiline", "label": "",
         "group": "Text", "row_label": "Format",
         "disabled_when": lambda p: not p.get("show_text")},
        {"name": "text_color", "type": "color", "label": "",
         "group": "Text", "row_label": "Color",
         "disabled_when": lambda p: not p.get("show_text")},
        {"name": "font_size", "type": "number", "label": "",
         "group": "Text", "row_label": "Size",
         "min": 8, "max": 72,
         "disabled_when": lambda p: not p.get("show_text")},
        {"name": "font_bold", "type": "boolean", "label": "",
         "group": "Text", "row_label": "Bold",
         "disabled_when": lambda p: not p.get("show_text")},
    ]

    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        return {
            k: v for k, v in properties.items()
            if k in _RUNTIME_KWARGS
        }

    @classmethod
    def create_widget(cls, master, properties: dict, init_kwargs=None):
        kwargs = cls.transform_properties(properties)
        if init_kwargs:
            kwargs.update(init_kwargs)
        return CircularProgress(master, **kwargs)
