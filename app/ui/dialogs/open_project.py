"""File → Open folder pick + classification + ambiguous resolve."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from app.core.project_folder import (
    find_active_page_entry,
    inspect_picked_folder,
    page_file_path,
    read_project_meta,
)
from app.ui.dialog_utils import safe_grab_set
from app.ui.dialogs._base import DarkDialog
from app.ui.dialogs._colors import _ABT_BG, _ABT_FG
from app.ui.system_fonts import ui_font


class _AmbiguousProjectPicker(DarkDialog):
    """Picker shown when a folder has >1 ``.ctkproj`` at its root and
    no ``project.json`` to disambiguate. Lists the candidates in a
    Listbox; ``self.result`` is the chosen ``Path`` or ``None``.
    """

    def __init__(self, parent, folder: Path, candidates: list[Path]) -> None:
        super().__init__(parent)
        self.title("Pick project file")
        self.result: Path | None = None
        self._candidates = candidates

        tk.Label(
            self,
            text=(
                f"Several '.ctkproj' files were found in:\n{folder}\n\n"
                "Pick the one to open."
            ),
            bg=_ABT_BG, fg=_ABT_FG, font=ui_font(10),
            justify="left", wraplength=420,
        ).pack(padx=24, pady=(20, 10))

        self._listbox = tk.Listbox(
            self,
            height=min(8, max(3, len(candidates))),
            width=50,
            bg="#2a2a2a", fg=_ABT_FG, selectbackground="#6366f1",
            relief="flat", bd=0, highlightthickness=0,
            font=ui_font(10),
        )
        for c in candidates:
            self._listbox.insert(tk.END, c.name)
        self._listbox.selection_set(0)
        self._listbox.pack(padx=24, pady=(0, 16))
        self._listbox.bind("<Double-Button-1>", lambda _e: self._on_ok())

        btn_row = tk.Frame(self, bg=_ABT_BG)
        btn_row.pack(pady=(0, 20))
        tk.Button(
            btn_row, text="Cancel", command=self._on_cancel,
            bg="#3a3a3a", fg=_ABT_FG, activebackground="#4a4a4a",
            activeforeground=_ABT_FG, relief="flat", bd=0,
            font=ui_font(10), padx=16, pady=4, cursor="hand2",
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            btn_row, text="Open", command=self._on_ok,
            bg="#6366f1", fg="#ffffff", activebackground="#4f46e5",
            activeforeground="#ffffff", relief="flat", bd=0,
            font=ui_font(10), padx=16, pady=4, cursor="hand2",
        ).pack(side="left")
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._on_ok())

        self.update_idletasks()
        W = self.winfo_reqwidth()
        H = self.winfo_reqheight()
        self.place_centered(W, H, parent)
        self.lift()
        self._listbox.focus_set()
        safe_grab_set(self)
        self.reveal()

    def _on_ok(self) -> None:
        sel = self._listbox.curselection()
        if not sel:
            self.bell()
            return
        self.result = self._candidates[sel[0]]
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()


def prompt_open_project_folder(
    parent, initial_dir: str | None = None,
) -> Path | None:
    """Folder-pick Open flow used by File → Open and the Welcome dialog.

    Pops ``askdirectory``, classifies the picked folder via
    ``inspect_picked_folder``, resolves the ambiguous case via a
    Listbox picker, and surfaces a clear error for the empty case.

    Always returns a ``.ctkproj`` page file path (or ``None``) so the
    caller's downstream code — autosave swap, asset resolution, save
    paths — keeps working unchanged. For multi-page projects the
    active page from ``project.json`` is resolved here.
    """
    folder = filedialog.askdirectory(
        parent=parent,
        title="Open project (pick the project folder)",
        initialdir=initial_dir or "",
        mustexist=True,
    )
    if not folder:
        return None
    result = inspect_picked_folder(folder)
    if result.kind == "multi_page":
        if result.folder is None:
            return None
        try:
            meta = read_project_meta(result.folder)
        except Exception as exc:
            messagebox.showerror(
                "Open failed",
                f"project.json could not be read.\n\n{exc}",
                parent=parent,
            )
            return None
        entry = find_active_page_entry(meta)
        if entry is None or not entry.get("file"):
            messagebox.showerror(
                "Open failed",
                "project.json has no active page.",
                parent=parent,
            )
            return None
        return page_file_path(result.folder, entry["file"])
    if result.kind == "legacy_single":
        return result.page_path
    if result.kind == "ambiguous":
        if result.folder is None:
            return None
        picker = _AmbiguousProjectPicker(
            parent, result.folder, result.candidates,
        )
        parent.wait_window(picker)
        return picker.result
    messagebox.showerror(
        "Open failed",
        result.message or "This folder isn't a CTkMaker project.",
        parent=parent,
    )
    return None
