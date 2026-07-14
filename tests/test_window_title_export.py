"""Exported ``self.title(...)`` for main windows vs dialogs.

A main window still named ``DEFAULT_MAIN_WINDOW_NAME`` gets the
project name on the titlebar; any other name (user rename, dialogs,
old projects whose main window carries the project name) is used
verbatim.
"""

from __future__ import annotations

import pytest

from app.core.document import DEFAULT_MAIN_WINDOW_NAME
from app.core.project import Project
from app.io import code_exporter
from app.io.code_exporter import generate_code


@pytest.fixture(autouse=True)
def _reset_exporter_state():
    code_exporter._VAR_NAME_FALLBACKS = []
    code_exporter._NAME_MAP_CACHE = {}
    yield
    code_exporter._VAR_NAME_FALLBACKS = []
    code_exporter._NAME_MAP_CACHE = {}


def test_fresh_project_first_document_has_default_name():
    project = Project()
    assert project.documents[0].name == DEFAULT_MAIN_WINDOW_NAME
    project.clear()
    assert project.documents[0].name == DEFAULT_MAIN_WINDOW_NAME


def test_default_main_window_titled_with_project_name():
    project = Project()
    project.name = "Demo"
    source = generate_code(project)
    assert 'self.title("Demo")' in source
    assert "class MainWindow(ctk.CTk):" in source


def test_renamed_main_window_keeps_user_title():
    project = Project()
    project.name = "Demo"
    project.active_document.name = "Dashboard"
    source = generate_code(project)
    assert 'self.title("Dashboard")' in source


def test_legacy_main_window_named_like_project_unchanged():
    # Old projects: main window carries the project name (pre-plan
    # default) — output must stay byte-identical to before.
    project = Project()
    project.name = "Demo"
    project.active_document.name = "Demo"
    source = generate_code(project)
    assert 'self.title("Demo")' in source
    assert "class Demo(ctk.CTk):" in source


def test_dialog_named_like_default_keeps_own_name():
    project = Project()
    project.name = "Demo"
    from app.core.document import Document
    dialog = Document(name=DEFAULT_MAIN_WINDOW_NAME, is_toplevel=True)
    project.documents.append(dialog)
    source = generate_code(project)
    assert f'self.title("{DEFAULT_MAIN_WINDOW_NAME}")' in source
