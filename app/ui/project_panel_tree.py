"""Tree population + info-panel + preview sidecar for ``ProjectPanel``.

Owns the read-only render side of the panel:

* ``populate_tree`` walks ``assets/`` recursively, classifies every
  file via ``_kind_for_path`` (with a special ``"page"`` re-class
  for ``.ctkproj`` files under ``assets/pages/``), and inserts
  rows into the ttk.Treeview with per-kind icons + active-page
  bold styling.
* ``resolve_pages_folder`` / ``resolve_active_page_file`` resolve
  the multi-page metadata path used both for tree styling and by
  the pages helper.
* ``ensure_kind_icons`` lazy-loads per-kind Lucide icons into
  ``panel._kind_icons`` once.
* ``on_folder_toggle`` / ``snapshot_open_paths`` persist the
  user's expand state so refresh doesn't collapse the tree.
* ``refresh_info_panel`` / ``show_image_preview`` / ``hide_preview``
  drive the metadata + thumbnail strip below the tree based on
  the current selection.

All UI elements (``_tree``, ``_iid_meta``, ``_info_var``,
``_preview_label``, ``_preview_thumb_ref``, ``_kind_icons``) live
on the panel so the helper just orchestrates the reads / writes.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path

from app.core.logger import log_error
from app.core.paths import ASSET_SUBDIRS, assets_dir
from app.ui.system_fonts import ui_font


class ProjectPanelTree:
    """Tree populate + info panel + preview helper.
    See module docstring.
    """

    def __init__(self, panel) -> None:
        self.panel = panel

    def refresh_info_panel(self) -> None:
        from app.ui.project_window import (
            _human_size, _read_font_family, _read_image_size,
        )
        panel = self.panel
        meta = panel._selected_meta()
        if meta is None:
            panel._info_var.set("")
            self.hide_preview()
            return
        file_path, kind = meta
        try:
            if kind == "folder":
                # Path.stat().st_size on a directory returns the
                # directory entry size on Windows (~4 KB block) — not
                # the recursive content total. Sum file sizes manually.
                size_bytes = sum(
                    p.stat().st_size for p in file_path.rglob("*")
                    if p.is_file()
                )
            else:
                size_bytes = file_path.stat().st_size
        except OSError:
            size_bytes = 0
        lines = [
            file_path.name,
            f"Size: {_human_size(size_bytes)}",
        ]
        if kind == "images":
            dims = _read_image_size(file_path)
            if dims is not None:
                lines.append(f"Dimensions: {dims[0]} × {dims[1]} px")
            self.show_image_preview(file_path)
        elif kind == "fonts":
            family = _read_font_family(file_path)
            if family:
                lines.append(f"Family: {family}")
            lines.append(f"Format: {file_path.suffix.lstrip('.').upper()}")
            self.hide_preview()
        elif kind == "sounds":
            lines.append(f"Format: {file_path.suffix.lstrip('.').upper()}")
            self.hide_preview()
        else:
            self.hide_preview()
        panel._info_var.set("\n".join(lines))

    def show_image_preview(self, file_path: Path) -> None:
        panel = self.panel
        try:
            from PIL import Image, ImageTk
            with Image.open(file_path) as img:
                preview = img.copy()
            preview.thumbnail((140, 140))
            tk_img = ImageTk.PhotoImage(preview)
        except Exception:
            self.hide_preview()
            return
        panel._preview_thumb_ref = tk_img
        panel._preview_label.configure(image=tk_img)
        try:
            panel._preview_label.pack(pady=(4, 6))
        except tk.TclError:
            pass

    def hide_preview(self) -> None:
        panel = self.panel
        try:
            panel._preview_label.pack_forget()
            panel._preview_label.configure(image="")
        except tk.TclError:
            pass
        panel._preview_thumb_ref = None

    def populate_tree(self, project_file: Path) -> None:
        from app.ui.project_window import _kind_for_path
        panel = self.panel
        # Snapshot expanded folders + selection so a refresh
        # (folder added / file moved) preserves the user's view.
        # Seed from live state; fall back to persisted state on first load.
        prev_open = self.snapshot_open_paths()
        _has_saved_state = bool(prev_open)
        if not prev_open:
            from app.core.settings import load_settings
            saved = load_settings().get("ui_assets_expanded_folders", [])
            prev_open = set(saved)
            _has_saved_state = bool(prev_open)
        prev_sel = panel._selected_meta()
        prev_sel_path = prev_sel[0] if prev_sel else None

        panel._tree.delete(*panel._tree.get_children())
        panel._iid_meta.clear()
        a_dir = assets_dir(project_file)
        if not a_dir.exists():
            return
        # Make sure the default skeleton exists for fresh projects so
        # the tree isn't empty on first open. Users can rename /
        # delete these later without breaking anything.
        for sub in ASSET_SUBDIRS:
            try:
                (a_dir / sub).mkdir(exist_ok=True)
            except OSError:
                log_error(f"ensure {sub} dir")

        # Bold tag for the active page — set up once, reused on every
        # populate so reload doesn't re-define the tag on every row.
        try:
            panel._tree.tag_configure(
                "active_page",
                font=ui_font(10, "bold"),
                foreground="#5bc0f8",
            )
        except tk.TclError:
            pass

        # Resolve the pages folder for this project so we can flag
        # ``.ctkproj`` rows nested under it as "page" kind. Empty in
        # legacy single-file projects (no project.json marker).
        pages_root = self.resolve_pages_folder(project_file)
        active_page_file = self.resolve_active_page_file()

        # Recursive populate. Folders first, then files within each
        # level so the tree reads as a normal file browser.
        new_sel_iid: str | None = None
        self.ensure_kind_icons()

        def walk(parent_iid: str, dir_path: Path) -> None:
            nonlocal new_sel_iid
            try:
                entries = list(dir_path.iterdir())
            except OSError:
                return
            folders = sorted(
                (e for e in entries if e.is_dir()),
                key=lambda p: p.name.lower(),
            )
            files = sorted(
                (
                    e for e in entries
                    if e.is_file()
                    # Hide builder-managed sidecars: .bak rotations,
                    # .autosave snapshots, .tmp atomic-write residue.
                    # User-relevant files are .ctkproj pages + assets.
                    and not e.name.endswith(".bak")
                    and not e.name.endswith(".autosave")
                    and not e.name.endswith(".tmp")
                ),
                key=lambda p: p.name.lower(),
            )
            for folder in folders:
                count = sum(1 for _ in folder.iterdir())
                # Leading spaces buy a small gap between icon and
                # text — ttk.Treeview has no native icon→text
                # padding knob, and adjusting the row image element
                # would touch the global Treeview style.
                label = f"  {folder.name}  ({count})"
                is_open = (
                    str(folder.resolve()) in prev_open
                    or (not _has_saved_state and parent_iid == "")
                )
                # Pages folder defaults to expanded so the user sees
                # their page list without an extra click — pages are
                # the primary navigation, not a buried subfolder.
                if (
                    pages_root is not None
                    and folder.resolve() == pages_root.resolve()
                ):
                    is_open = True
                fid = panel._tree.insert(
                    parent_iid, "end", text=label, open=is_open,
                    image=panel._kind_icons.get("folder", ""),
                )
                panel._iid_meta[fid] = (folder, "folder")
                if (
                    prev_sel_path is not None
                    and folder.resolve() == prev_sel_path.resolve()
                ):
                    new_sel_iid = fid
                walk(fid, folder)
            for f in files:
                kind = _kind_for_path(f)
                # Reclassify .ctkproj inside the pages folder as
                # "page" so the icon + context menu specialise.
                if (
                    pages_root is not None
                    and f.suffix.lower() == ".ctkproj"
                    and f.parent.resolve() == pages_root.resolve()
                ):
                    kind = "page"
                is_active = (
                    kind == "page"
                    and active_page_file is not None
                    and f.resolve() == active_page_file.resolve()
                )
                icon_key = "page_active" if is_active else kind
                tags = ("active_page",) if is_active else ()
                # "(active)" badge is the explicit cue; bold + cyan
                # are reinforcing visual cues.
                row_text = f"  {f.name}"
                if is_active:
                    row_text += "   (active)"
                iid = panel._tree.insert(
                    parent_iid, "end", text=row_text,
                    image=panel._kind_icons.get(
                        icon_key, panel._kind_icons.get("other", ""),
                    ),
                    tags=tags,
                )
                panel._iid_meta[iid] = (f, kind)
                if (
                    prev_sel_path is not None
                    and f.resolve() == prev_sel_path.resolve()
                ):
                    new_sel_iid = iid

        walk("", a_dir)
        if new_sel_iid is not None:
            try:
                panel._tree.selection_set(new_sel_iid)
                panel._tree.see(new_sel_iid)
            except tk.TclError:
                pass
        self.refresh_info_panel()

    def resolve_pages_folder(self, project_file: Path) -> Path | None:
        """Return ``<root>/assets/pages/`` for multi-page projects,
        ``None`` for legacy single-file. Used to flag rows in the
        tree as page-kind so the icon + context menu specialise.
        """
        from app.core.project_folder import find_project_root, pages_dir
        root = find_project_root(project_file)
        if root is None:
            return None
        pdir = pages_dir(root)
        return pdir if pdir.is_dir() else None

    def resolve_active_page_file(self) -> Path | None:
        """Absolute path to the current page's .ctkproj, used by the
        tree populate to bold the active row. Falls back to the
        ``path_provider`` value (which is already the active page)
        so the bold logic also works during the moment between
        in-memory change and project.json sync.
        """
        try:
            path = self.panel.path_provider()
        except Exception:
            path = None
        return Path(path) if path else None

    def ensure_kind_icons(self) -> None:
        """Lazy-load Lucide icons for the row leading column. Caches
        on ``panel._kind_icons`` keyed by row kind so a re-populate
        doesn't reload the PNGs from disk.
        """
        panel = self.panel
        if panel._kind_icons:
            return
        from app.ui.icons import load_tk_icon
        kind_to_icon_name = {
            "folder": "folder",
            "images": "image",
            "fonts": "type",
            "sounds": "music",
            "text": "file-text",
            "code": "file-code",
            "other": "file",
            # Page (.ctkproj inside assets/pages/) — same icon as
            # the canvas/window concept so it reads "this is a UI
            # design", distinct from generic files.
            "page": "layout-template",
            "page_active": "layout-template",
        }
        for kind, icon_name in kind_to_icon_name.items():
            try:
                color = "#5bc0f8" if kind == "page_active" else "#cccccc"
                img = load_tk_icon(icon_name, size=14, color=color)
            except Exception:
                img = None
            if img is not None:
                panel._kind_icons[kind] = img

    def on_folder_toggle(self, _event=None) -> None:
        from app.core.settings import save_setting
        save_setting(
            "ui_assets_expanded_folders",
            list(self.snapshot_open_paths()),
        )

    def snapshot_open_paths(self) -> set[str]:
        """Capture every currently-expanded folder iid → resolved
        path so a re-populate keeps user's expand state. Without
        this, every refresh would collapse the whole tree.
        """
        panel = self.panel
        opened: set[str] = set()
        for iid, (path, kind) in panel._iid_meta.items():
            if kind != "folder":
                continue
            try:
                if panel._tree.item(iid, "open"):
                    opened.add(str(path.resolve()))
            except tk.TclError:
                continue
        return opened
