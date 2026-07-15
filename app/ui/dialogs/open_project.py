"""File → Open folder pick + classification + ambiguous resolve."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from app.core.project_folder import (
    find_active_page_entry,
    inspect_picked_folder,
    page_file_path,
    read_project_meta,
)
from app.ui.dialog_utils import safe_grab_set
from app.ui.dialogs._base import DarkDialog
from app.ui.dialogs._colors import (
    ACCENT,
    FG_DIM,
    ON_ACCENT,
    PANEL,
    dialog_scaling,
    flat_button,
    hero_header,
)
from app.ui.dialogs.message import show_error
from app.ui.system_fonts import ui_font


class _AmbiguousProjectPicker(DarkDialog):
    """Picker shown when a folder has >1 ``.ctkproj`` at its root and
    no ``project.json`` to disambiguate. Lists the candidates in a
    Listbox; ``self.result`` is the chosen ``Path`` or ``None``.
    """

    def __init__(self, parent, folder: Path, candidates: list[Path]) -> None:
        super().__init__(parent, fg_color=PANEL)
        self.title("Pick project file")
        self.result: Path | None = None
        self._candidates = candidates
        s = dialog_scaling(self)

        hero_header(self, "Pick project file", "info", s)
        tk.Label(
            self,
            text=(
                f"Several '.ctkproj' files were found in:\n{folder}\n\n"
                "Pick the one to open."
            ),
            bg=PANEL, fg=FG_DIM, font=ui_font(round(10 * s)),
            justify="left", wraplength=round(420 * s), anchor="w",
        ).pack(
            fill="x", padx=(round(31 * s), round(18 * s)),
            pady=(round(6 * s), round(10 * s)),
        )

        self._listbox = tk.Listbox(
            self,
            height=min(8, max(3, len(candidates))),
            width=50,
            bg="#2a2a2a", fg="#ededed",
            selectbackground=ACCENT, selectforeground=ON_ACCENT,
            relief="flat", bd=0, highlightthickness=0,
            font=ui_font(round(10 * s)),
        )
        for c in candidates:
            self._listbox.insert(tk.END, c.name)
        self._listbox.selection_set(0)
        self._listbox.pack(
            padx=round(31 * s), pady=(0, round(16 * s)), fill="x",
        )
        self._listbox.bind("<Double-Button-1>", lambda _e: self._on_ok())

        btn_row = tk.Frame(self, bg=PANEL)
        btn_row.pack(fill="x", padx=round(18 * s), pady=(0, round(16 * s)))
        flat_button(
            btn_row, "Open", "accent", self._on_ok, s,
        ).pack(side="right")
        flat_button(
            btn_row, "Cancel", "ghost", self._on_cancel, s,
        ).pack(side="right", padx=(0, round(8 * s)))
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self.invoke_focused_or(self._on_ok))

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
            show_error(
                "Open failed",
                f"project.json could not be read.\n\n{exc}",
                parent=parent,
            )
            return None
        entry = find_active_page_entry(meta)
        if entry is None or not entry.get("file"):
            show_error(
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
    show_error(
        "Open failed",
        result.message or "This folder isn't a CTkMaker project.",
        parent=parent,
    )
    return None
