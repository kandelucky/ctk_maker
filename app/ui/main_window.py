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
from app.ui.console_window import ConsoleWindow
from app.ui.dialogs import NewProjectSizeDialog, prompt_open_project_folder
from app.ui.history_window import HistoryPanel, HistoryWindow
from app.ui.variables_window import VariablesWindow
from app.ui.main_menu import APPEARANCE_MODES, MenuMixin
from app.ui.main_shortcuts import ShortcutsMixin
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


def _console_reader(
    stream_name: str,
    fp,
    q: "queue.Queue[tuple[str, str]]",
) -> None:
    """Reader thread for one preview pipe. Pushes ``(stream_name,
    line)`` tuples into ``q`` until EOF, then closes the pipe.

    Daemon thread — never join; dies with the process. ``readline()``
    blocks until the child writes a newline (or the pipe closes), so
    no busy loop. Trailing ``\\n`` is stripped because the textbox
    appends its own.
    """
    try:
        for line in iter(fp.readline, ""):
            q.put((stream_name, line.rstrip("\r\n")))
    except (OSError, ValueError):
        pass
    finally:
        try:
            fp.close()
        except Exception:
            pass


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

WIKI_BASE_URL = "https://github.com/kandelucky/ctk_maker/wiki"
WIKI_USER_GUIDE_URL = f"{WIKI_BASE_URL}/User-Guide"
WIKI_WIDGETS_URL = f"{WIKI_BASE_URL}/Widgets"
WIKI_SHORTCUTS_URL = f"{WIKI_BASE_URL}/Keyboard-Shortcuts"
GITHUB_ISSUES_URL = "https://github.com/kandelucky/ctk_maker/issues"


