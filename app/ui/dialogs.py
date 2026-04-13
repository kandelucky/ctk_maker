"""Small modal dialogs used by the builder.

NewProjectSizeDialog: on File → New. Offers preset sizes + drag-scrubable
width/height entries. Returns (w, h) via `.result` or None if cancelled.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

PRESETS = [
    ("Desktop Small",   800,  600),
    ("Desktop Medium", 1024,  768),
    ("Desktop Large",  1280,  800),
    ("Wide",           1440,  900),
    ("Square",          600,  600),
    ("Portrait",        600,  800),
]

W_MIN, W_MAX = 100, 4000
H_MIN, H_MAX = 100, 4000

PANEL_BG = "#252526"
HOVER_BG = "#2d2d30"
SUBTITLE_FG = "#888888"
LABEL_FG = "#cccccc"


class NewProjectSizeDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        default_w: int = 800,
        default_h: int = 600,
    ):
        super().__init__(parent)
        self.title("New project")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result: tuple[int, int] | None = None

        self._w_var = tk.StringVar(value=str(default_w))
        self._h_var = tk.StringVar(value=str(default_h))

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(padx=24, pady=20, fill="both", expand=True)

        ctk.CTkLabel(
            container, text="New Project",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        self._build_presets(container)
        self._build_custom(container)
        self._build_buttons(container)

        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.after(100, self._center_on_parent)

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------
    def _build_presets(self, parent) -> None:
        ctk.CTkLabel(
            parent, text="Templates",
            font=("Segoe UI", 10, "bold"), text_color=SUBTITLE_FG, anchor="w",
        ).pack(fill="x", pady=(0, 4))

        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.pack(fill="x", pady=(0, 14))
        for i in range(3):
            grid.grid_columnconfigure(i, weight=1, uniform="preset")

        for idx, (name, w, h) in enumerate(PRESETS):
            row, col = divmod(idx, 3)
            self._make_preset_card(grid, name, w, h, row=row, col=col)

    def _make_preset_card(self, parent, name: str, w: int, h: int,
                          row: int, col: int) -> None:
        card = ctk.CTkFrame(parent, fg_color=PANEL_BG, corner_radius=4)
        card.grid(row=row, column=col, sticky="ew", padx=3, pady=3)

        title = ctk.CTkLabel(
            card, text=name, font=("Segoe UI", 11, "bold"),
            text_color=LABEL_FG, anchor="w",
        )
        title.pack(fill="x", padx=10, pady=(6, 0))

        dims = ctk.CTkLabel(
            card, text=f"{w} × {h}", font=("Segoe UI", 10),
            text_color=SUBTITLE_FG, anchor="w",
        )
        dims.pack(fill="x", padx=10, pady=(0, 6))

        def on_enter(_e, c=card):
            c.configure(fg_color=HOVER_BG)

        def on_leave(_e, c=card):
            c.configure(fg_color=PANEL_BG)

        def on_click(_e, ww=w, hh=h):
            self._w_var.set(str(ww))
            self._h_var.set(str(hh))

        for wdg in (card, title, dims):
            wdg.bind("<Enter>", on_enter, add="+")
            wdg.bind("<Leave>", on_leave, add="+")
            wdg.bind("<Button-1>", on_click, add="+")

    def _build_custom(self, parent) -> None:
        ctk.CTkLabel(
            parent, text="Custom size",
            font=("Segoe UI", 10, "bold"), text_color=SUBTITLE_FG, anchor="w",
        ).pack(fill="x", pady=(0, 4))

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0, 14))

        self._make_scrub_field(
            row, label="W", var=self._w_var,
            lo=W_MIN, hi=W_MAX, col=0,
        )
        self._make_scrub_field(
            row, label="H", var=self._h_var,
            lo=H_MIN, hi=H_MAX, col=1,
        )

    def _make_scrub_field(self, parent, *, label: str, var: tk.StringVar,
                          lo: int, hi: int, col: int) -> None:
        lbl = ctk.CTkLabel(
            parent, text=label, font=("Consolas", 11),
            text_color=SUBTITLE_FG, width=16,
        )
        lbl.grid(row=0, column=col * 2, padx=(0, 4))

        entry = ctk.CTkEntry(
            parent, textvariable=var, width=80, height=26,
            corner_radius=3, font=("Segoe UI", 11), justify="left",
        )
        entry.grid(row=0, column=col * 2 + 1, padx=(0, 14))

        self._bind_drag_scrub(lbl, var, lo, hi)

        try:
            lbl.configure(cursor="sb_h_double_arrow")
        except tk.TclError:
            pass

    def _bind_drag_scrub(self, label, var: tk.StringVar,
                         lo: int, hi: int) -> None:
        state = {"x": 0, "val": 0, "active": False}

        def on_press(event):
            try:
                state["val"] = int(var.get())
            except ValueError:
                state["val"] = lo
            state["x"] = event.x_root
            state["active"] = True

        def on_motion(event):
            if not state["active"]:
                return
            dx = event.x_root - state["x"]
            if event.state & 0x20000:  # Alt → fine
                dx = int(dx * 0.2)
            new = max(lo, min(hi, state["val"] + dx))
            var.set(str(new))

        def on_release(_e):
            state["active"] = False

        label.bind("<ButtonPress-1>", on_press, add="+")
        label.bind("<B1-Motion>", on_motion, add="+")
        label.bind("<ButtonRelease-1>", on_release, add="+")

    def _build_buttons(self, parent) -> None:
        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill="x")

        spacer = ctk.CTkFrame(btn_row, fg_color="transparent")
        spacer.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            btn_row, text="Cancel", width=80, height=30,
            command=self._on_cancel,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            btn_row, text="Create", width=80, height=30,
            command=self._on_ok,
        ).pack(side="left")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def _center_on_parent(self) -> None:
        self.update_idletasks()
        parent = self.master
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
        except tk.TclError:
            return
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _on_ok(self) -> None:
        try:
            w = max(W_MIN, min(W_MAX, int(self._w_var.get())))
            h = max(H_MIN, min(H_MAX, int(self._h_var.get())))
        except ValueError:
            return
        self.result = (w, h)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()
