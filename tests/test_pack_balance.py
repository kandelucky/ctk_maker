"""v1.10.2 flex-shrink — hbox/vbox auto-shrink with content_min floor.

Pre-1.10.2: dropping more children into an hbox container than its
configured width could hold left the latest siblings clipped off the
right edge — the existing ``_apply_grow_equal_split`` only triggered
on layout-type swaps, not on fresh add/remove. This module covers:

  - ``content_min_axis``: per-widget content-derived min size
  - exporter emission: ``_ctkmaker_min`` / ``_ctkmaker_fixed`` attrs
    on every pack child + a ``<Configure>`` bind on the container
  - ``ctk.balance_pack(...)`` call: emitted only when an hbox/vbox
    container actually exists in the export scope. The helper body
    lives in ctkmaker-core 5.4.17 (``customtkinter.bindings``); the
    exporter only emits the call.
"""
from __future__ import annotations

import pytest

from app.core.document import Document
from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.io import code_exporter
from app.io.code_exporter import (
    _project_needs_pack_balance,
    generate_code,
)
from app.widgets.content_min import content_min_axis
from app.widgets.registry import get_descriptor


@pytest.fixture(autouse=True)
def _reset_exporter_state():
    code_exporter._VAR_NAME_FALLBACKS = []
    code_exporter._NAME_MAP_CACHE = {}
    yield
    code_exporter._VAR_NAME_FALLBACKS = []
    code_exporter._NAME_MAP_CACHE = {}


def _make_button(text="Hi", **extra):
    descriptor = get_descriptor("CTkButton")
    props = dict(descriptor.default_properties)
    props["text"] = text
    props.update(extra)
    return WidgetNode(widget_type="CTkButton", properties=props)


# ---------------------------------------------------------------------
# content_min_axis — per-widget content floor
# ---------------------------------------------------------------------
def test_content_min_button_has_floor():
    btn = _make_button(text="X")
    # CTkButton's chrome floor is 32 — short text never goes below that.
    assert content_min_axis(btn, "width") >= 32


def test_content_min_button_grows_with_text_length():
    short = _make_button(text="OK")
    longer = _make_button(text="Submit application form")
    # Longer text → larger min (font.measure may return 0 if no Tk
    # root, in which case we still get the chrome floor; check
    # monotonicity which holds either way).
    assert content_min_axis(longer, "width") >= content_min_axis(short, "width")


def test_content_min_invalid_axis_returns_zero():
    btn = _make_button()
    assert content_min_axis(btn, "depth") == 0


def test_content_min_unknown_widget_uses_default():
    node = WidgetNode(widget_type="WhoKnows", properties={"text": "X"})
    # Default chrome floor is 20.
    assert content_min_axis(node, "width") >= 20
    assert content_min_axis(node, "height") >= 20


def test_content_min_oriented_slider_long_axis():
    # Horizontal slider — long axis is width, cross is height.
    node = WidgetNode(
        widget_type="CTkSlider",
        properties={"orientation": "horizontal"},
    )
    assert content_min_axis(node, "width") == 40
    assert content_min_axis(node, "height") == 16
    # Vertical → axes swap.
    node.properties["orientation"] = "vertical"
    assert content_min_axis(node, "width") == 16
    assert content_min_axis(node, "height") == 40


# ---------------------------------------------------------------------
# _project_needs_pack_balance — emission gate
# ---------------------------------------------------------------------
def _make_project_with_doc(doc_layout="place", child_count=0):
    project = Project()
    doc = Document(name="MainWindow")
    doc.window_properties["width"] = 400
    doc.window_properties["height"] = 300
    doc.window_properties["layout_type"] = doc_layout
    project.documents = [doc]
    project.active_document_id = doc.id

    if doc_layout in ("vbox", "hbox"):
        # Add buttons directly to window root.
        for i in range(child_count):
            btn = _make_button(text=f"Btn{i}")
            project.add_widget(btn, document_id=doc.id)
    return project, doc


def test_pack_balance_skipped_for_pure_place_project():
    project, doc = _make_project_with_doc(doc_layout="place", child_count=0)
    code = generate_code(project)
    assert "ctk.balance_pack" not in code


