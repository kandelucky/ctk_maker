"""External editor launch — open behavior files in VS Code / Notepad++ /
PyCharm / IDLE / user-configured editor.

Resolution order:
1. ``editor_command`` template from settings (``{file}`` / ``{line}`` /
   ``{folder}`` / ``{python}`` placeholders).
2. Auto-detected VS Code.
3. Auto-detected Notepad++ (Windows).
4. IDLE (always available via ``sys.executable``).
5. ``os.startfile`` (Windows default file association).
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


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


def launch_editor(
    file_path: str | Path,
    line: int | None = None,
    editor_command: str | None = None,
    project_root: str | Path | None = None,
) -> bool:
    """Open ``file_path`` in the user's editor, jumping to ``line``
    when the editor supports it. Returns ``True`` on success.

    Resolution order (Decision #1 = C — settings + OS-default
    fallback):

    1. ``editor_command`` — user-configured template from
       ``settings.json:editor_command``. Substitutes ``{file}`` and
       ``{line}`` placeholders. Empty / missing → fall through.
    2. ``code -g <file>:<line>`` — VS Code, when ``code`` (or
       ``code.cmd`` on Windows) is on PATH. Best UX because of the
       line jump.
    3. ``os.startfile(file)`` — Windows default file association
       (notepad, IDLE, whatever the user picked for ``.py``).
    4. Last resort: return ``False`` so the caller can surface a
       "couldn't open editor" toast.
    """
    file_path = str(file_path)
    folder = str(project_root) if project_root else ""
    if editor_command:
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
                    print(f"[editor] launching argv: {argv}")
                    subprocess.Popen(argv)
                    return True
            print(f"[editor] launching shell form: {cmd}")
            subprocess.Popen(cmd, shell=True)
            return True
        except (OSError, KeyError, IndexError) as exc:
            print(f"[editor] command failed: {exc}")
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
            print(f"[editor] auto VS Code: {argv}")
            subprocess.Popen(argv)
            return True
        except OSError as exc:
            print(f"[editor] auto VS Code failed: {exc}")
    npp_exe = _resolve_editor_binary("notepad++")
    if npp_exe:
        try:
            argv = [npp_exe]
            if line is not None:
                argv.append(f"-n{line}")
            argv.append(file_path)
            print(f"[editor] auto Notepad++: {argv}")
            subprocess.Popen(argv)
            return True
        except OSError as exc:
            print(f"[editor] auto Notepad++ failed: {exc}")
    # IDLE is the universal fallback — it ships with every Python
    # install (Windows / macOS / Ubuntu) and only needs ``sys.executable``
    # to run, so it works even when the user's PATH carries no
    # editor at all.
    try:
        argv = [sys.executable, "-m", "idlelib", file_path]
        print(f"[editor] auto IDLE: {argv}")
        subprocess.Popen(argv)
        return True
    except OSError as exc:
        print(f"[editor] auto IDLE failed: {exc}")
    if hasattr(os, "startfile"):
        try:
            os.startfile(file_path)  # type: ignore[attr-defined]
            return True
        except OSError:
            pass
    return False
