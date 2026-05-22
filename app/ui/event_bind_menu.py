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
    """Fill ``menu`` with bind options for one event on one widget.

    Groups appear in this order, when non-empty:

    * **Scripts** — CTkScript components attached to the widget (its
      own scope) or the window, each with its public methods; picking
      one binds a ``script_call`` (the primary, current model).
    * **Page Script** / **Object References** — legacy behavior-file
      methods + Object Reference actions, kept until those mechanisms
      are retired (see docs/plans/script_optimization.md).

    When nothing is bindable, a single dimmed hint points the user at
    the Scripts group.
    """
    from app.widgets.action_registry import actions_for
    from app.widgets.event_registry import event_by_key
    node = project.get_widget(widget_id)
    if node is None:
        _add_disabled_hint(menu, "No widget selected")
        return
    event_entry = event_by_key(node.widget_type, event_key)
    if event_entry is None:
        _add_disabled_hint(menu, "Unknown event")
        return
    document = project.find_document_for_widget(widget_id)
    if document is None:
        _add_disabled_hint(menu, "Open the project to bind handlers")
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
    # CTkScript components — primary path. Widget-scope components
    # first, then window-scope.
    comp_targets: list[tuple[str, str]] = []
    for comp in (getattr(node, "attached_components", None) or []):
        cls = comp.get("class", "")
        if cls:
            comp_targets.append((cls, "this widget"))
    for comp in (getattr(document, "attached_components", None) or []):
        cls = comp.get("class", "")
        if cls:
            comp_targets.append((cls, "window"))
    if comp_targets:
        scripts_menu = tk.Menu(menu, tearoff=0, **style)
        for cls, scope in comp_targets:
            sub = tk.Menu(scripts_menu, tearoff=0, **style)
            methods = _component_methods(project, cls)
            if methods:
                for method_name in methods:
                    sub.add_command(
                        label=method_name,
                        command=lambda c=cls, m=method_name:
                        _bind_script_call(
                            project, widget_id, event_key, c, m, on_commit,
                        ),
                    )
            else:
                _add_disabled_hint(sub, "No public methods")
            scripts_menu.add_cascade(label=f"{cls}  ({scope})", menu=sub)
        menu.add_cascade(label="Scripts", menu=scripts_menu)
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
    if not comp_targets and not page_methods and not obj_ref_actions:
        _add_disabled_hint(
            menu, "No actions yet — attach a script (＋ in the Scripts group)",
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


def _component_methods(project: "Project", cls: str) -> list[str]:
    """Public methods of an attached CTkScript class (minus the
    ``on_start``/``on_close`` lifecycle hooks). Empty when the project
    is unsaved or the class can't be located under ``scripts/``."""
    from pathlib import Path
    from app.core.script_paths import user_scripts_dir
    from app.io.scripts import find_attachable_scripts, parse_handler_methods
    scripts_dir = user_scripts_dir(getattr(project, "path", None))
    if scripts_dir is None or not cls:
        return []
    rel = next(
        (p for (p, c) in find_attachable_scripts(scripts_dir) if c == cls),
        None,
    )
    if not rel:
        return []
    return [
        m for m in parse_handler_methods(Path(scripts_dir) / rel, cls)
        if m not in ("on_start", "on_close")
    ]


def _bind_script_call(
    project: "Project", widget_id: str, event_key: str,
    class_name: str, method_name: str,
    on_commit: Callable[[], None] | None = None,
) -> None:
    """Bind a ``script_call`` entry (class + method already chosen) —
    the one-shot workspace path, vs the panel's pick-target-then-method
    flow. Resolved at export against the object's attached_components."""
    from app.core.commands import BindHandlerCommand
    entry = {
        "kind": "script_call", "class": class_name, "method": method_name,
    }
    cmd = BindHandlerCommand(widget_id, event_key, entry)
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

    # CTkScript model — components attached to this widget (its own
    # scope) and to the window (window scope). Picking one commits a
    # ``script_call`` with the class set; the Function row then lists
    # that class's public methods.
    comp_targets: list[tuple[str, str]] = []
    for comp in (getattr(node, "attached_components", None) or []):
        cls = comp.get("class", "")
        if cls:
            comp_targets.append((cls, "this widget"))
    for comp in (getattr(document, "attached_components", None) or []):
        cls = comp.get("class", "")
        if cls:
            comp_targets.append((cls, "window"))
    if comp_targets:
        menu.add_separator()
        for cls, scope in comp_targets:
            menu.add_command(
                label=f"{cls}  ({scope})",
                command=lambda c=cls: _commit_target_script_component(
                    project, widget_id, event_key, c, on_commit,
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


def _commit_target_script_component(
    project: "Project", widget_id: str, event_key: str,
    class_name: str,
    on_commit: Callable[[], None] | None,
) -> None:
    """Append an empty ``script_call`` entry — method left blank for the
    Function row picker to fill from the class's public methods. The
    component is resolved at export time against the object's / window's
    attached components.
    """
    from app.core.commands import BindHandlerCommand
    entry = {"kind": "script_call", "class": class_name, "method": ""}
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
