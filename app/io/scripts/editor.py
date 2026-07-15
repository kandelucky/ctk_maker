"""External editor launch — open behavior files in VS Code / Cursor /
Sublime / PyCharm / Notepad++ / IDLE, or a user-supplied editor.

The editor is chosen *by id* (``_EDITOR_REGISTRY``); each entry owns its
own "jump to line" grammar so the Settings UI never exposes a raw
command template. Resolution order:

1. ``editor_id`` + optional ``editor_path`` — registry launch.
2. ``editor_command`` — legacy raw template (``{file}`` / ``{line}`` /
   ``{folder}`` / ``{python}``), kept for back-compat + the Advanced
   escape hatch.
3. Auto fallback chain — VS Code → Notepad++ → IDLE → file association.
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


# Well-known Windows install paths for editors that ship a launcher
# script. Probed in order; the first existing entry wins. Maps the
# bare token the user types in Settings (``code``, ``code-insiders``)
# to the actual ``.cmd`` / ``.exe`` on disk so we don't fall victim
# to PATH ambiguity (Git Bash / MinGW / MSYS2 all ship a ``code``
# that's not VS Code).
_EDITOR_KNOWN_PATHS: dict[str, tuple[str, ...]] = {
    "code": (
        r"%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd",
        r"%PROGRAMFILES%\Microsoft VS Code\bin\code.cmd",
        r"%PROGRAMFILES(X86)%\Microsoft VS Code\bin\code.cmd",
    ),
    "code-insiders": (
        r"%LOCALAPPDATA%\Programs\Microsoft VS Code Insiders\bin\code-insiders.cmd",
        r"%PROGRAMFILES%\Microsoft VS Code Insiders\bin\code-insiders.cmd",
    ),
    # Cursor is a VS Code fork, so it honours the same ``-g file:line``
    # grammar. The CLI shim lives under the app's ``bin`` folder.
    "cursor": (
        r"%LOCALAPPDATA%\Programs\cursor\resources\app\bin\cursor.cmd",
        r"%PROGRAMFILES%\cursor\resources\app\bin\cursor.cmd",
    ),
    "subl": (
        r"%PROGRAMFILES%\Sublime Text\subl.exe",
        r"%PROGRAMFILES(X86)%\Sublime Text\subl.exe",
    ),
    "notepad++": (
        r"%PROGRAMFILES%\Notepad++\notepad++.exe",
        r"%PROGRAMFILES(X86)%\Notepad++\notepad++.exe",
    ),
    # PyCharm's bin folder lives under a versioned directory; the
    # Toolbox install also nests by channel + version. Probing every
    # combination is brittle, so we only list the JetBrains-default
    # paths the standard installer drops + the ``%LOCALAPPDATA%``
    # JetBrains Toolbox shim that some users add to PATH manually.
    "pycharm64": (
        r"%PROGRAMFILES%\JetBrains\PyCharm Community Edition\bin\pycharm64.exe",
        r"%PROGRAMFILES%\JetBrains\PyCharm\bin\pycharm64.exe",
        r"%LOCALAPPDATA%\JetBrains\Toolbox\scripts\pycharm.cmd",
    ),
}


def resolve_project_root_for_editor(project) -> str | None:
    """Project-folder path the external editor should open as a
    workspace, or ``None`` for unsaved / legacy single-file
    projects. Lets VS Code / PyCharm / Sublime activate their
    project-aware features (Python interpreter resolution, etc.)
    when CTkMaker hands them the behavior file.
    """
    path = getattr(project, "path", None)
    if not path:
        return None
    from app.core.project_folder import find_project_root
    root = find_project_root(path)
    if root is not None:
        return str(root)
    # Legacy single-file projects keep ``assets/scripts/`` next to
    # the .ctkproj — open that folder instead so VS Code still
    # gets a workspace context to run the Python tooling against.
    return str(Path(path).parent)


def _resolve_editor_binary(name: str) -> str | None:
    """Look up a bare editor command name on disk. Tries the
    well-known Windows install paths first (defeats Git Bash /
    MinGW / Cygwin shadowing), then falls back to ``shutil.which``
    for paths that do live on PATH legitimately. Names with path
    separators are returned as-is — the user explicitly pinned a
    full path and we shouldn't second-guess it.
    """
    if not name:
        return None
    if "/" in name or "\\" in name:
        return name if Path(name).exists() else None
    lookup_key = name.lower()
    for raw in _EDITOR_KNOWN_PATHS.get(lookup_key, ()):
        candidate = os.path.expandvars(raw)
        if Path(candidate).exists():
            return candidate
    return shutil.which(name) or shutil.which(f"{name}.cmd")


# ---------------------------------------------------------------------------
# Editor registry — id → display + launch grammar.
#
# The UI picks an editor *by id*; each argv builder owns that editor's
# "jump to line" syntax so the raw command template never has to be
# exposed to the user. ``line`` may be ``None`` (open the file with no
# jump). ``exe`` is the resolved binary path; ``folder`` the project
# root (empty string when unknown).


def _argv_vscode(exe: str, file: str, line: int | None, folder: str) -> list[str]:
    # VS Code / Cursor: open the folder as a workspace first (activates
    # the Python extension), then ``-g`` jumps to the line.
    argv = [exe]
    if folder:
        argv.append(folder)
    argv.extend(["-g", f"{file}:{line}" if line is not None else file])
    return argv


def _argv_sublime(exe: str, file: str, line: int | None, folder: str) -> list[str]:
    return [exe, f"{file}:{line}" if line is not None else file]


def _argv_pycharm(exe: str, file: str, line: int | None, folder: str) -> list[str]:
    if line is not None:
        return [exe, "--line", str(line), file]
    return [exe, file]


def _argv_notepadpp(exe: str, file: str, line: int | None, folder: str) -> list[str]:
    argv = [exe]
    if line is not None:
        argv.append(f"-n{line}")
    argv.append(file)
    return argv


def _argv_idle(exe: str, file: str, line: int | None, folder: str) -> list[str]:
    # ``exe`` is the Python interpreter; IDLE can't jump to a line.
    return [exe, "-m", "idlelib", file]


def _argv_generic(exe: str, file: str, line: int | None, folder: str) -> list[str]:
    # Unknown editor picked via "Other…" — open the file, no line jump.
    return [exe, file]


# id → (display label, resolver bin name, argv builder). ``bin`` is the
# bare name fed to ``_resolve_editor_binary`` (known-path + PATH lookup);
# ``None`` means "not resolved by name" (IDLE uses the interpreter,
# "other" relies solely on the user-supplied path).
_EDITOR_REGISTRY: dict[str, tuple[str, str | None, object]] = {
    "vscode": ("VS Code", "code", _argv_vscode),
    "sublime": ("Sublime Text", "subl", _argv_sublime),
    "pycharm": ("PyCharm", "pycharm64", _argv_pycharm),
    "notepadpp": ("Notepad++", "notepad++", _argv_notepadpp),
    "cursor": ("Cursor", "cursor", _argv_vscode),
    "idle": ("IDLE", None, _argv_idle),
    "other": ("Other…", None, _argv_generic),
}

# Dropdown order for the Settings picker. ``auto`` and ``custom`` are
# not registry entries (they map to the fallback chain / raw template).
EDITOR_ORDER: tuple[str, ...] = (
    "auto", "vscode", "sublime", "pycharm", "notepadpp", "cursor",
    "idle", "other",
)
_EXTRA_LABELS = {"auto": "Auto", "custom": "Custom command"}


def editor_label(editor_id: str) -> str:
    """Friendly display name for an editor id."""
    if editor_id in _EDITOR_REGISTRY:
        return _EDITOR_REGISTRY[editor_id][0]
    return _EXTRA_LABELS.get(editor_id, editor_id)


def editor_id_for_label(label: str) -> str:
    """Reverse of :func:`editor_label` — dropdown label → id."""
    for eid in EDITOR_ORDER:
        if editor_label(eid) == label:
            return eid
    return "auto"


def _resolve_editor_exe(editor_id: str, editor_path: str | None) -> str | None:
    """Resolve a registry editor's executable. An explicit
    ``editor_path`` wins; otherwise probe the editor's known install
    paths / PATH by its bare bin name.
    """
    if editor_path:
        expanded = os.path.expandvars(editor_path)
        return expanded if Path(expanded).exists() else None
    info = _EDITOR_REGISTRY.get(editor_id)
    if not info or info[1] is None:
        return None
    return _resolve_editor_binary(info[1])


def editor_is_available(editor_id: str | None, editor_path: str | None = None) -> bool:
    """Whether the chosen editor can actually be launched — drives the
    "found ✓ / not found" tag in Settings. ``auto`` and ``idle`` always
    resolve (the fallback chain / bundled interpreter); ``other`` needs
    a valid path.
    """
    if editor_id in (None, "", "auto", "idle"):
        return True
    if editor_id == "other":
        return bool(
            editor_path and Path(os.path.expandvars(editor_path)).exists()
        )
    return _resolve_editor_exe(editor_id, editor_path) is not None


def resolve_editor_path(
    editor_id: str | None, editor_path: str | None = None,
) -> str | None:
    """The actual executable CTkMaker would launch for this selection —
    drives the read-only "Launches: …" line in Settings so the user can
    see exactly where the editor is taken from. ``None`` when it can't
    be resolved (missing editor / "custom" template).
    """
    if editor_id in (None, "", "auto"):
        # Mirror the Auto fallback chain: VS Code → Notepad++ → IDLE.
        return (
            _resolve_editor_binary("code")
            or _resolve_editor_binary("notepad++")
            or sys.executable
        )
    if editor_id == "idle":
        return sys.executable
    if editor_id == "custom":
        return None
    if editor_id == "other":
        if editor_path:
            expanded = os.path.expandvars(editor_path)
            return expanded if Path(expanded).exists() else None
        return None
    return _resolve_editor_exe(editor_id, editor_path)


def editor_id_from_command(command: str | None) -> str | None:
    """Best-effort migration: map a legacy ``editor_command`` template
    to a registry id so old configs surface the right dropdown entry.
    Returns ``None`` for unrecognised commands (kept as "custom").
    """
    cmd = (command or "").strip().lower()
    if not cmd:
        return "auto"
    if "idlelib" in cmd:
        return "idle"
    if "notepad++" in cmd:
        return "notepadpp"
    if "cursor" in cmd:
        return "cursor"
    if "pycharm" in cmd:
        return "pycharm"
    if cmd.startswith("subl") or "\\subl" in cmd or "/subl" in cmd:
        return "sublime"
    if cmd.startswith("code") or "\\code" in cmd or "/code" in cmd:
        return "vscode"
    return None


def _launch_registry(
    file_path: str,
    line: int | None,
    editor_id: str,
    editor_path: str | None,
    folder: str,
) -> bool:
    """Launch a registry editor by id. Returns ``False`` (so the caller
    can fall back to Auto) when the editor can't be resolved or spawned.
    """
    info = _EDITOR_REGISTRY.get(editor_id)
    if info is None:
        return False
    exe = sys.executable if editor_id == "idle" else _resolve_editor_exe(
        editor_id, editor_path,
    )
    if not exe:
        return False
    try:
        argv = info[2](exe, file_path, line, folder)  # type: ignore[operator]
        logger.info("launch %s: %s", editor_id, argv)
        subprocess.Popen(argv)
        return True
    except OSError as exc:
        logger.warning("launch %s failed: %s", editor_id, exc)
        return False


def launch_editor_from_settings(
    file_path: str | Path,
    line: int | None,
    project_root: str | Path | None,
    settings: dict,
) -> bool:
    """Convenience wrapper — pull the editor keys out of a settings dict
    and dispatch. Keeps the key names in one place for the call sites.
    """
    return launch_editor(
        file_path,
        line,
        editor_command=settings.get("editor_command"),
        project_root=project_root,
        editor_id=settings.get("editor_id"),
        editor_path=settings.get("editor_path"),
    )


def launch_editor(
    file_path: str | Path,
    line: int | None = None,
    editor_command: str | None = None,
    project_root: str | Path | None = None,
    *,
    editor_id: str | None = None,
    editor_path: str | None = None,
) -> bool:
    """Open ``file_path`` in the user's editor, jumping to ``line``
    when the editor supports it. Returns ``True`` on success.

    Resolution order:

    1. ``editor_id`` (new model) — a registry editor resolved by id +
       optional ``editor_path``. ``auto`` skips straight to the
       fallback chain; ``custom`` (or a legacy config with no id but an
       ``editor_command``) uses the raw template below.
    2. ``editor_command`` — legacy user-configured template with
       ``{file}`` / ``{line}`` / ``{folder}`` / ``{python}``.
    3. Auto fallback chain — VS Code → Notepad++ → IDLE → file
       association. Always ends in something runnable.
    """
    file_path = str(file_path)
    folder = str(project_root) if project_root else ""

    # Absent id but a legacy template present → treat as "custom" so
    # existing configs keep working untouched.
    effective_id = editor_id or ("custom" if editor_command else "auto")

    if effective_id in _EDITOR_REGISTRY:
        if _launch_registry(file_path, line, effective_id, editor_path, folder):
            return True
        # Chosen editor missing/failed — drop to the Auto chain rather
        # than a possibly-stale legacy template.
        editor_command = None

    if effective_id == "custom" and editor_command:
        # Strip the ``:{line}`` / ``--line {line}`` / ``-n{line}``
        # tail when no line number is available — every editor has
        # its own grammar for "no line", and the safe answer across
        # all of them is to just open the file. Pattern: split on
        # ``{line}`` and trim whitespace + colons / dashes from the
        # right of the head before stitching together with the tail
        # (which is usually the closing ``"`` or empty).
        try:
            template = editor_command
            if line is None and "{line}" in template:
                head, _, tail = template.partition("{line}")
                head = head.rstrip(": -+,")
                template = head + tail
            # ``{python}`` resolves to the interpreter running
            # CTkMaker. Used by the IDLE preset so the call works
            # whether the system has ``python`` on PATH (Windows),
            # ``python3`` (mac/Ubuntu), or only the bundled
            # py-launcher install — sys.executable is always right.
            cmd = template.format(
                file=file_path,
                line=line if line is not None else "",
                folder=folder,
                python=f'"{sys.executable}"',
            )
            # Bare-name editor binaries (``code``, ``code-insiders``,
            # ``subl``, ``notepad++``, …) collide with unrelated
            # tools that ship the same name — Git Bash / MinGW /
            # MSYS2 / Cygwin all carry their own ``code`` that
            # rejects ``-g``. Tokenise the formatted command and
            # resolve the first arg to its real path before
            # spawning, bypassing cmd.exe's PATH lookup. Falls back
            # to the legacy shell=True path on any tokenise failure.
            try:
                tokens = shlex.split(cmd, posix=False)
            except ValueError:
                tokens = []
            if tokens:
                first = tokens[0].strip('"')
                resolved = _resolve_editor_binary(first)
                if resolved:
                    argv = [resolved] + [
                        t.strip('"') for t in tokens[1:]
                    ]
                    logger.info("launching argv: %s", argv)
                    subprocess.Popen(argv)
                    return True
            logger.info("launching shell form: %s", cmd)
            subprocess.Popen(cmd, shell=True)
            return True
        except (OSError, KeyError, IndexError) as exc:
            logger.warning("command failed: %s", exc)
    # Auto fallback chain: VS Code → Notepad++ (Windows) → IDLE.
    # Every Python install ships IDLE, so this list always ends in
    # something runnable — the user never gets a "couldn't open
    # editor" toast as long as they're running CTkMaker itself.
    code_exe = _resolve_editor_binary("code")
    if code_exe:
        try:
            target = (
                f"{file_path}:{line}" if line is not None else file_path
            )
            argv = [code_exe]
            if folder:
                # Open the project folder as a workspace first so
                # VS Code can resolve imports / activate the Python
                # extension. ``-g`` then jumps to the method line
                # inside that workspace.
                argv.append(folder)
            argv.extend(["-g", target])
            logger.info("auto VS Code: %s", argv)
            subprocess.Popen(argv)
            return True
        except OSError as exc:
            logger.warning("auto VS Code failed: %s", exc)
    npp_exe = _resolve_editor_binary("notepad++")
    if npp_exe:
        try:
            argv = [npp_exe]
            if line is not None:
                argv.append(f"-n{line}")
            argv.append(file_path)
            logger.info("auto Notepad++: %s", argv)
            subprocess.Popen(argv)
            return True
        except OSError as exc:
            logger.warning("auto Notepad++ failed: %s", exc)
    # IDLE is the universal fallback — it ships with every Python
    # install (Windows / macOS / Ubuntu) and only needs ``sys.executable``
    # to run, so it works even when the user's PATH carries no
    # editor at all.
    try:
        argv = [sys.executable, "-m", "idlelib", file_path]
        logger.info("auto IDLE: %s", argv)
        subprocess.Popen(argv)
        return True
    except OSError as exc:
        logger.warning("auto IDLE failed: %s", exc)
    if hasattr(os, "startfile"):
        try:
            os.startfile(file_path)  # type: ignore[attr-defined]
            return True
        except OSError:
            pass
    return False
