import os
import queue
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from app.core.autosave import (
    AutosaveController, autosave_path_for, clear_autosave,
)
from app.ui.system_fonts import ui_font
from app.core.fonts import (
    register_project_fonts, set_active_project_defaults,
)
from app.core.logger import log_error
from app.core.project import Project
from app.core.recent_files import add_recent
from app.core.settings import load_settings, save_setting
from app.io.code_exporter import export_project
from app.io.project_loader import ProjectLoadError, load_project
from app.io.project_saver import save_project
from app.ui.console_window import ConsolePanel, ConsoleWindow
from app.ui.dialogs import NewProjectSizeDialog, prompt_open_project_folder
from app.ui.history_window import HistoryPanel, HistoryWindow
from app.ui.variables_window import VariablesWindow
from app.ui.main_actions import ActionsMixin
from app.ui.main_documents import DocumentsMixin
from app.ui.main_files import FilesMixin
from app.ui.main_menu import APPEARANCE_MODES, MenuMixin
from app.ui.main_preview import PreviewMixin
from app.ui.main_shortcuts import ShortcutsMixin
from app.ui.main_windows import WindowsMixin
from app.ui.object_tree_window import ObjectTreePanel, ObjectTreeWindow
from app.ui.palette import Palette
from app.ui.project_window import ProjectPanel, ProjectWindow
from app.ui.properties_panel import PropertiesPanel
from app.ui.crash_dialog import show_crash_dialog
from app.ui.startup_dialog import StartupDialog
from app.ui.toolbar import Toolbar
from app.ui.workspace import Workspace
from app.core.platform_compat import IS_WINDOWS, MOD_KEY

PROJECT_FILE_TYPES = [("CTkMaker project", "*.ctkproj"), ("All files", "*.*")]


_CONSOLE_MODE_VALUES = ("off", "windows", "inapp")


def _preview_console_mode() -> str:
    """Resolve the preview-console mode from settings.

    Three values: ``"off"`` (no console at all, output discarded),
    ``"windows"`` (separate Windows ``cmd`` window — legacy default
    on Windows), ``"inapp"`` (capture stdout/stderr and stream into
    the in-app ``ConsoleWindow``).

    Migrates the legacy ``preview_show_console`` boolean: if the new
    ``preview_console_mode`` key is unset, ``True`` → ``"windows"``
    (the historical default), ``False`` → ``"off"``. Non-Windows
    platforms can never resolve to ``"windows"`` (no ``cmd``); they
    fall through to ``"off"`` for that legacy value.
    """
    try:
        from app.core.settings import load_settings
        from app.ui.settings_dialog import (
            KEY_PREVIEW_CONSOLE, KEY_PREVIEW_CONSOLE_MODE,
        )
    except ImportError:
        return "windows" if sys.platform == "win32" else "off"
    s = load_settings()
    mode = s.get(KEY_PREVIEW_CONSOLE_MODE)
    if mode in _CONSOLE_MODE_VALUES:
        if mode == "windows" and sys.platform != "win32":
            return "off"
        return mode
    legacy = bool(s.get(KEY_PREVIEW_CONSOLE, True))
    if legacy and sys.platform == "win32":
        return "windows"
    return "off"


def _preview_show_console() -> bool:
    """Backward-compatible shim: ``True`` only when mode is the legacy
    Windows-cmd console. Kept so any out-of-tree caller / future
    reference still works after the mode rewrite.
    """
    return _preview_console_mode() == "windows"


def _preview_show_floater() -> bool:
    """Read Settings → Preview → "Show preview tools" (default True).
    Off → exporter skips ``inject_preview_screenshot`` so no orange
    ring, no Save/Copy buttons, no PREVIEW title prefix."""
    try:
        from app.core.settings import load_settings
        from app.ui.settings_dialog import KEY_PREVIEW_FLOATER
        return bool(load_settings().get(KEY_PREVIEW_FLOATER, True))
    except ImportError:
        return True


def _preview_console_flags(mode: str | None = None) -> dict:
    """Subprocess kwargs controlling the preview process's console
    visibility. Windows-only — other platforms inherit launching
    terminal stdio.

    - ``"windows"`` → ``CREATE_NEW_CONSOLE`` (0x00000010) so behavior
      ``print()`` and crash tracebacks land in a visible cmd window.
    - ``"off"`` / ``"inapp"`` → ``CREATE_NO_WINDOW`` (0x08000000) so
      no extra cmd window pops; in ``inapp`` mode stdout/stderr are
      piped into the in-app console instead.
    """
    if sys.platform != "win32":
        return {}
    if mode is None:
        mode = _preview_console_mode()
    return {"creationflags": 0x00000010 if mode == "windows" else 0x08000000}


