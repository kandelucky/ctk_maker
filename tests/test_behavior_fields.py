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
    ensure_runtime_helpers,
    parse_behavior_class_fields,
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
