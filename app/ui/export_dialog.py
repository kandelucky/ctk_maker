"""Export to Python dialog.

Replaces the bare ``asksaveasfilename`` step with a Toplevel mimicking
the New Project dialog so both feel like they belong to the same
designer (rounded panel + label-aligned rows + section title +
prominent primary button in the footer).

Lets the user pick:
    - save location (folder + filename); defaults to
      ``<project>/exports/<scope>.py``
    - scope: whole project (all forms) or one specific document
    - open the .py with the OS edit-verb after export

Used by File → Export and the per-document chrome Export icon (via
the ``request_export_document`` event bus).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app.core.logger import log_error
from app.io.code_exporter import export_project
from app.ui.icons import load_icon

DIALOG_W = 560
DIALOG_H = 360

PANEL_BG = "#252526"
SUBTITLE_FG = "#888888"
FIELD_FG = "#cccccc"
ENTRY_BORDER_NORMAL = "#3c3c3c"
PREVIEW_FG = "#888888"
SEPARATOR_BG = "#333333"

ALL_FORMS_VALUE = "__all__"
LABEL_WIDTH = 80

# Dark dropdown palette so the option menu sits coherently on the
# panel surface.
_DROPDOWN_STYLE = dict(
    fg_color="#3c3c3c",
    button_color="#3c3c3c",
    button_hover_color="#4a4a4a",
    text_color=FIELD_FG,
    dropdown_fg_color="#2d2d30",
    dropdown_hover_color="#094771",
    dropdown_text_color=FIELD_FG,
)


class ExportDialog(ctk.CTkToplevel):
    """Pick where + what to export, then call ``export_project``.

    Parameters
    ----------
    parent : Tk widget
        Owner toplevel — dialog is transient over it and centers on it.
    project : Project
        Source project. Read for documents list + path defaults.
    preselected_doc_id : str | None
        If given, the scope dropdown opens on that document instead of
        "All forms". Used by the per-document Export chrome icon.
    """

    def __init__(self, parent, project, preselected_doc_id=None):
        super().__init__(parent)
        self.project = project
        self.result: str | None = None

        self.title("Export")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.geometry(f"{DIALOG_W}x{DIALOG_H}")

        self._scope_options: list[tuple[str, str]] = self._build_scope_list()
        if preselected_doc_id:
            initial_label = next(
                (
                    label for label, doc_id in self._scope_options
                    if doc_id == preselected_doc_id
                ),
                self._scope_options[0][0],
            )
        else:
            initial_label = self._scope_options[0][0]
        self._scope_label_var = tk.StringVar(value=initial_label)
        self._name_var = tk.StringVar()
        self._dir_var = tk.StringVar()
        self._preview_var = tk.StringVar()
        self._open_editor_var = tk.BooleanVar(value=False)
        self._run_preview_var = tk.BooleanVar(value=False)
        self._user_edited_name = False

        self._build()

        # Seed defaults from the initial scope. The folder defaults to
        # ``<project>/exports/`` and stays sticky once the user edits
        # it; the name follows the scope label until the user types a
        # custom one.
        default_name, default_dir = self._defaults_for_scope(initial_label)
        self._name_var.set(default_name)
        self._dir_var.set(default_dir)
        self._refresh_preview()

        self._scope_label_var.trace_add(
            "write", lambda *_: self._on_scope_change(),
        )
        self._name_var.trace_add(
            "write", lambda *_: self._on_name_change(),
        )
        self._dir_var.trace_add(
            "write", lambda *_: self._refresh_preview(),
        )

        self.bind("<Return>", lambda _e: self._on_export())
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.after(100, self._center_on_parent)

    # ------------------------------------------------------------------
    # Scope list
    # ------------------------------------------------------------------
    def _build_scope_list(self) -> list[tuple[str, str]]:
        docs = list(self.project.documents)
        out: list[tuple[str, str]] = []
        if len(docs) > 1:
            n = len(docs) - 1
            label = f"All forms (Main + {n} Dialog{'s' if n != 1 else ''})"
        else:
            label = "Whole project"
        out.append((label, ALL_FORMS_VALUE))
        for doc in docs:
            name = (doc.name or "Untitled").strip() or "Untitled"
            out.append((name, doc.id))
        return out

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self._panel = ctk.CTkFrame(
            self, fg_color=PANEL_BG, corner_radius=6,
        )
        self._panel.pack(
            padx=20, pady=(20, 10), fill="both", expand=True,
        )

        ctk.CTkLabel(
            self._panel, text="Export Project",
            font=("Segoe UI", 11, "bold"),
            text_color=SUBTITLE_FG, anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 10))

        self._add_row("Name", self._build_name_entry)
        self._add_row("Save to", self._build_save_row)
        self._build_preview_label()
        self._add_separator()
        self._add_row("Scope", self._build_scope_row)
        self._add_separator()
        self._add_row("After", self._build_after_checkbox)
        # Sub-hint pinned under the After row, indented past the
        # label gutter so it lines up with the checkboxes.
        tk.Label(
            self._panel,
            text=(
                "Editor: IDLE / VSCode / Notepad++ for code review.   "
                "Preview: runs the .py like Preview ▶."
            ),
            font=("Segoe UI", 9, "italic"),
            fg=PREVIEW_FG, bg=PANEL_BG,
            anchor="w", justify="left",
        ).pack(fill="x", padx=(LABEL_WIDTH + 28, 14), pady=(2, 0))

        self._build_footer()

    def _add_row(self, label: str, builder) -> None:
        row = ctk.CTkFrame(self._panel, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(
            row, text=f"{label}:", width=LABEL_WIDTH, anchor="w",
            font=("Segoe UI", 11), text_color=FIELD_FG,
        ).pack(side="left")
        builder(row)

    def _add_separator(self) -> None:
        ctk.CTkFrame(self._panel, height=1, fg_color=SEPARATOR_BG).pack(
            fill="x", padx=14, pady=(10, 10),
        )

    def _build_name_entry(self, row) -> None:
        ctk.CTkEntry(
            row, textvariable=self._name_var, height=26,
            corner_radius=3, font=("Segoe UI", 11), justify="left",
            border_color=ENTRY_BORDER_NORMAL, border_width=1,
        ).pack(side="left", fill="x", expand=True)

    def _build_save_row(self, row) -> None:
        ctk.CTkEntry(
            row, textvariable=self._dir_var, height=26,
            corner_radius=3, font=("Segoe UI", 10), justify="left",
            border_color=ENTRY_BORDER_NORMAL, border_width=1,
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        folder_icon = load_icon("folder", size=14)
        ctk.CTkButton(
            row, text="" if folder_icon else "…",
            image=folder_icon, width=28, height=26,
            corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_browse_folder,
        ).pack(side="left")

    def _build_preview_label(self) -> None:
        # Mirror NewProjectForm — italic preview line under Save to
        # showing the resolved full path. Width-bounded so a long path
        # doesn't reflow the dialog.
        lbl = tk.Label(
            self._panel, textvariable=self._preview_var,
            font=("Segoe UI", 9, "italic"),
            fg=PREVIEW_FG, bg=PANEL_BG,
            anchor="w", justify="left",
            width=58,
        )
        lbl.pack(fill="x", padx=(94, 14), pady=(0, 2))

    def _build_scope_row(self, row) -> None:
        labels = [label for label, _ in self._scope_options]
        ctk.CTkOptionMenu(
            row, values=labels, variable=self._scope_label_var,
            width=220, height=26, dynamic_resizing=False,
            corner_radius=3,
            **_DROPDOWN_STYLE,
        ).pack(side="left")
        n_forms = len(self.project.documents)
        info = f"{n_forms} form{'s' if n_forms != 1 else ''} in project"
        tk.Label(
            row, text=info, bg=PANEL_BG, fg=PREVIEW_FG,
            font=("Segoe UI", 9, "italic"),
        ).pack(side="left", padx=(10, 0))

    def _build_after_checkbox(self, row) -> None:
        # Two independent toggles. "Open in editor" routes through the
        # OS edit verb (IDLE / VSCode / Notepad++) — for code review.
        # "Run preview" launches the exported .py exactly like Preview
        # ▶ does — for verifying the result visually.
        ctk.CTkCheckBox(
            row, text="Open in editor",
            variable=self._open_editor_var,
            checkbox_width=18, checkbox_height=18,
            font=("Segoe UI", 11),
            text_color=FIELD_FG,
            fg_color="#0e639c", hover_color="#1177bb",
        ).pack(side="left")
        ctk.CTkCheckBox(
            row, text="Run preview",
            variable=self._run_preview_var,
            checkbox_width=18, checkbox_height=18,
            font=("Segoe UI", 11),
            text_color=FIELD_FG,
            fg_color="#0e639c", hover_color="#1177bb",
        ).pack(side="left", padx=(20, 0))

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(
            footer, text="Export", width=160, height=32,
            corner_radius=4, command=self._on_export,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel", width=90, height=32,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))

    # ------------------------------------------------------------------
    # Path defaults
    # ------------------------------------------------------------------
    def _defaults_for_scope(self, scope_label: str) -> tuple[str, str]:
        """Return ``(name_stem, save_dir)`` defaults for a scope label."""
        scope_id = self._scope_id_for(scope_label)
        if scope_id == ALL_FORMS_VALUE:
            stem = (self.project.name or "project").strip() or "project"
        else:
            doc = self.project.get_document(scope_id)
            stem = (doc.name if doc else None) or "document"
        stem = "".join(c for c in stem if c not in '\\/:*?"<>|').strip()
        if not stem:
            stem = "project"
        if self.project.path:
            base = Path(self.project.path).parent / "exports"
        else:
            base = Path.home() / "exports"
        return stem, str(base)

    def _scope_id_for(self, label: str) -> str:
        for lbl, doc_id in self._scope_options:
            if lbl == label:
                return doc_id
        return ALL_FORMS_VALUE

    def _resolved_path(self) -> Path | None:
        name = self._name_var.get().strip()
        directory = self._dir_var.get().strip()
        if not name or not directory:
            return None
        # Strip a redundant .py the user might've typed — we always
        # add it back in ``_on_export``.
        if name.lower().endswith(".py"):
            name = name[:-3]
        if not name:
            return None
        return Path(directory) / f"{name}.py"

    def _on_scope_change(self) -> None:
        # Only refresh the name when the user hasn't typed a custom
        # one. The save dir is sticky regardless — picking another
        # form shouldn't bounce the user out of a chosen folder.
        if self._user_edited_name:
            return
        new_name, _ = self._defaults_for_scope(self._scope_label_var.get())
        # Suppress the user-edit flag during the auto-update — the
        # name-trace would otherwise interpret our own write as a
        # user-typed change and pin the field forever.
        self._suppress_name_trace = True
        try:
            self._name_var.set(new_name)
        finally:
            self._suppress_name_trace = False

    def _on_name_change(self) -> None:
        if not getattr(self, "_suppress_name_trace", False):
            self._user_edited_name = True
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        resolved = self._resolved_path()
        if resolved is None:
            self._preview_var.set("")
            return
        display = str(resolved)
        max_len = 56
        if len(display) > max_len:
            display = "..." + display[-(max_len - 3):]
        self._preview_var.set(f"→ {display}")

    def _on_browse_folder(self) -> None:
        current = self._dir_var.get().strip()
        initial_dir = (
            current if current and Path(current).is_dir()
            else str(Path.home())
        )
        chosen = filedialog.askdirectory(
            parent=self, title="Export folder",
            initialdir=initial_dir,
        )
        if not chosen:
            return
        self._dir_var.set(chosen)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_export(self) -> None:
        target = self._resolved_path()
        if target is None:
            messagebox.showwarning(
                "Missing fields",
                "Pick a name and save folder for the export.",
                parent=self,
            )
            return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log_error("export dialog mkdir")
            messagebox.showerror(
                "Export failed",
                f"Could not create folder:\n{target.parent}\n\n{exc}",
                parent=self,
            )
            return
        scope_id = self._scope_id_for(self._scope_label_var.get())
        single_id = None if scope_id == ALL_FORMS_VALUE else scope_id
        try:
            export_project(
                self.project, str(target),
                single_document_id=single_id,
            )
        except OSError as exc:
            log_error("export dialog export_project")
            messagebox.showerror(
                "Export failed",
                f"Could not write the file:\n{target}\n\n{exc}",
                parent=self,
            )
            return
        self.result = str(target)
        do_editor = self._open_editor_var.get()
        do_preview = self._run_preview_var.get()
        if do_editor:
            self._open_exported_file(target)
        if do_preview:
            self._run_exported_preview(target)
        if not (do_editor or do_preview):
            messagebox.showinfo(
                "Export", f"Saved to:\n{target}", parent=self,
            )
        self.destroy()

    def _run_exported_preview(self, path: Path) -> None:
        # Spawn the exported file with the same Python interpreter the
        # builder is running under — mirrors File → Preview ▶ but
        # against the user's chosen output path instead of a temp dir.
        try:
            subprocess.Popen(
                [sys.executable, str(path)], cwd=str(path.parent),
            )
        except OSError:
            log_error("export dialog run preview")
            messagebox.showerror(
                "Preview failed",
                "Could not launch the exported file with Python.",
                parent=self,
            )

    def _open_exported_file(self, path: Path) -> None:
        # ``.py`` default Windows verb is "open" which RUNS the script
        # via python.exe — flashing terminal that closes when the
        # script ends. Use the explicit "edit" verb instead so the
        # registered editor (IDLE / VSCode / Notepad++) handles the
        # file. Falls back to IDLE bundled with the running Python.
        try:
            if sys.platform == "win32":
                try:
                    os.startfile(str(path), "edit")
                    return
                except OSError:
                    try:
                        subprocess.Popen(
                            [sys.executable, "-m", "idlelib", str(path)],
                        )
                        return
                    except (OSError, FileNotFoundError):
                        pass
                subprocess.Popen(["explorer.exe", str(path)])
                return
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
                return
            subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            log_error("export dialog open after export")

    def _on_cancel(self) -> None:
        self.destroy()

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------
    def _center_on_parent(self) -> None:
        self.update_idletasks()
        parent = self.master
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
        except tk.TclError:
            return
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
