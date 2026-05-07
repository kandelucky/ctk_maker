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
from app.ui.dialog_utils import prepare_dialog, reveal_dialog, safe_grab_set

DIALOG_W = 700
DIALOG_H = 520

SIDEBAR_W = 170
SIDEBAR_BG = "#252526"
SIDEBAR_ROW_BG = "#252526"
SIDEBAR_ROW_HOVER_BG = "#2a2d2e"
SIDEBAR_ROW_SELECTED_BG = "#37373d"
SIDEBAR_ROW_FG = "#cccccc"
SIDEBAR_ROW_SELECTED_FG = "#ffffff"

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
        prepare_dialog(self)
        self._on_appearance_change = on_appearance_change
        self._on_workspace_changed = on_workspace_changed

        self.title("Preferences")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        safe_grab_set(self)
        self.geometry(f"{DIALOG_W}x{DIALOG_H}")
        self._center_on_parent(parent)

        self._initial = load_settings()

        self._configure_ttk_style()
        self._build()

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._on_ok())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        reveal_dialog(self)

    # ------------------------------------------------------------------
    # Style
    # ------------------------------------------------------------------
    def _configure_ttk_style(self) -> None:
        # ttk style left in place for any future ttk widgets used inside
        # the panes (filedialog, etc.) — the main layout no longer uses
        # ttk.Notebook, so no Settings.TNotebook style is needed here.
        try:
            ttk.Style(self).theme_use("default")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build(self) -> None:
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True)

        body = tk.Frame(outer, bg=BG)
        body.pack(fill="both", expand=True)

        # Sidebar — fixed-width column of clickable rows on the left.
        sidebar = tk.Frame(body, bg=SIDEBAR_BG, width=SIDEBAR_W)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self._sidebar = sidebar

        # Content host — selected pane fills the remaining width.
        content = tk.Frame(body, bg=BG)
        content.pack(side="left", fill="both", expand=True)
        self._content = content

        # Per-tab state. Panes built up-front so their tk.Variables
        # exist when ``_persist`` reads them, regardless of which tab
        # the user clicked. Sidebar rows render in declared order.
        self._tab_panels: dict[str, tk.Frame] = {}
        self._tab_rows: dict[str, tk.Label] = {}
        self._selected_tab: str | None = None
        # Priority order — Workspace + Preview on top because they
        # affect every working session; Appearance last because the
        # theme dropdown is currently disabled.
        tabs = [
            ("Workspace", self._build_workspace),
            ("Preview", self._build_preview),
            ("Defaults", self._build_defaults),
            ("Editor", self._build_editor),
            ("Autosave", self._build_autosave),
            ("Notifications", self._build_notifications),
            ("Appearance", self._build_appearance),
        ]
        for name, builder in tabs:
            panel = builder(content)
            # Built but not packed — _select_tab will pack the active
            # one and forget the previous.
            self._tab_panels[name] = panel
            row = self._make_sidebar_row(name)
            self._tab_rows[name] = row

        self._select_tab("Workspace")
        self._build_footer()

    def _make_sidebar_row(self, name: str) -> tk.Label:
        row = tk.Label(
            self._sidebar, text=name, anchor="w",
            bg=SIDEBAR_ROW_BG, fg=SIDEBAR_ROW_FG,
            font=("Segoe UI", 11),
            padx=14, pady=7,
            cursor="hand2",
        )
        row.pack(fill="x")
        row.bind("<Button-1>", lambda _e, n=name: self._select_tab(n))
        row.bind("<Enter>", lambda _e, n=name: self._on_row_hover(n, True))
        row.bind("<Leave>", lambda _e, n=name: self._on_row_hover(n, False))
        return row

    def _on_row_hover(self, name: str, entering: bool) -> None:
        if name == self._selected_tab:
            return
        row = self._tab_rows[name]
        row.configure(bg=SIDEBAR_ROW_HOVER_BG if entering else SIDEBAR_ROW_BG)

    def _select_tab(self, name: str) -> None:
        if name == self._selected_tab:
            return
        if self._selected_tab is not None:
            self._tab_panels[self._selected_tab].pack_forget()
            self._tab_rows[self._selected_tab].configure(
                bg=SIDEBAR_ROW_BG, fg=SIDEBAR_ROW_FG,
            )
        self._tab_panels[name].pack(fill="both", expand=True)
        self._tab_rows[name].configure(
            bg=SIDEBAR_ROW_SELECTED_BG, fg=SIDEBAR_ROW_SELECTED_FG,
        )
        self._selected_tab = name

    def _tab_frame(self, parent: tk.Misc) -> tk.Frame:
        f = tk.Frame(parent, bg=BG, padx=14, pady=12)
        return f

    def _section_label(self, parent: tk.Misc, text: str) -> tk.Label:
        return tk.Label(
            parent, text=text, bg=BG, fg=SECTION_FG,
            font=("Segoe UI", 11, "bold"), anchor="w",
        )

    def _hint(self, parent: tk.Misc, text: str) -> tk.Label:
        return tk.Label(
            parent, text=text, bg=BG, fg=DIM_FG,
            font=("Segoe UI", 10), anchor="w", justify="left",
            # Sidebar takes SIDEBAR_W on the left + tab_frame padx — give
            # the hint room to wrap without bleeding past the content
            # pane's right edge.
            wraplength=DIALOG_W - SIDEBAR_W - 60,
        )

    # ----- Appearance tab -----

    def _build_appearance(self, parent: tk.Misc) -> tk.Frame:
        tab = self._tab_frame(parent)
        self._section_label(tab, "Theme").pack(anchor="w")
        row = tk.Frame(tab, bg=BG)
        row.pack(anchor="w", pady=(8, 4))
        tk.Label(
            row, text="Mode:", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 11), width=12, anchor="w",
        ).pack(side="left")
        self._theme_var = tk.StringVar(
            value=self._initial.get(KEY_THEME, "Dark"),
        )
        # Disabled until the Light theme polish lands — leaving it
        # visible keeps the user's mental model of where the option is.
        self._theme_menu = ctk.CTkOptionMenu(
            row, values=list(THEME_OPTIONS), width=160, height=24,
            variable=self._theme_var, dynamic_resizing=False,
            state="disabled",
            **_DROPDOWN_STYLE,
        )
        self._theme_menu.pack(side="left", padx=(8, 0))
        self._hint(
            tab,
            "Theme switching is being polished; coming soon. Use the "
            "toolbar toggle if you need to switch ad-hoc in the meantime.",
        ).pack(anchor="w", pady=(6, 0))
        return tab

    # ----- Defaults tab -----

    def _build_defaults(self, parent: tk.Misc) -> tk.Frame:
        tab = self._tab_frame(parent)
        self._section_label(tab, "New Project").pack(anchor="w")

        loc_row = tk.Frame(tab, bg=BG)
        loc_row.pack(fill="x", pady=(6, 4))
        tk.Label(
            loc_row, text="Save location:", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 11), width=14, anchor="w",
        ).pack(side="left")
        self._dir_var = tk.StringVar(
            value=self._initial.get(KEY_DEFAULT_DIR)
            or str(Path.home() / "Documents" / "CTkMaker"),
        )
        ctk.CTkEntry(
            loc_row, textvariable=self._dir_var,
            width=300, height=24,
        ).pack(side="left", padx=(8, 6))
        ctk.CTkButton(
            loc_row, text="Browse...", width=80, height=24,
            corner_radius=3, fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_browse_dir,
        ).pack(side="left")

        size_row = tk.Frame(tab, bg=BG)
        size_row.pack(fill="x")
        tk.Label(
            size_row, text="Project size:", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 11), width=14, anchor="w",
        ).pack(side="left")
        self._w_var = tk.StringVar(
            value=str(
                self._initial.get(KEY_DEFAULT_W) or DEFAULT_PROJECT_W,
            ),
        )
        ctk.CTkEntry(
            size_row, textvariable=self._w_var, width=80, height=24,
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
            size_row, textvariable=self._h_var, width=80, height=24,
        ).pack(side="left", padx=(4, 0))
        tk.Label(
            size_row, text="px", bg=BG, fg=DIM_FG,
            font=("Segoe UI", 11),
        ).pack(side="left", padx=(6, 0))

        self._hint(
            tab,
            "These defaults are used by the Welcome screen on launch. "
            "File → New always uses the active project's dimensions "
            "as a starting point.",
        ).pack(anchor="w", pady=(10, 0))
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
        style_row.pack(fill="x", pady=(6, 4))
        tk.Label(
            style_row, text="Style:", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 11), width=14, anchor="w",
        ).pack(side="left")
        self._grid_style_var = tk.StringVar(
            value=str(
                self._initial.get(KEY_GRID_STYLE) or DEFAULT_GRID_STYLE,
            ),
        )
        ctk.CTkOptionMenu(
            style_row, values=list(GRID_STYLE_OPTIONS),
            variable=self._grid_style_var,
            width=160, height=24, dynamic_resizing=False,
            **_DROPDOWN_STYLE,
        ).pack(side="left", padx=(8, 0))

        color_row = tk.Frame(tab, bg=BG)
        color_row.pack(fill="x", pady=(0, 6))
        tk.Label(
            color_row, text="Color:", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 11), width=14, anchor="w",
        ).pack(side="left")
        self._grid_color_var = tk.StringVar(
            value=str(
                self._initial.get(KEY_GRID_COLOR) or DEFAULT_GRID_COLOR,
            ),
        )
        ctk.CTkEntry(
            color_row, textvariable=self._grid_color_var,
            width=110, height=24,
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
            font=("Segoe UI", 11), width=14, anchor="w",
        ).pack(side="left")
        self._grid_spacing_var = tk.StringVar(
            value=str(
                self._initial.get(KEY_GRID_SPACING) or DEFAULT_GRID_SPACING,
            ),
        )
        ctk.CTkEntry(
            spacing_row, textvariable=self._grid_spacing_var,
            width=80, height=24,
        ).pack(side="left", padx=(8, 0))

        self._hint(
            tab,
            "Applies to every document in every project. Each document's "
            "own Window Settings grid controls are kept (loadable .ctkproj "
            "files still carry them) but are overridden globally as long "
            "as these values are set.",
        ).pack(anchor="w", pady=(10, 0))
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
        preset_row.pack(fill="x", pady=(6, 4))
        tk.Label(
            preset_row, text="Editor:", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 11), width=14, anchor="w",
        ).pack(side="left")
        ctk.CTkOptionMenu(
            preset_row,
            values=[label for label, _ in EDITOR_PRESETS] + ["Custom"],
            variable=self._editor_preset_var,
            command=self._on_editor_preset_change,
            width=320, height=24, dynamic_resizing=False,
            **_DROPDOWN_STYLE,
        ).pack(side="left", padx=(8, 0))

        cmd_row = tk.Frame(tab, bg=BG)
        cmd_row.pack(fill="x", pady=(0, 6))
        tk.Label(
            cmd_row, text="Command:", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 11), width=14, anchor="w",
        ).pack(side="left")
        self._editor_cmd_var = tk.StringVar(value=current_cmd)
        # Manual edits should flip the preset label to "Custom" so
        # the dropdown stays honest about what the textbox holds.
        self._editor_cmd_var.trace_add(
            "write", lambda *_: self._sync_editor_preset_from_cmd(),
        )
        cmd_entry = ctk.CTkEntry(
            cmd_row, textvariable=self._editor_cmd_var,
            width=420, height=24,
        )
        cmd_entry.pack(side="left", padx=(8, 0))

        self._hint(
            tab,
            "Used by Properties › Events ▸ double-click and the canvas "
            "right-click cascade. \"Auto\" tries VS Code → Notepad++ → "
            "IDLE in order. ``{file}`` is replaced with the path; "
            "``{line}`` with the method's line number; ``{folder}`` "
            "with the project root.",
        ).pack(anchor="w", pady=(10, 0))

        # Recommendation block — VS Code is what we test against
        # most heavily and what the planned CTkMaker extension will
        # plug into. The download link is a clickable text label so
        # the user can grab it without leaving the dialog.
        rec_frame = tk.Frame(tab, bg=BG)
        rec_frame.pack(anchor="w", pady=(12, 0), fill="x")
        tk.Label(
            rec_frame,
            text="★ Recommended:  VS Code",
            bg=BG, fg="#7dd3fc",
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            rec_frame,
            text=(
                "Best fit for CTkMaker — Python tooling, integrated "
                "terminal, and a dedicated CTkMaker extension is on "
                "the roadmap."
            ),
            bg=BG, fg=DIM_FG, font=("Segoe UI", 10),
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

        fix_frame = tk.Frame(tab, bg=BG)
        fix_frame.pack(anchor="w", pady=(14, 0), fill="x")
        tk.Label(
            fix_frame,
            text="VS Code showing red import errors?",
            bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            fix_frame,
            text=(
                "Writes .vscode/settings.json with the correct Python path "
                "so Pylance finds your packages."
            ),
            bg=BG, fg=DIM_FG, font=("Segoe UI", 9),
            anchor="w", justify="left",
            wraplength=DIALOG_W - 80,
        ).pack(anchor="w", pady=(2, 6))
        self._vscode_fix_status = tk.StringVar(value="")
        ctk.CTkButton(
            fix_frame,
            text="Configure VS Code Python Path",
            width=230, height=26,
            command=self._configure_vscode_python,
        ).pack(anchor="w")
        tk.Label(
            fix_frame,
            textvariable=self._vscode_fix_status,
            bg=BG, fg="#4ade80",
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))

        return tab

    def _open_vs_code_download(self) -> None:
        import webbrowser
        try:
            webbrowser.open("https://code.visualstudio.com/download")
        except Exception:
            pass

    def _configure_vscode_python(self) -> None:
        import sys, json, os
        from tkinter import filedialog

        folder = filedialog.askdirectory(
            parent=self,
            title="Select the project folder to configure for VS Code",
        )
        if not folder:
            return

        vscode_dir = os.path.join(folder, ".vscode")
        os.makedirs(vscode_dir, exist_ok=True)

        settings_path = os.path.join(vscode_dir, "settings.json")
        existing: dict = {}
        if os.path.isfile(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass

        python_exe = sys.executable.replace("pythonw.exe", "python.exe")
        existing["python.defaultInterpreterPath"] = python_exe
        try:
            import sysconfig
            site_pkgs = sysconfig.get_path("purelib")
            if site_pkgs:
                existing["python.analysis.extraPaths"] = [site_pkgs]
        except Exception:
            pass
        try:
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=4)

            pyright_path = os.path.join(folder, "pyrightconfig.json")
            pyright: dict[str, str] = {}
            if os.path.isfile(pyright_path):
                try:
                    with open(pyright_path, "r", encoding="utf-8") as f:
                        pyright = json.load(f)
                except Exception:
                    pass
            pyright["pythonPath"] = python_exe
            with open(pyright_path, "w", encoding="utf-8") as f:
                json.dump(pyright, f, indent=4)

            self._vscode_fix_status.set("✓ Done! Reopen the folder in VS Code.")
        except Exception as e:
            self._vscode_fix_status.set(f"✗ Error: {e}")

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
        cb_row.pack(fill="x", pady=(6, 2))
        ctk.CTkCheckBox(
            cb_row, text="Show preview tools (orange ring + Save/Copy buttons + title prefix)",
            variable=self._preview_floater_var,
            checkbox_width=16, checkbox_height=16,
            font=("Segoe UI", 11),
            fg_color="#0e639c", hover_color="#1177bb",
        ).pack(anchor="w")

        cb_row2 = tk.Frame(tab, bg=BG)
        cb_row2.pack(fill="x", pady=(8, 4))
        ctk.CTkCheckBox(
            cb_row2, text="Show preview console (Windows console window for print + tracebacks)",
            variable=self._preview_console_var,
            checkbox_width=16, checkbox_height=16,
            font=("Segoe UI", 11),
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
        ).pack(anchor="w", pady=(10, 0))
        return tab

    # ----- Autosave tab -----

    def _build_autosave(self, parent: tk.Misc) -> tk.Frame:
        tab = self._tab_frame(parent)
        self._section_label(tab, "Autosave").pack(anchor="w")

        row = tk.Frame(tab, bg=BG)
        row.pack(fill="x", pady=(10, 0))
        tk.Label(
            row, text="Interval (minutes):", bg=BG, fg=HEADER_FG,
            font=("Segoe UI", 11), width=18, anchor="w",
        ).pack(side="left")
        self._autosave_var = tk.StringVar(
            value=str(
                self._initial.get(KEY_AUTOSAVE, DEFAULT_AUTOSAVE_MIN),
            ),
        )
        ctk.CTkEntry(
            row, textvariable=self._autosave_var, width=80, height=24,
        ).pack(side="left", padx=(8, 0))

        self._hint(
            tab,
            "While a saved project is dirty, its current state is "
            "written to a sibling .autosave file every N minutes. "
            "0 disables the timer. Untitled projects are not autosaved. "
            "Changes apply on next launch.",
        ).pack(anchor="w", pady=(10, 0))
        return tab

    # ----- Notifications tab -----

    def _build_notifications(self, parent: tk.Misc) -> tk.Frame:
        tab = self._tab_frame(parent)
        self._section_label(tab, "Dismissed warnings").pack(anchor="w")

        self._reset_advisories_var = tk.BooleanVar(value=False)
        cb_row = tk.Frame(tab, bg=BG)
        cb_row.pack(fill="x", pady=(6, 2))
        ctk.CTkCheckBox(
            cb_row, text="Reset dismissed warnings on OK",
            variable=self._reset_advisories_var,
            checkbox_width=16, checkbox_height=16,
            font=("Segoe UI", 11),
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
        foot.pack(fill="x", padx=14, pady=10)
        ctk.CTkButton(
            foot, text="OK", width=80, height=24, corner_radius=3,
            command=self._on_ok,
        ).pack(side="right")
        ctk.CTkButton(
            foot, text="Cancel", width=80, height=24, corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 6))
        ctk.CTkButton(
            foot, text="Apply", width=80, height=24, corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_apply,
        ).pack(side="right", padx=(0, 6))

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
