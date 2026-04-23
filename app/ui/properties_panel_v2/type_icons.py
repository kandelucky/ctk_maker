"""Widget type → icon name lookup for the Properties panel v2 header."""

from __future__ import annotations


_TYPE_ICON_NAMES = {
    "CTkButton": "square-dot",
    "CTkLabel": "type",
    "CTkFrame": "frame",
    "CTkCheckBox": "square-check",
    "CTkRadioButton": "circle-dot",
    "CTkSwitch": "toggle-left",
    "CTkEntry": "text-cursor-input",
    "CTkTextbox": "file-text",
    "CTkComboBox": "chevrons-up-down",
    "CTkOptionMenu": "menu",
    "CTkSlider": "sliders-horizontal",
    "CTkSegmentedButton": "panel-left-right-dashed",
    "CTkScrollableFrame": "scroll-text",
    "CTkTabview": "layout-panel-top",
    "CTkProgressBar": "loader",
    "Image": "image",
}


def icon_for_type(type_name: str) -> str | None:
    return _TYPE_ICON_NAMES.get(type_name)
