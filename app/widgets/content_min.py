"""Content-minimum size per widget — flex-shrink floor.

Returns the smallest size (px) below which a widget's visible
content (text + icon + per-widget chrome padding) starts to clip.
Used by the ``hbox`` / ``vbox`` rebalance loop to floor the
auto-shrink slot once container width / height drops below the
sum of children's natural sizes — matches CSS flex's
``min-width: max-content`` semantic without touching tk's pack
manager (which has no native min-floor).

Same numbers are baked into the exporter so generated ``.py``
files behave identically on user resize.
"""
from __future__ import annotations

import tkinter.font as tkfont


# Per-widget chrome — text padding, icon-text gap, and an
# absolute floor below which the widget is unrecognisable
# regardless of text content. Numbers chosen by inspection of
# CTk's stock widgets at default sizes; verified manually
# against canvas preview at 100% zoom.
_CHROME: dict[str, dict[str, int]] = {
    "CTkButton":          {"text_pad": 16, "icon_gap": 6, "floor": 32},
    "CTkLabel":           {"text_pad": 8,  "icon_gap": 4, "floor": 16},
    "CTkOptionMenu":      {"text_pad": 36, "icon_gap": 0, "floor": 60},
    "CTkComboBox":        {"text_pad": 36, "icon_gap": 0, "floor": 60},
    "CTkCheckBox":        {"text_pad": 28, "icon_gap": 4, "floor": 28},
    "CTkRadioButton":     {"text_pad": 28, "icon_gap": 4, "floor": 28},
    "CTkSwitch":          {"text_pad": 50, "icon_gap": 4, "floor": 50},
    "CTkSegmentedButton": {"text_pad": 16, "icon_gap": 0, "floor": 60},
    "CTkEntry":           {"text_pad": 16, "icon_gap": 0, "floor": 50},
    "CTkTextbox":         {"text_pad": 16, "icon_gap": 0, "floor": 50},
    "CTkFrame":           {"text_pad": 0,  "icon_gap": 0, "floor": 20},
    "CTkScrollableFrame": {"text_pad": 0,  "icon_gap": 0, "floor": 40},
    "CTkTabview":         {"text_pad": 0,  "icon_gap": 0, "floor": 80},
    "Image":              {"text_pad": 0,  "icon_gap": 0, "floor": 16},
    "Card":               {"text_pad": 0,  "icon_gap": 0, "floor": 80},
    "CircularProgress":   {"text_pad": 0,  "icon_gap": 0, "floor": 32},
}

# Orientation-driven widgets — long axis carries a different
# floor than cross axis (a 16-px-wide vertical slider is fine,
# a 16-px-tall horizontal slider is not).
_ORIENTED: dict[str, dict[str, int]] = {
    "CTkSlider":      {"long": 40, "cross": 16},
    "CTkProgressBar": {"long": 40, "cross": 8},
}

_DEFAULT_CHROME = {"text_pad": 0, "icon_gap": 0, "floor": 20}


def _measure(text: str, size: int, bold: bool) -> int:
    """Pixel width of ``text``. Falls back to a coarse estimate
    if Tk isn't ready (no master root) — happens during unit
    tests where the suite is intentionally Tk-free.
    """
    if not text:
        return 0
    try:
        weight = "bold" if bold else "normal"
        f = tkfont.Font(size=int(size), weight=weight)
        return int(f.measure(str(text)))
    except Exception:
        return len(str(text)) * max(6, int(size) * 6 // 10)


def content_min_axis(node, axis: str) -> int:
    """Min content size (px) for ``node`` along ``axis`` ∈
    ``"width"`` / ``"height"``. Statically derived from the
    node's properties; the only Tk call is ``font.measure()``
    which is cheap and cached.
    """
    if axis not in ("width", "height"):
        return 0
    wtype = getattr(node, "widget_type", "") or ""
    props = getattr(node, "properties", {}) or {}

    oriented = _ORIENTED.get(wtype)
    if oriented is not None:
        orientation = str(props.get("orientation", "horizontal"))
        long_dir = "width" if orientation == "horizontal" else "height"
        return oriented["long"] if axis == long_dir else oriented["cross"]

    chrome = _CHROME.get(wtype, _DEFAULT_CHROME)

    if axis == "height":
        return chrome["floor"]

    text = str(props.get("text", "") or "")
    has_image = bool(props.get("image"))

    text_w = 0
    if text:
        try:
            size = int(props.get("font_size") or 13)
        except (TypeError, ValueError):
            size = 13
        bold = bool(props.get("font_bold"))
        text_w = _measure(text, size, bold)

    icon_w = 0
    if has_image:
        try:
            icon_w = int(props.get("image_width", 20) or 20)
        except (TypeError, ValueError):
            icon_w = 20
        compound = str(props.get("compound", "left"))
        if text and compound in ("left", "right"):
            icon_w += chrome["icon_gap"]
        elif text and compound in ("top", "bottom"):
            # Stacked — wider of the two drives min width.
            icon_w = max(icon_w, text_w)
            text_w = 0

    raw = text_w + icon_w + chrome["text_pad"]
    return max(chrome["floor"], raw)
