"""Undo/redo for attaching/detaching CTkScript components to a widget
or the window. Pure model-level (no Tk). See
docs/plans/script_optimization.md.
"""
from __future__ import annotations

from app.core.commands import (
    AttachComponentCommand,
    BindVariableCommand,
    DetachComponentCommand,
    SetFieldSourceCommand,
)
from app.core.project import WINDOW_ID, Project
from app.core.widget_node import WidgetNode


def _comp(script: str, cls: str) -> dict:
    return {"script": script, "class": cls}


def test_attach_to_window_undo_redo():
    project = Project()
    cmd = AttachComponentCommand(WINDOW_ID, _comp("x.py", "X"))
    cmd.redo(project)
    assert project.active_document.attached_components == [_comp("x.py", "X")]
    cmd.undo(project)
    assert project.active_document.attached_components == []
    cmd.redo(project)
    assert project.active_document.attached_components == [_comp("x.py", "X")]


def test_attach_to_widget_undo():
    project = Project()
    node = WidgetNode("CTkButton")
    project.active_document.root_widgets.append(node)
    cmd = AttachComponentCommand(node.id, _comp("c.py", "Counter"))
    cmd.redo(project)
    assert node.attached_components == [_comp("c.py", "Counter")]
    cmd.undo(project)
    assert node.attached_components == []


def test_detach_undo_restores_at_index():
    project = Project()
    doc = project.active_document
    doc.attached_components = [
        _comp("a.py", "A"), _comp("b.py", "B"), _comp("c.py", "C"),
    ]
    cmd = DetachComponentCommand(WINDOW_ID, "B")
    cmd.redo(project)
    assert [c["class"] for c in doc.attached_components] == ["A", "C"]
    cmd.undo(project)
    assert [c["class"] for c in doc.attached_components] == ["A", "B", "C"]


def test_detach_missing_class_is_noop():
    project = Project()
    project.active_document.attached_components = [_comp("a.py", "A")]
    cmd = DetachComponentCommand(WINDOW_ID, "Nope")
    cmd.redo(project)
    assert project.active_document.attached_components == [_comp("a.py", "A")]
    cmd.undo(project)  # nothing recorded → no-op
    assert project.active_document.attached_components == [_comp("a.py", "A")]


# -- BindVariableCommand (Phase 3b — script variable binding) ----------

def test_bind_variable_sets_and_undoes_to_unbound():
    project = Project()
    doc = project.active_document
    doc.attached_components = [_comp("f.py", "Form")]
    cmd = BindVariableCommand(WINDOW_ID, "Form", "user", "uuid-1")
    cmd.redo(project)
    assert doc.attached_components[0]["var_bindings"] == {"user": "uuid-1"}
    cmd.undo(project)
    # Was unbound before → key removed, empty map dropped.
    assert "var_bindings" not in doc.attached_components[0]
    cmd.redo(project)
    assert doc.attached_components[0]["var_bindings"] == {"user": "uuid-1"}


def test_bind_variable_rebind_restores_previous():
    project = Project()
    doc = project.active_document
    doc.attached_components = [
        {"script": "f.py", "class": "Form", "var_bindings": {"user": "old"}},
    ]
    cmd = BindVariableCommand(WINDOW_ID, "Form", "user", "new")
    cmd.redo(project)
    assert doc.attached_components[0]["var_bindings"] == {"user": "new"}
    cmd.undo(project)
    assert doc.attached_components[0]["var_bindings"] == {"user": "old"}


def test_bind_variable_clear_and_undo():
    project = Project()
    doc = project.active_document
    doc.attached_components = [
        {"script": "f.py", "class": "Form",
         "var_bindings": {"user": "u1", "x": "u2"}},
    ]
    cmd = BindVariableCommand(WINDOW_ID, "Form", "user", None)
    cmd.redo(project)
    assert doc.attached_components[0]["var_bindings"] == {"x": "u2"}
    cmd.undo(project)
    assert doc.attached_components[0]["var_bindings"] == {"user": "u1", "x": "u2"}


def test_bind_variable_on_widget():
    project = Project()
    node = WidgetNode("CTkButton")
    node.attached_components = [_comp("c.py", "C")]
    project.active_document.root_widgets.append(node)
    cmd = BindVariableCommand(node.id, "C", "score", "uuid-9")
    cmd.redo(project)
    assert node.attached_components[0]["var_bindings"] == {"score": "uuid-9"}
    cmd.undo(project)
    assert "var_bindings" not in node.attached_components[0]


def test_bind_variable_missing_component_is_noop():
    project = Project()
    project.active_document.attached_components = [_comp("f.py", "Form")]
    cmd = BindVariableCommand(WINDOW_ID, "Nope", "user", "u1")
    cmd.redo(project)
    assert project.active_document.attached_components == [_comp("f.py", "Form")]


# -- SetFieldSourceCommand (inline value ↔ variable, Phase 3b-iv) ------

def test_set_field_inline_value_and_undo():
    project = Project()
    doc = project.active_document
    doc.attached_components = [_comp("f.py", "Form")]
    cmd = SetFieldSourceCommand(WINDOW_ID, "Form", "count", "value", "5")
    cmd.redo(project)
    assert doc.attached_components[0]["field_values"] == {"count": "5"}
    cmd.undo(project)
    assert "field_values" not in doc.attached_components[0]


def test_set_field_var_clears_inline_and_undo_restores():
    project = Project()
    doc = project.active_document
    doc.attached_components = [
        {"script": "f.py", "class": "Form", "field_values": {"count": "5"}},
    ]
    cmd = SetFieldSourceCommand(WINDOW_ID, "Form", "count", "var", "uuid-1")
    cmd.redo(project)
    comp = doc.attached_components[0]
    assert comp["var_bindings"] == {"count": "uuid-1"}
    assert "field_values" not in comp           # inline cleared (single source)
    cmd.undo(project)
    comp = doc.attached_components[0]
    assert comp["field_values"] == {"count": "5"}   # restored
    assert "var_bindings" not in comp


def test_set_field_clear_restores_previous():
    project = Project()
    doc = project.active_document
    doc.attached_components = [
        {"script": "f.py", "class": "Form", "var_bindings": {"count": "u1"}},
    ]
    cmd = SetFieldSourceCommand(WINDOW_ID, "Form", "count", None)
    cmd.redo(project)
    assert "var_bindings" not in doc.attached_components[0]
    cmd.undo(project)
    assert doc.attached_components[0]["var_bindings"] == {"count": "u1"}
