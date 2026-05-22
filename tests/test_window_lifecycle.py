"""Phase 2a — window lifecycle events (direct-binding model).

``on_setup`` / ``on_close`` are document-scoped handlers bound to the
user's own functions (``func(window)``). Covers the Document model
round-trip, the export emission, and the picker signature filter.
Pure-Python, no Tk. See docs/plans/script_optimization.md.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.core.document import Document
from app.io import code_exporter
from app.io.code_exporter import _emit_lifecycle_lines
from app.io.scripts import parse_module_functions
from app.widgets.event_registry import lifecycle_events


def _lib(script: str, method: str) -> dict:
    return {"kind": "library_call", "script": script, "method": method}


# --------------------------------------------------------------------
# Document model round-trip

def test_lifecycle_handlers_round_trip():
    doc = Document(name="Main")
    doc.lifecycle_handlers = {
        "lifecycle:on_setup": [_lib("helpers.py", "on_setup")],
        "lifecycle:on_close": [_lib("helpers.py", "on_close")],
    }
    restored = Document.from_dict(doc.to_dict())
    assert restored.lifecycle_handlers == doc.lifecycle_handlers


def test_lifecycle_handlers_absent_by_default():
    doc = Document(name="Main")
    assert doc.lifecycle_handlers == {}
    # Empty dict is not serialised — keeps pre-feature .ctkproj clean.
    assert "lifecycle_handlers" not in doc.to_dict()


def test_lifecycle_from_dict_drops_malformed():
    data = Document(name="Main").to_dict()
    data["lifecycle_handlers"] = {
        "lifecycle:on_setup": [_lib("helpers.py", "go"), "", {"no": "kind"}],
        123: [_lib("helpers.py", "x")],         # non-str key
        "lifecycle:on_close": "not-a-list",      # non-list value
    }
    doc = Document.from_dict(data)
    assert doc.lifecycle_handlers == {
        "lifecycle:on_setup": [_lib("helpers.py", "go")],
    }


# --------------------------------------------------------------------
# Export emission

def test_emit_on_setup_calls(monkeypatch):
    monkeypatch.setattr(code_exporter, "_EXPORT_PROJECT", None)
    doc = SimpleNamespace(
        attached_scripts=["helpers.py"],
        lifecycle_handlers={
            "lifecycle:on_setup": [_lib("helpers.py", "on_setup")],
        },
    )
    lines = _emit_lifecycle_lines(doc)
    assert [ln.strip() for ln in lines] == ["helpers.on_setup(self)"]


def test_emit_on_close_protocol(monkeypatch):
    monkeypatch.setattr(code_exporter, "_EXPORT_PROJECT", None)
    doc = SimpleNamespace(
        attached_scripts=["helpers.py"],
        lifecycle_handlers={
            "lifecycle:on_close": [_lib("helpers.py", "on_close")],
        },
    )
    lines = _emit_lifecycle_lines(doc)
    assert [ln.strip() for ln in lines] == [
        'self.protocol("WM_DELETE_WINDOW", lambda: helpers.on_close(self))',
    ]


def test_emit_on_close_fans_out(monkeypatch):
    monkeypatch.setattr(code_exporter, "_EXPORT_PROJECT", None)
    doc = SimpleNamespace(
        attached_scripts=["a.py", "b.py"],
        lifecycle_handlers={
            "lifecycle:on_close": [_lib("a.py", "f"), _lib("b.py", "g")],
        },
    )
    lines = _emit_lifecycle_lines(doc)
    assert [ln.strip() for ln in lines] == [
        'self.protocol("WM_DELETE_WINDOW", '
        'lambda: (a.f(self), b.g(self)))',
    ]


def test_emit_empty_lifecycle():
    assert _emit_lifecycle_lines(SimpleNamespace(lifecycle_handlers={})) == []
    assert _emit_lifecycle_lines(SimpleNamespace()) == []


# --------------------------------------------------------------------
# Registry + picker filter

def test_lifecycle_events_registered():
    keys = {e.key for e in lifecycle_events()}
    assert keys == {"lifecycle:on_setup", "lifecycle:on_close"}
    assert all(e.wiring_kind == "lifecycle" for e in lifecycle_events())


def test_lifecycle_picker_requires_window(tmp_path):
    script = tmp_path / "helpers.py"
    script.write_text(
        "def win(window): ...\n"
        "def argless(): ...\n"
        "def win_event(window, event): ...\n",
        encoding="utf-8",
    )
    fns = parse_module_functions(script, "lifecycle")
    assert "win" in fns
    assert "argless" not in fns       # window would be dropped
    assert "win_event" not in fns     # 2 required, only window passed
