"""Splash shown while MainWindow is constructing.

Frameless Toplevel with logo + app name + version + status. Built
right after the MainWindow root is withdrawn so the user has
something to look at while toolbar/panels/fonts are wired up.
Destroyed right before StartupDialog appears.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk

from app import __version__
from app.core.screen import center_geometry
from app.ui.system_fonts import ui_font

SPLASH_W = 460
SPLASH_H = 280
BG = "#0d0d0d"
BORDER = "#1f1f1f"
TITLE_FG = "#ececec"
VERSION_FG = "#7a7a7a"
SUBTITLE_FG = "#6a6a6a"

LOGO_PATH = Path(__file__).resolve().parents[2] / "app" / "assets" / "icon.png"
LOGO_SIZE = 96


class SplashScreen(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        # Hide via alpha while the window is built — otherwise Windows
        # flashes the WM-default (white) background for one frame
        # before Tk paints the configured colours.
        self.attributes("-alpha", 0.0)
        self.overrideredirect(True)
        self.configure(bg=BORDER)

        geom = center_geometry(SPLASH_W, SPLASH_H)
        if geom is None:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = max(0, (sw - SPLASH_W) // 2)
            y = max(0, (sh - SPLASH_H) // 2)
            geom = f"{SPLASH_W}x{SPLASH_H}+{x}+{y}"
        self.geometry(geom)

        # 1px BORDER frame around an inner BG frame for a subtle outline
        # (overrideredirect strips the WM border).
        inner = tk.Frame(self, bg=BG, borderwidth=0)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        if LOGO_PATH.exists():
            try:
                img = Image.open(LOGO_PATH).resize(
                    (LOGO_SIZE, LOGO_SIZE), Image.LANCZOS,
                )
                self._logo = ImageTk.PhotoImage(img, master=self)
                tk.Label(
                    inner, image=self._logo, bg=BG, borderwidth=0,
                ).pack(pady=(40, 14))
            except Exception:
                pass

        tk.Label(
            inner, text="CTkMaker",
            bg=BG, fg=TITLE_FG, borderwidth=0,
            font=ui_font(18, "bold"),
        ).pack()
        tk.Label(
            inner, text=f"v{__version__}",
            bg=BG, fg=VERSION_FG, borderwidth=0,
            font=ui_font(10),
        ).pack(pady=(2, 0))
        tk.Label(
            inner, text="Loading...",
            bg=BG, fg=SUBTITLE_FG, borderwidth=0,
            font=ui_font(9),
        ).pack(pady=(10, 0))

        self.attributes("-topmost", True)
        self.lift()
        self.update_idletasks()
        self.attributes("-alpha", 1.0)
