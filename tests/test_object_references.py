"""v1.11.0 Object References — typed widget / document pointers
that live alongside Variables in the Variables window and surface
as a per-widget / per-Window toggle row in Properties.

Covers:
- ``ObjectReferenceEntry`` round-trip + scope defaults.
- ``suggest_ref_name`` collision suffixes + fallback for non-identifier
  widget names.
- ``is_valid_python_identifier`` keyword + identifier rules.
- ``short_type_label`` known-type mapping + identity fallback.
- ``required_scope_for`` Window / Dialog → global enforcement.
- ``Project`` and ``Document`` ``to_dict`` / ``from_dict`` round-trip.
- Legacy ``behavior_field_values`` JSON migration — handled inside
  ``Document.from_dict``, default target_type ``CTkLabel``,
  idempotent on already-present names.
- ``AddObjectReferenceCommand``, ``DeleteObjectReferenceCommand``,
  ``RenameObjectReferenceCommand``, ``SetObjectReferenceTargetCommand``
  redo / undo + scope routing.
- ``_emit_object_reference_lines`` — local widget refs + global doc
  refs both emit ``self._behavior.<name> = ...`` lines, missing
  targets are silently dropped.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.core.commands import (
    AddObjectReferenceCommand,
    DeleteObjectReferenceCommand,
    RenameObjectReferenceCommand,
    SetObjectReferenceTargetCommand,
)
from app.core.document import Document
from app.core.object_references import (
    DOCUMENT_TARGET_TYPES,
    ObjectReferenceEntry,
    is_valid_python_identifier,
    required_scope_for,
    short_type_label,
    suggest_ref_name,
)
from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.io import code_exporter
from app.io.code_exporter import _emit_object_reference_lines


# ---------------------------------------------------------------------
# ObjectReferenceEntry — model basics
# ---------------------------------------------------------------------
def test_entry_default_values():
    entry = ObjectReferenceEntry()
    assert entry.id  # uuid-generated
    assert entry.name == ""
    assert entry.target_type == "CTkLabel"
    assert entry.scope == "local"
    assert entry.target_id == ""


def test_entry_round_trip_preserves_fields():
    entry = ObjectReferenceEntry(
        id="ref-1", name="status_label",
        target_type="CTkLabel", scope="local",
        target_id="widget-7",
    )
    payload = entry.to_dict()
    restored = ObjectReferenceEntry.from_dict(payload)
    assert restored.id == "ref-1"
    assert restored.name == "status_label"
    assert restored.target_type == "CTkLabel"
    assert restored.scope == "local"
    assert restored.target_id == "widget-7"


def test_entry_from_dict_clamps_unknown_scope_to_local():
    entry = ObjectReferenceEntry.from_dict({
        "id": "ref-1", "name": "x", "target_type": "CTkLabel",
        "scope": "garbage", "target_id": "",
    })
    assert entry.scope == "local"


def test_entry_from_dict_generates_id_when_missing():
    entry = ObjectReferenceEntry.from_dict({
        "name": "x", "target_type": "CTkButton",
    })
    assert entry.id  # auto-uuid
    assert entry.name == "x"


# ---------------------------------------------------------------------
# Helpers — suggest_ref_name / is_valid_python_identifier /
# short_type_label / required_scope_for
# ---------------------------------------------------------------------
def test_suggest_ref_name_uses_widget_name_when_valid():
    out = suggest_ref_name("submit_btn", "CTkButton", existing_names=set())
    assert out == "submit_btn"


def test_suggest_ref_name_falls_back_to_type_when_name_invalid():
    out = suggest_ref_name("123 spaces!", "CTkLabel", existing_names=set())
    # Strips ``Ctk`` prefix + appends ``_ref``.
    assert out == "label_ref"


def test_suggest_ref_name_dedupes_with_numeric_suffix():
    existing = {"submit_btn", "submit_btn_2"}
    out = suggest_ref_name("submit_btn", "CTkButton", existing)
    assert out == "submit_btn_3"


def test_suggest_ref_name_skips_through_collisions():
    existing = {"label_ref", "label_ref_2"}
    out = suggest_ref_name("", "CTkLabel", existing)
    assert out == "label_ref_3"


def test_is_valid_python_identifier_accepts_snake_case():
    assert is_valid_python_identifier("foo_bar")
    assert is_valid_python_identifier("_leading_under")
    assert is_valid_python_identifier("name1")


def test_is_valid_python_identifier_rejects_keywords():
    assert not is_valid_python_identifier("class")
    assert not is_valid_python_identifier("def")
    assert not is_valid_python_identifier("None")


def test_is_valid_python_identifier_rejects_invalid_strings():
    assert not is_valid_python_identifier("")
    assert not is_valid_python_identifier("123name")
    assert not is_valid_python_identifier("with-dash")
    assert not is_valid_python_identifier("has space")


def test_short_type_label_maps_known_widget_types():
    assert short_type_label("CTkButton") == "Btn"
    assert short_type_label("CTkLabel") == "Lbl"
    assert short_type_label("CTkScrollableFrame") == "ScF"
    assert short_type_label("Window") == "Win"
    assert short_type_label("Dialog") == "Dlg"


def test_short_type_label_returns_input_for_unknown_types():
    # Custom widgets the table doesn't enumerate yet pass through.
    assert short_type_label("MyCustomWidget") == "MyCustomWidget"


def test_required_scope_for_window_and_dialog_are_global():
    assert required_scope_for("Window") == "global"
    assert required_scope_for("Dialog") == "global"


def test_required_scope_for_widgets_is_local():
    assert required_scope_for("CTkButton") == "local"
    assert required_scope_for("CTkLabel") == "local"


def test_document_target_types_includes_window_and_dialog():
    assert "Window" in DOCUMENT_TARGET_TYPES
    assert "Dialog" in DOCUMENT_TARGET_TYPES


# ---------------------------------------------------------------------
# Document round-trip
# ---------------------------------------------------------------------
def test_document_serializes_local_object_references():
    doc = Document(name="Main")
    doc.local_object_references.append(ObjectReferenceEntry(
        id="ref-1", name="status_label",
        target_type="CTkLabel", scope="local", target_id="widget-7",
    ))
    payload = doc.to_dict()
    restored = Document.from_dict(payload)
    assert len(restored.local_object_references) == 1
    entry = restored.local_object_references[0]
    assert entry.id == "ref-1"
    assert entry.name == "status_label"
    assert entry.scope == "local"
    assert entry.target_id == "widget-7"


def test_document_omits_local_refs_key_when_empty():
    doc = Document(name="Main")
    payload = doc.to_dict()
    assert "local_object_references" not in payload


def test_document_forces_local_scope_on_restore():
    payload = {
        "name": "Main", "width": 800, "height": 600,
        "local_object_references": [
            {
                "id": "ref-1", "name": "x", "target_type": "CTkLabel",
                "scope": "global",  # wrong — should be coerced
                "target_id": "",
            },
        ],
    }
    doc = Document.from_dict(payload)
    assert doc.local_object_references[0].scope == "local"


# ---------------------------------------------------------------------
# Project — globals
# ---------------------------------------------------------------------
def test_project_starts_with_empty_object_references():
    project = Project()
    assert project.object_references == []


def test_project_holds_global_refs_separately_from_doc_locals():
    project = Project()
    project.object_references.append(ObjectReferenceEntry(
        id="g1", name="settings_dialog",
        target_type="Dialog", scope="global",
        target_id=project.active_document.id,
    ))
    project.active_document.local_object_references.append(
        ObjectReferenceEntry(
            id="l1", name="status_label",
            target_type="CTkLabel", scope="local",
            target_id="widget-7",
        ),
    )
    assert len(project.object_references) == 1
    assert project.object_references[0].scope == "global"
    assert len(project.active_document.local_object_references) == 1
    assert project.active_document.local_object_references[0].scope == "local"


# ---------------------------------------------------------------------
# Legacy behavior_field_values JSON migration (Document.from_dict)
# ---------------------------------------------------------------------
def test_legacy_json_migration_converts_to_local_object_references():
    """A pre-v1.10.8 ``.ctkproj`` carrying a ``behavior_field_values``
    dict is migrated to ``local_object_references`` entries during
    ``Document.from_dict``. Target type defaults to ``CTkLabel``
    because the legacy JSON didn't carry type info.
    """
    payload = {
        "id": "doc-1", "name": "Main",
        "width": 800, "height": 600,
        "behavior_field_values": {"target_label": "widget-1"},
    }
    doc = Document.from_dict(payload)
    assert len(doc.local_object_references) == 1
    entry = doc.local_object_references[0]
    assert entry.name == "target_label"
    assert entry.target_id == "widget-1"
    assert entry.target_type == "CTkLabel"
    assert entry.scope == "local"


def test_legacy_json_migration_skips_existing_names():
    """When ``local_object_references`` already contains an entry with
    the same name (e.g. a partially-migrated project re-saved and
    re-loaded), the legacy entry is dropped — the modern entry wins.
    """
    payload = {
        "id": "doc-1", "name": "Main",
        "width": 800, "height": 600,
        "local_object_references": [{
            "id": "ref-1", "name": "status_label",
            "target_type": "CTkButton", "scope": "local",
            "target_id": "widget-7",
        }],
        "behavior_field_values": {"status_label": "different-widget"},
    }
    doc = Document.from_dict(payload)
    assert len(doc.local_object_references) == 1
    entry = doc.local_object_references[0]
    assert entry.target_id == "widget-7"
    assert entry.target_type == "CTkButton"


def test_legacy_json_migration_no_op_without_dict():
    payload = {
        "id": "doc-1", "name": "Main",
        "width": 800, "height": 600,
    }
    doc = Document.from_dict(payload)
    assert doc.local_object_references == []


def test_legacy_json_migration_drops_save_format():
    """Round-trip: a legacy dict in JSON should NOT round-trip back
    on save — ``to_dict`` must omit ``behavior_field_values`` so
    the next save format is the modern one.
    """
    payload = {
        "id": "doc-1", "name": "Main",
        "width": 800, "height": 600,
        "behavior_field_values": {"target_label": "widget-1"},
    }
    doc = Document.from_dict(payload)
    saved = doc.to_dict()
    assert "behavior_field_values" not in saved
    # The migrated entry persists in the modern slot.
    assert len(saved.get("local_object_references", [])) == 1


# ---------------------------------------------------------------------
# Commands — Add / Delete / Rename / SetTarget
# ---------------------------------------------------------------------
def test_add_object_reference_command_inserts_local_entry():
    project = Project()
    doc = project.active_document
    entry = ObjectReferenceEntry(
        id="ref-1", name="status_label",
        target_type="CTkLabel", scope="local",
        target_id="widget-7",
    )
    cmd = AddObjectReferenceCommand(
        entry.to_dict(), index=0,
        scope="local", document_id=doc.id,
    )
    cmd.redo(project)
    assert len(doc.local_object_references) == 1
    assert doc.local_object_references[0].name == "status_label"
    cmd.undo(project)
    assert doc.local_object_references == []


def test_add_object_reference_command_routes_globals_to_project():
    project = Project()
    entry = ObjectReferenceEntry(
        id="g1", name="settings_dialog",
        target_type="Dialog", scope="global",
        target_id="doc-x",
    )
    cmd = AddObjectReferenceCommand(
        entry.to_dict(), index=0, scope="global", document_id=None,
    )
    cmd.redo(project)
    assert len(project.object_references) == 1
    assert project.object_references[0].scope == "global"
    cmd.undo(project)
    assert project.object_references == []


def test_delete_object_reference_command_pops_at_recorded_index():
    project = Project()
    doc = project.active_document
    e1 = ObjectReferenceEntry(
        id="ref-1", name="a", target_type="CTkLabel",
        scope="local", target_id="w1",
    )
    e2 = ObjectReferenceEntry(
        id="ref-2", name="b", target_type="CTkLabel",
        scope="local", target_id="w2",
    )
    doc.local_object_references.extend([e1, e2])
    cmd = DeleteObjectReferenceCommand(
        e1.to_dict(), index=0, scope="local", document_id=doc.id,
    )
    cmd.redo(project)
    assert [e.id for e in doc.local_object_references] == ["ref-2"]
    cmd.undo(project)
    assert [e.id for e in doc.local_object_references] == ["ref-1", "ref-2"]


def test_rename_object_reference_command_round_trips():
    project = Project()
    doc = project.active_document
    entry = ObjectReferenceEntry(
        id="ref-1", name="old_name",
        target_type="CTkLabel", scope="local",
        target_id="w1",
    )
    doc.local_object_references.append(entry)
    cmd = RenameObjectReferenceCommand(
        ref_id="ref-1", before="old_name", after="new_name",
    )
    cmd.redo(project)
    assert doc.local_object_references[0].name == "new_name"
    cmd.undo(project)
    assert doc.local_object_references[0].name == "old_name"


def test_set_object_reference_target_command_round_trips():
    project = Project()
    doc = project.active_document
    entry = ObjectReferenceEntry(
        id="ref-1", name="status_label",
        target_type="CTkLabel", scope="local",
        target_id="widget-1",
    )
    doc.local_object_references.append(entry)
    cmd = SetObjectReferenceTargetCommand(
        ref_id="ref-1", new_target_id="widget-2",
    )
    cmd.redo(project)
    assert doc.local_object_references[0].target_id == "widget-2"
    cmd.undo(project)
    assert doc.local_object_references[0].target_id == "widget-1"


def test_set_object_reference_target_clears_with_empty_id():
    project = Project()
    doc = project.active_document
    entry = ObjectReferenceEntry(
        id="ref-1", name="status_label",
        target_type="CTkLabel", scope="local",
        target_id="widget-1",
    )
    doc.local_object_references.append(entry)
    cmd = SetObjectReferenceTargetCommand(
        ref_id="ref-1", new_target_id="",
    )
    cmd.redo(project)
    assert doc.local_object_references[0].target_id == ""
    cmd.undo(project)
    assert doc.local_object_references[0].target_id == "widget-1"


def test_command_no_op_when_entry_id_missing():
    project = Project()
    cmd = SetObjectReferenceTargetCommand(
        ref_id="nonexistent", new_target_id="widget-x",
    )
    # No raise — just silently skip.
    cmd.redo(project)
    cmd.undo(project)


# ---------------------------------------------------------------------
# Code exporter — _emit_object_reference_lines for locals + globals
# ---------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_exporter_globals():
    prev_project = code_exporter._EXPORT_PROJECT
    prev_doc_class = dict(code_exporter._DOC_ID_TO_CLASS)
    yield
    code_exporter._EXPORT_PROJECT = prev_project
    code_exporter._DOC_ID_TO_CLASS = prev_doc_class


def test_emit_field_lines_writes_local_refs_using_widget_var_map():
    doc = Document(name="Main")
    doc.local_object_references.append(ObjectReferenceEntry(
        id="ref-1", name="status_label",
        target_type="CTkLabel", scope="local",
        target_id="widget-7",
    ))
    project = Project()
    code_exporter._EXPORT_PROJECT = project
    code_exporter._DOC_ID_TO_CLASS = {}
    lines = _emit_object_reference_lines(
        doc, id_to_var={"widget-7": "label_1"}, instance_prefix="self.",
    )
    assert len(lines) == 1
    assert "self._behavior.status_label = self.label_1" in lines[0]


def test_emit_field_lines_writes_global_refs_using_class_map():
    doc = Document(name="Main")
    project = Project()
    project.object_references.append(ObjectReferenceEntry(
        id="g1", name="settings_dialog",
        target_type="Dialog", scope="global",
        target_id="dialog-doc-id",
    ))
    code_exporter._EXPORT_PROJECT = project
    code_exporter._DOC_ID_TO_CLASS = {"dialog-doc-id": "SettingsDialog"}
    lines = _emit_object_reference_lines(
        doc, id_to_var={}, instance_prefix="self.",
    )
    assert len(lines) == 1
    assert "self._behavior.settings_dialog = SettingsDialog" in lines[0]


def test_emit_field_lines_emits_locals_then_globals():
    doc = Document(name="Main")
    doc.local_object_references.append(ObjectReferenceEntry(
        id="l1", name="status_label",
        target_type="CTkLabel", scope="local",
        target_id="widget-7",
    ))
    project = Project()
    project.object_references.append(ObjectReferenceEntry(
        id="g1", name="settings_dialog",
        target_type="Dialog", scope="global",
        target_id="dialog-doc-id",
    ))
    code_exporter._EXPORT_PROJECT = project
    code_exporter._DOC_ID_TO_CLASS = {"dialog-doc-id": "SettingsDialog"}
    lines = _emit_object_reference_lines(
        doc, id_to_var={"widget-7": "label_1"}, instance_prefix="self.",
    )
    assert len(lines) == 2
    assert "status_label" in lines[0]
    assert "settings_dialog" in lines[1]


def test_emit_field_lines_drops_unbound_local():
    doc = Document(name="Main")
    doc.local_object_references.append(ObjectReferenceEntry(
        id="ref-1", name="status_label",
        target_type="CTkLabel", scope="local",
        target_id="",  # never bound
    ))
    project = Project()
    code_exporter._EXPORT_PROJECT = project
    code_exporter._DOC_ID_TO_CLASS = {}
    lines = _emit_object_reference_lines(
        doc, id_to_var={}, instance_prefix="self.",
    )
    assert lines == []


def test_emit_field_lines_drops_local_with_missing_widget():
    doc = Document(name="Main")
    doc.local_object_references.append(ObjectReferenceEntry(
        id="ref-1", name="status_label",
        target_type="CTkLabel", scope="local",
        target_id="widget-stale",
    ))
    project = Project()
    code_exporter._EXPORT_PROJECT = project
    code_exporter._DOC_ID_TO_CLASS = {}
    lines = _emit_object_reference_lines(
        doc, id_to_var={},  # widget-stale not present
        instance_prefix="self.",
    )
    assert lines == []


def test_emit_field_lines_skips_global_target_outside_export():
    """Single-document export only populates ``_DOC_ID_TO_CLASS``
    with the chosen doc; globals pointing at OTHER docs become
    unresolvable and are silently skipped so the generated .py
    stays runnable.
    """
    doc = Document(name="Main")
    project = Project()
    project.object_references.append(ObjectReferenceEntry(
        id="g1", name="settings_dialog",
        target_type="Dialog", scope="global",
        target_id="dialog-doc-id",
    ))
    code_exporter._EXPORT_PROJECT = project
    code_exporter._DOC_ID_TO_CLASS = {}  # other doc absent
    lines = _emit_object_reference_lines(
        doc, id_to_var={}, instance_prefix="self.",
    )
    assert lines == []


def test_emit_field_lines_skips_unbound_global():
    doc = Document(name="Main")
    project = Project()
    project.object_references.append(ObjectReferenceEntry(
        id="g1", name="settings_dialog",
        target_type="Dialog", scope="global",
        target_id="",  # declared but not bound
    ))
    code_exporter._EXPORT_PROJECT = project
    code_exporter._DOC_ID_TO_CLASS = {"some-other-doc": "Some"}
    lines = _emit_object_reference_lines(
        doc, id_to_var={}, instance_prefix="self.",
    )
    assert lines == []
