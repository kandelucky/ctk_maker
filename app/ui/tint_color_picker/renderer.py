"""PIL-based gradient image generation for ctk-color-picker.

`GradientRenderer` is a stateless helper that produces the
saturation/value square, hue strip, HSL lightness strip, and tint
palette shown in the color picker dialog.
"""
import colorsys

from PIL import Image

from .state import HsvState


class GradientRenderer:
    """Stateless helpers that produce PIL images for the picker gradients.

    All methods return a freshly-built PIL `Image` in RGB mode so callers
    can wrap them in `ImageTk.PhotoImage` and place them on a Canvas.
    """

    @staticmethod
    def sv_square(hue: float, width: int, height: int,
                  render_width: int, render_height: int) -> Image.Image:
        """Saturation × Value square at fixed hue.

        Rendered at `render_width × render_height` in HSV mode, converted
        to RGB, and bilinear-resized to `width × height` — about 2× faster
        than rendering at full resolution with no visible quality loss.
        """
        h_byte = min(255, max(0, int(hue * 255)))
        data = bytearray(render_width * render_height * 3)
        idx = 0
        for y in range(render_height):
            v_byte = int(255 * (1 - y / (render_height - 1)))
            for x in range(render_width):
                s_byte = int(255 * x / (render_width - 1))
                data[idx] = h_byte
                data[idx + 1] = s_byte
                data[idx + 2] = v_byte
                idx += 3
        img = Image.frombytes("HSV", (render_width, render_height), bytes(data))
        img = img.convert("RGB")
        return img.resize((width, height), Image.BILINEAR)

    @staticmethod
    def hue_strip(width: int, height: int) -> Image.Image:
        """Full-spectrum hue slider — one row generated then tiled vertically."""
        row = bytearray()
        for x in range(width):
            h_byte = min(255, int(255 * x / (width - 1)))
            row.extend([h_byte, 255, 255])
        data = bytes(row) * height
        img = Image.frombytes("HSV", (width, height), data)
        return img.convert("RGB")

    @staticmethod
    def lightness_strip(state: HsvState, width: int, height: int) -> Image.Image:
        """HSL lightness slider for the current hue + HSL saturation.

        Goes from pure black at x=0 to pure white at x=width-1, passing
        through the fully-saturated current color at x=width/2.
        """
        h_hls, _, s_hls = state.to_hls()
        row = bytearray()
        for x in range(width):
            l = x / (width - 1)
            rr, gg, bb = colorsys.hls_to_rgb(h_hls, l, s_hls)
            row.extend([round(rr * 255), round(gg * 255), round(bb * 255)])
        data = bytes(row) * height
        return Image.frombytes("RGB", (width, height), data)

    @staticmethod
    def tint_colors(state: HsvState, count: int,
                    range_width: float = 0.5) -> list[str]:
        """Compute `count` hex colors around the current HSL lightness.

        The returned list covers `range_width` of lightness centered on
        the current color, clamped and shifted so it always fits in 0..1.
        Index 0 is the lightest, index count-1 is the darkest.
        """
        h_hls, current_l, s_hls = state.to_hls()

        half = range_width / 2
        l_min = current_l - half
        l_max = current_l + half
        if l_max > 1.0:
            l_min -= (l_max - 1.0)
            l_max = 1.0
        if l_min < 0.0:
            l_max += (0.0 - l_min)
            l_min = 0.0
        l_min = max(0.0, l_min)
        l_max = min(1.0, l_max)

        colors = []
        for i in range(count):
            l = l_max - (l_max - l_min) * i / (count - 1)
            rr, gg, bb = colorsys.hls_to_rgb(h_hls, l, s_hls)
            colors.append("#{:02x}{:02x}{:02x}".format(
                round(rr * 255), round(gg * 255), round(bb * 255)))
        return colors
