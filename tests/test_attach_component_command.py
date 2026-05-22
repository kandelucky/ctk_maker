"""Undo/redo for attaching/detaching CTkScript components to a widget
or the window. Pure model-level (no Tk). See
docs/plans/script_optimization.md.
"""
from __future__ import annotations

from app.core.commands import AttachComponentCommand, DetachComponentCommand
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
