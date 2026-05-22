"""CTkScript component resolution — shared enumerator/resolver
(app/io/scripts/components.py) and the exporter's scope-aware
``_resolve_component_var``. Pure model-level (no Tk). See
docs/plans/script_optimization.md.
"""
from __future__ import annotations

from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.io.code_exporter import _resolve_component_var
from app.io.scripts import iter_script_call_targets, resolve_script_component


def _comp(script: str, cls: str) -> dict:
    return {"script": script, "class": cls}


def _widget(project: Project) -> WidgetNode:
    node = WidgetNode("CTkButton")
    project.active_document.root_widgets.append(node)
    return node


def test_iter_targets_widget_then_window():
    project = Project()
    doc = project.active_document
    node = _widget(project)
    node.attached_components = [_comp("a.py", "A")]
    doc.attached_components = [_comp("b.py", "B")]
    assert iter_script_call_targets(node, doc) == [
        ("a.py", "A", "widget"),
        ("b.py", "B", "window"),
    ]


def test_resolve_same_class_on_both_honors_scope():
    project = Project()
    doc = project.active_document
    node = _widget(project)
    node.attached_components = [_comp("w.py", "Dup")]
    doc.attached_components = [_comp("win.py", "Dup")]
    assert resolve_script_component(node, doc, "Dup", "widget")["script"] == "w.py"
    assert resolve_script_component(node, doc, "Dup", "window")["script"] == "win.py"
    # Legacy entry (no scope) keeps the widget-first fallback.
    assert resolve_script_component(node, doc, "Dup", None)["script"] == "w.py"


def test_resolve_window_scope_misses_widget_only():
    project = Project()
    doc = project.active_document
    node = _widget(project)
    node.attached_components = [_comp("w.py", "X")]
    assert resolve_script_component(node, doc, "X", "window") is None
    assert resolve_script_component(node, doc, "X", "widget")["script"] == "w.py"


def test_exporter_resolve_var_scope():
    records = [
        {"var": "_script_0", "class": "Dup", "scope": "window", "owner_id": None},
        {"var": "_script_1", "class": "Dup", "scope": "widget", "owner_id": "w1"},
    ]
    assert _resolve_component_var(records, "w1", "Dup", "widget") == "_script_1"
    assert _resolve_component_var(records, "w1", "Dup", "window") == "_script_0"
    # Legacy (no scope) → owner first.
    assert _resolve_component_var(records, "w1", "Dup", None) == "_script_1"


def test_exporter_resolve_var_window_scope_no_window_record():
    records = [
        {"var": "_script_1", "class": "Dup", "scope": "widget", "owner_id": "w1"},
    ]
    assert _resolve_component_var(records, "w1", "Dup", "window") is None
