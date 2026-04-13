"""Welcome / startup dialog shown when the builder launches.

50/50 split:
    Left half  — recent projects (click to open).
    Right half — new project tools: device + screen-size dropdown,
                 editable width/height, Create button.

Result is exposed via `.result` as one of:
    ("open", "<absolute path>") — user picked a recent file or browsed
    ("new",  w, h)              — user filled the New Project panel
    None                        — user closed the dialog
"""

from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app.core.recent_files import load_recent, remove_recent
from app.ui.icons import load_icon

DIALOG_W = 740
DIALOG_H = 510

BG = "#1e1e1e"
PANEL_BG = "#252526"
HOVER_BG = "#2d2d30"
SELECTED_BG = "#094771"
TITLE_FG = "#e0e0e0"
SUBTITLE_FG = "#888888"
FIELD_FG = "#cccccc"
FILE_NAME_FG = "#cccccc"
FILE_PATH_FG = "#666666"
META_FG = "#6a6a6a"
ENTRY_BORDER_NORMAL = "#3c3c3c"
ENTRY_BORDER_ERROR = "#d04040"


def _relative_time(ts: float) -> str:
    """Format a unix timestamp as 'Xm ago' / 'Xh ago' / etc."""
    diff = time.time() - ts
    if diff < 0:
        return "just now"
    if diff < 60:
        return "just now"
    if diff < 3600:
        return f"{int(diff / 60)}m ago"
    if diff < 86400:
        return f"{int(diff / 3600)}h ago"
    if diff < 604800:
        return f"{int(diff / 86400)}d ago"
    if diff < 2592000:
        return f"{int(diff / 604800)}w ago"
    if diff < 31536000:
        return f"{int(diff / 2592000)}mo ago"
    return f"{int(diff / 31536000)}y ago"

# Screen sizes grouped by device type (modern 2024 flagships for mobile
# and tablet; practical app-window sizes for desktop). Device selection
# filters the Screen Size dropdown. "Custom" hides presets.
SCREEN_SIZES_BY_DEVICE: dict[str, list[tuple[str, int, int]]] = {
    "Desktop": [
        ("Small",              800,  600),
        ("Medium",            1024,  768),
        ("Large",             1280,  800),
        ("HD 720p",           1280,  720),
        ("WXGA+",             1440,  900),
        ("HD+",               1600,  900),
        ("Full HD 1080p",     1920, 1080),
        ("WUXGA 16:10",       1920, 1200),
        ("QHD 1440p",         2560, 1440),
        ("4K UHD",            3840, 2160),
    ],
    "Mobile": [
        ("iPhone 15",          393,  852),
        ("iPhone 15 Pro Max",  430,  932),
        ("Pixel 8",            412,  915),
        ("Pixel 8 Pro",        448,  998),
        ("Galaxy S24",         360,  780),
        ("Galaxy S24 Ultra",   412,  915),
    ],
    "Tablet": [
        ("iPad Mini",          744, 1133),
        ("iPad 10.9",          820, 1180),
        ("iPad Air 11",        820, 1180),
        ("iPad Pro 11",        834, 1210),
        ("iPad Pro 13",       1032, 1376),
        ("Galaxy Tab S9+",     800, 1280),
        ("Galaxy Tab S9 Ultra", 960, 1520),
    ],
    "Custom": [],
}

DEVICE_OPTIONS = list(SCREEN_SIZES_BY_DEVICE.keys())
DEFAULT_DEVICE = "Desktop"
DEFAULT_SCREEN_INDEX = 1   # Desktop → SVGA (800 × 600)
W_MIN, W_MAX = 100, 4000
H_MIN, H_MAX = 100, 4000

# Characters Windows forbids in filenames. We reject them up-front in
# the New Project dialog so saving can never fail because of the name.
FORBIDDEN_NAME_CHARS = set('\\/:*?"<>|')


def _format_size_label(name: str, w: int, h: int) -> str:
    return f"{name}  ({w}×{h})"


class StartupDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("CTk Visual Builder")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=BG)

        self.result: tuple | None = None

        default_sizes = SCREEN_SIZES_BY_DEVICE[DEFAULT_DEVICE]
        default_name, default_w, default_h = default_sizes[DEFAULT_SCREEN_INDEX]
        self._w_var = tk.StringVar(value=str(default_w))
        self._h_var = tk.StringVar(value=str(default_h))
        self._screen_var = tk.StringVar(
            value=_format_size_label(default_name, default_w, default_h),
        )
        self._device_var = tk.StringVar(value=DEFAULT_DEVICE)
        self._size_map: dict[str, tuple[int, int]] = {}
        self._screen_menu: ctk.CTkOptionMenu | None = None
        self._rebuild_size_map(DEFAULT_DEVICE)

        self._name_var = tk.StringVar(value="Untitled")
        default_dir = Path.home() / "Desktop"
        self._save_dir_var = tk.StringVar(value=str(default_dir))

        self._name_entry: ctk.CTkEntry | None = None
        self._save_dir_entry: ctk.CTkEntry | None = None

        self._selected_recent_path: str | None = None
        self._recent_rows: list[tuple[ctk.CTkFrame, str]] = []
        self._open_btn: ctk.CTkButton | None = None
        self._recent_scroll: ctk.CTkScrollableFrame | None = None
        self._recent_empty_label: ctk.CTkLabel | None = None

        self._name_var.trace_add("write", lambda *_a: self._clear_name_error())

        self.geometry(f"{DIALOG_W}x{DIALOG_H}")
        self._center_on_parent()

        self._build_header()
        self._build_body()
        self._build_footer()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda e: self._on_close())
        self.bind("<Return>", lambda e: self._on_create())

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _center_on_parent(self) -> None:
        self.update_idletasks()
        try:
            px = self.master.winfo_rootx()
            py = self.master.winfo_rooty()
            pw = self.master.winfo_width()
            ph = self.master.winfo_height()
        except tk.TclError:
            return
        x = px + (pw - DIALOG_W) // 2
        y = py + (ph - DIALOG_H) // 2
        self.geometry(f"{DIALOG_W}x{DIALOG_H}+{max(0, x)}+{max(0, y)}")

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(18, 8))

        ctk.CTkLabel(
            header, text="CTk Visual Builder",
            font=("Segoe UI", 18, "bold"), text_color=TITLE_FG, anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            header, text="Open a recent project or create a new one",
            font=("Segoe UI", 11), text_color=SUBTITLE_FG, anchor="w",
        ).pack(fill="x", pady=(2, 0))

    def _build_body(self) -> None:
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(0, 8))
        body.grid_columnconfigure(0, weight=1, minsize=200)
        body.grid_columnconfigure(1, weight=0, minsize=12)
        body.grid_columnconfigure(2, weight=2, minsize=380)
        body.grid_rowconfigure(0, weight=1)

        self._build_recent_panel(body)
        self._build_new_panel(body)

    def _build_recent_panel(self, body) -> None:
        left = ctk.CTkFrame(body, fg_color=PANEL_BG, corner_radius=6)
        left.grid(row=0, column=0, sticky="nsew")

        ctk.CTkLabel(
            left, text="Recent",
            font=("Segoe UI", 11, "bold"), text_color=SUBTITLE_FG, anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 6))

        scroll = ctk.CTkScrollableFrame(
            left, fg_color="transparent", corner_radius=0,
        )
        scroll.pack(fill="both", expand=True, padx=4, pady=(0, 8))
        self._recent_scroll = scroll

        self._populate_recent_list()

        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=(0, 10))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            btn_row, text="Browse...", height=28, corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            font=("Segoe UI", 10),
            command=self._on_browse,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))

        self._open_btn = ctk.CTkButton(
            btn_row, text="Open", height=28, corner_radius=4,
            font=("Segoe UI", 10),
            state="disabled",
            command=self._on_open_selected,
        )
        self._open_btn.grid(row=0, column=1, sticky="ew", padx=(3, 0))

    def _populate_recent_list(self) -> None:
        scroll = self._recent_scroll
        if scroll is None:
            return
        for child in list(scroll.winfo_children()):
            child.destroy()
        self._recent_rows.clear()
        self._recent_empty_label = None

        recent = load_recent()
        if not recent:
            lbl = ctk.CTkLabel(
                scroll, text="No recent projects",
                font=("Segoe UI", 10, "italic"), text_color=FILE_PATH_FG,
            )
            lbl.pack(pady=20)
            self._recent_empty_label = lbl
            return
        for path in recent:
            self._add_recent_row(scroll, path)

    def _on_remove_recent(self, path: str) -> None:
        remove_recent(path)
        if self._selected_recent_path == path:
            self._selected_recent_path = None
            if self._open_btn is not None:
                self._open_btn.configure(state="disabled")
        self._populate_recent_list()

    def _show_recent_menu(self, event, path: str) -> str:
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="Remove from Recent",
            command=lambda p=path: self._on_remove_recent(p),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _add_recent_row(self, parent, path: str) -> None:
        row = ctk.CTkFrame(
            parent, fg_color="transparent", corner_radius=3, height=22,
        )
        row.pack(fill="x", padx=2, pady=1)
        row.pack_propagate(False)

        name = Path(path).stem

        try:
            mtime = Path(path).stat().st_mtime
            time_text = _relative_time(mtime)
        except OSError:
            time_text = "missing"

        parent_dir = str(Path(path).parent)
        if len(parent_dir) > 28:
            parent_dir = "…" + parent_dir[-27:]

        name_lbl = ctk.CTkLabel(
            row, text=name, font=("Segoe UI", 12, "bold"),
            text_color=FILE_NAME_FG, anchor="w",
        )
        name_lbl.pack(side="left", padx=(8, 16))

        time_lbl = ctk.CTkLabel(
            row, text=time_text, font=("Segoe UI", 9),
            text_color=META_FG, anchor="e",
        )
        time_lbl.pack(side="right", padx=(0, 8))

        path_lbl = ctk.CTkLabel(
            row, text=parent_dir, font=("Segoe UI", 9),
            text_color=FILE_PATH_FG, anchor="w",
        )
        path_lbl.pack(side="left", fill="x", expand=True)

        self._recent_rows.append((row, path))

        def on_enter(_e, r=row):
            if self._selected_recent_path != path:
                r.configure(fg_color=HOVER_BG)

        def on_leave(_e, r=row):
            if self._selected_recent_path != path:
                r.configure(fg_color="transparent")

        def on_click(_e, p=path, r=row):
            self._select_recent(p, r)

        def on_double(_e, p=path):
            self._select_recent(p, None)
            self.result = ("open", p)
            self.destroy()

        def on_right(_e, p=path):
            self._show_recent_menu(_e, p)

        for w in (row, name_lbl, path_lbl, time_lbl):
            w.bind("<Enter>", on_enter, add="+")
            w.bind("<Leave>", on_leave, add="+")
            w.bind("<Button-1>", on_click, add="+")
            w.bind("<Double-Button-1>", on_double, add="+")
            w.bind("<Button-3>", on_right, add="+")

    def _select_recent(self, path: str, row: ctk.CTkFrame | None) -> None:
        self._selected_recent_path = path
        for r, _p in self._recent_rows:
            r.configure(fg_color=SELECTED_BG if r is row else "transparent")
        if self._open_btn is not None:
            self._open_btn.configure(state="normal")

    def _on_open_selected(self) -> None:
        if self._selected_recent_path is None:
            return
        self.result = ("open", self._selected_recent_path)
        self.destroy()

    def _build_new_panel(self, body) -> None:
        right = ctk.CTkFrame(body, fg_color=PANEL_BG, corner_radius=6)
        right.grid(row=0, column=2, sticky="nsew")

        ctk.CTkLabel(
            right, text="New Project",
            font=("Segoe UI", 11, "bold"), text_color=SUBTITLE_FG, anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 10))

        self._add_form_row(right, "Name", self._build_name_entry)
        self._add_form_row(right, "Save to", self._build_save_dir_row)

        sep1 = ctk.CTkFrame(right, height=1, fg_color="#333333")
        sep1.pack(fill="x", padx=14, pady=(10, 10))

        self._add_form_row(right, "Device", self._build_device_dropdown)
        self._add_form_row(right, "Screen Size", self._build_screen_dropdown)

        sep2 = ctk.CTkFrame(right, height=1, fg_color="#333333")
        sep2.pack(fill="x", padx=14, pady=(10, 10))

        self._add_form_row(right, "Width", self._build_width_entry)
        self._add_form_row(right, "Height", self._build_height_entry)

    def _add_form_row(self, parent, label: str, builder) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(
            row, text=f"{label}:", width=88, anchor="w",
            font=("Segoe UI", 11), text_color=FIELD_FG,
        ).pack(side="left")
        builder(row)

    def _build_device_dropdown(self, row) -> None:
        menu = ctk.CTkOptionMenu(
            row, values=DEVICE_OPTIONS, variable=self._device_var,
            width=180, height=26, font=("Segoe UI", 10),
            dropdown_font=("Segoe UI", 10),
            fg_color="#2d2d2d", button_color="#2d2d2d",
            button_hover_color="#3a3a3a", corner_radius=3,
            command=self._on_device_selected,
        )
        menu.pack(side="left", fill="x", expand=True)

    def _build_screen_dropdown(self, row) -> None:
        values = list(self._size_map.keys()) or ["—"]
        menu = ctk.CTkOptionMenu(
            row,
            values=values,
            variable=self._screen_var,
            width=180, height=26, font=("Segoe UI", 10),
            dropdown_font=("Segoe UI", 10),
            fg_color="#2d2d2d", button_color="#2d2d2d",
            button_hover_color="#3a3a3a", corner_radius=3,
            command=self._on_screen_selected,
        )
        menu.pack(side="left", fill="x", expand=True)
        self._screen_menu = menu

    def _build_name_entry(self, row) -> None:
        entry = ctk.CTkEntry(
            row, textvariable=self._name_var, height=26,
            corner_radius=3, font=("Segoe UI", 11), justify="left",
            border_color=ENTRY_BORDER_NORMAL, border_width=1,
        )
        entry.pack(side="left", fill="x", expand=True)
        self._name_entry = entry

    def _build_save_dir_row(self, row) -> None:
        entry = ctk.CTkEntry(
            row, textvariable=self._save_dir_var, height=26,
            corner_radius=3, font=("Segoe UI", 10), justify="left",
            border_color=ENTRY_BORDER_NORMAL, border_width=1,
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._save_dir_entry = entry

        folder_icon = load_icon("folder", size=14)
        ctk.CTkButton(
            row, text="" if folder_icon else "…",
            image=folder_icon, width=28, height=26,
            corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_pick_save_dir,
        ).pack(side="left")

    def _build_width_entry(self, row) -> None:
        ctk.CTkEntry(
            row, textvariable=self._w_var, width=80, height=26,
            corner_radius=3, font=("Segoe UI", 11), justify="left",
        ).pack(side="left")

    def _build_height_entry(self, row) -> None:
        ctk.CTkEntry(
            row, textvariable=self._h_var, width=80, height=26,
            corner_radius=3, font=("Segoe UI", 11), justify="left",
        ).pack(side="left")

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(4, 16))
        ctk.CTkButton(
            footer, text="+ Create Project", width=160, height=32,
            corner_radius=4, command=self._on_create,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel", width=90, height=32,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_close,
        ).pack(side="right", padx=(0, 8))

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def _rebuild_size_map(self, device: str) -> None:
        self._size_map = {
            _format_size_label(n, w, h): (w, h)
            for (n, w, h) in SCREEN_SIZES_BY_DEVICE.get(device, [])
        }

    def _on_device_selected(self, device: str) -> None:
        self._rebuild_size_map(device)
        if self._screen_menu is None:
            return
        if not self._size_map:
            self._screen_menu.configure(values=["Custom"], state="disabled")
            self._screen_var.set("Custom")
            return
        values = list(self._size_map.keys())
        self._screen_menu.configure(values=values, state="normal")
        first = values[0]
        self._screen_var.set(first)
        self._on_screen_selected(first)

    def _on_screen_selected(self, label: str) -> None:
        wh = self._size_map.get(label)
        if wh is None:
            return
        w, h = wh
        self._w_var.set(str(w))
        self._h_var.set(str(h))

    def _on_browse(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Open project",
            filetypes=[("CTk Builder project", "*.ctkproj"), ("All files", "*.*")],
        )
        if not path:
            return
        self.result = ("open", path)
        self.destroy()

    def _on_pick_save_dir(self) -> None:
        path = filedialog.askdirectory(
            parent=self,
            title="Choose save location",
            initialdir=self._save_dir_var.get() or str(Path.home()),
        )
        if path:
            self._save_dir_var.set(path)

    def _flag_name_error(self) -> None:
        self.bell()
        if self._name_entry is not None:
            self._name_entry.configure(border_color=ENTRY_BORDER_ERROR)

    def _clear_name_error(self, *_args) -> None:
        if self._name_entry is not None:
            self._name_entry.configure(border_color=ENTRY_BORDER_NORMAL)

    def _on_create(self) -> None:
        try:
            w = max(W_MIN, min(W_MAX, int(self._w_var.get())))
            h = max(H_MIN, min(H_MAX, int(self._h_var.get())))
        except ValueError:
            return
        name = self._name_var.get().strip()
        if not name:
            self._flag_name_error()
            return
        if any(c in FORBIDDEN_NAME_CHARS for c in name):
            self._flag_name_error()
            messagebox.showwarning(
                "Invalid name",
                "Project name may not contain any of these characters:\n\n"
                '    \\  /  :  *  ?  "  <  >  |\n\n'
                "Please use only valid filename characters.",
                parent=self,
            )
            return
        save_dir = Path(self._save_dir_var.get()).expanduser()
        if not save_dir.exists():
            self._flag_name_error()
            return
        full_path = save_dir / f"{name}.ctkproj"
        if full_path.exists():
            self._flag_name_error()
            return
        self.result = ("new", name, w, h, str(full_path))
        self.destroy()

    def _on_close(self) -> None:
        self.result = None
        self.destroy()
