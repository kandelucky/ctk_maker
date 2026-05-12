"""File-menu handlers extracted from the monolithic ``main_window.py``.

Spans the entire File pipeline plus the related page-switch +
recovery helpers:

* **Startup** — ``_show_startup_dialog`` (modal launched from
  ``MainWindow.__init__`` once the splash is up; routes the user
  into Open or New).
* **Path tracking** — ``_set_current_path`` writes the active path
  back to settings / recent menu / behavior-file catchup;
  ``_open_path`` runs the load + autosave-swap + legacy-convert
  prompt + ghost replay.
* **File menu actions** — New, Open, Recover-from-backup, Save,
  Save As (multi-page + legacy single-file forms), Save-As page /
  clone-project / extract-page, Convert-to-multi-page, asset copy.
* **Toast + page switch** — ``_show_toast`` / ``_dismiss_toast`` are
  the shared status-banner; ``_switch_to_page`` /
  ``_on_active_page_renamed`` keep the active page in sync with the
  Project panel + recent-files entries.

Many handlers gate on ``_confirm_discard_if_dirty`` (stays in
``main_window.py`` as part of dirty-state) and finish with
``_set_current_path`` so the title + Recent menu + project-fonts +
behavior-file catchup all refresh in one place.
"""
from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

from app.core.autosave import autosave_path_for, clear_autosave
from app.core.fonts import (
    register_project_fonts, set_active_project_defaults,
)
from app.core.logger import log_error
from app.core.recent_files import add_recent
from app.io.project_loader import ProjectLoadError, load_project
from app.io.project_saver import save_project
from app.ui._main_window_host import _MainWindowHost
from app.ui.crash_dialog import show_crash_dialog
from app.ui.dialogs import NewProjectSizeDialog, prompt_open_project_folder
from app.ui.startup_dialog import StartupDialog
from app.ui.system_fonts import ui_font


PROJECT_FILE_TYPES = [("CTkMaker project", "*.ctkproj"), ("All files", "*.*")]


