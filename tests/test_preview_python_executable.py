"""Preview subprocess picks a console-capable Python interpreter.

Pre-1.9.11 the preview ``Popen`` call passed ``sys.executable`` straight
through. When CTk Maker was launched via a desktop shortcut targeting
``pythonw.exe`` (the windowless Python variant), ``sys.executable``
inherited that path. Spawning the preview runner under
``CREATE_NEW_CONSOLE`` then produced no visible console — pythonw
doesn't bind stdio to the new window — so ``print()`` output and
crash tracebacks vanished silently.

The fix swaps ``pythonw.exe`` for the sibling ``python.exe`` (when
present) on Windows. Other platforms and non-pythonw launches are
untouched.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.ui.main_window import _preview_python_executable


def test_pythonw_swapped_for_python_when_sibling_exists():
    fake_pythonw = r"C:\Python\pythonw.exe"
    with patch("app.ui.main_window.sys") as fake_sys, \
            patch.object(Path, "exists", lambda self: True):
        fake_sys.executable = fake_pythonw
        fake_sys.platform = "win32"
        result = _preview_python_executable()
    assert Path(result).name.lower() == "python.exe"


def test_pythonw_kept_when_sibling_python_missing():
    """No silent fallback to a non-existent path — if python.exe isn't
    next to pythonw.exe (broken/custom install), keep sys.executable
    so the launch still tries something the user has on disk.
    """
    fake_pythonw = r"C:\Python\pythonw.exe"
    with patch("app.ui.main_window.sys") as fake_sys, \
            patch.object(Path, "exists", lambda self: False):
        fake_sys.executable = fake_pythonw
        fake_sys.platform = "win32"
        result = _preview_python_executable()
    assert result == fake_pythonw


def test_python_exe_passed_through_unchanged():
    fake_python = r"C:\Python\python.exe"
    with patch("app.ui.main_window.sys") as fake_sys:
        fake_sys.executable = fake_python
        fake_sys.platform = "win32"
        result = _preview_python_executable()
    assert result == fake_python


def test_non_windows_platforms_untouched():
    """``creationflags`` / ``CREATE_NEW_CONSOLE`` are Windows-only —
    on Linux/macOS the preview inherits the launching terminal's
    stdio anyway, so the helper just hands back sys.executable.
    """
    with patch("app.ui.main_window.sys") as fake_sys:
        fake_sys.executable = "/usr/bin/python3"
        fake_sys.platform = "linux"
        result = _preview_python_executable()
    assert result == "/usr/bin/python3"


def test_case_insensitive_basename_match():
    """File system case shouldn't decide whether the swap fires —
    Windows treats ``Pythonw.exe`` and ``pythonw.exe`` as the same
    file. The check uses ``.lower()`` so either is recognised.
    """
    fake_pythonw = r"C:\Python\Pythonw.EXE"
    with patch("app.ui.main_window.sys") as fake_sys, \
            patch.object(Path, "exists", lambda self: True):
        fake_sys.executable = fake_pythonw
        fake_sys.platform = "win32"
        result = _preview_python_executable()
    assert Path(result).name.lower() == "python.exe"
