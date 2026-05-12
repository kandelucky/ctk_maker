"""Document lifecycle handlers extracted from ``main_window.py``.

Two groupings:

* **Document operations** — rename / form-settings / move up-down /
  close project / minimise + restore / add dialog / remove document /
  F7 edit behavior file.
* **Behavior-file sync** — event-bus subscribers that materialise,
  recycle, or rename the per-window ``assets/scripts/<page>/<window>.py``
  in response to document add / remove / rename. Silent no-ops for
  unsaved projects (no scripts folder yet); ``_set_current_path``
  triggers the one-shot ``_ensure_behavior_files_for_all_docs``
  catchup on first save.

``_auto_save_after_doc_change`` is the shared "structural change →
persist .ctkproj" helper. Without it, adding or removing a dialog
left the file on disk while the project's in-memory list moved on —
orphan files at next launch.
"""
from __future__ import annotations

from tkinter import messagebox

from app.core.autosave import clear_autosave
from app.core.logger import log_error
from app.io.project_saver import save_project
from app.ui._main_window_host import _MainWindowHost


class DocumentsMixin(_MainWindowHost):
    """Document add / remove / rename / move + behavior-file sync.
    See module docstring.
    """

    # ------------------------------------------------------------------
    # Rename + form settings + move up/down
    # ------------------------------------------------------------------
    def _on_rename_current_doc(self) -> None:
        from app.ui.dialogs import RenameDialog
        doc = self.project.active_document
        dialog = RenameDialog(self, doc.name)
        if dialog.result and dialog.result != doc.name:
            doc.name = dialog.result
            self.project.event_bus.publish("project_renamed", self.project.name)
            self._on_project_modified()

    def _on_form_settings(self) -> None:
        from app.core.project import WINDOW_ID
        self.project.select_widget(WINDOW_ID)

    def _on_move_doc_up(self) -> None:
        docs = self.project.documents
        doc = self.project.active_document
        idx = docs.index(doc)
        if idx <= 1:
            return
        docs[idx], docs[idx - 1] = docs[idx - 1], docs[idx]
        self.project.event_bus.publish("project_renamed", self.project.name)
        self._on_project_modified()

    def _on_move_doc_down(self) -> None:
        docs = self.project.documents
        doc = self.project.active_document
        idx = docs.index(doc)
        if idx == 0 or idx >= len(docs) - 1:
            return
        docs[idx], docs[idx + 1] = docs[idx + 1], docs[idx]
        self.project.event_bus.publish("project_renamed", self.project.name)
        self._on_project_modified()

    def _on_close_project(self) -> None:
        self._on_new()

    # ------------------------------------------------------------------
    # Window > Visibility submenu
    # ------------------------------------------------------------------
    def _on_minimize_active_doc(self) -> None:
        active = self.project.active_document
        if active is not None:
            self.project.set_document_collapsed(active.id, True)

    def _on_minimize_all_docs(self) -> None:
        # Walk via id snapshot — set_document_collapsed flips the
        # active id mid-loop and re-iterating ``documents`` directly
        # would skip whichever doc lands on the active slot last.
        for doc_id in [d.id for d in self.project.documents]:
            self.project.set_document_collapsed(doc_id, True)

    def _on_restore_all_docs(self) -> None:
        for doc_id in [d.id for d in self.project.documents]:
            self.project.set_document_collapsed(doc_id, False)

    # ------------------------------------------------------------------
    # Form menu — add / remove dialogs (multi-document projects)
    # ------------------------------------------------------------------
    def _on_add_dialog(self) -> None:
        from app.ui.dialogs import AddDialogSizeDialog
        existing = {doc.name for doc in self.project.documents}
        base_name = "Dialog"
        default_name = base_name
        n = 1
        while default_name in existing:
            n += 1
            default_name = f"{base_name} {n}"
        # Seed defaults from the main window (first document) so
        # "Same as Main" preset resolves to the right numbers.
        main_doc = self.project.documents[0] if self.project.documents else None
        main_w = main_doc.width if main_doc else 800
        main_h = main_doc.height if main_doc else 600
        dialog = AddDialogSizeDialog(
            self,
            default_name=default_name,
            main_w=main_w,
            main_h=main_h,
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        name, w, h = dialog.result
        self._add_document(name, is_toplevel=True, width=w, height=h)

    def _add_document(
        self,
        name: str,
        is_toplevel: bool,
        width: int = 400,
        height: int = 300,
    ) -> None:
        from app.core.commands import AddDocumentCommand
        from app.core.document import Document
        max_right = 0
        for doc in self.project.documents:
            right = doc.canvas_x + doc.width
            if right > max_right:
                max_right = right
        new_doc = Document(
            name=name,
            width=width,
            height=height,
            canvas_x=max_right + 120,
            canvas_y=0,
            is_toplevel=is_toplevel,
        )
        self.project.documents.append(new_doc)
        self.project.set_active_document(new_doc.id)
        self._on_project_modified()
        # Phase 2 — fire ``document_added`` so the eager behavior-file
        # subscriber materialises the per-window ``.py`` immediately.
        # Without this, "Add Dialog" left the scripts folder empty
        # until the next save and "Add Action" hit a missing file.
        # ``_restore_document`` (undo path) publishes the same event.
        self.project.event_bus.publish("document_added", new_doc.id)
        self.project.event_bus.publish(
            "project_renamed", self.project.name,
        )
        self.project.history.push(
            AddDocumentCommand(
                new_doc.to_dict(),
                len(self.project.documents) - 1,
            ),
        )
        # Scroll the canvas onto the new dialog — stacked to the right
        # of the last doc, the new form can easily land past the
        # current viewport (especially on zoom > 100 %). Ran after the
        # event bus has fired so the renderer has redrawn + updated
        # scrollregion before we sample it.
        self.after_idle(
            lambda did=new_doc.id: self.workspace.focus_document(did),
        )

    def _on_remove_current_document(self) -> None:
        doc = self.project.active_document
        if not doc.is_toplevel:
            messagebox.showinfo(
                "Remove document",
                "The main window can't be removed — only dialogs can.",
                parent=self,
            )
            return
        from app.ui.handler_delete_dialogs import run_window_delete_flow
        if not run_window_delete_flow(self, self.project, doc):
            return
        from app.core.commands import DeleteDocumentCommand
        snapshot = doc.to_dict()
        doc_id = doc.id
        doc_name = doc.name
        index = self.project.documents.index(doc)
        for node in list(doc.root_widgets):
            self.project.remove_widget(node.id)
        self.project.documents.remove(doc)
        self.project.active_document_id = self.project.documents[0].id
        self.project.event_bus.publish(
            "active_document_changed",
            self.project.active_document_id,
        )
        self.project.event_bus.publish(
            "project_renamed", self.project.name,
        )
        self._on_project_modified()
        # Phase 2 Step 3 — drives the asset-panel refresh + the
        # auto-save subscriber. Mirrors the chrome ✕ path so both
        # entry points stay in sync.
        self.project.event_bus.publish(
            "document_removed", doc_id, doc_name,
        )
        self.project.history.push(
            DeleteDocumentCommand(snapshot, index),
        )

    # ------------------------------------------------------------------
    # F7 — edit behavior file
    # ------------------------------------------------------------------
    def _on_f7_edit_behavior_file(self) -> None:
        """F7 / Edit menu → open the active document's behavior
        ``.py`` in the user's editor (Phase 2 Step 3). Toast for
        unsaved projects since the file lives under
        ``<project>/assets/scripts/`` and unsaved projects don't
        have that folder yet.
        """
        if not getattr(self.project, "path", None):
            messagebox.showinfo(
                "Save first",
                "Save the project before opening the behavior file — "
                "the file lives in assets/scripts/ in the project "
                "folder.",
                parent=self,
            )
            return
        doc = self.project.active_document
        if doc is None:
            return
        try:
            from app.core.settings import load_settings
            from app.io.scripts import (
                behavior_file_path,
                launch_editor,
                load_or_create_behavior_file,
                resolve_project_root_for_editor,
            )
            file_path = load_or_create_behavior_file(
                self.project.path, doc,
            )
            if file_path is None:
                file_path = behavior_file_path(self.project.path, doc)
            if file_path is None or not file_path.exists():
                return
            editor_command = load_settings().get("editor_command")
            launch_editor(
                file_path,
                editor_command=editor_command,
                project_root=resolve_project_root_for_editor(self.project),
            )
        except OSError:
            log_error("F7 edit behavior file")

    # ------------------------------------------------------------------
    # Behavior-file event-bus subscribers
    # ------------------------------------------------------------------
    def _on_document_added_for_behavior(self, doc_id: str) -> None:
        """Subscriber for ``document_added`` — materialises the
        per-window behavior file in ``assets/scripts/<page>/<window>.py``
        eagerly (Decision #12). Silently no-ops for unsaved projects;
        ``_set_current_path`` runs the catchup loop on first save.

        Also auto-saves the project so the on-disk window list keeps
        up with the active scripts folder. Without that, creating a
        dialog and exiting without manual save left the new ``.py``
        on disk while the .ctkproj still listed the old documents —
        an orphan file with no window referencing it.
        """
        if not getattr(self.project, "path", None):
            return
        doc = self.project.get_document(doc_id)
        if doc is None:
            return
        try:
            from app.io.scripts import load_or_create_behavior_file
            load_or_create_behavior_file(self.project.path, doc)
        except OSError:
            log_error("eager behavior file create")
        self._auto_save_after_doc_change()

    def _on_document_removed_for_behavior(
        self, doc_id: str, doc_name: str,
    ) -> None:
        """Recycle the leftover behavior file when a document is
        removed via undo of "Add Dialog" or any other code path that
        goes through ``_remove_document_by_id`` without first
        running ``WindowDeleteDialog`` (the explicit delete path
        already moved the file). Auto-saves after so the .ctkproj
        catches up to the in-memory state.

        Uses ``send2trash`` so the user keeps OS-level recovery if
        they regret an undo. The ``recycle_behavior_file`` helper
        no-ops when the file is already gone (the dialog path).
        """
        if not getattr(self.project, "path", None):
            return
        try:
            from app.io.scripts import recycle_behavior_file
            recycle_behavior_file(self.project.path, doc_name)
        except OSError:
            log_error("recycle behavior file (doc removed)")
        self._auto_save_after_doc_change()

    def _auto_save_after_doc_change(self) -> None:
        """Persist the .ctkproj after a structural document change
        (add / remove). Skipped for unsaved projects — the user has
        to choose a save path first via Save As. Save errors log
        but don't bubble up; the user still has manual save as a
        recovery path.
        """
        if not self._current_path:
            return
        try:
            save_project(self.project, self._current_path)
            clear_autosave(self._current_path)
            self._clear_dirty()
        except OSError:
            log_error("auto-save after document change")

    def _on_document_renamed_for_behavior(
        self, doc_id: str, old_name: str, new_name: str,
    ) -> None:
        """Rename ``<page>/<old_slug>.py`` → ``<new_slug>.py`` and
        rewrite the class header inside (Decision B=A). Silent
        no-op for unsaved projects, missing source files, or slug
        collisions in the destination — the user keeps the old
        file in place rather than facing a clobber.
        """
        if not getattr(self.project, "path", None):
            return
        try:
            from app.io.scripts import rename_behavior_file_and_class
            rename_behavior_file_and_class(
                self.project.path, old_name, new_name,
            )
        except OSError:
            log_error("rename behavior file")

    def _ensure_behavior_files_for_all_docs(self) -> None:
        """One-shot catchup: walk every Document and ensure its
        ``.py`` exists. Runs after open / save / save-as so a project
        loaded from disk (or freshly given a path) lands with all
        behavior files materialised even though no
        ``document_added`` event fired for them.
        """
        if not getattr(self.project, "path", None):
            return
        try:
            from app.io.scripts import load_or_create_behavior_file
            for doc in self.project.documents:
                load_or_create_behavior_file(self.project.path, doc)
        except OSError:
            log_error("behavior file catchup")
