"""Tools → Color Palette — designer reference window.

Shows 15 named palettes (3 muted variants + black-mono + white-mono +
10 popular schemes), 9 colors each. Click any swatch to copy its hex
to the system clipboard. Pure reference — touches no project state.

Window auto-fits to content on first open: pixel-perfect default_size
is unreliable across DPI / font scaling, so we let widgets render at
their natural size, query reqheight, then resize. Subsequent opens
restore whatever size the user last left.
"""
from __future__ import annotations

import re
import tkinter as tk

import customtkinter as ctk

from app.core.settings import load_settings
from app.ui.managed_window import ManagedToplevel
from app.ui.style import (
    BG, BORDER, EMPTY_FG, HEADER_BG, PANEL_BG, TOOLBAR_BG,
    TOOLBAR_HEIGHT, TREE_FG,
)
from app.ui.system_fonts import ui_font


# ---- layout constants -------------------------------------------------------

CARD_W = 168
CARD_H = 42
SWATCH_W = 38
COL_GAP = 8


# ---- palettes ---------------------------------------------------------------
# Each entry: (palette_id, palette_label, [(color_name, hex), ...])

PALETTES: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("A", "Deep / Dark", [
        ("Deep Blue",     "#1e3a8a"),
        ("Deep Sky",      "#0c4a6e"),
        ("Deep Emerald",  "#065f46"),
        ("Deep Olive",    "#365314"),
        ("Deep Amber",    "#78350f"),
        ("Deep Crimson",  "#7f1d1d"),
        ("Deep Violet",   "#4c1d95"),
        ("Deep Purple",   "#581c87"),
        ("Deep Magenta",  "#831843"),
    ]),
    ("B", "Slate-tinted", [
        ("Steel Blue",    "#3a4a6b"),
        ("Steel Cyan",    "#3a5b6b"),
        ("Steel Green",   "#3a6b54"),
        ("Steel Olive",   "#545a3a"),
        ("Steel Amber",   "#6b5a3a"),
        ("Steel Red",     "#6b3a3a"),
        ("Steel Violet",  "#4a3a6b"),
        ("Steel Purple",  "#5a3a6b"),
        ("Steel Rose",    "#6b3a54"),
    ]),
    ("C", "Earthy / dusty", [
        ("Slate Steel",   "#4a5d7a"),
        ("Dusty Teal",    "#5a7d8c"),
        ("Sage",          "#5d7a55"),
        ("Dusty Olive",   "#7a7d4a"),
        ("Mustard",       "#9c7a4a"),
        ("Terra",         "#8c5a4a"),
        ("Dusty Plum",    "#6e4a7a"),
        ("Lilac Smoke",   "#7a5a8c"),
        ("Dusty Rose",    "#8c5a6e"),
    ]),
    ("D", "Black mono", [
        ("Pure Black",    "#000000"),
        ("Carbon",        "#0a0a0a"),
        ("Ink",           "#141414"),
        ("Onyx",          "#1c1c1c"),
        ("Charcoal",      "#242424"),
        ("Graphite",      "#2c2c2c"),
        ("Slate",         "#383838"),
        ("Gunmetal",      "#424242"),
        ("Iron",          "#4d4d4d"),
    ]),
    ("E", "White mono", [
        ("Pure White",    "#ffffff"),
        ("Snow",          "#f8f8f8"),
        ("Linen",         "#efefef"),
        ("Pearl",         "#e6e6e6"),
        ("Silk",          "#dcdcdc"),
        ("Mist",          "#d0d0d0"),
        ("Cloud",         "#c4c4c4"),
        ("Fog",           "#b8b8b8"),
        ("Stone",         "#a8a8a8"),
    ]),
    ("F", "Material 500", [
        ("Red",           "#f44336"),
        ("Pink",          "#e91e63"),
        ("Purple",        "#9c27b0"),
        ("Indigo",        "#3f51b5"),
        ("Blue",          "#2196f3"),
        ("Teal",          "#009688"),
        ("Green",         "#4caf50"),
        ("Amber",         "#ffc107"),
        ("Orange",        "#ff9800"),
    ]),
    ("G", "Tailwind 500", [
        ("Red",           "#ef4444"),
        ("Orange",        "#f97316"),
        ("Amber",         "#f59e0b"),
        ("Lime",          "#84cc16"),
        ("Emerald",       "#10b981"),
        ("Teal",          "#14b8a6"),
        ("Sky",           "#0ea5e9"),
        ("Indigo",        "#6366f1"),
        ("Pink",          "#ec4899"),
    ]),
    ("H", "Nord", [
        ("Polar Night",   "#2e3440"),
        ("Polar Mid",     "#3b4252"),
        ("Snow Storm",    "#d8dee9"),
        ("Frost Cyan",    "#88c0d0"),
        ("Frost Blue",    "#5e81ac"),
        ("Aurora Red",    "#bf616a"),
        ("Aurora Orange", "#d08770"),
        ("Aurora Yellow", "#ebcb8b"),
        ("Aurora Green",  "#a3be8c"),
    ]),
    ("I", "Dracula", [
        ("Background",    "#282a36"),
        ("Current Line",  "#44475a"),
        ("Foreground",    "#f8f8f2"),
        ("Comment",       "#6272a4"),
        ("Cyan",          "#8be9fd"),
        ("Green",         "#50fa7b"),
        ("Orange",        "#ffb86c"),
        ("Pink",          "#ff79c6"),
        ("Purple",        "#bd93f9"),
    ]),
    ("J", "Gruvbox Dark", [
        ("Bg0",           "#282828"),
        ("Bg1",           "#3c3836"),
        ("Fg",            "#ebdbb2"),
        ("Red",           "#cc241d"),
        ("Green",         "#98971a"),
        ("Yellow",        "#d79921"),
        ("Blue",          "#458588"),
        ("Purple",        "#b16286"),
        ("Aqua",          "#689d6a"),
    ]),
    ("K", "Tokyo Night", [
        ("Background",    "#1a1b26"),
        ("Foreground",    "#c0caf5"),
        ("Comment",       "#565f89"),
        ("Red",           "#f7768e"),
        ("Green",         "#9ece6a"),
        ("Yellow",        "#e0af68"),
        ("Blue",          "#7aa2f7"),
        ("Magenta",       "#bb9af7"),
        ("Cyan",          "#7dcfff"),
    ]),
    ("L", "Catppuccin Mocha", [
        ("Base",          "#1e1e2e"),
        ("Surface",       "#313244"),
        ("Text",          "#cdd6f4"),
        ("Lavender",      "#b4befe"),
        ("Blue",          "#89b4fa"),
        ("Sapphire",      "#74c7ec"),
        ("Green",         "#a6e3a1"),
        ("Peach",         "#fab387"),
        ("Pink",          "#f5c2e7"),
    ]),
    ("M", "Solarized Dark", [
        ("Base03",        "#002b36"),
        ("Base02",        "#073642"),
        ("Base0",         "#839496"),
        ("Yellow",        "#b58900"),
        ("Orange",        "#cb4b16"),
        ("Red",           "#dc322f"),
        ("Magenta",       "#d33682"),
        ("Blue",          "#268bd2"),
        ("Cyan",          "#2aa198"),
    ]),
    ("N", "Monokai", [
        ("Background",    "#272822"),
        ("Foreground",    "#f8f8f2"),
        ("Comment",       "#75715e"),
        ("Red",           "#f92672"),
        ("Orange",        "#fd971f"),
        ("Yellow",        "#e6db74"),
        ("Green",         "#a6e22e"),
        ("Blue",          "#66d9ef"),
        ("Purple",        "#ae81ff"),
    ]),
    ("O", "One Dark", [
        ("Background",    "#282c34"),
        ("Foreground",    "#abb2bf"),
        ("Comment",       "#5c6370"),
        ("Red",           "#e06c75"),
        ("Green",         "#98c379"),
        ("Yellow",        "#e5c07b"),
        ("Blue",          "#61afef"),
        ("Purple",        "#c678dd"),
        ("Cyan",          "#56b6c2"),
    ]),
]


