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

This module also hosts the ``EditorConsoleHandler`` — a ``logging``
handler that pushes records into the in-app Console (the same buffer
the preview-subprocess pipes feed). ``MainWindow.install_console_log_sink``
attaches it once the queue is up; records emitted before that point
land in ``_PENDING_RECORDS`` and flush on attach.
"""

from __future__ import annotations

import datetime as _dt
import logging
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Callable, Optional

_CRASH_LOG_NAME = "ctkmaker_crash.log"
_LOG_SEPARATOR = "=" * 70


def crash_log_path() -> Path:
    """``<system temp>/ctkmaker_crash.log`` — same on every launch so
    users can find one file, not a graveyard. Rotation is left to the
    OS's TEMP cleanup."""
    return Path(tempfile.gettempdir()) / _CRASH_LOG_NAME


# Module-level sink — set by MainWindow at boot. Until then, records
# go to a small pending list that flushes on install. ``Optional`` so
# the type checker stops complaining about the None state.
_CONSOLE_SINK: Optional[Callable[[str, str], None]] = None
_PENDING_RECORDS: list[tuple[str, str]] = []
# A single ``EditorConsoleHandler`` instance, registered on root once
# at app boot. Tracked so a future ``shutdown`` can detach cleanly.
_INSTALLED_HANDLER: Optional["EditorConsoleHandler"] = None


def log_error(context: str, exc_info=None) -> str:
    """Format the current (or supplied) exception, write it to stderr
    and to the crash-log file, and return the traceback string for
    inline display in a dialog.

    Also forwards to the in-app Console via ``_CONSOLE_SINK`` so the
    user sees the same traceback without needing a stderr-bound launch.

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
    _emit_console("error", f"{header}\n{tb_text.rstrip()}")
    return tb_text


def _emit_console(level: str, message: str) -> None:
    """Send a line to the in-app Console sink, or buffer it if the
    sink isn't installed yet (very early boot — e.g. autosave/logging
    fires before MainWindow.__init__ finishes wiring it up).

    Wrapped in a broad ``try/except`` — a sink failure must never
    re-enter logging or kill the calling code path.
    """
    sink = _CONSOLE_SINK
    if sink is None:
        _PENDING_RECORDS.append((level, message))
        # Bound the pending list — if the sink never installs (e.g.
        # headless test run), don't let the list grow forever.
        if len(_PENDING_RECORDS) > 500:
            del _PENDING_RECORDS[:100]
        return
    try:
        sink(level, message)
    except Exception:  # noqa: BLE001 — must never propagate
        pass


class EditorConsoleHandler(logging.Handler):
    """``logging`` handler that pushes every record into the in-app
    Console. Attached once to the root logger at app boot; the
    formatter strips the level (which becomes the stream tag instead).

    ``emit`` is intentionally minimal — format, dispatch, never re-enter
    ``logging.*``. Cross-thread safety comes from the downstream sink
    routing through ``queue.Queue.put`` (a thread-safe primitive).
    """

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.setFormatter(logging.Formatter("%(name)s | %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:  # noqa: BLE001 — format errors must not propagate
            return
        _emit_console(record.levelname.lower(), message)


def install_console_sink(sink: Callable[[str, str], None]) -> None:
    """Wire the editor-side ``logging`` handler + ``log_error`` forward
    to the supplied ``(level, message)`` callback. Flushes any records
    that arrived before the sink was ready, then registers the
    root-logger handler. Idempotent — calling twice replaces the sink
    and reuses the existing handler.
    """
    global _CONSOLE_SINK, _INSTALLED_HANDLER
    _CONSOLE_SINK = sink
    pending = list(_PENDING_RECORDS)
    _PENDING_RECORDS.clear()
    for level, message in pending:
        try:
            sink(level, message)
        except Exception:  # noqa: BLE001
            pass
    if _INSTALLED_HANDLER is None:
        handler = EditorConsoleHandler()
        logging.getLogger().addHandler(handler)
        # Root defaults to WARNING; raise to DEBUG so the handler sees
        # everything. Users can override if they want.
        if logging.getLogger().level > logging.DEBUG:
            logging.getLogger().setLevel(logging.DEBUG)
        # Mute well-known noisy third-party loggers. PIL alone emits a
        # ``STREAM b'IHDR' / b'pHYs' / b'IDAT'`` line per PNG chunk per
        # icon load — a single CTkMaker startup decodes dozens of icons
        # and dumps hundreds of lines that drown out anything useful.
        # Capped at WARNING here; user can still re-enable per logger
        # with ``logging.getLogger("PIL").setLevel(logging.DEBUG)`` if
        # they actually need to debug image decoding.
        for noisy in ("PIL", "urllib3", "matplotlib", "asyncio"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
        _INSTALLED_HANDLER = handler
