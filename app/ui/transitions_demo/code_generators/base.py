"""Shared building blocks for "Generate code" output.

``HSL_HELPER`` and ``TWEEN_BLOCK`` are emitted verbatim into produced
snippets so the user pastes a single self-contained module — no
import back into CTkMaker. ``assemble_module`` stitches the per-tab
animation body together with imports / easings / helpers / Tween
into one valid ``.py`` source string.
"""

from __future__ import annotations

from app.ui.transitions_demo.easings import EASING_SOURCE


HSL_HELPER = (
    "def hex_to_rgb(h):\n"
    "    h = h.lstrip('#')\n"
    "    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))\n"
    "\n"
    "\n"
    "def rgb_to_hex(rgb):\n"
    "    return '#{:02x}{:02x}{:02x}'.format(\n"
    "        *[max(0, min(255, int(c))) for c in rgb]\n"
    "    )\n"
    "\n"
    "\n"
    "def lerp_color_hsl(c1, c2, t):\n"
    "    r1, g1, b1 = (v / 255 for v in hex_to_rgb(c1))\n"
    "    r2, g2, b2 = (v / 255 for v in hex_to_rgb(c2))\n"
    "    h1, l1, s1 = colorsys.rgb_to_hls(r1, g1, b1)\n"
    "    h2, l2, s2 = colorsys.rgb_to_hls(r2, g2, b2)\n"
    "    if abs(h2 - h1) > 0.5:\n"
    "        if h1 < h2:\n"
    "            h1 += 1\n"
    "        else:\n"
    "            h2 += 1\n"
    "    h = lerp(h1, h2, t) % 1.0\n"
    "    l = lerp(l1, l2, t)\n"
    "    s = lerp(s1, s2, t)\n"
    "    r, g, b = colorsys.hls_to_rgb(h, l, s)\n"
    "    return rgb_to_hex((r * 255, g * 255, b * 255))"
)


TWEEN_BLOCK = (
    "class Tween:\n"
    "    FRAME_MS = 16\n"
    "\n"
    "    def __init__(self, widget, duration, easing, step, on_done=None):\n"
    "        self.widget = widget\n"
    "        self.duration = max(duration, 0.001)\n"
    "        self.easing = easing\n"
    "        self.step = step\n"
    "        self.on_done = on_done\n"
    "        self._start = None\n"
    "        self._running = False\n"
    "\n"
    "    def start(self):\n"
    "        self._start = time.perf_counter()\n"
    "        self._running = True\n"
    "        self._tick()\n"
    "        return self\n"
    "\n"
    "    def _tick(self):\n"
    "        if not self._running:\n"
    "            return\n"
    "        t = min(\n"
    "            (time.perf_counter() - self._start) / self.duration, 1.0\n"
    "        )\n"
    "        self.step(self.easing(t))\n"
    "        if t < 1.0:\n"
    "            self.widget.after(self.FRAME_MS, self._tick)\n"
    "        else:\n"
    "            self._running = False\n"
    "            if self.on_done:\n"
    "                self.on_done()"
)


def assemble_module(
    title, settings, body, main_block,
    easings_needed, needs_math=False, needs_colorsys=False,
    extra_helpers=None,
):
    """Build a self-contained Python module string.

    ``body`` is the source for the main animation function(s).
    ``main_block`` is the source for the ``if __name__ == '__main__':``
    demo body (already indented 4 spaces).
    """
    imports = ["import time"]
    if needs_math:
        imports.insert(0, "import math")
    if needs_colorsys:
        imports.insert(0, "import colorsys")
    imports_text = "\n".join(imports) + "\n\nimport customtkinter as ctk"

    easings_text = "\n\n\n".join(
        EASING_SOURCE[n] for n in sorted(set(easings_needed))
    )

    helpers = ["def lerp(a, b, t):\n    return a + (b - a) * t"]
    if extra_helpers:
        helpers.extend(extra_helpers)
    helpers_text = "\n\n\n".join(helpers)

    settings_text = "\n".join(f"  {k}: {v}" for k, v in settings.items())

    return (
        f'"""{title}\n'
        f"\n"
        f"Settings:\n"
        f"{settings_text}\n"
        f'"""\n'
        f"{imports_text}\n"
        f"\n"
        f"\n"
        f"# --- easings ---\n"
        f"\n"
        f"{easings_text}\n"
        f"\n"
        f"\n"
        f"# --- helpers ---\n"
        f"\n"
        f"{helpers_text}\n"
        f"\n"
        f"\n"
        f"# --- tween engine ---\n"
        f"\n"
        f"{TWEEN_BLOCK}\n"
        f"\n"
        f"\n"
        f"# --- animation ---\n"
        f"\n"
        f"{body}\n"
        f"\n"
        f"\n"
        f'if __name__ == "__main__":\n'
        f"{main_block}\n"
    )
