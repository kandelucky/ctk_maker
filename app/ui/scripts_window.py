"""Scripts panel — per-page library `.py` files.

Shows the user's library scripts (helpers, api, sub-packages) that
live under ``<project>/assets/scripts/<active_page>/`` and are NOT
per-window behavior files. Lets the user add / rename / delete / open
those files without leaving the builder.

Mirrors ``HistoryWindow`` / ``VariablesWindow``: ``ScriptsPanel`` is
the embeddable ``CTkFrame``; ``ScriptsWindow`` is the floating
``ManagedToplevel`` wrapper opened by F6 / View → Scripts.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from app.core.logger import log_error
from app.core.settings import load_settings
from app.io.library_scripts import (
    LibraryEntry,
    create_library_script,
    list_library_scripts,
    recycle_library_script,
    rename_library_script,
    script_absolute_path,
)
from app.io.scripts import launch_editor, resolve_project_root_for_editor
from app.ui import style
from app.ui.managed_window import ManagedToplevel
from app.ui.system_fonts import ui_font

if TYPE_CHECKING:
    from app.core.project import Project

BG = style.BG
PANEL_BG = style.PANEL_BG
TOOLBAR_BG = style.TOOLBAR_BG
TREE_BG = style.TREE_BG
TREE_FG = style.TREE_FG
TREE_SELECTED_BG = style.TREE_SELECTED_BG
TREE_HEADING_BG = style.TREE_HEADING_BG
TREE_HEADING_FG = style.TREE_HEADING_FG
EMPTY_FG = style.EMPTY_FG
SECONDARY_BG = style.SECONDARY_BG
SECONDARY_HOVER = style.SECONDARY_HOVER
DANGER_HOVER = style.DANGER_HOVER
BUTTON_RADIUS = style.BUTTON_RADIUS

DIALOG_W = 360
DIALOG_H = 440
TREE_ROW_HEIGHT = style.TREE_ROW_HEIGHT
TREE_FONT_SIZE = style.TREE_FONT_SIZE

EMPTY_TEXT = "No library scripts in this page yet — click + Add to create one"
EMPTY_NO_PROJECT = "Save the project first to add library scripts"

FOLDER_ICON = "📁"
FILE_ICON = "📄"
BEHAVIOR_ICON = "🪟"
BEHAVIOR_FG = "#e8b86d"


class ScriptsPanel(ctk.CTkFrame):
    """Embeddable list of library scripts for the active page."""

    def __init__(
        self,
        parent,
        project: "Project",
        path_provider: Callable[[], str | None],
    ):
        super().__init__(parent, fg_color=PANEL_BG, corner_radius=0, border_width=0)
        self.project = project
        self._path_provider = path_provider
        self._build()
        self.after(0, self.refresh)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self._build_toolbar()
        self._build_tree()

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=TOOLBAR_BG, corner_radius=0, height=36)
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)
        ctk.CTkButton(
            bar, text="+ Add script", width=100, height=24,
            corner_radius=BUTTON_RADIUS,
            fg_color=SECONDARY_BG, hover_color=SECONDARY_HOVER,
            font=ui_font(11),
            command=self._on_add_file,
        ).pack(side="left", padx=(8, 4), pady=6)

    def _build_tree(self) -> None:
        wrapper = ctk.CTkFrame(self, fg_color=TREE_BG, corner_radius=0)
        wrapper.pack(side="top", fill="both", expand=True)

        style_name = "Scripts.Treeview"
        ttk_style = ttk.Style(self)
        ttk_style.configure(
            style_name,
            background=TREE_BG,
            fieldbackground=TREE_BG,
            foreground=TREE_FG,
            rowheight=TREE_ROW_HEIGHT,
            borderwidth=0,
            font=ui_font(TREE_FONT_SIZE),
        )
        ttk_style.map(
            style_name,
            background=[("selected", TREE_SELECTED_BG)],
            foreground=[("selected", "#ffffff")],
        )

        self.tree = ttk.Treeview(
            wrapper,
            columns=(),
            show="tree",
            style=style_name,
            selectmode="browse",
        )
        self.tree.tag_configure("empty", foreground=EMPTY_FG)
        self.tree.tag_configure("folder", foreground="#9cc7ff")
        self.tree.tag_configure("behavior", foreground=BEHAVIOR_FG)
        self.tree.bind("<Double-1>", self._on_double_click, add="+")
        self.tree.bind("<Return>", self._on_double_click, add="+")
        self.tree.bind("<Button-3>", self._on_right_click, add="+")
        self.tree.bind("<F2>", self._on_rename_shortcut, add="+")
        self.tree.bind("<Delete>", self._on_delete_shortcut, add="+")

        vsb = ctk.CTkScrollbar(
            wrapper, orientation="vertical",
            command=self.tree.yview,
            width=10, corner_radius=4,
            fg_color="transparent",
            button_color="#3a3a3a",
            button_hover_color="#4a4a4a",
        )
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    def _current_path(self) -> str | None:
        try:
            return self._path_provider()
        except Exception:
            return None

    def _window_names(self) -> list[str]:
        try:
            return [
                getattr(d, "name", "") or ""
                for d in (self.project.documents or [])
            ]
        except Exception:
            return []

    def refresh(self) -> None:
        for iid in self.tree.get_children(""):
            self.tree.delete(iid)
        path = self._current_path()
        if not path:
            self.tree.insert(
                "", "end", iid="__empty__",
                text=EMPTY_NO_PROJECT, tags=("empty",),
            )
            return
        entries = list_library_scripts(path, self._window_names())
        if not entries:
            self.tree.insert(
                "", "end", iid="__empty__",
                text=EMPTY_TEXT, tags=("empty",),
            )
            return
        self._populate("", entries)

    def _populate(self, parent_iid: str, entries: list[LibraryEntry]) -> None:
        for entry in entries:
            if entry.is_folder:
                tags: tuple[str, ...] = ("folder",)
                label = entry.name
            elif entry.is_behavior:
                tags = ("behavior",)
                label = f"{entry.name}  (window)"
            else:
                tags = ()
                label = entry.name
            iid = self.tree.insert(
                parent_iid, "end",
                iid=entry.rel_path,
                text=f"  {label}",
                tags=tags,
                open=True,
            )
            if entry.is_folder and entry.children:
                self._populate(iid, entry.children)

    # ------------------------------------------------------------------
    # Toolbar actions
    # ------------------------------------------------------------------
    def _on_add_file(self) -> None:
        path = self._current_path()
        if not path:
            messagebox.showwarning(
                "Save first",
                "Save the project before adding library scripts.",
                parent=self,
            )
            return
        rel = simpledialog.askstring(
            "Add library script",
            "Filename (e.g. helpers.py or services/auth.py):",
            parent=self,
        )
        if not rel:
            return
        result = create_library_script(path, rel, self._window_names())
        if result is None:
            messagebox.showerror(
                "Add failed",
                "Could not create the script.\n\n"
                "Possible reasons:\n"
                "• File already exists\n"
                "• Name clashes with a window's behavior file\n"
                "• Invalid path (absolute / .. traversal)",
                parent=self,
            )
            return
        self.refresh()
        try:
            self.tree.selection_set(result.relative_to(result.parent.parent).as_posix())
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Row actions
    # ------------------------------------------------------------------
    def _selected_rel_path(self) -> str | None:
        sel = self.tree.selection()
        if not sel:
            return None
        iid = sel[0]
        if iid.startswith("__"):
            return None
        return iid

    def _on_double_click(self, _event=None) -> None:
        rel = self._selected_rel_path()
        if not rel:
            return
        self._open_in_editor(rel)

    def _on_rename_shortcut(self, _event=None) -> None:
        sel = self.tree.selection()
        if sel and self.tree.tag_has("behavior", sel[0]):
            return
        self._rename_selected()

    def _on_delete_shortcut(self, _event=None) -> None:
        sel = self.tree.selection()
        if sel and self.tree.tag_has("behavior", sel[0]):
            return
        self._delete_selected()

    def _on_right_click(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid or iid.startswith("__"):
            return
        self.tree.selection_set(iid)
        menu = tk.Menu(self, **_menu_style())
        is_folder = bool(self.tree.tag_has("folder", iid))
        is_behavior = bool(self.tree.tag_has("behavior", iid))
        if not is_folder:
            menu.add_command(label="Open in editor", command=self._open_selected_in_editor)
        # Behavior files are managed via the window's chrome (rename =
        # window rename, delete = window delete). The icon + ``(window)``
        # suffix already signal this; we just skip the rename / delete
        # rows here to avoid orphaning the binding.
        if not is_behavior and not is_folder:
            menu.add_separator()
            menu.add_command(label="Rename…", command=self._rename_selected)
            menu.add_command(label="Delete", command=self._delete_selected)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_selected_in_editor(self) -> None:
        rel = self._selected_rel_path()
        if rel:
            self._open_in_editor(rel)

    def _open_in_editor(self, rel: str) -> None:
        path = self._current_path()
        if not path:
            return
        abs_path = script_absolute_path(path, rel)
        if abs_path is None:
            return
        try:
            editor_command = load_settings().get("editor_command")
            launch_editor(
                abs_path,
                editor_command=editor_command,
                project_root=resolve_project_root_for_editor(self.project),
            )
        except OSError:
            log_error("ScriptsPanel open_in_editor")

    def _rename_selected(self) -> None:
        rel = self._selected_rel_path()
        if not rel:
            return
        path = self._current_path()
        if not path:
            return
        old_name = rel.rsplit("/", 1)[-1]
        parent_dir = rel.rsplit("/", 1)[0] if "/" in rel else ""
        new_name = simpledialog.askstring(
            "Rename",
            "New name:",
            initialvalue=old_name,
            parent=self,
        )
        if not new_name or new_name == old_name:
            return
        new_rel = (
            f"{parent_dir}/{new_name}" if parent_dir else new_name
        )
        result = rename_library_script(
            path, rel, new_rel, self._window_names(),
        )
        if result is None:
            messagebox.showerror(
                "Rename failed",
                "Could not rename.\n\n"
                "Possible reasons:\n"
                "• Target already exists\n"
                "• Name clashes with a window's behavior file\n"
                "• Invalid name",
                parent=self,
            )
            return
        self.refresh()

    def _delete_selected(self) -> None:
        rel = self._selected_rel_path()
        if not rel:
            return
        path = self._current_path()
        if not path:
            return
        if not messagebox.askyesno(
            "Delete",
            f"Send '{rel}' to the recycle bin?",
            parent=self,
        ):
            return
        ok = recycle_library_script(path, rel)
        if not ok:
            messagebox.showerror(
                "Delete failed",
                "Could not send the file to the recycle bin.",
                parent=self,
            )
            return
        self.refresh()


def _menu_style() -> dict:
    """Match the dark popup menu styling used elsewhere — keeps the
    right-click menu visually consistent with the toolbar / file menu.
    """
    return {
        "bg": "#2d2d30",
        "fg": "#cccccc",
        "activebackground": TREE_SELECTED_BG,
        "activeforeground": "#ffffff",
        "bd": 0,
        "tearoff": 0,
        "font": ui_font(11),
    }


class ScriptsWindow(ManagedToplevel):
    """Floating Scripts panel (F6)."""

    window_key = "scripts"
    window_title = "Scripts"
    default_size = (DIALOG_W, DIALOG_H)
    min_size = (260, 240)
    fg_color = BG

    def __init__(
        self,
        parent,
        project: "Project",
        path_provider: Callable[[], str | None],
        on_close: Callable[[], None] | None = None,
    ):
        self.project = project
        self._path_provider = path_provider
        super().__init__(parent)
        self.set_on_close(on_close)

    def build_content(self) -> ctk.CTkFrame:
        self.panel = ScriptsPanel(self, self.project, self._path_provider)
        # Auto-refresh whenever this window regains focus — picks up
        # any files created / renamed / deleted via an external editor
        # (VS Code Save As, Notepad++, file explorer, etc.) without a
        # dedicated refresh button.
        self.bind("<FocusIn>", self._on_focus_in, add="+")
        return self.panel

    def _on_focus_in(self, event) -> None:
        # FocusIn fires for every descendant getting focus too — only
        # refresh when the toplevel itself takes focus (cheap guard).
        if event.widget is self:
            try:
                self.panel.refresh()
            except (AttributeError, tk.TclError):
                pass

    def default_offset(self, parent) -> tuple[int, int]:
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            return (px + pw - self.default_size[0] - 30, py + 200)
        except tk.TclError:
            return (140, 140)

    def refresh(self) -> None:
        """Triggered by MainWindow on page switch."""
        try:
            self.panel.refresh()
        except (AttributeError, tk.TclError):
            pass

    def update_title(self, page_name: str | None) -> None:
        """Append the active page name to the title bar."""
        if page_name:
            try:
                self.title(f"Scripts — {page_name}")
            except tk.TclError:
                pass
