"""Tools → Transitions Demo — animation/easing playground.

Bonus window: pick an easing, watch demo animations on a target card,
then generate a paste-anywhere snippet for a button press effect.
"""
from __future__ import annotations

import colorsys
import math
import time
import tkinter as tk
import tkinter.font as tkfont

import customtkinter as ctk

from app.ui.managed_window import ManagedToplevel
from app.ui.style import (
    BG, BORDER, BUTTON_FONT_SIZE, BUTTON_HEIGHT, BUTTON_RADIUS,
    CONTENT_PADX, CONTENT_PADY, EMPTY_FG, PANEL_BG, PRIMARY_BG,
    PRIMARY_HOVER, SECONDARY_BG, SECONDARY_HOVER, TREE_FG,
    primary_button, secondary_button,
)
from app.ui.system_fonts import ui_font


# ---- easing ---------------------------------------------------------------

def linear(t): return t
def ease_in(t): return t * t * t
def ease_out(t): return 1 - (1 - t) ** 3


def ease_in_out(t):
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_out_quint(t):
    return 1 - (1 - t) ** 5


def back_out(t):
    if t >= 1:
        return 1.0
    s = 1.70158
    u = t - 1
    return 1 + (s + 1) * u ** 3 + s * u ** 2


def elastic_out(t):
    if t == 0 or t == 1:
        return t
    p = 0.35
    return math.pow(2, -10 * t) * math.sin((t - p / 4) * (2 * math.pi) / p) + 1


def spring(t):
    if t == 0 or t == 1:
        return t
    return 1 - math.exp(-6 * t) * math.cos(4.5 * t)


def bounce_out(t):
    n1 = 7.5625
    d1 = 2.75
    if t < 1 / d1:
        return n1 * t * t
    if t < 2 / d1:
        u = t - 1.5 / d1
        return n1 * u * u + 0.75
    if t < 2.5 / d1:
        u = t - 2.25 / d1
        return n1 * u * u + 0.9375
    u = t - 2.625 / d1
    return n1 * u * u + 0.984375


EASINGS = {
    "linear": linear,
    "ease_in": ease_in,
    "ease_out": ease_out,
    "ease_in_out": ease_in_out,
    "ease_out_quint": ease_out_quint,
    "back_out": back_out,
    "elastic_out": elastic_out,
    "spring": spring,
    "bounce_out": bounce_out,
}


EASING_SOURCE = {
    "linear": "def linear(t):\n    return t",
    "ease_in": "def ease_in(t):\n    return t * t * t",
    "ease_out": "def ease_out(t):\n    return 1 - (1 - t) ** 3",
    "ease_in_out": (
        "def ease_in_out(t):\n"
        "    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2"
    ),
    "ease_out_quint": "def ease_out_quint(t):\n    return 1 - (1 - t) ** 5",
    "back_out": (
        "def back_out(t):\n"
        "    if t >= 1:\n"
        "        return 1.0\n"
        "    s = 1.70158\n"
        "    u = t - 1\n"
        "    return 1 + (s + 1) * u ** 3 + s * u ** 2"
    ),
    "elastic_out": (
        "def elastic_out(t):\n"
        "    if t == 0 or t == 1:\n"
        "        return t\n"
        "    p = 0.35\n"
        "    return (\n"
        "        math.pow(2, -10 * t) * math.sin((t - p / 4) * (2 * math.pi) / p)\n"
        "        + 1\n"
        "    )"
    ),
    "spring": (
        "def spring(t):\n"
        "    if t == 0 or t == 1:\n"
        "        return t\n"
        "    return 1 - math.exp(-6 * t) * math.cos(4.5 * t)"
    ),
    "bounce_out": (
        "def bounce_out(t):\n"
        "    n1 = 7.5625\n"
        "    d1 = 2.75\n"
        "    if t < 1 / d1:\n"
        "        return n1 * t * t\n"
        "    if t < 2 / d1:\n"
        "        u = t - 1.5 / d1\n"
        "        return n1 * u * u + 0.75\n"
        "    if t < 2.5 / d1:\n"
        "        u = t - 2.25 / d1\n"
        "        return n1 * u * u + 0.9375\n"
        "    u = t - 2.625 / d1\n"
        "    return n1 * u * u + 0.984375"
    ),
}


# ---- tween engine ---------------------------------------------------------

class Tween:
    FRAME_MS = 16

    def __init__(self, widget, duration, easing, step, on_done=None):
        self.widget = widget
        self.duration = max(duration, 0.001)
        self.easing = easing
        self.step = step
        self.on_done = on_done
        self._start = None
        self._running = False

    def start(self):
        self._start = time.perf_counter()
        self._running = True
        self._tick()
        return self

    def stop(self):
        self._running = False

    def _tick(self):
        if not self._running:
            return
        try:
            t = min((time.perf_counter() - self._start) / self.duration, 1.0)
            self.step(self.easing(t))
        except Exception as e:
            print(f"[tween] step error: {e}")
            self._running = False
            return
        if t < 1.0:
            self.widget.after(self.FRAME_MS, self._tick)
        else:
            self._running = False
            if self.on_done:
                self.on_done()


# ---- value helpers --------------------------------------------------------

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


# ---- window ---------------------------------------------------------------

CARD_COLOR = "#1f6aa5"
CARD_DEFAULT_W = 140
CARD_DEFAULT_H = 110
SAMPLE_BTN_W = 150
SAMPLE_BTN_H = 36
POPUP_TARGET = (320, 180, 920, 320)