class MainWindow(ShortcutsMixin, MenuMixin, ctk.CTk):
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
        # window can be opened mid-run and replay everything captured
        # so far. Reader threads (one per preview's stdout/stderr pipe)
        # push (stream, line) tuples into the queue; the main-thread
        # poller drains the queue, stamps an HH:MM:SS timestamp, and
        # appends a (stream, ts, line) entry to the buffer (and to the
        # live window when one exists).
        self._console_window: ConsoleWindow | None = None
        self._console_var = tk.BooleanVar(value=False)
        self._console_buffer: list[tuple[str, str, str]] = []
        self._console_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._console_poller_id: str | None = None

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

        self.paned = tk.PanedWindow(
            self,
            orient=tk.HORIZONTAL,
            sashwidth=5,
            sashrelief=tk.FLAT,
            bg="#1e1e1e",
            borderwidth=0,
            showhandle=False,
        )
        self.paned.pack(fill="both", expand=True, padx=8, pady=(0, 8))

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

    def _show_startup_dialog(self) -> None:
        # Hand the splash dismissal hook to the dialog so the splash
        # disappears in the same flush as the dialog reveal — avoids
        # a frame where neither window is visible.
        splash = self._splash
        self._splash = None

        def _dismiss_splash() -> None:
            if splash is not None:
                try:
                    splash.destroy()
                except Exception:
                    pass

        dialog = StartupDialog(self, on_ready=_dismiss_splash)
        self.wait_window(dialog)
        result = dialog.result
        if result is None:
            # No "untitled" fallback any more — every project lives
            # inside a folder structure, which means it must be either
            # opened from disk or freshly created via the New Project
            # dialog. Cancelling the startup dialog quits the app.
            self.destroy()
            return
        # Apply geometry / maximize state and load project content
        # while still alpha-hidden, then reveal in finally so the user
        # never sees the WM-default white BG nor content filling in.
        try:
            self._apply_saved_window_state()
            self.deiconify()
            if getattr(self, "_wants_maximized", False):
                self._safe_zoom()
            if result[0] == "open":
                self._open_path(result[1])
            elif result[0] == "new":
                _, name, w, h, path = result
                self.project.clear()
                self.project.resize_document(w, h)
                self.project.name = name
                self.project.active_document.name = name
                from app.core.project_folder import seed_multi_page_meta_from_disk
                seed_multi_page_meta_from_disk(self.project, path)
                try:
                    save_project(self.project, path)
                except OSError:
                    log_error("save_project (new project)")
                    messagebox.showerror(
                        "Save failed",
                        f"Could not create project file at:\n{path}",
                        parent=self,
                    )
                    return
                clear_autosave(path)
                self._set_current_path(path)
        finally:
            try:
                self.update_idletasks()
                self.attributes("-alpha", 1.0)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Current-path tracking
    # ------------------------------------------------------------------
    def _set_current_path(self, path: str | None) -> None:
        self._current_path = path
        self.project.path = path
        self._clear_dirty()
        if path:
            add_recent(path)
            self._rebuild_recent_menu()
            # Load any project-bundled .ttf/.otf into Tk so descriptors
            # that reference those families resolve them as real fonts
            # instead of silently falling back to Tk's default.
            register_project_fonts(path, root=self)
            # Phase 2 — once a path exists, materialise the behavior
            # file for every Document. Catches up the eager-create
            # logic for projects opened from disk (which never fired
            # ``document_added``) and for the first save of an
            # unsaved project (where the deferred queue lands here).
            self._ensure_behavior_files_for_all_docs()
        # Refresh the active font cascade from whatever the just-loaded
        # (or just-saved-as) project carries. New projects start with
        # an empty cascade; this also clears stale defaults left over
        # from the previous project.
        set_active_project_defaults(getattr(self.project, "font_defaults", {}))
        self._refresh_title()
        # Canvas chrome + anything else that mirrors project.name
        # needs a poke — New, Open and Save As all flow through here.
        self.project.event_bus.publish("project_renamed", self.project.name)

    def _open_path(self, path: str) -> None:
        if not Path(path).exists():
            messagebox.showerror("Open failed", f"File not found:\n{path}", parent=self)
            return
        # If an autosave sits next to this project AND is newer than
        # the saved file, the previous session crashed (or the user
        # closed without saving) — offer to restore from it instead
        # of loading the older saved copy.
        load_target = self._maybe_swap_for_autosave(path)
        try:
            load_project(self.project, load_target, root=self)
        except ProjectLoadError as exc:
            messagebox.showerror("Open failed", str(exc), parent=self)
            return
        except Exception:
            tb = log_error("load_project")
            show_crash_dialog(
                self, "Open failed",
                "Unexpected error opening project.", tb,
            )
            return
        self._set_current_path(path)
        # Detect legacy single-file projects (no project.json marker
        # in the walked-up folder) and offer a one-shot conversion
        # to the multi-page format. Skipped for already-converted
        # projects + when the user just declined a previous prompt
        # in this session (don't nag — they can use File menu).
        if (
            self.project.folder_path is None
            and not getattr(self, "_convert_prompt_dismissed", False)
        ):
            self._maybe_prompt_legacy_convert()
        # If we restored from autosave, drop the file now that the
        # state is in memory — next explicit save writes it back to
        # the real .ctkproj.
        if load_target != path:
            clear_autosave(path)
            self._dirty = True
            self.project.event_bus.publish("dirty_changed", True)
            self._refresh_title()

    def _maybe_swap_for_autosave(self, path: str) -> str:
        autosave = autosave_path_for(path)
        try:
            if not autosave.exists():
                return path
            real_mtime = Path(path).stat().st_mtime
            auto_mtime = autosave.stat().st_mtime
        except OSError:
            return path
        if auto_mtime <= real_mtime:
            return path
        from datetime import datetime
        ts = datetime.fromtimestamp(auto_mtime).strftime(
            "%Y-%m-%d %H:%M",
        )
        choice = messagebox.askyesno(
            "Restore from autosave?",
            (
                f"An autosave from {ts} is newer than the saved "
                f"project file.\n\n"
                f"This usually means the previous session ended "
                f"without an explicit Save — for example after a "
                f"crash or a forced close.\n\n"
                f"Yes  → restore from the autosave\n"
                f"No   → open the older saved copy "
                f"(autosave is left untouched)"
            ),
            parent=self,
        )
        return str(autosave) if choice else path

    # ------------------------------------------------------------------
    # File menu commands
    # ------------------------------------------------------------------
    def _stub(self, name: str) -> None:
        messagebox.showinfo("Toolbar stub", f"{name} — not implemented yet", parent=self)

    def _on_new(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        # Resolve the "Save to" default — the parent directory the
        # user originally picked (e.g. ``Documents/CTkMaker/``), one
        # level above the project folder. ``project.folder_path`` is
        # the multi-page project root; legacy single-file projects
        # fall back to two ``parent`` walks from the .ctkproj.
        if self.project.folder_path:
            default_dir = str(Path(self.project.folder_path).parent)
        elif self._current_path:
            default_dir = str(Path(self._current_path).parent.parent)
        else:
            default_dir = None
        dialog = NewProjectSizeDialog(
            self,
            default_w=self.project.document_width,
            default_h=self.project.document_height,
            default_save_dir=default_dir,
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        name, path, w, h = dialog.result
        self.project.clear()
        self.project.resize_document(w, h)
        self.project.name = name
        # Seed the first document's title from the project name so
        # the exported `app.title(...)` matches what the user typed
        # in the New dialog. They can still rename the window via
        # the Properties panel afterwards.
        self.project.active_document.name = name
        from app.core.project_folder import seed_multi_page_meta_from_disk
        seed_multi_page_meta_from_disk(self.project, path)
        try:
            save_project(self.project, path)
        except OSError:
            log_error("save_project (file new)")
            messagebox.showerror(
                "Save failed",
                f"Could not create project file at:\n{path}",
                parent=self,
            )
            return
        clear_autosave(path)
        self._set_current_path(path)

    def _on_open(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        # Default to the parent of the currently-open project (or
        # the user's projects root) so the picker lands one level
        # above where the user actually clicks — i.e. on the list of
        # projects, not inside one.
        if self.project.folder_path:
            initial = str(Path(self.project.folder_path).parent)
        elif self._current_path:
            initial = str(Path(self._current_path).parent.parent)
        else:
            from app.core.paths import get_default_projects_dir
            initial = str(get_default_projects_dir())
        picked = prompt_open_project_folder(self, initial_dir=initial)
        if picked is None:
            return
        self._open_path(str(picked))

    def _on_recover_from_backup(self) -> None:
        """Open a ``.ctkproj.bak`` file as an untitled project so the
        user must Save As before any further edits — prevents an
        accidental Save from overwriting the (presumably damaged)
        original next to the backup.
        """
        if not self._confirm_discard_if_dirty():
            return
        path = filedialog.askopenfilename(
            parent=self,
            title="Recover project from backup",
            filetypes=[
                ("CTkMaker backup", "*.ctkproj.bak"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        if not Path(path).exists():
            messagebox.showerror(
                "Recover failed",
                f"File not found:\n{path}",
                parent=self,
            )
            return
        try:
            load_project(self.project, path, root=self)
        except ProjectLoadError as exc:
            messagebox.showerror("Recover failed", str(exc), parent=self)
            return
        except Exception:
            tb = log_error("recover_from_backup")
            show_crash_dialog(
                self, "Recover failed",
                "Unexpected error recovering from backup.", tb,
            )
            return
        # Untitled — force Save As so the user can't blindly Ctrl+S
        # over the original .ctkproj sitting next to the .bak.
        self._current_path = None
        self._clear_dirty()
        self._refresh_title()
        self.project.event_bus.publish(
            "project_renamed", self.project.name,
        )
        messagebox.showinfo(
            "Recovered from backup",
            (
                "Loaded the backup as an untitled project.\n\n"
                "Use File → Save As to write it back as a real "
                ".ctkproj — direct Save is disabled until then so "
                "the original file (likely damaged) won't be "
                "overwritten by accident."
            ),
            parent=self,
        )

    def _maybe_prompt_legacy_convert(self) -> None:
        """Offer to convert the just-loaded legacy ``.ctkproj`` to
        the multi-page folder format. Auto-prompt fires once per
        session; further loads of legacy files in the same session
        skip the prompt so the user can keep working without
        repeated nags. ``File → Convert to Multi-Page Project...``
        is always available as an explicit entry point.
        """
        choice = messagebox.askyesno(
            "Convert to multi-page project?",
            (
                "This project uses the older single-file format.\n\n"
                "Multi-page projects let you keep multiple page "
                "designs (e.g. Login + Dashboard) inside one project, "
                "sharing the same fonts / images / icons.\n\n"
                "Yes  → convert now (a backup of the original .ctkproj "
                "is left next to it)\n"
                "No   → keep the single-file format for this session"
            ),
            parent=self,
        )
        if not choice:
            self._convert_prompt_dismissed = True
            return
        self._do_legacy_convert()

    def _on_convert_to_multi_page(self) -> None:
        """File menu entry — same conversion as the auto-prompt, but
        triggered explicitly. Refuses gracefully when already on a
        multi-page project.
        """
        if self.project.folder_path is not None:
            messagebox.showinfo(
                "Already converted",
                "This project is already in multi-page format.",
                parent=self,
            )
            return
        if not self._current_path:
            messagebox.showinfo(
                "Nothing to convert",
                "Open or create a project first.",
                parent=self,
            )
            return
        if not self._confirm_discard_if_dirty():
            return
        self._do_legacy_convert()

    def _do_legacy_convert(self) -> None:
        """Run the actual conversion. Saves any in-memory state to
        the legacy .ctkproj first so the converted page reflects the
        user's current edits, not just the last save.
        """
        if not self._current_path:
            return
        try:
            save_project(self.project, self._current_path)
        except OSError:
            log_error("convert pre-save")
            messagebox.showerror(
                "Convert failed",
                "Could not save current state before conversion.",
                parent=self,
            )
            return
        from app.core.project_folder import (
            ProjectMetaError, convert_legacy_to_multi_page,
        )
        try:
            new_page_path = convert_legacy_to_multi_page(self._current_path)
        except (ProjectMetaError, OSError) as exc:
            messagebox.showerror(
                "Convert failed", str(exc), parent=self,
            )
            return
        # Reload from the new layout so all in-memory pointers
        # (folder_path / pages / active_page_id / asset paths)
        # match the disk state. clear_autosave on old path drops
        # any sidecar that didn't follow the move.
        clear_autosave(self._current_path)
        self._open_path(str(new_page_path))
        self._show_toast("Converted to multi-page project")

    def _show_toast(self, text: str, duration_ms: int = 1600) -> None:
        """Pop a small non-modal banner near the top of the workspace
        and auto-destroy it. Used for page-switch feedback so the
        user sees "Switched to Login" without a blocking dialog.
        Multiple rapid switches replace the previous toast in place.
        """
        try:
            existing = getattr(self, "_toast_window", None)
            if existing is not None:
                try:
                    existing.destroy()
                except tk.TclError:
                    pass
            toast = tk.Toplevel(self)
            self._toast_window = toast
            toast.overrideredirect(True)
            toast.configure(bg="#2d2d30")
            toast.attributes("-topmost", True)
            tk.Label(
                toast, text=text,
                bg="#2d2d30", fg="#cccccc",
                font=ui_font(10),
                padx=18, pady=8,
            ).pack()
            toast.update_idletasks()
            # Anchor near the top-center of the main window so the
            # banner reads at a glance without covering the toolbar.
            try:
                self.update_idletasks()
                x = (
                    self.winfo_rootx()
                    + (self.winfo_width() - toast.winfo_width()) // 2
                )
                y = self.winfo_rooty() + 80
                toast.geometry(f"+{max(0, x)}+{max(0, y)}")
            except tk.TclError:
                pass
            toast.after(duration_ms, lambda: self._dismiss_toast(toast))
        except tk.TclError:
            pass

    def _dismiss_toast(self, toast: tk.Toplevel) -> None:
        try:
            toast.destroy()
        except tk.TclError:
            pass
        if getattr(self, "_toast_window", None) is toast:
            self._toast_window = None

    def _on_active_page_renamed(self, new_path: str) -> None:
        """Hook called when ProjectPanel renames the currently-active
        page on disk. Update ``_current_path`` so future Save / Save
        As / autosave land at the new filename, and refresh the title.
        Recent files entry shifts to the new path so the next launch
        opens the renamed file.
        """
        target = Path(new_path)
        # The on-disk rename already moved the autosave / .bak
        # sidecars (see project_folder.rename_page), so the previous
        # path's autosave is gone — no clear_autosave needed.
        self._current_path = str(target)
        self.project.path = str(target)
        try:
            add_recent(str(target))
            self._rebuild_recent_menu()
        except Exception:
            log_error("rename active page recent")
        self._refresh_title()

    def _switch_to_page(self, page_path: str) -> bool:
        """Switch the editor to a different page within the current
        multi-page project. Reuses the Open flow (dirty check + save +
        load), so the user gets the standard "Save / Don't Save /
        Cancel" prompt before the switch.

        Returns ``True`` when the switch happened, ``False`` if the
        user cancelled or the load failed. The caller decides whether
        to update any UI that mirrors the active page.
        """
        target = Path(page_path)
        # Same page — no-op.
        if (
            self._current_path
            and Path(self._current_path).resolve() == target.resolve()
        ):
            return True
        if not target.exists():
            messagebox.showerror(
                "Switch failed",
                f"Page file not found:\n{target}",
                parent=self,
            )
            return False
        if not self._confirm_discard_if_dirty():
            return False
        # Update project.json's active_page BEFORE loading so the
        # next launch lands on the page the user picked. Failure
        # here is non-fatal — the load below still proceeds.
        if self.project.folder_path:
            from app.core.project_folder import (
                ProjectMetaError, set_active_page,
            )
            try:
                page_id = next(
                    (
                        p["id"] for p in self.project.pages
                        if isinstance(p, dict)
                        and p.get("file") == target.name
                    ),
                    None,
                )
                if page_id is not None:
                    set_active_page(self.project.folder_path, page_id)
            except ProjectMetaError:
                log_error("switch_to_page set_active_page")
        # Resolve the page's display name BEFORE the load resets
        # in-memory metadata — the toast wants the user-facing name,
        # not the page filename slug.
        switched_name = next(
            (
                p.get("name", "") for p in (self.project.pages or [])
                if isinstance(p, dict) and p.get("file") == target.name
            ),
            target.stem,
        )
        self._open_path(str(target))
        self._show_toast(f"Switched to: {switched_name}")
        return True

    def _on_save(self) -> None:
        if self._current_path:
            try:
                save_project(self.project, self._current_path)
            except OSError:
                log_error("save_project")
                messagebox.showerror("Save failed", "Could not write the project file.", parent=self)
                return
            clear_autosave(self._current_path)
            self._set_current_path(self._current_path)
        else:
            self._on_save_as()

    def _on_save_as(self) -> None:
        # Multi-page projects open the 3-scope dialog; legacy
        # single-file projects still use the classic filedialog
        # (no concept of pages, no scope choice to make).
        if self.project.folder_path:
            self._save_as_multi_page()
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save project as",
            defaultextension=".ctkproj",
            filetypes=PROJECT_FILE_TYPES,
        )
        if not path:
            return
        # Copy the assets/ tree to the new location BEFORE saving the
        # ctkproj, so the saved file's tokenised asset paths
        # (``asset:images/...``) resolve against a real folder. Without
        # this, Save As writes only the .ctkproj and the new location
        # has dangling references to assets back at the original path.
        old_path = self._current_path
        if old_path and Path(old_path).resolve() != Path(path).resolve():
            self._copy_assets_to_new_location(old_path, path)
        try:
            save_project(self.project, path)
        except OSError:
            log_error("save_project")
            messagebox.showerror("Save failed", "Could not write the project file.", parent=self)
            return
        # Save As may target a brand-new path, but also clear any stale
        # autosave at the previous path so the next launch doesn't
        # offer to "restore" content the user already moved over.
        clear_autosave(self._current_path)
        clear_autosave(path)
        self._set_current_path(path)

    def _save_as_multi_page(self) -> None:
        """Multi-page Save As — opens the 3-scope dialog and
        dispatches:
          - ``page``    → add_page in current project
          - ``project`` → clone_project_folder + open the duplicate
          - ``extract`` → extract_page_to_new_project + open it
        """
        from app.ui.save_as_dialog import SaveAsDialog
        dlg = SaveAsDialog(self, self.project)
        self.wait_window(dlg)
        result = dlg.result
        if result is None:
            return
        scope = result["scope"]
        name = result["name"]
        if scope == "page":
            self._save_as_new_page(name)
        elif scope == "project":
            self._save_as_clone_project(name, result["save_to"])
        elif scope == "extract":
            self._save_as_extract_page(name, result["save_to"])

    def _save_as_new_page(self, name: str) -> None:
        """Add a new page in the current project, switch to it, and
        copy the in-memory state (so the new page starts as a clone
        of what the user is currently looking at — matches the
        traditional Save As mental model where the new file picks
        up your working state).
        """
        from app.core.project_folder import (
            ProjectMetaError, add_page, page_file_path,
            seed_multi_page_meta_from_disk,
        )
        folder_path = self.project.folder_path
        if folder_path is None:
            messagebox.showerror(
                "Save failed",
                "Project folder is not set.",
                parent=self,
            )
            return
        try:
            entry = add_page(folder_path, name)
        except ProjectMetaError as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)
            return
        new_page_path = page_file_path(folder_path, entry["file"])
        # Save current in-memory state into the new page file so
        # the new page starts as a copy of the working state.
        # Refresh metadata so the saver sees the new page entry.
        seed_multi_page_meta_from_disk(self.project, str(new_page_path))
        # Switch project.path so save lands on the new page.
        old_path = self._current_path
        self._current_path = str(new_page_path)
        self.project.path = str(new_page_path)
        self.project.active_page_id = entry["id"]
        try:
            save_project(self.project, str(new_page_path))
        except OSError:
            log_error("save_as new page")
            self._current_path = old_path
            self.project.path = old_path
            messagebox.showerror(
                "Save failed",
                "Could not write the new page file.",
                parent=self,
            )
            return
        clear_autosave(old_path)
        # Run a fresh open so all listeners (ProjectPanel, title
        # bar, etc.) reflect the new active page.
        self._set_current_path(str(new_page_path))
        self._show_toast(f"Saved as: {name}")

    def _save_as_clone_project(self, name: str, save_to: str) -> None:
        """Duplicate the entire project folder at ``<save_to>/<name>``
        and open the duplicate. The source project is left untouched.
        """
        # Save current state first so the duplicate captures any
        # in-memory edits.
        if self._current_path is None:
            messagebox.showerror(
                "Save failed",
                "No project is currently open.",
                parent=self,
            )
            return
        try:
            save_project(self.project, self._current_path)
        except OSError:
            log_error("save_as clone pre-save")
            messagebox.showerror(
                "Save failed",
                "Could not save current state before cloning.",
                parent=self,
            )
            return
        from app.core.project_folder import clone_project_folder
        folder_path = self.project.folder_path
        if folder_path is None:
            messagebox.showerror(
                "Save failed",
                "Project folder is not set.",
                parent=self,
            )
            return
        try:
            new_folder = clone_project_folder(
                folder_path, save_to, name,
            )
        except OSError as exc:
            messagebox.showerror(
                "Save failed", str(exc), parent=self,
            )
            return
        # Open the cloned project — load_project picks up the
        # active page from project.json automatically.
        if not self._confirm_discard_if_dirty():
            return
        self._open_path(str(new_folder))
        self._show_toast(f"Cloned to: {name}")

    def _save_as_extract_page(self, name: str, save_to: str) -> None:
        """Save the current page (with only its referenced assets)
        as a brand-new project at ``<save_to>/<name>``.
        """
        if self._current_path is None:
            messagebox.showerror(
                "Save failed",
                "No project is currently open.",
                parent=self,
            )
            return
        try:
            save_project(self.project, self._current_path)
        except OSError:
            log_error("save_as extract pre-save")
            messagebox.showerror(
                "Save failed",
                "Could not save current state before extracting.",
                parent=self,
            )
            return
        from app.core.project_folder import extract_page_to_new_project
        try:
            new_page_path = extract_page_to_new_project(
                self.project, save_to, name,
            )
        except OSError as exc:
            messagebox.showerror(
                "Save failed", str(exc), parent=self,
            )
            return
        if not self._confirm_discard_if_dirty():
            return
        self._open_path(str(new_page_path))
        self._show_toast(f"Extracted to: {name}")

    def _copy_assets_to_new_location(
        self, old_project_path: str, new_project_path: str,
    ) -> None:
        """Mirror the project's ``assets/`` folder from the old
        location to the new one so a Save As lands a self-contained
        project. Existing files at the destination are preserved
        (``dirs_exist_ok=True``) so a target directory the user
        prepared doesn't get blanked out. Failures log and continue —
        the .ctkproj save still proceeds; the user can drop missing
        assets in manually if needed.

        Multi-page projects use the project root's ``assets/`` (walked
        up via project.json); legacy projects use the .ctkproj's
        sibling ``assets/``. The destination layout mirrors the source
        — Save As to a multi-page page lands assets at the new root.
        """
        try:
            import shutil
            from app.core.assets import project_assets_dir
            src_assets = project_assets_dir(old_project_path)
            if src_assets is None:
                src_assets = Path(old_project_path).parent / "assets"
            if not src_assets.is_dir():
                return
            dst_assets = project_assets_dir(new_project_path)
            if dst_assets is None:
                dst_assets = Path(new_project_path).parent / "assets"
            dst_assets.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src_assets, dst_assets, dirs_exist_ok=True)
        except OSError:
            log_error("save_as copy assets")

    def _on_preview_active(self) -> None:
        doc = self.project.active_document
        if doc.is_toplevel and doc.root_widgets:
            self._on_preview_dialog(doc.id)

    def _on_rename_current_doc(self) -> None:
        from app.ui.dialogs import RenameDialog
        doc = self.project.active_document
        dialog = RenameDialog(self, doc.name)
        if dialog.result and dialog.result != doc.name:
            doc.name = dialog.result
            self.project.event_bus.publish("project_renamed", self.project.name)
            self._on_project_modified()

    def _on_form_settings(self) -> None:
        from app.core.project import WINDOW_ID
        self.project.select_widget(WINDOW_ID)

    def _on_move_doc_up(self) -> None:
        docs = self.project.documents
        doc = self.project.active_document
        idx = docs.index(doc)
        if idx <= 1:
            return
        docs[idx], docs[idx - 1] = docs[idx - 1], docs[idx]
        self.project.event_bus.publish("project_renamed", self.project.name)
        self._on_project_modified()

    def _on_move_doc_down(self) -> None:
        docs = self.project.documents
        doc = self.project.active_document
        idx = docs.index(doc)
        if idx == 0 or idx >= len(docs) - 1:
            return
        docs[idx], docs[idx + 1] = docs[idx + 1], docs[idx]
        self.project.event_bus.publish("project_renamed", self.project.name)
        self._on_project_modified()

    def _on_close_project(self) -> None:
        self._on_new()

    def _on_quit(self) -> None:
        self._on_window_close()

    # ------------------------------------------------------------------
    # Form menu — add / remove dialogs (multi-document projects)
    # ------------------------------------------------------------------
    def _on_add_dialog(self) -> None:
        from app.ui.dialogs import AddDialogSizeDialog
        existing = {doc.name for doc in self.project.documents}
        base_name = "Dialog"
        default_name = base_name
        n = 1
        while default_name in existing:
            n += 1
            default_name = f"{base_name} {n}"
        # Seed defaults from the main window (first document) so
        # "Same as Main" preset resolves to the right numbers.
        main_doc = self.project.documents[0] if self.project.documents else None
        main_w = main_doc.width if main_doc else 800
        main_h = main_doc.height if main_doc else 600
        dialog = AddDialogSizeDialog(
            self,
            default_name=default_name,
            main_w=main_w,
            main_h=main_h,
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        name, w, h = dialog.result
        self._add_document(name, is_toplevel=True, width=w, height=h)

    def _add_document(
        self,
        name: str,
        is_toplevel: bool,
        width: int = 400,
        height: int = 300,
    ) -> None:
        from app.core.commands import AddDocumentCommand
        from app.core.document import Document
        max_right = 0
        for doc in self.project.documents:
            right = doc.canvas_x + doc.width
            if right > max_right:
                max_right = right
        new_doc = Document(
            name=name,
            width=width,
            height=height,
            canvas_x=max_right + 120,
            canvas_y=0,
            is_toplevel=is_toplevel,
        )
        self.project.documents.append(new_doc)
        self.project.set_active_document(new_doc.id)
        self._on_project_modified()
        # Phase 2 — fire ``document_added`` so the eager behavior-file
        # subscriber materialises the per-window ``.py`` immediately.
        # Without this, "Add Dialog" left the scripts folder empty
        # until the next save and "Add Action" hit a missing file.
        # ``_restore_document`` (undo path) publishes the same event.
        self.project.event_bus.publish("document_added", new_doc.id)
        self.project.event_bus.publish(
            "project_renamed", self.project.name,
        )
        self.project.history.push(
            AddDocumentCommand(
                new_doc.to_dict(),
                len(self.project.documents) - 1,
            ),
        )
        # Scroll the canvas onto the new dialog — stacked to the right
        # of the last doc, the new form can easily land past the
        # current viewport (especially on zoom > 100 %). Ran after the
        # event bus has fired so the renderer has redrawn + updated
        # scrollregion before we sample it.
        self.after_idle(
            lambda did=new_doc.id: self.workspace.focus_document(did),
        )

    def _on_remove_current_document(self) -> None:
        doc = self.project.active_document
        if not doc.is_toplevel:
            messagebox.showinfo(
                "Remove document",
                "The main window can't be removed — only dialogs can.",
                parent=self,
            )
            return
        from app.ui.handler_delete_dialogs import run_window_delete_flow
        if not run_window_delete_flow(self, self.project, doc):
            return
        from app.core.commands import DeleteDocumentCommand
        snapshot = doc.to_dict()
        doc_id = doc.id
        doc_name = doc.name
        index = self.project.documents.index(doc)
        for node in list(doc.root_widgets):
            self.project.remove_widget(node.id)
        self.project.documents.remove(doc)
        self.project.active_document_id = self.project.documents[0].id
        self.project.event_bus.publish(
            "active_document_changed",
            self.project.active_document_id,
        )
        self.project.event_bus.publish(
            "project_renamed", self.project.name,
        )
        self._on_project_modified()
        # Phase 2 Step 3 — drives the asset-panel refresh + the
        # auto-save subscriber. Mirrors the chrome ✕ path so both
        # entry points stay in sync.
        self.project.event_bus.publish(
            "document_removed", doc_id, doc_name,
        )
        self.project.history.push(
            DeleteDocumentCommand(snapshot, index),
        )

    def _on_f7_edit_behavior_file(self) -> None:
        """F7 / Edit menu → open the active document's behavior
        ``.py`` in the user's editor (Phase 2 Step 3). Toast for
        unsaved projects since the file lives under
        ``<project>/assets/scripts/`` and unsaved projects don't
        have that folder yet.
        """
        if not getattr(self.project, "path", None):
            messagebox.showinfo(
                "Save first",
                "Save the project before opening the behavior file — "
                "the file lives in assets/scripts/ in the project "
                "folder.",
                parent=self,
            )
            return
        doc = self.project.active_document
        if doc is None:
            return
        try:
            from app.core.settings import load_settings
            from app.io.scripts import (
                behavior_file_path,
                launch_editor,
                load_or_create_behavior_file,
                resolve_project_root_for_editor,
            )
            file_path = load_or_create_behavior_file(
                self.project.path, doc,
            )
            if file_path is None:
                file_path = behavior_file_path(self.project.path, doc)
            if file_path is None or not file_path.exists():
                return
            editor_command = load_settings().get("editor_command")
            launch_editor(
                file_path,
                editor_command=editor_command,
                project_root=resolve_project_root_for_editor(self.project),
            )
        except OSError:
            log_error("F7 edit behavior file")

    def _on_document_added_for_behavior(self, doc_id: str) -> None:
        """Subscriber for ``document_added`` — materialises the
        per-window behavior file in ``assets/scripts/<page>/<window>.py``
        eagerly (Decision #12). Silently no-ops for unsaved projects;
        ``_set_current_path`` runs the catchup loop on first save.

        Also auto-saves the project so the on-disk window list keeps
        up with the active scripts folder. Without that, creating a
        dialog and exiting without manual save left the new ``.py``
        on disk while the .ctkproj still listed the old documents —
        an orphan file with no window referencing it.
        """
        if not getattr(self.project, "path", None):
            return
        doc = self.project.get_document(doc_id)
        if doc is None:
            return
        try:
            from app.io.scripts import load_or_create_behavior_file
            load_or_create_behavior_file(self.project.path, doc)
        except OSError:
            log_error("eager behavior file create")
        self._auto_save_after_doc_change()

    def _on_document_removed_for_behavior(
        self, doc_id: str, doc_name: str,
    ) -> None:
        """Recycle the leftover behavior file when a document is
        removed via undo of "Add Dialog" or any other code path that
        goes through ``_remove_document_by_id`` without first
        running ``WindowDeleteDialog`` (the explicit delete path
        already moved the file). Auto-saves after so the .ctkproj
        catches up to the in-memory state.

        Uses ``send2trash`` so the user keeps OS-level recovery if
        they regret an undo. The ``recycle_behavior_file`` helper
        no-ops when the file is already gone (the dialog path).
        """
        if not getattr(self.project, "path", None):
            return
        try:
            from app.io.scripts import recycle_behavior_file
            recycle_behavior_file(self.project.path, doc_name)
        except OSError:
            log_error("recycle behavior file (doc removed)")
        self._auto_save_after_doc_change()

    def _auto_save_after_doc_change(self) -> None:
        """Persist the .ctkproj after a structural document change
        (add / remove). Skipped for unsaved projects — the user has
        to choose a save path first via Save As. Save errors log
        but don't bubble up; the user still has manual save as a
        recovery path.
        """
        if not self._current_path:
            return
        try:
            save_project(self.project, self._current_path)
            clear_autosave(self._current_path)
            self._clear_dirty()
        except OSError:
            log_error("auto-save after document change")

    def _on_document_renamed_for_behavior(
        self, doc_id: str, old_name: str, new_name: str,
    ) -> None:
        """Rename ``<page>/<old_slug>.py`` → ``<new_slug>.py`` and
        rewrite the class header inside (Decision B=A). Silent
        no-op for unsaved projects, missing source files, or slug
        collisions in the destination — the user keeps the old
        file in place rather than facing a clobber.
        """
        if not getattr(self.project, "path", None):
            return
        try:
            from app.io.scripts import rename_behavior_file_and_class
            rename_behavior_file_and_class(
                self.project.path, old_name, new_name,
            )
        except OSError:
            log_error("rename behavior file")

    def _ensure_behavior_files_for_all_docs(self) -> None:
        """One-shot catchup: walk every Document and ensure its
        ``.py`` exists. Runs after open / save / save-as so a project
        loaded from disk (or freshly given a path) lands with all
        behavior files materialised even though no
        ``document_added`` event fired for them.
        """
        if not getattr(self.project, "path", None):
            return
        try:
            from app.io.scripts import load_or_create_behavior_file
            for doc in self.project.documents:
                load_or_create_behavior_file(self.project.path, doc)
        except OSError:
            log_error("behavior file catchup")

    def _on_preview(self) -> None:
        if not self.project.root_widgets:
            messagebox.showinfo(
                "Preview",
                "Nothing to preview — workspace is empty.",
                parent=self,
            )
            return
        # Same dedup as per-dialog preview: at most one main preview
        # window alive at a time. Closing it frees the slot.
        existing = self._main_preview_proc
        if existing is not None and existing.poll() is None:
            return
        self._main_preview_proc = None
        tmp_dir = Path(tempfile.mkdtemp(prefix="ctk_preview_"))
        tmp_path = tmp_dir / "preview.py"
        try:
            export_project(
                self.project, tmp_path,
                inject_preview_screenshot=_preview_show_floater(),
            )
        except OSError:
            log_error("preview export")
            messagebox.showerror("Preview failed", "Could not generate preview file.", parent=self)
            return
        if not _confirm_missing_handler_methods(self):
            return
        if not _confirm_var_name_fallbacks(self):
            return
        try:
            proc = _spawn_preview(
                tmp_dir, tmp_path,
                str(_preview_cwd(self.project, tmp_dir)),
            )
        except OSError:
            log_error("preview subprocess")
            messagebox.showerror("Preview failed", "Could not launch Python.", parent=self)
            return
        self._main_preview_proc = proc
        self._attach_console_capture(proc)

    def _on_preview_dialog(self, doc_id: str | None = None) -> None:
        """Launch a dialog-only preview — the chrome ▶ button on every
        Toplevel document routes here via ``request_preview_dialog``.
        Exports the project with ``preview_dialog_id=doc_id`` so the
        generated __main__ block opens just this dialog on top of a
        withdrawn root.

        One preview window per dialog: if a previous subprocess for
        the same ``doc_id`` is still alive, the click is a no-op (the
        user must close the existing preview first). Prevents a
        mash-of-clicks from flooding the screen with duplicate copies.
        """
        if not doc_id:
            return
        doc = self.project.get_document(doc_id)
        if doc is None or not doc.is_toplevel:
            return
        # One live preview per dialog.
        existing = self._dialog_preview_procs.get(doc_id)
        if existing is not None and existing.poll() is None:
            return
        self._dialog_preview_procs.pop(doc_id, None)
        tmp_dir = Path(tempfile.mkdtemp(prefix="ctk_preview_dlg_"))
        tmp_path = tmp_dir / "preview.py"
        try:
            export_project(
                self.project, tmp_path, preview_dialog_id=doc_id,
                inject_preview_screenshot=_preview_show_floater(),
            )
        except OSError:
            log_error("preview dialog export")
            messagebox.showerror(
                "Preview failed",
                "Could not generate preview file.",
                parent=self,
            )
            return
        if not _confirm_missing_handler_methods(self):
            return
        if not _confirm_var_name_fallbacks(self):
            return
        try:
            proc = _spawn_preview(
                tmp_dir, tmp_path,
                str(_preview_cwd(self.project, tmp_dir)),
            )
        except OSError:
            log_error("preview dialog subprocess")
            messagebox.showerror(
                "Preview failed", "Could not launch Python.",
                parent=self,
            )
            return
        self._dialog_preview_procs[doc_id] = proc
        self._attach_console_capture(proc)

    def _on_appearance_change(self) -> None:
        mode = self._appearance_var.get()
        ctk.set_appearance_mode(mode.lower())
        save_setting("appearance_mode", mode)

    def _open_url(self, url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception:
            log_error(f"open url {url}")

    def _on_widget_docs(self) -> None:
        # Help → Documentation entry — points at the wiki landing page
        # so users can navigate to whichever section they need.
        self._open_url(WIKI_BASE_URL)

    def _on_user_guide(self) -> None:
        self._open_url(WIKI_USER_GUIDE_URL)

    def _on_widget_catalog(self) -> None:
        self._open_url(WIKI_WIDGETS_URL)

    def _on_keyboard_shortcuts(self) -> None:
        self._open_url(WIKI_SHORTCUTS_URL)

    def _on_report_bug(self) -> None:
        from app.ui.bug_reporter import BugReporterWindow
        BugReporterWindow(self)

    def _on_about(self) -> None:
        from app.ui.dialogs import AboutDialog
        from app import __version__ as app_version
        AboutDialog(self, app_version=f"v{app_version}")

    def _on_inspect_widget(self) -> None:
        # Reuse a single Toplevel — clicking the menu while it's open
        # raises it instead of stacking duplicate windows.
        win = getattr(self, "_widget_inspector_win", None)
        if win is not None and win.winfo_exists():
            try:
                win.deiconify()
                win.lift()
                win.focus_set()
            except tk.TclError:
                self._widget_inspector_win = None
            else:
                return
        from app.ui.widget_inspector_window import WidgetInspectorWindow
        self._widget_inspector_win = WidgetInspectorWindow(self)

    def _on_toggle_object_tree(self) -> None:
        """Open/close Object Tree window in sync with its View-menu check.

        Driven by `self._object_tree_var`. When the var is toggled by
        the menu item or F8 shortcut, we open or close the window to
        match. When the user closes the window manually, the window's
        on-close callback flips the var back to False.
        """
        want_open = bool(self._object_tree_var.get())
        alive = (
            self._object_tree_window is not None
            and self._object_tree_window.winfo_exists()
        )
        if want_open and not alive:
            self._object_tree_window = ObjectTreeWindow(
                self, self.project,
                on_close=self._on_object_tree_closed,
                tool_setter=lambda t: self.workspace.controls.set_tool(t),
            )
        elif not want_open and alive:
            if self._object_tree_window is not None:
                try:
                    self._object_tree_window.destroy()
                except tk.TclError:
                    pass
            self._object_tree_window = None

    def _on_object_tree_closed(self) -> None:
        self._object_tree_window = None
        self._object_tree_var.set(False)

    def _on_f8_object_tree(self) -> None:
        self._object_tree_var.set(not self._object_tree_var.get())
        self._on_toggle_object_tree()

    def _on_toggle_history_window(self) -> None:
        want_open = bool(self._history_var.get())
        alive = (
            self._history_window is not None
            and self._history_window.winfo_exists()
        )
        if want_open and not alive:
            self._history_window = HistoryWindow(
                self, self.project,
                on_close=self._on_history_window_closed,
            )
        elif not want_open and alive:
            if self._history_window is not None:
                try:
                    self._history_window.destroy()
                except tk.TclError:
                    pass
            self._history_window = None

    def _on_history_window_closed(self) -> None:
        self._history_window = None
        self._history_var.set(False)

    def _on_f9_history_window(self) -> None:
        self._history_var.set(not self._history_var.get())
        self._on_toggle_history_window()

    def _on_toggle_variables_window(
        self, scope: str = "global",
        variable_id: str | None = None,
    ) -> None:
        want_open = bool(self._variables_var.get())
        alive = (
            self._variables_window is not None
            and self._variables_window.winfo_exists()
        )
        if want_open and not alive:
            self._variables_window = VariablesWindow(
                self, self.project,
                on_close=self._on_variables_window_closed,
                initial_scope=scope,
                initial_variable_id=variable_id,
            )
        elif want_open and alive:
            if self._variables_window is not None:
                self._variables_window.show_scope(scope, variable_id)
        elif not want_open and alive:
            if self._variables_window is not None:
                try:
                    self._variables_window.destroy()
                except tk.TclError:
                    pass
            self._variables_window = None

    def _on_request_open_variables_window(
        self, scope: str = "global", _doc_id: str | None = None,
        variable_id: str | None = None,
    ) -> None:
        """Bus-routed open. Sets the toggle var so menubar / F11 stay
        in sync, then switches to the requested scope tab. Optional
        ``variable_id`` pre-selects the matching row — used by the
        properties panel's double-click on a bound row."""
        self._variables_var.set(True)
        self._on_toggle_variables_window(scope, variable_id)

    def _on_variables_window_closed(self) -> None:
        self._variables_window = None
        self._variables_var.set(False)

    def _on_local_variables_migrated(self, count: int) -> None:
        """Surface the cross-document variable copy as a status toast.

        Fires from ``Project.migrate_local_var_bindings`` after a
        widget paste / reparent that brought local-variable bindings
        into a new document. The user otherwise wouldn't know that
        their variables list grew, so we tell them.
        """
        if count <= 0:
            return
        word = "variable" if count == 1 else "variables"
        self._show_toast(f"{count} local {word} copied")

    def _on_f11_variables_window(self) -> None:
        self._variables_var.set(not self._variables_var.get())
        self._on_toggle_variables_window()

    def _on_toggle_project_window(self) -> None:
        want_open = bool(self._project_var.get())
        alive = (
            self._project_window is not None
            and self._project_window.winfo_exists()
        )
        if want_open and not alive:
            self._project_window = ProjectWindow(
                self, self.project,
                path_provider=lambda: self._current_path,
                on_close=self._on_project_window_closed,
                on_switch_page=self._switch_to_page,
                on_active_page_path_changed=self._on_active_page_renamed,
            )
        elif not want_open and alive:
            if self._project_window is not None:
                try:
                    self._project_window.destroy()
                except tk.TclError:
                    pass
            self._project_window = None

    def _on_project_window_closed(self) -> None:
        self._project_window = None
        self._project_var.set(False)

    def _on_f10_project_window(self) -> None:
        self._project_var.set(not self._project_var.get())
        self._on_toggle_project_window()

    # ------------------------------------------------------------------
    # In-app preview console

    def _on_toggle_console_window(self) -> None:
        want_open = bool(self._console_var.get())
        alive = (
            self._console_window is not None
            and self._console_window.winfo_exists()
        )
        if want_open and not alive:
            self._console_window = ConsoleWindow(
                self,
                on_close=self._on_console_window_closed,
                on_clear=self._on_console_clear,
                on_stop=self._on_console_stop,
            )
            if self._console_buffer:
                self._console_window.replay(self._console_buffer)
        elif not want_open and alive:
            if self._console_window is not None:
                try:
                    self._console_window.destroy()
                except tk.TclError:
                    pass
            self._console_window = None

    def _on_console_window_closed(self) -> None:
        self._console_window = None
        self._console_var.set(False)

    def _on_console_clear(self) -> None:
        # User pressed Clear inside the console window — also drop the
        # main-window-side buffer so a later reopen doesn't replay
        # everything they just cleared.
        self._console_buffer.clear()

    def _on_console_stop(self) -> None:
        """User pressed Stop in the Console window. Terminate every
        alive preview subprocess (main + per-dialog). Reader threads
        notice EOF on the closed pipes and exit on their own.
        """
        procs: list[subprocess.Popen] = []
        if self._main_preview_proc is not None:
            procs.append(self._main_preview_proc)
        procs.extend(self._dialog_preview_procs.values())
        stopped = 0
        for proc in procs:
            if proc.poll() is None:
                try:
                    proc.terminate()
                    stopped += 1
                except OSError:
                    pass
        if stopped:
            plural = "s" if stopped != 1 else ""
            self._console_queue.put((
                "separator",
                f"─── stop requested ({stopped} preview{plural}) ───",
            ))

    def _attach_console_capture(self, proc: subprocess.Popen) -> None:
        """Spawn reader threads for ``proc.stdout`` / ``proc.stderr`` if
        the preview was launched in inapp mode (the only mode where
        ``Popen`` exposes pipes). Threads are daemons — they die with
        the app and end naturally on EOF when the preview exits.

        Pushes a ``separator`` line into the queue first so the buffer
        and live window both show a visual divider between successive
        preview runs (the buffer is shared across runs and would
        otherwise blur them together). The timestamp comes from the
        poller's ``HH:MM:SS`` prefix — no need to repeat it inline.
        """
        if proc.stdout is None and proc.stderr is None:
            return  # not inapp mode (devnull or new-console path)
        self._console_queue.put(("separator", "─── preview started ───"))
        for stream_name, fp in (("stdout", proc.stdout), ("stderr", proc.stderr)):
            if fp is None:
                continue
            t = threading.Thread(
                target=_console_reader,
                args=(stream_name, fp, self._console_queue),
                daemon=True,
            )
            t.start()

    def _drain_console_queue(self) -> None:
        """Main-thread poller: pull (stream, line) tuples out of the
        thread-safe queue, stamp an HH:MM:SS timestamp, append a
        (stream, ts, line) entry to the persistent buffer, and forward
        to the live console window if one is open. Capped at 200 lines
        per tick so a flood doesn't stall the Tk event loop.
        """
        drained = 0
        try:
            while drained < 200:
                stream, line = self._console_queue.get_nowait()
                # ``%f`` is 6-digit microseconds; trimming the last 4
                # leaves centiseconds (00-99) — enough precision to
                # order a flood arriving in the same second without
                # bloating every line by 4 extra characters.
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-4]
                entry = (stream, ts, line)
                self._console_buffer.append(entry)
                # Cap the persistent buffer so a long-running preview
                # with chatty print() doesn't eat unbounded memory.
                if len(self._console_buffer) > 5000:
                    del self._console_buffer[:500]
                if self._console_window is not None:
                    try:
                        self._console_window.append_line(*entry)
                    except tk.TclError:
                        pass
                drained += 1
        except queue.Empty:
            pass
        try:
            self._console_poller_id = self.after(
                50, self._drain_console_queue,
            )
        except tk.TclError:
            self._console_poller_id = None

    def _on_run_script(self) -> None:
        """Pick any local .py file and run it as a subprocess. Useful
        for quickly testing scripts the user already exported (or any
        other Python file) without leaving the builder. The chosen
        directory is remembered on the settings file so the next pick
        starts where the previous one left off.
        """
        from app.core.settings import load_settings, save_setting
        last_dir = load_settings().get("run_script_last_dir") or str(
            Path.home() / "Desktop",
        )
        path = filedialog.askopenfilename(
            parent=self,
            title="Run a Python script",
            initialdir=last_dir,
            filetypes=[("Python", "*.py"), ("All files", "*.*")],
        )
        if not path:
            return
        save_setting("run_script_last_dir", str(Path(path).parent))
        if Path(path).suffix.lower() not in {".py", ".pyw"}:
            messagebox.showerror(
                "Not a Python script",
                f"Run Python Script only accepts .py / .pyw files.\n\n"
                f"You picked:\n{path}",
                parent=self,
            )
            return
        try:
            subprocess.Popen(
                [sys.executable, path],
                cwd=str(Path(path).parent),
            )
        except OSError:
            log_error("run_script subprocess")
            messagebox.showerror(
                "Run failed",
                f"Could not launch:\n{path}",
                parent=self,
            )

    def _on_export(self) -> None:
        if not self._confirm_save_before_export():
            return
        from app.ui.export_dialog import ExportDialog
        ExportDialog(self, self.project)

    def _confirm_save_before_export(self) -> bool:
        """Block export if the project has unsaved changes — single
        OK button to acknowledge, then abort so the user can save
        manually. Returns True when the caller may proceed."""
        if not self._dirty:
            return True
        messagebox.showwarning(
            "Unsaved changes",
            "Please save your progress before exporting.",
            parent=self,
        )
        return False

    def _on_export_active_document(
        self, doc_id: str | None = None,
    ) -> None:
        """Quick-export ONE document (Main Window or Dialog) as a
        standalone runnable ``.py``. Asks one question only —
        ZIP-with-assets or plain .py — then writes straight to
        ``<project>/exports/<doc_slug>.{py|zip}`` with a toast.

        Asset filter is always document-scoped so the bundle ships
        only the fonts / images / icons this specific form actually
        references, never the whole shared pool.

        Triggered from File → "Export Active Document..." (active
        doc) and from the per-form chrome Export icon (specific id
        via ``request_export_document`` event bus).
        """
        if not self._confirm_save_before_export():
            return
        target_id = doc_id or self.project.active_document_id
        doc = self.project.get_document(target_id)
        if doc is None:
            return
        # Resolve output folder up-front so the dialog can preview
        # the path before the user commits. Multi-page projects use
        # <root>/exports/; legacy single-file projects use the
        # .ctkproj's sibling exports/ folder.
        if self.project.folder_path:
            out_dir = Path(self.project.folder_path) / "exports"
        elif self._current_path:
            out_dir = Path(self._current_path).parent / "exports"
        else:
            messagebox.showinfo(
                "Quick export",
                "Save the project before exporting.",
                parent=self,
            )
            return
        from app.core.project_folder import (
            collect_used_assets, slugify_page_name,
        )
        slug = slugify_page_name(doc.name or "document")
        # Preview shows the full output path with a wildcard
        # extension since the user hasn't picked a format yet.
        base_path = self.project.folder_path or self._current_path
        try:
            preview_path = str(
                (out_dir / f"{slug}.*").relative_to(
                    Path(base_path).parent if base_path else out_dir,
                ),
            )
        except (ValueError, TypeError):
            preview_path = str(out_dir / f"{slug}.*")
        from app.ui.quick_export_dialog import QuickExportDialog
        dlg = QuickExportDialog(self, doc.name or "Untitled", preview_path)
        self.wait_window(dlg)
        choice = dlg.result
        if choice is None:
            return
        as_zip = choice == "zip"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            log_error("quick export mkdir")
            messagebox.showerror(
                "Export failed",
                f"Could not create exports folder:\n{out_dir}",
                parent=self,
            )
            return
        ext = ".zip" if as_zip else ".py"
        target = out_dir / f"{slug}{ext}"
        asset_filter = collect_used_assets(self.project, document_id=target_id)
        # Respect the AI-bridge toggle persisted from the full Export
        # dialog so Quick Export's behaviour stays consistent.
        from app.core.settings import load_settings
        include_descriptions = bool(
            load_settings().get("export_include_descriptions", True),
        )
        try:
            export_project(
                self.project, str(target),
                single_document_id=target_id,
                as_zip=as_zip,
                asset_filter=asset_filter,
                include_descriptions=include_descriptions,
            )
        except OSError as exc:
            log_error("quick export")
            messagebox.showerror(
                "Export failed",
                f"Could not write the export:\n{target}\n\n{exc}",
                parent=self,
            )
            return
        # Show a relative path in the toast — the user already
        # knows their project folder; the noisy absolute prefix
        # would push the actual filename off-screen on a small
        # toast.
        base_path = self.project.folder_path or self._current_path
        try:
            display = target.relative_to(
                Path(base_path).parent if base_path else target.parent,
            )
        except (ValueError, TypeError):
            display = target.name
        self._show_toast(f"Exported: {display}", duration_ms=2400)

    # ------------------------------------------------------------------
    # Undo / redo
    # ------------------------------------------------------------------
    def _on_undo(self) -> str | None:
        # Always route Ctrl+Z through the project history, even when
        # an Entry widget has focus — the name entry's edits are
        # already tracked as coalesced RenameCommands, so app-level
        # undo is the right behaviour everywhere.
        self.project.history.undo()
        return "break"

    def _on_redo(self) -> str | None:
        self.project.history.redo()
        return "break"


    def _refresh_undo_redo_buttons(self) -> None:
        if not hasattr(self, "toolbar"):
            return
        self.toolbar.set_undo_enabled(self.project.history.can_undo())
        self.toolbar.set_redo_enabled(self.project.history.can_redo())

    # ------------------------------------------------------------------
    # Alignment + distribution
    # ------------------------------------------------------------------
    def _resolve_align_targets(self) -> tuple[list, object | None, tuple[int, int] | None]:
        """Resolve which widgets (if any) the alignment buttons
        currently operate on, plus the container reference.

        Returns ``(units, parent_node, container_size)`` where:
          - ``units`` is a list of node-lists. Each unit moves as one
            block: a fully-selected group becomes one multi-widget
            unit, every other selected widget becomes a singleton.
            Empty disables all buttons; widgets in a layout-managed
            parent are dropped since the layout owns positioning.
          - ``parent_node`` is the shared parent (``None`` for
            top-level / mixed-parent selections)
          - ``container_size`` is ``(width, height)`` for the parent
            container, or ``None`` when aligning to selection bbox
        """
        from app.widgets.layout_schema import is_layout_container
        sel_ids = list(self.project.selected_ids or [])
        if not sel_ids:
            return [], None, None
        nodes = [
            self.project.get_widget(wid)
            for wid in sel_ids
        ]
        nodes = [n for n in nodes if n is not None and getattr(n, "id", None) is not None]
        if not nodes:
            return [], None, None
        # All selected nodes must share a parent — mixed-parent
        # selections don't have a coherent coordinate space.
        parents = {id(n.parent) for n in nodes}
        if len(parents) != 1:
            return [], None, None
        parent = nodes[0].parent
        # Layout-managed children: layout manager owns x/y, so
        # alignment is meaningless. Block the whole action.
        if parent is not None and is_layout_container(parent.properties):
            return [], parent, None
        # Container size: for top-level widgets use the document
        # bounds; for nested widgets use the parent's width/height.
        if parent is None:
            doc = self.project.find_document_for_widget(nodes[0].id)
            if doc is None:
                doc = self.project.active_document
            container_size = (doc.width, doc.height)
        else:
            container_size = (
                int(parent.properties.get("width", 0) or 0),
                int(parent.properties.get("height", 0) or 0),
            )
        # Bundle selected group members into one unit per group_id;
        # ungrouped widgets stay as singleton units. This is what
        # makes "align group to other widget" treat the group as one
        # block rather than aligning members against each other first.
        units: list[list] = []
        seen_gids: set = set()
        for n in nodes:
            gid = getattr(n, "group_id", None)
            if gid:
                if gid in seen_gids:
                    continue
                members = [
                    m for m in nodes
                    if getattr(m, "group_id", None) == gid
                ]
                seen_gids.add(gid)
                units.append(members)
            else:
                units.append([n])
        # When 2+ units, switch reference to selection bbox so the
        # buttons mean "align units to each other". A single unit
        # (one widget OR one whole selected group) aligns to its
        # container.
        use_container = len(units) == 1
        return units, parent, container_size if use_container else None

    def _refresh_align_buttons(self) -> None:
        if not hasattr(self, "toolbar"):
            return
        from app.core.alignment import (
            ALIGN_MODES, MODE_DISTRIBUTE_H, MODE_DISTRIBUTE_V,
        )
        units, _parent, _container = self._resolve_align_targets()
        # Align-to-selection needs 2+ units to be useful; align-to-
        # container works with 1. Distribute always needs 3+ units.
        align_on = bool(units)
        distribute_on = len(units) >= 3
        states: dict[str, bool] = {
            mode: align_on for mode in ALIGN_MODES
        }
        states[MODE_DISTRIBUTE_H] = distribute_on
        states[MODE_DISTRIBUTE_V] = distribute_on
        self.toolbar.set_align_enabled(states)

    def _on_align_action(self, mode: str) -> None:
        from app.core.alignment import (
            DISTRIBUTE_MODES,
            compute_align_units,
            compute_distribute_units,
        )
        units, _parent, container_size = self._resolve_align_targets()
        if not units:
            return
        if mode in DISTRIBUTE_MODES:
            moves = compute_distribute_units(units, mode)
        else:
            moves = compute_align_units(
                units, mode, container_size=container_size,
            )
        # Drop no-op tuples so the history entry doesn't show the
        # widgets that were already aligned. If everything was
        # already aligned, do nothing.
        moves = [(wid, b, a) for wid, b, a in moves if b != a]
        if not moves:
            return
        from app.core.commands import BulkMoveCommand
        cmd = BulkMoveCommand(moves)
        cmd.redo(self.project)
        self.project.history.push(cmd)


    def _on_theme_toggle(self) -> None:
        current = self._appearance_var.get()
        nxt = "Light" if current == "Dark" else "Dark"
        self._appearance_var.set(nxt)
        self._on_appearance_change()

    def _set_centered_geometry(self, desired_w: int, desired_h: int) -> None:
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(desired_w, sw - 80)
        h = min(desired_h, sh - 120)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2 - 20)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _apply_saved_window_state(self) -> None:
        settings = load_settings()
        saved_geom = settings.get("window_geometry")
        applied = False
        if isinstance(saved_geom, str) and saved_geom:
            try:
                self.geometry(saved_geom)
                applied = True
            except tk.TclError:
                applied = False
        if not applied:
            self._set_centered_geometry(1280, 800)
        self._wants_maximized = bool(settings.get("window_maximized"))

    def _safe_zoom(self) -> None:
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

    def _save_window_state(self) -> None:
        try:
            is_max = self.state() == "zoomed"
        except tk.TclError:
            is_max = False
        save_setting("window_maximized", is_max)
        if not is_max:
            try:
                save_setting("window_geometry", self.geometry())
            except tk.TclError:
                pass
