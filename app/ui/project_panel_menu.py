"""Right-click context menu sidecar for ``ProjectPanel``.

Owns the entire tree right-click flow:

* ``on_tree_right_click`` selects the row under the cursor (or
  clears the selection on empty-area clicks so + Folder lands at
  assets root), refreshes the info panel, then opens the menu.
* ``show_context_menu`` builds a kind-specific menu — folder rows
  get New Subfolder + Add cascade + Rename + Delete; page rows get
  Switch / Duplicate / Rename / Delete; file rows get Open / Open
  in Explorer / Reimport / Rename / Remove. Empty-area menu shows
  New Folder + Add cascade + "Open assets folder in Explorer".

Action handlers exposed by the menu's command targets:

* ``on_context_open`` / ``on_context_reveal`` / ``on_context_remove``
  / ``on_context_reimport`` — single-row actions.
* ``on_reveal_assets_root`` — open ``assets/`` in the OS file manager.

Plus the OS-level file helpers ``reveal_file`` + ``open_with_os``
(default app or text-editor fallback for ``.md`` / ``.py`` / ...).

Cross-helper calls go through panel pass-throughs
(``panel._on_new_folder``, ``panel._on_new_page`` etc.) so this
helper stays decoupled from the other sidecars' internals.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path

from app.core.logger import log_error
from app.core.paths import assets_dir


_TEXT_LIKE_EXTS = {
    ".md", ".txt", ".py", ".json", ".yaml", ".yml",
    ".toml", ".cfg", ".ini", ".log",
}


class ProjectPanelMenu:
    """Right-click menu + file/folder OS helpers. See module docstring."""

    def __init__(self, panel) -> None:
        self.panel = panel

    def on_tree_right_click(self, event) -> None:
        panel = self.panel
        iid = panel._tree.identify_row(event.y)
        if iid:
            try:
                panel._tree.selection_set(iid)
            except tk.TclError:
                pass
        else:
            # Empty-area right-click clears the previous selection
            # so + Folder / Add ▶ entries from the empty-area menu
            # actually land at the assets root, not inside whatever
            # folder was selected before.
            try:
                panel._tree.selection_set([])
            except tk.TclError:
                pass
        panel.tree.refresh_info_panel()
        # Empty-area right-click pops the same menu but with file-only
        # entries disabled — the user can still create a folder/text
        # file at the assets root.
        self.show_context_menu(event.x_root, event.y_root, iid or "")

    def show_context_menu(
        self, x_root: int, y_root: int, iid: str,
    ) -> None:
        from app.ui.project_window import HEADER_FG
        from app.ui.system_fonts import ui_font
        panel = self.panel
        if panel._context_menu is not None:
            try:
                panel._context_menu.destroy()
            except tk.TclError:
                pass
        menu = tk.Menu(
            panel, tearoff=0,
            bg="#2d2d30", fg=HEADER_FG,
            activebackground="#094771", activeforeground="#ffffff",
            relief="flat", bd=0, font=ui_font(10),
        )
        meta = panel._iid_meta.get(iid)
        if meta is None:
            # Right-clicked on the empty area below all rows.
            # Compact: New Folder + an "Add ▶" cascade for the
            # four content-import actions, then Open in Explorer.
            panel._menu_command(
                menu, "New Folder...", "folder", panel._on_new_folder,
            )
            panel._menu_cascade(
                menu, "Add", "square-plus",
                panel._build_add_submenu(menu),
            )
            menu.add_separator()
            panel._menu_command(
                menu, "Open assets folder in Explorer",
                "folder-open", self.on_reveal_assets_root,
            )
        else:
            folder_path, kind = meta
            if kind == "folder":
                pages_root = panel._resolve_pages_folder_for_meta()
                is_pages_folder = (
                    pages_root is not None
                    and folder_path.resolve() == pages_root.resolve()
                )
                if is_pages_folder:
                    # Pages folder — only New Page makes sense here.
                    # Generic "New Subfolder" / "Add ▶" would create
                    # asset-files inside a directory the schema
                    # expects to hold .ctkproj pages only.
                    panel._menu_command(
                        menu, "New Page...", "layout-template",
                        panel._on_new_page,
                    )
                    menu.add_separator()
                    panel._menu_command(
                        menu, "Open in Explorer", "folder-open",
                        self.on_context_reveal,
                    )
                else:
                    # Folder right-click — same compact shape:
                    # New Subfolder + Add here ▶ + actions.
                    panel._menu_command(
                        menu, "New Subfolder...", "folder",
                        panel._on_new_folder,
                    )
                    panel._menu_cascade(
                        menu, "Add here", "square-plus",
                        panel._build_add_submenu(menu),
                    )
                    menu.add_separator()
                    panel._menu_command(
                        menu, "Open in Explorer", "folder-open",
                        self.on_context_reveal,
                    )
                    panel._menu_command(
                        menu, "Rename...", "pencil", panel._on_rename,
                    )
                    panel._menu_command(
                        menu, "Delete folder...", "trash-2",
                        panel._on_delete_folder,
                    )
            elif kind == "page":
                # Page right-click — switch / duplicate / rename /
                # delete. Filesystem-level operations (Open with OS,
                # Reimport) don't apply to pages — they're routed
                # through the page CRUD helpers so project.json
                # stays in sync with the disk.
                panel._menu_command(
                    menu, "Switch to this page", "external-link",
                    panel._on_context_switch_page,
                )
                panel._menu_command(
                    menu, "Duplicate", "copy",
                    panel._on_context_duplicate_page,
                )
                panel._menu_command(
                    menu, "Rename...", "pencil",
                    panel._on_context_rename_page,
                )
                menu.add_separator()
                panel._menu_command(
                    menu, "Open in Explorer", "folder-open",
                    self.on_context_reveal,
                )
                panel._menu_command(
                    menu, "Delete page...", "trash-2",
                    panel._on_context_delete_page,
                )
            else:
                panel._menu_command(
                    menu, "Open", "external-link", self.on_context_open,
                )
                panel._menu_command(
                    menu, "Open in Explorer", "folder-open",
                    self.on_context_reveal,
                )
                # Reimport is hidden for fonts because tkextrafont
                # caches the registration in the running Tk
                # interpreter — replacing the file on disk doesn't
                # reload the glyphs until a relaunch. Users can drop
                # a new font through the + menu instead.
                if kind != "fonts":
                    panel._menu_command(
                        menu, "Reimport...", "rotate-cw",
                        self.on_context_reimport,
                    )
                menu.add_separator()
                panel._menu_command(
                    menu, "Rename...", "pencil", panel._on_rename,
                )
                panel._menu_command(
                    menu, "Remove from project...", "trash-2",
                    self.on_context_remove,
                )
        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()
        panel._context_menu = menu

    def on_context_open(self) -> None:
        meta = self.panel._selected_meta()
        if meta is None:
            return
        self.open_with_os(meta[0])

    def on_context_reveal(self) -> None:
        meta = self.panel._selected_meta()
        if meta is None:
            return
        self.reveal_file(meta[0])

    def on_reveal_assets_root(self) -> None:
        """Empty-area menu hook → open the project's ``assets/``
        folder in the OS file manager. Useful when the user wants
        to drop in files via Explorer drag-drop or inspect the
        on-disk layout the tree is mirroring.
        """
        path = self.panel.path_provider()
        if not path:
            return
        a_dir = assets_dir(path)
        if not a_dir.exists():
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(a_dir))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(a_dir)])
            else:
                subprocess.Popen(["xdg-open", str(a_dir)])
        except OSError:
            log_error("open assets root")

    def on_context_remove(self) -> None:
        meta = self.panel._selected_meta()
        if meta is None:
            return
        file_path, kind = meta
        self.panel.files.remove_asset(file_path, kind)

    def on_context_reimport(self) -> None:
        meta = self.panel._selected_meta()
        if meta is None:
            return
        file_path, kind = meta
        self.panel.files.reimport_asset(file_path, kind)

    def reveal_file(self, file_path: Path) -> None:
        if not file_path.exists():
            return
        try:
            if sys.platform == "win32":
                # ``/select,`` opens Explorer with the file highlighted
                # rather than the parent folder generic-open.
                subprocess.Popen(
                    ["explorer", "/select,", str(file_path)],
                )
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(file_path)])
            else:
                subprocess.Popen(["xdg-open", str(file_path.parent)])
        except OSError:
            log_error("reveal asset")

    def open_with_os(self, file_path: Path) -> None:
        """Hand a file off to the OS default application — image
        viewer for .png, default font preview for .ttf, the user's
        preferred Markdown editor for .md, etc.

        Fallback chain when the default association doesn't open:
        1. text-like extensions (.md / .py / .txt / ...) → Notepad
           on Windows, TextEdit on macOS, xdg-open on Linux. Most
           users without an .md association still have a text
           editor that handles the file fine.
        2. otherwise: reveal in Explorer so the user sees the file.
        """
        panel = self.panel
        if not file_path.exists():
            return
        # ``.py`` opens through the user's configured editor
        # (Settings → Editor tab) so free-form scripts land in the
        # same editor F7 uses for behavior files. ``launch_editor``
        # falls back to the Auto chain (VS Code → Notepad++ → IDLE),
        # so something runnable always wins out — no need for the
        # ``.py``-specific OS branch below.
        if file_path.suffix.lower() == ".py":
            from app.core.settings import load_settings
            from app.io.scripts import (
                launch_editor,
                resolve_project_root_for_editor,
            )
            editor_command = load_settings().get("editor_command")
            if launch_editor(
                file_path,
                editor_command=editor_command,
                project_root=resolve_project_root_for_editor(panel.project),
            ):
                return
        try:
            if sys.platform == "win32":
                # Everything routes through ``explorer.exe``, which
                # delegates to Windows' normal double-click path.
                # Handles UWP / Microsoft Store associations cleanly.
                subprocess.Popen(
                    ["explorer.exe", str(file_path)],
                )
                return
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(file_path)])
                return
            subprocess.Popen(["xdg-open", str(file_path)])
            return
        except (OSError, FileNotFoundError):
            log_error("open with os default")

        # Default-app handler refused — usually means no
        # association. Try a text-editor fallback for text-like
        # extensions; everything else lands in the file manager.
        if file_path.suffix.lower() in _TEXT_LIKE_EXTS:
            try:
                if sys.platform == "win32":
                    subprocess.Popen(["notepad.exe", str(file_path)])
                    return
                if sys.platform == "darwin":
                    subprocess.Popen(
                        ["open", "-a", "TextEdit", str(file_path)],
                    )
                    return
                # Linux xdg-open already attempted; keep falling
                # through to the file-manager reveal.
            except (OSError, FileNotFoundError):
                log_error("open with notepad fallback")
        self.reveal_file(file_path)