def _spawn_preview(tmp_dir: Path, tmp_path: Path, cwd: str) -> subprocess.Popen:
    """Launch the preview subprocess in the mode the user picked.

    - ``"windows"``: route through ``preview_runner.py`` so a crashing
      preview pauses on "Press Enter" before its console disappears.
    - ``"inapp"``: pipe stdout/stderr back to the parent so
      ``MainWindow`` reader threads can stream them into the in-app
      console. ``-u`` + ``PYTHONUNBUFFERED=1`` defeat block-buffering
      on the redirected pipe so ``print()`` lines arrive immediately
      instead of waiting for a ~4KB buffer to fill or the process to
      exit. No ``cmd`` window pops (``CREATE_NO_WINDOW``).
    - ``"off"``: skip the runner (pause-on-error has nothing to display
      against hidden stdio) and spawn the preview directly with
      ``DEVNULL`` so output is silently discarded.

    The injected preview tools include ``print()`` calls with non-ASCII
    characters (em-dash, arrow). When stdout is redirected to DEVNULL,
    Python falls back to ``locale.getpreferredencoding()`` (cp1252 on
    most Windows installs), which can't encode those — preview crashed
    silently before mainloop. ``PYTHONIOENCODING=utf-8`` forces UTF-8
    on the child process regardless of where stdio points.
    """
    py = _preview_python_executable()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    mode = _preview_console_mode()
    if mode == "windows":
        runner_path = _write_preview_runner(tmp_dir)
        return subprocess.Popen(
            [py, str(runner_path)], cwd=cwd,
            env=env,
            **_preview_console_flags(mode),
        )
    if mode == "inapp":
        env["PYTHONUNBUFFERED"] = "1"
        # Lets the inlined preview floater know it's running under the
        # in-app console; the floater grows a 3rd "Console" button only
        # when this is set, and the click writes a marker line that
        # ``_drain_console_queue`` recognises as "open the Console".
        env["CTKMAKER_PREVIEW_CONSOLE_MODE"] = "inapp"
        return subprocess.Popen(
            [py, "-u", str(tmp_path)], cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
            **_preview_console_flags(mode),
        )
    return subprocess.Popen(
        [py, str(tmp_path)], cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        **_preview_console_flags(mode),
    )


def _preview_python_executable() -> str:
    """Pick a console-capable Python for the preview subprocess.

    When CTk Maker is launched via a ``.pyw`` association or a desktop
    shortcut targeting ``pythonw.exe``, ``sys.executable`` ends up as
    ``pythonw.exe`` — the windowless variant that doesn't bind stdio.
    Spawning the runner with that interpreter under
    ``CREATE_NEW_CONSOLE`` produces no visible console (stdout never
    reaches the new window), so ``print`` output and crash tracebacks
    disappear silently.

    Swap to the sibling ``python.exe`` when present so the preview's
    console actually shows. Falls back to ``sys.executable`` for any
    other launch shape (terminal launch already returns ``python.exe``;
    PyInstaller bundles will need their own handling — out of scope).
    """
    exe = sys.executable
    if sys.platform == "win32":
        exe_path = Path(exe)
        if exe_path.name.lower() == "pythonw.exe":
            candidate = exe_path.with_name("python.exe")
            if candidate.exists():
                return str(candidate)
    return exe


_PREVIEW_RUNNER_TEMPLATE = '''"""Preview runner — keeps the console open if the preview crashes.

Generated by CTkMaker; do not edit. Launches ``preview.py`` as a
subprocess; on non-zero exit it pauses for an Enter keypress so the
user can read the traceback before the console window closes. On a
clean exit (return code 0) the console disappears immediately,
matching the previous behaviour.
"""
import subprocess
import sys
from pathlib import Path


def _main() -> int:
    target = Path(__file__).parent / "preview.py"
    proc = subprocess.run([sys.executable, str(target)])
    if proc.returncode != 0:
        print()
        print("=" * 60)
        print(f"Preview exited with code {proc.returncode}.")
        print("Press Enter to close this window...")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
    return proc.returncode


if __name__ == "__main__":
    sys.exit(_main())
'''


def _write_preview_runner(tmp_dir: Path) -> Path:
    """Drop ``preview_runner.py`` next to ``preview.py`` so the launch
    subprocess goes through a small pause-on-error wrapper. The
    runner's exit code mirrors the inner preview's so callers that
    poll ``proc.poll()`` keep working.
    """
    runner_path = tmp_dir / "preview_runner.py"
    runner_path.write_text(_PREVIEW_RUNNER_TEMPLATE, encoding="utf-8")
    return runner_path


