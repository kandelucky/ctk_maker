"""log_error returns the formatted traceback and appends to the
crash log file. v1.9.15 — verifies the contract the crash-dialog
relies on (return string + log path stable across calls)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.core.logger import crash_log_path, log_error


def _clear_log() -> Path:
    p = crash_log_path()
    if p.exists():
        p.unlink()
    return p


def test_crash_log_path_is_in_temp() -> None:
    p = crash_log_path()
    assert p.name == "ctkmaker_crash.log"
    assert str(p).startswith(tempfile.gettempdir())


def test_log_error_returns_traceback_string() -> None:
    _clear_log()
    try:
        raise ValueError("boom")
    except ValueError:
        tb = log_error("test_ctx")
    assert "ValueError: boom" in tb
    assert "Traceback" in tb


def test_log_error_appends_to_file() -> None:
    log_path = _clear_log()
    try:
        raise RuntimeError("first")
    except RuntimeError:
        log_error("ctx_a")
    try:
        raise RuntimeError("second")
    except RuntimeError:
        log_error("ctx_b")
    contents = log_path.read_text(encoding="utf-8")
    assert "ctx_a" in contents
    assert "ctx_b" in contents
    assert "first" in contents
    assert "second" in contents


def test_log_error_no_live_exception_returns_empty() -> None:
    # Called outside an except block with no supplied exc_info — the
    # crash dialog should get an empty string and skip rendering.
    assert log_error("nothing") == ""


def test_log_error_accepts_exc_info_tuple() -> None:
    _clear_log()
    try:
        raise KeyError("captured")
    except KeyError:
        import sys
        info = sys.exc_info()
    tb = log_error("explicit", exc_info=info)
    assert "KeyError" in tb
    assert "captured" in tb
