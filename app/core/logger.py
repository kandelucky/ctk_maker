"""Crash logging — single point for swallowed exceptions.

Originally just printed to stderr. v1.9.15 also appends to a rolling
log file (``%TEMP%/ctkmaker_crash.log``) and returns the formatted
traceback so callers can show it inline in a dialog. This matters for
shortcut launches (target = ``pythonw.exe``), where stderr is detached
and the long-standing "see console" dialog text was a dead end — no
console exists to read.

The log file is best-effort: if writing fails (read-only TEMP, disk
full, race), we still print to stderr and return the traceback string
so the caller's dialog still surfaces something useful.
"""

from __future__ import annotations

import datetime as _dt
import sys
import tempfile
import traceback
from pathlib import Path

_CRASH_LOG_NAME = "ctkmaker_crash.log"
_LOG_SEPARATOR = "=" * 70


def crash_log_path() -> Path:
    """``<system temp>/ctkmaker_crash.log`` — same on every launch so
    users can find one file, not a graveyard. Rotation is left to the
    OS's TEMP cleanup."""
    return Path(tempfile.gettempdir()) / _CRASH_LOG_NAME


def log_error(context: str, exc_info=None) -> str:
    """Format the current (or supplied) exception, write it to stderr
    and to the crash-log file, and return the traceback string for
    inline display in a dialog.

    ``exc_info`` follows ``sys.exc_info()`` shape ``(type, value, tb)``
    or ``None`` to use the live exception. When called outside an
    ``except`` block with no exception, returns an empty string.
    """
    if exc_info is None:
        exc_info = sys.exc_info()
    exc_type, exc_value, exc_tb = exc_info
    if exc_type is None:
        return ""
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    header = f"[ERROR {context}]"
    print(header, file=sys.stderr)
    print(tb_text, file=sys.stderr, end="")
    try:
        stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with crash_log_path().open("a", encoding="utf-8") as fh:
            fh.write(f"{_LOG_SEPARATOR}\n{stamp}  {header}\n{tb_text}\n")
    except OSError:
        pass
    return tb_text
