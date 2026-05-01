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

from app.core.commands import SetBehaviorFieldCommand
from app.core.document import Document
from app.io.scripts import (
    add_behavior_field_annotation,
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
