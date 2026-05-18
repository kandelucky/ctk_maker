"""Shared dropdown menu for binding event handlers.

The Properties panel ``[+]`` button and the Workspace right-click
event submenu both need the same menu of "what can I wire to this
event?" — populating it from one place keeps the two surfaces in
sync. Picking entries here pushes ``BindHandlerCommand`` directly;
no auto-stub creation, no auto-rename, no auto-delete (file is the
user's source of truth — see ``docs/plans/event_binding.md``).
"""
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from app.core.project import Project


def populate_event_bind_menu(
    menu: tk.Menu,
    project: "Project",
    widget_id: str,
    event_key: str,
    on_commit: Callable[[], None] | None = None,
) -> None:
    """Fill ``menu`` with bind options for one event on one widget.

    Two groups appear (in this order, when non-empty):

    * **Page Script** — public methods on the per-window behavior
      class whose signature matches the event's wiring kind
      (``parse_handler_methods_compatible``).
    * **Object References** — every Object Reference on the active
      document whose target widget type has at least one action in
      ``WIDGET_ACTION_METHODS``, with the allowlisted actions
      nested under it.

    When both groups are empty, a single disabled hint entry is
    added so the user knows where to add methods.
    """
    from app.widgets.action_registry import actions_for
    from app.widgets.event_registry import event_by_key
    node = project.get_widget(widget_id)
    if node is None:
        menu.add_command(label="No widget selected", state="disabled")
        return
    event_entry = event_by_key(node.widget_type, event_key)
    if event_entry is None:
        menu.add_command(label="Unknown event", state="disabled")
        return
    document = project.find_document_for_widget(widget_id)
    if document is None:
        menu.add_command(
            label="Open the project to bind handlers",
            state="disabled",
        )
        return
    page_methods = _existing_page_methods(
        project, document, event_entry.wiring_kind,
    )
    obj_ref_actions: list[tuple] = []
    for ref in document.local_object_references:
        if not ref.target_id:
            continue
        target = project.get_widget(ref.target_id)
        if target is None:
            continue
        allowed = actions_for(target.widget_type)
        if allowed:
            obj_ref_actions.append((ref, allowed))
    from app.ui.properties_panel.constants import menu_style
    style = menu_style()
    if page_methods:
        page_menu = tk.Menu(menu, tearoff=0, **style)
        for method_name in page_methods:
            page_menu.add_command(
                label=method_name,
                command=lambda m=method_name:
                _bind_page_method(
                    project, widget_id, event_key, m, on_commit,
                ),
            )
        menu.add_cascade(label="Page Script", menu=page_menu)
    if obj_ref_actions:
        refs_menu = tk.Menu(menu, tearoff=0, **style)
        for ref_entry, actions in obj_ref_actions:
            sub = tk.Menu(refs_menu, tearoff=0, **style)
            for action in actions:
                sub.add_command(
                    label=action.label,
                    command=lambda r=ref_entry, a=action:
                    _bind_ref_call(
                        project, widget_id, event_key, r, a, on_commit,
                    ),
                )
            refs_menu.add_cascade(label=ref_entry.name, menu=sub)
        menu.add_cascade(label="Object References", menu=refs_menu)
    if not page_methods and not obj_ref_actions:
        menu.add_command(
            label="No public methods. Open behavior file (F7)…",
            state="disabled",
        )


def _existing_page_methods(
    project: "Project", document, wiring_kind: str,
) -> list[str]:
    """Compatible public methods on the document's behavior class.
    Empty when the project is unsaved or the behavior file doesn't
    exist yet — picker shows the empty-state hint in that case.
    """
    if not getattr(project, "path", None):
        return []
    from app.core.script_paths import (
        behavior_class_name, behavior_file_path,
    )
    from app.io.scripts import parse_handler_methods_compatible
    file_path = behavior_file_path(project.path, document)
    if file_path is None or not file_path.exists():
        return []
    return parse_handler_methods_compatible(
        file_path, behavior_class_name(document), wiring_kind,
    )


