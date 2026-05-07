"""CTkLabel widget descriptor.

Declares the full schema the Properties panel uses to render editors
for a CTkLabel, plus the bridge that converts the builder's property
dict into the kwargs CTkLabel actually accepts.

Groups shown in the Properties panel, in order
(Content → Layout → Visual → Behavior):

    Text            — label, font style, line align, wraplength, text colors
    Icon            — image picker, size, tint, compound, preserve aspect
    Geometry        — x/y, width/height
    Alignment       — content anchor + inner padding
    Rectangle       — corner radius
    Main Colors     — background
    Interaction     — enabled flag, cursor, takefocus
"""
import customtkinter as ctk

from app.core.logger import log_error
from app.widgets.base import WidgetDescriptor


class CTkLabelDescriptor(WidgetDescriptor):
    type_name = "CTkLabel"
    display_name = "Label"
    prefers_fill_in_layout = True

    default_properties = {
        # Geometry
        "x": 120,
        "y": 120,
        "width": 100,
        "height": 28,
        # Rectangle
        "corner_radius": 0,
        # Alignment — inner Tk Label padding (advances the text +
        # image block away from the widget edges). Note: italic /
        # script fonts may clip their slant tail at padx=0; bump
        # padx ≥ 4 to reserve room.
        "padx": 0,
        "pady": 0,
        # Interaction
        "label_enabled": True,
        "cursor": "",
        "takefocus": False,
        # Main colors
        "fg_color": "transparent",
        "bg_color": "transparent",
        # Text content + style
        "text": "CTkLabel",
        "font_family": None,
        "font_size": 13,
        "font_autofit": False,
        "font_bold": False,
        "font_italic": False,
        "font_underline": False,
        "font_overstrike": False,
        "font_wrap": True,
        "anchor": "center",
        "justify": "center",
        "wraplength": 0,
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

        {"name": "justify", "type": "justify", "label": "",
         "group": "Text", "row_label": "Line Align"},

        {"name": "font_wrap", "type": "boolean", "label": "",
         "group": "Text", "subgroup": "Wrap", "row_label": "Enabled"},
        {"name": "wraplength", "type": "number", "label": "",
         "group": "Text", "subgroup": "Wrap", "row_label": "Length",
         "min": 0, "max": 2000,
         "disabled_when": lambda p: not p.get("font_wrap")},

        {"name": "text_color", "type": "color", "label": "",
         "group": "Text", "row_label": "Normal Text Color"},
        {"name": "text_color_disabled", "type": "color", "label": "",
         "group": "Text", "row_label": "Disabled Text Color"},

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
         "group": "Geometry", "pair": "size", "min": 10, "max": 2000},

        # --- Alignment ---------------------------------------------------
        # `anchor` positions the entire content block (text + icon) within
        # the widget — not text-only — so it lives in its own group.
        {"name": "anchor", "type": "anchor", "label": "",
         "group": "Alignment", "row_label": "Anchor"},
        {"name": "padx", "type": "number", "label": "X",
         "group": "Alignment",
         "pair": "pad", "row_label": "Padding",
         "min": 0, "max": 50},
        {"name": "pady", "type": "number", "label": "Y",
         "group": "Alignment",
         "pair": "pad",
         "min": 0, "max": 50},

        # --- Rectangle ---------------------------------------------------
        {"name": "corner_radius", "type": "number", "label": "",
         "group": "Rectangle",
         "row_label": "Corner Radius", "min": 0,
         "max": lambda p: max(
             0,
             min(int(p.get("width", 0)), int(p.get("height", 0))) // 2,
         )},

        # --- Main Colors -------------------------------------------------
        # CTk semantics: `fg_color` = the label's filled body (the
        # "Foreground" of the widget on its parent), `bg_color` = the
        # parent-derived antialiasing layer behind the rounded corners
        # (the "Background"). Default both to transparent — fg picks up
        # nothing, bg auto-derives from parent. ✕ on either reverts to
        # transparent. Bumping bg_color away from transparent is rare:
        # only useful when the parent is a gradient / image where CTk's
        # auto-detect can't read a single solid color.
        {"name": "fg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Foreground",
         "clearable": True, "clear_value": "transparent"},
        {"name": "bg_color", "type": "color", "label": "",
         "group": "Main Colors", "row_label": "Background",
         "clearable": True, "clear_value": "transparent"},

        # --- Interaction -------------------------------------------------
        {"name": "label_enabled", "type": "boolean", "label": "",
         "group": "Interaction", "row_label": "Enabled"},
        {"name": "cursor", "type": "cursor", "label": "",
         "group": "Interaction", "row_label": "Cursor"},
        {"name": "takefocus", "type": "boolean", "label": "",
         "group": "Interaction", "row_label": "Take Focus"},
    ]

    derived_triggers = {
        "text", "width", "height", "font_bold",
        "font_autofit", "font_wrap",
    }

    _NODE_ONLY_KEYS = {
        "x", "y",
        "label_enabled",
        "image_width", "image_height",
        "preserve_aspect",
        "image_color", "image_color_disabled",
    }
    _FONT_KEYS = {
        "font_family",
        "font_size", "font_bold", "font_italic",
        "font_underline", "font_overstrike", "font_autofit",
        "font_wrap",
    }
    # Internal descriptor state persisted to JSON for runtime continuity
    # (e.g. autofit OFF→ON→OFF restore) but never passed to CTk kwargs.
    _SHADOW_KEYS = {"_font_size_pre_autofit"}

    # ==================================================================
    # Derived properties:
    #   - Autofit (Auto Fit)        — derives font_size from box + text
    # ==================================================================
    @classmethod
    def compute_derived(cls, properties: dict) -> dict:
        result: dict = {}

        # --- Autofit font size ----------------------------------------
        prev_stash = properties.get("_font_size_pre_autofit")
        if not properties.get("font_autofit"):
            # Toggling Auto Fit off — restore the size we stashed when
            # it turned on, so the user gets back their pre-autofit
            # value instead of the autofit-derived one.
            if prev_stash is not None:
                result["font_size"] = prev_stash
                result["_font_size_pre_autofit"] = None
        else:
            text = properties.get("text") or ""
            if text:
                try:
                    width = int(properties.get("width", 100))
                    height = int(properties.get("height", 28))
                    bold = bool(properties.get("font_bold", False))
                    wrap = bool(properties.get("font_wrap", False))
                    new_size = cls._compute_autofit_size(
                        text, width, height, bold, wrap,
                    )
                    if new_size > 0:
                        # Stash the user's size on the OFF→ON transition
                        # only. While autofit stays on, font_size already
                        # holds a derived value, so re-stashing on
                        # subsequent triggers (resize, bold toggle) would
                        # clobber the original.
                        if prev_stash is None:
                            result["_font_size_pre_autofit"] = (
                                properties.get("font_size", 13)
                            )
                        result["font_size"] = new_size
                except (ValueError, TypeError):
                    pass

        return result

    @classmethod
    def _compute_autofit_size(cls, text: str, width: int, height: int,
                              bold: bool, wrap: bool = False) -> int:
        import tkinter.font as tkfont
        avail_w = max(10, width - 12)
        avail_h = max(10, height - 4)
        weight = "bold" if bold else "normal"
        lo, hi = 6, 96
        best = 6
        while lo <= hi:
            mid = (lo + hi) // 2
            try:
                f = tkfont.Font(size=mid, weight=weight)
                line_h = f.metrics("linespace")
                if wrap:
                    lines = cls._wrap_lines(f, text, avail_w)
                    tw = max((f.measure(L) for L in lines), default=0)
                    th = line_h * len(lines)
                else:
                    tw = f.measure(text)
                    th = line_h
            except Exception:
                return 13
            if tw <= avail_w and th <= avail_h:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    @staticmethod
    def _wrap_lines(font, text: str, max_w: int) -> list[str]:
        # Greedy word-wrap mimicking Tk's wraplength behavior. Used by
        # autofit to estimate how many lines the text will occupy at a
        # given font size.
        lines: list[str] = []
        for paragraph in text.split("\n"):
            if not paragraph:
                lines.append("")
                continue
            words = paragraph.split(" ")
            cur = ""
            for w in words:
                trial = w if not cur else cur + " " + w
                if font.measure(trial) <= max_w:
                    cur = trial
                else:
                    if cur:
                        lines.append(cur)
                    cur = w
            if cur:
                lines.append(cur)
        return lines or [""]

    # ==================================================================
    # Builder → CTkLabel kwargs
    # ==================================================================
    @classmethod
    def export_kwarg_overrides(cls, properties: dict) -> dict:
        overrides: dict = {}
        # Mirror transform_properties' "wrap on + length 0 → derive from
        # width" rule so exported code wraps the same way the editor does.
        if properties.get("font_wrap") and not properties.get("wraplength"):
            try:
                w = int(properties.get("width", 100))
            except (ValueError, TypeError):
                w = 100
            overrides["wraplength"] = max(1, w - 8)
        # Mirror transform_properties' manual disabled-text swap. We
        # deliberately don't emit ``state="disabled"`` for labels (Tk
        # Label's native disabled rendering paints a stipple wash over
        # the image); instead we pre-substitute ``text_color`` with
        # ``text_color_disabled`` so the exported file shows the same
        # disabled appearance the editor renders.
        if not properties.get("label_enabled", True):
            disabled_color = properties.get("text_color_disabled")
            if disabled_color:
                overrides["text_color"] = disabled_color
        return overrides

    @classmethod
    def transform_properties(cls, properties: dict) -> dict:
        result = {
            k: v for k, v in properties.items()
            if k not in cls._NODE_ONLY_KEYS
            and k not in cls._FONT_KEYS
            and k not in cls._SHADOW_KEYS
        }

        # Manual disabled visuals — we do NOT pass `state="disabled"` to
        # the inner Tk Label because Windows-Tk paints a native white
        # "wash" over `image=` in disabled mode. Instead, when the label
        # is disabled we just swap text_color (and let `_build_image`
        # use image_color_disabled if the user set one). Image stays
        # untouched if no disabled tint is configured.
        if not properties.get("label_enabled", True):
            disabled_color = properties.get("text_color_disabled")
            if disabled_color:
                result["text_color"] = disabled_color

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
            log_error("CTkLabelDescriptor.transform_properties font")

        # Wrap on + length 0 → fall back to widget width so Tk actually
        # wraps. Tk's native wraplength=0 means "no wrap", which clashes
        # with the user-facing "Wrap > Enabled" checkbox semantics.
        if properties.get("font_wrap") and not properties.get("wraplength"):
            try:
                w = int(properties.get("width", 100))
            except (ValueError, TypeError):
                w = 100
            result["wraplength"] = max(1, w - 8)

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
            native_w, native_h = img.size
            # ``transparent`` is the colour-editor's "cleared" sentinel
            # — treat it as "no tint" alongside ``None`` so a cleared
            # disabled colour falls through to the normal tint instead
            # of being passed to ``_tint_image`` (which would otherwise
            # silently no-op via the ValueError catch but skip a valid
            # ``image_color`` fallback).
            def _active(c):
                return c if c and c != "transparent" else None
            if not properties.get("label_enabled", True):
                color = (
                    _active(properties.get("image_color_disabled"))
                    or _active(properties.get("image_color"))
                )
            else:
                color = _active(properties.get("image_color"))
            if color:
                img = cls._tint_image(img, color)
            iw = int(properties.get("image_width", 20) or 20)
            ih = int(properties.get("image_height", 20) or 20)
            # preserve_aspect=True → contain-fit the native image inside
            # the (image_width, image_height) box: scale so the smaller
            # side dictates and the longer axis leaves padding around the
            # icon (CTkLabel's compound + image_anchor handle placement).
            # Render-time so saved-state mismatches and live edits both
            # render correctly without needing an OFF→ON toggle.
            if (properties.get("preserve_aspect")
                    and native_w > 0 and native_h > 0):
                scale = min(iw / native_w, ih / native_h)
                iw = max(1, int(round(native_w * scale)))
                ih = max(1, int(round(native_h * scale)))
            return ctk.CTkImage(
                light_image=img, dark_image=img, size=(iw, ih),
            )
        except Exception:
            log_error("CTkLabelDescriptor.transform_properties image")
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
        widget = ctk.CTkLabel(master, **kwargs)
        return widget
