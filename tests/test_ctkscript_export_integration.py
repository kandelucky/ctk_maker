"""Integration: CTkScript wiring lands in the generated source.

Drives the real ``generate_code`` pipeline with a project that has
attached components + script_call bindings, and checks the emitted
instantiation / scope-injection / on_start / on_close / event wiring.
Component-less exports are unaffected (covered by the rest of the
suite). See docs/plans/script_optimization.md.
"""
from __future__ import annotations

import pytest

from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.io import code_exporter
from app.io.code_exporter import generate_code
from app.widgets.registry import get_descriptor


@pytest.fixture(autouse=True)
def _reset_exporter_state():
    code_exporter._VAR_NAME_FALLBACKS = []
    code_exporter._NAME_MAP_CACHE = {}
    code_exporter._CURRENT_DOC_COMPONENTS = None
    yield
    code_exporter._VAR_NAME_FALLBACKS = []
    code_exporter._NAME_MAP_CACHE = {}
    code_exporter._CURRENT_DOC_COMPONENTS = None


def _button(project: Project, name: str, handlers=None, components=None):
    desc = get_descriptor("CTkButton")
    node = WidgetNode(widget_type="CTkButton")
    node.name = name
    node.properties = dict(desc.default_properties)
    if handlers:
        node.handlers = handlers
    if components:
        node.attached_components = components
    project.active_document.root_widgets.append(node)
    return node


def test_widget_scoped_component_wiring():
    project = Project()
    _button(
        project, "my_button",
        components=[{"script": "counter.py", "class": "ClickCounter"}],
        handlers={"command": [
            {"kind": "script_call", "class": "ClickCounter", "method": "bump"},
        ]},
    )
    src = generate_code(project)
    assert "self._script_0 = ClickCounter()" in src       # before _build_ui
    assert "self._script_0.widget = self.my_button" in src  # widget scope
    assert "self._script_0.on_start()" in src
    assert "command=self._script_0.bump" in src           # event → method


def test_window_scoped_component_reachable_from_widget_event():
    project = Project()
    project.active_document.attached_components = [
        {"script": "form.py", "class": "LoginForm"},
    ]
    _button(
        project, "submit_btn",
        handlers={"command": [
            {"kind": "script_call", "class": "LoginForm", "method": "submit"},
        ]},
    )
    src = generate_code(project)
    assert "self._script_0 = LoginForm()" in src
    assert "self._script_0.window = self" in src          # window scope
    assert "command=self._script_0.submit" in src


def test_on_close_protocol_emitted():
    project = Project()
    project.active_document.attached_components = [
        {"script": "form.py", "class": "LoginForm"},
    ]
    src = generate_code(project)
    assert (
        'self.protocol("WM_DELETE_WINDOW", '
        'lambda: (self._script_0.on_close(), self.destroy()))'
    ) in src


def test_component_import_emitted():
    project = Project()
    _button(
        project, "my_button",
        components=[{"script": "counter.py", "class": "ClickCounter"}],
    )
    src = generate_code(project)
    assert "from scripts.counter import ClickCounter" in src


def test_component_import_deduped_across_widgets():
    project = Project()
    comp = [{"script": "counter.py", "class": "ClickCounter"}]
    _button(project, "btn_a", components=list(comp))
    _button(project, "btn_b", components=list(comp))
    src = generate_code(project)
    assert src.count("from scripts.counter import ClickCounter") == 1


def test_no_components_leaves_export_clean():
    project = Project()
    _button(project, "plain_btn")
    src = generate_code(project)
    assert "_script_0" not in src
    assert "on_start()" not in src
    assert "from scripts." not in src


def _script_file(tmp_path, body: str) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "counter.py").write_text(body, encoding="utf-8")


def test_exposed_field_triggers_tk_import(tmp_path):
    # Regression: a script exposing a field in a project with no
    # variables of its own must still pull in ``import tkinter as tk``
    # — the field injection emits ``tk.StringVar()``.
    _script_file(
        tmp_path,
        "import tkinter as tk\n"
        "from ctkmaker import CTkScript\n\n\n"
        "class ClickCounter(CTkScript):\n"
        "    title: tk.StringVar\n\n"
        "    def bump(self):\n"
        "        pass\n",
    )
    project = Project()
    project.path = str(tmp_path / "page.ctkproj")
    _button(
        project, "my_button",
        components=[{"script": "counter.py", "class": "ClickCounter"}],
    )
    src = generate_code(project)
    assert "self._script_0.title = tk.StringVar()" in src
    assert "import tkinter as tk" in src


def test_fieldless_script_keeps_tk_import_out(tmp_path):
    _script_file(
        tmp_path,
        "from ctkmaker import CTkScript\n\n\n"
        "class ClickCounter(CTkScript):\n"
        "    def bump(self):\n"
        "        pass\n",
    )
    project = Project()
    project.path = str(tmp_path / "page.ctkproj")
    _button(
        project, "my_button",
        components=[{"script": "counter.py", "class": "ClickCounter"}],
    )
    src = generate_code(project)
    assert "import tkinter as tk" not in src
