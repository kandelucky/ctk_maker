"""CTkLabel exports through the inlined ``CircleLabel`` class.

Every CTkLabel routes through ``CircleLabel`` — a CTkLabel override
that still carries the unified event router (``bind()`` dispatch).
Its old rounded-corner padx fix in ``_create_grid`` is now the fork's
native ``full_circle`` kwarg, but the class stays inlined until the
event router lands in the fork too. The Image descriptor stays on raw
``ctk.CTkLabel(...)`` because its text is empty — no squeeze to fix,
and Image widgets don't take user ``bind()`` handlers.
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


def test_button_emits_plain_ctkbutton_alongside_circlelabel():
    """A CTkButton + a CTkLabel in the same project: the button emits a
    plain ``ctk.CTkButton(...)`` (its full-circle layout fix is now the
    fork's native ``full_circle`` kwarg, no inlined class), while the
    label still routes through the inlined ``CircleLabel``.
    """
    project = Project()
    _add_default_label(project, "lbl")
    btn = WidgetNode(widget_type="CTkButton")
    btn.name = "btn"
    btn.properties = dict(get_descriptor("CTkButton").default_properties)
    project.active_document.root_widgets.append(btn)
    source = generate_code(project)
    assert "class CircleButton" not in source
    assert "self.btn = ctk.CTkButton(" in source
    assert "full_circle=True" in source
    assert source.count("class CircleLabel(ctk.CTkLabel):") == 1
    assert "self.lbl = CircleLabel(" in source


# ---------------------------------------------------------------------
# _circle_label_class_lines — helper sanity
# ---------------------------------------------------------------------
def test_circle_label_helper_returns_class_source():
    lines = _circle_label_class_lines()
    joined = "\n".join(lines)
    # The helper feeds inspect.getsource on the runtime class — the
    # class header + the constructor must both be present.
    assert "class CircleLabel(ctk.CTkLabel):" in joined
    assert "def __init__(self, *args, **kwargs):" in joined
    # The corner-radius fix is now the fork's native full_circle kwarg,
    # passed in __init__ — the old _create_grid override is gone.
    assert "def _create_grid(self):" not in joined
    assert 'kwargs.setdefault("full_circle", True)' in joined


def test_circle_label_helper_includes_unified_event_router():
    """v1.21.0 unified event routing layer — bind/configure overrides
    plus the internal helpers must inline. Catches accidental method
    renames and ``inspect.getsource`` regressions that would silently
    strip the router from exports.
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
