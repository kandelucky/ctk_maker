"""Preview / Run / Export action handlers extracted from ``main_window.py``.

Three families of "produce a runnable Python file" actions:

* **Preview** — full project (``_on_preview``, F5) or single dialog
  (``_on_preview_dialog``, chrome ▶ button). Exports to a temp dir,
  walks the user through the missing-handler / var-name-fallback /
  ref-annotation confirmations, then spawns the preview subprocess
  and pipes its stdout/stderr into the in-app Console panel.
* **Run script** — pick any ``.py`` file off disk and launch it with
  ``sys.executable``. The last-used directory is persisted so the
  next click starts where the previous one left off.
* **Export** — full export dialog + per-document quick export
  (``_on_export_active_document``) that writes to
  ``<project>/exports/<slug>.{py,zip}`` with a single ZIP-or-py prompt.

Relies on the module-level preview helpers (``_spawn_preview``,
``_preview_show_floater``, ``_confirm_missing_handler_methods``, …)
that still live in ``main_window`` — they're imported lazily inside
each method to avoid the circular ``main_window → main_preview →
main_window`` cycle at import time.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from tkinter import filedialog, messagebox

from app.core.logger import log_error
from app.core.settings import load_settings, save_setting
from app.io.code_exporter import export_project
from app.ui._main_window_host import _MainWindowHost


class PreviewMixin(_MainWindowHost):
    """Preview / run / export handlers. See module docstring."""

    # ------------------------------------------------------------------
    # Preview (full project + per-dialog)
    # ------------------------------------------------------------------
    def _on_preview_active(self) -> None:
        doc = self.project.active_document
        if doc.is_toplevel and doc.root_widgets:
            self._on_preview_dialog(doc.id)

    def _on_preview(self) -> None:
        from app.ui.main_window import (
            _confirm_missing_handler_methods, _confirm_ref_annotation_issues,
            _confirm_var_name_fallbacks, _preview_cwd, _preview_show_floater,
            _spawn_preview,
        )
        if not self.project.root_widgets:
            messagebox.showinfo(
                "Preview",
                "Nothing to preview — workspace is empty.",
                parent=self,
            )
            return
        # Same dedup as per-dialog preview: at most one main preview
        # window alive at a time. Closing it frees the slot.
        existing = self._main_preview_proc
        if existing is not None and existing.poll() is None:
            return
        self._main_preview_proc = None
        tmp_dir = Path(tempfile.mkdtemp(prefix="ctk_preview_"))
        tmp_path = tmp_dir / "preview.py"
        try:
            export_project(
                self.project, tmp_path,
                inject_preview_screenshot=_preview_show_floater(),
            )
        except OSError:
            log_error("preview export")
            messagebox.showerror("Preview failed", "Could not generate preview file.", parent=self)
            return
        if not _confirm_missing_handler_methods(self):
            return
        if not _confirm_var_name_fallbacks(self):
            return
        if not _confirm_ref_annotation_issues(self):
            return
        try:
            proc = _spawn_preview(
                tmp_dir, tmp_path,
                str(_preview_cwd(self.project, tmp_dir)),
            )
        except OSError:
            log_error("preview subprocess")
            messagebox.showerror("Preview failed", "Could not launch Python.", parent=self)
            return
        self._main_preview_proc = proc
        self._attach_console_capture(proc)

    def _on_preview_dialog(self, doc_id: str | None = None) -> None:
        """Launch a dialog-only preview — the chrome ▶ button on every
        Toplevel document routes here via ``request_preview_dialog``.
        Exports the project with ``preview_dialog_id=doc_id`` so the
        generated __main__ block opens just this dialog on top of a
        withdrawn root.

        One preview window per dialog: if a previous subprocess for
        the same ``doc_id`` is still alive, the click is a no-op (the
        user must close the existing preview first). Prevents a
        mash-of-clicks from flooding the screen with duplicate copies.
        """
        from app.ui.main_window import (
            _confirm_missing_handler_methods, _confirm_ref_annotation_issues,
            _confirm_var_name_fallbacks, _preview_cwd, _preview_show_floater,
            _spawn_preview,
        )
        if not doc_id:
            return
        doc = self.project.get_document(doc_id)
        if doc is None or not doc.is_toplevel:
            return
        # One live preview per dialog.
        existing = self._dialog_preview_procs.get(doc_id)
        if existing is not None and existing.poll() is None:
            return
        self._dialog_preview_procs.pop(doc_id, None)
        tmp_dir = Path(tempfile.mkdtemp(prefix="ctk_preview_dlg_"))
        tmp_path = tmp_dir / "preview.py"
        try:
            export_project(
                self.project, tmp_path, preview_dialog_id=doc_id,
                inject_preview_screenshot=_preview_show_floater(),
            )
        except OSError:
            log_error("preview dialog export")
            messagebox.showerror(
                "Preview failed",
                "Could not generate preview file.",
                parent=self,
            )
            return
        if not _confirm_missing_handler_methods(self):
            return
        if not _confirm_var_name_fallbacks(self):
            return
        if not _confirm_ref_annotation_issues(self):
            return
        try:
            proc = _spawn_preview(
                tmp_dir, tmp_path,
                str(_preview_cwd(self.project, tmp_dir)),
            )
        except OSError:
            log_error("preview dialog subprocess")
            messagebox.showerror(
                "Preview failed", "Could not launch Python.",
                parent=self,
            )
            return
        self._dialog_preview_procs[doc_id] = proc
        self._attach_console_capture(proc)

    # ------------------------------------------------------------------
    # Run script
    # ------------------------------------------------------------------
    def _on_run_script(self) -> None:
        """Pick any local .py file and run it as a subprocess. Useful
        for quickly testing scripts the user already exported (or any
        other Python file) without leaving the builder. The chosen
        directory is remembered on the settings file so the next pick
        starts where the previous one left off.
        """
        last_dir = load_settings().get("run_script_last_dir") or str(
            Path.home() / "Desktop",
        )
        path = filedialog.askopenfilename(
            parent=self,
            title="Run a Python script",
            initialdir=last_dir,
            filetypes=[("Python", "*.py"), ("All files", "*.*")],
        )
        if not path:
            return
        save_setting("run_script_last_dir", str(Path(path).parent))
        if Path(path).suffix.lower() not in {".py", ".pyw"}:
            messagebox.showerror(
                "Not a Python script",
                f"Run Python Script only accepts .py / .pyw files.\n\n"
                f"You picked:\n{path}",
                parent=self,
            )
            return
        try:
            subprocess.Popen(
                [sys.executable, path],
                cwd=str(Path(path).parent),
            )
        except OSError:
            log_error("run_script subprocess")
            messagebox.showerror(
                "Run failed",
                f"Could not launch:\n{path}",
                parent=self,
            )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def _on_export(self) -> None:
        if not self._confirm_save_before_export():
            return
        from app.ui.export_dialog import ExportDialog
        ExportDialog(self, self.project)

    def _confirm_save_before_export(self) -> bool:
        """Block export if the project has unsaved changes — single
        OK button to acknowledge, then abort so the user can save
        manually. Returns True when the caller may proceed."""
        if not self._dirty:
            return True
        messagebox.showwarning(
            "Unsaved changes",
            "Please save your progress before exporting.",
            parent=self,
        )
        return False

    def _on_export_active_document(
        self, doc_id: str | None = None,
    ) -> None:
        """Quick-export ONE document (Main Window or Dialog) as a
        standalone runnable ``.py``. Asks one question only —
        ZIP-with-assets or plain .py — then writes straight to
        ``<project>/exports/<doc_slug>.{py|zip}`` with a toast.

        Asset filter is always document-scoped so the bundle ships
        only the fonts / images / icons this specific form actually
        references, never the whole shared pool.

        Triggered from File → "Export Active Document..." (active
        doc) and from the per-form chrome Export icon (specific id
        via ``request_export_document`` event bus).
        """
        from app.ui.main_window import _format_ref_annotation_issues_body
        if not self._confirm_save_before_export():
            return
        target_id = doc_id or self.project.active_document_id
        doc = self.project.get_document(target_id)
        if doc is None:
            return
        # Resolve output folder up-front so the dialog can preview
        # the path before the user commits. Multi-page projects use
        # <root>/exports/; legacy single-file projects use the
        # .ctkproj's sibling exports/ folder.
        if self.project.folder_path:
            out_dir = Path(self.project.folder_path) / "exports"
        elif self._current_path:
            out_dir = Path(self._current_path).parent / "exports"
        else:
            messagebox.showinfo(
                "Quick export",
                "Save the project before exporting.",
                parent=self,
            )
            return
        from app.core.project_folder import (
            collect_used_assets, slugify_page_name,
        )
        slug = slugify_page_name(doc.name or "document")
        # Preview shows the full output path with a wildcard
        # extension since the user hasn't picked a format yet.
        base_path = self.project.folder_path or self._current_path
        try:
            preview_path = str(
                (out_dir / f"{slug}.*").relative_to(
                    Path(base_path).parent if base_path else out_dir,
                ),
            )
        except (ValueError, TypeError):
            preview_path = str(out_dir / f"{slug}.*")
        from app.ui.quick_export_dialog import QuickExportDialog
        dlg = QuickExportDialog(self, doc.name or "Untitled", preview_path)
        self.wait_window(dlg)
        choice = dlg.result
        if choice is None:
            return
        as_zip = choice == "zip"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            log_error("quick export mkdir")
            messagebox.showerror(
                "Export failed",
                f"Could not create exports folder:\n{out_dir}",
                parent=self,
            )
            return
        ext = ".zip" if as_zip else ".py"
        target = out_dir / f"{slug}{ext}"
        asset_filter = collect_used_assets(self.project, document_id=target_id)
        # Respect the AI-bridge toggle persisted from the full Export
        # dialog so Quick Export's behaviour stays consistent.
        include_descriptions = bool(
            load_settings().get("export_include_descriptions", True),
        )
        try:
            export_project(
                self.project, str(target),
                single_document_id=target_id,
                as_zip=as_zip,
                asset_filter=asset_filter,
                include_descriptions=include_descriptions,
            )
        except OSError as exc:
            log_error("quick export")
            messagebox.showerror(
                "Export failed",
                f"Could not write the export:\n{target}\n\n{exc}",
                parent=self,
            )
            return
        # Ref-annotation mismatches are non-fatal but bite at first
        # widget interaction in the exported app — surface them before
        # the success toast so the user can fix before sharing.
        ref_body = _format_ref_annotation_issues_body()
        if ref_body is not None:
            messagebox.showwarning(
                "Object Reference annotations out of sync",
                ref_body,
                parent=self,
            )
        # Show a relative path in the toast — the user already
        # knows their project folder; the noisy absolute prefix
        # would push the actual filename off-screen on a small
        # toast.
        base_path = self.project.folder_path or self._current_path
        try:
            display = target.relative_to(
                Path(base_path).parent if base_path else target.parent,
            )
        except (ValueError, TypeError):
            display = target.name
        self._show_toast(f"Exported: {display}", duration_ms=2400)
