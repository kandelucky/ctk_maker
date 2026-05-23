"""CTkScript model — export-engine helpers (pure, no Tk).

Covers component collection + var mapping, scope resolution, the
emitted init / post / close lines, the script_call formatter, and the
inlinable base source. See docs/plans/script_optimization.md.
"""
from __future__ import annotations

import ast
from types import SimpleNamespace

from app.io.code_exporter import (
    _collect_doc_components,
    _component_module_path,
    _ctkscript_base_source,
    _emit_component_close_lines,
    _emit_component_init_lines,
    _emit_component_post_lines,
    _field_value_literal,
    _format_script_call,
    _resolve_component_var,
)


def test_component_module_path():
    assert _component_module_path("counter.py") == "counter"
    assert _component_module_path("sub/auth.py") == "sub.auth"
    assert _component_module_path("sub\\auth.py") == "sub.auth"
    assert _component_module_path("") == ""


def _node(node_id, comps=None, children=None):
    return SimpleNamespace(
        id=node_id,
        attached_components=comps or [],
        children=children or [],
    )


def _doc(comps=None, roots=None):
    return SimpleNamespace(
        attached_components=comps or [],
        root_widgets=roots or [],
    )


def _comp(script, cls):
    return {"script": script, "class": cls}


# -- base source ------------------------------------------------------

def test_base_source_is_valid_classless_of_imports():
    src = _ctkscript_base_source()
    assert "class CTkScript" in src
    tree = ast.parse(src)  # parses standalone
    assert not [
        n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))
    ]


# -- collection -------------------------------------------------------

def test_collect_window_first_then_widgets_dfs():
    btn = _node("b1", [_comp("counter.py", "ClickCounter")])
    d = _doc([_comp("login.py", "LoginForm")], [btn])
    recs = _collect_doc_components(d, {"b1": "my_button"})
    assert recs == [
        {
            "var": "_script_0", "scope": "window", "target": "self",
            "script": "login.py", "class": "LoginForm", "owner_id": None,
            "var_bindings": {}, "field_values": {}, "fields": [],
        },
        {
            "var": "_script_1", "scope": "widget", "target": "self.my_button",
            "script": "counter.py", "class": "ClickCounter", "owner_id": "b1",
            "var_bindings": {}, "field_values": {}, "fields": [],
        },
    ]


def test_collect_nested_dfs_order():
    child = _node("c1", [_comp("a.py", "A")])
    parent = _node("p1", [_comp("b.py", "B")], [child])
    d = _doc([], [parent])
    recs = _collect_doc_components(d, {"p1": "p", "c1": "c"})
    assert [r["class"] for r in recs] == ["B", "A"]  # parent before child
    assert [r["var"] for r in recs] == ["_script_0", "_script_1"]


# -- scope resolution -------------------------------------------------

def test_resolve_widget_owned_wins_then_window():
    recs = _collect_doc_components(
        _doc([_comp("login.py", "LoginForm")],
             [_node("b1", [_comp("counter.py", "ClickCounter")])]),
        {"b1": "my_button"},
    )
    assert _resolve_component_var(recs, "b1", "ClickCounter") == "_script_1"
    assert _resolve_component_var(recs, "b1", "LoginForm") == "_script_0"
    assert _resolve_component_var(recs, "b2", "ClickCounter") is None
    assert _resolve_component_var(recs, "b1", "Nope") is None


# -- emitted lines ----------------------------------------------------

def test_init_lines():
    recs = _collect_doc_components(
        _doc([_comp("login.py", "LoginForm")],
             [_node("b1", [_comp("counter.py", "ClickCounter")])]),
        {"b1": "my_button"},
    )
    assert [ln.strip() for ln in _emit_component_init_lines(recs)] == [
        "self._script_0 = LoginForm()",
        "self._script_1 = ClickCounter()",
    ]


