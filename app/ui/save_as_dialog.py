"""Save As dialog for multi-page projects.

Replaces the bare ``asksaveasfilename`` step with a 3-scope chooser
matching the Export dialog's chrome (panel + label-aligned rows +
section heading + prominent footer button). Scopes:

    Save Page As...           → new page in the current project
                                 (asset pool stays shared)
    Save Project As...        → duplicate the entire project folder
                                 to a new location
    Save Page to New Project  → just the active page + the assets
                                 it references → new project folder

Returned ``result`` is a dict the caller dispatches on:
    {"scope": "page", "name": "Settings"}
    {"scope": "project", "name": "MyProj v2", "save_to": "C:/..."}
    {"scope": "extract", "name": "MyPage", "save_to": "C:/..."}

``None`` if the user cancelled.

Legacy (single-file) projects don't open this dialog — main_window
falls through to the classic Save As filedialog for them.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app.core.paths import get_default_projects_dir
from app.ui.dialog_utils import prepare_dialog, reveal_dialog, safe_grab_set
from app.ui.icons import load_icon

DIALOG_W = 540
DIALOG_H = 410

PANEL_BG = "#252526"
SUBTITLE_FG = "#888888"
FIELD_FG = "#cccccc"
ENTRY_BORDER_NORMAL = "#3c3c3c"
ENTRY_BORDER_ERROR = "#d04040"
PREVIEW_FG = "#888888"
SEPARATOR_BG = "#333333"

LABEL_WIDTH = 88

FORBIDDEN_NAME_CHARS = set('\\/:*?"<>|')

_SCOPE_PAGE = "page"
_SCOPE_PROJECT = "project"
_SCOPE_EXTRACT = "extract"


class SaveAsDialog(ctk.CTkToplevel):
    """Pick scope + name + (optional) destination for a save.

    Parameters
    ----------
    parent : Tk widget
        Owner toplevel.
    project : Project
        Source project. Used to default field values.
    """

    def __init__(self, parent, project):
        super().__init__(parent)
        prepare_dialog(self)
        self.project = project
        self.result: dict | None = None

        self.title("Save As")
        self.resizable(False, False)
        self.transient(parent)
        safe_grab_set(self)
        self.geometry(f"{DIALOG_W}x{DIALOG_H}")
        self.configure(fg_color="#1e1e1e")

        # Defaults pulled from the live project: current page name
        # for the Page scope; project name for Project / Extract.
        active_page_name = next(
            (
                p.get("name", "") for p in (project.pages or [])
                if isinstance(p, dict) and p.get("id") == project.active_page_id
            ),
            "",
        )

        self._scope_var = tk.StringVar(value=_SCOPE_PAGE)
        self._name_var = tk.StringVar(value=active_page_name or "Untitled")
        # "Save to" parent dir defaults to the source project's
        # parent folder so the duplicate lands as a sibling — the
        # user's "projects directory" by convention.
        if project.folder_path:
            default_save_dir = str(Path(project.folder_path).parent)
        else:
            default_save_dir = str(get_default_projects_dir())
        self._save_to_var = tk.StringVar(value=default_save_dir)
        self._preview_var = tk.StringVar()

        self._name_entry: ctk.CTkEntry | None = None
        self._save_to_entry: ctk.CTkEntry | None = None
        self._save_to_btn: ctk.CTkButton | None = None

        self._build()
        self._on_scope_change()  # prime preview + field enabled state
        self._center_on_parent(parent)

        self._name_var.trace_add(
            "write", lambda *_a: (
                self._clear_name_error(), self._refresh_preview(),
            ),
        )
        self._save_to_var.trace_add(
            "write", lambda *_a: self._refresh_preview(),
        )
        self._scope_var.trace_add(
            "write", lambda *_a: self._on_scope_change(),
        )

        self.bind("<Return>", lambda _e: self._on_save())
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        reveal_dialog(self)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=6)
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            outer, text="Save As",
            font=("Segoe UI", 11, "bold"),
            text_color=SUBTITLE_FG, anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 10))

        self._add_row(outer, "Name", self._build_name_entry)
        self._add_row(outer, "Save to", self._build_save_to_row)
        self._build_preview_label(outer)
        self._refresh_preview()
        self._add_separator(outer)

        ctk.CTkLabel(
            outer, text="Scope:",
            font=("Segoe UI", 10, "bold"),
            text_color=FIELD_FG, anchor="w",
        ).pack(fill="x", padx=14, pady=(2, 6))

        self._add_scope_option(
            outer, _SCOPE_PAGE, "Save Page As...",
            "Adds a new page in this project. The asset pool "
            "(fonts / images / icons) stays shared.",
        )
        self._add_scope_option(
            outer, _SCOPE_PROJECT, "Save Project As...",
            "Duplicates the entire project folder — every page, "
            "every asset, every backup — to a new location.",
        )
        self._add_scope_option(
            outer, _SCOPE_EXTRACT, "Save Page to New Project...",
            "Just this page plus the assets it actually references. "
            "Unused assets stay in the source project.",
        )

        self._build_footer(outer)

    def _add_row(self, parent, label, builder) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(
            row, text=f"{label}:", width=LABEL_WIDTH, anchor="w",
            font=("Segoe UI", 11), text_color=FIELD_FG,
        ).pack(side="left")
        builder(row)

    def _add_separator(self, parent) -> None:
        ctk.CTkFrame(parent, height=1, fg_color=SEPARATOR_BG).pack(
            fill="x", padx=14, pady=(10, 6),
        )

    def _build_name_entry(self, row) -> None:
        entry = ctk.CTkEntry(
            row, textvariable=self._name_var, height=26,
            corner_radius=3, font=("Segoe UI", 11), justify="left",
            border_color=ENTRY_BORDER_NORMAL, border_width=1,
        )
        entry.pack(side="left", fill="x", expand=True)
        self._name_entry = entry

    def _build_save_to_row(self, row) -> None:
        entry = ctk.CTkEntry(
            row, textvariable=self._save_to_var, height=26,
            corner_radius=3, font=("Segoe UI", 10), justify="left",
            border_color=ENTRY_BORDER_NORMAL, border_width=1,
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._save_to_entry = entry
        folder_icon = load_icon("folder", size=14)
        btn = ctk.CTkButton(
            row, text="" if folder_icon else "…",
            image=folder_icon, width=28, height=26, corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_pick_save_dir,
        )
        btn.pack(side="left")
        self._save_to_btn = btn

    def _build_preview_label(self, parent) -> None:
        lbl = tk.Label(
            parent, textvariable=self._preview_var,
            font=("Segoe UI", 9, "italic"),
            fg=PREVIEW_FG, bg=PANEL_BG,
            anchor="w", justify="left", width=58,
        )
        lbl.pack(fill="x", padx=(LABEL_WIDTH + 14, 14), pady=(0, 2))

    def _add_scope_option(
        self, parent, value: str, title: str, blurb: str,
    ) -> None:
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="x", padx=14, pady=1)
        rb = ctk.CTkRadioButton(
            wrap, text=title, variable=self._scope_var, value=value,
            font=("Segoe UI", 11), text_color=FIELD_FG,
            radiobutton_height=16, radiobutton_width=16,
            border_width_checked=4, border_width_unchecked=2,
        )
        rb.pack(anchor="w")
        ctk.CTkLabel(
            wrap, text=blurb, font=("Segoe UI", 9),
            text_color=SUBTITLE_FG, anchor="w", justify="left",
            wraplength=DIALOG_W - 80,
        ).pack(anchor="w", padx=(28, 0), pady=(0, 4))

    def _build_footer(self, parent) -> None:
        footer = ctk.CTkFrame(parent, fg_color="transparent")
        footer.pack(fill="x", padx=14, pady=(8, 10), side="bottom")
        ctk.CTkButton(
            footer, text="Cancel",
            width=80, height=28, corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Save",
            width=100, height=28, corner_radius=3,
            command=self._on_save,
        ).pack(side="right", padx=(0, 8))

    # ------------------------------------------------------------------
    # Behaviour
    # ------------------------------------------------------------------
    def _on_scope_change(self) -> None:
        # "Save to" only meaningful for Project / Extract scopes —
        # the in-project Page scope reuses the existing folder.
        scope = self._scope_var.get()
        save_to_active = scope in (_SCOPE_PROJECT, _SCOPE_EXTRACT)
        state = "normal" if save_to_active else "disabled"
        if self._save_to_entry is not None:
            self._save_to_entry.configure(state=state)
        if self._save_to_btn is not None:
            self._save_to_btn.configure(state=state)
        # Default name shifts based on scope: Page reuses the
        # current page name; Project/Extract use the project name
        # so the user sees a sensible starting point.
        self._refresh_preview()

    def _on_pick_save_dir(self) -> None:
        path = filedialog.askdirectory(
            parent=self,
            title="Choose save location",
            initialdir=self._save_to_var.get() or str(Path.home()),
        )
        if path:
            self._save_to_var.set(path)

    def _refresh_preview(self) -> None:
        scope = self._scope_var.get()
        name = (self._name_var.get() or "").strip()
        if not name:
            self._preview_var.set("")
            return
        if scope == _SCOPE_PAGE:
            from app.core.project_folder import slugify_page_name
            slug = slugify_page_name(name)
            target = (
                f"<this project>/assets/pages/{slug}.ctkproj"
                if self.project.folder_path
                else f"{slug}.ctkproj"
            )
        else:
            save_to = self._save_to_var.get() or ""
            if not save_to:
                self._preview_var.set("")
                return
            target = str(Path(save_to) / name) + "/"
        max_len = 56
        display = target
        if len(display) > max_len:
            display = "..." + display[-(max_len - 3):]
        self._preview_var.set(f"→ {display}")

    # ------------------------------------------------------------------
    # Validation + result
    # ------------------------------------------------------------------
    def _flag_name_error(self) -> None:
        try:
            self.bell()
        except tk.TclError:
            pass
        if self._name_entry is not None:
            self._name_entry.configure(border_color=ENTRY_BORDER_ERROR)

    def _clear_name_error(self) -> None:
        if self._name_entry is not None:
            self._name_entry.configure(border_color=ENTRY_BORDER_NORMAL)

    def _on_save(self) -> None:
        name = (self._name_var.get() or "").strip()
        if not name:
            self._flag_name_error()
            return
        if any(c in FORBIDDEN_NAME_CHARS for c in name):
            self._flag_name_error()
            messagebox.showwarning(
                "Invalid name",
                "Name may not contain any of these characters:\n\n"
                '    \\  /  :  *  ?  "  <  >  |',
                parent=self,
            )
            return
        scope = self._scope_var.get()
        result: dict = {"scope": scope, "name": name}
        if scope in (_SCOPE_PROJECT, _SCOPE_EXTRACT):
            save_to = (self._save_to_var.get() or "").strip()
            if not save_to:
                self._flag_name_error()
                return
            save_to_path = Path(save_to).expanduser()
            if not save_to_path.exists():
                messagebox.showwarning(
                    "Save location missing",
                    f"The save location does not exist:\n{save_to}",
                    parent=self,
                )
                return
            target_folder = save_to_path / name
            if target_folder.exists():
                messagebox.showwarning(
                    "Folder exists",
                    f"A folder named '{name}' already exists at:\n\n"
                    f"{save_to_path}\n\nPick a different name "
                    "or save location.",
                    parent=self,
                )
                self._flag_name_error()
                return
            result["save_to"] = str(save_to_path)
        elif scope == _SCOPE_PAGE:
            # Same-name guard mirrors add_page's check so the user
            # gets the failure surface in this dialog instead of
            # after dismissal.
            if any(
                isinstance(p, dict)
                and (p.get("name") or "").strip().lower()
                == name.lower()
                for p in (self.project.pages or [])
            ):
                messagebox.showwarning(
                    "Page name in use",
                    f"A page named '{name}' already exists "
                    "in this project.",
                    parent=self,
                )
                self._flag_name_error()
                return
        self.result = result
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent) -> None:
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + (pw - DIALOG_W) // 2
            y = py + (ph - DIALOG_H) // 2
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            pass
