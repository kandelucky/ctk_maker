"""User-set widget Names thread through to exported var names.

Pre-1.9.8 the exporter ignored ``WidgetNode.name`` entirely — every
widget got ``<type>_<N>`` regardless of what the user typed in the
Properties panel. Behavior files calling ``self.window.submit_btn``
crashed with ``AttributeError`` because the actual attribute was
``self.window.button_1``.

Covers ``_resolve_var_names`` (the single resolver both the live
emit walk and the Phase 3 Behavior Field replay use), the
fallback log surfaced via ``get_var_name_fallbacks``, and an
end-to-end ``generate_code`` snapshot.
"""

from __future__ import annotations

import pytest

from app.core.document import Document
from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.io import code_exporter
from app.io.code_exporter import (
    _resolve_var_names,
    generate_code,
    get_var_name_fallbacks,
)


@pytest.fixture(autouse=True)
def _reset_exporter_state():
    """Module-level state in ``code_exporter`` persists between
    ``_resolve_var_names`` calls so launchers can read the warnings
    after ``generate_code`` returns. Tests need a clean slate per
    case — flush the cache + fallback log before each.
    """
    code_exporter._VAR_NAME_FALLBACKS = []
    code_exporter._NAME_MAP_CACHE = {}
    yield
    code_exporter._VAR_NAME_FALLBACKS = []
    code_exporter._NAME_MAP_CACHE = {}


def _make_doc(name: str = "Window") -> Document:
    """Document factory with a stable id so tests can compare maps
    across the resolver's per-doc memoisation cache.
    """
    doc = Document(
        name=name,
        width=400,
        height=300,
        is_toplevel=False,
    )
    return doc


def _node(widget_type: str, name: str = "") -> WidgetNode:
    n = WidgetNode(widget_type=widget_type)
    n.name = name
    return n


# ---------------------------------------------------------------------
# _resolve_var_names — naming priority
# ---------------------------------------------------------------------
def test_user_name_used_when_valid_identifier():
    doc = _make_doc()
    btn = _node("CTkButton", "submit_btn")
    doc.root_widgets.append(btn)
    id_map = _resolve_var_names(doc)
    assert id_map[btn.id] == "submit_btn"
    assert get_var_name_fallbacks() == []


def test_empty_name_falls_back_to_type_counter_silently():
    doc = _make_doc()
    a = _node("CTkButton")
    b = _node("CTkButton")
    doc.root_widgets.extend([a, b])
    id_map = _resolve_var_names(doc)
    assert id_map[a.id] == "button_1"
    assert id_map[b.id] == "button_2"
    # Empty name → no warning.
    assert get_var_name_fallbacks() == []


def test_mixed_named_and_unnamed_keep_independent_counters():
    doc = _make_doc()
    btn = _node("CTkButton", "submit_btn")
    label = _node("CTkLabel")
    other = _node("CTkButton")
    doc.root_widgets.extend([btn, label, other])
    id_map = _resolve_var_names(doc)
    assert id_map[btn.id] == "submit_btn"
    assert id_map[label.id] == "label_1"
    # Counter sees one ``CTkButton`` so far → next is button_1, not _2.
    assert id_map[other.id] == "button_1"


def test_user_name_collides_with_type_counter_bumps_counter():
    """User explicitly named a button ``button_1``; an unnamed
    sibling can't quietly land on the same string. The counter
    bumps forward instead of silently overwriting.
    """
    doc = _make_doc()
    pinned = _node("CTkButton", "button_1")
    sibling = _node("CTkButton")
    doc.root_widgets.extend([pinned, sibling])
    id_map = _resolve_var_names(doc)
    assert id_map[pinned.id] == "button_1"
    assert id_map[sibling.id] == "button_2"


# ---------------------------------------------------------------------
# Duplicates — first wins, subsequent get _2 / _3
# ---------------------------------------------------------------------
def test_duplicate_user_name_suffixes_second():
    doc = _make_doc("Login")
    a = _node("CTkButton", "submit_btn")
    b = _node("CTkButton", "submit_btn")
    doc.root_widgets.extend([a, b])
    id_map = _resolve_var_names(doc)
    assert id_map[a.id] == "submit_btn"
    assert id_map[b.id] == "submit_btn_2"
    fallbacks = get_var_name_fallbacks()
    assert fallbacks == [("Login", "submit_btn", "submit_btn_2", "duplicate")]


def test_three_duplicates_run_to_3():
    doc = _make_doc()
    a = _node("CTkButton", "x")
    b = _node("CTkButton", "x")
    c = _node("CTkButton", "x")
    doc.root_widgets.extend([a, b, c])
    id_map = _resolve_var_names(doc)
    assert [id_map[n.id] for n in (a, b, c)] == ["x", "x_2", "x_3"]


# ---------------------------------------------------------------------
# Invalid / reserved names → fallback + warning
# ---------------------------------------------------------------------
def test_python_keyword_falls_back_with_warning():
    doc = _make_doc("MyWin")
    btn = _node("CTkButton", "class")
    doc.root_widgets.append(btn)
    id_map = _resolve_var_names(doc)
    assert id_map[btn.id] == "button_1"
    fallbacks = get_var_name_fallbacks()
    assert fallbacks == [("MyWin", "class", "button_1", "Python keyword")]


def test_invalid_identifier_falls_back_with_warning():
    doc = _make_doc("MyWin")
    btn = _node("CTkButton", "submit btn")
    doc.root_widgets.append(btn)
    id_map = _resolve_var_names(doc)
    assert id_map[btn.id] == "button_1"
    fallbacks = get_var_name_fallbacks()
    assert len(fallbacks) == 1
    assert fallbacks[0][1] == "submit btn"
    assert fallbacks[0][3] == "not a valid Python identifier"