_GEOMETRY_RE = re.compile(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$")


# ----------------------------------------------------------------------------

class ColorPaletteWindow(ManagedToplevel):
    window_key = "color_palette"
    window_title = "Color Palette"
    default_size = (980, 540)
    min_size = (560, 240)
    fg_color = BG
    panel_padding = (0, 0)

    def __init__(self, parent):
        self._status_after_id: str | None = None
        # Auto-fit window to content only on first-ever open. After
        # that, restore saved geometry as usual.
        settings = load_settings()
        self._needs_fit = (
            self.window_key not in settings.get("window_geometries", {})
        )
        super().__init__(parent)
        if self._needs_fit:
            self.after_idle(self._fit_to_content)

    def _fit_to_content(self) -> None:
        if self._content is None:
            return
        try:
            self.update_idletasks()
            content_h = self._content.winfo_reqheight()
            geom = self.geometry()
        except tk.TclError:
            return
        m = _GEOMETRY_RE.match(geom)
        if not m:
            return
        w = int(m.group(1))
        x = int(m.group(3))
        y = int(m.group(4))
        try:
            self.geometry(f"{w}x{content_h}+{x}+{y}")
        except tk.TclError:
            pass

    def build_content(self) -> ctk.CTkFrame:
        container = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)

        self._build_header(container)
        self._build_status(container)
        self._build_scroll_area(container)

        return container

    # ---- chrome -------------------------------------------------------------

    def _build_header(self, parent: tk.Misc) -> None:
        bar = tk.Frame(
            parent, bg=TOOLBAR_BG,
            height=TOOLBAR_HEIGHT, highlightthickness=0,
        )
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)
        tk.Label(
            bar, text="Color Palette",
            bg=TOOLBAR_BG, fg=TREE_FG,
            font=ui_font(12, "bold"),
        ).pack(side="left", padx=12)
        tk.Label(
            bar, text="click a swatch to copy hex",
            bg=TOOLBAR_BG, fg=EMPTY_FG,
            font=ui_font(10),
        ).pack(side="left", padx=4)

    def _build_status(self, parent: tk.Misc) -> None:
        self._status = tk.Label(
            parent, text=" ",
            bg=PANEL_BG, fg=EMPTY_FG,
            font=ui_font(10), anchor="w",
            height=1,
        )
        self._status.pack(side="bottom", fill="x")

    def _build_scroll_area(self, parent: tk.Misc) -> None:
        scroll = ctk.CTkScrollableFrame(
            parent, orientation="horizontal",
            fg_color=PANEL_BG, corner_radius=0,
        )
        scroll.pack(side="top", fill="both", expand=True)

        for pid, plabel, colors in PALETTES:
            self._build_palette_column(scroll, pid, plabel, colors)

    # ---- palette column -----------------------------------------------------

    def _build_palette_column(
        self, parent: tk.Misc, pid: str, plabel: str,
        colors: list[tuple[str, str]],
    ) -> None:
        col = tk.Frame(parent, bg=PANEL_BG)
        col.pack(side="left", padx=(COL_GAP, 0), pady=8, anchor="n")

        tk.Label(
            col, text=f"{pid} — {plabel}",
            bg=PANEL_BG, fg=TREE_FG,
            font=ui_font(11, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 4), padx=2)

        for name, hex_code in colors:
            self._build_color_card(col, name, hex_code)

    def _build_color_card(
        self, parent: tk.Misc, name: str, hex_code: str,
    ) -> None:
        card = tk.Frame(
            parent, bg=BORDER, width=CARD_W, height=CARD_H,
            highlightthickness=0,
        )
        card.pack(pady=2)
        card.pack_propagate(False)

        swatch = tk.Frame(card, bg=hex_code, width=SWATCH_W)
        swatch.pack(side="left", fill="y", padx=(1, 0), pady=1)
        swatch.pack_propagate(False)

        text_frame = tk.Frame(card, bg=HEADER_BG)
        text_frame.pack(side="left", fill="both", expand=True, padx=(1, 1), pady=1)

        name_lbl = tk.Label(
            text_frame, text=name,
            bg=HEADER_BG, fg=TREE_FG,
            font=ui_font(10, "bold"),
            anchor="w",
        )
        name_lbl.pack(fill="x", padx=8, pady=(3, 0))

        hex_lbl = tk.Label(
            text_frame, text=hex_code,
            bg=HEADER_BG, fg=EMPTY_FG,
            font=("Consolas", 9),
            anchor="w",
        )
        hex_lbl.pack(fill="x", padx=8)

        for w in (card, swatch, text_frame, name_lbl, hex_lbl):
            w.bind(
                "<Button-1>",
                lambda _e, h=hex_code, n=name: self._copy(h, n),
            )
            w.configure(cursor="hand2")

    # ---- copy ---------------------------------------------------------------

    def _copy(self, hex_code: str, name: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(hex_code)
        self._status.configure(
            text=f"  copied  {hex_code}  ({name})",
            fg=TREE_FG,
        )
        if self._status_after_id is not None:
            try:
                self.after_cancel(self._status_after_id)
            except tk.TclError:
                pass
        self._status_after_id = self.after(1800, self._clear_status)

    def _clear_status(self) -> None:
        try:
            self._status.configure(text=" ", fg=EMPTY_FG)
        except tk.TclError:
            pass
        self._status_after_id = None
