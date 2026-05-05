"""Type-checking stub for the MainWindow host that the menu / shortcuts
mixins assume.

``MenuMixin`` and ``ShortcutsMixin`` access ``self.project``,
``self.workspace``, ``self._appearance_var``, etc. — attributes that
live on ``MainWindow`` (the class they're mixed into). Pyright analyses
each mixin in isolation and has no way to discover that coupling, so it
flagged hundreds of false-positive ``reportAttributeAccessIssue``
errors.

This module declares a TYPE_CHECKING-only base class that:

* inherits from ``ctk.CTk`` so Tk methods (``bind``, ``focus_get``,
  ``after``, ``config``, …) resolve normally;
* declares the MainWindow-specific public attributes and Tk vars that
  the mixins reach for;
* declares the menubar widgets that one mixin sets up and the other
  reads;
* falls through unknown ``self.X`` lookups to ``Any`` via ``__getattr__``
  so the long tail of ``_on_*`` callbacks doesn't have to be enumerated.

At runtime, ``_MainWindowHost`` resolves to plain ``object`` so the MRO
is unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tkinter as tk

    import customtkinter as ctk

    from app.core.project import Project

    class _MainWindowHost(ctk.CTk):
        # Top-level panels assembled in MainWindow.__init__
        project: Project
        workspace: Any
        palette: Any
        toolbar: Any
        properties: Any
        object_tree: Any
        docked_project: Any
        paned: Any
        right_pane: Any

        # Tk Variables backing menubar checkbutton state
        _appearance_var: tk.StringVar
        _history_var: tk.BooleanVar
        _project_var: tk.BooleanVar
        _variables_var: tk.BooleanVar
        _object_tree_var: tk.BooleanVar

        # Modifier / keyboard state used by ShortcutsMixin
        _CTRL_MASK: int
        _SHIFT_MASK: int
        _redo_key_held: bool
        _undo_key_held: bool

        # Menubar widgets — created by MenuMixin._build_menubar, read
        # by both mixins (and refresh helpers).
        _edit_menu: tk.Menu
        _form_menu: tk.Menu
        _windows_menu: tk.Menu
        _recent_menu: tk.Menu
        _align_menu: tk.Menu
        _align_menu_modes: list[str]
        _menu_icons: list[Any]

        # Long tail (`_on_new`, `_on_save`, `_on_widget_docs`, etc.) is
        # left to ``__getattr__`` rather than enumerated — those
        # callbacks rotate often and listing them all would create a
        # second source of truth that drifts.
        def __getattr__(self, name: str) -> Any: ...

else:
    _MainWindowHost = object
