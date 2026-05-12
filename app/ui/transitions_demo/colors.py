"""Color + scalar interpolation helpers used by demo tweens.

``lerp`` works on numbers; ``lerp_color_hsl`` blends two hex colors
through HSL space so hue transitions stay visually smooth (the naive
RGB blend dips through gray for opposite hues).
"""

from __future__ import annotations

import colorsys


def lerp(a, b, t):
    return a + (b - a) * t


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(
        *[max(0, min(255, int(c))) for c in rgb]
    )


def lerp_color_hsl(c1, c2, t):
    r1, g1, b1 = (v / 255 for v in hex_to_rgb(c1))
    r2, g2, b2 = (v / 255 for v in hex_to_rgb(c2))
    h1, l1, s1 = colorsys.rgb_to_hls(r1, g1, b1)
    h2, l2, s2 = colorsys.rgb_to_hls(r2, g2, b2)
    if abs(h2 - h1) > 0.5:
        if h1 < h2:
            h1 += 1
        else:
            h2 += 1
    h = lerp(h1, h2, t) % 1.0
    l = lerp(l1, l2, t)
    s = lerp(s1, s2, t)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return rgb_to_hex((r * 255, g * 255, b * 255))
