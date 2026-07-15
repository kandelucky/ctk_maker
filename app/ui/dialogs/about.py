"""Help → About modal."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from app.ui.dialogs._base import DarkDialog
from app.ui.dialogs._colors import (
    _ABT_DIM,
    _ABT_FG,
    _ABT_LINK,
    _ABT_SEP,
    PANEL,
    dialog_scaling,
    flat_button,
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
        super().__init__(parent, fg_color=PANEL)
        self.title("About CTkMaker")
        self._s = dialog_scaling(self)
        self._build(app_version)
        # Fixed size — height bumped to accommodate the new Links
        # section + Buy me a coffee button.
        s = self._s
        self.place_centered(round(480 * s), round(540 * s), parent)
        self.lift()
        self.focus_set()
        self.reveal()

    def _build(self, version: str) -> None:
        import webbrowser
        s = self._s
        pad: dict[str, Any] = {"padx": round(24 * s)}

        tk.Frame(self, bg=PANEL, height=round(16 * s)).pack()
        tk.Label(
            self, text="CTkMaker",
            bg=PANEL, fg=_ABT_FG, font=ui_font(round(16 * s), "bold"),
        ).pack(**pad)
        tk.Label(
            self, text=version or "",
            bg=PANEL, fg=_ABT_DIM, font=ui_font(round(10 * s)),
        ).pack(**pad, pady=(round(2 * s), 0))
        tk.Label(
            self,
            text="Design CustomTkinter, visually — for free.",
            bg=PANEL, fg=_ABT_DIM, font=ui_font(round(10 * s)),
            justify="center",
        ).pack(padx=round(24 * s), pady=(round(10 * s), 0))

        tk.Frame(self, bg=_ABT_SEP, height=1).pack(
            fill="x", padx=round(24 * s), pady=round(12 * s),
        )

        tk.Label(
            self, text="Built with",
            bg=PANEL, fg=_ABT_FG, font=ui_font(round(10 * s), "bold"),
        ).pack(**pad, pady=(0, round(6 * s)))

        for name, url, lic in _BUILT_WITH:
            row = tk.Frame(self, bg=PANEL)
            row.pack(fill="x", padx=round(24 * s), pady=1)
            tk.Label(
                row, text=f"{name}  ", bg=PANEL, fg=_ABT_FG,
                font=ui_font(round(10 * s)), anchor="w",
            ).pack(side="left")
            link = tk.Label(
                row, text=url, bg=PANEL, fg=_ABT_LINK,
                font=ui_font(round(10 * s), "underline"), cursor="hand2",
            )
            link.pack(side="left")
            link.bind("<Button-1>", lambda _e, u=url: webbrowser.open(u))
            tk.Label(
                row, text=f"  ({lic})", bg=PANEL, fg=_ABT_DIM,
                font=ui_font(round(9 * s)),
            ).pack(side="left")

        tk.Frame(self, bg=_ABT_SEP, height=1).pack(
            fill="x", padx=round(24 * s), pady=round(12 * s),
        )

        tk.Label(
            self, text="Links",
            bg=PANEL, fg=_ABT_FG, font=ui_font(round(10 * s), "bold"),
        ).pack(**pad, pady=(0, round(6 * s)))
        for name, url in _PROJECT_LINKS:
            row = tk.Frame(self, bg=PANEL)
            row.pack(fill="x", padx=round(24 * s), pady=1)
            tk.Label(
                row, text=f"{name}  ", bg=PANEL, fg=_ABT_FG,
                font=ui_font(round(10 * s)), anchor="w",
            ).pack(side="left")
            link = tk.Label(
                row, text=url, bg=PANEL, fg=_ABT_LINK,
                font=ui_font(round(10 * s), "underline"), cursor="hand2",
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
        tk.Frame(self, bg=PANEL, height=round(34 * s)).pack()
        bmc_row = tk.Frame(self, bg=PANEL)
        bmc_row.pack(pady=(0, round(4 * s)))
        from app.ui.icons import load_tk_icon
        coffee_img = load_tk_icon(
            "coffee", size=round(18 * s), color=_BMC_FG,
        )
        bmc_btn = tk.Button(
            bmc_row,
            text="Buy me a coffee",
            image=coffee_img if coffee_img else "",
            compound="left",
            bg=_BMC_BG, fg=_BMC_FG,
            activebackground="#FFE54B", activeforeground=_BMC_FG,
            relief="solid", bd=1,
            highlightbackground=_BMC_OUTLINE,
            font=ui_font(round(11 * s), "bold"),
            padx=round(18 * s), pady=round(6 * s), cursor="hand2",
            command=lambda: webbrowser.open(_BMC_URL),
        )
        # Retain the PhotoImage on the button so Tk doesn't GC the
        # icon when the local var goes out of scope.
        bmc_btn.image = coffee_img  # type: ignore[attr-defined]
        bmc_btn.pack()

        tk.Frame(self, bg=PANEL, height=round(10 * s)).pack()
        flat_button(self, "Close", "ghost", self.destroy, s).pack(
            pady=(round(10 * s), round(16 * s)),
        )
