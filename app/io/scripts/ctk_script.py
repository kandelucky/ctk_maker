"""``CTkScript`` — base class for CTkMaker behavior scripts.

The Unity ``MonoBehaviour`` model for CTkMaker. You subclass it in your
own script (in the project's ``scripts/`` folder) and attach it to an
object in the builder. CTkMaker injects the object you attached it to —
and **only** that object:

    - attached to a **widget** → ``self.widget``. A widget script knows
      only its own widget; it has no ``self.window`` at all (strict
      scope), so it stays self-contained and reusable on any widget.
    - attached to a **window** → ``self.window``, which reaches every
      widget on it by builder name: ``self.window.my_button``. Use this
      for logic that coordinates several widgets (form logic).

You choose what to attach to; that alone decides what the script sees.

    class ClickCounter(CTkScript):        # attach to a button
        def on_start(self):
            self.count = 0
        def bump(self):                    # bound to the button's click
            self.count += 1
            self.widget.configure(text=str(self.count))

    class LoginForm(CTkScript):            # attach to the window
        def submit(self):                  # bound to a button's click
            name = self.window.username.get()
            self.window.status.configure(text=f"Hi {name}")

Add public methods and bind events to them in the builder; CTkMaker
never edits this file.

This module is the single source of truth for the class. The exporter
inlines its source into the build so exported apps stay self-contained
(no ``pip install`` needed) — hence only runtime-free stdlib imports
here; the ``customtkinter`` names live under ``TYPE_CHECKING`` and are
never imported when the app runs — they only feed the editor's
autocomplete and type checker.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import customtkinter as ctk


class CTkScript:
    """Base class for an attached behavior script. Subclass it, override
    the lifecycle hooks you need, and add public methods to bind to
    events. See the module docstring for the widget-vs-window scope.
    """

    # Type-only declarations so ``self.widget`` / ``self.window``
    # autocomplete in the editor. At runtime only the one matching the
    # attach target exists (strict scope) — the other raises
    # AttributeError, by design.
    widget: ctk.CTkBaseClass
    window: ctk.CTk | ctk.CTkToplevel

    def __init__(self, *, widget=None, window=None):
        # CTkMaker injects the matching context after building the
        # instance; the constructor mirrors that so the class stays
        # usable standalone (tests, manual instantiation). Only the
        # context for where it's attached is set — a widget script has
        # no ``window`` attribute at all, a window script has no
        # ``widget`` (strict scope).
        if widget is not None:
            self.widget = widget
        if window is not None:
            self.window = window

    # -- Lifecycle hooks — override what you need; defaults do nothing --
    def on_start(self):
        """Runs once after the object is built and its widgets exist.
        Use it for initial state, focus, populating fields, timers."""

    def on_close(self):
        """Runs when the window is closing — for **any** attached script
        (widget- or window-scope). A cleanup notification: stop timers,
        save state, release resources. The window closes either way; you
        don't control that here (don't call ``destroy()`` yourself)."""
