"""Top toolbar — icon-only buttons for quick access.

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
from app.ui.system_fonts import ui_font

BAR_BG = "#252526"
BTN_HOVER = "#3a3a3a"
SEP_FG = "#3c3c3c"
ICON_TINT = "#cccccc"
ICON_TINT_DISABLED = "#555555"
ICON_TINT_CARROT = "#e0ccb0"

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
        on_undo: Callable[[], object],
        on_redo: Callable[[], object],
        on_run_script: Callable[[], None] | None = None,
        on_align: Callable[[str], None] | None = None,
        on_report_bug: Callable[[], None] | None = None,
    ):
        super().__init__(
            master, fg_color=BAR_BG, corner_radius=0, height=BAR_HEIGHT,
        )
        self.pack_propagate(False)

        self._add_button("file-plus", on_new, tooltip="New project")
        self._add_button("folder", on_open, tooltip="Open project")
        self._add_button("save", on_save, tooltip="Save")
        self._add_separator()
        self._add_button(
            "file-code", on_export, tooltip="Export to Python",
            color=ICON_TINT_CARROT,
        )
        if on_run_script is not None:
            self._add_button(
                "tv-minimal-play", on_run_script,
                tooltip="Run Python Script...",
                color=ICON_TINT_CARROT,
            )
        self._add_separator()
        # Pre-load both icon variants so we can swap in place without
        # triggering a CTkButton layout shift on state change.
        self._icon_undo_on = load_icon("undo", size=ICON_SIZE, color=ICON_TINT)
        self._icon_undo_off = load_icon(
            "undo", size=ICON_SIZE, color=ICON_TINT_DISABLED,
        )
        self._icon_redo_on = load_icon("redo", size=ICON_SIZE, color=ICON_TINT)
        self._icon_redo_off = load_icon(
            "redo", size=ICON_SIZE, color=ICON_TINT_DISABLED,
        )
        self._undo_button = self._add_toggle_button(
            self._icon_undo_off, on_undo, tooltip="Undo (Ctrl+Z)",
        )
        self._redo_button = self._add_toggle_button(
            self._icon_redo_off, on_redo, tooltip="Redo (Ctrl+Y)",
        )
        self._undo_enabled = False
        self._redo_enabled = False

        # Alignment buttons — appear after a separator and stay
        # disabled until the selection has at least one moveable
        # widget on a place-managed parent. ``on_align(mode)`` is
        # the dispatcher MainWindow wires up.
        self._align_buttons: dict[str, ctk.CTkButton] = {}
        self._align_enabled: dict[str, bool] = {}
        if on_align is not None:
            self._add_separator()
            self._build_align_group(on_align)

        # Report-bug button — packed to the right edge so it sits in
        # its own quiet zone, well away from the functional cluster
        # on the left. The blank stretch in the middle is the visual
        # separator the user asked for.
        if on_report_bug is not None:
            self._add_report_bug_button(on_report_bug)

    def _build_align_group(self, on_align: Callable[[str], None]) -> None:
        """Pack the 6 align + 2 distribute icon buttons. Each entry
        in ``specs`` is ``(mode, icon_name, tooltip)`` and all start
        disabled (no selection on first paint)."""
        from app.core.alignment import (
            MODE_LEFT, MODE_CENTER_H, MODE_RIGHT,
            MODE_TOP, MODE_CENTER_V, MODE_BOTTOM,
            MODE_DISTRIBUTE_H, MODE_DISTRIBUTE_V,
        )
        specs: list[tuple[str, str, str]] = [
            (MODE_LEFT, "align-start-vertical", "Align Left"),
            (MODE_CENTER_H, "align-center-vertical", "Align Center (Horizontal)"),
            (MODE_RIGHT, "align-end-vertical", "Align Right"),
            (MODE_TOP, "align-start-horizontal", "Align Top"),
            (MODE_CENTER_V, "align-center-horizontal", "Align Middle (Vertical)"),
            (MODE_BOTTOM, "align-end-horizontal", "Align Bottom"),
        ]
        for mode, icon_name, tooltip in specs:
            btn = self._add_align_button(icon_name, mode, on_align, tooltip)
            self._align_buttons[mode] = btn
            self._align_enabled[mode] = False
        # Subtle separator before distribute — the two icons look
        # similar to align so the gap helps the eye chunk them.
        self._add_separator()
        for mode, icon_name, tooltip in (
            (MODE_DISTRIBUTE_H, "align-horizontal-distribute-center",
             "Distribute Horizontally"),
            (MODE_DISTRIBUTE_V, "align-vertical-distribute-center",
             "Distribute Vertically"),
        ):
            btn = self._add_align_button(icon_name, mode, on_align, tooltip)
            self._align_buttons[mode] = btn
            self._align_enabled[mode] = False

    def _add_align_button(
        self, icon_name: str, mode: str,
        dispatch: Callable[[str], None], tooltip: str,
    ) -> ctk.CTkButton:
        """Same shape as ``_add_button`` but caches both color
        variants of the icon so set_align_enabled can swap the
        glyph without rebuilding the button."""
        on_icon = load_icon(icon_name, size=ICON_SIZE, color=ICON_TINT)
        off_icon = load_icon(
            icon_name, size=ICON_SIZE, color=ICON_TINT_DISABLED,
        )
        btn = ctk.CTkButton(
            self, text="", image=off_icon,
            width=BTN_SIZE, height=BTN_SIZE,
            corner_radius=4, fg_color="transparent",
            hover_color=BTN_HOVER,
            command=lambda m=mode: dispatch(m),
        )
        btn.pack(side="left", padx=0, pady=3)
        btn._icon_on = on_icon
        btn._icon_off = off_icon
        if tooltip:
            _attach_tooltip(btn, tooltip)
        return btn

    def set_align_enabled(self, mode_states: dict[str, bool]) -> None:
        """Update the on/off glyph for each align button. ``mode_states``
        is the full ``{mode: bool}`` map from the dispatcher; missing
        modes default to disabled."""
        for mode, btn in self._align_buttons.items():
            enabled = bool(mode_states.get(mode, False))
            if enabled == self._align_enabled.get(mode, False):
                continue
            self._align_enabled[mode] = enabled
            btn.configure(
                image=btn._icon_on if enabled else btn._icon_off,
            )

    def set_undo_enabled(self, enabled: bool) -> None:
        if enabled == self._undo_enabled:
            return
        self._undo_enabled = enabled
        self._undo_button.configure(
            image=self._icon_undo_on if enabled else self._icon_undo_off,
        )

    def set_redo_enabled(self, enabled: bool) -> None:
        if enabled == self._redo_enabled:
            return
        self._redo_enabled = enabled
        self._redo_button.configure(
            image=self._icon_redo_on if enabled else self._icon_redo_off,
        )

    def _add_toggle_button(
        self,
        image,
        command: Callable[[], None],
        *,
        tooltip: str | None = None,
    ) -> ctk.CTkButton:
        btn = ctk.CTkButton(
            self,
            text="",
            image=image,
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
        return btn

    def _add_button(
        self,
        icon_name: str,
        command: Callable[[], None],
        *,
        tooltip: str | None = None,
        color: str = ICON_TINT,
    ) -> ctk.CTkButton:
        icon = load_icon(icon_name, size=ICON_SIZE, color=color)
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
        return btn

    def _add_separator(self) -> None:
        sep = ctk.CTkFrame(self, width=1, fg_color=SEP_FG, corner_radius=0)
        sep.pack(side="left", fill="y", padx=6, pady=6)

    def _add_report_bug_button(
        self, command: Callable[[], None],
    ) -> ctk.CTkButton:
        """Right-anchored 'Bug Report / Feature Request' button.
        Slight warm tint on the button background sets it apart from
        the functional cluster on the left without colouring the
        text or icon."""
        icon = load_icon("bug-play", size=20, color=ICON_TINT)
        btn = ctk.CTkButton(
            self,
            text="Bug Report / Feature Request",
            image=icon,
            width=220,
            height=28,
            corner_radius=4,
            fg_color="#3b3026",
            hover_color="#4a3b2c",
            text_color=ICON_TINT,
            font=ui_font(11, "bold"),
            compound="left",
            command=command,
        )
        btn.pack(side="right", padx=(8, 8), pady=3)
        _attach_tooltip(btn, "Report a bug or request a feature")
        return btn


# ----------------------------------------------------------------------------
# Tiny hover tooltip — vanilla tk, minimal footprint.
# ----------------------------------------------------------------------------
TOOLTIP_BG = "#1e1e1e"
TOOLTIP_FG = "#cccccc"
TOOLTIP_BORDER = "#3c3c3c"
TOOLTIP_DELAY_MS = 500


def _attach_tooltip(widget, text: str) -> None:
    state = {"after": None, "tip": None, "mx": 0, "my": 0}

    def show():
        state["after"] = None
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
            font=ui_font(9),
            padx=6, pady=2,
            bd=0,
        )
        label.pack(padx=1, pady=1)
        tip.update_idletasks()
        th = tip.winfo_height()
        # Show above the cursor so the tooltip is never covered
        tx = state["mx"] + 12
        ty = state["my"] - th - 6
        tip.geometry(f"+{tx}+{ty}")
        state["tip"] = tip

    def on_enter(e):
        state["mx"] = e.x_root
        state["my"] = e.y_root
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
