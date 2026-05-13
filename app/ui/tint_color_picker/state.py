"""HSV color state model for ctk-color-picker.

Defines `HsvState` — a mutable color model backed by HSV floats with
helpers for hex / RGB / HSL round-trips and HSL-lightness editing.
"""
import colorsys
from dataclasses import dataclass


@dataclass
class HsvState:
    """Pure color state stored as HSV (0..1 floats).

    Conversions to and from hex / RGB / HLS are provided. The state is
    mutable — callers directly assign to `hue`, `saturation`, `value` or
    use the helper methods.
    """
    hue: float = 0.0
    saturation: float = 0.0
    value: float = 0.0

    @classmethod
    def from_hex(cls, hex_str: str) -> "HsvState":
        """Create a new state initialized from a `#rrggbb` hex string."""
        state = cls()
        state.load_hex(hex_str)
        return state

    def load_hex(self, hex_str: str) -> bool:
        """Parse a `#rrggbb` hex and overwrite state in-place.

        Accepts the `#` prefix optionally and is case-insensitive.
        Returns True on success, False if the string is invalid — the
        current state is left untouched in that case.
        """
        s = (hex_str or "").strip().lstrip("#")
        if len(s) != 6:
            return False
        try:
            r = int(s[0:2], 16) / 255
            g = int(s[2:4], 16) / 255
            b = int(s[4:6], 16) / 255
        except ValueError:
            return False
        h, sat, val = colorsys.rgb_to_hsv(r, g, b)
        self.hue = h
        self.saturation = sat
        self.value = val
        return True

    def to_hex(self) -> str:
        """Return the current color as a lowercase `#rrggbb` string."""
        r, g, b = self.to_rgb()
        return "#{:02x}{:02x}{:02x}".format(
            round(r * 255), round(g * 255), round(b * 255))

    def to_rgb(self) -> tuple[float, float, float]:
        """Return the current color as `(r, g, b)` floats in 0..1."""
        return colorsys.hsv_to_rgb(self.hue, self.saturation, self.value)

    def to_hls(self) -> tuple[float, float, float]:
        """Return the current color as `(hue, lightness, saturation)` HLS floats."""
        r, g, b = self.to_rgb()
        return colorsys.rgb_to_hls(r, g, b)

    def lightness(self) -> float:
        """Return just the HSL lightness value in 0..1."""
        return self.to_hls()[1]

    def set_lightness(self, new_l: float) -> None:
        """Change HSL lightness while preserving hue and HSL saturation.

        The HSV state is rewritten via RGB to keep a consistent round-trip.
        """
        h_hls, _, s_hls = self.to_hls()
        r, g, b = colorsys.hls_to_rgb(h_hls, new_l, s_hls)
        new_h, new_s, new_v = colorsys.rgb_to_hsv(r, g, b)
        self.hue = new_h
        self.saturation = new_s
        self.value = new_v