def _confirm_missing_handler_methods(parent) -> bool:
    """If the most recent export had to skip handler bindings whose
    methods don't exist in the behavior file, surface a yes/no
    dialog so the user knows why their button no longer fires what
    they bound. Returns ``True`` on Yes (proceed with preview) or
    when the missing-methods list is empty; ``False`` when the user
    backs out so the caller can abort the preview launch.
    """
    try:
        from app.io.code_exporter import get_missing_behavior_methods
    except ImportError:
        return True
    missing = get_missing_behavior_methods()
    if not missing:
        return True
    # Cluster by document so the user can read the warning without
    # parsing a flat repeating list. Hard-cap each doc at 5 method
    # names so a project with 30 stale bindings doesn't blow out
    # the dialog vertically.
    by_doc: dict[str, list[str]] = {}
    for doc_name, method_name in missing:
        by_doc.setdefault(doc_name, []).append(method_name)
    lines = [
        "Some handler bindings reference methods that don't exist "
        "in the behavior file:",
        "",
    ]
    for doc_name, methods in by_doc.items():
        head = methods[:5]
        rest = len(methods) - len(head)
        formatted = ", ".join(head)
        if rest > 0:
            formatted += f", … (+{rest} more)"
        lines.append(f"  • {doc_name}: {formatted}")
    lines.append("")
    lines.append(
        "These bindings will be skipped — the buttons / events "
        "won't fire what was bound. Open the behavior file (F7) "
        "to add the methods back, or unbind the rows in the "
        "Properties panel.",
    )
    lines.append("")
    lines.append("Continue with the preview anyway?")
    return messagebox.askyesno(
        "Missing handler methods",
        "\n".join(lines),
        parent=parent,
    )


def _confirm_var_name_fallbacks(parent) -> bool:
    """Surface widget Names the exporter had to drop / suffix during
    the most recent ``generate_code`` call. Behavior files that
    reference ``self.window.<user_name>`` would otherwise fail with
    ``AttributeError`` at runtime — the user typed ``submit_btn`` but
    the export emitted ``button_1`` because the name was a Python
    keyword / duplicate / collided with a reserved attribute. Returns
    ``True`` (proceed) on Yes or empty fallback list, ``False`` when
    the user backs out so the caller can abort the preview.
    """
    try:
        from app.io.code_exporter import get_var_name_fallbacks
    except ImportError:
        return True
    fallbacks = get_var_name_fallbacks()
    if not fallbacks:
        return True
    by_doc: dict[str, list[tuple[str, str, str]]] = {}
    for doc_name, intent, fallback, reason in fallbacks:
        by_doc.setdefault(doc_name, []).append((intent, fallback, reason))
    lines = [
        "Some widget Names from the Properties panel couldn't be "
        "used as exported attribute names:",
        "",
    ]
    for doc_name, rows in by_doc.items():
        head = rows[:5]
        rest = len(rows) - len(head)
        lines.append(f"  • {doc_name}:")
        for intent, fallback, reason in head:
            lines.append(
                f"      \"{intent}\" → {fallback}  ({reason})",
            )
        if rest > 0:
            lines.append(f"      … (+{rest} more)")
    lines.append("")
    lines.append(
        "Behavior files referencing self.window.<original_name> will "
        "raise AttributeError. Use the suggested fallback name "
        "instead, or rename the widget in the Properties panel to a "
        "valid Python identifier.",
    )
    lines.append("")
    lines.append("Continue with the preview anyway?")
    return messagebox.askyesno(
        "Widget name fallbacks",
        "\n".join(lines),
        parent=parent,
    )