class FilesMixin(_MainWindowHost):
    """File menu + open / save / startup / page switch handlers.
    See module docstring.
    """

    def _show_startup_dialog(self) -> None:
        # Hand the splash dismissal hook to the dialog so the splash
        # disappears in the same flush as the dialog reveal — avoids
        # a frame where neither window is visible.
        splash = self._splash
        self._splash = None

        def _dismiss_splash() -> None:
            if splash is not None:
                try:
                    splash.destroy()
                except Exception:
                    pass

        dialog = StartupDialog(self, on_ready=_dismiss_splash)
        self.wait_window(dialog)
        result = dialog.result
        if result is None:
            # No "untitled" fallback any more — every project lives
            # inside a folder structure, which means it must be either
            # opened from disk or freshly created via the New Project
            # dialog. Cancelling the startup dialog quits the app.
            self.destroy()
            return
        # Apply geometry / maximize state and load project content
        # while still alpha-hidden, then reveal in finally so the user
        # never sees the WM-default white BG nor content filling in.
        try:
            self._apply_saved_window_state()
            self.deiconify()
            if getattr(self, "_wants_maximized", False):
                self._safe_zoom()
            if result[0] == "open":
                self._open_path(result[1])
            elif result[0] == "new":
                _, name, w, h, path = result
                self.project.clear()
                self.project.resize_document(w, h)
                self.project.name = name
                self.project.active_document.name = name
                from app.core.project_folder import seed_multi_page_meta_from_disk
                seed_multi_page_meta_from_disk(self.project, path)
                try:
                    save_project(self.project, path)
                except OSError:
                    log_error("save_project (new project)")
                    messagebox.showerror(
                        "Save failed",
                        f"Could not create project file at:\n{path}",
                        parent=self,
                    )
                    return
                clear_autosave(path)
                self._set_current_path(path)
        finally:
            try:
                self.update_idletasks()
                self.attributes("-alpha", 1.0)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Current-path tracking
    # ------------------------------------------------------------------
    def _set_current_path(self, path: str | None) -> None:
        self._current_path = path
        self.project.path = path
        self._clear_dirty()
        if path:
            add_recent(path)
            self._rebuild_recent_menu()
            # Load any project-bundled .ttf/.otf into Tk so descriptors
            # that reference those families resolve them as real fonts
            # instead of silently falling back to Tk's default.
            register_project_fonts(path, root=self)
            # Phase 2 — once a path exists, materialise the behavior
            # file for every Document. Catches up the eager-create
            # logic for projects opened from disk (which never fired
            # ``document_added``) and for the first save of an
            # unsaved project (where the deferred queue lands here).
            self._ensure_behavior_files_for_all_docs()
        # Refresh the active font cascade from whatever the just-loaded
        # (or just-saved-as) project carries. New projects start with
        # an empty cascade; this also clears stale defaults left over
        # from the previous project.
        set_active_project_defaults(getattr(self.project, "font_defaults", {}))
        self._refresh_title()
        # Canvas chrome + anything else that mirrors project.name
        # needs a poke — New, Open and Save As all flow through here.
        self.project.event_bus.publish("project_renamed", self.project.name)

    def _open_path(self, path: str) -> None:
        if not Path(path).exists():
            messagebox.showerror("Open failed", f"File not found:\n{path}", parent=self)
            return
        # If an autosave sits next to this project AND is newer than
        # the saved file, the previous session crashed (or the user
        # closed without saving) — offer to restore from it instead
        # of loading the older saved copy.
        load_target = self._maybe_swap_for_autosave(path)
        try:
            load_project(self.project, load_target, root=self)
        except ProjectLoadError as exc:
            messagebox.showerror("Open failed", str(exc), parent=self)
            return
        except Exception:
            tb = log_error("load_project")
            show_crash_dialog(
                self, "Open failed",
                "Unexpected error opening project.", tb,
            )
            return
        self._set_current_path(path)
        # Apply any ``_pending_ghost`` flags the loader queued up —
        # the load path skipped real freeze because widgets weren't
        # built yet; now they are, so the ghost manager can capture.
        gm = getattr(self.workspace, "ghost_manager", None)
        if gm is not None:
            gm.freeze_pending()
            # Re-focus the active doc after load. Deferred via
            # ``after_idle`` + a small ``after`` because at this point
            # the splash is still up (alpha=0), the paned window
            # hasn't divided the workspace into its final width, and
            # ``focus_document`` reads ``canvas.winfo_width()`` which
            # at that instant returns the placeholder / full-screen
            # size — the doc lands offset accordingly. Waiting one
            # idle round + a frame lets the layout settle so startup
            # centering matches the click-time behaviour.
            active_id = self.project.active_document_id
            if active_id is not None:
                self.after_idle(
                    lambda: self.after(
                        100,
                        lambda: self.workspace.focus_document(active_id),
                    ),
                )
        # Detect legacy single-file projects (no project.json marker
        # in the walked-up folder) and offer a one-shot conversion
        # to the multi-page format. Skipped for already-converted
        # projects + when the user just declined a previous prompt
        # in this session (don't nag — they can use File menu).
        if (
            self.project.folder_path is None
            and not getattr(self, "_convert_prompt_dismissed", False)
        ):
            self._maybe_prompt_legacy_convert()
        # If we restored from autosave, drop the file now that the
        # state is in memory — next explicit save writes it back to
        # the real .ctkproj.
        if load_target != path:
            clear_autosave(path)
            self._dirty = True
            self.project.event_bus.publish("dirty_changed", True)
            self._refresh_title()

    def _maybe_swap_for_autosave(self, path: str) -> str:
        autosave = autosave_path_for(path)
        try:
            if not autosave.exists():
                return path
            real_mtime = Path(path).stat().st_mtime
            auto_mtime = autosave.stat().st_mtime
        except OSError:
            return path
        if auto_mtime <= real_mtime:
            return path
        ts = datetime.fromtimestamp(auto_mtime).strftime(
            "%Y-%m-%d %H:%M",
        )
        choice = messagebox.askyesno(
            "Restore from autosave?",
            (
                f"An autosave from {ts} is newer than the saved "
                f"project file.\n\n"
                f"This usually means the previous session ended "
                f"without an explicit Save — for example after a "
                f"crash or a forced close.\n\n"
                f"Yes  → restore from the autosave\n"
                f"No   → open the older saved copy "
                f"(autosave is left untouched)"
            ),
            parent=self,
        )
        return str(autosave) if choice else path

    # ------------------------------------------------------------------
    # File menu commands
    # ------------------------------------------------------------------
    def _stub(self, name: str) -> None:
        messagebox.showinfo("Toolbar stub", f"{name} — not implemented yet", parent=self)

    def _on_new(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        # Resolve the "Save to" default — the parent directory the
        # user originally picked (e.g. ``Documents/CTkMaker/``), one
        # level above the project folder. ``project.folder_path`` is
        # the multi-page project root; legacy single-file projects
        # fall back to two ``parent`` walks from the .ctkproj.
        if self.project.folder_path:
            default_dir = str(Path(self.project.folder_path).parent)
        elif self._current_path:
            default_dir = str(Path(self._current_path).parent.parent)
        else:
            default_dir = None
        dialog = NewProjectSizeDialog(
            self,
            default_w=self.project.document_width,
            default_h=self.project.document_height,
            default_save_dir=default_dir,
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        name, path, w, h = dialog.result
        self.project.clear()
        self.project.resize_document(w, h)
        self.project.name = name
        # Seed the first document's title from the project name so
        # the exported `app.title(...)` matches what the user typed
        # in the New dialog. They can still rename the window via
        # the Properties panel afterwards.
        self.project.active_document.name = name
        from app.core.project_folder import seed_multi_page_meta_from_disk
        seed_multi_page_meta_from_disk(self.project, path)
        try:
            save_project(self.project, path)
        except OSError:
            log_error("save_project (file new)")
            messagebox.showerror(
                "Save failed",
                f"Could not create project file at:\n{path}",
                parent=self,
            )
            return
        clear_autosave(path)
        self._set_current_path(path)

    def _on_open(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        # Default to the parent of the currently-open project (or
        # the user's projects root) so the picker lands one level
        # above where the user actually clicks — i.e. on the list of
        # projects, not inside one.
        if self.project.folder_path:
            initial = str(Path(self.project.folder_path).parent)
        elif self._current_path:
            initial = str(Path(self._current_path).parent.parent)
        else:
            from app.core.paths import get_default_projects_dir
            initial = str(get_default_projects_dir())
        picked = prompt_open_project_folder(self, initial_dir=initial)
        if picked is None:
            return
        self._open_path(str(picked))

    def _on_recover_from_backup(self) -> None:
        """Open a ``.ctkproj.bak`` file as an untitled project so the
        user must Save As before any further edits — prevents an
        accidental Save from overwriting the (presumably damaged)
        original next to the backup.
        """
        if not self._confirm_discard_if_dirty():
            return
        path = filedialog.askopenfilename(
            parent=self,
            title="Recover project from backup",
            filetypes=[
                ("CTkMaker backup", "*.ctkproj.bak"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        if not Path(path).exists():
            messagebox.showerror(
                "Recover failed",
                f"File not found:\n{path}",
                parent=self,
            )
            return
        try:
            load_project(self.project, path, root=self)
        except ProjectLoadError as exc:
            messagebox.showerror("Recover failed", str(exc), parent=self)
            return
        except Exception:
            tb = log_error("recover_from_backup")
            show_crash_dialog(
                self, "Recover failed",
                "Unexpected error recovering from backup.", tb,
            )
            return
        gm = getattr(self.workspace, "ghost_manager", None)
        if gm is not None:
            gm.freeze_pending()
        # Untitled — force Save As so the user can't blindly Ctrl+S
        # over the original .ctkproj sitting next to the .bak.
        self._current_path = None
        self._clear_dirty()
        self._refresh_title()
        self.project.event_bus.publish(
            "project_renamed", self.project.name,
        )
        messagebox.showinfo(
            "Recovered from backup",
            (
                "Loaded the backup as an untitled project.\n\n"
                "Use File → Save As to write it back as a real "
                ".ctkproj — direct Save is disabled until then so "
                "the original file (likely damaged) won't be "
                "overwritten by accident."
            ),
            parent=self,
        )

    def _maybe_prompt_legacy_convert(self) -> None:
        """Offer to convert the just-loaded legacy ``.ctkproj`` to
        the multi-page folder format. Auto-prompt fires once per
        session; further loads of legacy files in the same session
        skip the prompt so the user can keep working without
        repeated nags. ``File → Convert to Multi-Page Project...``
        is always available as an explicit entry point.
        """
        choice = messagebox.askyesno(
            "Convert to multi-page project?",
            (
                "This project uses the older single-file format.\n\n"
                "Multi-page projects let you keep multiple page "
                "designs (e.g. Login + Dashboard) inside one project, "
                "sharing the same fonts / images / icons.\n\n"
                "Yes  → convert now (a backup of the original .ctkproj "
                "is left next to it)\n"
                "No   → keep the single-file format for this session"
            ),
            parent=self,
        )
        if not choice:
            self._convert_prompt_dismissed = True
            return
        self._do_legacy_convert()

    def _on_convert_to_multi_page(self) -> None:
        """File menu entry — same conversion as the auto-prompt, but
        triggered explicitly. Refuses gracefully when already on a
        multi-page project.
        """
        if self.project.folder_path is not None:
            messagebox.showinfo(
                "Already converted",
                "This project is already in multi-page format.",
                parent=self,
            )
            return
        if not self._current_path:
            messagebox.showinfo(
                "Nothing to convert",
                "Open or create a project first.",
                parent=self,
            )
            return
        if not self._confirm_discard_if_dirty():
            return
        self._do_legacy_convert()

    def _do_legacy_convert(self) -> None:
        """Run the actual conversion. Saves any in-memory state to
        the legacy .ctkproj first so the converted page reflects the
        user's current edits, not just the last save.
        """
        if not self._current_path:
            return
        try:
            save_project(self.project, self._current_path)
        except OSError:
            log_error("convert pre-save")
            messagebox.showerror(
                "Convert failed",
                "Could not save current state before conversion.",
                parent=self,
            )
            return
        from app.core.project_folder import (
            ProjectMetaError, convert_legacy_to_multi_page,
        )
        try:
            new_page_path = convert_legacy_to_multi_page(self._current_path)
        except (ProjectMetaError, OSError) as exc:
            messagebox.showerror(
                "Convert failed", str(exc), parent=self,
            )
            return
        # Reload from the new layout so all in-memory pointers
        # (folder_path / pages / active_page_id / asset paths)
        # match the disk state. clear_autosave on old path drops
        # any sidecar that didn't follow the move.
        clear_autosave(self._current_path)
        self._open_path(str(new_page_path))
        self._show_toast("Converted to multi-page project")

    # ------------------------------------------------------------------
    # Status toast
    # ------------------------------------------------------------------
    def _show_toast(self, text: str, duration_ms: int = 1600) -> None:
        """Pop a small non-modal banner near the top of the workspace
        and auto-destroy it. Used for page-switch feedback so the
        user sees "Switched to Login" without a blocking dialog.
        Multiple rapid switches replace the previous toast in place.
        """
        try:
            existing = getattr(self, "_toast_window", None)
            if existing is not None:
                try:
                    existing.destroy()
                except tk.TclError:
                    pass
            toast = tk.Toplevel(self)
            self._toast_window = toast
            toast.overrideredirect(True)
            toast.configure(bg="#2d2d30")
            toast.attributes("-topmost", True)
            tk.Label(
                toast, text=text,
                bg="#2d2d30", fg="#cccccc",
                font=ui_font(10),
                padx=18, pady=8,
            ).pack()
            toast.update_idletasks()
            # Anchor near the top-center of the main window so the
            # banner reads at a glance without covering the toolbar.
            try:
                self.update_idletasks()
                x = (
                    self.winfo_rootx()
                    + (self.winfo_width() - toast.winfo_width()) // 2
                )
                y = self.winfo_rooty() + 80
                toast.geometry(f"+{max(0, x)}+{max(0, y)}")
            except tk.TclError:
                pass
            toast.after(duration_ms, lambda: self._dismiss_toast(toast))
        except tk.TclError:
            pass

    def _dismiss_toast(self, toast: tk.Toplevel) -> None:
        try:
            toast.destroy()
        except tk.TclError:
            pass
        if getattr(self, "_toast_window", None) is toast:
            self._toast_window = None

    # ------------------------------------------------------------------
    # Page switch / rename
    # ------------------------------------------------------------------
    def _on_active_page_renamed(self, new_path: str) -> None:
        """Hook called when ProjectPanel renames the currently-active
        page on disk. Update ``_current_path`` so future Save / Save
        As / autosave land at the new filename, and refresh the title.
        Recent files entry shifts to the new path so the next launch
        opens the renamed file.
        """
        target = Path(new_path)
        # The on-disk rename already moved the autosave / .bak
        # sidecars (see project_folder.rename_page), so the previous
        # path's autosave is gone — no clear_autosave needed.
        self._current_path = str(target)
        self.project.path = str(target)
        try:
            add_recent(str(target))
            self._rebuild_recent_menu()
        except Exception:
            log_error("rename active page recent")
        self._refresh_title()

    def _switch_to_page(self, page_path: str) -> bool:
        """Switch the editor to a different page within the current
        multi-page project. Reuses the Open flow (dirty check + save +
        load), so the user gets the standard "Save / Don't Save /
        Cancel" prompt before the switch.

        Returns ``True`` when the switch happened, ``False`` if the
        user cancelled or the load failed. The caller decides whether
        to update any UI that mirrors the active page.
        """
        target = Path(page_path)
        # Same page — no-op.
        if (
            self._current_path
            and Path(self._current_path).resolve() == target.resolve()
        ):
            return True
        if not target.exists():
            messagebox.showerror(
                "Switch failed",
                f"Page file not found:\n{target}",
                parent=self,
            )
            return False
        if not self._confirm_discard_if_dirty():
            return False
        # Update project.json's active_page BEFORE loading so the
        # next launch lands on the page the user picked. Failure
        # here is non-fatal — the load below still proceeds.
        if self.project.folder_path:
            from app.core.project_folder import (
                ProjectMetaError, set_active_page,
            )
            try:
                page_id = next(
                    (
                        p["id"] for p in self.project.pages
                        if isinstance(p, dict)
                        and p.get("file") == target.name
                    ),
                    None,
                )
                if page_id is not None:
                    set_active_page(self.project.folder_path, page_id)
            except ProjectMetaError:
                log_error("switch_to_page set_active_page")
        # Resolve the page's display name BEFORE the load resets
        # in-memory metadata — the toast wants the user-facing name,
        # not the page filename slug.
        switched_name = next(
            (
                p.get("name", "") for p in (self.project.pages or [])
                if isinstance(p, dict) and p.get("file") == target.name
            ),
            target.stem,
        )
        self._open_path(str(target))
        self._show_toast(f"Switched to: {switched_name}")
        return True

    # ------------------------------------------------------------------
    # Save / Save As
    # ------------------------------------------------------------------
    def _on_save(self) -> None:
        if self._current_path:
            try:
                save_project(self.project, self._current_path)
            except OSError:
                log_error("save_project")
                messagebox.showerror("Save failed", "Could not write the project file.", parent=self)
                return
            clear_autosave(self._current_path)
            self._set_current_path(self._current_path)
        else:
            self._on_save_as()

    def _on_ghost_toggled_save(self, _doc_id, _ghost) -> None:
        """Persist the project immediately when a ghost toggle fires
        so the freshly captured base64 PNG in ``Document.to_dict``
        survives close-without-save. Silent on missing path
        (untitled project — nothing to write back to) and on OSError
        (next regular save will catch up; can't surface a modal in
        the middle of a workspace click)."""
        if self._current_path is None:
            return
        try:
            save_project(self.project, self._current_path)
            clear_autosave(self._current_path)
        except OSError:
            log_error("save_project (ghost toggle)")

    def _on_save_as(self) -> None:
        # Multi-page projects open the 3-scope dialog; legacy
        # single-file projects still use the classic filedialog
        # (no concept of pages, no scope choice to make).
        if self.project.folder_path:
            self._save_as_multi_page()
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save project as",
            defaultextension=".ctkproj",
            filetypes=PROJECT_FILE_TYPES,
        )
        if not path:
            return
        # Copy the assets/ tree to the new location BEFORE saving the
        # ctkproj, so the saved file's tokenised asset paths
        # (``asset:images/...``) resolve against a real folder. Without
        # this, Save As writes only the .ctkproj and the new location
        # has dangling references to assets back at the original path.
        old_path = self._current_path
        if old_path and Path(old_path).resolve() != Path(path).resolve():
            self._copy_assets_to_new_location(old_path, path)
        try:
            save_project(self.project, path)
        except OSError:
            log_error("save_project")
            messagebox.showerror("Save failed", "Could not write the project file.", parent=self)
            return
        # Save As may target a brand-new path, but also clear any stale
        # autosave at the previous path so the next launch doesn't
        # offer to "restore" content the user already moved over.
        clear_autosave(self._current_path)
        clear_autosave(path)
        self._set_current_path(path)

    def _save_as_multi_page(self) -> None:
        """Multi-page Save As — opens the 3-scope dialog and
        dispatches:
          - ``page``    → add_page in current project
          - ``project`` → clone_project_folder + open the duplicate
          - ``extract`` → extract_page_to_new_project + open it
        """
        from app.ui.save_as_dialog import SaveAsDialog
        dlg = SaveAsDialog(self, self.project)
        self.wait_window(dlg)
        result = dlg.result
        if result is None:
            return
        scope = result["scope"]
        name = result["name"]
        if scope == "page":
            self._save_as_new_page(name)
        elif scope == "project":
            self._save_as_clone_project(name, result["save_to"])
        elif scope == "extract":
            self._save_as_extract_page(name, result["save_to"])

    def _save_as_new_page(self, name: str) -> None:
        """Add a new page in the current project, switch to it, and
        copy the in-memory state (so the new page starts as a clone
        of what the user is currently looking at — matches the
        traditional Save As mental model where the new file picks
        up your working state).
        """
        from app.core.project_folder import (
            ProjectMetaError, add_page, page_file_path,
            seed_multi_page_meta_from_disk,
        )
        folder_path = self.project.folder_path
        if folder_path is None:
            messagebox.showerror(
                "Save failed",
                "Project folder is not set.",
                parent=self,
            )
            return
        try:
            entry = add_page(folder_path, name)
        except ProjectMetaError as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)
            return
        new_page_path = page_file_path(folder_path, entry["file"])
        # Save current in-memory state into the new page file so
        # the new page starts as a copy of the working state.
        # Refresh metadata so the saver sees the new page entry.
        seed_multi_page_meta_from_disk(self.project, str(new_page_path))
        # Switch project.path so save lands on the new page.
        old_path = self._current_path
        self._current_path = str(new_page_path)
        self.project.path = str(new_page_path)
        self.project.active_page_id = entry["id"]
        try:
            save_project(self.project, str(new_page_path))
        except OSError:
            log_error("save_as new page")
            self._current_path = old_path
            self.project.path = old_path
            messagebox.showerror(
                "Save failed",
                "Could not write the new page file.",
                parent=self,
            )
            return
        clear_autosave(old_path)
        # Run a fresh open so all listeners (ProjectPanel, title
        # bar, etc.) reflect the new active page.
        self._set_current_path(str(new_page_path))
        self._show_toast(f"Saved as: {name}")

    def _save_as_clone_project(self, name: str, save_to: str) -> None:
        """Duplicate the entire project folder at ``<save_to>/<name>``
        and open the duplicate. The source project is left untouched.
        """
        # Save current state first so the duplicate captures any
        # in-memory edits.
        if self._current_path is None:
            messagebox.showerror(
                "Save failed",
                "No project is currently open.",
                parent=self,
            )
            return
        try:
            save_project(self.project, self._current_path)
        except OSError:
            log_error("save_as clone pre-save")
            messagebox.showerror(
                "Save failed",
                "Could not save current state before cloning.",
                parent=self,
            )
            return
        from app.core.project_folder import clone_project_folder
        folder_path = self.project.folder_path
        if folder_path is None:
            messagebox.showerror(
                "Save failed",
                "Project folder is not set.",
                parent=self,
            )
            return
        try:
            new_folder = clone_project_folder(
                folder_path, save_to, name,
            )
        except OSError as exc:
            messagebox.showerror(
                "Save failed", str(exc), parent=self,
            )
            return
        # Open the cloned project — load_project picks up the
        # active page from project.json automatically.
        if not self._confirm_discard_if_dirty():
            return
        self._open_path(str(new_folder))
        self._show_toast(f"Cloned to: {name}")

    def _save_as_extract_page(self, name: str, save_to: str) -> None:
        """Save the current page (with only its referenced assets)
        as a brand-new project at ``<save_to>/<name>``.
        """
        if self._current_path is None:
            messagebox.showerror(
                "Save failed",
                "No project is currently open.",
                parent=self,
            )
            return
        try:
            save_project(self.project, self._current_path)
        except OSError:
            log_error("save_as extract pre-save")
            messagebox.showerror(
                "Save failed",
                "Could not save current state before extracting.",
                parent=self,
            )
            return
        from app.core.project_folder import extract_page_to_new_project
        try:
            new_page_path = extract_page_to_new_project(
                self.project, save_to, name,
            )
        except OSError as exc:
            messagebox.showerror(
                "Save failed", str(exc), parent=self,
            )
            return
        if not self._confirm_discard_if_dirty():
            return
        self._open_path(str(new_page_path))
        self._show_toast(f"Extracted to: {name}")

    def _copy_assets_to_new_location(
        self, old_project_path: str, new_project_path: str,
    ) -> None:
        """Mirror the project's ``assets/`` folder from the old
        location to the new one so a Save As lands a self-contained
        project. Existing files at the destination are preserved
        (``dirs_exist_ok=True``) so a target directory the user
        prepared doesn't get blanked out. Failures log and continue —
        the .ctkproj save still proceeds; the user can drop missing
        assets in manually if needed.

        Multi-page projects use the project root's ``assets/`` (walked
        up via project.json); legacy projects use the .ctkproj's
        sibling ``assets/``. The destination layout mirrors the source
        — Save As to a multi-page page lands assets at the new root.
        """
        try:
            import shutil
            from app.core.assets import project_assets_dir
            src_assets = project_assets_dir(old_project_path)
            if src_assets is None:
                src_assets = Path(old_project_path).parent / "assets"
            if not src_assets.is_dir():
                return
            dst_assets = project_assets_dir(new_project_path)
            if dst_assets is None:
                dst_assets = Path(new_project_path).parent / "assets"
            dst_assets.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src_assets, dst_assets, dirs_exist_ok=True)
        except OSError:
            log_error("save_as copy assets")
