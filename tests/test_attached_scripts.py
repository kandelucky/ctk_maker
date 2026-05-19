"""Library script attachments (v1.38).

Covers two surfaces of the "Library scripts as event targets" flow:

* ``Document.attached_scripts`` round-trip — page-folder-relative
  paths persist through ``to_dict`` / ``from_dict``; legacy projects
  load as empty list; non-string entries are filtered.
* Exporter ``library_call`` formatting — ``_format_library_call``
  and ``_library_script_module_name`` render a handler entry into
  the Python expression injected at the call site.
"""

from __future__ import annotations

from app.core.document import Document
from app.io.code_exporter import (
    _format_library_call,
    _library_script_module_name,
)


# ---- Document.attached_scripts round-trip --------------------------------

def test_attached_scripts_round_trip():
    doc = Document(name="Main")
    doc.attached_scripts = ["helpers.py", "services/auth.py"]

    restored = Document.from_dict(doc.to_dict())

    assert restored.attached_scripts == ["helpers.py", "services/auth.py"]


def test_to_dict_omits_attached_scripts_when_empty():
    doc = Document(name="Main")

    payload = doc.to_dict()

    assert "attached_scripts" not in payload


def test_from_dict_legacy_payload_loads_empty_attached_scripts():
    # Pre-v1.38 ``.ctkproj`` files have no ``attached_scripts`` key.
    payload = {"id": "doc-1", "name": "Main", "width": 800, "height": 600}

    doc = Document.from_dict(payload)

    assert doc.attached_scripts == []


def test_from_dict_filters_non_string_attached_script_entries():
    # Defensive: hand-edited JSON / future schema drift shouldn't
    # poison the live model.
    payload = {
        "id": "doc-1", "name": "Main", "width": 800, "height": 600,
        "attached_scripts": ["good.py", "", None, 123, "also_good.py"],
    }

    doc = Document.from_dict(payload)

    assert doc.attached_scripts == ["good.py", "also_good.py"]


# ---- _library_script_module_name -----------------------------------------

def test_library_module_name_strips_py_suffix():
    assert _library_script_module_name("helpers.py") == "helpers"


def test_library_module_name_takes_basename_of_nested_path():
    assert _library_script_module_name("services/auth.py") == "auth"


# ---- _format_library_call ------------------------------------------------

def test_format_library_call_no_args():
    entry = {
        "kind": "library_call",
        "script": "helpers.py",
        "method": "save_log",
        "args": [],
    }

    assert _format_library_call(entry) == "helpers.save_log()"


def test_format_library_call_typed_args():
    entry = {
        "kind": "library_call",
        "script": "services/auth.py",
        "method": "login",
        "args": [
            {"name": "user", "type": "str", "value": "alice"},
            {"name": "retries", "type": "int", "value": 3},
            {"name": "remember", "type": "bool", "value": True},
        ],
    }

    assert _format_library_call(entry) == (
        "auth.login('alice', 3, True)"
    )


def test_format_library_call_missing_args_key_treated_as_empty():
    entry = {
        "kind": "library_call",
        "script": "helpers.py",
        "method": "ping",
    }

    assert _format_library_call(entry) == "helpers.ping()"