class TransitionsDemoWindow(ManagedToplevel):
    window_key = "transitions_demo_v2"
    window_title = "Transitions Demo"
    default_size = (760, 380)
    min_size = (600, 360)
    fg_color = BG
    panel_padding = (0, 0)

    def build_content(self) -> ctk.CTkFrame:
        container = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)

        self.btn_effect_var = ctk.StringVar(value="Grow")
        self.btn_hover_var = ctk.StringVar(value="None")
        self.easing_var = ctk.StringVar(value="back_out")
        self.duration_var = ctk.StringVar(value="0.7")
        self.toast_position_var = ctk.StringVar(value="Bottom-Right")
        self._toast_stacks = {}
        self._last_selected = ("button", "Grow")
        self._hover_tween = None
        self._shimmer_active = False

        tab_names = ("Button", "Text", "Card", "Loaders", "Popups", "Toasts")
        self._tab_var = ctk.StringVar(value=tab_names[0])

        tab_strip = ctk.CTkFrame(container, fg_color=BG, corner_radius=0)
        tab_strip.pack(fill="x", padx=CONTENT_PADX, pady=(CONTENT_PADY, 0))
        self._tab_buttons = {}
        self._tab_indicators = {}
        for i, name in enumerate(tab_names):
            tab_strip.grid_columnconfigure(i, weight=1)
            btn = ctk.CTkButton(
                tab_strip, text=name,
                command=lambda n=name: self._tab_var.set(n),
                fg_color="transparent", hover_color=PANEL_BG,
                text_color=EMPTY_FG, text_color_disabled=EMPTY_FG,
                height=32, corner_radius=0,
                font=ui_font(BUTTON_FONT_SIZE, "bold"),
            )
            btn.grid(row=0, column=i, sticky="ew")
            indicator = ctk.CTkFrame(
                tab_strip, fg_color=PRIMARY_BG, height=3, corner_radius=0,
            )
            indicator.grid(row=1, column=i, sticky="ew", padx=2)
            self._tab_buttons[name] = btn
            self._tab_indicators[name] = indicator
        # Bottom border separator
        ctk.CTkFrame(
            container, fg_color=BORDER, height=1, corner_radius=0,
        ).pack(fill="x", padx=0, pady=(0, 4))

        content_area = ctk.CTkFrame(container, fg_color=BG, corner_radius=0)
        content_area.pack(fill="both", expand=True)

        self._tab_frames = {}
        for name in tab_names:
            f = ctk.CTkFrame(content_area, fg_color=BG, corner_radius=0)
            self._tab_frames[name] = f

        self._build_common_controls(container)

        self.selection_label = ctk.CTkLabel(
            container, text="", font=("Consolas", 11),
            text_color=TREE_FG, anchor="w",
        )
        self.selection_label.pack(
            side="bottom", fill="x", padx=CONTENT_PADX + 4, pady=(0, 4),
        )

        self._build_card_tab(self._tab_frames["Card"])
        self._build_text_tab(self._tab_frames["Text"])
        self._build_loaders_tab(self._tab_frames["Loaders"])
        self._build_popups_tab(self._tab_frames["Popups"])
        self._build_toasts_tab(self._tab_frames["Toasts"])
        self._build_button_tab(self._tab_frames["Button"])

        def on_tab_change(*_):
            active = self._tab_var.get()
            for name, frame in self._tab_frames.items():
                if name == active:
                    frame.pack(fill="both", expand=True)
                else:
                    frame.pack_forget()
            for name, btn in self._tab_buttons.items():
                if name == active:
                    btn.configure(text_color=TREE_FG)
                    self._tab_indicators[name].grid()
                else:
                    btn.configure(text_color=EMPTY_FG)
                    self._tab_indicators[name].grid_remove()

        self._tab_var.trace_add("write", on_tab_change)
        on_tab_change()

        self.easing_var.trace_add(
            "write", lambda *a: self._redraw_easing_curve()
        )
        for var in (self.easing_var, self.duration_var, self.btn_effect_var):
            var.trace_add("write", lambda *a: self._on_setting_changed())

        self.after(50, self._redraw_easing_curve)
        self._refresh_selection()

        return container

    def _on_setting_changed(self):
        if self._last_selected[0] == "button":
            self._last_selected = ("button", self.btn_effect_var.get())
        self._refresh_selection()

    def _refresh_selection(self):
        category, name = self._last_selected
        self.selection_label.configure(
            text=(
                f"Selected: {name} ({category})    "
                f"Easing={self.easing_var.get()}    "
                f"Duration={self.duration_var.get()}s"
            )
        )

    def _build_stage(self, parent):
        self.stage = ctk.CTkFrame(
            parent, fg_color=PANEL_BG, height=150, corner_radius=BUTTON_RADIUS,
        )
        self.stage.pack(fill="x", padx=CONTENT_PADX, pady=(CONTENT_PADY, 4))
        self.stage.pack_propagate(False)

        ctk.CTkLabel(
            self.stage, text="Click a button to animate the card.",
            font=ui_font(BUTTON_FONT_SIZE), text_color=EMPTY_FG,
        ).place(relx=0.5, rely=0.06, anchor="n")

        self.card = ctk.CTkFrame(
            self.stage,
            width=CARD_DEFAULT_W, height=CARD_DEFAULT_H,
            fg_color=CARD_COLOR, corner_radius=8,
        )
        self.card.place(relx=0.5, rely=0.55, anchor="center")
        ctk.CTkLabel(
            self.card, text="Target", font=ui_font(13, "bold"),
            text_color="white",
        ).place(relx=0.5, rely=0.5, anchor="center")

    def _build_text_stage(self, parent):
        self.text_stage = ctk.CTkFrame(
            parent, fg_color=PANEL_BG, height=150, corner_radius=BUTTON_RADIUS,
        )
        self.text_stage.pack(fill="x", padx=CONTENT_PADX, pady=(CONTENT_PADY, 4))
        self.text_stage.pack_propagate(False)
        self._reset_text_stage()

    def _build_loaders_stage(self, parent):
        self.loaders_stage = ctk.CTkFrame(
            parent, fg_color=PANEL_BG, height=150, corner_radius=BUTTON_RADIUS,
        )
        self.loaders_stage.pack(fill="x", padx=CONTENT_PADX, pady=(CONTENT_PADY, 4))
        self.loaders_stage.pack_propagate(False)
        self._add_loaders_instruction()

    def _add_loaders_instruction(self):
        ctk.CTkLabel(
            self.loaders_stage,
            text="Click a button to see a loading indicator.",
            font=ui_font(BUTTON_FONT_SIZE), text_color=EMPTY_FG,
        ).place(relx=0.5, rely=0.5, anchor="center")

    def _build_btn_stage(self, parent):
        self.btn_stage = ctk.CTkFrame(
            parent, fg_color=PANEL_BG, height=150, corner_radius=BUTTON_RADIUS,
        )
        self.btn_stage.pack(fill="x", padx=CONTENT_PADX, pady=(CONTENT_PADY, 4))
        self.btn_stage.pack_propagate(False)

        ctk.CTkLabel(
            self.btn_stage,
            text="Pick an effect, then click 'Press me'.",
            font=ui_font(BUTTON_FONT_SIZE), text_color=EMPTY_FG,
        ).place(relx=0.5, rely=0.06, anchor="n")

        self.sample_btn = ctk.CTkButton(
            self.btn_stage, text="Press me",
            width=SAMPLE_BTN_W, height=SAMPLE_BTN_H,
            corner_radius=BUTTON_RADIUS,
            fg_color=PRIMARY_BG, hover_color=PRIMARY_HOVER,
            font=ui_font(BUTTON_FONT_SIZE, "bold"),
            command=self._on_sample_press,
        )
        self.sample_btn.place(relx=0.5, rely=0.55, anchor="center")

    def _build_card_tab(self, parent):
        self._build_stage(parent)
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=CONTENT_PADX, pady=8)
        for i, (text, cmd) in enumerate([
            ("Slide", self.demo_slide),
            ("Color", self.demo_color),
            ("Scale", self.demo_scale),
            ("Shake", self.demo_shake),
            ("Card Enter", self.demo_card_enter),
            ("Stagger", self.demo_stagger),
            ("Reset", self.reset_card),
        ]):
            wrapped = (
                lambda f=cmd, n=text: self._trigger("card", n, f)
            )
            secondary_button(row, text, wrapped, width=98).grid(
                row=0, column=i, padx=2,
            )

    def _build_text_tab(self, parent):
        self._build_text_stage(parent)
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=CONTENT_PADX, pady=8)
        for text, cmd in [
            ("Typewriter", self.demo_text_typewriter),
            ("Counter", self.demo_text_counter),
            ("Wave", self.demo_text_wave),
            ("Fade Words", self.demo_text_fade_words),
        ]:
            wrapped = (
                lambda f=cmd, n=text: self._trigger("text", n, f)
            )
            secondary_button(row, text, wrapped, width=120).pack(side="left", padx=2)

    def _build_loaders_tab(self, parent):
        self._build_loaders_stage(parent)
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=CONTENT_PADX, pady=8)
        for text, cmd in [
            ("Pulse", self.demo_loader_pulse),
            ("Arc", self.demo_loader_arc),
            ("Three Dots", self.demo_loader_three_dots),
            ("Shimmer", self.demo_loader_shimmer),
            ("Progress", self.demo_loader_progress),
        ]:
            wrapped = (
                lambda f=cmd, n=text: self._trigger("loaders", n, f)
            )
            secondary_button(row, text, wrapped, width=120).pack(side="left", padx=2)

    def _build_popups_tab(self, parent):
        stage = ctk.CTkFrame(
            parent, fg_color=PANEL_BG, height=150, corner_radius=BUTTON_RADIUS,
        )
        stage.pack(fill="x", padx=CONTENT_PADX, pady=(CONTENT_PADY, 4))
        stage.pack_propagate(False)
        ctk.CTkLabel(
            stage,
            text=(
                "Popups appear as separate windows.\n"
                "Click a button to see the entrance animation."
            ),
            font=ui_font(BUTTON_FONT_SIZE), text_color=EMPTY_FG,
            justify="center",
        ).place(relx=0.5, rely=0.5, anchor="center")

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=CONTENT_PADX, pady=8)
        for text, cmd in [
            ("Fade", self.demo_popup_fade),
            ("Pop", self.demo_popup_pop),
            ("Slide-Down", self.demo_popup_slide_down),
            ("Slide-Up", self.demo_popup_slide_up),
            ("Slide-Right", self.demo_popup_slide_right),
            ("Zoom", self.demo_popup_zoom),
        ]:
            wrapped = (
                lambda f=cmd, n=text: self._trigger("popups", n, f)
            )
            secondary_button(row, text, wrapped, width=110).pack(side="left", padx=2)

    def _build_toasts_tab(self, parent):
        stage = ctk.CTkFrame(
            parent, fg_color=PANEL_BG, height=150, corner_radius=BUTTON_RADIUS,
        )
        stage.pack(fill="x", padx=CONTENT_PADX, pady=(CONTENT_PADY, 4))
        stage.pack_propagate(False)
        ctk.CTkLabel(
            stage,
            text=(
                "Toasts slide in from the chosen window corner.\n"
                "Pick a position, then a toast type."
            ),
            font=ui_font(BUTTON_FONT_SIZE), text_color=EMPTY_FG,
            justify="center",
        ).place(relx=0.5, rely=0.5, anchor="center")

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=CONTENT_PADX, pady=8)
        ctk.CTkLabel(
            row, text="Position:", font=ui_font(BUTTON_FONT_SIZE),
            text_color=TREE_FG,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkOptionMenu(
            row, values=self.TOAST_POSITIONS,
            variable=self.toast_position_var,
            width=140, height=BUTTON_HEIGHT,
            corner_radius=BUTTON_RADIUS, font=ui_font(BUTTON_FONT_SIZE),
            fg_color=SECONDARY_BG, button_color=PRIMARY_BG,
            button_hover_color=PRIMARY_HOVER,
        ).pack(side="left", padx=(0, 16))
        for text, cmd in [
            ("Info", self.demo_toast_info),
            ("Success", self.demo_toast_success),
            ("Warning", self.demo_toast_warning),
            ("Error", self.demo_toast_error),
        ]:
            wrapped = (
                lambda f=cmd, n=text: self._trigger("toasts", n, f)
            )
            secondary_button(row, text, wrapped, width=92).pack(side="left", padx=4)

    def _build_button_tab(self, parent):
        self._build_btn_stage(parent)

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=CONTENT_PADX, pady=8)
        ctk.CTkLabel(
            row, text="Press effect:", font=ui_font(BUTTON_FONT_SIZE),
            text_color=TREE_FG,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkOptionMenu(
            row, values=[
                "None", "Grow", "Shrink", "Rise", "Sink",
                "Wobble", "Squish", "Flash", "Press Down",
            ],
            variable=self.btn_effect_var,
            width=140, height=BUTTON_HEIGHT,
            corner_radius=BUTTON_RADIUS, font=ui_font(BUTTON_FONT_SIZE),
            fg_color=SECONDARY_BG, button_color=PRIMARY_BG,
            button_hover_color=PRIMARY_HOVER,
        ).pack(side="left", padx=(0, 16))

        ctk.CTkLabel(
            row, text="Hover effect:", font=ui_font(BUTTON_FONT_SIZE),
            text_color=TREE_FG,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkOptionMenu(
            row, values=["None", "Grow", "Lift", "Glow", "Shimmer"],
            variable=self.btn_hover_var,
            width=130, height=BUTTON_HEIGHT,
            corner_radius=BUTTON_RADIUS, font=ui_font(BUTTON_FONT_SIZE),
            fg_color=SECONDARY_BG, button_color=PRIMARY_BG,
            button_hover_color=PRIMARY_HOVER,
        ).pack(side="left")
        self.btn_hover_var.trace_add(
            "write", lambda *a: self._setup_hover_binding()
        )
        self.after(100, self._setup_hover_binding)

    def _build_common_controls(self, parent):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(side="bottom", fill="x", padx=CONTENT_PADX, pady=(4, CONTENT_PADY))

        ctk.CTkLabel(
            row, text="Easing:", font=ui_font(BUTTON_FONT_SIZE),
            text_color=TREE_FG,
        ).pack(side="left", padx=(0, 4))
        ctk.CTkOptionMenu(
            row, values=list(EASINGS.keys()), variable=self.easing_var,
            width=130, height=BUTTON_HEIGHT,
            corner_radius=BUTTON_RADIUS, font=ui_font(BUTTON_FONT_SIZE),
            fg_color=SECONDARY_BG, button_color=PRIMARY_BG,
            button_hover_color=PRIMARY_HOVER,
        ).pack(side="left", padx=(0, 6))

        self.easing_canvas = tk.Canvas(
            row, bg=PANEL_BG, width=180, height=BUTTON_HEIGHT,
            highlightthickness=1, highlightbackground=BORDER, bd=0,
        )
        self.easing_canvas.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(
            row, text="Duration (s):", font=ui_font(BUTTON_FONT_SIZE),
            text_color=TREE_FG,
        ).pack(side="left", padx=(0, 4))
        ctk.CTkEntry(
            row, textvariable=self.duration_var,
            width=60, height=BUTTON_HEIGHT,
            corner_radius=BUTTON_RADIUS, font=ui_font(BUTTON_FONT_SIZE),
            fg_color=BG, border_color=BORDER, text_color=TREE_FG,
        ).pack(side="left")

        primary_button(
            row, "Generate code", self._show_generated_code, width=140,
        ).pack(side="right")

    def _redraw_easing_curve(self):
        if not hasattr(self, "easing_canvas"):
            return
        canvas = self.easing_canvas
        canvas.delete("all")
        w = int(canvas.cget("width"))
        h = int(canvas.cget("height"))
        pad = 4
        plot_w = w - 2 * pad
        plot_h = h - 2 * pad
        y_min, y_max = -0.15, 1.15

        def map_y(v):
            normalized = (v - y_min) / (y_max - y_min)
            return pad + plot_h * (1 - normalized)

        canvas.create_line(
            pad, map_y(0), w - pad, map_y(0),
            fill=BORDER, dash=(2, 3),
        )
        canvas.create_line(
            pad, map_y(1), w - pad, map_y(1),
            fill=BORDER, dash=(2, 3),
        )

        f = EASINGS.get(self.easing_var.get(), linear)
        points = []
        n = 80
        for i in range(n + 1):
            t = i / n
            try:
                y = f(t)
            except Exception:
                y = t
            points.extend([pad + plot_w * t, map_y(y)])
        canvas.create_line(*points, fill=TREE_FG, width=2, smooth=True)

    # ---- helpers ----------------------------------------------------------

    def _easing(self):
        return EASINGS[self.easing_var.get()]

    def _duration(self):
        try:
            return float(self.duration_var.get())
        except ValueError:
            return 0.7

    def reset_card(self):
        self.card.place_configure(relx=0.5, rely=0.55, anchor="center")
        self.card.configure(
            width=CARD_DEFAULT_W, height=CARD_DEFAULT_H, fg_color=CARD_COLOR,
        )
        self.sample_btn.place_configure(relx=0.5, rely=0.55, anchor="center", y=0)
        self.sample_btn.configure(width=SAMPLE_BTN_W, height=SAMPLE_BTN_H)
        self._reset_text_stage()
        self._clear_loaders_stage()

    # ---- card demos -------------------------------------------------------

    def demo_slide(self):
        start_x, end_x = 0.2, 0.8
        self.card.place_configure(relx=start_x)
        Tween(
            self, self._duration(), self._easing(),
            lambda t: self.card.place_configure(relx=lerp(start_x, end_x, t)),
        ).start()

    def demo_color(self):
        start = CARD_COLOR
        target = "#d9534f"
        cur = self.card.cget("fg_color")
        if isinstance(cur, str) and cur.lower().startswith("#d"):
            start, target = target, CARD_COLOR
        Tween(
            self, self._duration(), self._easing(),
            lambda t: self.card.configure(fg_color=lerp_color_hsl(start, target, t)),
        ).start()

    def demo_scale(self):
        w0, h0 = CARD_DEFAULT_W, CARD_DEFAULT_H
        w1, h1 = 220, 70

        def to_big(t):
            self.card.configure(
                width=int(lerp(w0, w1, t)), height=int(lerp(h0, h1, t)),
            )

        def to_small(t):
            self.card.configure(
                width=int(lerp(w1, w0, t)), height=int(lerp(h1, h0, t)),
            )

        Tween(
            self, self._duration(), self._easing(), to_big,
            on_done=lambda: self.after(
                250,
                lambda: Tween(self, self._duration(), self._easing(), to_small).start(),
            ),
        ).start()

    def demo_shake(self):
        center = 0.5
        amp = 0.05

        def step(t):
            offset = math.sin(t * math.pi * 8) * amp * (1 - t)
            self.card.place_configure(relx=center + offset)

        Tween(
            self, self._duration(), linear, step,
            on_done=lambda: self.card.place_configure(relx=center),
        ).start()

    def demo_card_enter(self):
        start_rely = 1.35
        end_rely = 0.55
        start_color = PANEL_BG
        end_color = CARD_COLOR
        start_w, start_h = 90, 80
        end_w, end_h = CARD_DEFAULT_W, CARD_DEFAULT_H

        self.card.place_configure(relx=0.5, rely=start_rely, anchor="center")
        self.card.configure(width=start_w, height=start_h, fg_color=start_color)

        def step(t):
            self.card.place_configure(rely=lerp(start_rely, end_rely, t))
            self.card.configure(
                fg_color=lerp_color_hsl(start_color, end_color, max(0, min(1, t))),
                width=int(lerp(start_w, end_w, t)),
                height=int(lerp(start_h, end_h, t)),
            )

        Tween(self, self._duration(), back_out, step).start()

    def demo_stagger(self):
        self.card.place_forget()
        n = 5
        spacing = 0.14
        start_relx = 0.5 - spacing * (n - 1) / 2
        items = []
        for i in range(n):
            f = ctk.CTkFrame(
                self.stage, width=60, height=60,
                fg_color=PANEL_BG, corner_radius=8,
            )
            f.place(relx=start_relx + i * spacing, rely=1.3, anchor="center")
            items.append(f)

        counter = {"done": 0}

        def on_one_done():
            counter["done"] += 1
            if counter["done"] == n:
                self.after(900, lambda: self._stagger_cleanup(items))

        for i, frame in enumerate(items):
            def make_step(f=frame):
                def step(t):
                    f.place_configure(rely=lerp(1.3, 0.5, t))
                    f.configure(
                        fg_color=lerp_color_hsl(
                            PANEL_BG, CARD_COLOR, max(0, min(1, t))
                        )
                    )
                return step
            self.after(
                i * 90,
                lambda s=make_step(): Tween(
                    self, 0.6, back_out, s, on_done=on_one_done
                ).start(),
            )

    def _stagger_cleanup(self, items):
        for w in items:
            w.destroy()
        self.card.place(relx=0.5, rely=0.55, anchor="center")
        self.card.configure(
            width=CARD_DEFAULT_W, height=CARD_DEFAULT_H, fg_color=CARD_COLOR,
        )

    # ---- text demos -------------------------------------------------------

    DEFAULT_TEXT = "Click a button to animate text."
    TYPEWRITER_TEXT = "Hello, CTk!"
    WAVE_TEXT = "Animation"
    FADE_WORDS_TEXT = "This is a fade demo"

    def _clear_text_stage(self):
        for w in self.text_stage.winfo_children():
            w.destroy()

    def _reset_text_stage(self, text=None):
        self._clear_text_stage()
        self.text_label = ctk.CTkLabel(
            self.text_stage,
            text=self.DEFAULT_TEXT if text is None else text,
            font=ui_font(16, "bold"), text_color=TREE_FG,
        )
        self.text_label.place(relx=0.5, rely=0.5, anchor="center")

    def demo_text_typewriter(self):
        text = self.TYPEWRITER_TEXT
        self._reset_text_stage(text="")

        def step(t):
            n = max(0, min(int(len(text) * t + 0.5), len(text)))
            self.text_label.configure(text=text[:n])

        def on_done():
            self.text_label.configure(text=text)
            self.after(1500, self._reset_text_stage)

        Tween(self, self._duration(), self._easing(), step, on_done=on_done).start()

    def demo_text_counter(self):
        end_value = 100
        self._reset_text_stage(text="0")

        def step(t):
            self.text_label.configure(text=str(int(lerp(0, end_value, t))))

        def on_done():
            self.text_label.configure(text=str(end_value))
            self.after(1500, self._reset_text_stage)

        Tween(self, self._duration(), self._easing(), step, on_done=on_done).start()

    def demo_text_wave(self):
        text = self.WAVE_TEXT
        self._clear_text_stage()
        self.text_stage.update_idletasks()

        canvas = tk.Canvas(
            self.text_stage, bg=PANEL_BG,
            highlightthickness=0, bd=0,
        )
        canvas.pack(fill="both", expand=True)
        self.text_stage.update_idletasks()

        font_spec = ("Segoe UI", 16, "bold")
        f = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        char_widths = [f.measure(ch) for ch in text]
        total_w = sum(char_widths)

        stage_w = canvas.winfo_width()
        stage_h = canvas.winfo_height()
        cy = stage_h // 2
        cur_x = (stage_w - total_w) // 2

        char_ids = []
        for i, ch in enumerate(text):
            cid = canvas.create_text(
                cur_x + char_widths[i] // 2, cy,
                text=ch, font=font_spec,
                fill=TREE_FG, anchor="center",
            )
            char_ids.append((cid, cur_x + char_widths[i] // 2, cy))
            cur_x += char_widths[i]

        amp = 10

        def step(t):
            for i, (cid, base_x, base_y) in enumerate(char_ids):
                offset = math.sin(t * math.pi * 4 + i * 0.4) * amp * (1 - t)
                canvas.coords(cid, base_x, base_y + offset)

        Tween(
            self, self._duration(), linear, step,
            on_done=lambda: self.after(300, self._reset_text_stage),
        ).start()

    def demo_text_fade_words(self):
        text = self.FADE_WORDS_TEXT
        self._clear_text_stage()

        container = ctk.CTkFrame(self.text_stage, fg_color="transparent")
        container.place(relx=0.5, rely=0.5, anchor="center")

        words = text.split()
        word_labels = []
        for word in words:
            lbl = ctk.CTkLabel(
                container, text=word,
                font=ui_font(16, "bold"), text_color=PANEL_BG,
            )
            lbl.pack(side="left", padx=4)
            word_labels.append(lbl)

        n = len(word_labels)
        counter = {"done": 0}

        def on_one_done():
            counter["done"] += 1
            if counter["done"] == n:
                self.after(900, self._reset_text_stage)

        for i, lbl in enumerate(word_labels):
            def make_step(label=lbl):
                def step(t):
                    label.configure(
                        text_color=lerp_color_hsl(
                            PANEL_BG, TREE_FG, max(0, min(1, t))
                        )
                    )
                return step
            self.after(
                i * 120,
                lambda s=make_step(): Tween(
                    self, 0.5, ease_out, s, on_done=on_one_done
                ).start(),
            )

    # ---- loading indicators -----------------------------------------------

    LOADER_DURATION = 3.0

    def _clear_loaders_stage(self):
        for w in self.loaders_stage.winfo_children():
            w.destroy()
        self._add_loaders_instruction()

    def _new_loaders_canvas(self):
        self._clear_loaders_stage()
        canvas = tk.Canvas(
            self.loaders_stage, bg=PANEL_BG,
            highlightthickness=0, bd=0,
        )
        canvas.pack(fill="both", expand=True)
        self.loaders_stage.update_idletasks()
        return canvas

    def demo_loader_pulse(self):
        canvas = self._new_loaders_canvas()
        cx = canvas.winfo_width() // 2
        cy = canvas.winfo_height() // 2
        base_r = 14
        cid = canvas.create_oval(
            cx - base_r, cy - base_r, cx + base_r, cy + base_r,
            fill=PRIMARY_BG, outline="",
        )

        def step(t):
            pulse = (math.sin(t * 3 * 2 * math.pi) + 1) / 2
            r = base_r * (0.5 + pulse * 0.5)
            canvas.coords(cid, cx - r, cy - r, cx + r, cy + r)

        Tween(
            self, self.LOADER_DURATION, linear, step,
            on_done=self._clear_loaders_stage,
        ).start()

    def demo_loader_arc(self):
        canvas = self._new_loaders_canvas()
        cx = canvas.winfo_width() // 2
        cy = canvas.winfo_height() // 2
        r = 18
        arc_id = canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=0, extent=270,
            outline=PRIMARY_BG, width=4, style="arc",
        )

        def step(t):
            angle = -(t * 3 * 360) % 360
            canvas.itemconfigure(arc_id, start=angle)

        Tween(
            self, self.LOADER_DURATION, linear, step,
            on_done=self._clear_loaders_stage,
        ).start()

    def demo_loader_three_dots(self):
        canvas = self._new_loaders_canvas()
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        cy = h // 2

        dot_r = 6
        spacing = 22
        cx_start = w // 2 - spacing

        dots = []
        for i in range(3):
            cx = cx_start + i * spacing
            d = canvas.create_oval(
                cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r,
                fill=PRIMARY_BG, outline="",
            )
            dots.append((d, cx, cy))

        amp = 8
        cycles = 4

        def step(t):
            for i, (did, base_x, base_y) in enumerate(dots):
                phase = t * cycles * 2 * math.pi - i * (2 * math.pi / 3)
                offset = max(0, math.sin(phase)) * amp
                canvas.coords(
                    did,
                    base_x - dot_r, base_y - offset - dot_r,
                    base_x + dot_r, base_y - offset + dot_r,
                )

        Tween(
            self, self.LOADER_DURATION, linear, step,
            on_done=self._clear_loaders_stage,
        ).start()

    def demo_loader_shimmer(self):
        canvas = self._new_loaders_canvas()
        w = canvas.winfo_width()
        h = canvas.winfo_height()

        margin = 24
        card_x1 = margin
        card_x2 = w - margin
        card_y1 = h // 2 - 12
        card_y2 = h // 2 + 12
        canvas.create_rectangle(
            card_x1, card_y1, card_x2, card_y2,
            fill=SECONDARY_BG, outline="",
        )

        band_w = 60
        band = canvas.create_rectangle(
            card_x1, card_y1, card_x1, card_y2,
            fill=SECONDARY_HOVER, outline="",
        )

        card_w = card_x2 - card_x1

        def step(t):
            cycle_t = (t * 2) % 1
            x = card_x1 + cycle_t * (card_w + band_w) - band_w
            x_end = x + band_w
            x_clamped = max(card_x1, x)
            x_end_clamped = min(card_x2, x_end)
            if x_clamped < x_end_clamped:
                canvas.coords(
                    band, x_clamped, card_y1, x_end_clamped, card_y2,
                )
            else:
                canvas.coords(band, card_x1, card_y1, card_x1, card_y2)

        Tween(
            self, self.LOADER_DURATION, linear, step,
            on_done=self._clear_loaders_stage,
        ).start()

    def demo_loader_progress(self):
        self._clear_loaders_stage()
        self.loaders_stage.update_idletasks()
        bar = ctk.CTkProgressBar(
            self.loaders_stage,
            width=320, height=14,
            progress_color=PRIMARY_BG,
            fg_color=SECONDARY_BG,
        )
        bar.set(0)
        bar.place(relx=0.5, rely=0.5, anchor="center")

        def step(t):
            try:
                bar.set(max(0.0, min(1.0, t)))
            except tk.TclError:
                pass

        def finish():
            self.after(800, self._clear_loaders_stage)

        Tween(
            self, self._duration(), self._easing(), step,
            on_done=finish,
        ).start()

    # ---- toasts -----------------------------------------------------------

    TOAST_W = 280
    TOAST_H = 60
    TOAST_MARGIN = 16
    TOAST_SPACING = 8
    TOAST_HOLD_MS = 2000
    TOAST_SLIDE_OFFSET = 140
    TOAST_POSITIONS = [
        "Bottom-Right", "Bottom-Left", "Bottom-Center",
        "Top-Right", "Top-Left", "Top-Center",
    ]

    def _toast_slot(self, position, index):
        """Compute (target_x, target_y) for the index-th toast at position."""
        self.update_idletasks()
        win_x = self.winfo_x()
        win_y = self.winfo_y()
        win_w = self.winfo_width()
        win_h = self.winfo_height()
        tw, th = self.TOAST_W, self.TOAST_H
        margin = self.TOAST_MARGIN
        spacing = self.TOAST_SPACING

        if "Right" in position:
            x = win_x + win_w - tw - margin
        elif "Left" in position:
            x = win_x + margin
        else:
            x = win_x + (win_w - tw) // 2

        if "Bottom" in position:
            y = win_y + win_h - th - margin - index * (th + spacing)
        else:
            y = win_y + margin + index * (th + spacing)

        return x, y

    def _toast_start_pos(self, position, target_x, target_y):
        """Return (start_x, start_y) — where slide-in begins from."""
        offset = self.TOAST_SLIDE_OFFSET
        if "Right" in position:
            return target_x + offset, target_y
        if "Left" in position:
            return target_x - offset, target_y
        if position == "Top-Center":
            return target_x, target_y - offset
        return target_x, target_y + offset  # Bottom-Center

    def _make_toast(self, message, accent_color):
        position = self.toast_position_var.get()
        stack = self._toast_stacks.setdefault(position, [])
        used = {
            t._toast_index for t in stack if hasattr(t, "_toast_index")
        }
        index = 0
        while index in used:
            index += 1

        target_x, target_y = self._toast_slot(position, index)
        start_x, start_y = self._toast_start_pos(position, target_x, target_y)

        toast = tk.Toplevel(self)
        toast.overrideredirect(True)
        toast.attributes("-alpha", 0.0)
        toast.attributes("-topmost", True)
        toast.configure(bg=BORDER)
        toast._toast_index = index
        toast._toast_position = position

        inner = tk.Frame(toast, bg=PANEL_BG)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Frame(inner, bg=accent_color, width=4).pack(side="left", fill="y")
        ctk.CTkLabel(
            inner, text=message, font=ui_font(BUTTON_FONT_SIZE, "bold"),
            text_color=accent_color, anchor="w", fg_color=PANEL_BG,
        ).pack(side="left", padx=12, pady=10, fill="both", expand=True)

        toast.geometry(
            f"{self.TOAST_W}x{self.TOAST_H}+{start_x}+{start_y}"
        )
        stack.append(toast)

        def slide_in(t):
            cx = int(lerp(start_x, target_x, t))
            cy = int(lerp(start_y, target_y, t))
            toast.geometry(f"{self.TOAST_W}x{self.TOAST_H}+{cx}+{cy}")
            toast.attributes("-alpha", min(t * 1.5, 1.0))

        def slide_out():
            out_x, out_y = self._toast_start_pos(position, target_x, target_y)

            def step(t):
                cx = int(lerp(target_x, out_x, t))
                cy = int(lerp(target_y, out_y, t))
                toast.geometry(f"{self.TOAST_W}x{self.TOAST_H}+{cx}+{cy}")
                toast.attributes("-alpha", 1 - t)

            Tween(
                toast, 0.3, ease_in, step,
                on_done=lambda: self._dismiss_toast(toast),
            ).start()

        Tween(
            toast, 0.4, back_out, slide_in,
            on_done=lambda: toast.after(self.TOAST_HOLD_MS, slide_out),
        ).start()

    def _dismiss_toast(self, toast):
        position = getattr(toast, "_toast_position", None)
        if position is not None:
            stack = self._toast_stacks.get(position, [])
            if toast in stack:
                stack.remove(toast)
        try:
            toast.destroy()
        except tk.TclError:
            pass

    def demo_toast_info(self):
        self._make_toast("Info: this is informational", "#4a9eff")

    def demo_toast_success(self):
        self._make_toast("Success: action completed", "#6fcf6a")

    def demo_toast_warning(self):
        self._make_toast("Warning: something to check", "#e0a44a")

    def demo_toast_error(self):
        self._make_toast("Error: something went wrong", "#d9534f")

    # ---- pop-up dialogs ---------------------------------------------------

    def _make_popup(self, title):
        tw, th, tx, ty = POPUP_TARGET
        top = ctk.CTkToplevel(self)
        top.title(title)
        top.attributes("-alpha", 0.0)
        top.transient(self)
        top.configure(fg_color=BORDER)

        inner = ctk.CTkFrame(
            top, fg_color=PANEL_BG, corner_radius=BUTTON_RADIUS,
        )
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        ctk.CTkLabel(
            inner, text=title, font=ui_font(16, "bold"), text_color=TREE_FG,
        ).pack(expand=True)

        # Force dark titlebar via the withdraw+deiconify trick — Windows
        # defers the DWM dark NC paint past the first map; only this
        # cycle reliably triggers it. Same pattern as ManagedToplevel's
        # `_kick_dark_remap`.
        def _kick():
            try:
                top.update_idletasks()
                top.withdraw()
                top.update_idletasks()
                top.deiconify()
            except tk.TclError:
                pass
        top.after(50, _kick)

        return top, tw, th, tx, ty

    def _close_popup_after(self, top, hold_ms=1100):
        def out():
            Tween(
                top, 0.35, ease_in,
                lambda t: top.attributes("-alpha", 1 - t),
                on_done=top.destroy,
            ).start()
        top.after(hold_ms, out)

    def demo_popup_fade(self):
        top, tw, th, tx, ty = self._make_popup("Fade")
        top.geometry(f"{tw}x{th}+{tx}+{ty}")
        Tween(
            top, 0.5, ease_out,
            lambda t: top.attributes("-alpha", min(t, 1.0)),
            on_done=lambda: self._close_popup_after(top),
        ).start()

    def demo_popup_pop(self):
        top, tw, th, tx, ty = self._make_popup("Pop")
        sw, sh = int(tw * 0.82), int(th * 0.82)
        top.geometry(f"{sw}x{sh}+{tx + (tw - sw) // 2}+{ty + (th - sh) // 2}")

        def step(t):
            w = int(lerp(sw, tw, t))
            h = int(lerp(sh, th, t))
            top.geometry(f"{w}x{h}+{tx + (tw - w) // 2}+{ty + (th - h) // 2}")
            top.attributes("-alpha", min(t, 1.0))

        Tween(
            top, 0.45, back_out, step,
            on_done=lambda: self._close_popup_after(top),
        ).start()

    def demo_popup_slide_down(self):
        top, tw, th, tx, ty = self._make_popup("Slide-Down")
        start_y = ty - 240
        top.geometry(f"{tw}x{th}+{tx}+{start_y}")

        def step(t):
            y = int(lerp(start_y, ty, t))
            top.geometry(f"{tw}x{th}+{tx}+{y}")
            top.attributes("-alpha", min(t * 1.6, 1.0))

        Tween(
            top, 0.6, bounce_out, step,
            on_done=lambda: self._close_popup_after(top),
        ).start()

    def demo_popup_slide_up(self):
        top, tw, th, tx, ty = self._make_popup("Slide-Up")
        start_y = ty + 240
        top.geometry(f"{tw}x{th}+{tx}+{start_y}")

        def step(t):
            y = int(lerp(start_y, ty, t))
            top.geometry(f"{tw}x{th}+{tx}+{y}")
            top.attributes("-alpha", min(t * 1.6, 1.0))

        Tween(
            top, 0.5, ease_out_quint, step,
            on_done=lambda: self._close_popup_after(top),
        ).start()

    def demo_popup_slide_right(self):
        top, tw, th, tx, ty = self._make_popup("Slide-Right")
        start_x = tx - 300
        top.geometry(f"{tw}x{th}+{start_x}+{ty}")

        def step(t):
            x = int(lerp(start_x, tx, t))
            top.geometry(f"{tw}x{th}+{x}+{ty}")
            top.attributes("-alpha", min(t * 1.6, 1.0))

        Tween(
            top, 0.5, back_out, step,
            on_done=lambda: self._close_popup_after(top),
        ).start()

    def demo_popup_zoom(self):
        top, tw, th, tx, ty = self._make_popup("Zoom")
        sw, sh = int(tw * 0.4), int(th * 0.4)
        top.geometry(f"{sw}x{sh}+{tx + (tw - sw) // 2}+{ty + (th - sh) // 2}")

        def step(t):
            w = int(lerp(sw, tw, t))
            h = int(lerp(sh, th, t))
            top.geometry(f"{w}x{h}+{tx + (tw - w) // 2}+{ty + (th - h) // 2}")
            top.attributes("-alpha", min(t, 1.0))

        Tween(
            top, 0.5, back_out, step,
            on_done=lambda: self._close_popup_after(top),
        ).start()

    # ---- button hover/press effects ---------------------------------------

    def _btn_size_pulse(self, scale_peak):
        base_w, base_h = SAMPLE_BTN_W, SAMPLE_BTN_H
        peak_w = max(1, int(base_w * scale_peak))
        peak_h = max(1, int(base_h * scale_peak))

        def to_peak(t):
            self.sample_btn.configure(
                width=int(lerp(base_w, peak_w, t)),
                height=int(lerp(base_h, peak_h, t)),
            )

        def to_base(t):
            self.sample_btn.configure(
                width=int(lerp(peak_w, base_w, t)),
                height=int(lerp(peak_h, base_h, t)),
            )

        Tween(
            self, 0.12, ease_out, to_peak,
            on_done=lambda: Tween(self, 0.22, self._easing(), to_base).start(),
        ).start()

    def _btn_offset_pulse(self, dy_peak):
        def to_peak(t):
            self.sample_btn.place_configure(
                relx=0.5, rely=0.55, anchor="center", y=lerp(0, dy_peak, t)
            )

        def to_base(t):
            self.sample_btn.place_configure(
                relx=0.5, rely=0.55, anchor="center", y=lerp(dy_peak, 0, t)
            )

        Tween(
            self, 0.12, ease_out, to_peak,
            on_done=lambda: Tween(self, 0.22, self._easing(), to_base).start(),
        ).start()

    def _btn_wobble(self):
        amp = 6

        def step(t):
            offset = math.sin(t * math.pi * 6) * amp * (1 - t)
            self.sample_btn.place_configure(
                relx=0.5, rely=0.5, anchor="center", x=offset,
            )

        Tween(
            self, 0.5, linear, step,
            on_done=lambda: self.sample_btn.place_configure(
                relx=0.5, rely=0.5, anchor="center", x=0,
            ),
        ).start()

    def _btn_squish(self):
        base_w, base_h = SAMPLE_BTN_W, SAMPLE_BTN_H
        peak_w = int(base_w * 1.08)
        peak_h = int(base_h * 0.92)

        def to_peak(t):
            self.sample_btn.configure(
                width=int(lerp(base_w, peak_w, t)),
                height=int(lerp(base_h, peak_h, t)),
            )

        def to_base(t):
            self.sample_btn.configure(
                width=int(lerp(peak_w, base_w, t)),
                height=int(lerp(peak_h, base_h, t)),
            )

        Tween(
            self, 0.12, ease_out, to_peak,
            on_done=lambda: Tween(self, 0.22, self._easing(), to_base).start(),
        ).start()

    def _btn_flash(self):
        base = PRIMARY_BG
        peak = PRIMARY_HOVER

        def to_peak(t):
            self.sample_btn.configure(
                fg_color=lerp_color_hsl(base, peak, max(0, min(1, t)))
            )

        def to_base(t):
            self.sample_btn.configure(
                fg_color=lerp_color_hsl(peak, base, max(0, min(1, t)))
            )

        Tween(
            self, 0.12, ease_out, to_peak,
            on_done=lambda: Tween(self, 0.22, self._easing(), to_base).start(),
        ).start()

    def _btn_press_down(self):
        base_w, base_h = SAMPLE_BTN_W, SAMPLE_BTN_H
        peak_w = int(base_w * 0.95)
        peak_h = int(base_h * 0.95)
        sink_y = 4

        def to_peak(t):
            self.sample_btn.configure(
                width=int(lerp(base_w, peak_w, t)),
                height=int(lerp(base_h, peak_h, t)),
            )
            self.sample_btn.place_configure(
                relx=0.5, rely=0.5, anchor="center", y=lerp(0, sink_y, t),
            )

        def to_base(t):
            self.sample_btn.configure(
                width=int(lerp(peak_w, base_w, t)),
                height=int(lerp(peak_h, base_h, t)),
            )
            self.sample_btn.place_configure(
                relx=0.5, rely=0.5, anchor="center", y=lerp(sink_y, 0, t),
            )

        Tween(
            self, 0.12, ease_out, to_peak,
            on_done=lambda: Tween(self, 0.22, self._easing(), to_base).start(),
        ).start()

    def _on_sample_press(self):
        mode = self.btn_effect_var.get()
        self._last_selected = ("button", mode)
        if mode == "Grow":
            self._btn_size_pulse(1.08)
        elif mode == "Shrink":
            self._btn_size_pulse(0.92)
        elif mode == "Rise":
            self._btn_offset_pulse(-6)
        elif mode == "Sink":
            self._btn_offset_pulse(6)
        elif mode == "Wobble":
            self._btn_wobble()
        elif mode == "Squish":
            self._btn_squish()
        elif mode == "Flash":
            self._btn_flash()
        elif mode == "Press Down":
            self._btn_press_down()

    def _trigger(self, category, name, fn):
        self._last_selected = (category, name)
        fn()

    # ---- hover effects ----------------------------------------------------

    def _setup_hover_binding(self):
        try:
            self.sample_btn.unbind("<Enter>")
            self.sample_btn.unbind("<Leave>")
        except Exception:
            return
        self._shimmer_active = False
        if self._hover_tween:
            self._hover_tween.stop()
        self.sample_btn.configure(
            width=SAMPLE_BTN_W, height=SAMPLE_BTN_H,
            border_width=0, fg_color=PRIMARY_BG,
        )
        self.sample_btn.place_configure(
            relx=0.5, rely=0.55, anchor="center", y=0,
        )

        mode = self.btn_hover_var.get()
        if mode == "None":
            return

        enter = {
            "Grow": self._hover_grow_enter,
            "Lift": self._hover_lift_enter,
            "Glow": self._hover_glow_enter,
            "Shimmer": self._hover_shimmer_enter,
        }
        leave = {
            "Grow": self._hover_grow_leave,
            "Lift": self._hover_lift_leave,
            "Glow": self._hover_glow_leave,
            "Shimmer": self._hover_shimmer_leave,
        }
        self.sample_btn.bind("<Enter>", lambda e: enter[mode]())
        self.sample_btn.bind("<Leave>", lambda e: leave[mode]())

    def _hover_grow_enter(self):
        if self._hover_tween:
            self._hover_tween.stop()
        base_w, base_h = SAMPLE_BTN_W, SAMPLE_BTN_H
        peak_w, peak_h = int(base_w * 1.05), int(base_h * 1.05)
        cur_w = self.sample_btn.cget("width")
        cur_h = self.sample_btn.cget("height")

        def step(t):
            self.sample_btn.configure(
                width=int(lerp(cur_w, peak_w, t)),
                height=int(lerp(cur_h, peak_h, t)),
            )
        self._hover_tween = Tween(self, 0.15, ease_out, step).start()

    def _hover_grow_leave(self):
        if self._hover_tween:
            self._hover_tween.stop()
        base_w, base_h = SAMPLE_BTN_W, SAMPLE_BTN_H
        cur_w = self.sample_btn.cget("width")
        cur_h = self.sample_btn.cget("height")

        def step(t):
            self.sample_btn.configure(
                width=int(lerp(cur_w, base_w, t)),
                height=int(lerp(cur_h, base_h, t)),
            )
        self._hover_tween = Tween(self, 0.2, ease_out, step).start()

    def _hover_lift_enter(self):
        if self._hover_tween:
            self._hover_tween.stop()

        def step(t):
            self.sample_btn.place_configure(
                relx=0.5, rely=0.55, anchor="center", y=lerp(0, -3, t),
            )
        self._hover_tween = Tween(self, 0.15, ease_out, step).start()

    def _hover_lift_leave(self):
        if self._hover_tween:
            self._hover_tween.stop()

        def step(t):
            self.sample_btn.place_configure(
                relx=0.5, rely=0.55, anchor="center", y=lerp(-3, 0, t),
            )
        self._hover_tween = Tween(self, 0.2, ease_out, step).start()

    def _hover_glow_enter(self):
        if self._hover_tween:
            self._hover_tween.stop()
        self.sample_btn.configure(border_color=PRIMARY_HOVER)
        cur_bw = self.sample_btn.cget("border_width")

        def step(t):
            self.sample_btn.configure(border_width=int(round(lerp(cur_bw, 2, t))))
        self._hover_tween = Tween(self, 0.18, ease_out, step).start()

    def _hover_glow_leave(self):
        if self._hover_tween:
            self._hover_tween.stop()
        cur_bw = self.sample_btn.cget("border_width")

        def step(t):
            self.sample_btn.configure(border_width=int(round(lerp(cur_bw, 0, t))))
        self._hover_tween = Tween(self, 0.22, ease_out, step).start()

    def _hover_shimmer_enter(self):
        self._shimmer_active = True
        self._shimmer_loop()

    def _shimmer_loop(self):
        if not self._shimmer_active:
            return
        base = PRIMARY_BG
        peak = PRIMARY_HOVER

        def to_peak(t):
            self.sample_btn.configure(fg_color=lerp_color_hsl(base, peak, t))

        def to_base(t):
            self.sample_btn.configure(fg_color=lerp_color_hsl(peak, base, t))

        def back():
            Tween(
                self, 0.6, ease_in_out, to_base,
                on_done=self._shimmer_loop,
            ).start()

        Tween(self, 0.6, ease_in_out, to_peak, on_done=back).start()

    def _hover_shimmer_leave(self):
        self._shimmer_active = False
        self.sample_btn.configure(fg_color=PRIMARY_BG)

    # ---- code generator ---------------------------------------------------

    def _show_generated_code(self):
        code = self._generate_code()
        top = ctk.CTkToplevel(self)
        top.title("Generated code")
        top.geometry("760x520")
        top.transient(self)
        top.configure(fg_color=BG)

        def _kick():
            try:
                top.update_idletasks()
                top.withdraw()
                top.update_idletasks()
                top.deiconify()
            except tk.TclError:
                pass
        top.after(50, _kick)

        textbox = ctk.CTkTextbox(
            top, font=("Consolas", 11), wrap="none",
            fg_color=PANEL_BG, text_color=TREE_FG,
            corner_radius=BUTTON_RADIUS, border_color=BORDER, border_width=1,
        )
        textbox.pack(fill="both", expand=True, padx=CONTENT_PADX, pady=(CONTENT_PADX, 6))
        textbox.insert("1.0", code)

        btn_row = ctk.CTkFrame(top, fg_color="transparent")
        btn_row.pack(fill="x", padx=CONTENT_PADX, pady=(0, CONTENT_PADX))

        copy_btn = primary_button(btn_row, "Copy to clipboard", lambda: None, width=160)

        def copy():
            top.clipboard_clear()
            top.clipboard_append(code)
            copy_btn.configure(text="Copied!")
            top.after(1200, lambda: copy_btn.configure(text="Copy to clipboard"))

        copy_btn.configure(command=copy)
        copy_btn.pack(side="left")
        secondary_button(btn_row, "Close", top.destroy, width=80).pack(side="right")

    def _generate_code(self):
        category, name = self._last_selected
        if category == "card":
            return self._generate_card_code(name)
        if category == "text":
            return self._generate_text_code(name)
        if category == "loaders":
            return self._generate_loader_code(name)
        if category == "popups":
            return self._generate_popup_code(name)
        if category == "toasts":
            return self._generate_toast_code(name)
        if category != "button":
            return (
                f"# Code generation for {category} is coming soon.\n"
                f"# Last selected: {name} ({category})\n"
            )

        mode = self.btn_effect_var.get()
        easing_name = self.easing_var.get()
        duration = self._duration()

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

    # ---- card code generator ---------------------------------------------

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

    def _assemble_module(
        self, title, settings, body, main_block,
        easings_needed, needs_math=False, needs_colorsys=False,
        extra_helpers=None,
    ):
        """Build a self-contained Python module string.

        body: source for the main animation function(s).
        main_block: source for the `if __name__ == '__main__':` demo body
                    (already indented 4 spaces).
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
            f"{self.TWEEN_BLOCK}\n"
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

    def _generate_card_code(self, name):
        easing_name = self.easing_var.get()
        duration = self._duration()

        if name == "Reset":
            return (
                "# Reset is not an animation — it just snaps the card back\n"
                "# to its starting position. Pick Slide / Color / Scale /\n"
                "# Shake / Card Enter / Stagger and click Generate code.\n"
            )

        easings_needed = {easing_name}
        needs_math = name == "Shake"
        needs_colorsys = name in ("Color", "Card Enter", "Stagger")
        extra_helpers = [self.HSL_HELPER] if needs_colorsys else None

        # Shake uses linear ease (the sine wave already shapes the motion).
        if name == "Shake":
            easings_needed.add("linear")

        title = f"Card animation — {name} (generated by Transitions Demo)."
        settings = {
            "Animation": name,
            "Easing": easing_name,
            "Duration": f"{duration}s",
        }

        if name == "Slide":
            body = (
                f"def animate_card(card):\n"
                f"    start_x, end_x = 0.2, 0.8\n"
                f"    card.place_configure(relx=start_x, rely=0.5,"
                f' anchor="center")\n'
                f"    Tween(\n"
                f"        card, {duration}, {easing_name},\n"
                f"        lambda t: card.place_configure("
                f"relx=lerp(start_x, end_x, t)),\n"
                f"    ).start()"
            )
        elif name == "Color":
            body = (
                f"BASE_COLOR = '#1f6aa5'\n"
                f"PEAK_COLOR = '#d9534f'\n"
                f"\n"
                f"\n"
                f"def animate_card(card):\n"
                f"    Tween(\n"
                f"        card, {duration}, {easing_name},\n"
                f"        lambda t: card.configure(\n"
                f"            fg_color=lerp_color_hsl(BASE_COLOR, PEAK_COLOR, t)\n"
                f"        ),\n"
                f"    ).start()"
            )
        elif name == "Scale":
            body = (
                f"def animate_card(card, base_w=140, base_h=110):\n"
                f"    PEAK_W, PEAK_H = 220, 70\n"
                f"\n"
                f"    def to_big(t):\n"
                f"        card.configure(\n"
                f"            width=int(lerp(base_w, PEAK_W, t)),\n"
                f"            height=int(lerp(base_h, PEAK_H, t)),\n"
                f"        )\n"
                f"\n"
                f"    def to_small(t):\n"
                f"        card.configure(\n"
                f"            width=int(lerp(PEAK_W, base_w, t)),\n"
                f"            height=int(lerp(PEAK_H, base_h, t)),\n"
                f"        )\n"
                f"\n"
                f"    Tween(\n"
                f"        card, {duration}, {easing_name}, to_big,\n"
                f"        on_done=lambda: card.after(\n"
                f"            250,\n"
                f"            lambda: Tween(\n"
                f"                card, {duration}, {easing_name}, to_small\n"
                f"            ).start(),\n"
                f"        ),\n"
                f"    ).start()"
            )
        elif name == "Shake":
            body = (
                f"def animate_card(card):\n"
                f"    center = 0.5\n"
                f"    AMP = 0.05\n"
                f"\n"
                f"    def step(t):\n"
                f"        offset = math.sin(t * math.pi * 8) * AMP * (1 - t)\n"
                f'        card.place_configure(relx=center + offset,'
                f' rely=0.5, anchor="center")\n'
                f"\n"
                f"    Tween(\n"
                f"        card, {duration}, linear, step,\n"
                f"        on_done=lambda: card.place_configure("
                f'relx=center, rely=0.5, anchor="center"),\n'
                f"    ).start()"
            )
        elif name == "Card Enter":
            body = (
                f"BASE_COLOR = '#1f6aa5'\n"
                f"START_COLOR = '#2d2d30'\n"
                f"\n"
                f"\n"
                f"def animate_card(card, base_w=140, base_h=110):\n"
                f"    START_RELY, END_RELY = 1.35, 0.5\n"
                f"    START_W, START_H = 90, 80\n"
                f"\n"
                f'    card.place_configure(relx=0.5, rely=START_RELY,'
                f' anchor="center")\n'
                f"    card.configure(\n"
                f"        width=START_W, height=START_H, fg_color=START_COLOR\n"
                f"    )\n"
                f"\n"
                f"    def step(t):\n"
                f"        card.place_configure(rely=lerp(START_RELY, END_RELY, t))\n"
                f"        card.configure(\n"
                f"            fg_color=lerp_color_hsl(\n"
                f"                START_COLOR, BASE_COLOR, max(0.0, min(1.0, t))\n"
                f"            ),\n"
                f"            width=int(lerp(START_W, base_w, t)),\n"
                f"            height=int(lerp(START_H, base_h, t)),\n"
                f"        )\n"
                f"\n"
                f"    Tween(card, {duration}, {easing_name}, step).start()"
            )
        else:  # Stagger
            body = (
                f"BASE_COLOR = '#1f6aa5'\n"
                f"START_COLOR = '#2d2d30'\n"
                f"\n"
                f"\n"
                f"def animate_stagger(parent, n=5, item_size=60, gap_ms=80):\n"
                f"    spacing = 0.14\n"
                f"    start_relx = 0.5 - spacing * (n - 1) / 2\n"
                f"    items = []\n"
                f"    for i in range(n):\n"
                f"        f = ctk.CTkFrame(\n"
                f"            parent, width=item_size, height=item_size,\n"
                f"            fg_color=START_COLOR, corner_radius=8,\n"
                f"        )\n"
                f"        f.place(\n"
                f'            relx=start_relx + i * spacing, rely=1.3,'
                f' anchor="center",\n'
                f"        )\n"
                f"        items.append(f)\n"
                f"\n"
                f"    def make_step(f):\n"
                f"        def step(t):\n"
                f"            f.place_configure(rely=lerp(1.3, 0.5, t))\n"
                f"            f.configure(\n"
                f"                fg_color=lerp_color_hsl(\n"
                f"                    START_COLOR, BASE_COLOR,\n"
                f"                    max(0.0, min(1.0, t)),\n"
                f"                )\n"
                f"            )\n"
                f"        return step\n"
                f"\n"
                f"    for i, frame in enumerate(items):\n"
                f"        parent.after(\n"
                f"            i * gap_ms,\n"
                f"            lambda step=make_step(frame): Tween(\n"
                f"                parent, {duration}, {easing_name}, step\n"
                f"            ).start(),\n"
                f"        )"
            )

        if name == "Stagger":
            main_block = (
                "    ctk.set_appearance_mode('dark')\n"
                "    app = ctk.CTk()\n"
                "    app.geometry('600x300')\n"
                "    stage = ctk.CTkFrame(app, fg_color='#252526')\n"
                "    stage.pack(fill='both', expand=True, padx=12, pady=12)\n"
                "    app.after(100, lambda: animate_stagger(stage))\n"
                "    app.mainloop()"
            )
        else:
            main_block = (
                "    ctk.set_appearance_mode('dark')\n"
                "    app = ctk.CTk()\n"
                "    app.geometry('500x260')\n"
                "    card = ctk.CTkFrame(\n"
                "        app, width=140, height=110,\n"
                "        fg_color='#1f6aa5', corner_radius=12,\n"
                "    )\n"
                "    card.place(relx=0.5, rely=0.5, anchor='center')\n"
                "    app.after(200, lambda: animate_card(card))\n"
                "    app.mainloop()"
            )

        return self._assemble_module(
            title=title,
            settings=settings,
            body=body,
            main_block=main_block,
            easings_needed=easings_needed,
            needs_math=needs_math,
            needs_colorsys=needs_colorsys,
            extra_helpers=extra_helpers,
        )

    # ---- loaders code generator ------------------------------------------

    def _generate_loader_code(self, name):
        easing_name = self.easing_var.get()
        duration = self._duration()

        title = (
            f"Loading indicator — {name} (generated by Transitions Demo)."
        )

        if name == "Progress":
            settings = {
                "Indicator": name,
                "Easing": easing_name,
                "Duration": f"{duration}s",
            }
            body = (
                f"def animate_progress(bar):\n"
                f"    bar.set(0)\n"
                f"\n"
                f"    def step(t):\n"
                f"        bar.set(max(0.0, min(1.0, t)))\n"
                f"\n"
                f"    Tween(bar, {duration}, {easing_name}, step).start()"
            )
            main_block = (
                "    ctk.set_appearance_mode('dark')\n"
                "    app = ctk.CTk()\n"
                "    app.geometry('500x180')\n"
                "    bar = ctk.CTkProgressBar(app, width=320, height=14)\n"
                "    bar.set(0)\n"
                "    bar.place(relx=0.5, rely=0.5, anchor='center')\n"
                "    app.after(300, lambda: animate_progress(bar))\n"
                "    app.mainloop()"
            )
            return self._assemble_module(
                title=title,
                settings=settings,
                body=body,
                main_block=main_block,
                easings_needed={easing_name},
            )

        # Canvas-based loaders all use linear easing and run for 3 seconds
        # by default (looping shapes inside one tween).
        settings = {
            "Indicator": name,
            "Easing": "linear (sine/loop driven)",
            "Duration": f"{self.LOADER_DURATION}s",
        }

        if name == "Pulse":
            body = (
                "def animate_pulse(canvas, fg='#1f6aa5', duration=3.0):\n"
                "    canvas.delete('all')\n"
                "    canvas.update_idletasks()\n"
                "    cx = canvas.winfo_width() // 2\n"
                "    cy = canvas.winfo_height() // 2\n"
                "    base_r = 14\n"
                "    cid = canvas.create_oval(\n"
                "        cx - base_r, cy - base_r,"
                " cx + base_r, cy + base_r,\n"
                "        fill=fg, outline='',\n"
                "    )\n"
                "\n"
                "    def step(t):\n"
                "        pulse = (math.sin(t * 3 * 2 * math.pi) + 1) / 2\n"
                "        r = base_r * (0.5 + pulse * 0.5)\n"
                "        canvas.coords(cid, cx - r, cy - r, cx + r, cy + r)\n"
                "\n"
                "    Tween(canvas, duration, linear, step).start()"
            )
            entry = "animate_pulse(canvas)"
        elif name == "Arc":
            body = (
                "def animate_arc(canvas, fg='#1f6aa5', duration=3.0):\n"
                "    canvas.delete('all')\n"
                "    canvas.update_idletasks()\n"
                "    cx = canvas.winfo_width() // 2\n"
                "    cy = canvas.winfo_height() // 2\n"
                "    r = 18\n"
                "    arc_id = canvas.create_arc(\n"
                "        cx - r, cy - r, cx + r, cy + r,\n"
                "        start=0, extent=270,\n"
                "        outline=fg, width=4, style='arc',\n"
                "    )\n"
                "\n"
                "    def step(t):\n"
                "        angle = -(t * 3 * 360) % 360\n"
                "        canvas.itemconfigure(arc_id, start=angle)\n"
                "\n"
                "    Tween(canvas, duration, linear, step).start()"
            )
            entry = "animate_arc(canvas)"
        elif name == "Three Dots":
            body = (
                "def animate_three_dots(canvas, fg='#1f6aa5', duration=3.0):\n"
                "    canvas.delete('all')\n"
                "    canvas.update_idletasks()\n"
                "    w = canvas.winfo_width()\n"
                "    h = canvas.winfo_height()\n"
                "    cy = h // 2\n"
                "    dot_r = 6\n"
                "    spacing = 22\n"
                "    cx_start = w // 2 - spacing\n"
                "    dots = []\n"
                "    for i in range(3):\n"
                "        cx = cx_start + i * spacing\n"
                "        d = canvas.create_oval(\n"
                "            cx - dot_r, cy - dot_r,"
                " cx + dot_r, cy + dot_r,\n"
                "            fill=fg, outline='',\n"
                "        )\n"
                "        dots.append((d, cx, cy))\n"
                "\n"
                "    AMP = 8\n"
                "    CYCLES = 4\n"
                "\n"
                "    def step(t):\n"
                "        for i, (did, base_x, base_y) in enumerate(dots):\n"
                "            phase = (\n"
                "                t * CYCLES * 2 * math.pi\n"
                "                - i * (2 * math.pi / 3)\n"
                "            )\n"
                "            offset = max(0, math.sin(phase)) * AMP\n"
                "            canvas.coords(\n"
                "                did,\n"
                "                base_x - dot_r, base_y - offset - dot_r,\n"
                "                base_x + dot_r, base_y - offset + dot_r,\n"
                "            )\n"
                "\n"
                "    Tween(canvas, duration, linear, step).start()"
            )
            entry = "animate_three_dots(canvas)"
        else:  # Shimmer
            body = (
                "def animate_shimmer(\n"
                "    canvas, base='#3a3a3a', highlight='#5a5a5a', duration=3.0,\n"
                "):\n"
                "    canvas.delete('all')\n"
                "    canvas.update_idletasks()\n"
                "    w = canvas.winfo_width()\n"
                "    h = canvas.winfo_height()\n"
                "    margin = 24\n"
                "    card_x1 = margin\n"
                "    card_x2 = w - margin\n"
                "    card_y1 = h // 2 - 12\n"
                "    card_y2 = h // 2 + 12\n"
                "    canvas.create_rectangle(\n"
                "        card_x1, card_y1, card_x2, card_y2,\n"
                "        fill=base, outline='',\n"
                "    )\n"
                "    BAND_W = 60\n"
                "    band = canvas.create_rectangle(\n"
                "        card_x1, card_y1, card_x1, card_y2,\n"
                "        fill=highlight, outline='',\n"
                "    )\n"
                "    card_w = card_x2 - card_x1\n"
                "\n"
                "    def step(t):\n"
                "        cycle_t = (t * 2) % 1\n"
                "        x = card_x1 + cycle_t * (card_w + BAND_W) - BAND_W\n"
                "        x_end = x + BAND_W\n"
                "        x_clamped = max(card_x1, x)\n"
                "        x_end_clamped = min(card_x2, x_end)\n"
                "        if x_clamped < x_end_clamped:\n"
                "            canvas.coords(\n"
                "                band, x_clamped, card_y1,\n"
                "                x_end_clamped, card_y2,\n"
                "            )\n"
                "        else:\n"
                "            canvas.coords(band, card_x1, card_y1, card_x1, card_y2)\n"
                "\n"
                "    Tween(canvas, duration, linear, step).start()"
            )
            entry = "animate_shimmer(canvas)"

        body = "import tkinter as tk\n\n\n" + body
        main_block = (
            "    ctk.set_appearance_mode('dark')\n"
            "    app = ctk.CTk()\n"
            "    app.geometry('400x180')\n"
            "    canvas = tk.Canvas(\n"
            "        app, bg='#252526', highlightthickness=0, bd=0,\n"
            "    )\n"
            "    canvas.pack(fill='both', expand=True)\n"
            f"    app.after(300, lambda: {entry})\n"
            "    app.mainloop()"
        )

        return self._assemble_module(
            title=title,
            settings=settings,
            body=body,
            main_block=main_block,
            easings_needed={"linear"},
            needs_math=True,
        )

    # ---- toast code generator --------------------------------------------

    TOAST_ACCENTS = {
        "Info": "#4a9eff",
        "Success": "#6fcf6a",
        "Warning": "#e0a44a",
        "Error": "#d9534f",
    }

    TOAST_MESSAGES = {
        "Info": "Info: this is informational",
        "Success": "Success: action completed",
        "Warning": "Warning: something to check",
        "Error": "Error: something went wrong",
    }

    def _generate_toast_code(self, name):
        easing_name = self.easing_var.get()
        duration = self._duration()
        position = self.toast_position_var.get()
        accent = self.TOAST_ACCENTS.get(name, "#4a9eff")
        message = self.TOAST_MESSAGES.get(name, name)

        title = f"Toast notification — {name} (generated by Transitions Demo)."
        settings = {
            "Type": name,
            "Position": position,
            "Easing": easing_name,
            "Duration": f"{duration}s",
        }

        body = (
            "import tkinter as tk\n"
            "\n"
            "\n"
            "TOAST_W = 280\n"
            "TOAST_H = 60\n"
            "TOAST_MARGIN = 16\n"
            "TOAST_SPACING = 8\n"
            "TOAST_HOLD_MS = 2000\n"
            "TOAST_SLIDE_OFFSET = 140\n"
            "\n"
            "_toast_stacks = {}\n"
            "\n"
            "\n"
            "def _toast_slot(parent, position, index):\n"
            "    parent.update_idletasks()\n"
            "    win_x = parent.winfo_x()\n"
            "    win_y = parent.winfo_y()\n"
            "    win_w = parent.winfo_width()\n"
            "    win_h = parent.winfo_height()\n"
            "\n"
            "    if 'Right' in position:\n"
            "        x = win_x + win_w - TOAST_W - TOAST_MARGIN\n"
            "    elif 'Left' in position:\n"
            "        x = win_x + TOAST_MARGIN\n"
            "    else:\n"
            "        x = win_x + (win_w - TOAST_W) // 2\n"
            "\n"
            "    if 'Bottom' in position:\n"
            "        y = (\n"
            "            win_y + win_h - TOAST_H - TOAST_MARGIN\n"
            "            - index * (TOAST_H + TOAST_SPACING)\n"
            "        )\n"
            "    else:\n"
            "        y = (\n"
            "            win_y + TOAST_MARGIN\n"
            "            + index * (TOAST_H + TOAST_SPACING)\n"
            "        )\n"
            "    return x, y\n"
            "\n"
            "\n"
            "def _toast_start(position, target_x, target_y):\n"
            "    offset = TOAST_SLIDE_OFFSET\n"
            "    if 'Right' in position:\n"
            "        return target_x + offset, target_y\n"
            "    if 'Left' in position:\n"
            "        return target_x - offset, target_y\n"
            "    if position == 'Top-Center':\n"
            "        return target_x, target_y - offset\n"
            "    return target_x, target_y + offset\n"
            "\n"
            "\n"
            "def _dismiss_toast(toast):\n"
            "    position = getattr(toast, '_toast_position', None)\n"
            "    if position is not None:\n"
            "        stack = _toast_stacks.get(position, [])\n"
            "        if toast in stack:\n"
            "            stack.remove(toast)\n"
            "    try:\n"
            "        toast.destroy()\n"
            "    except tk.TclError:\n"
            "        pass\n"
            "\n"
            "\n"
            f"def show_toast(parent, message, accent='{accent}',"
            f" position='{position}'):\n"
            "    stack = _toast_stacks.setdefault(position, [])\n"
            "    used = {\n"
            "        t._toast_index for t in stack if hasattr(t, '_toast_index')\n"
            "    }\n"
            "    index = 0\n"
            "    while index in used:\n"
            "        index += 1\n"
            "\n"
            "    target_x, target_y = _toast_slot(parent, position, index)\n"
            "    start_x, start_y = _toast_start(position, target_x, target_y)\n"
            "\n"
            "    toast = tk.Toplevel(parent)\n"
            "    toast.overrideredirect(True)\n"
            "    toast.attributes('-alpha', 0.0)\n"
            "    toast.attributes('-topmost', True)\n"
            "    toast.configure(bg='#3c3c3c')\n"
            "    toast._toast_index = index\n"
            "    toast._toast_position = position\n"
            "\n"
            "    inner = tk.Frame(toast, bg='#252526')\n"
            "    inner.pack(fill='both', expand=True, padx=1, pady=1)\n"
            "    tk.Frame(inner, bg=accent, width=4).pack(side='left', fill='y')\n"
            "    ctk.CTkLabel(\n"
            "        inner, text=message,\n"
            "        font=('Segoe UI', 13, 'bold'),\n"
            "        text_color=accent, anchor='w', fg_color='#252526',\n"
            "    ).pack(side='left', padx=12, pady=10, fill='both', expand=True)\n"
            "\n"
            "    toast.geometry(f'{TOAST_W}x{TOAST_H}+{start_x}+{start_y}')\n"
            "    stack.append(toast)\n"
            "\n"
            "    def slide_in(t):\n"
            "        cx = int(lerp(start_x, target_x, t))\n"
            "        cy = int(lerp(start_y, target_y, t))\n"
            "        toast.geometry(f'{TOAST_W}x{TOAST_H}+{cx}+{cy}')\n"
            "        toast.attributes('-alpha', min(t * 1.5, 1.0))\n"
            "\n"
            "    def slide_out():\n"
            "        out_x, out_y = _toast_start(position, target_x, target_y)\n"
            "\n"
            "        def step(t):\n"
            "            cx = int(lerp(target_x, out_x, t))\n"
            "            cy = int(lerp(target_y, out_y, t))\n"
            "            toast.geometry(f'{TOAST_W}x{TOAST_H}+{cx}+{cy}')\n"
            "            toast.attributes('-alpha', 1 - t)\n"
            "\n"
            "        Tween(\n"
            "            toast, 0.3, ease_in, step,\n"
            "            on_done=lambda: _dismiss_toast(toast),\n"
            "        ).start()\n"
            "\n"
            f"    Tween(\n"
            f"        toast, {duration}, {easing_name}, slide_in,\n"
            f"        on_done=lambda: toast.after(TOAST_HOLD_MS, slide_out),\n"
            f"    ).start()\n"
            "    return toast"
        )

        main_block = (
            "    ctk.set_appearance_mode('dark')\n"
            "    app = ctk.CTk()\n"
            "    app.geometry('600x320')\n"
            "    ctk.CTkButton(\n"
            f"        app, text='Show {name}',\n"
            f"        command=lambda: show_toast(app, '{message}'),\n"
            "    ).place(relx=0.5, rely=0.5, anchor='center')\n"
            "    app.mainloop()"
        )

        return self._assemble_module(
            title=title,
            settings=settings,
            body=body,
            main_block=main_block,
            easings_needed={easing_name, "ease_in"},
        )

    # ---- popup code generator --------------------------------------------

    POPUP_PREAMBLE = (
        "POPUP_W, POPUP_H = 400, 140\n"
        "\n"
        "\n"
        "def _make_popup(parent, title):\n"
        "    parent.update_idletasks()\n"
        "    px = parent.winfo_rootx()\n"
        "    py = parent.winfo_rooty()\n"
        "    pw = parent.winfo_width()\n"
        "    ph = parent.winfo_height()\n"
        "    tx = px + (pw - POPUP_W) // 2\n"
        "    ty = py + (ph - POPUP_H) // 2\n"
        "\n"
        "    top = ctk.CTkToplevel(parent)\n"
        "    top.title(title)\n"
        "    top.attributes('-alpha', 0.0)\n"
        "    top.transient(parent)\n"
        "    ctk.CTkLabel(\n"
        "        top, text=title, font=('Segoe UI', 16, 'bold'),\n"
        "    ).pack(expand=True, fill='both')\n"
        "\n"
        "    # Force dark titlebar (Windows DWM defers NC paint past the\n"
        "    # first map; only withdraw+deiconify reliably triggers it).\n"
        "    def _kick():\n"
        "        try:\n"
        "            top.update_idletasks()\n"
        "            top.withdraw()\n"
        "            top.update_idletasks()\n"
        "            top.deiconify()\n"
        "        except tk.TclError:\n"
        "            pass\n"
        "    top.after(50, _kick)\n"
        "    return top, tx, ty"
    )

    def _generate_popup_code(self, name):
        easing_name = self.easing_var.get()
        duration = self._duration()

        title = f"Popup animation — {name} (generated by Transitions Demo)."
        settings = {
            "Animation": name,
            "Easing": easing_name,
            "Duration": f"{duration}s",
        }

        if name == "Fade":
            anim = (
                f"def show_popup(parent, title='Popup'):\n"
                f"    top, tx, ty = _make_popup(parent, title)\n"
                f"    top.geometry(f'{{POPUP_W}}x{{POPUP_H}}+{{tx}}+{{ty}}')\n"
                f"    Tween(\n"
                f"        top, {duration}, {easing_name},\n"
                f"        lambda t: top.attributes('-alpha', min(t, 1.0)),\n"
                f"    ).start()\n"
                f"    return top"
            )
        elif name == "Pop":
            anim = (
                f"def show_popup(parent, title='Popup'):\n"
                f"    top, tx, ty = _make_popup(parent, title)\n"
                f"    sw = int(POPUP_W * 0.82)\n"
                f"    sh = int(POPUP_H * 0.82)\n"
                f"    top.geometry(\n"
                f"        f'{{sw}}x{{sh}}+'\n"
                f"        f'{{tx + (POPUP_W - sw) // 2}}+'\n"
                f"        f'{{ty + (POPUP_H - sh) // 2}}'\n"
                f"    )\n"
                f"\n"
                f"    def step(t):\n"
                f"        w = int(lerp(sw, POPUP_W, t))\n"
                f"        h = int(lerp(sh, POPUP_H, t))\n"
                f"        top.geometry(\n"
                f"            f'{{w}}x{{h}}+'\n"
                f"            f'{{tx + (POPUP_W - w) // 2}}+'\n"
                f"            f'{{ty + (POPUP_H - h) // 2}}'\n"
                f"        )\n"
                f"        top.attributes('-alpha', min(t, 1.0))\n"
                f"\n"
                f"    Tween(top, {duration}, {easing_name}, step).start()\n"
                f"    return top"
            )
        elif name == "Slide-Down":
            anim = (
                f"def show_popup(parent, title='Popup'):\n"
                f"    top, tx, ty = _make_popup(parent, title)\n"
                f"    start_y = ty - 240\n"
                f"    top.geometry(f'{{POPUP_W}}x{{POPUP_H}}+{{tx}}+{{start_y}}')\n"
                f"\n"
                f"    def step(t):\n"
                f"        y = int(lerp(start_y, ty, t))\n"
                f"        top.geometry(f'{{POPUP_W}}x{{POPUP_H}}+{{tx}}+{{y}}')\n"
                f"        top.attributes('-alpha', min(t * 1.6, 1.0))\n"
                f"\n"
                f"    Tween(top, {duration}, {easing_name}, step).start()\n"
                f"    return top"
            )
        elif name == "Slide-Up":
            anim = (
                f"def show_popup(parent, title='Popup'):\n"
                f"    top, tx, ty = _make_popup(parent, title)\n"
                f"    start_y = ty + 240\n"
                f"    top.geometry(f'{{POPUP_W}}x{{POPUP_H}}+{{tx}}+{{start_y}}')\n"
                f"\n"
                f"    def step(t):\n"
                f"        y = int(lerp(start_y, ty, t))\n"
                f"        top.geometry(f'{{POPUP_W}}x{{POPUP_H}}+{{tx}}+{{y}}')\n"
                f"        top.attributes('-alpha', min(t * 1.6, 1.0))\n"
                f"\n"
                f"    Tween(top, {duration}, {easing_name}, step).start()\n"
                f"    return top"
            )
        elif name == "Slide-Right":
            anim = (
                f"def show_popup(parent, title='Popup'):\n"
                f"    top, tx, ty = _make_popup(parent, title)\n"
                f"    start_x = tx - 300\n"
                f"    top.geometry(f'{{POPUP_W}}x{{POPUP_H}}+{{start_x}}+{{ty}}')\n"
                f"\n"
                f"    def step(t):\n"
                f"        x = int(lerp(start_x, tx, t))\n"
                f"        top.geometry(f'{{POPUP_W}}x{{POPUP_H}}+{{x}}+{{ty}}')\n"
                f"        top.attributes('-alpha', min(t * 1.6, 1.0))\n"
                f"\n"
                f"    Tween(top, {duration}, {easing_name}, step).start()\n"
                f"    return top"
            )
        else:  # Zoom
            anim = (
                f"def show_popup(parent, title='Popup'):\n"
                f"    top, tx, ty = _make_popup(parent, title)\n"
                f"    sw = int(POPUP_W * 0.4)\n"
                f"    sh = int(POPUP_H * 0.4)\n"
                f"    top.geometry(\n"
                f"        f'{{sw}}x{{sh}}+'\n"
                f"        f'{{tx + (POPUP_W - sw) // 2}}+'\n"
                f"        f'{{ty + (POPUP_H - sh) // 2}}'\n"
                f"    )\n"
                f"\n"
                f"    def step(t):\n"
                f"        w = int(lerp(sw, POPUP_W, t))\n"
                f"        h = int(lerp(sh, POPUP_H, t))\n"
                f"        top.geometry(\n"
                f"            f'{{w}}x{{h}}+'\n"
                f"            f'{{tx + (POPUP_W - w) // 2}}+'\n"
                f"            f'{{ty + (POPUP_H - h) // 2}}'\n"
                f"        )\n"
                f"        top.attributes('-alpha', min(t, 1.0))\n"
                f"\n"
                f"    Tween(top, {duration}, {easing_name}, step).start()\n"
                f"    return top"
            )

        body = (
            "import tkinter as tk\n\n\n"
            + self.POPUP_PREAMBLE
            + "\n\n\n"
            + anim
        )

        main_block = (
            "    ctk.set_appearance_mode('dark')\n"
            "    app = ctk.CTk()\n"
            "    app.geometry('600x300')\n"
            "    ctk.CTkButton(\n"
            "        app, text='Show popup',\n"
            "        command=lambda: show_popup(app, 'Hello!'),\n"
            "    ).place(relx=0.5, rely=0.5, anchor='center')\n"
            "    app.mainloop()"
        )

        return self._assemble_module(
            title=title,
            settings=settings,
            body=body,
            main_block=main_block,
            easings_needed={easing_name},
        )

    # ---- text code generator ---------------------------------------------

    def _generate_text_code(self, name):
        easing_name = self.easing_var.get()
        duration = self._duration()

        easings_needed = {easing_name}
        needs_math = name == "Wave"
        needs_colorsys = name == "Fade Words"
        extra_helpers = [self.HSL_HELPER] if needs_colorsys else None

        # Wave uses linear; Fade Words uses ease_out for per-word fade.
        if name == "Wave":
            easings_needed.add("linear")
        if name == "Fade Words":
            easings_needed.add("ease_out")

        title = f"Text animation — {name} (generated by Transitions Demo)."
        settings = {
            "Animation": name,
            "Easing": easing_name,
            "Duration": f"{duration}s",
        }

        if name == "Typewriter":
            body = (
                f"def animate_typewriter(label, text):\n"
                f'    label.configure(text="")\n'
                f"\n"
                f"    def step(t):\n"
                f"        n = max(0, min(int(len(text) * t + 0.5), len(text)))\n"
                f"        label.configure(text=text[:n])\n"
                f"\n"
                f"    Tween(\n"
                f"        label, {duration}, {easing_name}, step,\n"
                f"        on_done=lambda: label.configure(text=text),\n"
                f"    ).start()"
            )
            main_block = (
                "    ctk.set_appearance_mode('dark')\n"
                "    app = ctk.CTk()\n"
                "    app.geometry('500x180')\n"
                "    label = ctk.CTkLabel(\n"
                "        app, text='', font=('Segoe UI', 16, 'bold'),\n"
                "    )\n"
                "    label.place(relx=0.5, rely=0.5, anchor='center')\n"
                "    app.after(\n"
                "        300,\n"
                "        lambda: animate_typewriter(label, 'Hello, world!'),\n"
                "    )\n"
                "    app.mainloop()"
            )
        elif name == "Counter":
            body = (
                f"def animate_counter(label, end_value, start_value=0):\n"
                f"    label.configure(text=str(start_value))\n"
                f"\n"
                f"    def step(t):\n"
                f"        label.configure(\n"
                f"            text=str(int(lerp(start_value, end_value, t)))\n"
                f"        )\n"
                f"\n"
                f"    Tween(\n"
                f"        label, {duration}, {easing_name}, step,\n"
                f"        on_done=lambda: label.configure(text=str(end_value)),\n"
                f"    ).start()"
            )
            main_block = (
                "    ctk.set_appearance_mode('dark')\n"
                "    app = ctk.CTk()\n"
                "    app.geometry('400x180')\n"
                "    label = ctk.CTkLabel(\n"
                "        app, text='0', font=('Segoe UI', 28, 'bold'),\n"
                "    )\n"
                "    label.place(relx=0.5, rely=0.5, anchor='center')\n"
                "    app.after(300, lambda: animate_counter(label, 100))\n"
                "    app.mainloop()"
            )
        elif name == "Wave":
            body = (
                f"import tkinter as tk\n"
                f"import tkinter.font as tkfont\n"
                f"\n"
                f"\n"
                f"def animate_wave(\n"
                f"    canvas, text, fg='#cccccc',\n"
                f"    family='Segoe UI', size=16, weight='bold',\n"
                f"):\n"
                f"    canvas.delete('all')\n"
                f"    canvas.update_idletasks()\n"
                f"    f = tkfont.Font(family=family, size=size, weight=weight)\n"
                f"    char_widths = [f.measure(ch) for ch in text]\n"
                f"    total_w = sum(char_widths)\n"
                f"    stage_w = canvas.winfo_width()\n"
                f"    stage_h = canvas.winfo_height()\n"
                f"    cy = stage_h // 2\n"
                f"    cur_x = (stage_w - total_w) // 2\n"
                f"    char_ids = []\n"
                f"    for i, ch in enumerate(text):\n"
                f"        cid = canvas.create_text(\n"
                f"            cur_x + char_widths[i] // 2, cy,\n"
                f"            text=ch, font=(family, size, weight),\n"
                f"            fill=fg, anchor='center',\n"
                f"        )\n"
                f"        char_ids.append((cid, cur_x + char_widths[i] // 2, cy))\n"
                f"        cur_x += char_widths[i]\n"
                f"\n"
                f"    AMP = 10\n"
                f"\n"
                f"    def step(t):\n"
                f"        for i, (cid, base_x, base_y) in enumerate(char_ids):\n"
                f"            offset = (\n"
                f"                math.sin(t * math.pi * 4 + i * 0.4)\n"
                f"                * AMP * (1 - t)\n"
                f"            )\n"
                f"            canvas.coords(cid, base_x, base_y + offset)\n"
                f"\n"
                f"    Tween(canvas, {duration}, linear, step).start()"
            )
            main_block = (
                "    ctk.set_appearance_mode('dark')\n"
                "    app = ctk.CTk()\n"
                "    app.geometry('500x180')\n"
                "    canvas = tk.Canvas(\n"
                "        app, bg='#252526', highlightthickness=0, bd=0,\n"
                "    )\n"
                "    canvas.pack(fill='both', expand=True)\n"
                "    app.after(300, lambda: animate_wave(canvas, 'Animated text'))\n"
                "    app.mainloop()"
            )
        else:  # Fade Words
            body = (
                f"BG_COLOR = '#252526'\n"
                f"FG_COLOR = '#cccccc'\n"
                f"\n"
                f"\n"
                f"def animate_fade_words(parent, text, gap_ms=120, per_word_dur=0.5):\n"
                f"    for child in parent.winfo_children():\n"
                f"        child.destroy()\n"
                f"    container = ctk.CTkFrame(parent, fg_color='transparent')\n"
                f"    container.place(relx=0.5, rely=0.5, anchor='center')\n"
                f"\n"
                f"    labels = []\n"
                f"    for word in text.split():\n"
                f"        lbl = ctk.CTkLabel(\n"
                f"            container, text=word,\n"
                f"            font=('Segoe UI', 16, 'bold'), text_color=BG_COLOR,\n"
                f"        )\n"
                f"        lbl.pack(side='left', padx=4)\n"
                f"        labels.append(lbl)\n"
                f"\n"
                f"    def make_step(label):\n"
                f"        def step(t):\n"
                f"            label.configure(\n"
                f"                text_color=lerp_color_hsl(\n"
                f"                    BG_COLOR, FG_COLOR, max(0.0, min(1.0, t))\n"
                f"                )\n"
                f"            )\n"
                f"        return step\n"
                f"\n"
                f"    for i, lbl in enumerate(labels):\n"
                f"        parent.after(\n"
                f"            i * gap_ms,\n"
                f"            lambda step=make_step(lbl): Tween(\n"
                f"                parent, per_word_dur, ease_out, step\n"
                f"            ).start(),\n"
                f"        )"
            )
            main_block = (
                "    ctk.set_appearance_mode('dark')\n"
                "    app = ctk.CTk()\n"
                "    app.geometry('600x180')\n"
                "    stage = ctk.CTkFrame(app, fg_color='#252526')\n"
                "    stage.pack(fill='both', expand=True, padx=12, pady=12)\n"
                "    app.after(\n"
                "        200,\n"
                "        lambda: animate_fade_words(stage, 'Words fade in one by one'),\n"
                "    )\n"
                "    app.mainloop()"
            )

        return self._assemble_module(
            title=title,
            settings=settings,
            body=body,
            main_block=main_block,
            easings_needed=easings_needed,
            needs_math=needs_math,
            needs_colorsys=needs_colorsys,
            extra_helpers=extra_helpers,
        )
