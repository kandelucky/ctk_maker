"""Export to Python dialog.

Replaces the bare ``asksaveasfilename`` step with a Toplevel mimicking
the New Project dialog so both feel like they belong to the same
designer (rounded panel + label-aligned rows + section title +
prominent primary button in the footer).

Lets the user pick:
    - save location (folder + name); a .py export bundles everything
      in ``<folder>/<name>/`` (defaults under ``<project>/exports/``),
      a .zip lands flat as ``<folder>/<name>.zip``
    - scope: whole project (all forms) or one specific document
    - after-export actions: open the .py in an editor, run it like
      Preview ▶, open the bundle folder in the file manager

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

from typing import Any

import customtkinter as ctk

from app.core.logger import log_error
from app.core.settings import load_settings, save_setting
from app.io.code_exporter import export_project
from app.ui.icons import load_icon
from app.ui.managed_window import ManagedToplevel
from app.ui.properties_panel.tooltip import PropertyTooltip
from app.ui.system_fonts import ui_font

SETTING_INCLUDE_DESCRIPTIONS = "export_include_descriptions"

DIALOG_W = 560
DIALOG_H = 460

PANEL_BG = "#252526"
SUBTITLE_FG = "#888888"
FIELD_FG = "#cccccc"
ENTRY_BORDER_NORMAL = "#3c3c3c"
PREVIEW_FG = "#888888"
SEPARATOR_BG = "#333333"

ALL_FORMS_VALUE = "__all__"
ALL_PAGES_VALUE = "__all_pages__"
PAGE_SCOPE_PREFIX = "page:"
LABEL_WIDTH = 80

# Dark dropdown palette so the option menu sits coherently on the
# panel surface.
_DROPDOWN_STYLE: dict[str, Any] = {
    "fg_color": "#3c3c3c",
    "button_color": "#3c3c3c",
    "button_hover_color": "#4a4a4a",
    "text_color": FIELD_FG,
    "dropdown_fg_color": "#2d2d30",
    "dropdown_hover_color": "#094771",
    "dropdown_text_color": FIELD_FG,
}


def folder_to_open(target: Path) -> Path:
    """Folder the "Show in Explorer" toggle reveals after an export.

    A .py export bundles into ``<dir>/<name>/<name>.py`` — reveal the
    bundle folder itself. A .zip lands flat as ``<dir>/<name>.zip`` —
    reveal the containing folder. Both are ``target.parent``.
    """
    return target.parent


class ExportDialog(ManagedToplevel):
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

    window_title = "Export"
    default_size = (DIALOG_W, DIALOG_H)
    min_size = (DIALOG_W - 40, DIALOG_H - 40)
    panel_padding = (0, 0)
    modal = True
    window_resizable = (False, False)

    def __init__(self, parent, project, preselected_doc_id=None):
        self.project = project
        self.result: str | None = None
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
        self._scope_label_var = tk.StringVar(master=parent, value=initial_label)
        self._name_var = tk.StringVar(master=parent)
        self._dir_var = tk.StringVar(master=parent)
        self._preview_var = tk.StringVar(master=parent)
        self._open_editor_var = tk.BooleanVar(master=parent, value=False)
        self._run_preview_var = tk.BooleanVar(master=parent, value=False)
        # Default ON — landing in the bundle folder is the most common
        # follow-up (double-click the .bat, grab the files, share).
        self._open_folder_var = tk.BooleanVar(master=parent, value=True)
        self._as_zip_var = tk.BooleanVar(master=parent, value=False)
        # Asset filter: default ON for multi-page projects (avoid
        # shipping unused assets per page); OFF for legacy projects
        # to preserve the historical "everything in assets/" behaviour.
        self._only_used_assets_var = tk.BooleanVar(
            master=parent, value=bool(project.folder_path),
        )
        # Phase 0 AI-bridge toggle. Persists to settings so the user's
        # last choice survives across exports / sessions. Default OFF
        # — clean code is the more common need; AI workflow is opt-in.
        _settings = load_settings()
        self._include_descriptions_var = tk.BooleanVar(
            master=parent,
            value=bool(
                _settings.get(SETTING_INCLUDE_DESCRIPTIONS, False),
            ),
        )
        self._open_editor_cb: ctk.CTkCheckBox | None = None
        self._run_preview_cb: ctk.CTkCheckBox | None = None
        self._open_folder_cb: ctk.CTkCheckBox | None = None
        self._tooltip: PropertyTooltip | None = None
        self._user_edited_name = False
        self._initial_label = initial_label

        super().__init__(parent)

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
        self._as_zip_var.trace_add(
            "write", lambda *_: self._on_zip_toggle(),
        )
        self.bind("<Return>", lambda _e: self._on_export())

    def default_offset(self, parent) -> tuple[int, int]:
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            w, h = self.default_size
            return (
                max(0, px + (pw - w) // 2),
                max(0, py + (ph - h) // 2),
            )
        except tk.TclError:
            return (100, 100)

    def build_content(self) -> ctk.CTkFrame:
        container = ctk.CTkFrame(self, fg_color="transparent")
        self._build(container)
        return container

    # ------------------------------------------------------------------
    # Scope list
    # ------------------------------------------------------------------
    def _build_scope_list(self) -> list[tuple[str, str]]:
        """Build scope dropdown options. Multi-page projects list
        every page first (with the user-facing names from project.json),
        then the active page's documents underneath. Legacy single-
        file projects keep the original "Whole project + per-doc" set.
        """
        out: list[tuple[str, str]] = []
        docs = list(self.project.documents)
        pages = list(self.project.pages or [])
        is_multi_page = bool(self.project.folder_path) and bool(pages)

        if is_multi_page:
            # Top entry: every page as separate .py. Only meaningful
            # when the project actually has multiple pages — for a
            # 1-page folder project "All pages" collapses into a
            # single-page export that ignores the Name field, so we
            # skip the entry there and let the user pick the page
            # directly (which uses Name correctly).
            n = len(pages)
            if n > 1:
                out.append((
                    f"All pages ({n} pages)",
                    ALL_PAGES_VALUE,
                ))
            # Per-page scopes — one .py per pick.
            for entry in pages:
                if not isinstance(entry, dict):
                    continue
                name = (entry.get("name") or "").strip() or "Untitled"
                out.append((
                    f"Page: {name}",
                    f"{PAGE_SCOPE_PREFIX}{entry.get('id')}",
                ))
            # Active page's documents — kept under the page list so
            # the user can still emit a single dialog from a multi-
            # document page.
            if len(docs) > 1:
                for doc in docs:
                    dname = (doc.name or "Untitled").strip() or "Untitled"
                    out.append((f"Document: {dname}", doc.id))
            return out

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
    def _build(self, container) -> None:
        self._container = container
        # One shared dark tooltip instance serves every control in the
        # dialog (created before the rows so builders can attach).
        self._tooltip = PropertyTooltip(self)
        self._panel = ctk.CTkFrame(
            container, fg_color=PANEL_BG, corner_radius=6,
        )
        self._panel.pack(
            padx=20, pady=(20, 10), fill="both", expand=True,
        )

        ctk.CTkLabel(
            self._panel, text="Export Project",
            font=ui_font(11, "bold"),
            text_color=SUBTITLE_FG, anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 10))

        self._add_row("Name", self._build_name_entry)
        self._add_row("Save to", self._build_save_row)
        self._build_preview_label()
        self._add_separator()
        self._add_row("Scope", self._build_scope_row)
        self._add_separator()
        self._add_row("Format", self._build_format_checkbox)
        self._add_separator()
        self._add_row("Comments", self._build_descriptions_checkbox)
        self._add_separator()
        self._add_row("After", self._build_after_checkbox)
        self._build_footer()

    def _add_row(self, label: str, builder) -> None:
        row = ctk.CTkFrame(self._panel, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=2)
        ctk.CTkLabel(
            row, text=f"{label}:", width=LABEL_WIDTH, anchor="w",
            font=ui_font(11), text_color=FIELD_FG,
        ).pack(side="left")
        builder(row)

    def _add_separator(self) -> None:
        ctk.CTkFrame(self._panel, height=1, fg_color=SEPARATOR_BG).pack(
            fill="x", padx=14, pady=(10, 10),
        )

    def _build_name_entry(self, row) -> None:
        self._name_entry = ctk.CTkEntry(
            row, textvariable=self._name_var, height=26,
            corner_radius=3, font=ui_font(11), justify="left",
            border_color=ENTRY_BORDER_NORMAL, border_width=1,
        )
        self._name_entry.pack(side="left", fill="x", expand=True)
        self._name_entry.bind("<FocusIn>", self._on_name_focus_in)
        self._attach_tooltip(
            self._name_entry, "name",
            "Name for the export — a .py export bundles into a "
            "<name>/ folder holding <name>.py, a ZIP becomes "
            "<name>.zip.",
        )

    @staticmethod
    def _on_name_focus_in(event) -> None:
        # Click / Tab into the field selects the whole name — the
        # seeded default is usually replaced wholesale. Deferred to
        # idle so the click's own cursor placement (which clears the
        # selection) runs first. event.widget is the inner tk.Entry —
        # CTkEntry delegates binds to it.
        widget = event.widget

        def _select() -> None:
            try:
                widget.select_range(0, "end")
                widget.icursor("end")
            except tk.TclError:
                pass

        widget.after_idle(_select)

    def _build_save_row(self, row) -> None:
        entry = ctk.CTkEntry(
            row, textvariable=self._dir_var, height=26,
            corner_radius=3, font=ui_font(10), justify="left",
            border_color=ENTRY_BORDER_NORMAL, border_width=1,
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._attach_tooltip(
            entry, "save_to",
            "Folder the export lands in — a .py export creates its "
            "bundle folder inside it, a .zip is written directly "
            "here.",
        )

        folder_icon = load_icon("folder", size=14)
        browse = ctk.CTkButton(
            row, text="" if folder_icon else "…",
            image=folder_icon, width=28, height=26,
            corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_browse_folder,
        )
        browse.pack(side="left")
        self._attach_tooltip(
            browse, "browse", "Browse for the export folder.",
        )

    def _build_preview_label(self) -> None:
        # Mirror NewProjectForm — italic preview line under Save to
        # showing the resolved full path. Width-bounded so a long path
        # doesn't reflow the dialog.
        lbl = tk.Label(
            self._panel, textvariable=self._preview_var,
            font=ui_font(9, "italic"),
            fg=PREVIEW_FG, bg=PANEL_BG,
            anchor="w", justify="left",
            width=58,
        )
        lbl.pack(fill="x", padx=(94, 14), pady=(0, 2))

    def _build_scope_row(self, row) -> None:
        labels = [label for label, _ in self._scope_options]
        dropdown = ctk.CTkOptionMenu(
            row, values=labels, variable=self._scope_label_var,
            width=220, height=26, dynamic_resizing=False,
            corner_radius=3,
            **_DROPDOWN_STYLE,
        )
        dropdown.pack(side="left")
        self._attach_tooltip(
            dropdown, "scope",
            "What to export — every page, one page, or a single "
            "form of the active page.",
        )
        n_forms = len(self.project.documents)
        info = f"{n_forms} form{'s' if n_forms != 1 else ''} in project"
        tk.Label(
            row, text=info, bg=PANEL_BG, fg=PREVIEW_FG,
            font=ui_font(9, "italic"),
        ).pack(side="left", padx=(10, 0))

    def _build_format_checkbox(self, row) -> None:
        # ZIP output bundles the .py + assets/ + helper modules into
        # one archive — convenient for sharing the export by email or
        # chat. Toggling it disables the After checkboxes (editor /
        # preview don't apply to a .zip).
        wrap = ctk.CTkFrame(row, fg_color="transparent")
        wrap.pack(side="left", fill="x", expand=True)
        zip_row = ctk.CTkFrame(wrap, fg_color="transparent")
        zip_row.pack(fill="x", anchor="w")
        zip_cb = ctk.CTkCheckBox(
            zip_row, text="Export as ZIP archive",
            variable=self._as_zip_var,
            checkbox_width=18, checkbox_height=18,
            font=ui_font(11),
            text_color=FIELD_FG,
            fg_color="#0e639c", hover_color="#1177bb",
        )
        zip_cb.pack(side="left")
        self._attach_tooltip(
            zip_cb, "zip",
            "Python code + assets bundled into one .zip — easy to "
            "share by email or chat.",
        )
        # Asset filter — only meaningful for multi-page projects
        # (legacy projects always copy the whole asset pool).
        if self.project.folder_path:
            filter_row = ctk.CTkFrame(wrap, fg_color="transparent")
            filter_row.pack(fill="x", anchor="w", pady=(4, 0))
            filter_cb = ctk.CTkCheckBox(
                filter_row, text="Include only used assets",
                variable=self._only_used_assets_var,
                checkbox_width=18, checkbox_height=18,
                font=ui_font(11),
                text_color=FIELD_FG,
                fg_color="#0e639c", hover_color="#1177bb",
            )
            filter_cb.pack(side="left")
            self._attach_tooltip(
                filter_cb, "used_assets",
                "Skip fonts / images / icons not referenced by the "
                "exported pages — smaller bundle.",
            )

    def _build_descriptions_checkbox(self, row) -> None:
        # Phase 0 AI bridge: toggle whether widget descriptions emit
        # as Python ``# comments`` above each constructor. Default on
        # so the AI workflow is discoverable; the choice persists in
        # Settings, so power users who flip it off don't have to redo
        # it on every export.
        wrap = ctk.CTkFrame(row, fg_color="transparent")
        wrap.pack(side="left", fill="x", expand=True)
        desc_row = ctk.CTkFrame(wrap, fg_color="transparent")
        desc_row.pack(fill="x", anchor="w")
        desc_cb = ctk.CTkCheckBox(
            desc_row, text="Include descriptions as comments",
            variable=self._include_descriptions_var,
            checkbox_width=18, checkbox_height=18,
            font=ui_font(11),
            text_color=FIELD_FG,
            fg_color="#0e639c", hover_color="#1177bb",
        )
        desc_cb.pack(side="left")
        self._attach_tooltip(
            desc_cb, "descriptions",
            "Widget descriptions emitted as # comment lines above "
            "each constructor — uncheck for clean production code.",
        )

    def _build_after_checkbox(self, row) -> None:
        # Three independent toggles; each explains itself via a hover
        # tooltip.
        self._open_editor_cb = ctk.CTkCheckBox(
            row, text="Open in editor",
            variable=self._open_editor_var,
            checkbox_width=18, checkbox_height=18,
            font=ui_font(11),
            text_color=FIELD_FG,
            fg_color="#0e639c", hover_color="#1177bb",
        )
        self._open_editor_cb.pack(side="left")
        self._attach_tooltip(
            self._open_editor_cb, "after_editor",
            "Open the exported .py with your code editor "
            "(IDLE / VSCode / Notepad++) — for reviewing the "
            "generated code.",
        )
        self._run_preview_cb = ctk.CTkCheckBox(
            row, text="Run preview",
            variable=self._run_preview_var,
            checkbox_width=18, checkbox_height=18,
            font=ui_font(11),
            text_color=FIELD_FG,
            fg_color="#0e639c", hover_color="#1177bb",
        )
        self._run_preview_cb.pack(side="left", padx=(20, 0))
        self._attach_tooltip(
            self._run_preview_cb, "after_preview",
            "Run the exported .py right away — same as Preview ▶, "
            "but from the export folder.",
        )
        self._open_folder_cb = ctk.CTkCheckBox(
            row, text="Show in Explorer",
            variable=self._open_folder_var,
            checkbox_width=18, checkbox_height=18,
            font=ui_font(11),
            text_color=FIELD_FG,
            fg_color="#0e639c", hover_color="#1177bb",
        )
        self._open_folder_cb.pack(side="left", padx=(20, 0))
        self._attach_tooltip(
            self._open_folder_cb, "after_folder",
            "Show the export in File Explorer — the bundle folder "
            "for a .py export, the .zip's folder for an archive.",
        )

    def _attach_tooltip(self, widget, key: str, text: str) -> None:
        # CTk widgets' .bind targets their canvas / label / entry
        # leaves, so Enter/Leave fire without parent-frame flicker.
        # Click hides — once the user acts, the explanation is noise.
        widget.bind(
            "<Enter>",
            lambda e: self._tooltip.schedule(
                e.x_root, e.y_root, text, key=key,
            ),
        )
        widget.bind("<Leave>", lambda _e: self._tooltip.cancel())
        widget.bind("<Button-1>", lambda _e: self._tooltip.cancel())

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self._container, fg_color="transparent")
        footer.pack(fill="x", padx=20, pady=(0, 16))
        export_btn = ctk.CTkButton(
            footer, text="Export", width=160, height=32,
            corner_radius=4, command=self._on_export,
        )
        export_btn.pack(side="right")
        self._attach_tooltip(
            export_btn, "export",
            "Write the export to the path shown in the preview line.",
        )
        cancel_btn = ctk.CTkButton(
            footer, text="Cancel", width=90, height=32,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        )
        cancel_btn.pack(side="right", padx=(0, 8))
        self._attach_tooltip(
            cancel_btn, "cancel", "Close without exporting.",
        )

    # ------------------------------------------------------------------
    # Path defaults
    # ------------------------------------------------------------------
    def _defaults_for_scope(self, scope_label: str) -> tuple[str, str]:
        """Return ``(name_stem, save_dir)`` defaults for a scope label."""
        scope_id = self._scope_id_for(scope_label)
        if scope_id in (ALL_FORMS_VALUE, ALL_PAGES_VALUE):
            stem = (self.project.name or "project").strip() or "project"
        elif scope_id.startswith(PAGE_SCOPE_PREFIX):
            page_id = scope_id[len(PAGE_SCOPE_PREFIX):]
            entry = next(
                (
                    p for p in (self.project.pages or [])
                    if isinstance(p, dict) and p.get("id") == page_id
                ),
                None,
            )
            stem = (
                (entry.get("name") if entry else None) or "page"
            ).strip() or "page"
        else:
            doc = self.project.get_document(scope_id)
            stem = (doc.name if doc else None) or "document"
        stem = "".join(c for c in stem if c not in '\\/:*?"<>|').strip()
        if not stem:
            stem = "project"
        # Default export folder: project root for multi-page (so
        # each export lands in <project>/exports/), else the legacy
        # sibling of the .ctkproj.
        if self.project.folder_path:
            base = Path(self.project.folder_path) / "exports"
        elif self.project.path:
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
        # Strip a redundant extension the user might've typed — we
        # always add the right one back below based on the ZIP toggle.
        lowered = name.lower()
        if lowered.endswith(".py"):
            name = name[:-3]
        elif lowered.endswith(".zip"):
            name = name[:-4]
        if not name:
            return None
        if self._as_zip_var.get():
            # A .zip is already a single self-contained bundle.
            return Path(directory) / f"{name}.zip"
        # Multi-file output (.py + launcher + ctkmaker.py + scripts/ +
        # assets/) — gather everything in a folder named by the user.
        return Path(directory) / name / f"{name}.py"

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

    def _on_zip_toggle(self) -> None:
        # ZIP output: editor + preview don't apply to an archive, so
        # disable both checkboxes (also force them off so a stale
        # checked state doesn't survive when the user toggles ZIP back
        # off and on). "Show in Explorer" stays enabled — revealing
        # the .zip's folder is just as useful as revealing a bundle.
        # Refresh the preview so the path extension flips.
        is_zip = self._as_zip_var.get()
        new_state = "disabled" if is_zip else "normal"
        if is_zip:
            self._open_editor_var.set(False)
            self._run_preview_var.set(False)
        for cb in (self._open_editor_cb, self._run_preview_cb):
            if cb is not None:
                cb.configure(state=new_state)
        self._refresh_preview()

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
        # Persist the AI-bridge toggle so the user's last choice
        # survives across exports / sessions.
        save_setting(
            SETTING_INCLUDE_DESCRIPTIONS,
            bool(self._include_descriptions_var.get()),
        )
        scope_id = self._scope_id_for(self._scope_label_var.get())
        try:
            self._dispatch_export(scope_id, target)
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
        do_folder = self._open_folder_var.get()
        if do_editor:
            self._open_exported_file(target)
        if do_preview:
            self._run_exported_preview(target)
        if do_folder:
            self._open_export_folder(target)
        if not (do_editor or do_preview or do_folder):
            messagebox.showinfo(
                "Export", f"Saved to:\n{target}", parent=self,
            )
        self.destroy()

    def _dispatch_export(self, scope_id: str, target: Path) -> None:
        """Route the chosen scope to the right export call:
          - ALL_PAGES_VALUE → iterate every page in project.json,
            emit one .py per page into ``target.parent``
          - PAGE_SCOPE_PREFIX + id → load that page off disk,
            export it as ``target``
          - doc_id (active page document) → existing single-doc export
          - ALL_FORMS_VALUE → existing whole-project export
        """
        as_zip = self._as_zip_var.get()
        use_filter = self._only_used_assets_var.get()

        if scope_id == ALL_PAGES_VALUE:
            self._export_all_pages(target.parent, target.suffix, as_zip, use_filter)
            return
        if scope_id.startswith(PAGE_SCOPE_PREFIX):
            page_id = scope_id[len(PAGE_SCOPE_PREFIX):]
            self._export_single_page(page_id, target, as_zip, use_filter)
            return
        # Active-page scope (legacy / per-document or whole project).
        single_id = None if scope_id == ALL_FORMS_VALUE else scope_id
        asset_filter: set[Path] | None = None
        if use_filter and self.project.folder_path:
            from app.core.project_folder import collect_used_assets
            asset_filter = collect_used_assets(self.project)
        export_project(
            self.project, str(target),
            single_document_id=single_id,
            as_zip=as_zip,
            asset_filter=asset_filter,
            include_descriptions=self._include_descriptions_var.get(),
            emit_launcher=True,
        )

    def _export_single_page(
        self, page_id: str, target: Path,
        as_zip: bool, use_filter: bool,
    ) -> None:
        """Load a non-active page from disk into a temporary Project
        clone and export it. Avoids switching the live project's
        active page (the user just wanted a .py, not a context flip).
        """
        # Active page exports through the in-memory project — fall
        # back to the cheap path when the user picked the page they
        # already have loaded.
        if page_id == self.project.active_page_id:
            asset_filter: set[Path] | None = None
            if use_filter:
                from app.core.project_folder import collect_used_assets
                asset_filter = collect_used_assets(self.project)
            export_project(
                self.project, str(target),
                as_zip=as_zip,
                asset_filter=asset_filter,
                include_descriptions=self._include_descriptions_var.get(),
                emit_launcher=True,
            )
            return
        clone = self._build_temp_project_for_page(page_id)
        if clone is None:
            messagebox.showerror(
                "Export failed",
                "Could not load the selected page off disk.",
                parent=self,
            )
            return
        asset_filter = None
        if use_filter:
            from app.core.project_folder import collect_used_assets
            asset_filter = collect_used_assets(clone)
        export_project(
            clone, str(target),
            as_zip=as_zip,
            asset_filter=asset_filter,
            include_descriptions=self._include_descriptions_var.get(),
            emit_launcher=True,
        )

    def _export_all_pages(
        self, out_dir: Path, ext: str,
        as_zip: bool, use_filter: bool,
    ) -> None:
        """Emit one ``.py`` (or ``.zip``) per page into ``out_dir``.
        Asset filter is per-page so each export bundle ships only
        its own references — switching the filter off shares the
        whole assets/ pool across all bundles instead.
        """
        from app.core.project_folder import collect_used_assets, slugify_page_name
        for entry in self.project.pages or []:
            if not isinstance(entry, dict):
                continue
            page_id = entry.get("id")
            if not isinstance(page_id, str):
                continue
            page_name = (entry.get("name") or "untitled").strip() or "untitled"
            slug = slugify_page_name(page_name)
            target = out_dir / f"{slug}{ext}"
            if page_id == self.project.active_page_id:
                src_project = self.project
            else:
                src_project = self._build_temp_project_for_page(page_id)
                if src_project is None:
                    continue
            asset_filter = None
            if use_filter:
                asset_filter = collect_used_assets(src_project)
            export_project(
                src_project, str(target),
                as_zip=as_zip,
                asset_filter=asset_filter,
                include_descriptions=self._include_descriptions_var.get(),
                emit_launcher=True,
            )

    def _build_temp_project_for_page(self, page_id: str):
        """Spin up a fresh Project loaded with the given page's data
        without touching the dialog's source project. Returns ``None``
        if the page can't be located or loaded.
        """
        from app.core.project import Project
        from app.core.project_folder import (
            page_file_path,
        )
        entry = next(
            (
                p for p in (self.project.pages or [])
                if isinstance(p, dict) and p.get("id") == page_id
            ),
            None,
        )
        if entry is None or not self.project.folder_path:
            return None
        page_path = page_file_path(
            self.project.folder_path, entry.get("file") or "",
        )
        if not page_path.is_file():
            return None
        from app.io.project_loader import load_project
        clone = Project()
        try:
            load_project(clone, str(page_path))
        except Exception:
            log_error("export_dialog build_temp_project")
            return None
        return clone

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

    def _open_export_folder(self, path: Path) -> None:
        # Reveal the export location in the OS file manager — same
        # platform ladder as _open_exported_file.
        folder = folder_to_open(path)
        try:
            if sys.platform == "win32":
                os.startfile(str(folder))
                return
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
                return
            subprocess.Popen(["xdg-open", str(folder)])
        except Exception:
            log_error("export dialog open folder")

    def _on_cancel(self) -> None:
        self.destroy()

    def destroy(self) -> None:
        # Kill any pending/visible tooltip first — its after-callback
        # would otherwise fire against a dead master.
        if self._tooltip is not None:
            self._tooltip.cancel()
        super().destroy()
