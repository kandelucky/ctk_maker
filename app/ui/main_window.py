import subprocess
import sys
import tempfile
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app.core.logger import log_error
from app.core.project import Project
from app.core.recent_files import add_recent, clear_recent, load_recent
from app.core.settings import load_settings, save_setting
from app.io.code_exporter import export_project
from app.io.project_loader import ProjectLoadError, load_project
from app.io.project_saver import save_project
from app.ui.dialogs import NewProjectSizeDialog
from app.ui.history_window import HistoryWindow
from app.ui.icons import load_tk_icon
from app.ui.object_tree_window import ObjectTreeWindow
from app.ui.palette import Palette
from app.ui.properties_panel_v2 import PropertiesPanelV2 as PropertiesPanel
from app.ui.startup_dialog import StartupDialog
from app.ui.toolbar import Toolbar
from app.ui.workspace import Workspace

PROJECT_FILE_TYPES = [("CTk Builder project", "*.ctkproj"), ("All files", "*.*")]

MENU_BG = "#2d2d30"
MENU_FG = "#cccccc"
MENU_ACTIVE_BG = "#094771"
MENU_ACTIVE_FG = "#ffffff"
MENU_DISABLED_FG = "#888888"
MENU_FONT = ("Segoe UI", 11)
MENU_ICON_SIZE = 18

MENU_STYLE = dict(
    bg=MENU_BG,
    fg=MENU_FG,
    activebackground=MENU_ACTIVE_BG,
    activeforeground=MENU_ACTIVE_FG,
    disabledforeground=MENU_DISABLED_FG,
    bd=0,
    borderwidth=0,
    activeborderwidth=0,
    relief="flat",
    font=MENU_FONT,
)

APPEARANCE_MODES = ["Light", "Dark", "System"]

ABOUT_TEXT = (
    "CTk Visual Builder\n"
    "v0.0.7\n\n"
    "Drag-and-drop designer for CustomTkinter that exports clean Python code.\n\n"
    "Built with:\n"
    "  • CustomTkinter (MIT)\n"
    "  • Lucide Icons (MIT)\n"
    "  • Pillow\n"
    "  • ctk-tint-color-picker"
)

