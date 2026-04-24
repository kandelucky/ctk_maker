import subprocess
import sys
import tempfile
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app.core.autosave import (
    AutosaveController, autosave_path_for, clear_autosave,
)
from app.core.logger import log_error
from app.core.project import Project
from app.core.recent_files import add_recent
from app.core.settings import load_settings, save_setting
from app.io.code_exporter import export_project
from app.io.project_loader import ProjectLoadError, load_project
from app.io.project_saver import save_project
from app.ui.dialogs import NewProjectSizeDialog
from app.ui.history_window import HistoryPanel, HistoryWindow
from app.ui.main_menu import APPEARANCE_MODES, MenuMixin
from app.ui.main_shortcuts import ShortcutsMixin
from app.ui.object_tree_window import ObjectTreePanel, ObjectTreeWindow
from app.ui.palette import Palette
from app.ui.project_window import ProjectWindow
from app.ui.properties_panel_v2 import PropertiesPanelV2 as PropertiesPanel
from app.ui.startup_dialog import StartupDialog
from app.ui.toolbar import Toolbar
from app.ui.workspace import Workspace

PROJECT_FILE_TYPES = [("CTkMaker project", "*.ctkproj"), ("All files", "*.*")]

ABOUT_TEXT = (
    "CTkMaker\n"
    "v0.0.12\n\n"
    "Drag-and-drop designer for CustomTkinter that exports clean Python code.\n\n"
    "Built with:\n"
    "  • CustomTkinter (MIT)\n"
    "  • Lucide Icons (MIT)\n"
    "  • Pillow\n"
    "  • ctk-tint-color-picker"
)

GITHUB_DOCS_URL = "https://github.com/kandelucky/ctk_maker/blob/main/docs/widgets/README.md"


