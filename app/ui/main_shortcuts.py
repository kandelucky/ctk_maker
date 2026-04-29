"""Keyboard shortcut wiring + non-Latin layout fallback mixin.

Split out of the monolithic ``main_window.py`` (v0.0.15.17 refactor).
Covers every piece of global keyboard handling:

- ``<Control-n>`` / ``<Control-o>`` / ``<Control-s>`` ... app-level
  accelerators routed to the corresponding ``MainWindow._on_*`` method
- ``<Control-KeyPress>`` fallback that routes by hardware keycode so
  Ctrl+V / C / X / S / Z ... still fire on non-Latin keyboard layouts
  (bpo-46052 — Tk can't match the Latin keysym on non-Latin layouts)
- ``<KeyPress-z/y>`` + ``<KeyRelease>`` guards that kill OS key-repeat
  on Ctrl+Z / Ctrl+Y — one press = one undo step
- ``<<Copy>>`` / ``<<Paste>>`` virtual events so Object Tree's own
  handlers win when the tree has focus, and our fallback runs
  otherwise

Relies on ``MainWindow`` for the actual action methods (``_on_new``,
``_on_save``, ``_on_undo``, ``_on_menu_copy`` etc.) and the held-state
flags (``_undo_key_held`` / ``_redo_key_held``).
"""

from __future__ import annotations

import tkinter as tk


