"""Periodic autosave of the active project to a sibling ``.autosave``
file.

Layer 3 in the project safety stack:

- Layer 1 (.bak)  — ``project_saver.save_project`` rotates the prior
  save to ``<path>.ctkproj.bak`` on every explicit save.
- Layer 3 (.autosave, this module) — every ``interval_minutes`` while
  the project is **dirty AND has a saved path**, write the current
  state to ``<path>.ctkproj.autosave``. An explicit save clears the
  ``.autosave`` (no longer needed). On open, the loader checks for a
  newer ``.autosave`` and offers to restore.

Untitled projects are skipped in this layer — without a path there's
no obvious place to put the autosave. Phase 2 will spool them to
``~/.ctk_visual_builder/autosave/`` instead.
"""

from __future__ import annotations

import json
import os
import tkinter as tk
from pathlib import Path
from typing import Callable

from app.core.logger import log_error
from app.core.project import Project
from app.io.project_saver import project_to_dict

AUTOSAVE_SUFFIX = ".autosave"


def autosave_path_for(path: str | Path) -> Path:
    """Sibling ``.autosave`` for a given project path."""
    path = Path(path)
    return path.with_name(path.name + AUTOSAVE_SUFFIX)


def clear_autosave(path: str | Path | None) -> None:
    """Delete the ``.autosave`` next to ``path`` if it exists. Called
    after an explicit successful save so we don't leave a stale file
    behind to confuse the next launch.
    """
    if not path:
        return
    target = autosave_path_for(path)
    try:
        target.unlink(missing_ok=True)
    except OSError:
        log_error("clear_autosave")


class AutosaveController:
    """Owns the autosave tk-after timer for a single MainWindow.

    The MainWindow constructs one of these, calls ``start()`` once,
    and otherwise leaves it alone. The controller pulls the current
    project path from a callback (``path_provider``) on every tick so
    a Save As mid-session moves the autosave file along with the
    project.
    """

    def __init__(
        self,
        project: Project,
        root: tk.Misc,
        path_provider: Callable[[], str | None],
        interval_minutes: int = 5,
    ) -> None:
        self.project = project
        self.root = root
        self.path_provider = path_provider
        self.interval_ms = max(60, interval_minutes * 60) * 1000
        self._after_id: str | None = None
        self._is_dirty = False
        # History top at the last successful autosave write. Compared
        # to the current top each tick — if unchanged, skip the write
        # so a long idle period with no edits doesn't rewrite the
        # same .autosave content every minute.
        self._last_autosave_marker: object | None = None
        # Subscribe to project's dirty signal so we know when to skip
        # ticks (clean state) and when to bump them (dirty edits).
        self.project.event_bus.subscribe(
            "dirty_changed", self._on_dirty_changed,
        )

    # ------- public API -------

    def start(self) -> None:
        self._cancel()
        self._schedule()

    def stop(self) -> None:
        self._cancel()

    def force_now(self) -> None:
        """Best-effort autosave outside the timer — used on close so a
        dirty session leaves a recoverable file behind even if the
        user clicks Discard at the unsaved-changes prompt.
        """
        self._tick(reschedule=False)

    # ------- internals -------

    def _on_dirty_changed(self, is_dirty: bool) -> None:
        self._is_dirty = bool(is_dirty)
        # Explicit save / undo back to saved state flips dirty off;
        # forget the autosave marker so the next dirty cycle starts
        # fresh and the very first edit triggers a write again.
        if not self._is_dirty:
            self._last_autosave_marker = None

    def _schedule(self) -> None:
        try:
            self._after_id = self.root.after(
                self.interval_ms, self._tick,
            )
        except tk.TclError:
            self._after_id = None

    def _cancel(self) -> None:
        if self._after_id is None:
            return
        try:
            self.root.after_cancel(self._after_id)
        except tk.TclError:
            pass
        self._after_id = None

    def _tick(self, reschedule: bool = True) -> None:
        try:
            if self._is_dirty:
                path = self.path_provider()
                if path and self._has_changed_since_last_write():
                    self._write_autosave(path)
                    self._snapshot_marker()
        except Exception:
            log_error("autosave tick")
        if reschedule:
            self._schedule()

    def _has_changed_since_last_write(self) -> bool:
        # If we never wrote yet this dirty cycle, definitely write.
        if self._last_autosave_marker is None:
            return True
        try:
            history = self.project.history
            current_top = history._undo[-1] if history._undo else None
        except Exception:
            return True
        return current_top is not self._last_autosave_marker

    def _snapshot_marker(self) -> None:
        try:
            history = self.project.history
            self._last_autosave_marker = (
                history._undo[-1] if history._undo else None
            )
        except Exception:
            self._last_autosave_marker = None

    def _write_autosave(self, path: str) -> None:
        target = autosave_path_for(path)
        # Atomic-ish: write to .tmp first, then os.replace into final
        # name. A crash mid-write leaves the prior .autosave intact
        # (or no .autosave at all on the very first cycle).
        tmp = target.with_name(target.name + ".tmp")
        data = project_to_dict(self.project)
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, target)
        except OSError:
            log_error("autosave write")
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
