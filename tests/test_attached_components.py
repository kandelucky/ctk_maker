"""Storage tests for the CTkScript attachment model — components
attached to a widget or to the window, plus the ``script_call`` handler
entry kind. Pure-Python, no Tk. See docs/plans/script_optimization.md.
"""
from __future__ import annotations

from app.core.document import Document
from app.core.widget_node import WidgetNode


def _comp(script: str, cls: str) -> dict:
    return {"script": script, "class": cls}


# -- WidgetNode attachment --------------------------------------------

def test_widget_components_round_trip():
    node = WidgetNode("CTkButton")
    node.attached_components = [_comp("counter.py", "ClickCounter")]
    restored = WidgetNode.from_dict(node.to_dict())
    assert restored.attached_components == [_comp("counter.py", "ClickCounter")]


def test_widget_components_multiple():
    node = WidgetNode("CTkButton")
    node.attached_components = [
        _comp("counter.py", "ClickCounter"),
        _comp("fx.py", "HoverGlow"),
    ]
    restored = WidgetNode.from_dict(node.to_dict())
    assert restored.attached_components == node.attached_components


def test_widget_components_absent_by_default():
    node = WidgetNode("CTkButton")
    assert node.attached_components == []
    assert "attached_components" not in node.to_dict()


def test_widget_components_drop_malformed():
    data = WidgetNode("CTkButton").to_dict()
    data["attached_components"] = [
        _comp("counter.py", "ClickCounter"),
        {"script": "x.py"},          # missing class
        {"class": "Y"},              # missing script
        {"script": "", "class": "Z"},  # empty script
        "nope",                       # not a dict
    ]
    node = WidgetNode.from_dict(data)
    assert node.attached_components == [_comp("counter.py", "ClickCounter")]


# -- script_call handler entry ----------------------------------------

def test_script_call_handler_round_trips():
    node = WidgetNode("CTkButton")
    node.handlers = {
        "command": [
            {"kind": "script_call", "class": "ClickCounter", "method": "bump"},
        ],
    }
    restored = WidgetNode.from_dict(node.to_dict())
    assert restored.handlers == node.handlers


# -- Document (window) attachment -------------------------------------

def test_window_components_round_trip():
    doc = Document(name="Main")
    doc.attached_components = [_comp("login_form.py", "LoginForm")]
    restored = Document.from_dict(doc.to_dict())
    assert restored.attached_components == [_comp("login_form.py", "LoginForm")]


def test_window_components_absent_by_default():
    doc = Document(name="Main")
    assert doc.attached_components == []
    assert "attached_components" not in doc.to_dict()


def test_window_components_drop_malformed():
    data = Document(name="Main").to_dict()
    data["attached_components"] = [
        _comp("login_form.py", "LoginForm"),
        {"script": "x.py"},
        42,
    ]
    doc = Document.from_dict(data)
    assert doc.attached_components == [_comp("login_form.py", "LoginForm")]


# -- var_bindings (declared variable fields, Q1=B) --------------------

def test_widget_var_bindings_round_trip():
    node = WidgetNode("CTkButton")
    node.attached_components = [
        {"script": "counter.py", "class": "ClickCounter",
         "var_bindings": {"score": "uuid-1", "title": "uuid-2"}},
    ]
    restored = WidgetNode.from_dict(node.to_dict())
    assert restored.attached_components == node.attached_components


def test_window_var_bindings_round_trip():
    doc = Document(name="Main")
    doc.attached_components = [
        {"script": "form.py", "class": "LoginForm",
         "var_bindings": {"user": "uuid-7"}},
    ]
    restored = Document.from_dict(doc.to_dict())
    assert restored.attached_components == doc.attached_components


def test_var_bindings_empty_key_omitted():
    data = WidgetNode("CTkButton").to_dict()
    data["attached_components"] = [
        {"script": "c.py", "class": "C", "var_bindings": {}},
    ]
    node = WidgetNode.from_dict(data)
    # Empty mapping → key dropped; the component itself is still kept.
    assert node.attached_components == [{"script": "c.py", "class": "C"}]


def test_var_bindings_drop_malformed_pairs():
    data = WidgetNode("CTkButton").to_dict()
    data["attached_components"] = [
        {"script": "c.py", "class": "C", "var_bindings": {
            "ok": "uuid-9",
            "": "uuid-x",   # empty field name
            "bad": "",       # empty uuid
            "n": 123,        # non-str uuid
        }},
    ]
    node = WidgetNode.from_dict(data)
    assert node.attached_components == [
        {"script": "c.py", "class": "C", "var_bindings": {"ok": "uuid-9"}},
    ]


def test_var_bindings_non_dict_ignored():
    data = WidgetNode("CTkButton").to_dict()
    data["attached_components"] = [
        {"script": "c.py", "class": "C", "var_bindings": "nope"},
    ]
    node = WidgetNode.from_dict(data)
    assert node.attached_components == [{"script": "c.py", "class": "C"}]