GITHUB_DOCS_URL = "https://github.com/kandelucky/ctk_visual_builder/blob/main/docs/widgets/README.md"


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CTk Visual Builder")
        self.minsize(900, 600)
        self._set_centered_geometry(1280, 800)

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
        self._object_tree_window: ObjectTreeWindow | None = None
        self._object_tree_var = tk.BooleanVar(value=True)
        self._history_window: HistoryWindow | None = None
        self._history_var = tk.BooleanVar(value=False)

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

        self.palette = Palette(self.paned, self.project)
        self.workspace = Workspace(self.paned, self.project)
        self.properties = PropertiesPanel(self.paned, self.project)

        self.paned.add(self.palette, minsize=150, width=200, stretch="never")
        self.paned.add(self.workspace, minsize=400, stretch="always")
        self.paned.add(self.properties, minsize=320, width=340, stretch="never")

        bus = self.project.event_bus
        for evt in ("widget_added", "widget_removed", "property_changed",
                    "widget_z_changed", "document_resized"):
            bus.subscribe(evt, self._on_project_modified)
        bus.subscribe("history_changed", self._on_history_changed)
        self._refresh_undo_redo_buttons()

        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        self.after(120, self._show_startup_dialog)
        self.after(250, self._auto_open_object_tree)

    # ------------------------------------------------------------------
    # Non-Latin keyboard layout fallback
    # ------------------------------------------------------------------
    def _on_control_keypress(self, event) -> str | None:
        # If the keysym is already the Latin letter, tk's default
        # binding handled (or will handle) the shortcut — don't double.
        latin = event.keysym.lower()
        if latin in ("v", "c", "x", "a", "s", "n", "o", "w", "q", "r", "z", "y"):
            return None
        kc = event.keycode
        widget = event.widget
        if kc == 86:  # V
            widget.event_generate("<<Paste>>")
            return "break"
        if kc == 67:  # C
            widget.event_generate("<<Copy>>")
            return "break"
        if kc == 88:  # X
            widget.event_generate("<<Cut>>")
            return "break"
        if kc == 65:  # A
            try:
                widget.event_generate("<<SelectAll>>")
            except tk.TclError:
                pass
            return "break"
        if kc == 83:  # S
            self._on_save()
            return "break"
        if kc == 78:  # N
            self._on_new()
            return "break"
        if kc == 79:  # O
            self._on_open()
            return "break"
        if kc == 87:  # W
            self._on_close_project()
            return "break"
        if kc == 81:  # Q
            self._on_quit()
            return "break"
        if kc == 82:  # R
            self._on_preview()
            return "break"
        if kc == 90:  # Z
            if event.state & 0x0001:  # Shift → redo
                self._on_redo()
            else:
                self._on_undo()
            return "break"
        if kc == 89:  # Y
            self._on_redo()
            return "break"
        return None

    # ------------------------------------------------------------------
    # Dirty tracking
    # ------------------------------------------------------------------
    def _on_project_modified(self, *_args, **_kwargs) -> None:
        if not self._dirty:
            self._dirty = True
            self._refresh_title()

    def _clear_dirty(self) -> None:
        if self._dirty:
            self._dirty = False
            self._refresh_title()

    def _refresh_title(self) -> None:
        base = "CTk Visual Builder"
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
            return
        if result[0] == "open":
            self._open_path(result[1])
        elif result[0] == "new":
            _, name, w, h, path = result
            self.project.clear()
            self.project.resize_document(w, h)
            self.project.name = name
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
            self._set_current_path(path)

    # ------------------------------------------------------------------
    # Menubar
    # ------------------------------------------------------------------
    def _menu_icon(self, name: str):
        icon = load_tk_icon(name, size=MENU_ICON_SIZE)
        if icon is not None:
            self._menu_icons.append(icon)  # prevent GC
        return icon

    def _add_cmd(self, menu: tk.Menu, label: str, command, icon: str | None = None, accelerator: str | None = None) -> None:
        kwargs = dict(label=label, command=command)
        if accelerator:
            kwargs["accelerator"] = accelerator
        img = self._menu_icon(icon) if icon else None
        if img is not None:
            kwargs["image"] = img
            kwargs["compound"] = "left"
        menu.add_command(**kwargs)

    def _add_cascade(self, parent: tk.Menu, label: str, submenu: tk.Menu, icon: str | None = None) -> None:
        kwargs = dict(label=label, menu=submenu)
        img = self._menu_icon(icon) if icon else None
        if img is not None:
            kwargs["image"] = img
            kwargs["compound"] = "left"
        parent.add_cascade(**kwargs)

    def _build_menubar(self) -> None:
        self._menu_icons: list = []
        menubar = tk.Menu(self, **MENU_STYLE)

        # ---- File ----
        file_menu = tk.Menu(menubar, tearoff=0, **MENU_STYLE)
        self._add_cmd(file_menu, "New...", self._on_new, icon="file-plus", accelerator="Ctrl+N")
        self._add_cmd(file_menu, "Open...", self._on_open, icon="folder-open", accelerator="Ctrl+O")

        self._recent_menu = tk.Menu(file_menu, tearoff=0, **MENU_STYLE)
        self._add_cascade(file_menu, "Recent Forms", self._recent_menu, icon="history")
        self._rebuild_recent_menu()

        file_menu.add_separator()
        self._add_cmd(file_menu, "Save", self._on_save, icon="save", accelerator="Ctrl+S")
        self._add_cmd(file_menu, "Save As...", self._on_save_as, icon="save", accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        self._add_cmd(file_menu, "Export to Python...", self._on_export, icon="file-code")
        file_menu.add_separator()
        self._add_cmd(file_menu, "Close", self._on_close_project, icon="x", accelerator="Ctrl+W")
        self._add_cmd(file_menu, "Quit", self._on_quit, icon="log-out", accelerator="Ctrl+Q")
        menubar.add_cascade(label="File", menu=file_menu)

        # ---- Edit ----
        # postcommand recomputes enabled/disabled state just before
        # the menu drops open so it always reflects current selection,
        # clipboard, and history state.
        edit_menu = tk.Menu(
            menubar, tearoff=0,
            postcommand=self._refresh_edit_menu_state,
            **MENU_STYLE,
        )
        self._edit_menu = edit_menu
        self._add_cmd(
            edit_menu, "Undo", self._on_undo, accelerator="Ctrl+Z",
        )
        self._add_cmd(
            edit_menu, "Redo", self._on_redo, accelerator="Ctrl+Y",
        )
        edit_menu.add_separator()
        self._add_cmd(
            edit_menu, "Copy", self._on_menu_copy,
            accelerator="Ctrl+C",
        )
        self._add_cmd(
            edit_menu, "Paste", self._on_menu_paste,
            accelerator="Ctrl+V",
        )
        self._add_cmd(
            edit_menu, "Delete", self._on_menu_delete,
            accelerator="Del",
        )
        edit_menu.add_separator()
        self._add_cmd(
            edit_menu, "Select All", self._on_menu_select_all,
            accelerator="Ctrl+A",
        )
        edit_menu.add_separator()
        self._add_cmd(
            edit_menu, "Bring to Front", self._on_menu_bring_to_front,
        )
        self._add_cmd(
            edit_menu, "Send to Back", self._on_menu_send_to_back,
        )
        menubar.add_cascade(label="Edit", menu=edit_menu)

        # ---- Form ----
        form_menu = tk.Menu(menubar, tearoff=0, **MENU_STYLE)
        self._add_cmd(form_menu, "Preview", self._on_preview, icon="play", accelerator="Ctrl+R")
        menubar.add_cascade(label="Form", menu=form_menu)

        # ---- View ----
        view_menu = tk.Menu(menubar, tearoff=0, **MENU_STYLE)
        view_menu.add_checkbutton(
            label="Object Tree",
            variable=self._object_tree_var,
            command=self._on_toggle_object_tree,
            accelerator="F8",
        )
        view_menu.add_checkbutton(
            label="History",
            variable=self._history_var,
            command=self._on_toggle_history_window,
            accelerator="F9",
        )
        menubar.add_cascade(label="View", menu=view_menu)

        # ---- Settings ----
        settings_menu = tk.Menu(menubar, tearoff=0, **MENU_STYLE)
        appearance_menu = tk.Menu(settings_menu, tearoff=0, **MENU_STYLE)
        for mode in APPEARANCE_MODES:
            appearance_menu.add_radiobutton(
                label=mode,
                variable=self._appearance_var,
                value=mode,
                command=self._on_appearance_change,
            )
        self._add_cascade(settings_menu, "Appearance Mode", appearance_menu, icon="palette")
        menubar.add_cascade(label="Settings", menu=settings_menu)

        # ---- Help ----
        help_menu = tk.Menu(menubar, tearoff=0, **MENU_STYLE)
        self._add_cmd(help_menu, "Widget Documentation", self._on_widget_docs, icon="book-open")
        help_menu.add_separator()
        self._add_cmd(help_menu, "About...", self._on_about, icon="info")
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-n>", lambda e: self._on_new())
        self.bind("<Control-o>", lambda e: self._on_open())
        self.bind("<Control-s>", lambda e: self._on_save())
        self.bind("<Control-Shift-S>", lambda e: self._on_save_as())
        self.bind("<Control-r>", lambda e: self._on_preview())
        self.bind("<Control-w>", lambda e: self._on_close_project())
        self.bind("<F8>", lambda e: self._on_f8_object_tree())
        self.bind("<F9>", lambda e: self._on_f9_history_window())
        self.bind("<Control-q>", lambda e: self._on_quit())
        # bind_all so undo/redo works when the Object Tree toplevel
        # has focus too — regular `self.bind` only fires for the
        # main window's widget tree.
        self.bind_all("<Control-z>", lambda e: self._on_undo())
        self.bind_all("<Control-y>", lambda e: self._on_redo())
        self.bind_all("<Control-Shift-Z>", lambda e: self._on_redo())

    def _rebuild_recent_menu(self) -> None:
        self._recent_menu.delete(0, "end")
        paths = load_recent()
        if not paths:
            self._recent_menu.add_command(label="(empty)", state="disabled")
        else:
            for p in paths:
                label = Path(p).name
                self._recent_menu.add_command(
                    label=label,
                    command=lambda path=p: self._open_path(path),
                )
        self._recent_menu.add_separator()
        self._recent_menu.add_command(label="Clear Menu", command=self._on_clear_recent)

    def _on_clear_recent(self) -> None:
        clear_recent()
        self._rebuild_recent_menu()

    # ------------------------------------------------------------------
    # Current-path tracking
    # ------------------------------------------------------------------
    def _set_current_path(self, path: str | None) -> None:
        self._current_path = path
        self._clear_dirty()
        if path:
            add_recent(path)
            self._rebuild_recent_menu()
        self._refresh_title()

    def _open_path(self, path: str) -> None:
        if not Path(path).exists():
            messagebox.showerror("Open failed", f"File not found:\n{path}", parent=self)
            return
        try:
            load_project(self.project, path)
        except ProjectLoadError as exc:
            messagebox.showerror("Open failed", str(exc), parent=self)
            return
        except Exception:
            log_error("load_project")
            messagebox.showerror("Open failed", "Unexpected error — see console.", parent=self)
            return
        self._set_current_path(path)

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

    def _on_save(self) -> None:
        if self._current_path:
            try:
                save_project(self.project, self._current_path)
            except OSError:
                log_error("save_project")
                messagebox.showerror("Save failed", "Could not write the project file.", parent=self)
                return
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
        self._set_current_path(path)

    def _on_close_project(self) -> None:
        self._on_new()

    def _on_quit(self) -> None:
        self._on_window_close()

    def _on_preview(self) -> None:
        if not self.project.root_widgets:
            messagebox.showinfo(
                "Preview",
                "Nothing to preview — workspace is empty.",
                parent=self,
            )
            return
        tmp_dir = Path(tempfile.mkdtemp(prefix="ctk_preview_"))
        tmp_path = tmp_dir / "preview.py"
        try:
            export_project(self.project, tmp_path)
        except OSError:
            log_error("preview export")
            messagebox.showerror("Preview failed", "Could not generate preview file.", parent=self)
            return
        try:
            subprocess.Popen([sys.executable, str(tmp_path)], cwd=str(tmp_dir))
        except OSError:
            log_error("preview subprocess")
            messagebox.showerror("Preview failed", "Could not launch Python.", parent=self)

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
        messagebox.showinfo("About CTk Visual Builder", ABOUT_TEXT, parent=self)

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

    def _auto_open_object_tree(self) -> None:
        """Open Object Tree on launch if the checkbox says it should be
        visible. Runs after the startup dialog so the main window has
        its final position (the tree window auto-places relative to
        the main window's top-right)."""
        if self._object_tree_var.get():
            self._on_toggle_object_tree()

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

    # ------------------------------------------------------------------
    # Undo / redo
    # ------------------------------------------------------------------
    def _on_undo(self) -> str | None:
        if isinstance(self.focus_get(), (tk.Entry, tk.Text)):
            return None
        self.project.history.undo()
        return "break"

    def _on_redo(self) -> str | None:
        if isinstance(self.focus_get(), (tk.Entry, tk.Text)):
            return None
        self.project.history.redo()
        return "break"

    def _on_history_changed(self, *_args, **_kwargs) -> None:
        self._refresh_undo_redo_buttons()

    def _refresh_undo_redo_buttons(self) -> None:
        if not hasattr(self, "toolbar"):
            return
        self.toolbar.set_undo_enabled(self.project.history.can_undo())
        self.toolbar.set_redo_enabled(self.project.history.can_redo())

    def _refresh_edit_menu_state(self) -> None:
        """Dims menu entries whose action can't run right now.

        Windows tk.Menu draws a nasty emboss/shadow effect on
        ``state=disabled`` entries, so we keep them enabled and only
        swap the foreground colour. The command callbacks themselves
        no-op when the action can't run, and the inert-color rows
        visually communicate 'not available'.
        """
        menu = getattr(self, "_edit_menu", None)
        if menu is None:
            return
        has_selection = bool(self.project.selected_ids)
        has_clipboard = bool(self.project.clipboard)
        has_any = any(True for _ in self.project.iter_all_widgets())
        states = {
            "Undo": self.project.history.can_undo(),
            "Redo": self.project.history.can_redo(),
            "Copy": has_selection,
            "Paste": has_clipboard,
            "Delete": has_selection,
            "Select All": has_any,
            "Bring to Front": has_selection,
            "Send to Back": has_selection,
        }
        try:
            last = menu.index("end")
        except tk.TclError:
            return
        if last is None:
            return
        for i in range(last + 1):
            try:
                if menu.type(i) != "command":
                    continue
                label = menu.entrycget(i, "label")
            except tk.TclError:
                continue
            if label in states:
                menu.entryconfigure(
                    i,
                    foreground=MENU_FG if states[label] else MENU_DISABLED_FG,
                )

    # ------------------------------------------------------------------
    # Edit menu dispatchers — route to project methods so the same
    # action works regardless of which window has focus.
    # ------------------------------------------------------------------
    def _on_menu_copy(self) -> None:
        ids = self.project.selected_ids
        if ids:
            self.project.copy_to_clipboard(ids)

    def _on_menu_paste(self) -> None:
        if not self.project.clipboard:
            return
        # Paste into the currently selected container if one is, else
        # as a sibling of the selected leaf, else top level.
        parent_id: str | None = None
        primary = self.project.selected_id
        if primary is not None:
            from app.widgets.registry import get_descriptor
            node = self.project.get_widget(primary)
            if node is not None:
                descriptor = get_descriptor(node.widget_type)
                if descriptor is not None and getattr(
                    descriptor, "is_container", False,
                ):
                    parent_id = primary
                elif node.parent is not None:
                    parent_id = node.parent.id
        self.project.paste_from_clipboard(parent_id=parent_id)

    def _on_menu_delete(self) -> None:
        sid = self.project.selected_id
        if sid is None:
            return
        node = self.project.get_widget(sid)
        if node is None:
            return
        from app.core.commands import DeleteWidgetCommand
        from app.widgets.registry import get_descriptor
        descriptor = get_descriptor(node.widget_type)
        type_label = (
            descriptor.display_name if descriptor else node.widget_type
        )
        confirmed = messagebox.askyesno(
            title="Delete widget",
            message=f"Delete this {type_label}?",
            icon="warning",
            parent=self,
        )
        if not confirmed:
            return
        snapshot = node.to_dict()
        parent_id = node.parent.id if node.parent is not None else None
        siblings = (
            node.parent.children if node.parent is not None
            else self.project.root_widgets
        )
        try:
            index = siblings.index(node)
        except ValueError:
            index = len(siblings)
        self.project.remove_widget(sid)
        self.project.history.push(
            DeleteWidgetCommand(snapshot, parent_id, index),
        )

    def _on_menu_select_all(self) -> None:
        all_ids = {node.id for node in self.project.iter_all_widgets()}
        if not all_ids:
            return
        primary = self.project.selected_id or next(iter(all_ids))
        self.project.set_multi_selection(all_ids, primary=primary)

    def _on_menu_bring_to_front(self) -> None:
        sid = self.project.selected_id
        if sid is not None:
            self.project.bring_to_front(sid)

    def _on_menu_send_to_back(self) -> None:
        sid = self.project.selected_id
        if sid is not None:
            self.project.send_to_back(sid)

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
