"""CTkLabel exports through the inlined ``CircleLabel`` class.

Symmetric to ``test_var_name_threading``'s CircleButton coverage. Every
CTkLabel routes through ``CircleLabel`` (a CTkLabel override that
zeroes the rounded-corner padx in ``_create_grid``) so full-circle /
pill labels with text stop overflowing their nominal frame size. The
Image descriptor stays on raw ``ctk.CTkLabel(...)`` because its text
is empty — no horizontal squeeze to fix.
"""

from __future__ import annotations

import pytest

from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.io import code_exporter
from app.io.code_exporter import (
    _circle_label_class_lines,
    generate_code,
)
from app.widgets.registry import get_descriptor


@pytest.fixture(autouse=True)
def _reset_exporter_state():
    code_exporter._VAR_NAME_FALLBACKS = []
    code_exporter._NAME_MAP_CACHE = {}
    yield
    code_exporter._VAR_NAME_FALLBACKS = []
    code_exporter._NAME_MAP_CACHE = {}


def _add_default_label(project: Project, name: str = "lbl") -> WidgetNode:
    desc = get_descriptor("CTkLabel")
    node = WidgetNode(widget_type="CTkLabel")
    node.name = name
    node.properties = dict(desc.default_properties)
    project.active_document.root_widgets.append(node)
    return node


def _add_default_image(project: Project, name: str = "img") -> WidgetNode:
    desc = get_descriptor("Image")
    node = WidgetNode(widget_type="Image")
    node.name = name
    node.properties = dict(desc.default_properties)
    project.active_document.root_widgets.append(node)
    return node


# ---------------------------------------------------------------------
# Descriptor flags
# ---------------------------------------------------------------------
def test_label_descriptor_routes_to_circle_label():
    desc = get_descriptor("CTkLabel")
    # Both flags must agree — the exporter checks ``is_ctk_class`` to
    # decide between bare ``Foo(...)`` and ``ctk.Foo(...)``, and reads
    # ``ctk_class_name`` for the actual class to emit.
    assert desc.is_ctk_class is False
    assert desc.ctk_class_name == "CircleLabel"


def test_image_descriptor_stays_on_ctk_label():
    desc = get_descriptor("Image")
    # Image is image-only (text=""), no horizontal squeeze possible —
    # it must keep emitting as ``ctk.CTkLabel(...)`` and NOT route
    # through CircleLabel.
    assert desc.is_ctk_class is True
    assert desc.ctk_class_name == "CTkLabel"


# ---------------------------------------------------------------------
# generate_code — end-to-end snapshot
# ---------------------------------------------------------------------
def test_default_label_emits_circle_label_constructor():
    project = Project()
    _add_default_label(project, "title_lbl")
    source = generate_code(project)
    # Bare ``CircleLabel(...)`` (no ``ctk.`` prefix), keyed by the
    # user-set var name.
    assert "self.title_lbl = CircleLabel(" in source
    # The runtime class must be inlined — generated files have no
    # import path for ``CircleLabel``.
    assert "class CircleLabel(ctk.CTkLabel):" in source


def test_label_with_invalid_name_falls_back_to_typed_default():
    project = Project()
    node = _add_default_label(project, "class")  # Python keyword
    source = generate_code(project)
    # Same fallback path as buttons — invalid name → ``<type>_<N>``.
    assert "self.label_1 = CircleLabel(" in source
    # The keyword name must NOT leak into the source.
    assert "self.class = " not in source


def test_image_only_project_does_not_inline_circle_label():
    """Image descriptor exports as ``ctk.CTkLabel(...)``. A project
    with only Image widgets must NOT inline the CircleLabel class —
    the helper would be dead code in the generated file.
    """
    project = Project()
    _add_default_image(project, "hero_img")
    source = generate_code(project)
    # Image keeps the ``ctk.`` prefix.
    assert "self.hero_img = ctk.CTkLabel(" in source
    # And the runtime override is NOT inlined.
    assert "class CircleLabel(" not in source


def test_label_and_image_coexist_correctly():
    """Mixed project: real CTkLabel routes through CircleLabel, Image
    routes through ctk.CTkLabel — both in the same file.
    """
    project = Project()
    _add_default_label(project, "title_lbl")
    _add_default_image(project, "hero_img")
    source = generate_code(project)
    assert "self.title_lbl = CircleLabel(" in source
    assert "self.hero_img = ctk.CTkLabel(" in source
    # The CircleLabel class must be inlined exactly once.
    assert source.count("class CircleLabel(ctk.CTkLabel):") == 1


def test_button_and_label_inline_both_runtime_classes():
    """Both CircleButton and CircleLabel inline cleanly when their
    respective widget types appear together. Each class definition
    emitted once.
    """
    project = Project()
    _add_default_label(project, "lbl")
    btn = WidgetNode(widget_type="CTkButton")
    btn.name = "btn"
    btn.properties = dict(get_descriptor("CTkButton").default_properties)
    project.active_document.root_widgets.append(btn)
    source = generate_code(project)
    assert source.count("class CircleButton(ctk.CTkButton):") == 1
    assert source.count("class CircleLabel(ctk.CTkLabel):") == 1
    assert "self.btn = CircleButton(" in source
    assert "self.lbl = CircleLabel(" in source


# ---------------------------------------------------------------------
# _circle_label_class_lines — helper sanity
# ---------------------------------------------------------------------
def test_circle_label_helper_returns_class_source():
    lines = _circle_label_class_lines()
    joined = "\n".join(lines)
    # The helper feeds inspect.getsource on the runtime class — the
    # class header + the override method must both be present.
    assert "class CircleLabel(ctk.CTkLabel):" in joined
    assert "def _create_grid(self):" in joined


def test_circle_label_helper_includes_unified_event_router():
    """v1.21.0 unified event routing layer — bind/configure overrides
    plus the internal helpers must inline alongside the corner-radius
    fix. Catches accidental method renames and ``inspect.getsource``
    regressions that would silently strip the router from exports.
    """
    joined = "\n".join(_circle_label_class_lines())
    # Public overrides
    assert "def bind(self" in joined
    assert "def configure(self" in joined
    # Internal dispatch helpers
    assert "def _on_internal_enter" in joined
    assert "def _check_truly_left" in joined
    assert "def _bind_outer_only" in joined
    assert "def _dedup_dual_bind" in joined