def test_pack_balance_emitted_for_hbox_window():
    project, doc = _make_project_with_doc(doc_layout="hbox", child_count=2)
    code = generate_code(project)
    # Helper body lives in ctkmaker-core (customtkinter.bindings); the
    # exporter just wires the bind + call to the fork API.
    assert "def _ctkmaker_balance_pack" not in code  # no inline helper
    assert 'self.bind("<Configure>"' in code
    assert "ctk.balance_pack(self," in code


def test_pack_balance_emitted_for_nested_hbox_frame():
    project = Project()
    doc = Document(name="MainWindow")
    doc.window_properties["width"] = 600
    doc.window_properties["height"] = 400
    project.documents = [doc]
    project.active_document_id = doc.id
    # Nested Frame in hbox layout with 3 buttons.
    frame_desc = get_descriptor("CTkFrame")
    frame_props = dict(frame_desc.default_properties)
    frame_props["layout_type"] = "hbox"
    frame_props["width"] = 400
    frame = WidgetNode(widget_type="CTkFrame", properties=frame_props)
    project.add_widget(frame, document_id=doc.id)
    for i in range(3):
        btn = _make_button(text=f"B{i}")
        project.add_widget(btn, parent_id=frame.id, document_id=doc.id)
    code = generate_code(project)
    # Fork API call site, not inline helper definition.
    assert "ctk.balance_pack(" in code
    assert "def _ctkmaker_balance_pack" not in code
    # Each button gets its content-min attr.
    assert "._ctkmaker_min = " in code


def test_per_child_attrs_emitted_for_hbox_children():
    project, doc = _make_project_with_doc(doc_layout="hbox", child_count=2)
    code = generate_code(project)
    # _ctkmaker_min appears for each pack child (default stretch="grow"
    # via apply_fill_default since CTkButton.prefers_fill_in_layout).
    assert code.count("._ctkmaker_min = ") >= 2


def test_fixed_stretch_marks_child_as_locked():
    project = Project()
    doc = Document(name="MainWindow")
    doc.window_properties["width"] = 400
    doc.window_properties["height"] = 300
    doc.window_properties["layout_type"] = "hbox"
    project.documents = [doc]
    project.active_document_id = doc.id
    # Two buttons: one explicit grow, one explicit fixed. Real
    # drops get stretch="grow" via widget_lifecycle._apply_fill_default,
    # but Project-level construction doesn't run the workspace path —
    # set stretch by hand to mirror what the workspace would have done.
    btn1 = _make_button(text="Grow")
    btn1.properties["stretch"] = "grow"
    project.add_widget(btn1, document_id=doc.id)
    btn2 = _make_button(text="Locked")
    btn2.properties["stretch"] = "fixed"
    project.add_widget(btn2, document_id=doc.id)
    code = generate_code(project)
    # Locked button gets the _ctkmaker_fixed = True line; the grow
    # button does NOT (only min, no fixed flag).
    assert "._ctkmaker_fixed = True" in code
    fixed_count = code.count("._ctkmaker_fixed = True")
    assert fixed_count == 1


# ---------------------------------------------------------------------
# _project_needs_pack_balance — direct unit tests
# ---------------------------------------------------------------------
def test_needs_pack_balance_false_for_empty_project():
    project = Project()
    doc = Document(name="MainWindow")
    doc.window_properties["layout_type"] = "place"
    project.documents = [doc]
    project.active_document_id = doc.id
    assert _project_needs_pack_balance([doc], []) is False


def test_needs_pack_balance_true_for_window_hbox_with_children():
    project, doc = _make_project_with_doc(doc_layout="hbox", child_count=1)
    widgets = []
    for root in doc.root_widgets:
        widgets.append(root)
    assert _project_needs_pack_balance([doc], widgets) is True


def test_needs_pack_balance_false_for_empty_hbox():
    # hbox container with NO children — nothing to redistribute.
    project, doc = _make_project_with_doc(doc_layout="place")
    frame_desc = get_descriptor("CTkFrame")
    frame_props = dict(frame_desc.default_properties)
    frame_props["layout_type"] = "hbox"
    frame = WidgetNode(widget_type="CTkFrame", properties=frame_props)
    project.add_widget(frame, document_id=doc.id)
    # No children inside.
    assert _project_needs_pack_balance([doc], [frame]) is False
