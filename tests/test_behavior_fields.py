"""Phase 3 Step 1 — Behavior Fields (ref[<WidgetType>] annotations).

Covers:
- ``parse_behavior_class_fields`` — AST scanner that extracts field
  specs from a behavior file's class body.
- ``ensure_runtime_helpers`` — auto-creates ``_runtime.py`` next to
  the per-page behavior subfolders.
- ``Document`` round-trips ``behavior_field_values`` through
  ``to_dict``/``from_dict``.
- ``SetBehaviorFieldCommand`` redo / undo flips the entry in
  ``Document.behavior_field_values`` and clears it on empty value.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.core.commands import (
    SetBehaviorFieldCommand,
    _clear_behavior_field_bindings_for_ids,
    _collect_ids_from_snapshot,
    _restore_behavior_field_bindings,
)
from app.core.document import Document
from app.io.scripts import (
    add_behavior_field_annotation,
    delete_behavior_field_annotation,
    ensure_imports_in_behavior_file,
    ensure_relative_import_in_behavior_file,
    ensure_runtime_helpers,
    existing_behavior_field_names,
    parse_behavior_class_fields,
    suggest_behavior_field_name,
)


# ---------------------------------------------------------------------
# parse_behavior_class_fields
# ---------------------------------------------------------------------
def _write_behavior(tmp_path: Path, body: str) -> Path:
    file_path = tmp_path / "login.py"
    file_path.write_text(textwrap.dedent(body), encoding="utf-8")
    return file_path


def test_parse_behavior_class_fields_returns_single_ref(tmp_path):
    file = _write_behavior(tmp_path, """
        class LoginPage:
            target_label: ref[CTkLabel]

            def setup(self, window):
                self.window = window
    """)
    fields = parse_behavior_class_fields(file, "LoginPage")
    assert len(fields) == 1
    assert fields[0].name == "target_label"
    assert fields[0].type_name == "CTkLabel"
    assert fields[0].lineno > 0


def test_parse_behavior_class_fields_returns_multiple_in_source_order(tmp_path):
    file = _write_behavior(tmp_path, """
        class LoginPage:
            label_top: ref[CTkLabel]
            entry: ref[CTkEntry]
            confirm_btn: ref[CTkButton]

            def setup(self, window):
                pass
    """)
    fields = parse_behavior_class_fields(file, "LoginPage")
    names = [f.name for f in fields]
    assert names == ["label_top", "entry", "confirm_btn"]
    types = [f.type_name for f in fields]
    assert types == ["CTkLabel", "CTkEntry", "CTkButton"]


def test_parse_behavior_class_fields_ignores_non_ref_annotations(tmp_path):
    file = _write_behavior(tmp_path, """
        class LoginPage:
            label: ref[CTkLabel]
            counter: int
            label_text: str = "hello"

            def setup(self, window):
                pass
    """)
    fields = parse_behavior_class_fields(file, "LoginPage")
    names = [f.name for f in fields]
    assert names == ["label"]


def test_parse_behavior_class_fields_ignores_optional_wrap(tmp_path):
    """Wrappers like ``Optional[ref[X]]`` are intentionally skipped —
    v1 only recognises bare ``ref[Name]`` so users can still keep
    plain typed attributes outside the binding system.
    """
    file = _write_behavior(tmp_path, """
        from typing import Optional
        class LoginPage:
            maybe: Optional[ref[CTkLabel]]
            real: ref[CTkLabel]
    """)
    fields = parse_behavior_class_fields(file, "LoginPage")
    names = [f.name for f in fields]
    assert names == ["real"]


def test_parse_behavior_class_fields_returns_empty_for_missing_file(tmp_path):
    fields = parse_behavior_class_fields(
        tmp_path / "missing.py", "LoginPage",
    )
    assert fields == []


def test_parse_behavior_class_fields_returns_empty_for_syntax_error(tmp_path):
    file = tmp_path / "broken.py"
    file.write_text("class LoginPage:\n    target = (", encoding="utf-8")
    fields = parse_behavior_class_fields(file, "LoginPage")
    assert fields == []


def test_parse_behavior_class_fields_returns_empty_when_class_missing(tmp_path):
    file = _write_behavior(tmp_path, """
        class OtherClass:
            target: ref[CTkLabel]
    """)
    fields = parse_behavior_class_fields(file, "LoginPage")
    assert fields == []


# ---------------------------------------------------------------------
# ensure_runtime_helpers
# ---------------------------------------------------------------------
def test_ensure_runtime_helpers_creates_module(tmp_path):
    project_file = tmp_path / "demo.ctkproj"
    project_file.write_text("{}", encoding="utf-8")
    runtime = ensure_runtime_helpers(project_file)
    assert runtime is not None
    assert runtime.exists()
    body = runtime.read_text(encoding="utf-8")
    assert "class ref(Generic[T]):" in body


def test_ensure_runtime_helpers_idempotent(tmp_path):
    project_file = tmp_path / "demo.ctkproj"
    project_file.write_text("{}", encoding="utf-8")
    runtime = ensure_runtime_helpers(project_file)
    assert runtime is not None
    runtime.write_text("# user edit\n", encoding="utf-8")
    again = ensure_runtime_helpers(project_file)
    assert again == runtime
    assert runtime.read_text(encoding="utf-8") == "# user edit\n"


def test_ensure_runtime_helpers_returns_none_for_unsaved():
    assert ensure_runtime_helpers(None) is None
    assert ensure_runtime_helpers("") is None


# ---------------------------------------------------------------------
# Document.behavior_field_values persistence
# ---------------------------------------------------------------------
def test_document_initialises_empty_field_values():
    doc = Document(name="Main")
    assert doc.behavior_field_values == {}


def test_document_to_dict_skips_empty_field_values():
    doc = Document(name="Main")
    payload = doc.to_dict()
    assert "behavior_field_values" not in payload


def test_document_to_dict_round_trips_field_values():
    doc = Document(name="Main")
    doc.behavior_field_values = {"target_label": "widget-uuid-1"}
    payload = doc.to_dict()
    assert payload["behavior_field_values"] == {
        "target_label": "widget-uuid-1",
    }
    restored = Document.from_dict(payload)
    assert restored.behavior_field_values == {
        "target_label": "widget-uuid-1",
    }


def test_document_from_dict_drops_non_string_values():
    payload = {
        "name": "Main",
        "widgets": [],
        "behavior_field_values": {
            "valid": "uuid-1",
            "drop_int": 42,
            "drop_empty": "",
            "drop_none": None,
        },
    }
    doc = Document.from_dict(payload)
    assert doc.behavior_field_values == {"valid": "uuid-1"}


# ---------------------------------------------------------------------
# SetBehaviorFieldCommand
# ---------------------------------------------------------------------
class _FakeBus:
    def __init__(self):
        self.events = []

    def publish(self, name, *args, **kwargs):
        self.events.append((name, args, kwargs))


class _FakeProject:
    def __init__(self, doc):
        self.documents = [doc]
        self.event_bus = _FakeBus()


def test_set_behavior_field_redo_writes_value():
    doc = Document(name="Main")
    project = _FakeProject(doc)
    cmd = SetBehaviorFieldCommand(doc.id, "target", "widget-1")
    cmd.redo(project)
    assert doc.behavior_field_values == {"target": "widget-1"}
    assert project.event_bus.events[0][0] == "behavior_field_changed"


def test_set_behavior_field_undo_clears_first_assignment():
    doc = Document(name="Main")
    project = _FakeProject(doc)
    cmd = SetBehaviorFieldCommand(doc.id, "target", "widget-1")
    cmd.redo(project)
    cmd.undo(project)
    assert doc.behavior_field_values == {}


def test_set_behavior_field_undo_restores_previous_value():
    doc = Document(name="Main")
    doc.behavior_field_values = {"target": "old-id"}
    project = _FakeProject(doc)
    cmd = SetBehaviorFieldCommand(doc.id, "target", "new-id")
    cmd.redo(project)
    assert doc.behavior_field_values == {"target": "new-id"}
    cmd.undo(project)
    assert doc.behavior_field_values == {"target": "old-id"}


def test_set_behavior_field_clear_drops_entry():
    doc = Document(name="Main")
    doc.behavior_field_values = {"target": "old-id"}
    project = _FakeProject(doc)
    cmd = SetBehaviorFieldCommand(doc.id, "target", "")
    cmd.redo(project)
    assert "target" not in doc.behavior_field_values
    cmd.undo(project)
    assert doc.behavior_field_values == {"target": "old-id"}


def test_set_behavior_field_no_op_for_missing_doc():
    doc = Document(name="Main")
    project = _FakeProject(doc)
    cmd = SetBehaviorFieldCommand("nonexistent-doc", "target", "widget-1")
    cmd.redo(project)
    assert doc.behavior_field_values == {}
    assert project.event_bus.events == []


# ---------------------------------------------------------------------
# existing_behavior_field_names
# ---------------------------------------------------------------------
def test_existing_behavior_field_names_includes_annotations_and_methods(tmp_path):
    file = _write_behavior(tmp_path, """
        class LoginPage:
            target: ref[CTkLabel]
            label_text: str = "hi"

            def setup(self, window):
                pass

            def on_click(self):
                pass
    """)
    names = existing_behavior_field_names(file, "LoginPage")
    assert names == {"target", "label_text", "setup", "on_click"}


def test_existing_behavior_field_names_empty_for_missing_file(tmp_path):
    assert existing_behavior_field_names(
        tmp_path / "missing.py", "LoginPage",
    ) == set()


# ---------------------------------------------------------------------
# add_behavior_field_annotation
# ---------------------------------------------------------------------
def test_add_behavior_field_annotation_inserts_above_first_method(tmp_path):
    file = _write_behavior(tmp_path, """
        class LoginPage:
            def setup(self, window):
                self.window = window
    """)
    ok = add_behavior_field_annotation(
        file, "LoginPage", "target", "CTkLabel",
    )
    assert ok is True
    body = file.read_text(encoding="utf-8")
    assert "target: ref[CTkLabel]" in body
    # Annotation appears before "def setup"
    assert body.index("target: ref[CTkLabel]") < body.index("def setup")


def test_add_behavior_field_annotation_replaces_pass_in_empty_class(tmp_path):
    file = _write_behavior(tmp_path, """
        class LoginPage:
            pass
    """)
    ok = add_behavior_field_annotation(
        file, "LoginPage", "target", "CTkLabel",
    )
    assert ok is True
    body = file.read_text(encoding="utf-8")
    assert "target: ref[CTkLabel]" in body
    assert "pass" not in body


def test_add_behavior_field_annotation_appends_after_existing_fields(tmp_path):
    file = _write_behavior(tmp_path, """
        class LoginPage:
            existing: ref[CTkLabel]

            def setup(self, window):
                pass
    """)
    add_behavior_field_annotation(
        file, "LoginPage", "added", "CTkButton",
    )
    body = file.read_text(encoding="utf-8")
    # Both annotations live above the method.
    assert body.index("existing") < body.index("added")
    assert body.index("added") < body.index("def setup")


def test_add_behavior_field_annotation_returns_false_for_syntax_error(tmp_path):
    file = tmp_path / "broken.py"
    file.write_text("class LoginPage:\n    target = (", encoding="utf-8")
    assert (
        add_behavior_field_annotation(
            file, "LoginPage", "target", "CTkLabel",
        )
        is False
    )


# ---------------------------------------------------------------------
# ensure_imports_in_behavior_file
# ---------------------------------------------------------------------
def test_ensure_imports_adds_missing(tmp_path):
    file = _write_behavior(tmp_path, '''
        """Doc."""

        class LoginPage:
            pass
    ''')
    ok = ensure_imports_in_behavior_file(
        file, [("customtkinter", "CTkLabel")],
    )
    assert ok is True
    body = file.read_text(encoding="utf-8")
    assert "from customtkinter import CTkLabel" in body


def test_ensure_imports_skips_existing(tmp_path):
    file = _write_behavior(tmp_path, """
        from customtkinter import CTkLabel

        class LoginPage:
            pass
    """)
    before = file.read_text(encoding="utf-8")
    ensure_imports_in_behavior_file(
        file, [("customtkinter", "CTkLabel")],
    )
    after = file.read_text(encoding="utf-8")
    # No duplicate added.
    assert after.count("from customtkinter import CTkLabel") == 1
    assert before.count("\n") == after.count("\n")


def test_ensure_imports_groups_same_module(tmp_path):
    file = _write_behavior(tmp_path, """
        class LoginPage:
            pass
    """)
    ensure_imports_in_behavior_file(
        file, [("customtkinter", "CTkLabel"), ("customtkinter", "CTkButton")],
    )
    body = file.read_text(encoding="utf-8")
    assert "from customtkinter import CTkLabel, CTkButton" in body


# ---------------------------------------------------------------------
# ensure_relative_import_in_behavior_file
# ---------------------------------------------------------------------
def test_ensure_relative_import_adds_runtime_ref(tmp_path):
    file = _write_behavior(tmp_path, """
        class LoginPage:
            pass
    """)
    ok = ensure_relative_import_in_behavior_file(
        file, level=2, module="_runtime", name="ref",
    )
    assert ok is True
    body = file.read_text(encoding="utf-8")
    assert "from .._runtime import ref" in body


def test_ensure_relative_import_idempotent(tmp_path):
    file = _write_behavior(tmp_path, """
        from .._runtime import ref

        class LoginPage:
            pass
    """)
    before = file.read_text(encoding="utf-8")
    ensure_relative_import_in_behavior_file(
        file, level=2, module="_runtime", name="ref",
    )
    after = file.read_text(encoding="utf-8")
    assert after.count("from .._runtime import ref") == 1
    assert before == after


# ---------------------------------------------------------------------
# suggest_behavior_field_name
# ---------------------------------------------------------------------
def test_suggest_behavior_field_name_uses_widget_name():
    assert (
        suggest_behavior_field_name("My Label", "CTkLabel", set())
        == "my_label"
    )


def test_suggest_behavior_field_name_falls_back_to_type():
    assert (
        suggest_behavior_field_name("", "CTkButton", set())
        == "ctkbutton"
    )


def test_suggest_behavior_field_name_appends_suffix_on_collision():
    existing = {"my_label", "my_label_2"}
    assert (
        suggest_behavior_field_name("My Label", "CTkLabel", existing)
        == "my_label_3"
    )


# ---------------------------------------------------------------------
# Orphan handler filtering (v1.9.1 — defensive export)
# ---------------------------------------------------------------------
def test_filter_handlers_keeps_existing_drops_missing(monkeypatch):
    """``_filter_handlers_to_existing_methods`` keeps method names
    listed in the per-doc scan, drops ones that don't exist, and
    appends drops to ``_MISSING_BEHAVIOR_METHODS`` so the caller
    can surface them via ``get_missing_behavior_methods``.
    """
    import app.io.code_exporter as ce

    class _FakeNode:
        id = "widget-1"

    class _FakeDoc:
        id = "doc-1"
        name = "Main"

    class _FakeProject:
        documents = [_FakeDoc()]

        def find_document_for_widget(self, wid):
            return _FakeDoc() if wid == "widget-1" else None

    monkeypatch.setattr(ce, "_EXPORT_PROJECT", _FakeProject())
    monkeypatch.setattr(
        ce, "_BEHAVIOR_METHODS_BY_DOC_ID", {"doc-1": {"on_click"}},
    )
    monkeypatch.setattr(ce, "_MISSING_BEHAVIOR_METHODS", [])
    kept = ce._filter_handlers_to_existing_methods(
        _FakeNode(), ["on_click", "missing_method"],
    )
    assert kept == ["on_click"]
    assert ce.get_missing_behavior_methods() == [
        ("Main", "missing_method"),
    ]


def test_filter_handlers_no_op_without_scan_data(monkeypatch):
    """When the doc has no scan data (file never materialised, or
    project unsaved), the filter falls through unchanged so legacy
    exports keep working.
    """
    import app.io.code_exporter as ce

    class _FakeNode:
        id = "widget-1"

    class _FakeDoc:
        id = "doc-1"
        name = "Main"

    class _FakeProject:
        documents = [_FakeDoc()]

        def find_document_for_widget(self, wid):
            return _FakeDoc()

    monkeypatch.setattr(ce, "_EXPORT_PROJECT", _FakeProject())
    monkeypatch.setattr(ce, "_BEHAVIOR_METHODS_BY_DOC_ID", {})
    monkeypatch.setattr(ce, "_MISSING_BEHAVIOR_METHODS", [])
    kept = ce._filter_handlers_to_existing_methods(
        _FakeNode(), ["on_click", "missing_method"],
    )
    assert kept == ["on_click", "missing_method"]
    assert ce.get_missing_behavior_methods() == []


def test_filter_handlers_no_op_without_export_project(monkeypatch):
    import app.io.code_exporter as ce

    class _FakeNode:
        id = "widget-1"

    monkeypatch.setattr(ce, "_EXPORT_PROJECT", None)
    monkeypatch.setattr(ce, "_BEHAVIOR_METHODS_BY_DOC_ID", {})
    monkeypatch.setattr(ce, "_MISSING_BEHAVIOR_METHODS", [])
    kept = ce._filter_handlers_to_existing_methods(
        _FakeNode(), ["on_click"],
    )
    assert kept == ["on_click"]


# ---------------------------------------------------------------------
# delete_behavior_field_annotation (v1.9.3 — UI delete flow)
# ---------------------------------------------------------------------
def test_delete_behavior_field_annotation_removes_line(tmp_path):
    file = _write_behavior(tmp_path, """
        class LoginPage:
            target: ref[CTkLabel]
            other: ref[CTkButton]

            def setup(self, window):
                pass
    """)
    ok = delete_behavior_field_annotation(file, "LoginPage", "target")
    assert ok is True
    body = file.read_text(encoding="utf-8")
    assert "target: ref[CTkLabel]" not in body
    # Sibling annotation survives — single-line removal only.
    assert "other: ref[CTkButton]" in body
    # Method below stays put.
    assert "def setup" in body


def test_delete_behavior_field_annotation_no_op_for_missing_field(tmp_path):
    file = _write_behavior(tmp_path, """
        class LoginPage:
            target: ref[CTkLabel]
    """)
    before = file.read_text(encoding="utf-8")
    ok = delete_behavior_field_annotation(file, "LoginPage", "ghost")
    assert ok is False
    assert file.read_text(encoding="utf-8") == before


def test_delete_behavior_field_annotation_no_op_for_syntax_error(tmp_path):
    file = tmp_path / "broken.py"
    file.write_text("class LoginPage:\n    target = (", encoding="utf-8")
    assert (
        delete_behavior_field_annotation(file, "LoginPage", "target")
        is False
    )


# ---------------------------------------------------------------------
# Widget delete cascade — Behavior Field cleanup (v1.9.3)
# ---------------------------------------------------------------------
def test_collect_ids_from_snapshot_walks_descendants():
    snapshot = {
        "id": "root",
        "children": [
            {"id": "child-1", "children": []},
            {
                "id": "child-2",
                "children": [
                    {"id": "grandchild", "children": []},
                ],
            },
        ],
    }
    ids = _collect_ids_from_snapshot(snapshot)
    assert ids == {"root", "child-1", "child-2", "grandchild"}


def test_clear_behavior_field_bindings_clears_pointing_entries():
    doc = Document(name="Main")
    doc.behavior_field_values = {
        "label": "widget-1",
        "button": "widget-2",
    }
    project = _FakeProject(doc)
    cleared = _clear_behavior_field_bindings_for_ids(
        project, {"widget-1"},
    )
    assert cleared == [(doc.id, "label", "widget-1")]
    assert doc.behavior_field_values == {"button": "widget-2"}
    # Single behavior_field_changed event for the cleared slot.
    assert any(
        e[0] == "behavior_field_changed"
        for e in project.event_bus.events
    )


def test_clear_behavior_field_bindings_walks_every_doc():
    doc1 = Document(name="Main")
    doc1.behavior_field_values = {"shared": "widget-1"}
    doc2 = Document(name="Dialog")
    doc2.behavior_field_values = {"local": "widget-1"}

    class _MultiDocProject(_FakeProject):
        def __init__(self):
            self.documents = [doc1, doc2]
            self.event_bus = _FakeBus()

    project = _MultiDocProject()
    cleared = _clear_behavior_field_bindings_for_ids(
        project, {"widget-1"},
    )
    assert {(d, f) for d, f, _ in cleared} == {
        (doc1.id, "shared"), (doc2.id, "local"),
    }
    assert doc1.behavior_field_values == {}
    assert doc2.behavior_field_values == {}


def test_restore_behavior_field_bindings_replays_cleared_entries():
    doc = Document(name="Main")
    project = _FakeProject(doc)
    cleared = [(doc.id, "label", "widget-1")]
    _restore_behavior_field_bindings(project, cleared)
    assert doc.behavior_field_values == {"label": "widget-1"}
    assert any(
        e[0] == "behavior_field_changed"
        for e in project.event_bus.events
    )


def test_restore_behavior_field_bindings_skips_missing_doc():
    doc = Document(name="Main")
    project = _FakeProject(doc)
    cleared = [("ghost-doc", "label", "widget-1")]
    _restore_behavior_field_bindings(project, cleared)
    assert doc.behavior_field_values == {}


# ---------------------------------------------------------------------
# Auto-trace emission for non-textvariable var bindings (v1.9.5)
# ---------------------------------------------------------------------
def _build_export_project(extra_widgets=()):
    """Synthesise a Project with one Document + a global ``status`` var.
    Returns ``(project, var)``. Caller plops widgets into
    ``doc.root_widgets``.
    """
    from app.core.project import Project
    from app.core.variables import VariableEntry
    project = Project()
    project.path = "/tmp/probe.ctkproj"
    var = VariableEntry(name="status", type="str", default="initial")
    project.variables = [var]
    doc = project.documents[0]
    doc.name = "Main Window"
    for w in extra_widgets:
        doc.root_widgets.append(w)
    return project, var


def _export_to_string(project, tmp_path):
    """Run ``export_project`` against ``tmp_path/out.py`` and return
    the generated source as a string. Wraps the file IO so tests
    don't have to.
    """
    from app.io.code_exporter import export_project
    out = tmp_path / "out.py"
    export_project(project, out, inject_preview_screenshot=False)
    return out.read_text(encoding="utf-8")


def test_export_emits_widget_helper_for_button_text_binding(tmp_path):
    from app.core.widget_node import WidgetNode
    button = WidgetNode("CTkButton")
    button.properties = {
        "x": 10, "y": 40, "width": 80, "height": 30,
    }
    project, var = _build_export_project([button])
    button.properties["text"] = f"var:{var.id}"
    src = _export_to_string(project, tmp_path)
    assert "def _bind_var_to_widget" in src
    assert (
        '_bind_var_to_widget(self.var_status, self.button_1, "text")'
        in src
    )


def test_export_emits_textbox_helper_for_initial_text_binding(tmp_path):
    from app.core.widget_node import WidgetNode
    tb = WidgetNode("CTkTextbox")
    tb.properties = {
        "x": 10, "y": 40, "width": 200, "height": 100,
    }
    project, var = _build_export_project([tb])
    tb.properties["initial_text"] = f"var:{var.id}"
    src = _export_to_string(project, tmp_path)
    assert "def _bind_var_to_textbox" in src
    assert "_bind_var_to_textbox(self.var_status, self.textbox_1)" in src


def test_export_skips_helpers_for_pure_textvariable_projects(tmp_path):
    """Label.text is in BINDING_WIRINGS — it routes through
    ``textvariable=`` and shouldn't trigger the auto-trace
    helpers.
    """
    from app.core.widget_node import WidgetNode
    label = WidgetNode("CTkLabel")
    label.properties = {
        "x": 10, "y": 10, "width": 80, "height": 20,
    }
    project, var = _build_export_project([label])
    label.properties["text"] = f"var:{var.id}"
    src = _export_to_string(project, tmp_path)
    assert "textvariable=" in src
    assert "_bind_var_to_widget" not in src
    assert "_bind_var_to_textbox" not in src


def test_export_resolves_textbox_token_to_current_value(tmp_path):
    """Pre-1.9.5 the exporter wrote ``self.textbox_1.insert("1.0",
    "var:<uuid>")`` literally because the var-token sub layer only
    rewrote constructor kwargs. v1.9.5 resolves the token to the
    var's current value before passing props to ``export_state``.
    """
    from app.core.widget_node import WidgetNode
    tb = WidgetNode("CTkTextbox")
    tb.properties = {
        "x": 10, "y": 40, "width": 200, "height": 100,
    }
    project, var = _build_export_project([tb])
    tb.properties["initial_text"] = f"var:{var.id}"
    src = _export_to_string(project, tmp_path)
    assert f"var:{var.id}" not in src
    assert "self.textbox_1.insert" in src
    assert "'initial'" in src or '"initial"' in src


def test_export_compiles_clean_python(tmp_path):
    """Catches indentation / quoting bugs in the helper templates +
    per-widget binding lines. Compile without raising = the
    generated file is at least syntactically valid.
    """
    from app.core.widget_node import WidgetNode
    button = WidgetNode("CTkButton")
    button.properties = {
        "x": 10, "y": 40, "width": 80, "height": 30,
    }
    tb = WidgetNode("CTkTextbox")
    tb.properties = {
        "x": 10, "y": 80, "width": 200, "height": 60,
    }
    project, var = _build_export_project([button, tb])
    button.properties["text"] = f"var:{var.id}"
    tb.properties["initial_text"] = f"var:{var.id}"
    src = _export_to_string(project, tmp_path)
    compile(src, "<exported>", "exec")  # raises on syntax error
