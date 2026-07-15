"""Shared dark-theme tokens + helpers for the dialog package.

Visual language is TintKit-derived: every colour comes from one seed
per role (accent / danger / warn) via ``shades`` — change a seed and
the whole dialog family follows. ``flat_button`` and ``hero_header``
are the two building blocks every raw-tk dialog uses; ``dialog_scaling``
returns the CTk widget-scaling factor the raw-tk content must apply
itself (it sits outside CTk's DPI system, so without it dialogs render
visibly smaller than the CTk-scaled UI around them on non-100%
displays).

The ``_ABT_*`` names predate the token block and are kept for the
older dialogs that still read them.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from app.ui.system_fonts import ui_font

# ----------------------------------------------------------------------
# Seed → shades colour maths

ACCENT_SEED = "#8fae9b"
DANGER_SEED = "#c75d54"
WARN_SEED = "#d6a85c"


def mix(c1: str, c2: str, t: float) -> str:
    a = tuple(int(c1.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    b = tuple(int(c2.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % tuple(
        max(0, min(255, round(a[i] * (1 - t) + b[i] * t))) for i in range(3)
    )


def on_color(c: str) -> str:
    r, g, b = (int(c.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.55:
        return mix("#000000", c, 0.10)
    return mix("#ffffff", c, 0.06)


def shades(seed: str) -> tuple[str, str, str]:
    """(base, hover, on) for a button role from one seed colour."""
    return seed, mix(seed, "#ffffff", 0.14), on_color(seed)


# ----------------------------------------------------------------------
# Tokens

PANEL = "#1d1d1d"
LIFT = "#242424"
HOVER = "#2a2a2a"
FG = "#ededed"
FG_DIM = "#8a8a8a"

ACCENT, ACCENT_HOVER, ON_ACCENT = shades(ACCENT_SEED)
DANGER, DANGER_HOVER, ON_DANGER = shades(DANGER_SEED)
WARN, WARN_HOVER, ON_WARN = shades(WARN_SEED)

# Hero-bar colour per severity; the bar is the themed stand-in for the
# native severity icon (glyph icons render unreliably in the app font).
HERO = {
    "info": ACCENT,
    "question": ACCENT,
    "warning": WARN,
    "error": DANGER,
}

# Button roles → (bg, hover bg, fg).
BTN_COLORS = {
    "ghost": (LIFT, HOVER, FG),
    "accent": (ACCENT, ACCENT_HOVER, ON_ACCENT),
    "danger": (DANGER, DANGER_HOVER, ON_DANGER),
}

# Legacy names (pre-token dialogs read these).
_ABT_BG = PANEL
_ABT_FG = "#cccccc"
_ABT_DIM = "#888888"
_ABT_LINK = "#5bc0f8"
_ABT_SEP = "#3a3a3a"


# ----------------------------------------------------------------------
# Building blocks

def dialog_scaling(widget) -> float:
    """CTk widget-scaling factor for raw-tk dialog content."""
    try:
        return float(ctk.ScalingTracker.get_widget_scaling(widget))
    except Exception:
        return 1.0


def flat_button(
    parent, text: str, role: str, command, s: float = 1.0,
) -> tk.Button:
    """Flat TintKit-style button: ghost | accent | danger."""
    bg, hover, fg = BTN_COLORS[role]
    btn = tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
        relief="flat", bd=0, font=ui_font(round(10 * s)),
        padx=round(18 * s), pady=round(5 * s), cursor="hand2",
    )
    btn.bind("<Enter>", lambda _e: btn.configure(bg=hover))
    btn.bind("<Leave>", lambda _e: btn.configure(bg=bg))
    return btn


def hero_header(
    dialog, title: str, severity: str = "info", s: float = 1.0,
    bg: str = PANEL,
) -> tk.Frame:
    """Pack the hero line — severity bar + bold title — at the top of
    ``dialog``. Returns the header frame so callers can add to it."""
    head = tk.Frame(dialog, bg=bg)
    head.pack(fill="x", padx=round(18 * s), pady=(round(16 * s), 0))
    tk.Frame(
        head, bg=HERO.get(severity, ACCENT),
        width=max(3, round(3 * s)), height=round(20 * s),
    ).pack(side="left")
    tk.Label(
        head, text=title, bg=bg, fg=FG,
        font=ui_font(round(11 * s), "bold"),
    ).pack(side="left", padx=(round(10 * s), 0))
    return head
