"""Shared dropdown menu for binding event handlers.

The Properties panel ``[+]`` button and the Workspace right-click event
submenu both need the same menu of "what can I wire to this event?" —
populating it from one place keeps the two surfaces in sync. The only
bindable target is a **CTkScript** component's public method
(``script_call``); picking one pushes ``BindHandlerCommand`` directly.
No auto-stub creation, no auto-rename — the binding lives in the
``.ctkproj``, never in the user's script (see
docs/plans/script_optimization.md).
"""
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from app.core.project import Project


def _add_disabled_hint(menu: tk.Menu, label: str) -> None:
    """Dimmed, inert hint instead of ``state="disabled"`` — Windows
    native menus draw disabled entries as etched-ghost text on the dark
    theme ("ჯადო"); a grey foreground + no-op command reads cleanly."""
    menu.add_command(
        label=label, command=lambda: None,
        foreground="#777777", activeforeground="#777777",
        activebackground="#2d2d30",
    )


def populate_event_bind_menu(
    menu: tk.Menu,
    project: "Project",
    widget_id: str,
    event_key: str,
    on_commit: Callable[[], None] | None = None,
) -> None:
    """Fill ``menu`` with bind options for one event on one widget — a
    **Scripts** group listing every CTkScript component attached to the
    widget (its own scope) or the window, each with its public methods.
    Picking one binds a ``script_call`` in one shot (used by the
    workspace right-click). A dimmed hint shows when nothing is bindable.
    """
    from app.widgets.event_registry import event_by_key
    node = project.get_widget(widget_id)
    if node is None:
        _add_disabled_hint(menu, "No widget selected")
        return
    if event_by_key(node.widget_type, event_key) is None:
        _add_disabled_hint(menu, "Unknown event")
        return
    document = project.find_document_for_widget(widget_id)
    if document is None:
        _add_disabled_hint(menu, "Open the project to bind handlers")
        return
    from app.io.scripts import iter_script_call_targets
    from app.ui.properties_panel.constants import menu_style
    style = menu_style()
    # CTkScript components — widget-scope first, then window-scope
    # (shared enumeration with the panel picker).
    comp_targets = iter_script_call_targets(node, document)
    if not comp_targets:
        _add_disabled_hint(
            menu, "No actions yet — attach a script (＋ in the Scripts group)",
        )
        return
    scripts_menu = tk.Menu(menu, tearoff=0, **style)
    for script_rel, cls, scope in comp_targets:
        label_scope = "this widget" if scope == "widget" else "window"
        sub = tk.Menu(scripts_menu, tearoff=0, **style)
        methods = _component_methods(project, script_rel, cls)
        if methods:
            for method_name in methods:
                sub.add_command(
                    label=method_name,
                    command=lambda c=cls, m=method_name, s=scope:
                    _bind_script_call(
                        project, widget_id, event_key, c, m, s, on_commit,
                    ),
                )
        else:
            _add_disabled_hint(sub, "No public methods")
        scripts_menu.add_cascade(label=f"{cls}  ({label_scope})", menu=sub)
    menu.add_cascade(label="Scripts", menu=scripts_menu)


def _component_methods(
    project: "Project", script_rel: str, cls: str,
) -> list[str]:
    """Public methods of an attached CTkScript class (minus the
    ``on_start``/``on_close`` lifecycle hooks), read from its stored file
    path. Empty when the project is unsaved or the file is gone. Uses the
    path from ``attached_components`` — no whole-folder rescan, so two
    files sharing a class name can't be confused."""
    from pathlib import Path
    from app.core.script_paths import user_scripts_dir
    from app.io.scripts import parse_handler_methods
    scripts_dir = user_scripts_dir(getattr(project, "path", None))
    if scripts_dir is None or not script_rel or not cls:
        return []
    return [
        m for m in parse_handler_methods(Path(scripts_dir) / script_rel, cls)
        if m not in ("on_start", "on_close")
    ]


