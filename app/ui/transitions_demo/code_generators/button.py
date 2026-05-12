"""Generate a paste-anywhere ``attach_press_effect`` snippet.

The button tab is the odd one out — it doesn't go through
``assemble_module`` because the output is wrapped as a callable
(``attach_press_effect(button)``) rather than a one-shot animation
function, so the surrounding template differs.
"""

from __future__ import annotations

from app.ui.transitions_demo.easings import EASING_SOURCE


def generate_button_code(mode: str, easing_name: str, duration: float) -> str:
    if mode == "None":
        return (
            "# No effect selected.\n"
            "# Pick an effect (Grow / Shrink / Rise / Sink / Wobble /\n"
            "# Squish / Flash / Press Down) and click Generate code again."
        )

    easings_needed = sorted({easing_name, "ease_out"})
    easing_funcs = "\n\n\n".join(EASING_SOURCE[n] for n in easings_needed)

    needs_math = (
        easing_name in ("elastic_out", "spring") or mode == "Wobble"
    )
    imports = "import time\n"
    if needs_math:
        imports = "import math\nimport time\n"
    imports += "\nimport customtkinter as ctk"

    helpers = ["def lerp(a, b, t):\n    return a + (b - a) * t"]
    if mode == "Flash":
        helpers.append(
            "def lerp_color(c1, c2, t):\n"
            "    def _rgb(h):\n"
            "        h = h.lstrip('#')\n"
            "        return [int(h[i:i + 2], 16) for i in (0, 2, 4)]\n"
            "    r1, g1, b1 = _rgb(c1)\n"
            "    r2, g2, b2 = _rgb(c2)\n"
            "    r = max(0, min(255, int(r1 + (r2 - r1) * t)))\n"
            "    g = max(0, min(255, int(g1 + (g2 - g1) * t)))\n"
            "    b = max(0, min(255, int(b1 + (b2 - b1) * t)))\n"
            "    return '#{:02x}{:02x}{:02x}'.format(r, g, b)"
        )
    helpers_text = "\n\n\n".join(helpers)

    geometry_note = ""
    if mode in ("Grow", "Shrink", "Squish"):
        if mode == "Grow":
            sw, sh = 1.08, 1.08
        elif mode == "Shrink":
            sw, sh = 0.92, 0.92
        else:
            sw, sh = 1.08, 0.92
        effect_logic = (
            f"    PEAK_W = max(1, int(base_w * {sw}))\n"
            f"    PEAK_H = max(1, int(base_h * {sh}))\n"
            f"\n"
            f"    def to_peak(t):\n"
            f"        button.configure(\n"
            f"            width=int(lerp(base_w, PEAK_W, t)),\n"
            f"            height=int(lerp(base_h, PEAK_H, t)),\n"
            f"        )\n"
            f"\n"
            f"    def to_base(t):\n"
            f"        button.configure(\n"
            f"            width=int(lerp(PEAK_W, base_w, t)),\n"
            f"            height=int(lerp(PEAK_H, base_h, t)),\n"
            f"        )\n"
            f"\n"
            f"    def on_press():\n"
            f"        Tween(\n"
            f"            button, 0.12, ease_out, to_peak,\n"
            f"            on_done=lambda: Tween(\n"
            f"                button, duration, {easing_name}, to_base\n"
            f"            ).start(),\n"
            f"        ).start()\n"
            f"        original()"
        )
    elif mode in ("Rise", "Sink"):
        dy = -6 if mode == "Rise" else 6
        effect_logic = (
            f"    DY = {dy}\n"
            f"\n"
            f"    def on_press():\n"
            f"        info = button.place_info()\n"
            f"        relx = float(info.get('relx') or 0)\n"
            f"        rely = float(info.get('rely') or 0)\n"
            f"        anchor = info.get('anchor', 'center')\n"
            f"\n"
            f"        def to_peak(t):\n"
            f"            button.place_configure(\n"
            f"                relx=relx, rely=rely, anchor=anchor,\n"
            f"                y=lerp(0, DY, t),\n"
            f"            )\n"
            f"\n"
            f"        def to_base(t):\n"
            f"            button.place_configure(\n"
            f"                relx=relx, rely=rely, anchor=anchor,\n"
            f"                y=lerp(DY, 0, t),\n"
            f"            )\n"
            f"\n"
            f"        Tween(\n"
            f"            button, 0.12, ease_out, to_peak,\n"
            f"            on_done=lambda: Tween(\n"
            f"                button, duration, {easing_name}, to_base\n"
            f"            ).start(),\n"
            f"        ).start()\n"
            f"        original()"
        )
        geometry_note = (
            "\n"
            "    NOTE: Button must be placed with .place() (not pack/grid)\n"
            "    so the y offset can be animated.\n    "
        )
    elif mode == "Wobble":
        effect_logic = (
            f"    AMP = 6\n"
            f"    WOBBLE_DURATION = 0.5\n"
            f"\n"
            f"    def on_press():\n"
            f"        info = button.place_info()\n"
            f"        relx = float(info.get('relx') or 0)\n"
            f"        rely = float(info.get('rely') or 0)\n"
            f"        anchor = info.get('anchor', 'center')\n"
            f"\n"
            f"        def step(t):\n"
            f"            offset = math.sin(t * math.pi * 6) * AMP * (1 - t)\n"
            f"            button.place_configure(\n"
            f"                relx=relx, rely=rely, anchor=anchor, x=offset,\n"
            f"            )\n"
            f"\n"
            f"        Tween(\n"
            f"            button, WOBBLE_DURATION, lambda u: u, step,\n"
            f"            on_done=lambda: button.place_configure(\n"
            f"                relx=relx, rely=rely, anchor=anchor, x=0,\n"
            f"            ),\n"
            f"        ).start()\n"
            f"        original()"
        )
        geometry_note = (
            "\n"
            "    NOTE: Button must be placed with .place() (not pack/grid)\n"
            "    so the x offset can be animated.\n    "
        )
    elif mode == "Flash":
        effect_logic = (
            f"    BASE_COLOR = '#0e639c'\n"
            f"    PEAK_COLOR = '#1177bb'\n"
            f"\n"
            f"    def to_peak(t):\n"
            f"        button.configure(\n"
            f"            fg_color=lerp_color(BASE_COLOR, PEAK_COLOR, t)\n"
            f"        )\n"
            f"\n"
            f"    def to_base(t):\n"
            f"        button.configure(\n"
            f"            fg_color=lerp_color(PEAK_COLOR, BASE_COLOR, t)\n"
            f"        )\n"
            f"\n"
            f"    def on_press():\n"
            f"        Tween(\n"
            f"            button, 0.12, ease_out, to_peak,\n"
            f"            on_done=lambda: Tween(\n"
            f"                button, duration, {easing_name}, to_base\n"
            f"            ).start(),\n"
            f"        ).start()\n"
            f"        original()"
        )
    else:  # Press Down
        effect_logic = (
            f"    PEAK_W = max(1, int(base_w * 0.95))\n"
            f"    PEAK_H = max(1, int(base_h * 0.95))\n"
            f"    SINK_Y = 4\n"
            f"\n"
            f"    def on_press():\n"
            f"        info = button.place_info()\n"
            f"        relx = float(info.get('relx') or 0)\n"
            f"        rely = float(info.get('rely') or 0)\n"
            f"        anchor = info.get('anchor', 'center')\n"
            f"\n"
            f"        def to_peak(t):\n"
            f"            button.configure(\n"
            f"                width=int(lerp(base_w, PEAK_W, t)),\n"
            f"                height=int(lerp(base_h, PEAK_H, t)),\n"
            f"            )\n"
            f"            button.place_configure(\n"
            f"                relx=relx, rely=rely, anchor=anchor,\n"
            f"                y=lerp(0, SINK_Y, t),\n"
            f"            )\n"
            f"\n"
            f"        def to_base(t):\n"
            f"            button.configure(\n"
            f"                width=int(lerp(PEAK_W, base_w, t)),\n"
            f"                height=int(lerp(PEAK_H, base_h, t)),\n"
            f"            )\n"
            f"            button.place_configure(\n"
            f"                relx=relx, rely=rely, anchor=anchor,\n"
            f"                y=lerp(SINK_Y, 0, t),\n"
            f"            )\n"
            f"\n"
            f"        Tween(\n"
            f"            button, 0.12, ease_out, to_peak,\n"
            f"            on_done=lambda: Tween(\n"
            f"                button, duration, {easing_name}, to_base\n"
            f"            ).start(),\n"
            f"        ).start()\n"
            f"        original()"
        )
        geometry_note = (
            "\n"
            "    NOTE: Button must be placed with .place() (not pack/grid)\n"
            "    so the y offset can be animated.\n    "
        )

    return (
        f'"""Button press effect — generated by Transitions Demo.\n'
        f"\n"
        f"Settings:\n"
        f"  Effect:   {mode}\n"
        f"  Easing:   {easing_name}\n"
        f"  Duration: {duration}s\n"
        f"\n"
        f"Usage:\n"
        f"  attach_press_effect(my_button, base_w=160, base_h=44)\n"
        f'"""\n'
        f"{imports}\n"
        f"\n"
        f"\n"
        f"# --- easings ---\n"
        f"\n"
        f"{easing_funcs}\n"
        f"\n"
        f"\n"
        f"# --- tween engine ---\n"
        f"\n"
        f"class Tween:\n"
        f"    FRAME_MS = 16\n"
        f"\n"
        f"    def __init__(self, widget, duration, easing, step, on_done=None):\n"
        f"        self.widget = widget\n"
        f"        self.duration = max(duration, 0.001)\n"
        f"        self.easing = easing\n"
        f"        self.step = step\n"
        f"        self.on_done = on_done\n"
        f"        self._start = None\n"
        f"        self._running = False\n"
        f"\n"
        f"    def start(self):\n"
        f"        self._start = time.perf_counter()\n"
        f"        self._running = True\n"
        f"        self._tick()\n"
        f"        return self\n"
        f"\n"
        f"    def _tick(self):\n"
        f"        if not self._running:\n"
        f"            return\n"
        f"        t = min((time.perf_counter() - self._start) / self.duration, 1.0)\n"
        f"        self.step(self.easing(t))\n"
        f"        if t < 1.0:\n"
        f"            self.widget.after(self.FRAME_MS, self._tick)\n"
        f"        else:\n"
        f"            self._running = False\n"
        f"            if self.on_done:\n"
        f"                self.on_done()\n"
        f"\n"
        f"\n"
        f"{helpers_text}\n"
        f"\n"
        f"\n"
        f"# --- attach press effect ---\n"
        f"\n"
        f"def attach_press_effect(button, base_w=160, base_h=44, duration={duration}):\n"
        f'    """Wrap button command with a "{mode}" press animation.{geometry_note}"""\n'
        f"    original = button.cget('command') or (lambda: None)\n"
        f"\n"
        f"{effect_logic}\n"
        f"\n"
        f"    button.configure(command=on_press)\n"
        f"\n"
        f"\n"
        f'if __name__ == "__main__":\n'
        f'    ctk.set_appearance_mode("dark")\n'
        f"    app = ctk.CTk()\n"
        f'    app.geometry("400x200")\n'
        f"    btn = ctk.CTkButton(\n"
        f'        app, text="Press me", width=160, height=44,\n'
        f'        command=lambda: print("clicked"),\n'
        f"    )\n"
        f'    btn.place(relx=0.5, rely=0.5, anchor="center")\n'
        f"    attach_press_effect(btn, base_w=160, base_h=44)\n"
        f"    app.mainloop()\n"
    )
