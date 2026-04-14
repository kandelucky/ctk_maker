"""Top toolbar — Qt Designer-style icon-only buttons for quick access.

Lives between the menu bar and the three-panel paned window in
MainWindow. Buttons carry a Lucide icon only (no text label), grouped
by function with thin vertical separators. Missing icons fall back to
the first letter of the action name.

Callbacks are passed in from MainWindow so this module stays UI-only.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk

from app.ui.icons import load_icon

BAR_BG = "#252526"
BTN_HOVER = "#3a3a3a"
SEP_FG = "#3c3c3c"
ICON_TINT = "#cccccc"

BAR_HEIGHT = 34
BTN_SIZE = 26
ICON_SIZE = 18


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
        super().__init__(
            master, fg_color=BAR_BG, corner_radius=0, height=BAR_HEIGHT,
        )
        self.pack_propagate(False)

        self._add_button("file-plus", on_new, tooltip="New project")
        self._add_button("folder", on_open, tooltip="Open project")
        self._add_button("save-all", on_save, tooltip="Save")

    def _add_button(
        self,
        icon_name: str,
        command: Callable[[], None],
        *,
        tooltip: str | None = None,
    ) -> None:
        icon = load_icon(icon_name, size=ICON_SIZE, color=ICON_TINT)
        btn = ctk.CTkButton(
            self,
            text="" if icon else icon_name[0].upper(),
            image=icon,
            width=BTN_SIZE,
            height=BTN_SIZE,
            corner_radius=4,
            fg_color="transparent",
            hover_color=BTN_HOVER,
            command=command,
        )
        btn.pack(side="left", padx=0, pady=3)
        if tooltip:
            _attach_tooltip(btn, tooltip)

    def _add_separator(self) -> None:
        sep = ctk.CTkFrame(self, width=1, fg_color=SEP_FG, corner_radius=0)
        sep.pack(side="left", fill="y", padx=6, pady=6)


# ----------------------------------------------------------------------------
# Tiny hover tooltip — vanilla tk, minimal footprint.
# ----------------------------------------------------------------------------
TOOLTIP_BG = "#1e1e1e"
TOOLTIP_FG = "#cccccc"
TOOLTIP_BORDER = "#3c3c3c"
TOOLTIP_DELAY_MS = 500


def _attach_tooltip(widget, text: str) -> None:
    state = {"after": None, "tip": None}

    def show():
        state["after"] = None
        try:
            rx = widget.winfo_rootx()
            ry = widget.winfo_rooty() + widget.winfo_height() + 4
        except tk.TclError:
            return
        tip = tk.Toplevel(widget)
        tip.wm_overrideredirect(True)
        try:
            tip.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        tip.configure(bg=TOOLTIP_BORDER)
        label = tk.Label(
            tip, text=text,
            bg=TOOLTIP_BG, fg=TOOLTIP_FG,
            font=("Segoe UI", 9),
            padx=6, pady=2,
            bd=0,
        )
        label.pack(padx=1, pady=1)
        tip.geometry(f"+{rx}+{ry}")
        state["tip"] = tip

    def on_enter(_e):
        cancel()
        state["after"] = widget.after(TOOLTIP_DELAY_MS, show)

    def on_leave(_e):
        cancel()
        tip = state["tip"]
        if tip is not None:
            try:
                tip.destroy()
            except tk.TclError:
                pass
            state["tip"] = None

    def cancel():
        if state["after"] is not None:
            try:
                widget.after_cancel(state["after"])
            except Exception:
                pass
            state["after"] = None

    widget.bind("<Enter>", on_enter, add="+")
    widget.bind("<Leave>", on_leave, add="+")
    widget.bind("<ButtonPress>", on_leave, add="+")
