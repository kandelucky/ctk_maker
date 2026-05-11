"""Color editor: persistent swatch overlay + color picker dialog.

Schema can mark a colour property ``clearable: True`` (or a callable
``clearable(props) -> bool`` for context-dependent cases) with an
optional ``clear_value`` (defaults to ``None``). When set, the editor
draws a small ✕ button at the right edge of the value cell — click
resets the prop to its ``clear_value`` (typical uses: ``image_color``
= ``None``, ``fg_color`` / ``bg_color`` = ``"transparent"``). Covers
the UX gap where once a colour was picked the user had to type the
sentinel back in by hand to return to the "inactive" default.
"""

from __future__ import annotations

import tkinter as tk

from ..constants import BOOL_OFF_FG, TREE_FG, VALUE_BG
from ..overlays import (
    SLOT_BOUND_COLOR_SWATCH,
    SLOT_COLOR,
    SLOT_COLOR_CLEAR,
    place_bound_color_swatch,
    place_color_clear,
    place_color_swatch,
)
from app.ui.system_fonts import ui_font
from .base import Editor

# CTk-only sentinel values that Tk's colour parser rejects. Map them
# to a readable swatch background so editors can render without
# tripping `_tkinter.TclError: unknown color name "transparent"`.
_CTK_SENTINEL_BG = {
    "transparent": "#2b2b2b",
}


def _swatch_bg(value) -> str:
    if not value:
        return VALUE_BG
    text = str(value)
    if text in _CTK_SENTINEL_BG:
        return _CTK_SENTINEL_BG[text]
    return text


_CLEARED_SENTINELS = frozenset({None, "", "transparent"})


def _is_cleared(value, clear_value) -> bool:
    """True when the current value matches the schema's clear sentinel.

    ``None`` and ``"transparent"`` are treated as equivalent cleared
    states so that a field whose clear_value is ``"transparent"``
    shows the ✕ as inactive when the stored value is still ``None``
    (e.g. a freshly-dropped widget whose optional tint was never set).
    """
    if value == clear_value:
        return True
    # Both "empty-like" and both sentinels → cleared.
    if value in _CLEARED_SENTINELS and clear_value in _CLEARED_SENTINELS:
        return True
    return False


