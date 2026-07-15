"""OS-specific cursor picker.

Opens from the cursor property's "Advanced…" dropdown row. Lists
Windows / macOS / Linux cursors in tabs; each row uses the cursor
itself, so the user can hover-preview before picking. ``self.result``
is the picked cursor name, or ``None`` on cancel.
"""

from __future__ import annotations

import platform
import tkinter as tk

from app.ui.dialog_utils import safe_grab_set
from app.ui.dialogs._base import DarkDialog
from app.ui.dialogs._colors import (
    _ABT_SEP,
    ACCENT,
    FG,
    FG_DIM,
    ON_ACCENT,
    PANEL,
    dialog_scaling,
    flat_button,
    hero_header,
)
from app.ui.properties_panel.constants import OS_SPECIFIC_CURSORS
from app.ui.style import styled_scrollbar
from app.ui.system_fonts import ui_font


_OS_LABELS = {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}
_ROW_BG = "#252526"
_ROW_HOVER = "#2d2d30"
_TAB_INACTIVE_BG = "#2d2d30"


class CursorAdvancedDialog(DarkDialog):
    def __init__(self, parent) -> None:
        super().__init__(parent, fg_color=PANEL)
        self.title("Advanced Cursor")
        self.result: str | None = None
        self._current_os = platform.system()
        if self._current_os not in OS_SPECIFIC_CURSORS:
            self._current_os = "Linux"
        self._active_tab = self._current_os
        self._list_frame: tk.Frame | None = None
        self._tab_buttons: dict[str, tk.Label] = {}
        self._s = dialog_scaling(self)
        self._build()
        self.update_idletasks()
        self.place_centered(
            round(420 * self._s), round(520 * self._s), parent,
        )
        self.lift()
        self.focus_set()
        safe_grab_set(self)
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.reveal()

    def _build(self) -> None:
        s = self._s
        hero_header(self, "Advanced Cursor", "info", s)
        tk.Label(
            self,
            text="OS-specific cursors render only on the matching system. "
                 "On other systems Tk falls back to the default arrow.",
            bg=PANEL, fg=FG_DIM, font=ui_font(round(9 * s)),
            justify="left", wraplength=round(380 * s), anchor="w",
        ).pack(
            fill="x", padx=(round(31 * s), round(18 * s)),
            pady=(round(6 * s), round(10 * s)),
        )

        tab_row = tk.Frame(self, bg=PANEL)
        tab_row.pack(padx=round(18 * s), fill="x")
        for os_key in ("Windows", "Darwin", "Linux"):
            label_text = _OS_LABELS[os_key]
            if os_key == self._current_os:
                label_text += "  •"
            tab = tk.Label(
                tab_row, text=label_text,
                bg=_TAB_INACTIVE_BG, fg=FG,
                font=ui_font(round(10 * s)),
                padx=round(14 * s), pady=round(6 * s),
                cursor="hand2",
            )
            tab.pack(side="left", padx=(0, round(4 * s)))
            tab.bind(
                "<Button-1>",
                lambda _e, k=os_key: self._switch_tab(k),
            )
            self._tab_buttons[os_key] = tab

        tk.Frame(self, bg=_ABT_SEP, height=1).pack(
            fill="x", padx=round(18 * s), pady=(round(8 * s), 0),
        )

        list_outer = tk.Frame(self, bg=PANEL)
        list_outer.pack(
            padx=round(18 * s), pady=(round(8 * s), round(8 * s)),
            fill="both", expand=True,
        )

        self._canvas = tk.Canvas(
            list_outer, bg=PANEL, highlightthickness=0, bd=0,
        )
        scrollbar = styled_scrollbar(list_outer, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._list_frame = tk.Frame(self._canvas, bg=PANEL)
        self._canvas.create_window(
            (0, 0), window=self._list_frame, anchor="nw",
        )
        self._list_frame.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all"),
            ),
        )
        self._canvas.bind(
            "<MouseWheel>",
            lambda e: self._canvas.yview_scroll(
                int(-e.delta / 120), "units",
            ),
        )

        btn_row = tk.Frame(self, bg=PANEL)
        btn_row.pack(
            fill="x", padx=round(18 * s), pady=(0, round(16 * s)),
        )
        flat_button(
            btn_row, "Cancel", "ghost", self._on_cancel, s,
        ).pack(side="right")

        self._render_list()

    def _switch_tab(self, os_key: str) -> None:
        self._active_tab = os_key
        self._render_list()

    def _render_list(self) -> None:
        for os_key, tab in self._tab_buttons.items():
            active = os_key == self._active_tab
            tab.configure(
                bg=ACCENT if active else _TAB_INACTIVE_BG,
                fg=ON_ACCENT if active else FG,
            )
        if self._list_frame is None:
            return
        for child in self._list_frame.winfo_children():
            child.destroy()
        cursors = OS_SPECIFIC_CURSORS.get(self._active_tab, [])
        for name in cursors:
            self._make_row(name)
        self._canvas.yview_moveto(0)

    def _make_row(self, name: str) -> None:
        row = tk.Frame(self._list_frame, bg=_ROW_BG)
        row.pack(fill="x", pady=1)
        label = tk.Label(
            row, text=name, bg=_ROW_BG, fg=FG,
            font=ui_font(round(11 * self._s)),
            padx=round(14 * self._s), pady=round(7 * self._s),
            anchor="w",
        )
        label.pack(fill="x")
        # Try the OS-specific cursor; if this Tk build rejects it
        # (e.g. macOS cursors on Windows raise "bad cursor spec"),
        # fall back to arrow + dim the row to mark it unavailable.
        try:
            row.configure(cursor=name)
            label.configure(cursor=name)
        except tk.TclError:
            label.configure(fg=FG_DIM)

        def on_enter(_e, r=row, lb=label) -> None:
            r.configure(bg=_ROW_HOVER)
            lb.configure(bg=_ROW_HOVER)

        def on_leave(_e, r=row, lb=label) -> None:
            r.configure(bg=_ROW_BG)
            lb.configure(bg=_ROW_BG)

        def on_click(_e, n=name) -> None:
            self._pick(n)

        for w in (row, label):
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", on_click)

    def _pick(self, name: str) -> None:
        self.result = name
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()