def test_leading_digit_name_rejected():
    doc = _make_doc()
    btn = _node("CTkButton", "1submit")
    doc.root_widgets.append(btn)
    id_map = _resolve_var_names(doc)
    assert id_map[btn.id] == "button_1"
    fallbacks = get_var_name_fallbacks()
    assert fallbacks[0][3] == "not a valid Python identifier"


def test_reserved_name_behavior_falls_back():
    doc = _make_doc()
    btn = _node("CTkButton", "_behavior")
    doc.root_widgets.append(btn)
    id_map = _resolve_var_names(doc)
    assert id_map[btn.id] == "button_1"
    fallbacks = get_var_name_fallbacks()
    assert fallbacks[0][3] == "reserved by exported code"


def test_reserved_name_build_ui_falls_back():
    doc = _make_doc()
    btn = _node("CTkButton", "_build_ui")
    doc.root_widgets.append(btn)
    id_map = _resolve_var_names(doc)
    assert id_map[btn.id] == "button_1"


def test_inherited_ctk_method_names_fall_back():
    """Names that shadow Tk root / CTk inherited methods (``title``,
    ``geometry``, ``mainloop``, ``destroy``, ``configure``,
    ``protocol``, ``after``, ``bind``, …) crash anything that
    touches the window — CTkScrollableDropdown calling
    ``root.title()``, CTk's own appearance / scaling internals,
    even ``__init__``'s ``self.geometry(...)``. Validation pulls
    the list dynamically from ``dir(ctk.CTk) ∪ dir(ctk.CTkToplevel)``
    so we stay in sync as CTk evolves.
    """
    doc = _make_doc()
    forbidden = [
        "title", "geometry", "mainloop", "destroy",
        "configure", "protocol", "after", "bind",
    ]
    for name in forbidden:
        # Each gets its own widget — the resolver shares state per
        # doc, so reuse would let the first non-rejection mask
        # later ones.
        n = _node("CTkButton", name)
        doc.root_widgets.append(n)
    id_map = _resolve_var_names(doc)
    fallbacks = get_var_name_fallbacks()
    intents_rejected = {row[1] for row in fallbacks}
    for name in forbidden:
        assert name in intents_rejected, (
            f"expected '{name}' to be rejected as inherited"
        )
    # Every fallback should be a counter-shape (button_N), not the
    # original name.
    for n in doc.root_widgets:
        assert id_map[n.id].startswith("button_")


# ---------------------------------------------------------------------
# Memoisation cache
# ---------------------------------------------------------------------
def test_resolver_memoised_does_not_double_log_fallbacks():
    doc = _make_doc("Login")
    a = _node("CTkButton", "submit_btn")
    b = _node("CTkButton", "submit_btn")
    doc.root_widgets.extend([a, b])
    # First call records the duplicate fallback once.
    _resolve_var_names(doc)
    # Second call (Phase 3 replay path) hits the cache — same map,
    # no extra log entries.
    map_again = _resolve_var_names(doc)
    assert map_again[a.id] == "submit_btn"
    assert map_again[b.id] == "submit_btn_2"
    fallbacks = get_var_name_fallbacks()
    assert len(fallbacks) == 1


# ---------------------------------------------------------------------
# Nested children — DFS order preserved
# ---------------------------------------------------------------------
def test_nested_children_walk_dfs_order():
    doc = _make_doc()
    frame = _node("CTkFrame", "main_frame")
    child = _node("CTkButton", "ok_btn")
    grandchild = _node("CTkLabel")
    frame.children.append(child)
    child.children.append(grandchild)
    doc.root_widgets.append(frame)
    id_map = _resolve_var_names(doc)
    assert id_map[frame.id] == "main_frame"
    assert id_map[child.id] == "ok_btn"
    assert id_map[grandchild.id] == "label_1"


# ---------------------------------------------------------------------
# End-to-end: exported source contains user-set name
# ---------------------------------------------------------------------
def test_generate_code_emits_user_set_var_name():
    project = Project()
    doc = project.active_document
    btn = _node("CTkButton", "submit_btn")
    btn.properties = {
        "x": 10, "y": 10, "width": 100, "height": 32,
        "text": "Submit",
    }
    doc.root_widgets.append(btn)
    source = generate_code(project)
    # Every CTkButton exports as a plain ``ctk.CTkButton(...)`` with the
    # fork's native ``full_circle=True`` — the old inlined CircleButton
    # override is gone.
    assert "self.submit_btn = ctk.CTkButton(" in source
    # Legacy-shape attribute name must NOT appear when the user set
    # an explicit name — the whole point of the fix.
    assert "self.button_1 = ctk.CTkButton(" not in source


def test_generate_code_falls_back_when_name_invalid():
    project = Project()
    doc = project.active_document
    btn = _node("CTkButton", "class")  # Python keyword
    btn.properties = {
        "x": 10, "y": 10, "width": 100, "height": 32, "text": "X",
    }
    doc.root_widgets.append(btn)
    source = generate_code(project)
    # Every CTkButton exports as a plain ``ctk.CTkButton(...)``.
    assert "self.button_1 = ctk.CTkButton(" in source
    fallbacks = get_var_name_fallbacks()
    assert any(
        intent == "class" and reason == "Python keyword"
        for _, intent, _, reason in fallbacks
    )
