"""Shared "New Project" form component.

Used by both StartupDialog (bundled welcome screen) and
NewProjectSizeDialog (File → New). Owns:
- screen-size catalog + defaults
- Name / Save to / Device / Screen / W / H form widgets
- validation (empty, forbidden chars, missing dir, existing file)
- error feedback (red border, bell, messagebox)

Use `form.validate_and_get()` to collect a validated result tuple
`(name, path, w, h)` or `None` if validation failed.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app.core.paths import (
    get_default_projects_dir, project_folder,
)
from app.core.project_folder import bootstrap_project_folder
from app.ui.icons import load_icon

# ---- Style ------------------------------------------------------------------
PANEL_BG = "#252526"
SUBTITLE_FG = "#888888"
FIELD_FG = "#cccccc"
ENTRY_BORDER_NORMAL = "#3c3c3c"
ENTRY_BORDER_ERROR = "#d04040"

# ---- Catalog ----------------------------------------------------------------
# Modern 2024 flagships for mobile/tablet, practical app-window sizes for
# desktop. Device selection filters the Screen Size dropdown.
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
DEFAULT_SCREEN_INDEX = 1   # Desktop → Medium (1024 × 768)

W_MIN, W_MAX = 100, 4000
H_MIN, H_MAX = 100, 4000

# Characters Windows forbids in filenames. Rejected up-front so disk
# save can't fail because of the name.
FORBIDDEN_NAME_CHARS = set('\\/:*?"<>|')


def format_size_label(name: str, w: int, h: int) -> str:
    return f"{name}  ({w}×{h})"


def _label_for_size(w: int, h: int) -> tuple[str, str]:
    """Find the device + screen-preset label that matches a w/h, so
    the dropdown stays in sync with caller-supplied dimensions.
    Falls back to ``(Custom, Custom)`` when nothing matches.
    """
    for device, sizes in SCREEN_SIZES_BY_DEVICE.items():
        for n, sw, sh in sizes:
            if sw == w and sh == h:
                return format_size_label(n, sw, sh), device
    return "Custom", "Custom"


class NewProjectForm(ctk.CTkFrame):
    """Reusable New Project form panel."""

    def __init__(
        self,
        master,
        *,
        default_w: int = 800,
        default_h: int = 600,
        default_name: str = "Untitled",
        default_save_dir: str | None = None,
    ):
        super().__init__(master, fg_color=PANEL_BG, corner_radius=6)

        default_sizes = SCREEN_SIZES_BY_DEVICE[DEFAULT_DEVICE]
        fallback_name, fallback_w, fallback_h = default_sizes[
            DEFAULT_SCREEN_INDEX
        ]
        w_initial = default_w or fallback_w
        h_initial = default_h or fallback_h
        self._w_var = tk.StringVar(value=str(w_initial))
        self._h_var = tk.StringVar(value=str(h_initial))
        # If the caller's W/H matches one of the Desktop presets, pick
        # that label so the Screen Size dropdown stays in sync; fall
        # back to Custom (empty list) when nothing matches.
        screen_label, device_label = _label_for_size(w_initial, h_initial)
        self._screen_var = tk.StringVar(value=screen_label)
        self._device_var = tk.StringVar(value=device_label)
        self._name_var = tk.StringVar(value=default_name)
        self._save_dir_var = tk.StringVar(
            value=default_save_dir or str(get_default_projects_dir()),
        )
        self._preview_var = tk.StringVar()

        self._size_map: dict[str, tuple[int, int]] = {}
        self._screen_menu: ctk.CTkOptionMenu | None = None
        self._name_entry: ctk.CTkEntry | None = None
        self._rebuild_size_map(DEFAULT_DEVICE)

        # Live-update the preview line whenever the name or save dir
        # changes — user can see exactly where the project will land
        # before clicking Create.
        self._name_var.trace_add(
            "write",
            lambda *_a: (self._clear_name_error(), self._refresh_preview()),
        )
        self._save_dir_var.trace_add(
            "write", lambda *_a: self._refresh_preview(),
        )

        self._build()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build(self) -> None:
        ctk.CTkLabel(
            self, text="New Project",
            font=("Segoe UI", 11, "bold"),
            text_color=SUBTITLE_FG, anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 10))

        self._add_row("Name", self._build_name_entry)
        self._add_row("Save to", self._build_save_dir_row)
        self._build_preview_label()
        self._refresh_preview()
        self._add_separator()
        self._add_row("Device", self._build_device_dropdown)
        self._add_row("Screen Size", self._build_screen_dropdown)
        self._add_separator()
        self._add_row("Width", self._build_width_entry)
        self._add_row("Height", self._build_height_entry)

    def _add_row(self, label: str, builder) -> None:
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(
            row, text=f"{label}:", width=88, anchor="w",
            font=("Segoe UI", 11), text_color=FIELD_FG,
        ).pack(side="left")
        builder(row)

    def _add_separator(self) -> None:
        ctk.CTkFrame(self, height=1, fg_color="#333333").pack(
            fill="x", padx=14, pady=(10, 10),
        )

    def _build_name_entry(self, row) -> None:
        entry = ctk.CTkEntry(
            row, textvariable=self._name_var, height=26,
            corner_radius=3, font=("Segoe UI", 11), justify="left",
            border_color=ENTRY_BORDER_NORMAL, border_width=1,
        )
        entry.pack(side="left", fill="x", expand=True)
        self._name_entry = entry

    def _build_save_dir_row(self, row) -> None:
        ctk.CTkEntry(
            row, textvariable=self._save_dir_var, height=26,
            corner_radius=3, font=("Segoe UI", 10), justify="left",
            border_color=ENTRY_BORDER_NORMAL, border_width=1,
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        folder_icon = load_icon("folder", size=14)
        ctk.CTkButton(
            row, text="" if folder_icon else "…",
            image=folder_icon, width=28, height=26,
            corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_pick_save_dir,
        ).pack(side="left")

    def _build_preview_label(self) -> None:
        # Hint line right under the Save to row — shows where the
        # project folder + file will land. Width is locked so a long
        # path doesn't widen the label (and through it, the dialog +
        # the Name entry).
        lbl = tk.Label(
            self, textvariable=self._preview_var,
            font=("Segoe UI", 9, "italic"),
            fg=SUBTITLE_FG, bg=PANEL_BG,
            anchor="w", justify="left",
            width=58,  # in chars; bounds the label visually
        )
        lbl.pack(fill="x", padx=(102, 14), pady=(0, 2))
        self._preview_label = lbl

    def _refresh_preview(self) -> None:
        name = (self._name_var.get() or "").strip()
        save_dir = self._save_dir_var.get() or ""
        if not name or not save_dir:
            self._preview_var.set("")
            return
        try:
            target = str(project_folder(save_dir, name)) + "/"
        except (OSError, ValueError):
            self._preview_var.set("")
            return
        # Truncate long paths from the front so the project file
        # name (the part the user actually cares about) stays visible.
        max_len = 56
        if len(target) > max_len:
            target = "..." + target[-(max_len - 3):]
        self._preview_var.set(f"→ {target}")

    def _build_device_dropdown(self, row) -> None:
        ctk.CTkOptionMenu(
            row, values=DEVICE_OPTIONS, variable=self._device_var,
            width=220, height=26,
            font=("Segoe UI", 10), dropdown_font=("Segoe UI", 10),
            fg_color="#2d2d2d", button_color="#2d2d2d",
            button_hover_color="#3a3a3a", corner_radius=3,
            command=self._on_device_selected,
        ).pack(side="left", fill="x", expand=True)

    def _build_screen_dropdown(self, row) -> None:
        values = list(self._size_map.keys()) or ["—"]
        menu = ctk.CTkOptionMenu(
            row, values=values, variable=self._screen_var,
            width=220, height=26,
            font=("Segoe UI", 10), dropdown_font=("Segoe UI", 10),
            fg_color="#2d2d2d", button_color="#2d2d2d",
            button_hover_color="#3a3a3a", corner_radius=3,
            command=self._on_screen_selected,
        )
        menu.pack(side="left", fill="x", expand=True)
        self._screen_menu = menu

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

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def _rebuild_size_map(self, device: str) -> None:
        self._size_map = {
            format_size_label(n, w, h): (w, h)
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

    def _on_pick_save_dir(self) -> None:
        path = filedialog.askdirectory(
            parent=self.winfo_toplevel(),
            title="Choose save location",
            initialdir=self._save_dir_var.get() or str(Path.home()),
        )
        if path:
            self._save_dir_var.set(path)

    # ------------------------------------------------------------------
    # Error feedback
    # ------------------------------------------------------------------
    def _flag_name_error(self) -> None:
        try:
            self.winfo_toplevel().bell()
        except tk.TclError:
            pass
        if self._name_entry is not None:
            self._name_entry.configure(border_color=ENTRY_BORDER_ERROR)

    def _clear_name_error(self) -> None:
        if self._name_entry is not None:
            self._name_entry.configure(border_color=ENTRY_BORDER_NORMAL)

    # ------------------------------------------------------------------
    # Validation + result
    # ------------------------------------------------------------------
    def validate_and_get(self) -> tuple[str, str, int, int] | None:
        """Return (name, path, w, h) on success, None on failure.

        Failure modes show inline error feedback (bell, red border,
        optional messagebox) and leave the form open.
        """
        try:
            w = max(W_MIN, min(W_MAX, int(self._w_var.get())))
            h = max(H_MIN, min(H_MAX, int(self._h_var.get())))
        except ValueError:
            return None

        name = self._name_var.get().strip()
        if not name:
            self._flag_name_error()
            return None
        if any(c in FORBIDDEN_NAME_CHARS for c in name):
            self._flag_name_error()
            messagebox.showwarning(
                "Invalid name",
                "Project name may not contain any of these characters:\n\n"
                '    \\  /  :  *  ?  "  <  >  |\n\n'
                "Please use only valid filename characters.",
                parent=self.winfo_toplevel(),
            )
            return None

        save_dir = Path(self._save_dir_var.get()).expanduser()
        if not save_dir.exists():
            self._flag_name_error()
            return None
        # New project = new folder. Refuse if the folder already
        # exists so we never overwrite an existing project's files.
        target_folder = project_folder(save_dir, name)
        if target_folder.exists():
            self._flag_name_error()
            messagebox.showwarning(
                "Folder exists",
                f"A folder named '{name}' already exists at:\n\n"
                f"{save_dir}\n\n"
                "Pick a different project name or save location.",
                parent=self.winfo_toplevel(),
            )
            return None
        # Bootstrap the multi-page folder structure: project.json +
        # assets/{pages,fonts,images,icons}/. The first page's
        # .ctkproj is written by save_project after this returns;
        # the path we return points at where it will land.
        try:
            _folder, _meta, page_path = bootstrap_project_folder(
                save_dir, name,
            )
        except OSError:
            self._flag_name_error()
            messagebox.showerror(
                "Save location unwritable",
                f"Could not create:\n\n{target_folder}\n\n"
                "Pick a different save location.",
                parent=self.winfo_toplevel(),
            )
            return None
        return name, str(page_path), w, h
