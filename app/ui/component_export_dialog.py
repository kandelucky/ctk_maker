"""Modal — export an existing ``.ctkcomp`` to an arbitrary disk
location. Shows component metadata, lets the user override the
``author`` field for this export only, and writes a copy at the
chosen path.

Returns ``True`` from ``run()`` when the file was written.
"""

from __future__ import annotations

import datetime
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app.core.component_paths import COMPONENT_EXT, component_display_stem
from app.core.logger import log_error
from app.core.settings import load_settings, save_setting
from app.io.component_io import load_metadata, rewrite_payload_author
from app.ui.managed_window import ManagedToplevel
from app.ui.system_fonts import ui_font

LAST_AUTHOR_KEY = "last_component_author"

_FORBIDDEN = set('\\/:*?"<>|')


def _is_valid_name(name: str) -> bool:
    name = name.strip()
    if not name or name in (".", ".."):
        return False
    return not any(ch in _FORBIDDEN for ch in name)


def _format_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    kb = num_bytes / 1024
    if kb < 1024:
        return f"{kb:.1f} KB"
    mb = kb / 1024
    return f"{mb:.1f} MB"


def _format_date(iso: str) -> str:
    return iso[:10] if iso else ""


class ComponentExportDialog(ManagedToplevel):
    window_title = "Export component"
    default_size = (400, 360)
    min_size = (380, 340)
    panel_padding = (0, 0)
    modal = True
    window_resizable = (False, False)

    def __init__(self, parent, source_path: Path):
        self.result: bool = False
        self._source_path = source_path
        self._destination: Path | None = None
        self._meta = load_metadata(source_path) or {}
        try:
            self._file_bytes = source_path.stat().st_size
        except OSError:
            self._file_bytes = 0
        cached_author = str(
            load_settings().get(LAST_AUTHOR_KEY, "") or "",
        )
        self._cached_author = cached_author
        self._name_var = tk.StringVar(
            master=parent, value=component_display_stem(source_path),
        )
        self._author_var = tk.StringVar(
            master=parent,
            value=self._meta.get("author", "") or cached_author,
        )
        self._dest_var = tk.StringVar(master=parent, value="")
        super().__init__(parent)

    def default_offset(self, parent) -> tuple[int, int]:
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            w, h = self.default_size
            return (
                max(0, px + (pw - w) // 2),
                max(0, py + (ph - h) // 2),
            )
        except tk.TclError:
            return (100, 100)

    def build_content(self) -> ctk.CTkFrame:
        container = ctk.CTkFrame(self, fg_color="transparent")
        meta = self._meta

        body = ctk.CTkFrame(container, fg_color="transparent")
        body.pack(padx=20, pady=(18, 6), fill="x")

        ctk.CTkLabel(
            body,
            text=meta.get("name") or component_display_stem(self._source_path),
            font=ui_font(14, "bold"),
            text_color="#e6e6e6", anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            body,
            text=(
                f"{meta.get('view_w', 0)} × {meta.get('view_h', 0)}"
                f"  ·  {_format_size(self._file_bytes)}"
                f"  ·  {_format_date(meta.get('created_at', ''))}"
            ),
            font=ui_font(9),
            text_color="#888888", anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(0, 12))

        ctk.CTkLabel(
            body, text="Name", font=ui_font(10),
        ).grid(row=2, column=0, sticky="w", pady=(0, 4))
        ctk.CTkEntry(
            body, textvariable=self._name_var, width=320,
        ).grid(row=3, column=0, sticky="ew", pady=(0, 12))

        ctk.CTkLabel(
            body, text="Author", font=ui_font(10),
        ).grid(row=4, column=0, sticky="w", pady=(0, 4))
        ctk.CTkEntry(
            body, textvariable=self._author_var, width=320,
            placeholder_text="optional",
        ).grid(row=5, column=0, sticky="ew", pady=(0, 12))

        ctk.CTkLabel(
            body, text="Destination folder", font=ui_font(10),
        ).grid(row=6, column=0, sticky="w", pady=(0, 4))
        path_row = ctk.CTkFrame(body, fg_color="transparent")
        path_row.grid(row=7, column=0, sticky="ew", pady=(0, 12))
        path_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(
            path_row, textvariable=self._dest_var,
            placeholder_text="(pick a folder)", height=28,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            path_row, text="Browse…", width=80, height=28,
            corner_radius=4, command=self._on_browse,
        ).grid(row=0, column=1)

        body.grid_columnconfigure(0, weight=1)

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(4, 16))
        ctk.CTkButton(
            footer, text="Export", width=120, height=32,
            corner_radius=4, command=self._on_export,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel", width=90, height=32,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))
        return container

    def _on_browse(self) -> None:
        path = filedialog.askdirectory(
            parent=self,
            title="Export component — pick destination folder",
        )
        if not path:
            return
        self._dest_var.set(path)

    def _on_export(self) -> None:
        dest = self._dest_var.get().strip()
        if not dest:
            self.bell()
            messagebox.showwarning(
                "Pick a destination",
                "Click Browse… to choose a destination folder.",
                parent=self,
            )
            return
        # Strip a trailing extension if user typed one — we'll add the
        # canonical one back below so the resulting path is always
        # exactly one ".ctkcomp".
        name = self._name_var.get().strip()
        if name.lower().endswith(COMPONENT_EXT):
            name = name[: -len(COMPONENT_EXT)]
        if not _is_valid_name(name):
            self.bell()
            messagebox.showwarning(
                "Invalid name",
                "Names can't be empty or contain \\ / : * ? \" < > |.",
                parent=self,
            )
            return
        dest_dir = Path(dest)
        if not dest_dir.is_dir():
            self.bell()
            messagebox.showwarning(
                "Folder not found",
                f"'{dest_dir}' is not a folder. Pick another destination.",
                parent=self,
            )
            return
        dest_path = dest_dir / f"{name}{COMPONENT_EXT}"
        if dest_path.exists():
            overwrite = messagebox.askyesno(
                "Already exists",
                f"'{dest_path.name}' already exists in this folder. "
                "Overwrite?",
                parent=self,
            )
            if not overwrite:
                return
        try:
            shutil.copy2(self._source_path, dest_path)
        except OSError as exc:
            messagebox.showerror(
                "Export failed",
                f"Couldn't write to:\n{dest_path}\n\n{exc}",
                parent=self,
            )
            log_error(f"component export {dest_path}")
            return
        # Override author on the copy if the user changed it; the
        # original library file is untouched either way.
        new_author = self._author_var.get().strip()
        try:
            rewrite_payload_author(dest_path, new_author)
        except OSError:
            log_error(f"component export rewrite {dest_path}")
        if new_author and new_author != self._cached_author:
            save_setting(LAST_AUTHOR_KEY, new_author)
        self.result = True
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = False
        self.destroy()