def _format_ref_annotation_issues_body() -> str | None:
    """Build the human-readable issue list shared by the F5 confirm
    dialog and the export-dialog post-export warning. Returns
    ``None`` when there's nothing to report (or the exporter symbol
    isn't importable, which happens during partial-rebuild tests).
    """
    try:
        from app.io.code_exporter import get_ref_annotation_issues
    except ImportError:
        return None
    issues = get_ref_annotation_issues()
    if not issues:
        return None
    by_doc: dict[str, list[tuple[str, str, str]]] = {}
    for doc_name, kind, ref_name, detail in issues:
        by_doc.setdefault(doc_name, []).append((kind, ref_name, detail))
    lines = [
        "Some Object References don't line up with the behavior "
        "file's ref[Type] annotations:",
        "",
    ]
    for doc_name, rows in by_doc.items():
        head = rows[:5]
        rest = len(rows) - len(head)
        lines.append(f"  • {doc_name}:")
        for kind, ref_name, detail in head:
            if kind == "missing_annotation":
                lines.append(
                    f"      {ref_name!r} — no matching "
                    f"`{ref_name}: ref[{detail}]` in the behavior class",
                )
            elif kind == "orphan_annotation":
                lines.append(
                    f"      {ref_name!r} — annotation has no matching "
                    f"Object Reference (type ref[{detail}])",
                )
            elif kind == "type_mismatch":
                lines.append(
                    f"      {ref_name!r} — type mismatch ({detail})",
                )
            else:
                lines.append(f"      {ref_name!r} — {kind}: {detail}")
        if rest > 0:
            lines.append(f"      … (+{rest} more)")
    lines.append("")
    lines.append(
        "Behavior code reading self.<ref_name> on these will raise "
        "AttributeError at the first click. Rename the annotation or "
        "the Properties-panel entry so the names match verbatim.",
    )
    return "\n".join(lines)


def _confirm_ref_annotation_issues(parent) -> bool:
    """Surface mismatches between GUI Object References and behavior-
    file ``<name>: ref[<Type>]`` annotations from the most recent
    export. Verbatim wiring means a typo or rename in either place
    leaves ``self.<ref_name>`` unbound until the first widget
    interaction raises ``AttributeError`` — far from the user's edit
    site. Returns ``True`` (proceed) on Yes or when the issue list is
    empty, ``False`` when the user backs out.
    """
    body = _format_ref_annotation_issues_body()
    if body is None:
        return True
    return messagebox.askyesno(
        "Object Reference annotations out of sync",
        body + "\n\nContinue with the preview anyway?",
        parent=parent,
    )


def _preview_cwd(project, tmp_dir: Path) -> Path:
    """Pick the working directory for a preview subprocess. Multi-page
    projects expose ``project.folder_path`` — the project root holding
    ``assets/`` — and the generated preview emits relative imports
    like ``from assets.scripts.<page>.<window> import …`` plus
    ``assets/images/…`` paths that only resolve when cwd is the
    project root. Single-file legacy projects fall back to the
    sibling of their ``.ctkproj`` for the same reason. Otherwise the
    temp dir holding ``preview.py`` itself is the safest fallback.
    """
    folder = getattr(project, "folder_path", None)
    if folder:
        return Path(folder)
    project_path = getattr(project, "path", None)
    if project_path:
        return Path(project_path).parent
    return tmp_dir

ABOUT_TEXT = (
    "CTkMaker\n"
    "v0.0.12\n\n"
    "Drag-and-drop designer for CustomTkinter that exports clean Python code.\n\n"
    "Built with:\n"
    "  • CustomTkinter (MIT)\n"
    "  • Lucide Icons (MIT)\n"
    "  • Pillow\n"
    "  • ctk-tint-color-picker"
)

GITHUB_ISSUES_URL = "https://github.com/kandelucky/ctk_maker/issues"


