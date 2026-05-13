"""Configuration dataclasses for ctk-color-picker.

`PickerConfig` controls sizes and counts, `PickerTheme` controls colors,
and `EyedropConfig` tunes the screen-eyedropper feature. All three are
plain dataclasses — override individual fields to customize.
"""
from dataclasses import dataclass, field


@dataclass
class EyedropConfig:
    """Tuning knobs for the screen-eyedropper feature."""
    preview_size: int = 32
    preview_offset: int = 14

    overlay_alpha: float = 0.01
    withdraw_delay_ms: int = 80

    hint_visible_ms: int = 2000
    fade_step_ms: int = 40
    fade_step_alpha: float = 0.1

    hint_y: int = 40
    hint_padx: int = 18
    hint_pady: int = 9
    hint_bg: str = "#222222"
    hint_fg: str = "#ffffff"
    hint_text: str = "Click anywhere to pick a color   ·   Esc to cancel"

    transparent_key: str = "#ff00fe"


@dataclass
class PickerConfig:
    """Sizes and counts for the color picker layout.

    All size values are in *logical* pixels — the dialog applies DPI
    scaling automatically. Defaults reproduce the current bundled look.
    """
    sv_size: tuple[int, int] = (260, 185)
    sv_render_size: tuple[int, int] = (130, 92)

    hue_size: tuple[int, int] = (260, 18)
    light_size: tuple[int, int] = (260, 18)

    compare_swatch_size: tuple[int, int] = (72, 24)

    saved_rows: int = 2
    saved_per_row: int = 10
    saved_btn_size: int = 18

    tint_count: int = 13
    tint_btn_size: tuple[int, int] = (20, 16)
    tint_range_width: float = 0.5

    window_padding: tuple[int, int] = (4, 12)

    eyedrop: EyedropConfig = field(default_factory=EyedropConfig)


@dataclass
class PickerTheme:
    """Color palette used by the picker widgets.

    Override any of these to re-skin the dialog without touching source.
    """
    canvas_bg: str = "#1e1e1e"
    canvas_border: str = "#666666"

    label_color: str = "#888888"
    header_color: str = "#888888"

    swatch_border: str = "#666666"
    highlight_border: str = "#ffffff"

    placeholder_fg: str = "#2a2a2a"
    placeholder_border: str = "#3a3a3a"

    plus_button_fg: str = "#3a3a3a"
    plus_button_hover: str = "#4a4a4a"
