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
from app.core.settings import load_settings, save_setting
from app.io.code_exporter import export_project
from app.ui.dialog_utils import safe_grab_set
from app.ui.icons import load_icon

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
        safe_grab_set(self)
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
        self._open_editor_var = tk.BooleanVar(value=True)
        self._run_preview_var = tk.BooleanVar(value=False)
        self._as_zip_var = tk.BooleanVar(value=False)
        # Asset filter: default ON for multi-page projects (avoid
        # shipping unused assets per page); OFF for legacy projects
        # to preserve the historical "everything in assets/" behaviour.
        self._only_used_assets_var = tk.BooleanVar(
            value=bool(project.folder_path),
        )
        # Phase 0 AI-bridge toggle. Persists to settings so the user's
        # last choice survives across exports / sessions. Default OFF
        # — clean code is the more common need; AI workflow is opt-in.
        _settings = load_settings()
        self._include_descriptions_var = tk.BooleanVar(
            value=bool(
                _settings.get(SETTING_INCLUDE_DESCRIPTIONS, False),
            ),
        )
        self._open_editor_cb: ctk.CTkCheckBox | None = None
        self._run_preview_cb: ctk.CTkCheckBox | None = None
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
        self._as_zip_var.trace_add(
            "write", lambda *_: self._on_zip_toggle(),
        )

        self.bind("<Return>", lambda _e: self._on_export())
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.after(100, self._center_on_parent)

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
        self._add_row("Format", self._build_format_checkbox)
        self._add_separator()
        self._add_row("Comments", self._build_descriptions_checkbox)
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

    def _build_format_checkbox(self, row) -> None:
        # ZIP output bundles the .py + assets/ + helper modules into
        # one archive — convenient for sharing the export by email or
        # chat. Toggling it disables the After checkboxes (editor /
        # preview don't apply to a .zip).
        wrap = ctk.CTkFrame(row, fg_color="transparent")
        wrap.pack(side="left", fill="x", expand=True)
        zip_row = ctk.CTkFrame(wrap, fg_color="transparent")
        zip_row.pack(fill="x", anchor="w")
        ctk.CTkCheckBox(
            zip_row, text="Export as ZIP archive",
            variable=self._as_zip_var,
            checkbox_width=18, checkbox_height=18,
            font=("Segoe UI", 11),
            text_color=FIELD_FG,
            fg_color="#0e639c", hover_color="#1177bb",
        ).pack(side="left")
        tk.Label(
            zip_row,
            text="Python code + assets bundled into one .zip — easy to share",
            bg=PANEL_BG, fg=PREVIEW_FG,
            font=("Segoe UI", 9, "italic"),
        ).pack(side="left", padx=(10, 0))
        # Asset filter — only meaningful for multi-page projects
        # (legacy projects always copy the whole asset pool).
        if self.project.folder_path:
            filter_row = ctk.CTkFrame(wrap, fg_color="transparent")
            filter_row.pack(fill="x", anchor="w", pady=(4, 0))
            ctk.CTkCheckBox(
                filter_row, text="Include only used assets",
                variable=self._only_used_assets_var,
                checkbox_width=18, checkbox_height=18,
                font=("Segoe UI", 11),
                text_color=FIELD_FG,
                fg_color="#0e639c", hover_color="#1177bb",
            ).pack(side="left")
            tk.Label(
                filter_row,
                text="Skip fonts / images / icons not referenced by the exported pages",
                bg=PANEL_BG, fg=PREVIEW_FG,
                font=("Segoe UI", 9, "italic"),
            ).pack(side="left", padx=(10, 0))

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
        ctk.CTkCheckBox(
            desc_row, text="Include descriptions as comments",
            variable=self._include_descriptions_var,
            checkbox_width=18, checkbox_height=18,
            font=("Segoe UI", 11),
            text_color=FIELD_FG,
            fg_color="#0e639c", hover_color="#1177bb",
        ).pack(side="left")
        tk.Label(
            desc_row,
            text=(
                "Widget descriptions emitted as # lines — "
                "uncheck for clean production code"
            ),
            bg=PANEL_BG, fg=PREVIEW_FG,
            font=("Segoe UI", 9, "italic"),
        ).pack(side="left", padx=(10, 0))

    def _build_after_checkbox(self, row) -> None:
        # Two independent toggles. "Open in editor" routes through the
        # OS edit verb (IDLE / VSCode / Notepad++) — for code review.
        # "Run preview" launches the exported .py exactly like Preview
        # ▶ does — for verifying the result visually.
        self._open_editor_cb = ctk.CTkCheckBox(
            row, text="Open in editor",
            variable=self._open_editor_var,
            checkbox_width=18, checkbox_height=18,
            font=("Segoe UI", 11),
            text_color=FIELD_FG,
            fg_color="#0e639c", hover_color="#1177bb",
        )
        self._open_editor_cb.pack(side="left")
        self._run_preview_cb = ctk.CTkCheckBox(
            row, text="Run preview",
            variable=self._run_preview_var,
            checkbox_width=18, checkbox_height=18,
            font=("Segoe UI", 11),
            text_color=FIELD_FG,
            fg_color="#0e639c", hover_color="#1177bb",
        )
        self._run_preview_cb.pack(side="left", padx=(20, 0))

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
        ext = ".zip" if self._as_zip_var.get() else ".py"
        return Path(directory) / f"{name}{ext}"

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
        # off and on). Refresh the preview so the path extension flips.
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
        if do_editor:
            self._open_exported_file(target)
        if do_preview:
            self._run_exported_preview(target)
        if not (do_editor or do_preview):
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
