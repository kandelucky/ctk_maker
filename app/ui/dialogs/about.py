"""Help → About modal."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from app.ui.dialogs._base import DarkDialog
from app.ui.dialogs._colors import (
    _ABT_BG, _ABT_DIM, _ABT_FG, _ABT_LINK, _ABT_SEP,
)
from app.ui.system_fonts import ui_font


_BUILT_WITH = [
    ("CustomTkinter", "https://github.com/TomSchimansky/CustomTkinter", "MIT"),
    ("Lucide Icons",  "https://lucide.dev",                             "MIT"),
    ("Pillow",        "https://pypi.org/project/Pillow/",               "HPND"),
    ("tkextrafont",   "https://pypi.org/project/tkextrafont/",          "MIT"),
]

_PROJECT_LINKS = [
    ("Source", "https://github.com/kandelucky/ctk_maker"),
    ("Discussions", "https://github.com/kandelucky/ctk_maker/discussions"),
]
_BMC_URL = "https://buymeacoffee.com/Kandelucky_dev"
# BMC official button palette — copied off the embed snippet so the
# in-app button reads as the same brand visual.
_BMC_BG = "#FFDD00"
_BMC_FG = "#000000"
_BMC_OUTLINE = "#000000"


class AboutDialog(DarkDialog):
    def __init__(self, parent, app_version: str = ""):
        super().__init__(parent)
        self.title("About CTkMaker")
        self._build(app_version)
        # Fixed size — height bumped to accommodate the new Links
        # section + Buy me a coffee button.
        W, H = 480, 540
        self.place_centered(W, H, parent)
        self.lift()
        self.focus_set()
        self.reveal()

    def _build(self, version: str) -> None:
        import webbrowser
        pad: dict[str, Any] = {"padx": 24}

        tk.Frame(self, bg=_ABT_BG, height=16).pack()
        tk.Label(
            self, text="CTkMaker",
            bg=_ABT_BG, fg=_ABT_FG, font=ui_font(16, "bold"),
        ).pack(**pad)
        tk.Label(
            self, text=version or "",
            bg=_ABT_BG, fg=_ABT_DIM, font=ui_font(10),
        ).pack(**pad, pady=(2, 0))
        tk.Label(
            self,
            text="Design CustomTkinter, visually — for free.",
            bg=_ABT_BG, fg=_ABT_DIM, font=ui_font(10),
            justify="center",
        ).pack(padx=24, pady=(10, 0))

        tk.Frame(self, bg=_ABT_SEP, height=1).pack(fill="x", padx=24, pady=12)

        tk.Label(
            self, text="Built with",
            bg=_ABT_BG, fg=_ABT_FG, font=ui_font(10, "bold"),
        ).pack(**pad, pady=(0, 6))

        for name, url, lic in _BUILT_WITH:
            row = tk.Frame(self, bg=_ABT_BG)
            row.pack(fill="x", padx=24, pady=1)
            tk.Label(
                row, text=f"{name}  ", bg=_ABT_BG, fg=_ABT_FG,
                font=ui_font(10), anchor="w",
            ).pack(side="left")
            link = tk.Label(
                row, text=url, bg=_ABT_BG, fg=_ABT_LINK,
                font=ui_font(10, "underline"), cursor="hand2",
            )
            link.pack(side="left")
            link.bind("<Button-1>", lambda _e, u=url: webbrowser.open(u))
            tk.Label(
                row, text=f"  ({lic})", bg=_ABT_BG, fg=_ABT_DIM,
                font=ui_font(9),
            ).pack(side="left")

        tk.Frame(self, bg=_ABT_SEP, height=1).pack(fill="x", padx=24, pady=12)

        tk.Label(
            self, text="Links",
            bg=_ABT_BG, fg=_ABT_FG, font=ui_font(10, "bold"),
        ).pack(**pad, pady=(0, 6))
        for name, url in _PROJECT_LINKS:
            row = tk.Frame(self, bg=_ABT_BG)
            row.pack(fill="x", padx=24, pady=1)
            tk.Label(
                row, text=f"{name}  ", bg=_ABT_BG, fg=_ABT_FG,
                font=ui_font(10), anchor="w",
            ).pack(side="left")
            link = tk.Label(
                row, text=url, bg=_ABT_BG, fg=_ABT_LINK,
                font=ui_font(10, "underline"), cursor="hand2",
            )
            link.pack(side="left")
            link.bind("<Button-1>", lambda _e, u=url: webbrowser.open(u))

        # Buy me a coffee button — official BMC palette so the
        # in-app version visually matches the badge users see on
        # the website. The ☕ emoji rendered as a missing-glyph
        # box on some Windows default fonts; replaced with the
        # Lucide ``coffee`` PNG so the cup is reliably visible.
        # Tk doesn't have a Cookie-script font on Windows by
        # default, so we emulate the chunky BMC text with bold
        # Segoe UI.
        tk.Frame(self, bg=_ABT_BG, height=34).pack()
        bmc_row = tk.Frame(self, bg=_ABT_BG)
        bmc_row.pack(pady=(0, 4))
        from app.ui.icons import load_tk_icon
        coffee_img = load_tk_icon("coffee", size=18, color=_BMC_FG)
        bmc_btn = tk.Button(
            bmc_row,
            text="Buy me a coffee",
            image=coffee_img if coffee_img else "",
            compound="left",
            bg=_BMC_BG, fg=_BMC_FG,
            activebackground="#FFE54B", activeforeground=_BMC_FG,
            relief="solid", bd=1,
            highlightbackground=_BMC_OUTLINE,
            font=ui_font(11, "bold"),
            padx=18, pady=6, cursor="hand2",
            command=lambda: webbrowser.open(_BMC_URL),
        )
        # Retain the PhotoImage on the button so Tk doesn't GC the
        # icon when the local var goes out of scope.
        bmc_btn.image = coffee_img  # type: ignore[attr-defined]
        bmc_btn.pack()

        tk.Frame(self, bg=_ABT_BG, height=10).pack()
        btn = tk.Button(
            self, text="Close", command=self.destroy,
            bg="#3a3a3a", fg=_ABT_FG, activebackground="#4a4a4a",
            activeforeground=_ABT_FG, relief="flat", bd=0,
            font=ui_font(10), padx=20, pady=4, cursor="hand2",
        )
        btn.pack(pady=(10, 16))
