"""Dark drop-in replacements for ``tkinter.messagebox``.

Native message boxes are drawn by the OS with the light theme, so
CTkMaker's dark palette can never apply to them — the only way to a
consistent look is to not open them at all. This module provides
``DarkDialog``-based equivalents with the native argument shape
(``title, message, parent``) so migrating a call site is mechanical.

Visual language ("hero line" layout, TintKit-derived): a 3px severity
bar + bold title inside the card, dim body text, flat buttons aligned
bottom-right with the affirmative rightmost. Every colour derives from
one seed per role (accent / danger / warn) via ``_shades`` — change a
seed and the whole dialog family follows.

Safety contract — each rule guards a known way a themed replacement
of a native message box breaks:

* Any ``TclError`` on the themed path falls back to the real
  ``tkinter.messagebox``, so a message (usually an error report) is
  never lost just because the themed dialog could not be built.
* Re-entry guard — key autorepeat (e.g. holding Delete) can re-fire
  the calling handler while ``safe_grab_set``'s ``wait_visibility``
  pumps events. An identical dialog that is already open is lifted
  instead of duplicated and the duplicate call returns its cancel
  default.
* ``parent=None`` resolves to the window registered via
  ``set_default_parent`` (falling back to Tk's default root); with no
  usable parent at all the native box is used rather than crashing.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from app.ui.dialog_utils import safe_grab_set
from app.ui.dialogs._base import DarkDialog
from app.ui.dialogs._colors import (
    FG_DIM,
    PANEL,
    dialog_scaling,
    flat_button,
    hero_header,
)
from app.ui.system_fonts import ui_font


class MessageDialog(DarkDialog):
    """Modal message/question dialog, hero-line layout.

    ``buttons`` is a sequence of ``(text, value, role)`` tuples laid
    out bottom-right, affirmative last (= rightmost, Return default).
    Escape / titlebar close yield ``cancel_value``. The caller reads
    ``self.result`` after ``wait_window``.
    """

    def __init__(
        self, parent, title: str, message: str, *,
        buttons: tuple[tuple[str, object, str], ...],
        cancel_value: object = None,
        severity: str = "info",
    ) -> None:
        super().__init__(parent, fg_color=PANEL)
        self.title(title)
        self.result: object = cancel_value
        self._cancel_value = cancel_value
        self._default_value = buttons[-1][1]
        self._s = dialog_scaling(self)
        self._build(title, message, buttons, severity)
        self.update_idletasks()
        W = max(round(400 * self._s), self.winfo_reqwidth())
        H = self.winfo_reqheight()
        self.place_centered(W, H, parent)
        self.lift()
        self.focus_set()
        safe_grab_set(self)
        self.reveal()

    def _build(
        self, title: str, message: str,
        buttons: tuple[tuple[str, object, str], ...],
        severity: str,
    ) -> None:
        s = self._s
        hero_header(self, title, severity, s)
        tk.Label(
            self, text=message,
            bg=PANEL, fg=FG_DIM, font=ui_font(round(10 * s)),
            justify="left", wraplength=round(350 * s), anchor="w",
        ).pack(
            fill="x", padx=(round(31 * s), round(18 * s)),
            pady=(round(6 * s), round(14 * s)),
        )
        row = tk.Frame(self, bg=PANEL)
        row.pack(fill="x", padx=round(18 * s), pady=(0, round(16 * s)))
        # right-aligned, affirmative rightmost — pack in reverse
        for text, value, role in reversed(buttons):
            flat_button(
                row, text, role, lambda v=value: self._finish(v), s,
            ).pack(side="right", padx=(round(8 * s), 0))
        self.bind("<Escape>", lambda _e: self._finish(self._cancel_value))
        self.bind("<Return>", lambda _e: self._finish(self._default_value))
        self.protocol(
            "WM_DELETE_WINDOW",
            lambda: self._finish(self._cancel_value),
        )

    def _finish(self, value: object) -> None:
        self.result = value
        self.destroy()


# ----------------------------------------------------------------------
# Module-level wrappers (the migration surface)

_default_parent: tk.Misc | None = None

# (severity, title, message) keys of currently-open dialogs — the
# re-entry guard from the module docstring.
_open_keys: set[tuple[str, str, str]] = set()


def set_default_parent(widget: tk.Misc) -> None:
    """Register the main window as the fallback dialog parent."""
    global _default_parent
    _default_parent = widget


def _alive(widget: tk.Misc | None) -> bool:
    if widget is None:
        return False
    try:
        return bool(widget.winfo_exists())
    except tk.TclError:
        return False


def _resolve_parent(parent: tk.Misc | None) -> tk.Misc | None:
    if _alive(parent):
        return parent
    if _alive(_default_parent):
        return _default_parent
    root = getattr(tk, "_default_root", None)
    return root if _alive(root) else None


def _run(
    title: str, message: str, parent: tk.Misc | None, *,
    buttons: tuple[tuple[str, object, str], ...],
    cancel_value: object, severity: str,
    native_fallback,
):
    key = (severity, title, message)
    if key in _open_keys:
        return cancel_value
    owner = _resolve_parent(parent)
    if owner is None:
        return native_fallback()
    _open_keys.add(key)
    try:
        dialog = MessageDialog(
            owner, title, message,
            buttons=buttons, cancel_value=cancel_value, severity=severity,
        )
        dialog.wait_window()
        return dialog.result
    except tk.TclError:
        return native_fallback()
    finally:
        _open_keys.discard(key)


def show_info(title: str, message: str, parent=None) -> None:
    _run(
        title, message, parent,
        buttons=(("OK", None, "accent"),),
        cancel_value=None, severity="info",
        native_fallback=lambda: messagebox.showinfo(
            title=title, message=message,
        ),
    )


def show_warning(title: str, message: str, parent=None) -> None:
    _run(
        title, message, parent,
        buttons=(("OK", None, "accent"),),
        cancel_value=None, severity="warning",
        native_fallback=lambda: messagebox.showwarning(
            title=title, message=message,
        ),
    )


def show_error(title: str, message: str, parent=None) -> None:
    _run(
        title, message, parent,
        buttons=(("OK", None, "accent"),),
        cancel_value=None, severity="error",
        native_fallback=lambda: messagebox.showerror(
            title=title, message=message,
        ),
    )


def ask_yes_no(
    title: str, message: str, parent=None, *,
    danger: bool = False,
    yes_text: str = "Yes", no_text: str = "No",
) -> bool:
    return bool(_run(
        title, message, parent,
        buttons=(
            (no_text, False, "ghost"),
            (yes_text, True, "danger" if danger else "accent"),
        ),
        cancel_value=False,
        severity="error" if danger else "question",
        native_fallback=lambda: messagebox.askyesno(
            title=title, message=message,
        ),
    ))


def ask_ok_cancel(
    title: str, message: str, parent=None, *,
    ok_text: str = "OK", cancel_text: str = "Cancel",
) -> bool:
    return bool(_run(
        title, message, parent,
        buttons=(
            (cancel_text, False, "ghost"),
            (ok_text, True, "accent"),
        ),
        cancel_value=False, severity="question",
        native_fallback=lambda: messagebox.askokcancel(
            title=title, message=message,
        ),
    ))


def ask_yes_no_cancel(
    title: str, message: str, parent=None,
) -> bool | None:
    # Three-state: Yes → True, No → False, Cancel/Escape → None —
    # exactly ``messagebox.askyesnocancel``'s contract.
    result = _run(
        title, message, parent,
        buttons=(
            ("Cancel", None, "ghost"),
            ("No", False, "ghost"),
            ("Yes", True, "accent"),
        ),
        cancel_value=None, severity="question",
        native_fallback=lambda: messagebox.askyesnocancel(
            title=title, message=message,
        ),
    )
    return result if isinstance(result, bool) else None


def ask_string(
    title: str, prompt: str, parent=None, initialvalue: str = "",
) -> str | None:
    """Themed ``simpledialog.askstring`` stand-in on ``RenameDialog``."""
    from app.ui.dialogs.rename import RenameDialog

    owner = _resolve_parent(parent)
    if owner is None:
        from tkinter import simpledialog
        return simpledialog.askstring(
            title, prompt, initialvalue=initialvalue,
        )
    dialog = RenameDialog(
        owner, initialvalue, title=title, label=prompt,
    )
    return dialog.result
