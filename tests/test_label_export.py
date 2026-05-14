"""CTkLabel exports as the fork's native ``ctk.CTkLabel``.

The old editor-side ``CircleLabel`` override is gone — its two jobs
(full-circle layout, unified ``bind()`` event routing) are now
fork-native kwargs (``full_circle`` / ``unified_bind``, ctkmaker-core
>= 5.4.14), injected by the descriptor's ``export_kwarg_overrides``.
The Image descriptor also emits ``ctk.CTkLabel(...)`` but without
those kwargs — its text is empty (no squeeze) and it takes no user
``bind()`` handlers.
"""

from __future__ import annotations

import pytest

from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.io import code_exporter
from app.io.code_exporter import generate_code
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
def test_label_descriptor_is_native_ctk_label():
    desc = get_descriptor("CTkLabel")
    # CTkLabel is now a direct CTk wrapper — no inlined subclass.
    assert desc.is_ctk_class is True
    assert desc.ctk_class_name == "CTkLabel"


def test_image_descriptor_stays_on_ctk_label():
    desc = get_descriptor("Image")
    assert desc.is_ctk_class is True
    assert desc.ctk_class_name == "CTkLabel"


# ---------------------------------------------------------------------
# generate_code — end-to-end snapshot
# ---------------------------------------------------------------------
def test_default_label_emits_native_ctk_label_with_fork_kwargs():
    project = Project()
    _add_default_label(project, "title_lbl")
    source = generate_code(project)
    # Plain ``ctk.CTkLabel(...)``, keyed by the user-set var name.
    assert "self.title_lbl = ctk.CTkLabel(" in source
    # Fork-native composite-widget support is injected as kwargs.
    assert "full_circle=True" in source
    assert "unified_bind=True" in source
    # No inlined override class — that crutch is gone.
    assert "class CircleLabel" not in source


def test_label_with_invalid_name_falls_back_to_typed_default():
    project = Project()
    _add_default_label(project, "class")  # Python keyword
    source = generate_code(project)
    # Same fallback path as buttons — invalid name → ``<type>_<N>``.
    assert "self.label_1 = ctk.CTkLabel(" in source
    # The keyword name must NOT leak into the source.
    assert "self.class = " not in source


def test_image_emits_ctk_label_without_fork_composite_kwargs():
    """The Image descriptor exports as a plain ``ctk.CTkLabel(...)`` —
    it must NOT carry ``unified_bind`` / ``full_circle`` (image-only,
    no text squeeze, no user bind handlers).
    """
    project = Project()
    _add_default_image(project, "hero_img")
    source = generate_code(project)
    assert "self.hero_img = ctk.CTkLabel(" in source
    assert "unified_bind=True" not in source
    assert "full_circle=True" not in source
    assert "class CircleLabel" not in source


def test_label_and_image_coexist_correctly():
    """Mixed project: a real CTkLabel carries the fork composite
    kwargs, an Image stays a bare ``ctk.CTkLabel`` — both in one file.
    """
    project = Project()
    _add_default_label(project, "title_lbl")
    _add_default_image(project, "hero_img")
    source = generate_code(project)
    assert "self.title_lbl = ctk.CTkLabel(" in source
    assert "self.hero_img = ctk.CTkLabel(" in source
    # The composite kwargs appear exactly once — on the real label.
    assert source.count("unified_bind=True") == 1
    assert source.count("full_circle=True") == 1


def test_button_and_label_both_emit_plain_ctk_widgets():
    """A CTkButton + a CTkLabel in the same project both emit plain
    ``ctk.Ctk*(...)`` — neither inlines a CircleButton / CircleLabel
    override; full-circle support is fork-native for both.
    """
    project = Project()
    _add_default_label(project, "lbl")
    btn = WidgetNode(widget_type="CTkButton")
    btn.name = "btn"
    btn.properties = dict(get_descriptor("CTkButton").default_properties)
    project.active_document.root_widgets.append(btn)
    source = generate_code(project)
    assert "class CircleButton" not in source
    assert "class CircleLabel" not in source
    assert "self.btn = ctk.CTkButton(" in source
    assert "self.lbl = ctk.CTkLabel(" in source
