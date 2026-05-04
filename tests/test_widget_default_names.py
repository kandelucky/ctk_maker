"""Newly dropped widgets get identifier-safe default Names.

Pre-fix the Properties-panel "Name" field defaulted to the
descriptor's display label ("Button", "Check Box (1)") which was
not a valid Python identifier — so the export-time
``_resolve_var_names`` fallback log fired on every preview, and the
F5 launcher surfaced a "Widget name fallbacks" warning dialog
before every run. The fix flips ``_generate_unique_name`` to the
same slug rule as the resolver (``CTk`` stripped, lowercased,
``_<N>`` counter) so the default itself is identifier-safe and
the fallback never triggers for fresh drops.
"""

from __future__ import annotations

from app.core.document import Document
from app.core.project import Project
from app.core.widget_node import WidgetNode


def _make_project() -> Project:
    project = Project()
    project.documents = [Document(name="Window", width=400, height=300)]
    project.active_document_id = project.documents[0].id
    return project


def test_default_names_are_valid_python_identifiers():
    project = _make_project()

    project.add_widget(WidgetNode("CTkButton"))
    project.add_widget(WidgetNode("CTkCheckBox"))
    project.add_widget(WidgetNode("CTkScrollableFrame"))
    project.add_widget(WidgetNode("CTkRadioButton"))

    names = [n.name for n in project.active_document.root_widgets]
    assert names == ["button_1", "checkbox_1", "scrollableframe_1", "radiobutton_1"]
    for name in names:
        assert name.isidentifier()


def test_repeated_drops_increment_per_type_counter():
    project = _make_project()

    project.add_widget(WidgetNode("CTkButton"))
    project.add_widget(WidgetNode("CTkButton"))
    project.add_widget(WidgetNode("CTkButton"))

    names = [n.name for n in project.active_document.root_widgets]
    assert names == ["button_1", "button_2", "button_3"]


def test_layout_base_overrides_widget_type_slug():
    project = _make_project()

    project.add_widget(WidgetNode("CTkFrame"), name_base="vertical_layout")
    project.add_widget(WidgetNode("CTkFrame"), name_base="horizontal_layout")
    project.add_widget(WidgetNode("CTkFrame"), name_base="grid_layout")
    project.add_widget(WidgetNode("CTkFrame"), name_base="vertical_layout")

    names = [n.name for n in project.active_document.root_widgets]
    assert names == [
        "vertical_layout_1",
        "horizontal_layout_1",
        "grid_layout_1",
        "vertical_layout_2",
    ]


def test_explicit_node_name_wins_over_auto_generation():
    project = _make_project()

    pre_named = WidgetNode("CTkButton")
    pre_named.name = "submit_btn"
    project.add_widget(pre_named)

    project.add_widget(WidgetNode("CTkButton"))

    names = [n.name for n in project.active_document.root_widgets]
    assert names == ["submit_btn", "button_1"]


def test_counters_are_per_document():
    project = _make_project()
    second = Document(name="Second", width=400, height=300)
    project.documents.append(second)

    project.add_widget(WidgetNode("CTkButton"))
    project.add_widget(WidgetNode("CTkButton"), document_id=second.id)

    assert project.documents[0].root_widgets[0].name == "button_1"
    assert second.root_widgets[0].name == "button_1"