class ShortcutsMixin:
    """Global keyboard shortcut handlers. See module docstring."""

    # Event.state bit masks on Windows.
    # Tk's <Control-z> binding fires for every OS-generated auto-repeat,
    # so holding Ctrl+Z rips the entire history. We bind raw
    # <KeyPress-z> / <KeyRelease-z> instead and ignore auto-repeat
    # presses via a held-state flag.
    _CTRL_MASK = 0x04
    _SHIFT_MASK = 0x01

    # ------------------------------------------------------------------
    # Non-Latin layout keycode router
    # ------------------------------------------------------------------
    def _on_control_keypress(self, event) -> str | None:
        # If the keysym is already the Latin letter, tk's default
        # binding handled (or will handle) the shortcut — don't double.
        latin = event.keysym.lower()
        if latin in (
            "v", "c", "x", "a", "s", "n", "o", "w", "q", "r", "z", "y",
            "d", "i", "p", "m", "g",
        ):
            return None
        kc = event.keycode
        widget = event.widget
        if kc == 86:  # V
            widget.event_generate("<<Paste>>")
            return "break"
        if kc == 67:  # C
            widget.event_generate("<<Copy>>")
            return "break"
        if kc == 88:  # X
            widget.event_generate("<<Cut>>")
            return "break"
        if kc == 65:  # A
            focused = self.focus_get()
            if isinstance(focused, (tk.Entry, tk.Text)):
                try:
                    focused.event_generate("<<SelectAll>>")
                except tk.TclError:
                    pass
            else:
                self._on_menu_select_all()
            return "break"
        if kc == 83:  # S
            self._on_save()
            return "break"
        if kc == 78:  # N
            self._on_new()
            return "break"
        if kc == 79:  # O
            self._on_open()
            return "break"
        if kc == 87:  # W
            self._on_close_project()
            return "break"
        if kc == 81:  # Q
            self._on_quit()
            return "break"
        if kc == 82:  # R
            self._on_preview()
            return "break"
        if kc == 68:  # D
            self._on_menu_duplicate()
            return "break"
        if kc == 73:  # I
            if event.state & self._SHIFT_MASK:
                self._on_docs_shortcut()
            else:
                self._on_menu_rename()
            return "break"
        if kc == 80:  # P
            self._on_preview_active()
            return "break"
        if kc == 77:  # M
            self._on_add_dialog()
            return "break"
        if kc == 71:  # G
            if event.state & self._SHIFT_MASK:
                self._on_ungroup_shortcut()
            else:
                self._on_group_shortcut()
            return "break"
        if kc == 90:  # Z
            is_redo = bool(event.state & self._SHIFT_MASK)
            held = self._redo_key_held if is_redo else self._undo_key_held
            if held:
                return "break"
            if is_redo:
                self._redo_key_held = True
                self._on_redo()
            else:
                self._undo_key_held = True
                self._on_undo()
            return "break"
        if kc == 89:  # Y
            if self._redo_key_held:
                return "break"
            self._redo_key_held = True
            self._on_redo()
            return "break"
        return None

    # ------------------------------------------------------------------
    # Bind setup — called once from MainWindow.__init__
    # ------------------------------------------------------------------
    def _bind_shortcuts(self) -> None:
        self.bind("<Control-n>", lambda e: self._on_new())
        self.bind("<Control-o>", lambda e: self._on_open())
        self.bind("<Control-s>", lambda e: self._on_save())
        self.bind("<Control-Shift-S>", lambda e: self._on_save_as())
        self.bind("<Control-r>", lambda e: self._on_preview())
        self.bind("<Control-w>", lambda e: self._on_close_project())
        self.bind("<F8>", lambda e: self._on_f8_object_tree())
        self.bind("<F9>", lambda e: self._on_f9_history_window())
        self.bind("<F10>", lambda e: self._on_f10_project_window())
        self.bind("<F11>", lambda e: self._on_f11_variables_window())
        self.bind("<Control-q>", lambda e: self._on_quit())
        self.bind("<Control-comma>", lambda e: self._on_open_preferences())
        # bind_all so undo/redo works when the Object Tree toplevel
        # has focus too — regular `self.bind` only fires for the
        # main window's widget tree.
        # Block OS key-repeat on Ctrl+Z / Ctrl+Y — holding the key
        # rips through the entire history in a blur. One press = one
        # undo; releasing + pressing again is required for the next
        # step. Tracks the pressed state per-accelerator; KeyPress
        # events past the first are ignored until the matching
        # KeyRelease clears the flag.
        self._undo_key_held: bool = False
        self._redo_key_held: bool = False
        self.bind_all("<KeyPress-z>", self._on_undo_keypress)
        self.bind_all("<KeyRelease-z>", self._on_undo_keyrelease)
        self.bind_all("<KeyPress-y>", self._on_redo_keypress)
        self.bind_all("<KeyRelease-y>", self._on_redo_keyrelease)
        self.bind_all("<KeyPress-Z>", self._on_redo_keypress)
        self.bind_all("<KeyRelease-Z>", self._on_redo_keyrelease)
        # Non-Latin keyboard layouts send their own keysyms instead of
        # the Latin z/y, so the KeyRelease bindings above never fire.
        # Catch by hardware keycode instead so the held flags clear on
        # release.
        self.bind_all("<KeyRelease>", self._on_any_keyrelease)
        # Copy / Paste at the main-window level so they work regardless
        # of which panel has focus. Widget bindings fire first in tk's
        # dispatch order, so Object Tree's own handlers still win when
        # the tree is focused; these are the fallback for everything
        # else (canvas, palette, empty focus). Entry / Text widgets
        # short-circuit so native text copy/paste keeps working there.
        self.bind("<Control-c>", self._on_copy_shortcut)
        self.bind("<Control-C>", self._on_copy_shortcut)
        self.bind("<Control-v>", self._on_paste_shortcut)
        self.bind("<Control-V>", self._on_paste_shortcut)
        self.bind("<Control-x>", self._on_cut_shortcut)
        self.bind("<Control-X>", self._on_cut_shortcut)
        self.bind("<Control-d>", lambda e: self._on_menu_duplicate())
        self.bind("<Control-D>", lambda e: self._on_menu_duplicate())
        self.bind("<Control-i>", lambda e: self._on_menu_rename())
        self.bind("<Control-I>", lambda e: self._on_menu_rename())
        self.bind("<Control-Shift-I>", lambda e: self._on_docs_shortcut())
        self.bind("<Control-p>", lambda e: self._on_preview_active())
        self.bind("<Control-P>", lambda e: self._on_preview_active())
        self.bind("<Control-m>", lambda e: self._on_add_dialog())
        self.bind("<Control-M>", lambda e: self._on_add_dialog())
        self.bind("<Control-g>", lambda e: self._on_group_shortcut())
        self.bind("<Control-G>", lambda e: self._on_group_shortcut())
        self.bind("<Control-Shift-G>", lambda e: self._on_ungroup_shortcut())
        self.bind_all("<Control-a>", self._on_select_all_shortcut)
        self.bind_all("<Control-A>", self._on_select_all_shortcut)
        self.bind("<<Copy>>", self._on_copy_shortcut)
        self.bind("<<Paste>>", self._on_paste_shortcut)
        self.bind("<<Cut>>", self._on_cut_shortcut)

    # ------------------------------------------------------------------
    # Auto-repeat guards
    # ------------------------------------------------------------------
    def _on_undo_keypress(self, event) -> str | None:
        if not (event.state & self._CTRL_MASK):
            return None
        # Ctrl+Shift+Z is redo, not undo.
        if event.state & self._SHIFT_MASK:
            return None
        if self._undo_key_held:
            return "break"
        self._undo_key_held = True
        return self._on_undo()

    def _on_undo_keyrelease(self, event) -> str | None:
        self._undo_key_held = False
        return None

    def _on_redo_keypress(self, event) -> str | None:
        if not (event.state & self._CTRL_MASK):
            return None
        if self._redo_key_held:
            return "break"
        self._redo_key_held = True
        return self._on_redo()

    def _on_redo_keyrelease(self, event) -> str | None:
        self._redo_key_held = False
        return None

    def _on_any_keyrelease(self, event) -> str | None:
        # Non-Latin layout fallback — clear the held flag by hardware
        # keycode when the z/y KeyRelease binding doesn't match.
        kc = getattr(event, "keycode", 0)
        if kc == 90:  # Z
            self._undo_key_held = False
            self._redo_key_held = False
        elif kc == 89:  # Y
            self._redo_key_held = False
        return None

    # ------------------------------------------------------------------
    # Copy / Paste fallbacks
    # ------------------------------------------------------------------
    def _on_copy_shortcut(self, _event=None) -> str | None:
        # Let Entry / Text widgets handle their native Ctrl+C. Our
        # fallback only fires when focus isn't on an editable field.
        if isinstance(self.focus_get(), (tk.Entry, tk.Text)):
            return None
        self._on_menu_copy()
        return "break"

    def _on_paste_shortcut(self, _event=None) -> str | None:
        if isinstance(self.focus_get(), (tk.Entry, tk.Text)):
            return None
        self._on_menu_paste()
        return "break"

    def _on_cut_shortcut(self, _event=None) -> str | None:
        if isinstance(self.focus_get(), (tk.Entry, tk.Text)):
            return None
        self._on_menu_cut()
        return "break"

    def _on_select_all_shortcut(self, _event=None) -> str | None:
        if isinstance(self.focus_get(), (tk.Entry, tk.Text)):
            return None
        self._on_menu_select_all()
        return "break"

    def _on_docs_shortcut(self, _event=None) -> str | None:
        self._on_widget_docs()
        return "break"
