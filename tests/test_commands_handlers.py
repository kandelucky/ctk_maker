import pytest

from app.core.commands import (
    BindHandlerCommand,
    ReorderHandlerCommand,
    UnbindHandlerCommand,
)
from app.core.project import Project
from app.core.widget_node import WidgetNode


@pytest.fixture
def project_with_button():
    project = Project()
    button = WidgetNode("CTkButton")
    project.add_widget(button)
    return project, button


def _record_events(project):
    events = []

    def listener(*args):
        events.append(args)

    project.event_bus.subscribe("widget_handler_changed", listener)
    return events


# ---- BindHandlerCommand --------------------------------------------------

def test_bind_handler_redo_appends_method(project_with_button):
    project, button = project_with_button
    cmd = BindHandlerCommand(button.id, "command", "on_click")

    cmd.redo(project)

    assert button.handlers == {"command": ["on_click"]}


def test_bind_handler_undo_clears_event(project_with_button):
    project, button = project_with_button
    cmd = BindHandlerCommand(button.id, "command", "on_click")
    cmd.redo(project)

    cmd.undo(project)

    assert button.handlers == {}


def test_bind_handler_publishes_event(project_with_button):
    project, button = project_with_button
    events = _record_events(project)
    cmd = BindHandlerCommand(button.id, "command", "on_click")

    cmd.redo(project)

    assert (button.id, "command", "on_click") in events


def test_bind_handler_multi_method_appends_in_order(project_with_button):
    project, button = project_with_button
    BindHandlerCommand(button.id, "command", "first").redo(project)
    BindHandlerCommand(button.id, "command", "second").redo(project)

    assert button.handlers == {"command": ["first", "second"]}


def test_bind_handler_undo_pops_only_its_own_row(project_with_button):
    project, button = project_with_button
    first = BindHandlerCommand(button.id, "command", "alpha")
    second = BindHandlerCommand(button.id, "command", "beta")
    first.redo(project)
    second.redo(project)

    second.undo(project)

    assert button.handlers == {"command": ["alpha"]}

    first.undo(project)

    assert button.handlers == {}


def test_bind_handler_unknown_widget_id_is_noop(project_with_button):
    project, _button = project_with_button
    cmd = BindHandlerCommand("does-not-exist", "command", "on_click")

    cmd.redo(project)
    cmd.undo(project)


# ---- UnbindHandlerCommand ------------------------------------------------

def test_unbind_handler_redo_removes_method(project_with_button):
    project, button = project_with_button
    BindHandlerCommand(button.id, "command", "on_click").redo(project)
    cmd = UnbindHandlerCommand(button.id, "command", "on_click", index=0)

    cmd.redo(project)

    assert button.handlers == {}


def test_unbind_handler_undo_restores_method_at_original_index(project_with_button):
    project, button = project_with_button
    BindHandlerCommand(button.id, "command", "alpha").redo(project)
    BindHandlerCommand(button.id, "command", "beta").redo(project)
    BindHandlerCommand(button.id, "command", "gamma").redo(project)
    cmd = UnbindHandlerCommand(button.id, "command", "beta", index=1)
    cmd.redo(project)
    assert button.handlers == {"command": ["alpha", "gamma"]}

    cmd.undo(project)

    assert button.handlers == {"command": ["alpha", "beta", "gamma"]}


# ---- ReorderHandlerCommand -----------------------------------------------

def test_reorder_handler_moves_method(project_with_button):
    project, button = project_with_button
    for name in ("a", "b", "c"):
        BindHandlerCommand(button.id, "command", name).redo(project)
    cmd = ReorderHandlerCommand(
        button.id, "command", from_index=0, to_index=2,
    )

    cmd.redo(project)

    assert button.handlers == {"command": ["b", "c", "a"]}


def test_reorder_handler_undo_restores_order(project_with_button):
    project, button = project_with_button
    for name in ("a", "b", "c"):
        BindHandlerCommand(button.id, "command", name).redo(project)
    cmd = ReorderHandlerCommand(
        button.id, "command", from_index=0, to_index=2,
    )
    cmd.redo(project)

    cmd.undo(project)

    assert button.handlers == {"command": ["a", "b", "c"]}


def test_reorder_handler_noop_when_indices_equal(project_with_button):
    project, button = project_with_button
    for name in ("a", "b"):
        BindHandlerCommand(button.id, "command", name).redo(project)
    cmd = ReorderHandlerCommand(
        button.id, "command", from_index=1, to_index=1,
    )

    cmd.redo(project)

    assert button.handlers == {"command": ["a", "b"]}
