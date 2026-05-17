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
from app.ui.dialogs._colors import _ABT_BG, _ABT_DIM, _ABT_FG, _ABT_SEP
from app.ui.properties_panel.constants import OS_SPECIFIC_CURSORS
from app.ui.style import styled_scrollbar
from app.ui.system_fonts import ui_font


_OS_LABELS = {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}
_ROW_BG = "#252526"
_ROW_HOVER = "#2d2d30"
_TAB_ACTIVE_BG = "#094771"
_TAB_INACTIVE_BG = "#2d2d30"


class CursorAdvancedDialog(DarkDialog):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.title("Advanced Cursor")
        self.result: str | None = None
        self._current_os = platform.system()
        if self._current_os not in OS_SPECIFIC_CURSORS:
            self._current_os = "Linux"
        self._active_tab = self._current_os
        self._list_frame: tk.Frame | None = None
        self._tab_buttons: dict[str, tk.Label] = {}
        self._build()
        self.update_idletasks()
        self.place_centered(420, 520, parent)
        self.lift()
        self.focus_set()
        safe_grab_set(self)
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.reveal()

    def _build(self) -> None:
        tk.Frame(self, bg=_ABT_BG, height=14).pack()
        tk.Label(
            self,
            text="OS-specific cursors render only on the matching system. "
                 "On other systems Tk falls back to the default arrow.",
            bg=_ABT_BG, fg=_ABT_DIM, font=ui_font(9),
            justify="left", wraplength=380,
        ).pack(padx=20, pady=(0, 10))

        tab_row = tk.Frame(self, bg=_ABT_BG)
        tab_row.pack(padx=20, fill="x")
        for os_key in ("Windows", "Darwin", "Linux"):
            label_text = _OS_LABELS[os_key]
            if os_key == self._current_os:
                label_text += "  •"
            tab = tk.Label(
                tab_row, text=label_text,
                bg=_TAB_INACTIVE_BG, fg=_ABT_FG,
                font=ui_font(10), padx=14, pady=6,
                cursor="hand2",
            )
            tab.pack(side="left", padx=(0, 4))
            tab.bind(
                "<Button-1>",
                lambda _e, k=os_key: self._switch_tab(k),
            )
            self._tab_buttons[os_key] = tab

        tk.Frame(self, bg=_ABT_SEP, height=1).pack(
            fill="x", padx=20, pady=(8, 0),
        )

        list_outer = tk.Frame(self, bg=_ABT_BG)
        list_outer.pack(padx=20, pady=(8, 8), fill="both", expand=True)

        self._canvas = tk.Canvas(
            list_outer, bg=_ABT_BG, highlightthickness=0, bd=0,
        )
        scrollbar = styled_scrollbar(list_outer, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._list_frame = tk.Frame(self._canvas, bg=_ABT_BG)
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

        btn_row = tk.Frame(self, bg=_ABT_BG)
        btn_row.pack(pady=(0, 16))
        tk.Button(
            btn_row, text="Cancel", command=self._on_cancel,
            bg="#3a3a3a", fg=_ABT_FG, activebackground="#4a4a4a",
            activeforeground=_ABT_FG, relief="flat", bd=0,
            font=ui_font(10), padx=18, pady=4, cursor="hand2",
        ).pack()

        self._render_list()

    def _switch_tab(self, os_key: str) -> None:
        self._active_tab = os_key
        self._render_list()

    def _render_list(self) -> None:
        for os_key, tab in self._tab_buttons.items():
            active = os_key == self._active_tab
            tab.configure(
                bg=_TAB_ACTIVE_BG if active else _TAB_INACTIVE_BG,
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
            row, text=name, bg=_ROW_BG, fg=_ABT_FG,
            font=ui_font(11), padx=14, pady=7,
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
            label.configure(fg=_ABT_DIM)

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
