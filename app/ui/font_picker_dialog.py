"""Font picker dialog — project-palette + secondary system-font dialog.

The main picker only lists the project's font palette: imported
``.ttf`` / ``.otf`` files inside ``assets/fonts/`` plus system fonts
the user has explicitly added via the secondary picker. Listing
every OS font in the main dialog felt heavy (hundreds of rows on
Windows) and pushed obscure / legacy fonts to the top. Now the user
curates a small palette per project.

Two add paths in the header:
* **+ Import file...** — copy a ``.ttf`` / ``.otf`` from disk into
  ``<project>/assets/fonts/`` (deduped by SHA). Picker auto-selects
  the freshly imported family.
* **+ Add system font...** — opens ``SystemFontPickerDialog`` (the
  full OS font list) and adds the picked family name to
  ``project.system_fonts``. Picker auto-selects it.

The footer carries a scope selector (this widget / All [Type] / All
in project). Result on OK is ``(family: str | None, scope: str)``;
``None`` family means "use default" (clears any per-widget override).
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app.core.assets import copy_to_assets, resolve_asset_token
from app.core.fonts import (
    FONT_EXTS, list_project_fonts, list_system_families,
    register_font_file, resolve_system_font_path,
)
from app.core.logger import log_error
from app.ui.icons import load_tk_icon

HELP_TEXT = (
    "Choose a font family for this widget's text.\n\n"
    "• + Import file — copy a .ttf / .otf from disk into the\n"
    "    project's assets/fonts/ folder. Travels with the\n"
    "    .ctkproj across machines.\n"
    "• + Add system font — pick from the operating system's\n"
    "    fonts and add it to this project's palette. The\n"
    "    family name is saved with the project; users opening\n"
    "    the exported app need the same font installed.\n\n"
    "Apply to:\n"
    "• This widget   — only the selected widget.\n"
    "• All [Type]    — every widget of the same type that\n"
    "    hasn't been overridden one-by-one.\n"
    "• All in project — every text widget that hasn't been\n"
    "    overridden by type or one-by-one.\n\n"
    "Per-widget setting wins, then per-type, then project-wide."
)

BG = "#1e1e1e"
PANEL_BG = "#252526"
HEADER_BG = "#2d2d30"
HEADER_FG = "#cccccc"
DIM_FG = "#888888"
SECTION_FG = "#9aa0a6"
ROW_HOVER = "#2a2a2a"
ROW_SELECTED = "#094771"
DIVIDER = "#3a3a3a"

DIALOG_W = 460
DIALOG_H = 560
PREVIEW_TEXT = "AaBb 123"

SCOPE_WIDGET = "widget"
SCOPE_TYPE = "type"
SCOPE_ALL = "all"


class FontPickerDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        project,
        current: str | None = None,
        type_name: str | None = None,
        type_display: str | None = None,
    ):
        super().__init__(parent)
        self.project = project
        self.project_file = getattr(project, "path", None)
        self.current = current
        self.type_name = type_name
        self.type_display = type_display or type_name or "Type"
        self.result: tuple[str | None, str] | None = None

        self.title("Select font")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.geometry(f"{DIALOG_W}x{DIALOG_H}")
        self._center_on_parent(parent)

        self._selected_family: str | None = current
        self._row_widgets: dict[str, dict] = {}
        self._scope_var = tk.StringVar(value=SCOPE_WIDGET)

        self._build_header()
        self._build_list()
        self._build_footer()

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._on_ok())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.after_idle(self._refresh)

    # ------- layout -------

    def _build_header(self) -> None:
        bar = tk.Frame(self, bg=HEADER_BG)
        bar.pack(fill="x")
        ctk.CTkButton(
            bar, text="+ Import file...", width=140, height=30,
            corner_radius=4,
            command=self._on_import,
        ).pack(side="left", padx=(10, 4), pady=10)
        ctk.CTkButton(
            bar, text="+ Add system font...", width=170, height=30,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_add_system_font,
        ).pack(side="left", padx=(0, 4), pady=10)

        help_img = load_tk_icon("circle-help", size=20, color="#aaaaaa")
        self._help_lbl = tk.Label(
            bar, bg=HEADER_BG, image=help_img if help_img else None,
            text="" if help_img else "?", fg="#cccccc",
            font=("Segoe UI", 12, "bold"), cursor="hand2",
        )
        self._help_lbl.image = help_img  # keep ref
        self._help_lbl.pack(side="right", padx=14, pady=8)
        self._help_lbl.bind("<Enter>", self._show_help)
        self._help_lbl.bind("<Leave>", self._hide_help)
        self._help_lbl.bind("<Button-1>", self._show_help)
        self._tip_window: tk.Toplevel | None = None

    def _build_list(self) -> None:
        wrap = ctk.CTkScrollableFrame(
            self, fg_color=PANEL_BG, corner_radius=0,
        )
        wrap.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        self._list_wrap = wrap

    def _build_footer(self) -> None:
        scope = tk.Frame(self, bg=BG)
        scope.pack(fill="x", padx=10, pady=(4, 4))
        tk.Label(
            scope, text="Apply to:", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left", padx=(0, 8))
        for value, label in (
            (SCOPE_WIDGET, "This widget"),
            (SCOPE_TYPE, f"All {self.type_display}s"),
            (SCOPE_ALL, "All in project"),
        ):
            tk.Radiobutton(
                scope, text=label, variable=self._scope_var, value=value,
                bg=BG, fg=HEADER_FG, selectcolor=BG,
                activebackground=BG, activeforeground="#ffffff",
                font=("Segoe UI", 10), bd=0, highlightthickness=0,
                cursor="hand2",
            ).pack(side="left", padx=(0, 10))

        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=10, pady=(2, 10))
        self._ok_btn = ctk.CTkButton(
            foot, text="OK", width=90, height=30, corner_radius=4,
            command=self._on_ok,
        )
        self._ok_btn.pack(side="right")
        ctk.CTkButton(
            foot, text="Cancel", width=90, height=30, corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))
        ctk.CTkButton(
            foot, text="Use default", width=110, height=30,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_use_default,
        ).pack(side="left")

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

    # ------- list population -------

    def _palette_families(self) -> list[str]:
        """Sorted, deduped family list = imported fonts (already
        registered with Tk via ``register_project_fonts``) plus
        ``project.system_fonts``. Empty list when neither path has
        entries — the picker shows an empty-state hint instead.
        """
        proj = list_project_fonts(self.project_file)
        out: set[str] = {fam for fam, _ in proj}
        out.update(self.project.system_fonts or [])
        return sorted(out, key=str.lower)

    def _refresh(self, select: str | None = None) -> None:
        for child in list(self._list_wrap.winfo_children()):
            try:
                child.destroy()
            except tk.TclError:
                pass
        self._row_widgets.clear()

        families = self._palette_families()
        if not families:
            ctk.CTkLabel(
                self._list_wrap,
                text=(
                    "No fonts in this project yet.\n\n"
                    "• Click + Import file to bundle a .ttf / .otf.\n"
                    "• Click + Add system font to pick from the OS."
                ),
                font=("Segoe UI", 10), text_color=DIM_FG,
                justify="left",
            ).pack(pady=40, padx=20, anchor="w")
            self._set_selected(None)
            return

        for family in families:
            self._build_row(family)

        target = select if select is not None else self._selected_family
        self._set_selected(target)

    def _build_row(self, family: str) -> None:
        row = tk.Frame(self._list_wrap, bg=PANEL_BG, cursor="hand2")
        row.pack(fill="x", padx=2, pady=1)

        name_lbl = tk.Label(
            row, text=family, bg=PANEL_BG, fg="#cccccc",
            font=("Segoe UI", 10), anchor="w",
        )
        name_lbl.pack(side="left", padx=(8, 6), pady=4)

        try:
            preview_font = (family, 13)
            preview_lbl = tk.Label(
                row, text=PREVIEW_TEXT, bg=PANEL_BG, fg="#dddddd",
                font=preview_font, anchor="w",
            )
        except tk.TclError:
            preview_lbl = tk.Label(
                row, text=PREVIEW_TEXT, bg=PANEL_BG, fg="#888888",
                font=("Segoe UI", 11), anchor="w",
            )
        preview_lbl.pack(side="right", padx=8, pady=4)

        for w in (row, name_lbl, preview_lbl):
            w.bind("<Button-1>", lambda _e, f=family: self._set_selected(f))
            w.bind(
                "<Double-Button-1>",
                lambda _e, f=family: self._on_double_click(f),
            )

        self._row_widgets[family] = {
            "row": row, "name": name_lbl, "preview": preview_lbl,
        }

    # ------- selection handling -------

    def _set_selected(self, family: str | None) -> None:
        self._selected_family = family
        for key, widgets in self._row_widgets.items():
            is_sel = family is not None and key == family
            bg = ROW_SELECTED if is_sel else PANEL_BG
            for w in widgets.values():
                try:
                    w.configure(bg=bg)
                except tk.TclError:
                    pass

    def _on_double_click(self, family: str) -> None:
        self._selected_family = family
        self._on_ok()

    # ------- actions -------

    def _on_import(self) -> None:
        if not self.project_file:
            messagebox.showinfo(
                "Save first",
                "Save the project before importing fonts — they're "
                "stored inside the project's assets/fonts/ folder.",
                parent=self,
            )
            return
        src = filedialog.askopenfilename(
            parent=self, title="Import font into project",
            filetypes=[
                ("Font files", "*.ttf *.otf *.ttc"),
                ("All files", "*.*"),
            ],
        )
        if not src:
            return
        if Path(src).suffix.lower() not in FONT_EXTS:
            messagebox.showwarning(
                "Not a font",
                f"{Path(src).name} doesn't look like a font file.",
                parent=self,
            )
            return
        try:
            token = copy_to_assets(src, self.project_file, "fonts")
        except OSError:
            log_error("font picker import")
            messagebox.showerror(
                "Import failed",
                "Could not copy the font into the project's "
                "assets folder.",
                parent=self,
            )
            return
        resolved = resolve_asset_token(token, self.project_file)
        family = (
            register_font_file(resolved, root=self) if resolved else None
        )
        if family is None:
            messagebox.showwarning(
                "Font registered with no family",
                "The file copied into the project, but Tk couldn't "
                "extract a family name. The font may be unsupported.",
                parent=self,
            )
        self._refresh(select=family)

    def _on_add_system_font(self) -> None:
        """Open the secondary system-font picker. On OK, try to copy
        the picked family's actual ``.ttf`` file into the project's
        ``assets/fonts/`` folder so the font travels with the project
        like an imported one. If the file can't be located (rare —
        non-Windows / fontless registry entry), fall back to a bare
        reference in ``project.system_fonts``.
        """
        existing = set(self._palette_families())
        sub = SystemFontPickerDialog(self, exclude=existing)
        sub.wait_window()
        if not sub.result:
            return
        family = sub.result
        copied = False
        if self.project_file:
            ttf_path = resolve_system_font_path(family)
            if ttf_path and ttf_path.exists():
                try:
                    token = copy_to_assets(
                        ttf_path, self.project_file, "fonts",
                    )
                    resolved = resolve_asset_token(
                        token, self.project_file,
                    )
                    if resolved is not None:
                        registered = register_font_file(
                            resolved, root=self,
                        )
                        if registered:
                            family = registered
                        copied = True
                except OSError:
                    log_error("font picker add system font copy")
        if not copied:
            if family not in self.project.system_fonts:
                self.project.system_fonts = sorted(
                    set(self.project.system_fonts or []) | {family},
                )
        self._refresh(select=family)

    def _on_ok(self) -> None:
        self.result = (self._selected_family, self._scope_var.get())
        self._hide_help()
        self.destroy()

    def _on_use_default(self) -> None:
        self.result = (None, self._scope_var.get())
        self._hide_help()
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self._hide_help()
        self.destroy()

    # ------- help tooltip -------

    def _show_help(self, _event=None) -> None:
        if self._tip_window is not None:
            return
        try:
            x = self._help_lbl.winfo_rootx() - 280
            y = self._help_lbl.winfo_rooty() + 24
        except tk.TclError:
            return
        tip = tk.Toplevel(self)
        tip.overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        tip.configure(bg="#1c1c1c")
        frame = tk.Frame(tip, bg="#1c1c1c", padx=10, pady=8)
        frame.pack()
        tk.Label(
            frame, text=HELP_TEXT, bg="#1c1c1c", fg="#dddddd",
            font=("Segoe UI", 11), justify="left", anchor="w",
        ).pack()
        tip.geometry(f"+{max(0, x)}+{y}")
        self._tip_window = tip

    def _hide_help(self, _event=None) -> None:
        if self._tip_window is not None:
            try:
                self._tip_window.destroy()
            except tk.TclError:
                pass
            self._tip_window = None


# ---------------------------------------------------------------------------
# Secondary dialog — full system-font list
# ---------------------------------------------------------------------------

SYS_DIALOG_W = 460
SYS_DIALOG_H = 600


class SystemFontPickerDialog(tk.Toplevel):
    """Pick from the operating system's installed fonts. Returns the
    family name in ``self.result`` on OK or ``None`` on Cancel.
    """

    def __init__(self, parent, exclude: set[str] | None = None):
        super().__init__(parent)
        self.exclude = set(exclude or [])
        self.result: str | None = None

        self.title("Add system font")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.geometry(f"{SYS_DIALOG_W}x{SYS_DIALOG_H}")
        self._center_on_parent(parent)

        self._selected_family: str | None = None
        self._row_widgets: dict[str, dict] = {}

        self._build_header()
        self._build_list()
        self._build_footer()

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._on_ok())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.after_idle(self._refresh)

    def _center_on_parent(self, parent) -> None:
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + (pw - SYS_DIALOG_W) // 2
            y = py + (ph - SYS_DIALOG_H) // 2
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            pass

    def _build_header(self) -> None:
        bar = tk.Frame(self, bg=HEADER_BG)
        bar.pack(fill="x")
        tk.Label(
            bar, text="System fonts", bg=HEADER_BG, fg=HEADER_FG,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left", padx=12, pady=8)
        # Search entry — narrows the long OS list to substring matches.
        self._search_var = tk.StringVar()
        entry = tk.Entry(
            bar, textvariable=self._search_var,
            bg="#1e1e1e", fg="#cccccc", insertbackground="#cccccc",
            relief="flat", bd=1, font=("Segoe UI", 10),
            highlightthickness=1, highlightbackground="#3a3a3a",
            highlightcolor="#3b8ed0",
        )
        entry.pack(side="right", padx=12, pady=8, ipady=3, fill="x", expand=True)
        self._search_var.trace_add("write", lambda *_: self._refresh())

    def _build_list(self) -> None:
        wrap = ctk.CTkScrollableFrame(
            self, fg_color=PANEL_BG, corner_radius=0,
        )
        wrap.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        self._list_wrap = wrap

    def _build_footer(self) -> None:
        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=10, pady=(4, 10))
        self._ok_btn = ctk.CTkButton(
            foot, text="Add", width=90, height=30, corner_radius=4,
            command=self._on_ok, state="disabled",
        )
        self._ok_btn.pack(side="right")
        ctk.CTkButton(
            foot, text="Cancel", width=90, height=30, corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))

    def _refresh(self) -> None:
        for child in list(self._list_wrap.winfo_children()):
            try:
                child.destroy()
            except tk.TclError:
                pass
        self._row_widgets.clear()

        families = list_system_families(self)
        # Drop @-prefixed CJK vertical-text variants (legacy / niche).
        families = [f for f in families if not f.startswith("@")]
        if self.exclude:
            families = [f for f in families if f not in self.exclude]
        query = (self._search_var.get() or "").strip().lower()
        if query:
            families = [f for f in families if query in f.lower()]

        if not families:
            ctk.CTkLabel(
                self._list_wrap,
                text="No matching system fonts.",
                font=("Segoe UI", 10), text_color=DIM_FG,
            ).pack(pady=40)
            self._set_selected(None)
            return

        for family in families:
            self._build_row(family)

        self._set_selected(None)

    def _build_row(self, family: str) -> None:
        row = tk.Frame(self._list_wrap, bg=PANEL_BG, cursor="hand2")
        row.pack(fill="x", padx=2, pady=1)
        name_lbl = tk.Label(
            row, text=family, bg=PANEL_BG, fg="#cccccc",
            font=("Segoe UI", 10), anchor="w",
        )
        name_lbl.pack(side="left", padx=(8, 6), pady=4)
        try:
            preview_font = (family, 13)
            preview_lbl = tk.Label(
                row, text=PREVIEW_TEXT, bg=PANEL_BG, fg="#dddddd",
                font=preview_font, anchor="w",
            )
        except tk.TclError:
            preview_lbl = tk.Label(
                row, text=PREVIEW_TEXT, bg=PANEL_BG, fg="#888888",
                font=("Segoe UI", 11), anchor="w",
            )
        preview_lbl.pack(side="right", padx=8, pady=4)
        for w in (row, name_lbl, preview_lbl):
            w.bind("<Button-1>", lambda _e, f=family: self._set_selected(f))
            w.bind(
                "<Double-Button-1>",
                lambda _e, f=family: self._on_double_click(f),
            )
        self._row_widgets[family] = {
            "row": row, "name": name_lbl, "preview": preview_lbl,
        }

    def _set_selected(self, family: str | None) -> None:
        self._selected_family = family
        for key, widgets in self._row_widgets.items():
            is_sel = family is not None and key == family
            bg = ROW_SELECTED if is_sel else PANEL_BG
            for w in widgets.values():
                try:
                    w.configure(bg=bg)
                except tk.TclError:
                    pass
        try:
            self._ok_btn.configure(
                state="normal" if family is not None else "disabled",
            )
        except tk.TclError:
            pass

    def _on_double_click(self, family: str) -> None:
        self._selected_family = family
        self._on_ok()

    def _on_ok(self) -> None:
        if self._selected_family is None:
            return
        self.result = self._selected_family
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()