class MainWindow(ShortcutsMixin, MenuMixin, ctk.CTk):
    """Top-level application window.

    Method surface split across mixins:

    - ``ShortcutsMixin`` (``main_shortcuts.py``) — keyboard bindings,
      non-Latin keycode router, Ctrl+Z/Y auto-repeat guards, Copy /
      Paste virtual-event fallbacks.
    - ``MenuMixin`` (``main_menu.py``) — menubar construction, Recent
      Forms submenu, Edit-menu state (dimming via foreground swap),
      Edit-menu dispatchers.
    """
    def __init__(self):
        super().__init__()
        self.title("CTkMaker")
        self.minsize(900, 600)
        self._set_centered_geometry(1280, 800)
        self.configure(fg_color="#252526")

        # Reconfigure every named Tk font to Segoe UI so Georgian (and
        # other non-Latin scripts) renders instead of "?" placeholders.
        # Empty-family tuples like `font=("", 11)` resolve through these
        # named fonts, so this single change covers most call sites.
        if sys.platform == "win32":
            for _font_name in (
                "TkDefaultFont", "TkTextFont", "TkFixedFont",
                "TkMenuFont", "TkHeadingFont", "TkCaptionFont",
                "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont",
            ):
                try:
                    tkfont.nametofont(_font_name).configure(family="Segoe UI")
                except tk.TclError:
                    pass
        self.option_add("*Font", "{Segoe UI} 11")

        # Non-Latin keyboard layouts (Georgian, Russian, ...) remap the
        # V/C/X/A keysyms, so tk's default <Control-v> etc. never fire
        # and clipboard shortcuts break. Fall back to the hardware
        # keycode (Windows VK) and emit the corresponding virtual event.
        self.bind_all("<Control-KeyPress>", self._on_control_keypress)

        self.project = Project()
        self._current_path: str | None = None
        self._dirty: bool = False
        # History top at the last save — ``_recompute_dirty`` compares
        # the current top to this marker so undo-ing back to the saved
        # state flips dirty off automatically.
        self._saved_history_marker = None
        # Active ``subprocess.Popen`` handles for per-dialog previews,
        # keyed by document id. We poll the handle before launching a
        # new one so clicking ▶ repeatedly on the same dialog doesn't
        # spawn duplicate preview windows.
        self._dialog_preview_procs: dict[str, subprocess.Popen] = {}
        self._main_preview_proc: subprocess.Popen | None = None
        self._object_tree_window: ObjectTreeWindow | None = None
        # Default: Object Tree is docked above the Properties panel —
        # the floating window only opens via the View menu toggle.
        self._object_tree_var = tk.BooleanVar(value=False)
        self._history_window: HistoryWindow | None = None
        self._history_var = tk.BooleanVar(value=False)
        self._project_window: ProjectWindow | None = None
        self._project_var = tk.BooleanVar(value=False)

        settings = load_settings()
        initial_mode = settings.get("appearance_mode", "Dark")
        if initial_mode not in APPEARANCE_MODES:
            initial_mode = "Dark"
        ctk.set_appearance_mode(initial_mode.lower())
        self._appearance_var = tk.StringVar(value=initial_mode)

        self._build_menubar()
        self._bind_shortcuts()

        self.toolbar = Toolbar(
            self,
            on_new=self._on_new,
            on_open=self._on_open,
            on_save=self._on_save,
            on_preview=self._on_preview,
            on_export=self._on_export,
            on_theme_toggle=self._on_theme_toggle,
            on_undo=self._on_undo,
            on_redo=self._on_redo,
            on_run_script=self._on_run_script,
        )
        self.toolbar.pack(side="top", fill="x")

        self.paned = tk.PanedWindow(
            self,
            orient=tk.HORIZONTAL,
            sashwidth=5,
            sashrelief=tk.FLAT,
            bg="#1e1e1e",
            borderwidth=0,
            showhandle=False,
        )
        self.paned.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.palette = Palette(
            self.paned, self.project,
            on_collapse_changed=self._on_palette_collapsed,
        )
        self.workspace = Workspace(self.paned, self.project)
        self.palette.drop_validator = self.workspace.is_cursor_over_document

        # Right sidebar: Object Tree docked above the Properties panel
        # in a nested vertical PanedWindow. A slightly-wider horizontal
        # sash so the user can actually grab it; bg colour picks up the
        # same gutter shade the main horizontal sash uses.
        self.right_pane = tk.PanedWindow(
            self.paned,
            orient=tk.VERTICAL,
            sashwidth=7,
            sashrelief=tk.FLAT,
            bg="#3a3a3a",
            borderwidth=0,
            showhandle=False,
        )
        # Top pane: Object Tree + History share one slot, switched by
        # a header row with two toggle buttons.
        _top_wrap = tk.Frame(self.right_pane, bg="#1e1e1e")

        _hdr = tk.Frame(_top_wrap, bg="#2d2d2d", height=28)
        _hdr.pack(side="top", fill="x")
        _hdr.pack_propagate(False)

        _content = tk.Frame(_top_wrap, bg="#1e1e1e")
        _content.pack(fill="both", expand=True)

        self.object_tree = ObjectTreePanel(_content, self.project)
        self._docked_history = HistoryPanel(_content, self.project)
        self.object_tree.pack(fill="both", expand=True)

        _ACT_BG   = "#3a3a3a"
        _ACT_FG   = "#ffffff"
        _INACT_FG = "#888888"

        def _show_tree():
            self._docked_history.pack_forget()
            self.object_tree.pack(fill="both", expand=True)
            self._btn_tree.configure(
                fg_color=_ACT_BG, text_color=_ACT_FG, hover_color=_ACT_BG,
            )
            self._btn_hist.configure(
                fg_color="transparent", text_color=_INACT_FG,
                hover_color="#2d2d2d",
            )

        def _show_history():
            self.object_tree.pack_forget()
            self._docked_history.pack(fill="both", expand=True)
            self._btn_hist.configure(
                fg_color=_ACT_BG, text_color=_ACT_FG, hover_color=_ACT_BG,
            )
            self._btn_tree.configure(
                fg_color="transparent", text_color=_INACT_FG,
                hover_color="#2d2d2d",
            )

        _btn_kw = dict(
            height=28, corner_radius=0,
            font=("Segoe UI", 10), border_width=0,
        )
        self._btn_tree = ctk.CTkButton(
            _hdr, text="Object Tree", command=_show_tree,
            fg_color=_ACT_BG, text_color=_ACT_FG,
            hover_color=_ACT_BG, **_btn_kw,
        )
        self._btn_hist = ctk.CTkButton(
            _hdr, text="History", command=_show_history,
            fg_color="transparent", text_color=_INACT_FG,
            hover_color="#2d2d2d", **_btn_kw,
        )
        self._btn_tree.pack(side="left", expand=True, fill="both")
        self._btn_hist.pack(side="left", expand=True, fill="both")

        # Bottom pane: Properties (+ future tabs via same header pattern).
        _props_wrap = tk.Frame(self.right_pane, bg="#1e1e1e")

        _phdr = tk.Frame(_props_wrap, bg="#2d2d2d", height=28)
        _phdr.pack(side="top", fill="x")
        _phdr.pack_propagate(False)

        _pcontent = tk.Frame(_props_wrap, bg="#1e1e1e")
        _pcontent.pack(fill="both", expand=True)

        self.properties = PropertiesPanel(
            _pcontent, self.project,
            tool_provider=lambda: self.workspace.controls.tool,
            tool_setter=lambda t: self.workspace.controls.set_tool(t),
        )
        self.properties.pack(fill="both", expand=True)

        self._btn_props = ctk.CTkButton(
            _phdr, text="Properties",
            fg_color=_ACT_BG, text_color=_ACT_FG,
            hover_color=_ACT_BG,
            height=28, corner_radius=0,
            font=("Segoe UI", 10), border_width=0,
        )
        self._btn_props.pack(side="left", expand=True, fill="both")

        self.right_pane.add(
            _top_wrap, minsize=160, height=280, stretch="never",
        )
        self.right_pane.add(
            _props_wrap, minsize=320, stretch="always",
        )

        self.paned.add(self.palette, minsize=150, width=200, stretch="never")
        self.paned.add(self.workspace, minsize=400, stretch="always")
        self.paned.add(self.right_pane, minsize=320, width=360, stretch="never")

        bus = self.project.event_bus
        for evt in ("widget_added", "widget_removed", "property_changed",
                    "widget_z_changed", "document_resized"):
            bus.subscribe(evt, self._on_project_modified)
        bus.subscribe("history_changed", self._on_history_changed)
        bus.subscribe(
            "request_close_project",
            lambda *_a, **_k: self._on_close_project(),
        )
        bus.subscribe(
            "request_add_dialog",
            lambda *_a, **_k: self._on_add_dialog(),
        )
        bus.subscribe(
            "request_preview_dialog", self._on_preview_dialog,
        )
        bus.subscribe(
            "request_preview", lambda *_a, **_k: self._on_preview(),
        )
        bus.subscribe(
            "request_preview_active", lambda *_a, **_k: self._on_preview_active(),
        )
        bus.subscribe(
            "request_export_document", self._on_export_active_document,
        )
        self._refresh_undo_redo_buttons()

        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Layer 3 of project safety stack — periodic write-out of the
        # current state to ``<path>.autosave`` while dirty. Skipped
        # for untitled projects (no path = no autosave). Cleared on
        # explicit save.
        self._autosave = AutosaveController(
            self.project, self,
            path_provider=lambda: self._current_path,
            interval_minutes=int(
                load_settings().get("autosave_interval_minutes", 5),
            ),
        )
        self._autosave.start()

        self.after(120, self._show_startup_dialog)

    # ------------------------------------------------------------------
    # Palette collapse — Widget Box shrinks to an icon-only strip.
    # Kept here (not in Palette) because only the main PanedWindow
    # knows how to resize the pane that hosts it.
    # ------------------------------------------------------------------
    def _on_palette_collapsed(self, collapsed: bool) -> None:
        width = 48 if collapsed else 200
        minsize = 44 if collapsed else 150
        try:
            self.paned.paneconfigure(
                self.palette, width=width, minsize=minsize,
            )
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Dirty tracking
    # ------------------------------------------------------------------
    def _on_project_modified(self, *_args, **_kwargs) -> None:
        # Widget-level events fire on both fresh edits AND on undo/redo
        # replays. Undo-ing back to the saved state used to leave the
        # dirty flag on — the title still showed •, prompting a save
        # that was not needed. Dirty now tracks the history top instead
        # of raw event firings; ``_recompute_dirty`` does the match.
        self._recompute_dirty()

    def _on_history_changed(self, *_args, **_kwargs) -> None:
        self._refresh_undo_redo_buttons()
        self._recompute_dirty()

    def _recompute_dirty(self) -> None:
        """Compare the top of the undo stack to the marker captured at
        the last save. Matching marker means the project state is
        byte-identical to what was saved — flag is cleared. Anything
        else sets dirty. Handles both directions (new edits + undo
        back to saved).
        """
        history = self.project.history
        current_top = history._undo[-1] if history._undo else None
        is_dirty = current_top is not self._saved_history_marker
        if is_dirty == self._dirty:
            return
        self._dirty = is_dirty
        self._refresh_title()
        self.project.event_bus.publish("dirty_changed", is_dirty)

    def _clear_dirty(self) -> None:
        # Stamp the history top as the "saved" marker. Any subsequent
        # push / undo / redo that changes the top flips dirty back on;
        # returning to this exact top (e.g. via undo) clears it again.
        history = self.project.history
        self._saved_history_marker = (
            history._undo[-1] if history._undo else None
        )
        if self._dirty:
            self._dirty = False
            self._refresh_title()
            self.project.event_bus.publish("dirty_changed", False)

    def _refresh_title(self) -> None:
        base = "CTkMaker"
        if self._current_path:
            base += f" — {Path(self._current_path).stem}"
        elif self.project.name and self.project.name != "Untitled":
            base += f" — {self.project.name}"
        if self._dirty:
            base += " •"
        self.title(base)

    def _confirm_discard_if_dirty(self) -> bool:
        """Return True if caller may proceed (discard current work)."""
        if not self._dirty:
            return True
        self.bell()
        reply = messagebox.askyesnocancel(
            "Unsaved changes",
            "Save changes before continuing?",
            icon="warning",
            parent=self,
        )
        if reply is None:
            return False
        if reply is True:
            self._on_save()
            if self._dirty:
                return False
        else:
            # Explicit discard — drop the autosave so the next launch
            # doesn't offer to restore the changes the user just
            # decided to throw away.
            clear_autosave(self._current_path)
        return True

    def _on_window_close(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        self.destroy()

    def _show_startup_dialog(self) -> None:
        dialog = StartupDialog(self)
        self.wait_window(dialog)
        result = dialog.result
        if result is None:
            # No "untitled" fallback any more — every project lives
            # inside a folder structure, which means it must be either
            # opened from disk or freshly created via the New Project
            # dialog. Cancelling the startup dialog quits the app.
            self.destroy()
            return
        if result[0] == "open":
            self._open_path(result[1])
        elif result[0] == "new":
            _, name, w, h, path = result
            self.project.clear()
            self.project.resize_document(w, h)
            self.project.name = name
            self.project.active_document.name = name
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
            load_project(self.project, load_target)
        except ProjectLoadError as exc:
            messagebox.showerror("Open failed", str(exc), parent=self)
            return
        except Exception:
            log_error("load_project")
            messagebox.showerror("Open failed", "Unexpected error — see console.", parent=self)
            return
        self._set_current_path(path)
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
        from datetime import datetime
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
        default_dir = (
            str(Path(self._current_path).parent) if self._current_path
            else None
        )
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
        path = filedialog.askopenfilename(
            parent=self,
            title="Open project",
            filetypes=PROJECT_FILE_TYPES,
        )
        if not path:
            return
        self._open_path(path)

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
            load_project(self.project, path)
        except ProjectLoadError as exc:
            messagebox.showerror("Recover failed", str(exc), parent=self)
            return
        except Exception:
            log_error("recover_from_backup")
            messagebox.showerror(
                "Recover failed",
                "Unexpected error — see console.",
                parent=self,
            )
            return
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

    def _on_save_as(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save project as",
            defaultextension=".ctkproj",
            filetypes=PROJECT_FILE_TYPES,
        )
        if not path:
            return
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

    def _on_preview_active(self) -> None:
        doc = self.project.active_document
        if doc.is_toplevel and doc.root_widgets:
            self._on_preview_dialog(doc.id)

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

    def _on_quit(self) -> None:
        self._on_window_close()

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
        confirmed = messagebox.askyesno(
            "Remove document",
            f"Remove '{doc.name}' from the project?",
            icon="warning",
            parent=self,
        )
        if not confirmed:
            return
        from app.core.commands import DeleteDocumentCommand
        snapshot = doc.to_dict()
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
        self.project.history.push(
            DeleteDocumentCommand(snapshot, index),
        )

    def _on_preview(self) -> None:
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
            export_project(self.project, tmp_path)
        except OSError:
            log_error("preview export")
            messagebox.showerror("Preview failed", "Could not generate preview file.", parent=self)
            return
        try:
            proc = subprocess.Popen(
                [sys.executable, str(tmp_path)], cwd=str(tmp_dir),
            )
        except OSError:
            log_error("preview subprocess")
            messagebox.showerror("Preview failed", "Could not launch Python.", parent=self)
            return
        self._main_preview_proc = proc

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
            )
        except OSError:
            log_error("preview dialog export")
            messagebox.showerror(
                "Preview failed",
                "Could not generate preview file.",
                parent=self,
            )
            return
        try:
            proc = subprocess.Popen(
                [sys.executable, str(tmp_path)], cwd=str(tmp_dir),
            )
        except OSError:
            log_error("preview dialog subprocess")
            messagebox.showerror(
                "Preview failed", "Could not launch Python.",
                parent=self,
            )
            return
        self._dialog_preview_procs[doc_id] = proc

    def _on_appearance_change(self) -> None:
        mode = self._appearance_var.get()
        ctk.set_appearance_mode(mode.lower())
        save_setting("appearance_mode", mode)

    def _on_widget_docs(self) -> None:
        try:
            webbrowser.open(GITHUB_DOCS_URL)
        except Exception:
            log_error("widget docs open")

    def _on_about(self) -> None:
        from app.ui.dialogs import AboutDialog
        AboutDialog(self, app_version="v0.0.20")

    def _on_inspect_widget(self) -> None:
        # Reuse a single Toplevel — clicking the menu while it's open
        # raises it instead of stacking duplicate windows.
        win = getattr(self, "_widget_inspector_win", None)
        if win is not None and win.winfo_exists():
            try:
                win.deiconify()
                win.lift()
                win.focus_set()
            except tk.TclError:
                self._widget_inspector_win = None
            else:
                return
        from app.ui.widget_inspector_window import WidgetInspectorWindow
        self._widget_inspector_win = WidgetInspectorWindow(self)

    def _on_toggle_object_tree(self) -> None:
        """Open/close Object Tree window in sync with its View-menu check.

        Driven by `self._object_tree_var`. When the var is toggled by
        the menu item or F8 shortcut, we open or close the window to
        match. When the user closes the window manually, the window's
        on-close callback flips the var back to False.
        """
        want_open = bool(self._object_tree_var.get())
        alive = (
            self._object_tree_window is not None
            and self._object_tree_window.winfo_exists()
        )
        if want_open and not alive:
            self._object_tree_window = ObjectTreeWindow(
                self, self.project,
                on_close=self._on_object_tree_closed,
            )
        elif not want_open and alive:
            try:
                self._object_tree_window.destroy()
            except tk.TclError:
                pass
            self._object_tree_window = None

    def _on_object_tree_closed(self) -> None:
        self._object_tree_window = None
        self._object_tree_var.set(False)

    def _on_f8_object_tree(self) -> None:
        self._object_tree_var.set(not self._object_tree_var.get())
        self._on_toggle_object_tree()

    def _on_toggle_history_window(self) -> None:
        want_open = bool(self._history_var.get())
        alive = (
            self._history_window is not None
            and self._history_window.winfo_exists()
        )
        if want_open and not alive:
            self._history_window = HistoryWindow(
                self, self.project,
                on_close=self._on_history_window_closed,
            )
        elif not want_open and alive:
            try:
                self._history_window.destroy()
            except tk.TclError:
                pass
            self._history_window = None

    def _on_history_window_closed(self) -> None:
        self._history_window = None
        self._history_var.set(False)

    def _on_f9_history_window(self) -> None:
        self._history_var.set(not self._history_var.get())
        self._on_toggle_history_window()

    def _on_toggle_project_window(self) -> None:
        want_open = bool(self._project_var.get())
        alive = (
            self._project_window is not None
            and self._project_window.winfo_exists()
        )
        if want_open and not alive:
            self._project_window = ProjectWindow(
                self, self.project,
                path_provider=lambda: self._current_path,
                on_close=self._on_project_window_closed,
            )
        elif not want_open and alive:
            try:
                self._project_window.destroy()
            except tk.TclError:
                pass
            self._project_window = None

    def _on_project_window_closed(self) -> None:
        self._project_window = None
        self._project_var.set(False)

    def _on_f10_project_window(self) -> None:
        self._project_var.set(not self._project_var.get())
        self._on_toggle_project_window()

    def _on_run_script(self) -> None:
        """Pick any local .py file and run it as a subprocess. Useful
        for quickly testing scripts the user already exported (or any
        other Python file) without leaving the builder. The chosen
        directory is remembered on the settings file so the next pick
        starts where the previous one left off.
        """
        from app.core.settings import load_settings, save_setting
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

    def _on_export(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export to Python",
            defaultextension=".py",
            filetypes=[("Python", "*.py"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            export_project(self.project, path)
        except OSError:
            log_error("export_project")
            messagebox.showerror("Export failed", "Could not write the file.", parent=self)
            return
        messagebox.showinfo("Export", f"Saved to:\n{path}", parent=self)

    def _on_export_active_document(
        self, doc_id: str | None = None,
    ) -> None:
        """Export only ONE document (Main Window or Dialog) as a
        standalone runnable ``.py``. The target class subclasses
        ``ctk.CTk`` regardless of the source doc's ``is_toplevel``
        flag, so the output file runs on its own without wiring into
        the rest of the project.

        ``doc_id`` defaults to the currently active document — the
        File menu entry uses that default. The chrome per-dialog
        Export button passes an explicit id through the
        ``request_export_document`` event bus.
        """
        target_id = doc_id or self.project.active_document_id
        doc = self.project.get_document(target_id)
        if doc is None:
            return
        default_name = f"{doc.name or 'document'}.py"
        path = filedialog.asksaveasfilename(
            parent=self,
            title=f"Export '{doc.name}' to Python",
            defaultextension=".py",
            initialfile=default_name,
            filetypes=[("Python", "*.py"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            export_project(
                self.project, path, single_document_id=target_id,
            )
        except OSError:
            log_error("export_active_document")
            messagebox.showerror(
                "Export failed", "Could not write the file.",
                parent=self,
            )
            return
        messagebox.showinfo(
            "Export", f"Saved to:\n{path}", parent=self,
        )

    # ------------------------------------------------------------------
    # Undo / redo
    # ------------------------------------------------------------------
    def _on_undo(self) -> str | None:
        # Always route Ctrl+Z through the project history, even when
        # an Entry widget has focus — the name entry's edits are
        # already tracked as coalesced RenameCommands, so app-level
        # undo is the right behaviour everywhere.
        self.project.history.undo()
        return "break"

    def _on_redo(self) -> str | None:
        self.project.history.redo()
        return "break"


    def _refresh_undo_redo_buttons(self) -> None:
        if not hasattr(self, "toolbar"):
            return
        self.toolbar.set_undo_enabled(self.project.history.can_undo())
        self.toolbar.set_redo_enabled(self.project.history.can_redo())


    def _on_theme_toggle(self) -> None:
        current = self._appearance_var.get()
        nxt = "Light" if current == "Dark" else "Dark"
        self._appearance_var.set(nxt)
        self._on_appearance_change()

    def _set_centered_geometry(self, desired_w: int, desired_h: int) -> None:
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(desired_w, sw - 80)
        h = min(desired_h, sh - 120)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2 - 20)
        self.geometry(f"{w}x{h}+{x}+{y}")
