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
from typing import Any

import customtkinter as ctk

from app.core.assets import copy_to_assets, resolve_asset_token
from app.core.fonts import (
    FONT_EXTS, list_project_fonts, list_system_families,
    register_font_file, resolve_system_font_path,
)
from app.ui.system_fonts import ui_font
from app.core.logger import log_error
from app.ui.dialog_utils import prepare_dialog, reveal_dialog, safe_grab_set
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

DIALOG_W = 540
DIALOG_H = 720
PREVIEW_TEXT = "AaBb 123"
# Sizes used by the preview pane below the palette list. Two
# rows kept narrow on purpose — every extra row risks pushing the
# scope radios + OK / Cancel under tall script fonts.
PREVIEW_SIZES = (13, 24)

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
        prepare_dialog(self)
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
        safe_grab_set(self)

        self.geometry(f"{DIALOG_W}x{DIALOG_H}")
        self._center_on_parent(parent)

        self._selected_family: str | None = current
        self._row_widgets: dict[str, dict] = {}
        self._scope_var = tk.StringVar(value=SCOPE_WIDGET)
        # ``family -> Path`` cache populated by ``_refresh`` from
        # ``list_project_fonts``. Used by the right-click "Remove
        # from project" path so we know which file (if any) to delete.
        self._family_paths: dict[str, Path] = {}
        # Editable preview text — defaults to the row sample. The
        # entry below the palette list lets the user type real
        # content and see it in the chosen font live.
        self._preview_var = tk.StringVar(value=PREVIEW_TEXT)
        self._preview_var.trace_add(
            "write", lambda *_a: self._refresh_preview(),
        )
        self._preview_labels: list[tk.Label] = []

        # Layout order (top → bottom): header buttons, live preview
        # (just under the action buttons so it's the first thing
        # the eye lands on), palette list (absorbs the slack), scope
        # segmented control, footer with Reset / Cancel / Apply.
        # Footer + scope pack ``side="bottom"`` so they're always
        # visible — the list shrinks before the action row gets
        # pushed below the visible region.
        self._build_header()
        self._build_preview()
        self._build_footer()
        self._build_list()

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._on_ok())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        reveal_dialog(self)
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
            bar, bg=HEADER_BG, image=help_img if help_img else "",
            text="" if help_img else "?", fg="#cccccc",
            font=ui_font(12, "bold"), cursor="hand2",
        )
        self._help_lbl.image = help_img  # type: ignore[attr-defined]  # keep ref
        self._help_lbl.pack(side="right", padx=14, pady=8)
        self._help_lbl.bind("<Enter>", self._show_help)
        self._help_lbl.bind("<Leave>", self._hide_help)
        self._help_lbl.bind("<Button-1>", self._show_help)
        self._tip_window: tk.Toplevel | None = None

    def _build_list(self) -> None:
        wrap = ctk.CTkScrollableFrame(
            self, fg_color=PANEL_BG, corner_radius=0,
        )
        # ``side="top"`` here (after footer/preview claim bottom
        # space) means the list takes whatever's left between header
        # and preview — exactly the slack we want it to absorb.
        wrap.pack(side="top", fill="both", expand=True,
                  padx=8, pady=(8, 4))
        self._list_wrap = wrap

    def _build_preview(self) -> None:
        """Live preview directly under the import buttons — the user
        sees how their currently-selected family looks before
        scrolling through the list. Fixed pixel height with
        ``pack_propagate(False)`` so swapping in a tall script font
        doesn't grow the dialog (the previous flow auto-resized,
        which felt jarring while clicking through families).
        """
        # tk.Frame instead of CTkFrame here so pack_propagate(False)
        # is reliably supported — CTkFrame's geometry knobs can
        # silently restore propagation on theme reapply.
        wrap = tk.Frame(self, bg=PANEL_BG, height=110)
        wrap.pack(side="top", fill="x", padx=8, pady=(8, 0))
        wrap.pack_propagate(False)

        head = tk.Frame(wrap, bg=PANEL_BG)
        head.pack(fill="x", padx=6, pady=(4, 2))
        tk.Label(
            head, text="Preview", bg=PANEL_BG, fg=HEADER_FG,
            font=ui_font(9, "bold"),
        ).pack(side="left")
        entry = tk.Entry(
            head, textvariable=self._preview_var,
            bg="#1e1e1e", fg="#cccccc", insertbackground="#cccccc",
            relief="flat", bd=1, font=ui_font(10),
            highlightthickness=1, highlightbackground="#3a3a3a",
            highlightcolor="#3b8ed0",
        )
        entry.pack(side="right", fill="x", expand=True, padx=(8, 0), ipady=2)

        self._preview_body = tk.Frame(wrap, bg=PANEL_BG)
        # Body also pinned — labels grow with font size, but the
        # body frame's fixed height contains them so neighbours
        # don't shift.
        self._preview_body.pack(fill="x", padx=6, pady=(2, 6))
        for size in PREVIEW_SIZES:
            lbl = tk.Label(
                self._preview_body,
                text=PREVIEW_TEXT, bg=PANEL_BG, fg="#dddddd",
                font=ui_font(size), anchor="w", justify="left",
            )
            lbl.pack(fill="x", pady=1)
            self._preview_labels.append(lbl)

    def _refresh_preview(self) -> None:
        """Push the current sample text + selected family into every
        preview label. Falls back to a UI-default font for readable
        empty-state when nothing's selected.
        """
        text = self._preview_var.get() or PREVIEW_TEXT
        family = self._selected_family
        for lbl, size in zip(self._preview_labels, PREVIEW_SIZES):
            font_tuple = (family, size) if family else ui_font(size)
            try:
                lbl.configure(text=text, font=font_tuple)
            except tk.TclError:
                pass

    def _build_footer(self) -> None:
        # Pack ``foot`` (Reset / Cancel / Apply) BEFORE ``scope_wrap``
        # — both pack ``side="bottom"`` and Tk's pack manager makes
        # earlier ``bottom`` siblings sit lowest. Visually ends up
        # top→bottom: scope segmented → action buttons.
        scope_wrap = tk.Frame(self, bg=BG)
        tk.Label(
            scope_wrap, text="Apply to:", bg=BG, fg=HEADER_FG,
            font=ui_font(10, "bold"), anchor="w",
        ).pack(fill="x", pady=(0, 4))
        scope_labels = (
            "Just this widget",
            f"All {self.type_display}s",
            "Whole project",
        )
        scope_to_value = {
            scope_labels[0]: SCOPE_WIDGET,
            scope_labels[1]: SCOPE_TYPE,
            scope_labels[2]: SCOPE_ALL,
        }
        self._scope_segmented = ctk.CTkSegmentedButton(
            scope_wrap, values=list(scope_labels),
            font=ui_font(10),
            height=32,
            # Match the dialog frame's rounded look — sharp 4px
            # buttons inside a softer container felt off.
            corner_radius=10,
            command=lambda lbl: self._scope_var.set(
                scope_to_value.get(lbl, SCOPE_WIDGET),
            ),
        )
        self._scope_segmented.pack(fill="x")
        # Initialise the segment from the StringVar default
        # (SCOPE_WIDGET) so the visual state matches.
        value_to_scope = {v: k for k, v in scope_to_value.items()}
        self._scope_segmented.set(
            value_to_scope.get(self._scope_var.get(), scope_labels[0]),
        )

        foot = tk.Frame(self, bg=BG)
        # Pack ``foot`` first → bottommost; ``scope_wrap`` packs
        # second → sits just above the buttons.
        foot.pack(side="bottom", fill="x", padx=10, pady=(10, 14))
        scope_wrap.pack(side="bottom", fill="x", padx=10, pady=(6, 4))
        # Grid layout — explicit column placement, no pack quirks.
        # Column 1 is a flexible spacer that absorbs the gap between
        # Reset (left) and Cancel + Apply (right). Each button keeps
        # its declared pixel width regardless of dialog width changes.
        foot.grid_columnconfigure(0, weight=0)  # Reset
        foot.grid_columnconfigure(1, weight=1)  # flexible spacer
        foot.grid_columnconfigure(2, weight=0)  # Cancel
        foot.grid_columnconfigure(3, weight=0)  # Apply
        # Hierarchy: Reset (tertiary, smallest) → Cancel (secondary)
        # → Apply (primary, widest). Visual weight matches each
        # action's importance.
        btn_kw: dict[str, Any] = {
            "height": 32, "corner_radius": 10, "font": ui_font(10),
        }
        ctk.CTkButton(
            foot, text="Reset", width=70,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_use_default, **btn_kw,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            foot, text="Cancel", width=90,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel, **btn_kw,
        ).grid(row=0, column=2, padx=(0, 8))
        self._ok_btn = ctk.CTkButton(
            foot, text="Apply", width=140,
            command=self._on_ok, **btn_kw,
        )
        self._ok_btn.grid(row=0, column=3, sticky="e")

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
        Side effect: refreshes ``self._family_paths`` so the
        right-click "Remove" path knows which families have a
        backing file in ``assets/fonts/``.
        """
        proj = list_project_fonts(self.project_file)
        self._family_paths = {fam: path for fam, path in proj}
        out: set[str] = set(self._family_paths.keys())
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
                font=ui_font(10), text_color=DIM_FG,
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
            font=ui_font(10), anchor="w",
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
                font=ui_font(11), anchor="w",
            )
        preview_lbl.pack(side="right", padx=8, pady=4)

        for w in (row, name_lbl, preview_lbl):
            w.bind("<Button-1>", lambda _e, f=family: self._set_selected(f))
            w.bind(
                "<Double-Button-1>",
                lambda _e, f=family: self._on_double_click(f),
            )
            w.bind(
                "<Button-3>",
                lambda e, f=family: self._on_row_right_click(e, f),
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
        self._refresh_preview()

    # ------- row context menu (Remove from project) -------

    def _on_row_right_click(self, event, family: str) -> None:
        self._set_selected(family)
        menu = tk.Menu(
            self, tearoff=0,
            bg="#2d2d30", fg=HEADER_FG,
            activebackground="#094771", activeforeground="#ffffff",
            relief="flat", bd=0, font=ui_font(10),
        )
        menu.add_command(
            label=f"Remove '{family}' from project...",
            command=lambda: self._remove_palette_family(family),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _remove_palette_family(self, family: str) -> None:
        """Drop a family from the project palette. Imported fonts
        (have a file in ``assets/fonts/``) get the file deleted —
        Asset panel + filesystem stay in sync. Bare references in
        ``project.system_fonts`` just lose the entry. Picker
        refreshes immediately; widgets that pointed at this family
        fall back to Tk default at next render.
        """
        file_path = self._family_paths.get(family)
        if not messagebox.askyesno(
            "Remove from project",
            f"Remove '{family}' from this project?\n\n"
            + (
                f"File: {file_path}\n\n"
                "The .ttf/.otf is deleted from disk."
                if file_path else
                "Reference only — no file to delete.\n"
            )
            + "\nThis cannot be undone. Widgets that referenced "
            "this family fall back to a default at next render.",
            parent=self,
            icon="warning",
        ):
            return
        # Delete the file (if any) before scrubbing references so a
        # later "still in fonts list" check doesn't see a phantom.
        if file_path and file_path.exists():
            try:
                file_path.unlink()
            except OSError:
                log_error("font picker remove unlink")
                messagebox.showerror(
                    "Remove failed",
                    f"Couldn't delete:\n{file_path}",
                    parent=self,
                )
                return
        from app.core.fonts import purge_family_from_project
        purge_family_from_project(self.project, family)
        self.project.event_bus.publish(
            "font_defaults_changed", self.project.font_defaults,
        )
        self.project.event_bus.publish("dirty_changed", True)
        # If the removed family was the picker's current selection,
        # drop it so OK doesn't try to commit a deleted family.
        if self._selected_family == family:
            self._selected_family = None
        self._refresh()

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
        # Wake up any docked / floating Assets panel that's listening —
        # without this the new file lands on disk but the tree shows
        # stale contents until the next manual refresh.
        self.project.event_bus.publish("dirty_changed", True)
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
        # Either a new file landed in assets/fonts/ (the copied path)
        # or system_fonts grew — both move the project's "dirty" state
        # and any listening Assets panel needs the nudge.
        self.project.event_bus.publish("dirty_changed", True)
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
            font=ui_font(11), justify="left", anchor="w",
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
        prepare_dialog(self)
        self.exclude = set(exclude or [])
        self.result: str | None = None

        self.title("Add system font")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        safe_grab_set(self)
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

        reveal_dialog(self)
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
            font=ui_font(11, "bold"),
        ).pack(side="left", padx=12, pady=8)
        # Search entry — narrows the long OS list to substring matches.
        self._search_var = tk.StringVar()
        entry = tk.Entry(
            bar, textvariable=self._search_var,
            bg="#1e1e1e", fg="#cccccc", insertbackground="#cccccc",
            relief="flat", bd=1, font=ui_font(10),
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
                font=ui_font(10), text_color=DIM_FG,
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
            font=ui_font(10), anchor="w",
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
                font=ui_font(11), anchor="w",
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
