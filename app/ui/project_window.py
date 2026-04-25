"""Project inspector — floating panel that shows the current project's
folder layout and the assets that live inside it.

``ProjectPanel`` is the embeddable widget; ``ProjectWindow`` is the
floating-toplevel wrapper opened by F10 / View menu.

Phase B-1 scope (this file): browse the folder, add image assets via
file picker, reveal the folder in Explorer. Drag-to-canvas + Image
widget integration land in Phase B-2.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from app.core.logger import log_error
from app.core.paths import (
    ASSET_SUBDIRS, assets_dir, ensure_project_folder,
)

if TYPE_CHECKING:
    from app.core.project import Project

BG = "#1e1e1e"
PANEL_BG = "#252526"
HEADER_BG = "#2d2d30"
HEADER_FG = "#cccccc"
DIM_FG = "#888888"
ACCENT = "#5bc0f8"
TREE_BG = "#1e1e1e"
TREE_FG = "#cccccc"
TREE_SEL_BG = "#094771"

DIALOG_W = 320
DIALOG_H = 480
TREE_ROW_HEIGHT = 22

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico"}


class ProjectPanel(ctk.CTkFrame):
    """Embeddable Project panel. The MainWindow owns one of these
    inside ``ProjectWindow`` (floating). A future Phase C will dock
    this into the right sidebar as a 4th tab.
    """

    def __init__(
        self,
        parent,
        project: "Project",
        path_provider: Callable[[], str | None],
    ):
        super().__init__(
            parent, fg_color=PANEL_BG, corner_radius=0, border_width=0,
        )
        self.project = project
        self.path_provider = path_provider

        self._name_var = tk.StringVar()
        self._path_var = tk.StringVar()

        self._build_header()
        self._build_tree()
        self._build_footer()

        # Refresh whenever project name / save target / dirty state
        # changes — keeps the header text current after Save As, New
        # Project, etc.
        bus = project.event_bus
        for evt in ("project_renamed", "dirty_changed"):
            bus.subscribe(evt, lambda *_a, **_k: self.refresh())
        self.after(0, self.refresh)

    # ------- public API -------

    def refresh(self) -> None:
        # Event-bus subscribers from a closed Project window can fire
        # after their panel has been destroyed — the lambdas captured
        # ``self`` and live on past the panel's lifetime. Guard with a
        # widget-existence check so a stale dirty_changed publish
        # doesn't surface a Tcl "invalid command name" traceback.
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        path = self.path_provider()
        if path:
            p = Path(path)
            self._name_var.set(p.stem)
            self._path_var.set(str(p.parent))
            self._populate_tree(p)
            self._set_buttons_enabled(True)
        else:
            self._name_var.set("(untitled)")
            self._path_var.set(
                "Save the project first to enable assets.",
            )
            try:
                self._tree.delete(*self._tree.get_children())
            except tk.TclError:
                pass
            self._set_buttons_enabled(False)

    # ------- internal layout -------

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=0)
        header.pack(fill="x")
        ctk.CTkLabel(
            header, text="Project",
            font=("Segoe UI", 11, "bold"),
            text_color=HEADER_FG, anchor="w",
        ).pack(fill="x", padx=10, pady=(8, 2))

        body = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0)
        body.pack(fill="x", padx=10, pady=(6, 4))

        # Name line — bold project name
        ctk.CTkLabel(
            body, textvariable=self._name_var,
            font=("Segoe UI", 12, "bold"),
            text_color=HEADER_FG, anchor="w", justify="left",
        ).pack(fill="x")
        # Path line — wraps so long Documents paths stay readable
        ctk.CTkLabel(
            body, textvariable=self._path_var,
            font=("Segoe UI", 9),
            text_color=DIM_FG, anchor="w", justify="left",
            wraplength=DIALOG_W - 30,
        ).pack(fill="x", pady=(2, 0))

        ctk.CTkButton(
            body, text="Reveal in Explorer", height=24,
            font=("Segoe UI", 10), corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_reveal,
        ).pack(fill="x", pady=(8, 0))
        self._reveal_btn = body.winfo_children()[-1]

    def _build_tree(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0)
        wrap.pack(fill="both", expand=True, padx=10, pady=(8, 4))

        ctk.CTkLabel(
            wrap, text="Assets",
            font=("Segoe UI", 11, "bold"),
            text_color=HEADER_FG, anchor="w",
        ).pack(fill="x", pady=(0, 4))

        style = ttk.Style(wrap)
        style_name = "Project.Treeview"
        style.configure(
            style_name,
            background=TREE_BG, fieldbackground=TREE_BG,
            foreground=TREE_FG, rowheight=TREE_ROW_HEIGHT,
            borderwidth=0, font=("Segoe UI", 10),
        )
        style.map(
            style_name,
            background=[("selected", TREE_SEL_BG)],
            foreground=[("selected", "#ffffff")],
        )
        self._tree = ttk.Treeview(
            wrap, columns=(), show="tree", style=style_name,
            selectmode="browse",
        )
        self._tree.pack(fill="both", expand=True)

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0)
        footer.pack(fill="x", padx=10, pady=(4, 10))
        self._add_image_btn = ctk.CTkButton(
            footer, text="+ Add Image...", height=28,
            font=("Segoe UI", 10), corner_radius=4,
            command=self._on_add_image,
        )
        self._add_image_btn.pack(fill="x")

    # ------- actions -------

    def _on_reveal(self) -> None:
        path = self.path_provider()
        if not path:
            return
        folder = Path(path).parent
        if not folder.exists():
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(folder))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError:
            log_error("project reveal in explorer")

    def _on_add_image(self) -> None:
        path = self.path_provider()
        if not path:
            return
        src = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="Add image to project",
            filetypes=[
                ("Images",
                 "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.ico"),
                ("All files", "*.*"),
            ],
        )
        if not src:
            return
        src_path = Path(src)
        if src_path.suffix.lower() not in IMAGE_EXTS:
            messagebox.showwarning(
                "Not an image",
                f"{src_path.name} doesn't look like an image file.",
                parent=self.winfo_toplevel(),
            )
            return
        # Make sure the folder skeleton exists — Add Image is the
        # most likely first asset-add step on a freshly-saved project.
        project_folder = Path(path).parent
        ensure_project_folder(project_folder)
        target_dir = assets_dir(path) / "images"

        try:
            sha = _sha256(src_path)
        except OSError:
            log_error("add image sha")
            messagebox.showerror(
                "Add image failed",
                "Couldn't read the image file.",
                parent=self.winfo_toplevel(),
            )
            return

        # Dedupe by content hash. If a same-content file already
        # lives in assets/images/, reuse it instead of writing a
        # second copy with a different name.
        existing = _find_by_sha(target_dir, sha)
        if existing is None:
            dst = _unique_dest(target_dir, src_path.name)
            try:
                shutil.copy2(src_path, dst)
            except OSError:
                log_error("add image copy")
                messagebox.showerror(
                    "Add image failed",
                    f"Couldn't copy:\n{src_path}\n→\n{dst}",
                    parent=self.winfo_toplevel(),
                )
                return
        self.refresh()

    # ------- tree population -------

    def _populate_tree(self, project_file: Path) -> None:
        self._tree.delete(*self._tree.get_children())
        a_dir = assets_dir(project_file)
        if not a_dir.exists():
            return
        for sub in ASSET_SUBDIRS:
            folder = a_dir / sub
            if not folder.exists():
                folder.mkdir(parents=True, exist_ok=True)
            files = sorted(
                p for p in folder.iterdir() if p.is_file()
            )
            label = f"{sub}/  ({len(files)})"
            parent_id = self._tree.insert("", "end", text=label, open=True)
            for f in files:
                self._tree.insert(parent_id, "end", text=f.name)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for btn in (self._add_image_btn, self._reveal_btn):
            try:
                btn.configure(state=state)
            except tk.TclError:
                pass


# ---------------------------------------------------------------------------
# Floating window wrapper
# ---------------------------------------------------------------------------

class ProjectWindow(ctk.CTkToplevel):
    """Floating wrapper around ``ProjectPanel`` (opened by F10)."""

    def __init__(
        self,
        parent,
        project: "Project",
        path_provider: Callable[[], str | None],
        on_close: Callable[[], None] | None = None,
    ):
        super().__init__(parent)
        self.title("Project")
        self.configure(fg_color=BG)
        self.geometry(f"{DIALOG_W}x{DIALOG_H}")
        self.minsize(260, 320)
        try:
            self.transient(parent)
        except tk.TclError:
            pass

        self._on_close_callback = on_close
        self.panel = ProjectPanel(self, project, path_provider)
        self.panel.pack(fill="both", expand=True, padx=6, pady=6)
        self._place_relative_to(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _place_relative_to(self, parent) -> None:
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            x = px + 60
            y = py + 80
            self.geometry(f"{DIALOG_W}x{DIALOG_H}+{x}+{y}")
        except tk.TclError:
            pass

    def _on_close(self) -> None:
        if self._on_close_callback is not None:
            try:
                self._on_close_callback()
            except Exception:
                pass
        self.destroy()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_by_sha(folder: Path, sha: str) -> Path | None:
    if not folder.exists():
        return None
    for f in folder.iterdir():
        if not f.is_file():
            continue
        try:
            if _sha256(f) == sha:
                return f
        except OSError:
            continue
    return None


def _unique_dest(folder: Path, name: str) -> Path:
    """Avoid filename collision — append `_2`, `_3`, ... before suffix."""
    folder.mkdir(parents=True, exist_ok=True)
    candidate = folder / name
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    n = 2
    while True:
        candidate = folder / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1
