"""Preferences dialog — exposes the keys persisted in
``~/.ctk_visual_builder/settings.json`` through a tabbed UI.

Tabs:
    - Appearance: theme (currently disabled — full Light theme polish
      pending; the toolbar toggle still works for ad-hoc switching).
    - Defaults: New Project save location + width × height.
    - Autosave: interval in minutes.
    - Notifications: reset dismissed advisory warnings.

Most of the settings infrastructure already existed (autosave reads
``autosave_interval_minutes``, advisories reset via
``app.core.settings``); this dialog gathers them into one
discoverable place and adds the two New-Project defaults.

Open via ``Settings → Preferences...`` or ``Ctrl+,``.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import customtkinter as ctk

from app.core.settings import load_settings, save_setting

DIALOG_W = 600
DIALOG_H = 500

BG = "#1e1e1e"
PANEL_BG = "#252526"
HEADER_BG = "#2d2d30"
HEADER_FG = "#cccccc"
SECTION_FG = "#bbbbbb"
DIM_FG = "#888888"
ENTRY_BORDER = "#3c3c3c"

THEME_OPTIONS = ("Dark", "Light", "System")
GRID_STYLE_OPTIONS = ("dots", "lines", "none")
DEFAULT_AUTOSAVE_MIN = 5
DEFAULT_PROJECT_W = 800
DEFAULT_PROJECT_H = 600
DEFAULT_GRID_STYLE = "dots"
DEFAULT_GRID_COLOR = "#555555"
DEFAULT_GRID_SPACING = 20

# Keys mirrored from app/core/settings.py call sites.
KEY_THEME = "appearance_mode"
KEY_AUTOSAVE = "autosave_interval_minutes"
KEY_DEFAULT_DIR = "default_projects_dir"
KEY_DEFAULT_W = "default_project_width"
KEY_DEFAULT_H = "default_project_height"
KEY_GRID_STYLE = "grid_style"
KEY_GRID_COLOR = "grid_color"
KEY_GRID_SPACING = "grid_spacing"
KEY_EDITOR_COMMAND = "editor_command"
KEY_PREVIEW_FLOATER = "preview_show_floater"
KEY_PREVIEW_CONSOLE = "preview_show_console"

# Editor presets — labelled command templates for common Windows
# editors. ``{file}`` and ``{line}`` are substituted by
# ``app.io.scripts.launch_editor`` at click time. The empty string
# means "auto-detect" (try VS Code on PATH, fall back to OS default).
EDITOR_PRESETS: tuple[tuple[str, str], ...] = (
    # Auto = try VS Code, then Notepad++ (Windows), then IDLE.
    # The runtime walks this fallback chain in
    # ``app.io.scripts.launch_editor`` — the empty template signals
    # "no preset, use auto-detect".
    ("Auto (VS Code → Notepad++ → IDLE)", ""),
    # ``{folder}`` opens the project root as a workspace so the
    # Python extension activates and IntelliSense resolves
    # CTkMaker / customtkinter imports. ``-g`` then jumps to the
    # method line inside that workspace.
    ("VS Code", 'code "{folder}" -g "{file}:{line}"'),
    ("Notepad++", 'notepad++ -n{line} "{file}"'),
    # IDLE always works — ``{python}`` resolves to the same
    # interpreter running CTkMaker (``sys.executable``), so the
    # preset doesn't depend on a PATH-visible ``python`` shim.
    ("IDLE (Python's built-in editor)", '{python} -m idlelib "{file}"'),
)

# Dark-themed CTkOptionMenu palette so the dropdowns inside the
# Settings dialog don't render with CTk's default light-grey button
# colour against the dark surrounding panels.
_DROPDOWN_STYLE = dict(
    fg_color="#3c3c3c",
    button_color="#3c3c3c",
    button_hover_color="#4a4a4a",
    text_color="#cccccc",
    dropdown_fg_color="#2d2d30",
    dropdown_hover_color="#094771",
    dropdown_text_color="#cccccc",
)


class SettingsDialog(tk.Toplevel):
    """Preferences window. ``on_appearance_change`` is reserved for
    when the theme tab gets re-enabled; it is currently not invoked
    because the theme dropdown is disabled.
    """

    def __init__(
        self, parent, on_appearance_change=None,
        on_workspace_changed=None,
    ):
        super().__init__(parent)
        self._on_appearance_change = on_appearance_change
        self._on_workspace_changed = on_workspace_changed

        self.title("Preferences")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.geometry(f"{DIALOG_W}x{DIALOG_H}")
        self._center_on_parent(parent)

        self._initial = load_settings()

        self._configure_ttk_style()
        self._build()

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._on_ok())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    # ------------------------------------------------------------------
    # Style
    # ------------------------------------------------------------------
    def _configure_ttk_style(self) -> None:
        # Dark notebook tabs to match the rest of the dialog.
        style = ttk.Style(self)
        style_name = "Settings.TNotebook"
        tab_style = "Settings.TNotebook.Tab"
        try:
            style.theme_use("default")
        except tk.TclError:
            pass
        style.configure(
            style_name,
            background=BG, borderwidth=0,
            tabmargins=(8, 8, 8, 0),
        )
        style.configure(
            tab_style,
            background=PANEL_BG, foreground=HEADER_FG,
            padding=(16, 8),
            font=("Segoe UI", 10),
            borderwidth=0,
        )
        style.map(
            tab_style,
            background=[("selected", "#094771")],
            foreground=[("selected", "#ffffff")],
        )

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True)

        notebook = ttk.Notebook(outer, style="Settings.TNotebook")
        notebook.pack(fill="both", expand=True, padx=12, pady=(12, 6))
        self._notebook = notebook

        notebook.add(self._build_defaults(notebook), text="Defaults")
        notebook.add(self._build_workspace(notebook), text="Workspace")
        notebook.add(self._build_editor(notebook), text="Editor")
        notebook.add(self._build_preview(notebook), text="Preview")
        notebook.add(self._build_autosave(notebook), text="Autosave")
        notebook.add(
            self._build_notifications(notebook), text="Notifications",
        )
        notebook.add(self._build_appearance(notebook), text="Appearance")

        self._build_footer()

    def _tab_frame(self, parent: tk.Misc) -> tk.Frame:
        f = tk.Frame(parent, bg=BG, padx=22, pady=20)
        return f

    def _section_label(self, parent: tk.Misc, text: str) -> tk.Label:
        return tk.Label(
            parent, text=text, bg=BG, fg=SECTION_FG,
            font=("Segoe UI", 11, "bold"), anchor="w",
        )

    def _hint(self, parent: tk.Misc, text: str) -> tk.Label:
        return tk.Label(
            parent, text=text, bg=BG, fg=DIM_FG,
            font=("Segoe UI", 9), anchor="w", justify="left",
            wraplength=DIALOG_W - 80,
        )

    # ----- Appearance tab -----

    def _build_appearance(self, parent: tk.Misc) -> tk.Frame:
        tab = self._tab_frame(parent)
        self._section_label(tab, "Theme").pack(anchor="w")
        row = tk.Frame(tab, bg=BG)
        row.pack(anchor="w", pady=(8, 4))
        tk.Label(
            row, text="Mode:", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 10), width=12, anchor="w",
        ).pack(side="left")
        self._theme_var = tk.StringVar(
            value=self._initial.get(KEY_THEME, "Dark"),
        )
        # Disabled until the Light theme polish lands — leaving it
        # visible keeps the user's mental model of where the option is.
        self._theme_menu = ctk.CTkOptionMenu(
            row, values=list(THEME_OPTIONS), width=160, height=28,
            variable=self._theme_var, dynamic_resizing=False,
            state="disabled",
            **_DROPDOWN_STYLE,
        )
        self._theme_menu.pack(side="left", padx=(8, 0))
        self._hint(
            tab,
            "Theme switching is being polished; coming soon. Use the "
            "toolbar toggle if you need to switch ad-hoc in the meantime.",
        ).pack(anchor="w", pady=(8, 0))
        return tab

    # ----- Defaults tab -----

    def _build_defaults(self, parent: tk.Misc) -> tk.Frame:
        tab = self._tab_frame(parent)
        self._section_label(tab, "New Project").pack(anchor="w")

        loc_row = tk.Frame(tab, bg=BG)
        loc_row.pack(fill="x", pady=(10, 6))
        tk.Label(
            loc_row, text="Save location:", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 10), width=14, anchor="w",
        ).pack(side="left")
        self._dir_var = tk.StringVar(
            value=self._initial.get(KEY_DEFAULT_DIR)
            or str(Path.home() / "Documents" / "CTkMaker"),
        )
        ctk.CTkEntry(
            loc_row, textvariable=self._dir_var,
            width=300, height=28,
        ).pack(side="left", padx=(8, 6))
        ctk.CTkButton(
            loc_row, text="Browse...", width=80, height=28,
            corner_radius=4, fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_browse_dir,
        ).pack(side="left")

        size_row = tk.Frame(tab, bg=BG)
        size_row.pack(fill="x")
        tk.Label(
            size_row, text="Project size:", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 10), width=14, anchor="w",
        ).pack(side="left")
        self._w_var = tk.StringVar(
            value=str(
                self._initial.get(KEY_DEFAULT_W) or DEFAULT_PROJECT_W,
            ),
        )
        ctk.CTkEntry(
            size_row, textvariable=self._w_var, width=80, height=28,
        ).pack(side="left", padx=(8, 4))
        tk.Label(
            size_row, text="×", bg=BG, fg=DIM_FG,
            font=("Segoe UI", 11),
        ).pack(side="left")
        self._h_var = tk.StringVar(
            value=str(
                self._initial.get(KEY_DEFAULT_H) or DEFAULT_PROJECT_H,
            ),
        )
        ctk.CTkEntry(
            size_row, textvariable=self._h_var, width=80, height=28,
        ).pack(side="left", padx=(4, 0))
        tk.Label(
            size_row, text="px", bg=BG, fg=DIM_FG,
            font=("Segoe UI", 10),
        ).pack(side="left", padx=(6, 0))

        self._hint(
            tab,
            "These defaults are used by the Welcome screen on launch. "
            "File → New always uses the active project's dimensions "
            "as a starting point.",
        ).pack(anchor="w", pady=(14, 0))
        return tab

    def _on_browse_dir(self) -> None:
        current = self._dir_var.get().strip()
        path = filedialog.askdirectory(
            parent=self, title="Default project save location",
            initialdir=current if current and Path(current).is_dir()
            else str(Path.home()),
        )
        if path:
            self._dir_var.set(path)

    # ----- Workspace tab -----

    def _build_workspace(self, parent: tk.Misc) -> tk.Frame:
        tab = self._tab_frame(parent)
        self._section_label(tab, "Builder grid").pack(anchor="w")

        style_row = tk.Frame(tab, bg=BG)
        style_row.pack(fill="x", pady=(10, 6))
        tk.Label(
            style_row, text="Style:", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 10), width=14, anchor="w",
        ).pack(side="left")
        self._grid_style_var = tk.StringVar(
            value=str(
                self._initial.get(KEY_GRID_STYLE) or DEFAULT_GRID_STYLE,
            ),
        )
        ctk.CTkOptionMenu(
            style_row, values=list(GRID_STYLE_OPTIONS),
            variable=self._grid_style_var,
            width=160, height=28, dynamic_resizing=False,
            **_DROPDOWN_STYLE,
        ).pack(side="left", padx=(8, 0))

        color_row = tk.Frame(tab, bg=BG)
        color_row.pack(fill="x", pady=(0, 6))
        tk.Label(
            color_row, text="Color:", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 10), width=14, anchor="w",
        ).pack(side="left")
        self._grid_color_var = tk.StringVar(
            value=str(
                self._initial.get(KEY_GRID_COLOR) or DEFAULT_GRID_COLOR,
            ),
        )
        ctk.CTkEntry(
            color_row, textvariable=self._grid_color_var,
            width=110, height=28,
        ).pack(side="left", padx=(8, 6))
        self._grid_swatch = tk.Frame(
            color_row, bg=self._grid_color_var.get(),
            width=24, height=24, relief="solid", bd=1, cursor="hand2",
        )
        self._grid_swatch.pack(side="left")
        self._grid_swatch.bind(
            "<Button-1>", lambda _e: self._pick_grid_color(),
        )
        self._grid_color_var.trace_add(
            "write", lambda *_: self._sync_grid_swatch(),
        )

        spacing_row = tk.Frame(tab, bg=BG)
        spacing_row.pack(fill="x")
        tk.Label(
            spacing_row, text="Spacing (px):", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 10), width=14, anchor="w",
        ).pack(side="left")
        self._grid_spacing_var = tk.StringVar(
            value=str(
                self._initial.get(KEY_GRID_SPACING) or DEFAULT_GRID_SPACING,
            ),
        )
        ctk.CTkEntry(
            spacing_row, textvariable=self._grid_spacing_var,
            width=80, height=28,
        ).pack(side="left", padx=(8, 0))

        self._hint(
            tab,
            "Applies to every document in every project. Each document's "
            "own Window Settings grid controls are kept (loadable .ctkproj "
            "files still carry them) but are overridden globally as long "
            "as these values are set.",
        ).pack(anchor="w", pady=(14, 0))
        return tab

    def _pick_grid_color(self) -> None:
        try:
            from ctk_color_picker import ColorPickerDialog
        except ImportError:
            return
        dlg = ColorPickerDialog(
            self, initial_color=self._grid_color_var.get().strip()
            or DEFAULT_GRID_COLOR,
        )
        dlg.wait_window()
        new = getattr(dlg, "result", None)
        if not new:
            return
        self._grid_color_var.set(new)

    def _sync_grid_swatch(self) -> None:
        value = self._grid_color_var.get().strip()
        if not value.startswith("#") or len(value) not in (4, 7):
            return
        try:
            self._grid_swatch.configure(bg=value)
        except tk.TclError:
            pass

    # ----- Editor tab -----

    def _build_editor(self, parent: tk.Misc) -> tk.Frame:
        """Behavior-file editor preference. The picker drops a
        labelled preset into the command template; the textbox
        underneath stays editable so power users can tweak the
        flags or point at an editor that isn't on the preset list.
        """
        tab = self._tab_frame(parent)
        self._section_label(tab, "External editor").pack(anchor="w")

        current_cmd = str(
            self._initial.get(KEY_EDITOR_COMMAND) or "",
        ).strip()
        # Match the current command against the preset list — if it
        # matches, the dropdown surfaces the friendly label; if not,
        # we surface the special ``Custom`` entry so the user knows
        # the textbox holds something they hand-edited.
        preset_label = self._editor_preset_label_for(current_cmd)
        self._editor_preset_var = tk.StringVar(value=preset_label)

        preset_row = tk.Frame(tab, bg=BG)
        preset_row.pack(fill="x", pady=(10, 6))
        tk.Label(
            preset_row, text="Editor:", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 10), width=14, anchor="w",
        ).pack(side="left")
        ctk.CTkOptionMenu(
            preset_row,
            values=[label for label, _ in EDITOR_PRESETS] + ["Custom"],
            variable=self._editor_preset_var,
            command=self._on_editor_preset_change,
            width=320, height=28, dynamic_resizing=False,
            **_DROPDOWN_STYLE,
        ).pack(side="left", padx=(8, 0))

        cmd_row = tk.Frame(tab, bg=BG)
        cmd_row.pack(fill="x", pady=(0, 6))
        tk.Label(
            cmd_row, text="Command:", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 10), width=14, anchor="w",
        ).pack(side="left")
        self._editor_cmd_var = tk.StringVar(value=current_cmd)
        # Manual edits should flip the preset label to "Custom" so
        # the dropdown stays honest about what the textbox holds.
        self._editor_cmd_var.trace_add(
            "write", lambda *_: self._sync_editor_preset_from_cmd(),
        )
        cmd_entry = ctk.CTkEntry(
            cmd_row, textvariable=self._editor_cmd_var,
            width=420, height=28,
        )
        cmd_entry.pack(side="left", padx=(8, 0))

        self._hint(
            tab,
            "Used by Properties › Events ▸ double-click and the canvas "
            "right-click cascade. \"Auto\" tries VS Code → Notepad++ → "
            "IDLE in order. ``{file}`` is replaced with the path; "
            "``{line}`` with the method's line number; ``{folder}`` "
            "with the project root.",
        ).pack(anchor="w", pady=(14, 0))

        # Recommendation block — VS Code is what we test against
        # most heavily and what the planned CTkMaker extension will
        # plug into. The download link is a clickable text label so
        # the user can grab it without leaving the dialog.
        rec_frame = tk.Frame(tab, bg=BG)
        rec_frame.pack(anchor="w", pady=(18, 0), fill="x")
        tk.Label(
            rec_frame,
            text="★ Recommended:  VS Code",
            bg=BG, fg="#7dd3fc",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            rec_frame,
            text=(
                "Best fit for CTkMaker — Python tooling, integrated "
                "terminal, and a dedicated CTkMaker extension is on "
                "the roadmap."
            ),
            bg=BG, fg=DIM_FG, font=("Segoe UI", 9),
            anchor="w", justify="left",
            wraplength=DIALOG_W - 80,
        ).pack(anchor="w", pady=(2, 4))
        link_lbl = tk.Label(
            rec_frame,
            text="https://code.visualstudio.com/download",
            bg=BG, fg="#5eb3ff",
            font=("Segoe UI", 9, "underline"),
            anchor="w", cursor="hand2",
        )
        link_lbl.pack(anchor="w")
        link_lbl.bind(
            "<Button-1>",
            lambda _e: self._open_vs_code_download(),
        )
        return tab

    def _open_vs_code_download(self) -> None:
        import webbrowser
        try:
            webbrowser.open("https://code.visualstudio.com/download")
        except Exception:
            pass

    def _editor_preset_label_for(self, cmd: str) -> str:
        cmd = (cmd or "").strip()
        if not cmd:
            return EDITOR_PRESETS[0][0]
        for label, template in EDITOR_PRESETS:
            if template and template.strip() == cmd:
                return label
        return "Custom"

    def _on_editor_preset_change(self, label: str) -> None:
        for preset_label, template in EDITOR_PRESETS:
            if preset_label == label:
                self._editor_cmd_var.set(template)
                return
        # ``Custom`` selected — leave the existing textbox value
        # alone so the user can keep editing whatever they had.

    def _sync_editor_preset_from_cmd(self) -> None:
        target = self._editor_preset_label_for(
            self._editor_cmd_var.get().strip(),
        )
        if self._editor_preset_var.get() != target:
            self._editor_preset_var.set(target)

    # ----- Preview tab -----

    def _build_preview(self, parent: tk.Misc) -> tk.Frame:
        tab = self._tab_frame(parent)
        self._section_label(tab, "F5 preview window").pack(anchor="w")

        # Defaults preserve existing behavior — both on.
        self._preview_floater_var = tk.BooleanVar(
            value=bool(self._initial.get(KEY_PREVIEW_FLOATER, True)),
        )
        self._preview_console_var = tk.BooleanVar(
            value=bool(self._initial.get(KEY_PREVIEW_CONSOLE, True)),
        )

        cb_row = tk.Frame(tab, bg=BG)
        cb_row.pack(fill="x", pady=(10, 4))
        ctk.CTkCheckBox(
            cb_row, text="Show preview tools (orange ring + Save/Copy buttons + title prefix)",
            variable=self._preview_floater_var,
            checkbox_width=18, checkbox_height=18,
            font=("Segoe UI", 10),
            fg_color="#0e639c", hover_color="#1177bb",
        ).pack(anchor="w")

        cb_row2 = tk.Frame(tab, bg=BG)
        cb_row2.pack(fill="x", pady=(8, 4))
        ctk.CTkCheckBox(
            cb_row2, text="Show preview console (Windows console window for print + tracebacks)",
            variable=self._preview_console_var,
            checkbox_width=18, checkbox_height=18,
            font=("Segoe UI", 10),
            fg_color="#0e639c", hover_color="#1177bb",
        ).pack(anchor="w")

        self._hint(
            tab,
            "Both options apply to the next F5 preview launch — close "
            "and re-open any active preview to see the change. The "
            "preview-tools toggle controls the visible PREVIEW marker "
            "(orange edge ring, title prefix) and the floating "
            "Save / Copy buttons. The console toggle suppresses the "
            "separate Windows console window — turn it off if you "
            "don't want preview output to appear; turn it on to see "
            "behavior-file print() output and crash tracebacks.",
        ).pack(anchor="w", pady=(14, 0))
        return tab

    # ----- Autosave tab -----

    def _build_autosave(self, parent: tk.Misc) -> tk.Frame:
        tab = self._tab_frame(parent)
        self._section_label(tab, "Autosave").pack(anchor="w")

        row = tk.Frame(tab, bg=BG)
        row.pack(fill="x", pady=(10, 0))
        tk.Label(
            row, text="Interval (minutes):", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 10), width=18, anchor="w",
        ).pack(side="left")
        self._autosave_var = tk.StringVar(
            value=str(
                self._initial.get(KEY_AUTOSAVE, DEFAULT_AUTOSAVE_MIN),
            ),
        )
        ctk.CTkEntry(
            row, textvariable=self._autosave_var, width=80, height=28,
        ).pack(side="left", padx=(8, 0))

        self._hint(
            tab,
            "While a saved project is dirty, its current state is "
            "written to a sibling .autosave file every N minutes. "
            "0 disables the timer. Untitled projects are not autosaved. "
            "Changes apply on next launch.",
        ).pack(anchor="w", pady=(14, 0))
        return tab

    # ----- Notifications tab -----

    def _build_notifications(self, parent: tk.Misc) -> tk.Frame:
        tab = self._tab_frame(parent)
        self._section_label(tab, "Dismissed warnings").pack(anchor="w")

        self._reset_advisories_var = tk.BooleanVar(value=False)
        cb_row = tk.Frame(tab, bg=BG)
        cb_row.pack(fill="x", pady=(10, 4))
        ctk.CTkCheckBox(
            cb_row, text="Reset dismissed warnings on OK",
            variable=self._reset_advisories_var,
            checkbox_width=18, checkbox_height=18,
            font=("Segoe UI", 10),
            fg_color="#0e639c", hover_color="#1177bb",
        ).pack(anchor="w")

        self._hint(
            tab,
            "When checked, every advisory dialog you've previously "
            "dismissed with “don't show again” will surface again the "
            "next time it would normally appear (e.g. the cascade "
            "warning when applying a font to all widgets of a type, "
            "or the irreversibility prompt when removing an asset). "
            "Reset only fires once when you press OK.",
        ).pack(anchor="w", pady=(10, 0))
        return tab

    # ----- Footer -----

    def _build_footer(self) -> None:
        sep = tk.Frame(self, bg="#3a3a3a", height=1)
        sep.pack(fill="x")
        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=18, pady=12)
        ctk.CTkButton(
            foot, text="OK", width=90, height=32, corner_radius=4,
            command=self._on_ok,
        ).pack(side="right")
        ctk.CTkButton(
            foot, text="Cancel", width=90, height=32, corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))
        ctk.CTkButton(
            foot, text="Apply", width=90, height=32, corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_apply,
        ).pack(side="right", padx=(0, 8))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _persist(self) -> bool:
        # Validate numeric entries before any write so a bad value
        # doesn't half-save settings.
        try:
            w = int(self._w_var.get().strip())
            h = int(self._h_var.get().strip())
            if w < 100 or h < 100 or w > 10000 or h > 10000:
                raise ValueError
        except ValueError:
            messagebox.showwarning(
                "Invalid size",
                "Project width and height must be integers "
                "between 100 and 10000.",
                parent=self,
            )
            return False
        try:
            autosave = int(self._autosave_var.get().strip())
            if autosave < 0 or autosave > 120:
                raise ValueError
        except ValueError:
            messagebox.showwarning(
                "Invalid interval",
                "Autosave interval must be an integer between 0 and 120.",
                parent=self,
            )
            return False
        # Theme stays persisted at its current value — disabled menu
        # means we don't trust user input here yet, but we shouldn't
        # silently flip an existing setting either.
        # Validate grid values before any write.
        grid_color = self._grid_color_var.get().strip()
        if grid_color and not _looks_like_hex(grid_color):
            messagebox.showwarning(
                "Invalid color",
                "Grid color must be a hex value like #555555.",
                parent=self,
            )
            return False
        try:
            grid_spacing = int(self._grid_spacing_var.get().strip())
            if grid_spacing < 4 or grid_spacing > 200:
                raise ValueError
        except ValueError:
            messagebox.showwarning(
                "Invalid spacing",
                "Grid spacing must be an integer between 4 and 200.",
                parent=self,
            )
            return False
        save_setting(KEY_DEFAULT_DIR, self._dir_var.get().strip())
        save_setting(KEY_DEFAULT_W, w)
        save_setting(KEY_DEFAULT_H, h)
        save_setting(KEY_AUTOSAVE, autosave)
        save_setting(KEY_GRID_STYLE, self._grid_style_var.get())
        save_setting(KEY_GRID_COLOR, grid_color)
        save_setting(KEY_GRID_SPACING, grid_spacing)
        save_setting(
            KEY_EDITOR_COMMAND,
            self._editor_cmd_var.get().strip(),
        )
        save_setting(KEY_PREVIEW_FLOATER, bool(self._preview_floater_var.get()))
        save_setting(KEY_PREVIEW_CONSOLE, bool(self._preview_console_var.get()))
        if callable(self._on_workspace_changed):
            try:
                self._on_workspace_changed()
            except Exception:
                pass
        if self._reset_advisories_var.get():
            self._reset_advisories()
            # One-shot — don't keep the box ticked across opens.
            self._reset_advisories_var.set(False)
        return True

    def _reset_advisories(self) -> None:
        data = load_settings()
        advisory_keys = [k for k in data if k.startswith("advisory_")]
        if not advisory_keys:
            messagebox.showinfo(
                "Warnings reset",
                "No dismissed warnings to reset.",
                parent=self,
            )
            return
        for key in advisory_keys:
            save_setting(key, False)
        messagebox.showinfo(
            "Warnings reset",
            f"Cleared {len(advisory_keys)} dismissed warning(s). "
            "They'll surface again on their next trigger.",
            parent=self,
        )

    def _on_ok(self) -> None:
        if not self._persist():
            return
        self.destroy()

    def _on_apply(self) -> None:
        # Same as OK but keeps the dialog open so the user can verify
        # the validation passed without losing their place.
        self._persist()

    def _on_cancel(self) -> None:
        self.destroy()

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------
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


def _looks_like_hex(value: str) -> bool:
    if not value.startswith("#"):
        return False
    body = value[1:]
    if len(body) not in (3, 6):
        return False
    return all(c in "0123456789abcdefABCDEF" for c in body)


def get_default_project_size() -> tuple[int, int]:
    """Settings-aware default for File → New / StartupDialog."""
    s = load_settings()
    try:
        w = int(s.get(KEY_DEFAULT_W) or DEFAULT_PROJECT_W)
        h = int(s.get(KEY_DEFAULT_H) or DEFAULT_PROJECT_H)
    except (TypeError, ValueError):
        return DEFAULT_PROJECT_W, DEFAULT_PROJECT_H
    return w, h