def _bind_script_call(
    project: "Project", widget_id: str, event_key: str,
    class_name: str, method_name: str, scope: str,
    on_commit: Callable[[], None] | None = None,
) -> None:
    """Bind a ``script_call`` entry (class + method + scope already
    chosen) — the one-shot workspace path, vs the panel's
    pick-target-then-method flow. ``scope`` records which attachment was
    picked so export resolves the right instance."""
    from app.core.commands import BindHandlerCommand
    entry = {
        "kind": "script_call", "class": class_name,
        "method": method_name, "scope": scope,
    }
    cmd = BindHandlerCommand(widget_id, event_key, entry)
    cmd.redo(project)
    project.history.push(cmd)
    if on_commit is not None:
        on_commit()


def show_event_bind_menu_at_cursor(
    parent: tk.Widget,
    project: "Project",
    widget_id: str,
    event_key: str,
    on_commit: Callable[[], None] | None = None,
) -> None:
    """Pop the dropdown at the current cursor position. Use when a
    parent menu's command can't pass an event (the parent menu has
    already closed by the time the callback runs) — ``parent`` only
    needs to be a Tk widget that owns the screen the menu pops on.

    ``on_commit`` fires after a successful bind so callers (e.g.
    pending-row pickers) can clean up their transient UI state.
    """
    from app.ui.properties_panel.constants import menu_style
    menu = tk.Menu(parent, tearoff=0, **menu_style())
    populate_event_bind_menu(
        menu, project, widget_id, event_key, on_commit=on_commit,
    )
    try:
        menu.tk_popup(parent.winfo_pointerx(), parent.winfo_pointery())
    finally:
        menu.grab_release()


def populate_target_only_menu(
    menu: tk.Menu,
    project: "Project",
    widget_id: str,
    event_key: str,
    on_commit: Callable[[], None] | None = None,
) -> None:
    """Flat target picker — lists the CTkScript components attached to
    the widget (its own scope) and the window. Picking one commits a
    ``script_call`` with the class + scope set and the method left empty,
    so the user fills the Function row separately ("first pick target,
    then pick function" — the Unity Inspector flow).
    """
    node = project.get_widget(widget_id)
    if node is None:
        _add_disabled_hint(menu, "No widget selected")
        return
    document = project.find_document_for_widget(widget_id)
    if document is None:
        _add_disabled_hint(menu, "Open the project to bind handlers")
        return
    from app.io.scripts import iter_script_call_targets
    comp_targets = iter_script_call_targets(node, document)
    if not comp_targets:
        _add_disabled_hint(
            menu, "No actions yet — attach a script (＋ in the Scripts group)",
        )
        return
    for _script_rel, cls, scope in comp_targets:
        label_scope = "this widget" if scope == "widget" else "window"
        menu.add_command(
            label=f"{cls}  ({label_scope})",
            command=lambda c=cls, s=scope:
            _commit_target_script_component(
                project, widget_id, event_key, c, s, on_commit,
            ),
        )


def _commit_target_script_component(
    project: "Project", widget_id: str, event_key: str,
    class_name: str, scope: str,
    on_commit: Callable[[], None] | None,
) -> None:
    """Append an empty ``script_call`` entry — method left blank for the
    Function row picker to fill from the class's public methods. ``scope``
    (``"widget"`` / ``"window"``) records which attachment the user
    picked, so export resolves the right instance even when the same
    class is attached to both.
    """
    from app.core.commands import BindHandlerCommand
    entry = {
        "kind": "script_call", "class": class_name,
        "method": "", "scope": scope,
    }
    cmd = BindHandlerCommand(widget_id, event_key, entry)
    cmd.redo(project)
    project.history.push(cmd)
    if on_commit is not None:
        on_commit()


def show_target_only_menu_at_cursor(
    parent: tk.Widget,
    project: "Project",
    widget_id: str,
    event_key: str,
    on_commit: Callable[[], None] | None = None,
) -> None:
    """Pop the flat target picker at the cursor."""
    from app.ui.properties_panel.constants import menu_style
    menu = tk.Menu(parent, tearoff=0, **menu_style())
    populate_target_only_menu(
        menu, project, widget_id, event_key, on_commit=on_commit,
    )
    try:
        menu.tk_popup(parent.winfo_pointerx(), parent.winfo_pointery())
    finally:
        menu.grab_release()
