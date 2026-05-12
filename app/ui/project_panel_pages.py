"""Page-operations sidecar for ``ProjectPanel``.

Owns every per-page action that mutates ``project.json`` and the
pages folder:

* ``on_new_page`` — prompt for a name, ``add_page`` in project,
  reseed metadata, auto-switch to the new page.
* ``on_context_switch_page`` — context-menu shortcut routes through
  the ``on_switch_page`` callback (same Ctrl+O dirty-prompt flow
  ``MainWindow._switch_to_page`` uses).
* ``on_context_duplicate_page`` — ``duplicate_page`` + reseed.
* ``on_context_rename_page`` — rename with active-page callback so
  MainWindow updates ``_current_path``.
* ``on_context_delete_page`` / ``_do_delete_page`` — last-page guard,
  switch-before-delete when the active page is being removed, full
  metadata reseed afterward.

Plus the small resolver helpers ``resolve_pages_folder_for_meta``
and ``selected_page_id`` that context-menu / show-context-menu
reach for to decide which entry to act on.
"""
from __future__ import annotations

from pathlib import Path
from tkinter import messagebox

from app.core.logger import log_error


class ProjectPanelPages:
    """Page CRUD + lookup helpers. See module docstring."""

    def __init__(self, panel) -> None:
        self.panel = panel

    def resolve_pages_folder_for_meta(self) -> Path | None:
        """Same as ``ProjectPanelTree.resolve_pages_folder`` but uses
        the current path_provider rather than a passed-in project
        file. Used by right-click handlers that don't already have a
        file path."""
        panel = self.panel
        path = panel.path_provider()
        if not path:
            return None
        return panel.tree.resolve_pages_folder(Path(path))

    def selected_page_id(self) -> str | None:
        """Look up the project.json page id for the currently
        right-clicked page row. Walks ``project.pages`` matching the
        filename — id<->file is stable across rename within a session.
        """
        panel = self.panel
        meta = panel._selected_meta()
        if meta is None:
            return None
        file_path, kind = meta
        if kind != "page":
            return None
        target = file_path.name
        for entry in panel.project.pages or []:
            if isinstance(entry, dict) and entry.get("file") == target:
                return entry.get("id")
        return None

    def on_new_page(self) -> None:
        """Prompt for a name and create a new empty page in the
        project. The new page is added after the current one in
        project.json; the user explicitly switches to it via a
        follow-up double-click (matches "Ctrl+O within project").
        """
        panel = self.panel
        if not panel.project.folder_path:
            return
        from tkinter import simpledialog
        name = simpledialog.askstring(
            "New page", "Page name:",
            initialvalue="New page",
            parent=panel.winfo_toplevel(),
        )
        if not name or not name.strip():
            return
        name = name.strip()
        from app.core.project_folder import (
            ProjectMetaError, add_page, seed_multi_page_meta_from_disk,
        )
        try:
            entry = add_page(panel.project.folder_path, name)
        except ProjectMetaError as exc:
            messagebox.showerror(
                "New page failed", str(exc),
                parent=panel.winfo_toplevel(),
            )
            return
        # Re-read project.json so project.pages reflects the new
        # entry — without this, selected_page_id wouldn't find the
        # page if the user immediately right-clicks it.
        if panel.path_provider():
            seed_multi_page_meta_from_disk(
                panel.project, panel.path_provider(),
            )
        panel.refresh()
        # Auto-switch to the new page so the user can start editing
        # it immediately. Same dirty-prompt + load flow as a manual
        # double-click. ``add_page`` returned the entry; the file
        # lives at <pages>/<entry.file>.
        if panel.on_switch_page is not None:
            from app.core.project_folder import pages_dir
            page_path = pages_dir(panel.project.folder_path) / entry["file"]
            panel.on_switch_page(str(page_path))

    def on_context_switch_page(self) -> None:
        panel = self.panel
        meta = panel._selected_meta()
        if meta is None or panel.on_switch_page is None:
            return
        file_path, kind = meta
        if kind != "page":
            return
        panel.on_switch_page(str(file_path))

    def on_context_duplicate_page(self) -> None:
        panel = self.panel
        page_id = self.selected_page_id()
        if not page_id or not panel.project.folder_path:
            return
        from app.core.project_folder import (
            ProjectMetaError, duplicate_page, seed_multi_page_meta_from_disk,
        )
        try:
            duplicate_page(panel.project.folder_path, page_id)
        except ProjectMetaError as exc:
            messagebox.showerror(
                "Duplicate failed", str(exc),
                parent=panel.winfo_toplevel(),
            )
            return
        if panel.path_provider():
            seed_multi_page_meta_from_disk(
                panel.project, panel.path_provider(),
            )
        panel.refresh()

    def on_context_rename_page(self) -> None:
        panel = self.panel
        page_id = self.selected_page_id()
        meta = panel._selected_meta()
        if not page_id or meta is None or not panel.project.folder_path:
            return
        # Pull current display name from project.pages so the prompt
        # pre-fills what the user sees in the tree, not the slugged
        # filename stem.
        current_name = next(
            (
                p.get("name", "") for p in (panel.project.pages or [])
                if isinstance(p, dict) and p.get("id") == page_id
            ),
            "",
        )
        from app.ui.dialogs import prompt_rename_page
        new_name = prompt_rename_page(
            panel.winfo_toplevel(), current_name,
        )
        if not new_name:
            return
        new_name = new_name.strip()
        if not new_name or new_name == current_name:
            return
        from app.core.project_folder import (
            ProjectMetaError, rename_page, seed_multi_page_meta_from_disk,
        )
        try:
            rename_page(panel.project.folder_path, page_id, new_name)
        except ProjectMetaError as exc:
            messagebox.showerror(
                "Rename failed", str(exc),
                parent=panel.winfo_toplevel(),
            )
            return
        # If the active page got renamed, the on-disk filename
        # changed too — notify MainWindow via the callback so it
        # can update ``_current_path`` and re-prime path-derived
        # state (autosave path, recent files, title bar).
        active_id = panel.project.active_page_id
        if active_id == page_id and panel.on_active_page_path_changed:
            from app.core.project_folder import (
                find_active_page_entry, page_file_path, read_project_meta,
            )
            try:
                meta_now = read_project_meta(panel.project.folder_path)
                entry = find_active_page_entry(meta_now)
                if entry is not None:
                    new_path = page_file_path(
                        panel.project.folder_path, entry["file"],
                    )
                    panel.on_active_page_path_changed(str(new_path))
            except Exception:
                log_error("rename_page active sync")
        if panel.path_provider():
            try:
                seed_multi_page_meta_from_disk(
                    panel.project, panel.path_provider(),
                )
            except Exception:
                log_error("rename_page reseed")
        panel.refresh()

    def on_context_delete_page(self) -> None:
        # Defer until the context menu's grab fully releases so the
        # askyesno dialog actually pops modal — without after_idle
        # the menu was still holding focus and the dialog flashed
        # behind / didn't surface for some users.
        self.panel.after_idle(self._do_delete_page)

    def _do_delete_page(self) -> None:
        panel = self.panel
        page_id = self.selected_page_id()
        if not page_id or not panel.project.folder_path:
            return
        # Block deleting the only page — a project must always have
        # one. Surface the rule explicitly so the user understands
        # why the operation no-ops, instead of silently failing.
        if len(panel.project.pages or []) <= 1:
            messagebox.showinfo(
                "Cannot delete page",
                "A project must have at least one page. Add another "
                "page first if you want to remove this one.",
                parent=panel.winfo_toplevel(),
            )
            return
        # Resolve display name for the confirmation prompt.
        display = next(
            (
                p.get("name", "") for p in (panel.project.pages or [])
                if isinstance(p, dict) and p.get("id") == page_id
            ),
            "",
        )
        if not messagebox.askyesno(
            "Delete page",
            f"Delete page '{display}'?\n\n"
            "The page file and its backups will be removed from disk. "
            "This can't be undone via Ctrl+Z.",
            parent=panel.winfo_toplevel(),
        ):
            return
        # If the deleted page is the currently-active one, we need
        # to switch to the new active first so the editor isn't
        # holding state for a file that's about to vanish. Resolve
        # the new active id, switch, THEN delete.
        from app.core.project_folder import (
            ProjectMetaError, delete_page,
            page_file_path, read_project_meta,
            seed_multi_page_meta_from_disk,
        )
        was_active = panel.project.active_page_id == page_id
        try:
            new_active_id = delete_page(
                panel.project.folder_path, page_id,
            )
        except ProjectMetaError as exc:
            messagebox.showerror(
                "Delete failed", str(exc),
                parent=panel.winfo_toplevel(),
            )
            return
        if new_active_id is None:
            return  # last-page guard fired inside delete_page
        if was_active and panel.on_switch_page is not None:
            try:
                meta_now = read_project_meta(panel.project.folder_path)
                entry = next(
                    (
                        p for p in meta_now.get("pages", [])
                        if isinstance(p, dict) and p.get("id") == new_active_id
                    ),
                    None,
                )
                if entry is not None:
                    target = page_file_path(
                        panel.project.folder_path, entry["file"],
                    )
                    # Skip the dirty prompt — the page being deleted
                    # took its dirty state with it. Just load the
                    # replacement directly.
                    panel.on_switch_page(str(target))
            except Exception:
                log_error("delete_page switch")
        if panel.path_provider():
            try:
                seed_multi_page_meta_from_disk(
                    panel.project, panel.path_provider(),
                )
            except Exception:
                log_error("delete_page reseed")
        panel.refresh()