class MainWindow(
    ShortcutsMixin, MenuMixin,
    FilesMixin, DocumentsMixin, PreviewMixin, WindowsMixin, ActionsMixin,
    ctk.CTk,
):
    """Top-level application window.

    Method surface split across mixins:

    - ``ShortcutsMixin`` (``main_shortcuts.py``) — keyboard bindings,
      non-Latin keycode router, Ctrl+Z/Y auto-repeat guards, Copy /
      Paste virtual-event fallbacks.
    - ``MenuMixin`` (``main_menu.py``) — menubar construction, Recent
      Forms submenu, Edit-menu state (dimming via foreground swap),
      Edit-menu dispatchers.
    """
    def __init__(self):
        super().__init__()
        # Hide the main window during construction so the user only
        # sees the startup dialog at first. The window is deiconified
        # (with saved geometry / maximized state applied) after the
        # user picks a project — this avoids the "main window appears
        # then resizes when dialog opens" flicker.
        self.withdraw()
        # Hide via alpha too — withdraw alone leaves the window briefly
        # showing the WM-default white BG when it eventually deiconifies
        # while project content is still loading. Reveal at the end of
        # ``_show_startup_dialog`` after the content fills in.
        self.attributes("-alpha", 0.0)
        # Splash covers the heavy construction below (toolbar, panels,
        # fonts, ...). Destroyed right before StartupDialog reveals.
        from app.ui.splash import SplashScreen
        self._splash: SplashScreen | None = SplashScreen(self)
        self.update()
        # Set the default window icon BEFORE any Toplevels (dialogs,
        # floating panels, palette popups) are constructed below — Tk
        # only inherits ``default=`` onto Toplevels created AFTER this
        # call, so a late hookup leaves the docked panels using the
        # plain Tk feather instead of our logo.
        try:
            _assets = Path(__file__).resolve().parents[2] / "app" / "assets"
            _ico = _assets / "icon.ico"
            _png = _assets / "icon.png"
            if sys.platform == "win32" and _ico.exists():
                self.iconbitmap(default=str(_ico))
            elif _png.exists():
                self.iconphoto(
                    True, tk.PhotoImage(file=str(_png), master=self),
                )
        except Exception:
            pass
        from app import __version__
        self.title(f"CTkMaker v{__version__}")
        self.minsize(900, 600)
        self.configure(fg_color="#252526")

        # Reconfigure every named Tk font to Segoe UI so non-Latin
        # scripts (Cyrillic, Greek, Arabic, CJK, ...) render instead of
        # "?" placeholders. Empty-family tuples like ``font=("", 11)``
        # resolve through these named fonts, so this single change
        # covers most call sites.
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

        # Non-Latin keyboard layouts remap the V/C/X/A keysyms, so
        # tk's default <Control-v> etc. never fire and clipboard
        # shortcuts break. Fall back to the hardware keycode (Windows
        # VK) and emit the corresponding virtual event.
        # Win-only — the keycode table in `_on_control_keypress` uses
        # Windows VK values, so the fallback is gated to Windows. macOS
        # non-Latin layout handling is GitHub issue #5 deferred work
        # (Tk-aqua's Cmd state bit + Mac keycode tables differ).
        if IS_WINDOWS:
            self.bind_all("<Control-KeyPress>", self._on_control_keypress)

        self.project = Project()
        self._current_path: str | None = None
        self._dirty: bool = False
        # History top at the last save — ``_recompute_dirty`` compares
        # the current top to this marker so undo-ing back to the saved
        # state flips dirty off automatically.
        self._saved_history_marker = None
        # Active ``subprocess.Popen`` handles for per-dialog previews,
        # keyed by document id. We poll the handle before launching a
        # new one so clicking ▶ repeatedly on the same dialog doesn't
        # spawn duplicate preview windows.
        self._dialog_preview_procs: dict[str, subprocess.Popen] = {}
        self._main_preview_proc: subprocess.Popen | None = None
        self._object_tree_window: ObjectTreeWindow | None = None
        # Default: Object Tree is docked above the Properties panel —
        # the floating window only opens via the View menu toggle.
        self._object_tree_var = tk.BooleanVar(value=False)
        self._history_window: HistoryWindow | None = None
        self._history_var = tk.BooleanVar(value=False)
        self._project_window: ProjectWindow | None = None
        self._project_var = tk.BooleanVar(value=False)
        self._variables_window: VariablesWindow | None = None
        self._variables_var = tk.BooleanVar(value=False)
        # In-app preview console: buffer survives close/reopen so the
        # console can be opened mid-run and replay everything captured
        # so far. Reader threads (one per preview's stdout/stderr pipe)
        # push (stream, line) tuples into the queue; the main-thread
        # poller drains the queue, stamps an HH:MM:SS.cc timestamp, and
        # appends a (stream, ts, line) entry to the buffer plus every
        # live console form.
        #
        # Two coordinated forms:
        # - ``_console_panel`` — docked at the bottom of paned_outer
        #   (View → Console / F12). Default home for the log.
        # - ``_console_window`` — floating ManagedToplevel (View →
        #   Console (floating), no shortcut). Pop-out for users who
        #   want the log on a second monitor.
        # Both can be open simultaneously and stay in sync because the
        # poller fans out append_line to both.
        self._console_panel: ConsolePanel | None = None
        self._console_dock_var = tk.BooleanVar(value=False)
        self._console_window: ConsoleWindow | None = None
        self._console_window_var = tk.BooleanVar(value=False)
        self._console_buffer: list[tuple[str, str, str]] = []
        self._console_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._console_poller_id: str | None = None
        self._console_clear_on_preview_var = tk.BooleanVar(
            value=bool(load_settings().get(
                "console_clear_on_preview_start", False,
            )),
        )
        self._console_clear_on_preview_var.trace_add(
            "write",
            lambda *_: save_setting(
                "console_clear_on_preview_start",
                bool(self._console_clear_on_preview_var.get()),
            ),
        )

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
            on_run_script=self._on_run_script,
            on_align=self._on_align_action,
            on_report_bug=self._on_report_bug,
        )
        self.toolbar.pack(side="top", fill="x")

        # Vertical outer pane: existing horizontal split on top, the
        # docked Console panel on the bottom. The Console pane is
        # added/removed lazily by ``_on_toggle_console_dock`` so the
        # bottom area collapses fully when the console is hidden.
        self.paned_outer = tk.PanedWindow(
            self,
            orient=tk.VERTICAL,
            sashwidth=5,
            sashrelief=tk.FLAT,
            bg="#1e1e1e",
            borderwidth=0,
            showhandle=False,
        )
        self.paned_outer.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.paned = tk.PanedWindow(
            self.paned_outer,
            orient=tk.HORIZONTAL,
            sashwidth=5,
            sashrelief=tk.FLAT,
            bg="#1e1e1e",
            borderwidth=0,
            showhandle=False,
        )
        self.paned_outer.add(self.paned, stretch="always", minsize=200)

        self.palette = Palette(
            self.paned, self.project,
            path_provider=lambda: self._current_path,
        )
        self.workspace = Workspace(self.paned, self.project)
        self.palette.drop_validator = self.workspace.is_cursor_over_document

        # Right sidebar: Object Tree docked above the Properties panel
        # in a nested vertical PanedWindow. A slightly-wider horizontal
        # sash so the user can actually grab it; bg colour picks up the
        # same gutter shade the main horizontal sash uses.
        self.right_pane = tk.PanedWindow(
            self.paned,
            orient=tk.VERTICAL,
            sashwidth=7,
            sashrelief=tk.FLAT,
            bg="#3a3a3a",
            borderwidth=0,
            showhandle=False,
        )
        # Top pane: Object Tree + History share one slot, switched by
        # a header row with two toggle buttons.
        _top_wrap = tk.Frame(self.right_pane, bg="#1e1e1e")

        _hdr = tk.Frame(_top_wrap, bg="#1e1e1e", height=49)
        _hdr.pack(side="top", fill="x")
        _hdr.pack_propagate(False)

        _pill_top = ctk.CTkFrame(_hdr, fg_color="#2a2a2a", corner_radius=4)
        _pill_top.pack(fill="x", padx=4, pady=4)

        _content = tk.Frame(_top_wrap, bg="#1e1e1e")
        _content.pack(fill="both", expand=True)

        self.object_tree = ObjectTreePanel(
            _content, self.project,
            tool_setter=lambda t: self.workspace.controls.set_tool(t),
        )
        self._docked_history = HistoryPanel(_content, self.project)
        self.object_tree.pack(fill="both", expand=True)

        _PILL_ACT  = "#1f6aa5"
        _ACT_FG    = "#ffffff"
        _INACT_FG  = "#888888"

        def _show_tree():
            self._docked_history.pack_forget()
            self.object_tree.pack(fill="both", expand=True)
            self._btn_tree.configure(
                fg_color=_PILL_ACT, text_color=_ACT_FG, hover_color=_PILL_ACT,
            )
            self._btn_hist.configure(
                fg_color="transparent", text_color=_INACT_FG,
                hover_color="#333333",
            )

        def _show_history():
            self.object_tree.pack_forget()
            self._docked_history.pack(fill="both", expand=True)
            self._btn_hist.configure(
                fg_color=_PILL_ACT, text_color=_ACT_FG, hover_color=_PILL_ACT,
            )
            self._btn_tree.configure(
                fg_color="transparent", text_color=_INACT_FG,
                hover_color="#333333",
            )

        _btn_kw: dict[str, Any] = {
            "height": 20, "corner_radius": 5,
            "font": ui_font(11), "border_width": 0,
        }
        self._btn_tree = ctk.CTkButton(
            _pill_top, text="Object Tree", command=_show_tree,
            fg_color=_PILL_ACT, text_color=_ACT_FG,
            hover_color=_PILL_ACT, **_btn_kw,
        )
        self._btn_hist = ctk.CTkButton(
            _pill_top, text="History", command=_show_history,
            fg_color="transparent", text_color=_INACT_FG,
            hover_color="#333333", **_btn_kw,
        )
        _pill_top.columnconfigure(0, weight=1)
        _pill_top.columnconfigure(1, weight=1)
        self._btn_tree.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self._btn_hist.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)

        # Bottom pane: Properties + Project share one slot, mirroring
        # the Tree / History tab pattern in the top pane. The floating
        # F10 ProjectWindow stays available for users who prefer the
        # asset list off to the side.
        _props_wrap = tk.Frame(self.right_pane, bg="#1e1e1e")

        _phdr = tk.Frame(_props_wrap, bg="#1e1e1e", height=49)
        _phdr.pack(side="top", fill="x")
        _phdr.pack_propagate(False)

        _pill_bot = ctk.CTkFrame(_phdr, fg_color="#2a2a2a", corner_radius=4)
        _pill_bot.pack(fill="x", padx=4, pady=4)

        _pcontent = tk.Frame(_props_wrap, bg="#1e1e1e")
        _pcontent.pack(fill="both", expand=True)

        self.properties = PropertiesPanel(
            _pcontent, self.project,
            tool_provider=lambda: self.workspace.controls.tool,
            tool_setter=lambda t: self.workspace.controls.set_tool(t),
        )
        self.properties.pack(fill="both", expand=True)
        # Docked Project panel — same component as the floating
        # ProjectWindow, just packed into the right pane. Both
        # instances refresh from the same event bus, so a save in
        # one is visible in the other without extra plumbing.
        self.docked_project = ProjectPanel(
            _pcontent, self.project,
            path_provider=lambda: self._current_path,
            on_switch_page=self._switch_to_page,
            on_active_page_path_changed=self._on_active_page_renamed,
        )

        def _show_properties():
            self.docked_project.pack_forget()
            self.properties.pack(fill="both", expand=True)
            self._btn_props.configure(
                fg_color=_PILL_ACT, text_color=_ACT_FG, hover_color=_PILL_ACT,
            )
            self._btn_proj.configure(
                fg_color="transparent", text_color=_INACT_FG,
                hover_color="#333333",
            )

        def _show_project():
            self.properties.pack_forget()
            self.docked_project.pack(fill="both", expand=True)
            self._btn_proj.configure(
                fg_color=_PILL_ACT, text_color=_ACT_FG, hover_color=_PILL_ACT,
            )
            self._btn_props.configure(
                fg_color="transparent", text_color=_INACT_FG,
                hover_color="#333333",
            )

        self._btn_props = ctk.CTkButton(
            _pill_bot, text="Properties", command=_show_properties,
            fg_color=_PILL_ACT, text_color=_ACT_FG,
            hover_color=_PILL_ACT, **_btn_kw,
        )
        self._btn_proj = ctk.CTkButton(
            _pill_bot, text="Assets", command=_show_project,
            fg_color="transparent", text_color=_INACT_FG,
            hover_color="#333333", **_btn_kw,
        )
        _pill_bot.columnconfigure(0, weight=1)
        _pill_bot.columnconfigure(1, weight=1)
        self._btn_props.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self._btn_proj.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)

        self.right_pane.add(
            _top_wrap, minsize=160, height=280, stretch="never",
        )
        self.right_pane.add(
            _props_wrap, minsize=320, stretch="always",
        )

        self.paned.add(self.palette, minsize=150, width=200, stretch="never")
        self.paned.add(self.workspace, minsize=400, stretch="always")
        self.paned.add(self.right_pane, minsize=320, width=360, stretch="never")

        bus = self.project.event_bus
        for evt in ("widget_added", "widget_removed", "property_changed",
                    "widget_z_changed", "document_resized"):
            bus.subscribe(evt, self._on_project_modified)
        bus.subscribe("history_changed", self._on_history_changed)
        bus.subscribe(
            "request_close_project",
            lambda *_a, **_k: self._on_close_project(),
        )
        bus.subscribe(
            "request_add_dialog",
            lambda *_a, **_k: self._on_add_dialog(),
        )
        bus.subscribe(
            "request_open_variables_window",
            self._on_request_open_variables_window,
        )
        bus.subscribe(
            "local_variables_migrated",
            self._on_local_variables_migrated,
        )
        bus.subscribe(
            "request_preview_dialog", self._on_preview_dialog,
        )
        bus.subscribe(
            "request_preview", lambda *_a, **_k: self._on_preview(),
        )
        bus.subscribe(
            "request_preview_active", lambda *_a, **_k: self._on_preview_active(),
        )
        bus.subscribe(
            "request_export_document", self._on_export_active_document,
        )
        # Phase 2 visual scripting — eager behavior-file creation
        # (Decision #12). Every Document gets its own ``.py`` the
        # moment it's added to a saved project, so the user can
        # discover handlers + Edit Behavior File commands without
        # needing to first attach a handler.
        bus.subscribe(
            "document_added", self._on_document_added_for_behavior,
        )
        # Phase 2 Step 3 — keep the per-window behavior file in
        # sync with the document on disk. Rename → rename file +
        # rewrite class header (Decision B=A). The
        # ``document_removed`` subscriber recycles any leftover
        # ``.py`` after an undo of "Add Dialog" (the explicit
        # delete path runs ``WindowDeleteDialog`` BEFORE the
        # command and moves the file there). Both
        # ``document_added`` and ``document_removed`` also trigger
        # an auto-save so the on-disk window list never lags
        # behind the active scripts folder — the user kept losing
        # state to "I created a dialog and exited without saving"
        # orphans.
        bus.subscribe(
            "document_renamed", self._on_document_renamed_for_behavior,
        )
        bus.subscribe(
            "document_removed", self._on_document_removed_for_behavior,
        )
        # Ghost toggle persists the base64 screenshot into
        # ``Document.to_dict`` — flush to disk immediately so the
        # frozen image survives close-without-save. Load-time
        # ``freeze_pending`` deliberately bypasses the bus, so this
        # subscriber only fires for genuine user toggles.
        bus.subscribe(
            "document_ghost_changed",
            self._on_ghost_toggled_save,
        )
        # Alignment toolbar buttons enable/disable on selection
        # change — also fire on widget add/remove since the same
        # selection might gain or lose siblings.
        for evt in (
            "selection_changed", "widget_added", "widget_removed",
            "widget_reparented", "active_document_changed",
        ):
            bus.subscribe(evt, lambda *_a, **_k: self._refresh_align_buttons())
        self._refresh_undo_redo_buttons()
        self._refresh_align_buttons()

        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Layer 3 of project safety stack — periodic write-out of the
        # current state to ``<path>.autosave`` while dirty. Skipped
        # for untitled projects (no path = no autosave). Cleared on
        # explicit save.
        self._autosave = AutosaveController(
            self.project, self,
            path_provider=lambda: self._current_path,
            interval_minutes=int(
                load_settings().get("autosave_interval_minutes", 5),
            ),
        )
        self._autosave.start()

        # Start the in-app console queue poller — idle-cheap (50 ms tick
        # against an empty queue) so it's safe to leave running even
        # when the console mode is off.
        self._console_poller_id = self.after(50, self._drain_console_queue)

        # Restore the docked-console open state from settings. Defer
        # via ``after_idle`` so the rest of the layout has settled (the
        # bottom pane add resizes ``paned_outer`` and would fight the
        # initial geometry otherwise).
        self.after_idle(self._restore_console_dock_state)

        self.after(120, self._show_startup_dialog)

    # ------------------------------------------------------------------
    # Dirty tracking
    # ------------------------------------------------------------------
    def _on_project_modified(self, *_args, **_kwargs) -> None:
        # Widget-level events fire on both fresh edits AND on undo/redo
        # replays. Undo-ing back to the saved state used to leave the
        # dirty flag on — the title still showed •, prompting a save
        # that was not needed. Dirty now tracks the history top instead
        # of raw event firings; ``_recompute_dirty`` does the match.
        self._recompute_dirty()

    def _on_history_changed(self, *_args, **_kwargs) -> None:
        self._refresh_undo_redo_buttons()
        self._recompute_dirty()

    def _recompute_dirty(self) -> None:
        """Compare the top of the undo stack to the marker captured at
        the last save. Matching marker means the project state is
        byte-identical to what was saved — flag is cleared. Anything
        else sets dirty. Handles both directions (new edits + undo
        back to saved).
        """
        history = self.project.history
        current_top = history._undo[-1] if history._undo else None
        is_dirty = current_top is not self._saved_history_marker
        if is_dirty == self._dirty:
            return
        self._dirty = is_dirty
        self._refresh_title()
        self.project.event_bus.publish("dirty_changed", is_dirty)

    def _clear_dirty(self) -> None:
        # Stamp the history top as the "saved" marker. Any subsequent
        # push / undo / redo that changes the top flips dirty back on;
        # returning to this exact top (e.g. via undo) clears it again.
        history = self.project.history
        self._saved_history_marker = (
            history._undo[-1] if history._undo else None
        )
        if self._dirty:
            self._dirty = False
            self._refresh_title()
            self.project.event_bus.publish("dirty_changed", False)

    def _refresh_title(self) -> None:
        from app import __version__
        base = f"CTkMaker v{__version__}"
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
        else:
            # Explicit discard — drop the autosave so the next launch
            # doesn't offer to restore the changes the user just
            # decided to throw away.
            clear_autosave(self._current_path)
        return True

    def _on_window_close(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        self._save_window_state()
        self.destroy()

    def _on_quit(self) -> None:
        self._on_window_close()

