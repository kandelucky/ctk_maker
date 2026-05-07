"""Modal — import an external ``.ctkcomp`` into the project's
``components/`` library. Shows the component's metadata (name, size,
author, date), offers a Preview button + a target-folder picker, and
copies the file into the chosen location on Import.

On filename collision the user picks Overwrite / Rename / Cancel via
``confirm_collision_action``.

Returns ``True`` from ``run()`` when the file was imported.
"""

from __future__ import annotations

import shutil
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from app.core.component_paths import COMPONENT_EXT, component_display_stem
from app.core.logger import log_error
from app.io.component_io import load_metadata, load_payload
from app.ui.dialog_utils import prepare_dialog, reveal_dialog, safe_grab_set

_ROOT_LABEL = "(root)"


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


def _list_folders(root: Path) -> list[str]:
    out: list[str] = []
    for path in root.rglob("*"):
        if path.is_dir():
            rel = path.relative_to(root).as_posix()
            out.append(rel)
    out.sort()
    return out


def _unique_name(target_dir: Path, base_stem: str) -> str:
    """``base_stem_2``, ``base_stem_3``, … until the resulting filename
    doesn't exist in ``target_dir``. Used by the Rename branch of the
    collision dialog.
    """
    n = 2
    while True:
        candidate = f"{base_stem}_{n}{COMPONENT_EXT}"
        if not (target_dir / candidate).exists():
            return candidate
        n += 1


class ComponentImportDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        source_path: Path,
        components_dir: Path,
    ):
        super().__init__(parent)
        prepare_dialog(self)
        self.title("Import component")
        self.resizable(False, False)
        self.transient(parent)
        safe_grab_set(self)

        self.result: bool = False
        self._source_path = source_path
        self._components_dir = components_dir

        self._payload = load_payload(source_path)
        meta = load_metadata(source_path) or {}
        try:
            file_bytes = source_path.stat().st_size
        except OSError:
            file_bytes = 0
        self._meta = meta

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(padx=20, pady=(18, 6), fill="x")

        ctk.CTkLabel(
            body, text=meta.get("name") or component_display_stem(source_path),
            font=("Segoe UI", 14, "bold"),
            text_color="#e6e6e6", anchor="w",
        ).grid(row=0, column=0, sticky="w")

        author = meta.get("author", "") or ""
        date_part = _format_date(meta.get("created_at", ""))
        info_parts = [
            f"{meta.get('view_w', 0)} × {meta.get('view_h', 0)}",
            _format_size(file_bytes),
        ]
        if author:
            info_parts.append(f"by {author}")
        if date_part:
            info_parts.append(date_part)
        ctk.CTkLabel(
            body,
            text="  ·  ".join(info_parts),
            font=("Segoe UI", 9),
            text_color="#888888", anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(0, 12))

        ctk.CTkButton(
            body, text="Preview", width=100, height=28,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_preview,
        ).grid(row=2, column=0, sticky="w", pady=(0, 12))

        ctk.CTkLabel(
            body, text="Import to", font=("Segoe UI", 10),
        ).grid(row=3, column=0, sticky="w", pady=(0, 4))
        folders = [_ROOT_LABEL] + _list_folders(components_dir)
        self._folder_var = tk.StringVar(value=_ROOT_LABEL)
        ctk.CTkOptionMenu(
            body, values=folders, variable=self._folder_var, width=320,
        ).grid(row=4, column=0, sticky="ew", pady=(0, 12))

        body.grid_columnconfigure(0, weight=1)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(4, 16))
        ctk.CTkButton(
            footer, text="Import", width=120, height=32,
            corner_radius=4, command=self._on_import,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel", width=90, height=32,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.after(100, self._center_on_parent)

    def _on_preview(self) -> None:
        if self._payload is None:
            messagebox.showwarning(
                "Preview unavailable",
                "This file isn't a valid component.",
                parent=self,
            )
            return
        from app.ui.component_preview_window import ComponentPreviewWindow
        ComponentPreviewWindow(self, self._payload, self._source_path)

    def _on_import(self) -> None:
        if self._payload is None:
            messagebox.showerror(
                "Invalid component",
                "This file isn't a readable .ctkcomp.",
                parent=self,
            )
            return
        folder_label = self._folder_var.get()
        if folder_label == _ROOT_LABEL:
            target_dir = self._components_dir
        else:
            target_dir = self._components_dir / folder_label
        target_dir.mkdir(parents=True, exist_ok=True)

        # Normalise to the local extension on import — the source
        # file may carry the Hub-upload .ctkcomp.zip suffix from the
        # community library, but the local library uses plain
        # .ctkcomp so files stay short inside the user's project.
        local_stem = component_display_stem(self._source_path)
        target_name = f"{local_stem}{COMPONENT_EXT}"
        target_path = target_dir / target_name
        if target_path.exists():
            action = self._confirm_collision()
            if action == "cancel":
                return
            if action == "rename":
                target_name = _unique_name(target_dir, local_stem)
                target_path = target_dir / target_name
            # "overwrite" → keep target_path as-is; shutil.copy2 will
            # replace it.
        try:
            shutil.copy2(self._source_path, target_path)
        except OSError as exc:
            messagebox.showerror(
                "Import failed",
                f"Couldn't copy:\n{self._source_path}\n→\n{target_path}\n\n{exc}",
                parent=self,
            )
            log_error(f"component import {target_path}")
            return
        self.result = True
        self.destroy()

    def _confirm_collision(self) -> str:
        """Three-button dialog. Returns ``"overwrite"`` / ``"rename"``
        / ``"cancel"``. Tk's stock messagebox doesn't support three
        custom labels portably, so we roll our own tiny modal.
        """
        choice = {"value": "cancel"}
        modal = ctk.CTkToplevel(self)
        modal.title("Already exists")
        modal.transient(self)
        safe_grab_set(modal)
        modal.resizable(False, False)
        ctk.CTkLabel(
            modal,
            text=(
                f"'{self._source_path.name}' already exists in this "
                "folder. Pick how to resolve:"
            ),
            font=("Segoe UI", 10),
            wraplength=320, justify="left",
        ).pack(padx=18, pady=(16, 12))
        row = ctk.CTkFrame(modal, fg_color="transparent")
        row.pack(padx=18, pady=(0, 16))

        def _pick(value: str) -> None:
            choice["value"] = value
            modal.destroy()

        ctk.CTkButton(
            row, text="Overwrite", width=92, height=30,
            corner_radius=4, command=lambda: _pick("overwrite"),
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            row, text="Rename", width=80, height=30,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=lambda: _pick("rename"),
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            row, text="Cancel", width=80, height=30,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=lambda: _pick("cancel"),
        ).pack(side="left")
        modal.protocol("WM_DELETE_WINDOW", lambda: _pick("cancel"))
        modal.bind("<Escape>", lambda _e: _pick("cancel"))
        modal.update_idletasks()
        # Defensive: update_idletasks + safe_grab_set's wait_visibility
        # together pump the event loop twice. A stale Escape from the
        # parent dialog can dispatch to the modal's binding mid-build
        # and call destroy() before we get here. Skip centering +
        # wait_window when that happens — just return the default
        # ``cancel`` choice.
        if not modal.winfo_exists():
            return choice["value"]
        # Center over self
        try:
            sx = self.winfo_rootx()
            sy = self.winfo_rooty()
            sw = self.winfo_width()
            sh = self.winfo_height()
            mw = modal.winfo_width()
            mh = modal.winfo_height()
            modal.geometry(
                f"+{sx + (sw - mw) // 2}+{sy + (sh - mh) // 2}",
            )
        except tk.TclError:
            pass
        if modal.winfo_exists():
            self.wait_window(modal)
        return choice["value"]

    def _on_cancel(self) -> None:
        self.result = False
        self.destroy()

    def _center_on_parent(self) -> None:
        self.update_idletasks()
        parent = self.master
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
        except tk.TclError:
            reveal_dialog(self)
            return
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        reveal_dialog(self)
