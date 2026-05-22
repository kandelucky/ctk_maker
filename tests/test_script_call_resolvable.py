"""Panel flags an orphaned ``script_call`` — a binding whose CTkScript
was detached after being wired into an event. The resolution rule
mirrors the exporter's ``_resolve_component_var`` (widget scope first,
window scope as fallback). Pure model-level (no Tk). See
docs/plans/script_optimization.md.
"""
from __future__ import annotations

from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.ui.properties_panel.panel_schema import _script_call_resolvable


def _comp(script: str, cls: str) -> dict:
    return {"script": script, "class": cls}


def _widget_in_doc(project: Project) -> WidgetNode:
    node = WidgetNode("CTkButton")
    project.active_document.root_widgets.append(node)
    return node


def test_resolvable_on_widget():
    project = Project()
    node = _widget_in_doc(project)
    node.attached_components = [_comp("counter.py", "Counter")]
    assert _script_call_resolvable(project, node, "Counter") is True


def test_resolvable_via_window_fallback():
    project = Project()
    node = _widget_in_doc(project)
    # Not on the widget, but attached to the window → still reachable.
    project.active_document.attached_components = [_comp("counter.py", "Counter")]
    assert _script_call_resolvable(project, node, "Counter") is True


def test_orphaned_after_detach_is_unresolvable():
    project = Project()
    node = _widget_in_doc(project)
    # The class was wired into an event, then detached from both the
    # widget and the window — nothing left to resolve against.
    assert _script_call_resolvable(project, node, "Counter") is False


def test_empty_class_is_unresolvable():
    project = Project()
    node = _widget_in_doc(project)
    node.attached_components = [_comp("counter.py", "Counter")]
    assert _script_call_resolvable(project, node, "") is False


def test_saved_project_requires_the_file_to_exist(tmp_path):
    # When the project is saved, resolvable must verify the script file
    # still exists — a binding to a deleted file is NOT valid (fix 3).
    proj_file = tmp_path / "demo.ctkproj"
    proj_file.write_text("{}", encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "counter.py").write_text(
        "from ctkmaker import CTkScript\n"
        "class Counter(CTkScript):\n    def go(self):\n        pass\n",
        encoding="utf-8",
    )
    project = Project()
    project.path = str(proj_file)
    node = _widget_in_doc(project)
    node.attached_components = [_comp("counter.py", "Counter")]

    assert _script_call_resolvable(project, node, "Counter", "widget") is True
    (scripts / "counter.py").unlink()
    assert _script_call_resolvable(project, node, "Counter", "widget") is False


def test_window_scope_does_not_resolve_against_widget(tmp_path):
    # A window-scope binding must not silently bind to a widget-scope
    # component of the same class (fix 2 — strict scope).
    proj_file = tmp_path / "demo.ctkproj"
    proj_file.write_text("{}", encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "dup.py").write_text(
        "from ctkmaker import CTkScript\nclass Dup(CTkScript):\n    pass\n",
        encoding="utf-8",
    )
    project = Project()
    project.path = str(proj_file)
    node = _widget_in_doc(project)
    node.attached_components = [_comp("dup.py", "Dup")]   # widget only

    assert _script_call_resolvable(project, node, "Dup", "widget") is True
    assert _script_call_resolvable(project, node, "Dup", "window") is False
