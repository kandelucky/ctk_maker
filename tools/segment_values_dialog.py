"""Segment values editor — table-based dialog for CTkSegmentedButton.

Each row is one segment name (editable). Add / remove rows with the
+ and − buttons. Empty rows are stripped on commit.

Result contract:
    dialog = SegmentValuesDialog(parent, "Edit Segments", ["First", "Second"])
    dialog.wait_window()
    if dialog.result is not None:
        new_values = dialog.result   # list[str]
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk


BG = "#1e1e1e"
ROW_BG = "#2d2d2d"
ROW_FG = "#cccccc"
BORDER = "#3a3a3a"
STATUS_FG = "#888888"


class SegmentValuesDialog(ctk.CTkToplevel):
    """Modal dialog for editing a list of segment names."""

    def __init__(
        self,
        parent,
        title: str,
        initial_values: list[str],
        *,
        width: int = 360,
        height: int = 360,
    ):
        super().__init__(parent)
        self.title(title)
        self.configure(fg_color=BG)
        self.geometry(f"{width}x{height}")
        self.minsize(280, 240)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.result: list[str] | None = None

        # Track row entries so we can read them back on OK and add /
        # remove dynamically.
        self._rows: list[tk.Entry] = []

        self._build_chrome()
        self._build_body()
        self._build_footer()

        for value in initial_values or [""]:
            self._add_row(value)
        if not self._rows:
            self._add_row("")

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    # ------------------------------------------------------------------
    # Chrome
    # ------------------------------------------------------------------
    def _build_chrome(self) -> None:
        bar = ctk.CTkFrame(
            self, fg_color=ROW_BG, height=28, corner_radius=0,
        )
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)
        ctk.CTkLabel(
            bar, text="Segments  ·  one per row",
            font=("Segoe UI", 10), text_color=STATUS_FG, anchor="w",
        ).pack(side="left", padx=12)

    def _build_body(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        wrap.pack(fill="both", expand=True, padx=12, pady=(8, 4))

        self._scroll = ctk.CTkScrollableFrame(
            wrap, fg_color=BG, corner_radius=0,
        )
        self._scroll.pack(fill="both", expand=True)

        action_bar = ctk.CTkFrame(
            self, fg_color="transparent", height=32,
        )
        action_bar.pack(side="top", fill="x", padx=12)
        action_bar.pack_propagate(False)
        ctk.CTkButton(
            action_bar, text="+", width=28, height=22, corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=lambda: self._add_row(""),
        ).pack(side="left")
        ctk.CTkButton(
            action_bar, text="−", width=28, height=22, corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._remove_last_row,
        ).pack(side="left", padx=(4, 0))
        ctk.CTkLabel(
            action_bar,
            text="Empty rows won't be saved.",
            font=("Segoe UI", 9), text_color=STATUS_FG,
        ).pack(side="left", padx=(12, 0))

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent", height=44)
        footer.pack(side="bottom", fill="x", padx=12, pady=(4, 10))
        footer.pack_propagate(False)

        ctk.CTkButton(
            footer, text="OK", width=80, height=26, corner_radius=3,
            command=self._on_ok,
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            footer, text="Cancel", width=80, height=26, corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right")

    # ------------------------------------------------------------------
    # Row mgmt
    # ------------------------------------------------------------------
    def _add_row(self, value: str = "") -> None:
        row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        row.pack(fill="x", pady=2)

        idx_lbl = ctk.CTkLabel(
            row, text=f"{len(self._rows) + 1}",
            width=24, anchor="e", text_color=STATUS_FG,
            font=("Segoe UI", 10),
        )
        idx_lbl.pack(side="left", padx=(0, 6))

        entry = tk.Entry(
            row, font=("Segoe UI", 11),
            bg=ROW_BG, fg=ROW_FG, insertbackground=ROW_FG,
            relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor="#3b8ed0",
        )
        entry.insert(0, value)
        entry.pack(side="left", fill="x", expand=True, ipady=3)

        remove_btn = ctk.CTkButton(
            row, text="✕", width=24, height=22, corner_radius=3,
            fg_color="transparent", hover_color="#4a2a2a",
            text_color="#888888",
            command=lambda r=row, e=entry: self._remove_row(r, e),
        )
        remove_btn.pack(side="left", padx=(6, 0))

        self._rows.append(entry)
        entry.focus_set()
        # Scroll to bottom so the freshly-added row is visible.
        self.after(10, lambda: self._scroll._parent_canvas.yview_moveto(1.0))

    def _remove_row(self, row_frame, entry) -> None:
        # A segmented button needs at least one segment — refuse to
        # delete the last row. The user can clear its text instead;
        # empty rows are dropped on save anyway.
        if len(self._rows) <= 1:
            return
        if entry in self._rows:
            self._rows.remove(entry)
        try:
            row_frame.destroy()
        except tk.TclError:
            pass
        # Renumber the visible labels — index column drifts otherwise.
        self._renumber_rows()

    def _remove_last_row(self) -> None:
        if len(self._rows) <= 1:
            return
        last_entry = self._rows[-1]
        try:
            last_entry.master.destroy()
        except tk.TclError:
            pass
        self._rows.pop()
        self._renumber_rows()

    def _renumber_rows(self) -> None:
        for new_idx, entry in enumerate(self._rows, start=1):
            try:
                # entry.master is the row CTkFrame; its first child
                # (winfo_children()[0]) is the index CTkLabel.
                row = entry.master
                children = row.winfo_children()
                if children:
                    children[0].configure(text=f"{new_idx}")
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------
    def _on_ok(self) -> None:
        values = []
        for entry in self._rows:
            try:
                v = entry.get()
            except tk.TclError:
                continue
            if v.strip():
                values.append(v)
        self.result = values
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()


if __name__ == "__main__":
    root = ctk.CTk()
    ctk.set_appearance_mode("dark")
    root.geometry("220x100")
    root.title("Segment Values — Smoke Test")

    def open_dialog():
        d = SegmentValuesDialog(
            root, "Edit Segments", ["First", "Second", "Third"],
        )
        d.wait_window()
        print("Result:", d.result)

    ctk.CTkButton(root, text="Open Editor", command=open_dialog).pack(
        pady=32,
    )
    root.mainloop()
