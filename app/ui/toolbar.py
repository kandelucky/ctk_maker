"""Top toolbar — Qt Designer-style icon+label buttons for file ops and preview.

Lives above the three-panel paned window in MainWindow. Buttons carry a Lucide
icon (via app.ui.icons.load_icon) and a short text label. Icons missing from
app/assets/icons/ fall back to text-only automatically.

Callbacks are passed in from MainWindow so this module stays UI-only.
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from app.ui.icons import load_icon

BAR_BG = "#252526"
BTN_HOVER = "#2d2d30"
BTN_FG = "#cccccc"
SEP_FG = "#3c3c3c"

BTN_WIDTH = 56
BTN_HEIGHT = 24
ICON_SIZE = 14
LABEL_FONT = ("Segoe UI", 10)


class Toolbar(ctk.CTkFrame):
    def __init__(
        self,
        master,
        *,
        on_new: Callable[[], None],
        on_open: Callable[[], None],
        on_save: Callable[[], None],
        on_preview: Callable[[], None],
        on_export: Callable[[], None],
        on_theme_toggle: Callable[[], None],
    ):
        super().__init__(master, fg_color=BAR_BG, corner_radius=0, height=BTN_HEIGHT + 6)
        self.pack_propagate(False)

        self._add_button("file-plus", "New", on_new)
        self._add_button("folder-open", "Open", on_open)
        self._add_button("save", "Save", on_save)
        self._add_separator()
        self._add_button("play", "Preview", on_preview)
        self._add_button("file-code", "Export", on_export)
        self._add_separator()
        self._add_button("sun-moon", "Theme", on_theme_toggle)

    def _add_button(self, icon_name: str, label: str, command: Callable[[], None]) -> None:
        icon = load_icon(icon_name, size=ICON_SIZE)
        btn = ctk.CTkButton(
            self,
            text=label,
            image=icon,
            compound="left",
            width=BTN_WIDTH,
            height=BTN_HEIGHT,
            corner_radius=4,
            fg_color="transparent",
            hover_color=BTN_HOVER,
            text_color=BTN_FG,
            font=LABEL_FONT,
            command=command,
        )
        btn.pack(side="left", padx=2, pady=3)

    def _add_separator(self) -> None:
        sep = ctk.CTkFrame(self, width=1, fg_color=SEP_FG, corner_radius=0)
        sep.pack(side="left", fill="y", padx=6, pady=5)
