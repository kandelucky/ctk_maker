"""Save-as-prefab modal — name + target folder picker.

Returns ``(name, target_path)`` on OK; ``None`` on Cancel. ``target_path``
is the full ``.ctkprefab`` file path inside the user's prefab library
(see ``app/core/prefab_paths.py``).

If the selection contains any ``var:<uuid>`` token bindings, an
inline warning shows that those bindings will be replaced with their
current literal values — Phase A keeps prefabs portable across
projects whose variable namespaces don't match.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from app.core.prefab_paths import (
    PREFAB_EXT, ensure_prefabs_root,
)

_FORBIDDEN = set('\\/:*?"<>|')
_ROOT_LABEL = "(root)"


def _is_valid_name(name: str) -> bool:
    name = name.strip()
    if not name or name in (".", ".."):
        return False
    return not any(ch in _FORBIDDEN for ch in name)


def _list_folders(root: Path) -> list[str]:
    """Recursive list of subfolder paths relative to ``root``, sorted
    by name. Returns POSIX-style paths so the dropdown reads
    consistently across platforms.
    """
    out: list[str] = []
    for path in root.rglob("*"):
        if path.is_dir():
            rel = path.relative_to(root).as_posix()
            out.append(rel)
    out.sort()
    return out


class PrefabSaveDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        default_name: str,
        var_binding_count: int = 0,
        initial_folder: str = "",
    ):
        super().__init__(parent)
        self.title("Save as prefab")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result: tuple[str, Path] | None = None
        self._root_dir = ensure_prefabs_root()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(padx=20, pady=(18, 10), fill="x")

        ctk.CTkLabel(body, text="Name").grid(
            row=0, column=0, sticky="w", pady=(0, 4),
        )
        self._name_var = tk.StringVar(value=default_name)
        name_entry = ctk.CTkEntry(
            body, textvariable=self._name_var, width=260,
        )
        name_entry.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        ctk.CTkLabel(body, text="Folder").grid(
            row=2, column=0, sticky="w", pady=(0, 4),
        )
        folders = [_ROOT_LABEL] + _list_folders(self._root_dir)
        self._folder_var = tk.StringVar(
            value=initial_folder if initial_folder in folders else _ROOT_LABEL,
        )
        ctk.CTkOptionMenu(
            body, values=folders, variable=self._folder_var, width=260,
        ).grid(row=3, column=0, sticky="ew", pady=(0, 10))

        body.grid_columnconfigure(0, weight=1)

        if var_binding_count > 0:
            warn = ctk.CTkLabel(
                self,
                text=(
                    f"⚠ {var_binding_count} variable binding(s) will be "
                    "replaced with their current values."
                ),
                text_color="#cc7e1f",
                font=("Segoe UI", 10),
                wraplength=280,
                justify="left",
            )
            warn.pack(padx=20, pady=(0, 8), anchor="w")

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(4, 16))
        ctk.CTkButton(
            footer, text="Save", width=120, height=32,
            corner_radius=4, command=self._on_ok,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel", width=90, height=32,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))

        self.bind("<Return>", lambda _e: self._on_ok())
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        name_entry.focus_set()
        name_entry.select_range(0, tk.END)
        self.after(100, self._center_on_parent)

    def _on_ok(self) -> None:
        from tkinter import messagebox
        name = self._name_var.get().strip()
        if not _is_valid_name(name):
            self.bell()
            messagebox.showwarning(
                "Invalid name",
                "Names can't be empty or contain \\ / : * ? \" < > |.",
                parent=self,
            )
            return
        folder_label = self._folder_var.get()
        if folder_label == _ROOT_LABEL:
            target_dir = self._root_dir
        else:
            target_dir = self._root_dir / folder_label
        target_path = target_dir / f"{name}{PREFAB_EXT}"
        if target_path.exists():
            self.bell()
            overwrite = messagebox.askyesno(
                "Already exists",
                f"'{name}{PREFAB_EXT}' already exists in this folder. "
                "Overwrite?",
                parent=self,
            )
            if not overwrite:
                return
        self.result = (name, target_path)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
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
            return
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