def _bind_page_method(
    project: "Project", widget_id: str, event_key: str,
    method_name: str,
    on_commit: Callable[[], None] | None = None,
) -> None:
    from app.core.commands import BindHandlerCommand
    cmd = BindHandlerCommand(widget_id, event_key, method_name)
    cmd.redo(project)
    project.history.push(cmd)
    if on_commit is not None:
        on_commit()


def _bind_ref_call(
    project: "Project", widget_id: str, event_key: str,
    ref_entry, action,
    on_commit: Callable[[], None] | None = None,
) -> None:
    from app.core.commands import BindHandlerCommand
    args = [
        {
            "name": p.name,
            "type": p.type,
            "value": p.default,
            "kwarg": p.kwarg,
        }
        for p in action.params
    ]
    entry = {
        "kind": "ref_call",
        "ref": ref_entry.name,
        "method": action.name,
        "args": args,
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
    """Flat target picker — lists Page Script, Object References,
    and library scripts attached to the document. Picking commits
    the entry to ``handlers`` with the target set and method/args
    left empty so the user fills the Function row separately.

    Use when the workflow is "first pick target, then pick
    function" (Unity Inspector behaviour); the cascading
    ``populate_event_bind_menu`` is reserved for one-shot quick-add
    surfaces like the workspace right-click context menu.
    """
    from app.widgets.action_registry import actions_for
    node = project.get_widget(widget_id)
    if node is None:
        menu.add_command(label="No widget selected", state="disabled")
        return
    document = project.find_document_for_widget(widget_id)
    if document is None:
        menu.add_command(
            label="Open the project to bind handlers",
            state="disabled",
        )
        return
    menu.add_command(
        label="Page Script",
        command=lambda: _commit_target_page(
            project, widget_id, event_key, on_commit,
        ),
    )
    refs_with_actions: list = []
    for ref in document.local_object_references:
        if not ref.target_id:
            continue
        target = project.get_widget(ref.target_id)
        if target is None:
            continue
        if actions_for(target.widget_type):
            refs_with_actions.append((ref, target))
    if refs_with_actions:
        menu.add_separator()
        for ref, target in refs_with_actions:
            menu.add_command(
                label=f"{ref.name} ({target.widget_type})",
                command=lambda r=ref: _commit_target_ref(
                    project, widget_id, event_key, r.name, on_commit,
                ),
            )
    attached = getattr(document, "attached_scripts", []) or []
    if attached:
        menu.add_separator()
        for path in attached:
            menu.add_command(
                label=path,
                command=lambda p=path: _commit_target_library(
                    project, widget_id, event_key, p, on_commit,
                ),
            )


def _commit_target_page(
    project: "Project", widget_id: str, event_key: str,
    on_commit: Callable[[], None] | None,
) -> None:
    """Append an empty page-method entry — the Function row's picker
    completes the binding. Mirrors ``_bind_page_method`` but the
    method name is the empty string so the entry stays in the
    "target picked, function pending" state until the user finishes.
    """
    from app.core.commands import BindHandlerCommand
    cmd = BindHandlerCommand(widget_id, event_key, "")
    cmd.redo(project)
    project.history.push(cmd)
    if on_commit is not None:
        on_commit()


def _commit_target_ref(
    project: "Project", widget_id: str, event_key: str,
    ref_name: str,
    on_commit: Callable[[], None] | None,
) -> None:
    """Append an empty ref_call entry — method/args left blank for
    the Function row picker to fill.
    """
    from app.core.commands import BindHandlerCommand
    entry = {
        "kind": "ref_call",
        "ref": ref_name,
        "method": "",
        "args": [],
    }
    cmd = BindHandlerCommand(widget_id, event_key, entry)
    cmd.redo(project)
    project.history.push(cmd)
    if on_commit is not None:
        on_commit()


def _commit_target_library(
    project: "Project", widget_id: str, event_key: str,
    script_path: str,
    on_commit: Callable[[], None] | None,
) -> None:
    """Append an empty library_call entry — method/args left blank
    for the Function row picker to fill. ``script_path`` is the
    page-folder-relative path stored in
    ``Document.attached_scripts``.
    """
    from app.core.commands import BindHandlerCommand
    entry = {
        "kind": "library_call",
        "script": script_path,
        "method": "",
        "args": [],
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