def test_post_lines_inject_scope_then_on_start():
    recs = _collect_doc_components(
        _doc([_comp("login.py", "LoginForm")],
             [_node("b1", [_comp("counter.py", "ClickCounter")])]),
        {"b1": "my_button"},
    )
    assert [ln.strip() for ln in _emit_component_post_lines(recs)] == [
        "self._script_0.window = self",
        "self._script_1.widget = self.my_button",
        "self._script_0.on_start()",
        "self._script_1.on_start()",
    ]


def test_post_lines_inject_bound_variables(monkeypatch):
    recs = _collect_doc_components(
        _doc([{"script": "f.py", "class": "Form",
               "var_bindings": {"user": "uuid-1"}}], []),
        {},
    )
    recs[0]["fields"] = [("user", "str")]  # set directly (no real script)
    monkeypatch.setattr(
        "app.io.code_exporter._VAR_ID_TO_ATTR", {"uuid-1": "self.var_user"},
    )
    # var injection lands between scope inject and on_start.
    assert [ln.strip() for ln in _emit_component_post_lines(recs)] == [
        "self._script_0.window = self",
        "self._script_0.user = self.var_user",
        "self._script_0.on_start()",
    ]


def test_post_lines_stale_binding_falls_back_to_default(monkeypatch):
    recs = _collect_doc_components(
        _doc([{"script": "f.py", "class": "Form",
               "var_bindings": {"user": "deleted-uuid"}}], []),
        {},
    )
    recs[0]["fields"] = [("user", "str")]
    monkeypatch.setattr("app.io.code_exporter._VAR_ID_TO_ATTR", {})
    # Stale binding (variable deleted) → field still set, fresh default.
    assert [ln.strip() for ln in _emit_component_post_lines(recs)] == [
        "self._script_0.window = self",
        "self._script_0.user = tk.StringVar()",
        "self._script_0.on_start()",
    ]


def test_post_lines_inline_value_and_default():
    recs = _collect_doc_components(
        _doc([{"script": "f.py", "class": "Form",
               "field_values": {"count": "5", "name": "Hi"}}], []),
        {},
    )
    recs[0]["fields"] = [("count", "int"), ("name", "str"), ("flag", "bool")]
    # inline → typed value; unset field → type default.
    assert [ln.strip() for ln in _emit_component_post_lines(recs)] == [
        "self._script_0.window = self",
        "self._script_0.count = tk.IntVar(value=5)",
        "self._script_0.name = tk.StringVar(value='Hi')",
        "self._script_0.flag = tk.BooleanVar()",
        "self._script_0.on_start()",
    ]


def test_field_value_literal_coercion():
    assert _field_value_literal("int", "5") == "5"
    assert _field_value_literal("int", "x") == "0"      # malformed → 0
    assert _field_value_literal("float", "1.5") == "1.5"
    assert _field_value_literal("bool", "true") == "True"
    assert _field_value_literal("bool", "no") == "False"
    assert _field_value_literal("str", "hi") == "'hi'"
    assert _field_value_literal("color", "#abc") == "'#abc'"


def test_close_lines():
    recs = _collect_doc_components(
        _doc([_comp("login.py", "LoginForm")], []), {},
    )
    assert [ln.strip() for ln in _emit_component_close_lines(recs)] == [
        'self.protocol("WM_DELETE_WINDOW", '
        'lambda: (self._script_0.on_close(), self.destroy()))',
    ]
    assert _emit_component_close_lines([]) == []


# -- script_call formatting -------------------------------------------

def test_format_script_call():
    recs = _collect_doc_components(
        _doc([], [_node("b1", [_comp("counter.py", "ClickCounter")])]),
        {"b1": "my_button"},
    )
    assert _format_script_call(
        {"class": "ClickCounter", "method": "bump"}, recs, "b1",
    ) == "self._script_0.bump"
    assert _format_script_call(
        {"class": "Nope", "method": "x"}, recs, "b1",
    ) is None
    assert _format_script_call(
        {"class": "ClickCounter", "method": ""}, recs, "b1",
    ) is None
