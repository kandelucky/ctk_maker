"""Number editor: inline tk.Entry overlay on double-click + ±1 spinner.

Each numeric row gets a tiny vertical spinner (▲ / ▼) overlay pinned to
the right edge of the value cell. Click steps ±1; hold auto-repeats.
min/max clamp uses the same schema fields as the horizontal drag-scrub,
so both input paths stay consistent. Press / release brackets one
ChangePropertyCommand so a hold collapses into a single undo step.
"""

from __future__ import annotations

import tkinter as tk

from app.core.commands import ChangePropertyCommand

from ..constants import DISABLED_FG, TREE_FG, VALUE_BG
from ..overlays import SLOT_NUMBER_SPIN, place_number_spin
from .base import Editor


_REPEAT_DELAY_MS = 350
_REPEAT_INTERVAL_MS = 60
_BTN_BG = "#2d2d2d"
_BTN_HOVER_BG = "#3a3a3a"


class NumberEditor(Editor):
    def populate(self, panel, iid, pname, prop, value) -> None:
        if panel.overlays is None:
            return
        spinner = _NumberSpinner(panel.tree, panel, pname, prop)
        panel.overlays.add(
            iid, SLOT_NUMBER_SPIN, spinner, place_number_spin,
        )

    def set_disabled(self, panel, iid, pname, prop, disabled) -> None:
        if panel.overlays is None:
            return
        spinner = panel.overlays.get(iid, SLOT_NUMBER_SPIN)
        if isinstance(spinner, _NumberSpinner):
            spinner.set_disabled(disabled)

    def on_double_click(self, panel, pname, prop, event) -> bool:
        iid = panel._prop_iids.get(pname)
        if iid is None:
            return False
        bbox = panel.tree.bbox(iid, "#1")
        if not bbox:
            return False
        panel._commit_active_editor()
        panel._open_entry_overlay(iid, pname, prop, bbox)
        return True


class _NumberSpinner(tk.Frame):
    """Two-button ▲ / ▼ overlay. Press→step, hold→repeat, release→undo."""

    def __init__(self, master, panel, pname, prop):
        super().__init__(
            master, bg=VALUE_BG, bd=0, highlightthickness=0,
        )
        self._panel = panel
        self._pname = pname
        self._prop = prop
        self._repeat_job: str | None = None
        self._active_direction = 0
        self._disabled = False
        self._start_value: int = 0
        self._start_widget_id: str | None = None

        self._up = self._make_button("▲", +1)
        self._up.place(relx=0, rely=0, relwidth=1, relheight=0.5)
        self._down = self._make_button("▼", -1)
        self._down.place(relx=0, rely=0.5, relwidth=1, relheight=0.5)

        self.bind("<Destroy>", self._on_destroy)

    def _make_button(self, glyph: str, direction: int) -> tk.Label:
        lbl = tk.Label(
            self, text=glyph, bg=_BTN_BG, fg=TREE_FG,
            font=("Segoe UI", 6), cursor="arrow",
        )
        lbl.bind(
            "<ButtonPress-1>", lambda _e, d=direction: self._press(d),
        )
        lbl.bind("<ButtonRelease-1>", self._release)
        lbl.bind(
            "<Enter>", lambda _e, w=lbl: self._hover(w, True),
        )
        lbl.bind(
            "<Leave>", lambda _e, w=lbl: self._hover(w, False),
        )
        return lbl

    # ------------------------------------------------------------------
    # Visual feedback
    # ------------------------------------------------------------------
    def _hover(self, label: tk.Label, inside: bool) -> None:
        if self._disabled:
            return
        try:
            label.configure(bg=_BTN_HOVER_BG if inside else _BTN_BG)
        except tk.TclError:
            pass

    def set_disabled(self, disabled: bool) -> None:
        self._disabled = disabled
        fg = DISABLED_FG if disabled else TREE_FG
        for lbl in (self._up, self._down):
            try:
                lbl.configure(fg=fg, bg=_BTN_BG)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Step loop
    # ------------------------------------------------------------------
    def _press(self, direction: int) -> None:
        if self._disabled:
            return
        panel = self._panel
        if panel.current_id is None:
            return
        node = panel.project.get_widget(panel.current_id)
        if node is None:
            return
        self._start_value = self._read_int(node.properties)
        self._start_widget_id = panel.current_id
        self._active_direction = direction
        # Suspend history so the repeat loop collapses into one undo
        # entry pushed at release — matches drag_scrub's approach.
        panel._suspend_history = True
        self._step(direction)
        try:
            self._repeat_job = self.after(
                _REPEAT_DELAY_MS, self._repeat,
            )
        except tk.TclError:
            self._repeat_job = None

    def _repeat(self) -> None:
        if self._active_direction == 0:
            return
        try:
            self._step(self._active_direction)
        except tk.TclError:
            return
        try:
            self._repeat_job = self.after(
                _REPEAT_INTERVAL_MS, self._repeat,
            )
        except tk.TclError:
            self._repeat_job = None

    def _release(self, _event=None) -> None:
        self._active_direction = 0
        self._cancel_repeat()
        panel = self._panel
        panel._suspend_history = False
        widget_id = self._start_widget_id
        self._start_widget_id = None
        if widget_id is None:
            return
        node = panel.project.get_widget(widget_id)
        if node is None:
            return
        after = self._read_int(node.properties)
        if after == self._start_value:
            return
        panel.project.history.push(
            ChangePropertyCommand(
                widget_id, self._pname, self._start_value, after,
            ),
        )

    def _step(self, delta: int) -> None:
        panel = self._panel
        if panel.current_id is None:
            return
        node = panel.project.get_widget(panel.current_id)
        if node is None:
            return
        current = self._read_int(node.properties)
        new_value = self._clamp(current + delta, node.properties)
        if new_value == current:
            return
        panel._commit_prop(self._pname, new_value)

    def _cancel_repeat(self) -> None:
        if self._repeat_job is not None:
            try:
                self.after_cancel(self._repeat_job)
            except (ValueError, tk.TclError):
                pass
            self._repeat_job = None

    def _on_destroy(self, _event=None) -> None:
        self._active_direction = 0
        self._cancel_repeat()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _read_int(self, props: dict) -> int:
        try:
            return int(props.get(self._pname, 0) or 0)
        except (ValueError, TypeError):
            return 0

    def _clamp(self, value: int, props: dict) -> int:
        min_val = self._prop.get("min")
        max_val = self._prop.get("max")
        if callable(min_val):
            try:
                min_val = min_val(props)
            except Exception:
                min_val = None
        if callable(max_val):
            try:
                max_val = max_val(props)
            except Exception:
                max_val = None
        if min_val is not None:
            try:
                value = max(int(min_val), value)
            except (ValueError, TypeError):
                pass
        if max_val is not None:
            try:
                value = min(int(max_val), value)
            except (ValueError, TypeError):
                pass
        return value