class ColorEditor(Editor):
    def populate(self, panel, iid, pname, prop, value) -> None:
        try:
            overlay = tk.Frame(
                panel.tree, bg=_swatch_bg(value),
                highlightthickness=1, highlightbackground="#3a3a3a",
                cursor="hand2",
            )
        except tk.TclError:
            # Any other unrecognised colour — fall back to the neutral
            # value-bg so the editor still renders.
            overlay = tk.Frame(
                panel.tree, bg=VALUE_BG,
                highlightthickness=1, highlightbackground="#3a3a3a",
                cursor="hand2",
            )
        overlay.bind(
            "<Button-1>",
            lambda _e, p=pname: panel._pick_color(p),
        )
        panel.overlays.add(iid, SLOT_COLOR, overlay, place_color_swatch)
        if self._is_clearable(panel, prop):
            self._add_clear_button(panel, iid, pname, prop, value)

    def _is_clearable(self, panel, prop: dict) -> bool:
        """Resolve ``clearable`` — bool literal or a callable that takes
        the current node's properties dict. Callable form lets a schema
        opt in only when the context matches (e.g. CTkFrame's fg_color
        is clearable only for Layout Frames, never for plain ones)."""
        flag = prop.get("clearable")
        if callable(flag):
            node = panel.project.get_widget(panel.current_id)
            props = node.properties if node is not None else {}
            try:
                return bool(flag(props))
            except Exception:
                return False
        return bool(flag)

    def _add_clear_button(
        self, panel, iid: str, pname: str, prop: dict, value,
    ) -> None:
        clear_value = prop.get("clear_value")
        cleared = _is_cleared(value, clear_value)
        btn = tk.Label(
            panel.tree, text="✕", bg=VALUE_BG,
            fg=self._clear_fg(value, clear_value),
            font=ui_font(9),
            cursor="arrow" if cleared else "hand2",
            highlightthickness=0, bd=0,
        )

        def _on_click(_e, p=pname, cv=clear_value, w=btn):
            if _is_cleared(self._read_value(panel, p), cv):
                return
            panel._commit_prop(p, cv)

        def _on_enter(_e, w=btn, p=pname, cv=clear_value):
            if not _is_cleared(self._read_value(panel, p), cv):
                w.configure(fg=TREE_FG)

        def _on_leave(_e, w=btn, p=pname, cv=clear_value):
            val = self._read_value(panel, p)
            is_cleared = _is_cleared(val, cv)
            w.configure(
                fg=self._clear_fg(val, cv),
                cursor="arrow" if is_cleared else "hand2",
            )

        btn.bind("<Button-1>", _on_click)
        btn.bind("<Enter>", _on_enter)
        btn.bind("<Leave>", _on_leave)
        panel.overlays.add(iid, SLOT_COLOR_CLEAR, btn, place_color_clear)

    def _clear_fg(self, value, clear_value) -> str:
        """✕ glyph dims to the bool-off grey when the colour is
        already cleared — there's nothing to clear, but the button
        still exists so layout stays stable."""
        return BOOL_OFF_FG if _is_cleared(value, clear_value) else TREE_FG

    def _read_value(self, panel, pname: str):
        node = panel.project.get_widget(panel.current_id)
        return node.properties.get(pname) if node is not None else None

    def refresh(self, panel, iid, pname, prop, value) -> None:
        overlay = panel.overlays.get(iid, SLOT_COLOR)
        if overlay is not None:
            try:
                overlay.configure(bg=_swatch_bg(value))
            except tk.TclError:
                pass
        btn = panel.overlays.get(iid, SLOT_COLOR_CLEAR)
        if btn is not None:
            try:
                btn.configure(
                    fg=self._clear_fg(value, prop.get("clear_value")),
                )
            except tk.TclError:
                pass

    def set_disabled(self, panel, iid, pname, prop, disabled) -> None:
        overlay = panel.overlays.get(iid, SLOT_COLOR)
        if overlay is None:
            return
        node = panel.project.get_widget(panel.current_id)
        val = node.properties.get(pname) if node else None
        try:
            overlay.configure(
                bg="#444444" if disabled else _swatch_bg(val),
                cursor="arrow" if disabled else "hand2",
            )
        except tk.TclError:
            pass
        btn = panel.overlays.get(iid, SLOT_COLOR_CLEAR)
        if btn is not None:
            try:
                btn.configure(
                    fg=BOOL_OFF_FG if disabled else self._clear_fg(
                        val, prop.get("clear_value"),
                    ),
                    cursor="arrow" if disabled else "hand2",
                )
            except tk.TclError:
                pass

    def populate_bound(self, panel, iid: str, pname: str) -> None:
        """Render the picker-affordance swatch on a variable-bound row.
        The regular ``populate`` is skipped for bound rows (the chip
        pill owns the value cell), but the color editor still needs a
        clickable surface to surface the picker-edits-variable flow.
        Resolves the swatch fill through the live tk var so the
        rendered color tracks whatever the variable currently holds.
        """
        from app.core.variables import parse_var_token
        node = panel.project.get_widget(panel.current_id)
        if node is None:
            return
        var_id = parse_var_token(node.properties.get(pname))
        if var_id is None:
            return
        tk_var = panel.project.get_tk_var(var_id)
        try:
            hex_color = tk_var.get() if tk_var is not None else None
        except Exception:
            hex_color = None
        overlay = tk.Frame(
            panel.tree, bg=_swatch_bg(hex_color),
            highlightthickness=1, highlightbackground="#3a3a3a",
            cursor="hand2",
        )
        overlay.bind(
            "<Button-1>",
            lambda _e, p=pname: panel._pick_color(p),
        )
        panel.overlays.add(
            iid, SLOT_BOUND_COLOR_SWATCH, overlay, place_bound_color_swatch,
        )

    def on_double_click(self, panel, pname, prop, event) -> bool:
        # Var-bound rows are intercepted in panel_commit._on_double_click
        # before this dispatch (jumps to the Variables window), so the
        # editor only sees literal values here.
        panel._pick_color(pname)
        return True
