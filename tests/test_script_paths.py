from pathlib import Path

import pytest

from app.core.script_paths import (
    archive_dir,
    behavior_class_name,
    behavior_file_path,
    behavior_file_stem,
    ensure_scripts_root,
    page_scripts_dir,
    scripts_root,
    slugify_window_name,
)
from tests.conftest import StubDoc


# ---- scripts_root --------------------------------------------------------

def test_scripts_root_none_when_no_path():
    assert scripts_root(None) is None
    assert scripts_root("") is None


def test_scripts_root_legacy_single_file(tmp_path):
    project_file = tmp_path / "demo.ctkproj"
    project_file.write_text("{}", encoding="utf-8")

    root = scripts_root(project_file)

    assert root == tmp_path / "assets" / "scripts"


# ---- page_scripts_dir ----------------------------------------------------

def test_page_scripts_dir_uses_lowercase_stem(tmp_path):
    project_file = tmp_path / "Login.ctkproj"
    project_file.write_text("{}", encoding="utf-8")

    page_dir = page_scripts_dir(project_file)

    assert page_dir == tmp_path / "assets" / "scripts" / "login"


def test_page_scripts_dir_none_when_unsaved():
    assert page_scripts_dir(None) is None


# ---- behavior_file_stem --------------------------------------------------

@pytest.mark.parametrize(
    "filename, expected",
    [
        ("Login.ctkproj", "login"),
        ("dashboard.ctkproj", "dashboard"),
        ("MIXED_Case.ctkproj", "mixed_case"),
    ],
)
def test_behavior_file_stem_lowercases(filename, expected, tmp_path):
    project_file = tmp_path / filename
    assert behavior_file_stem(project_file) == expected


def test_behavior_file_stem_falls_back_to_page_when_unsaved():
    assert behavior_file_stem(None) == "page"
    assert behavior_file_stem("") == "page"


# ---- slugify_window_name -------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Main Window", "main_window"),
        ("Confirm Dialog!", "confirm_dialog"),
        ("1Setup", "_1setup"),
        ("Already_Snake_Case", "already_snake_case"),
        ("multiple   spaces", "multiple_spaces"),
        ("UPPER", "upper"),
    ],
)
def test_slugify_window_name_known_inputs(raw, expected):
    assert slugify_window_name(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "!!!", "   "])
def test_slugify_window_name_falls_back_to_window(raw):
    assert slugify_window_name(raw) == "window"


# ---- behavior_file_path --------------------------------------------------

def test_behavior_file_path_uses_main_when_no_document(tmp_path):
    project_file = tmp_path / "demo.ctkproj"
    project_file.write_text("{}", encoding="utf-8")

    path = behavior_file_path(project_file, document=None)

    assert path == tmp_path / "assets" / "scripts" / "demo" / "main.py"


def test_behavior_file_path_uses_document_slug(tmp_path):
    project_file = tmp_path / "demo.ctkproj"
    project_file.write_text("{}", encoding="utf-8")
    doc = StubDoc(name="Login Form")

    path = behavior_file_path(project_file, document=doc)

    assert path == (
        tmp_path / "assets" / "scripts" / "demo" / "login_form.py"
    )


def test_behavior_file_path_none_when_unsaved():
    assert behavior_file_path(None, document=StubDoc("anything")) is None


# ---- behavior_class_name -------------------------------------------------

@pytest.mark.parametrize(
    "doc_name, expected",
    [
        ("Main Window", "MainWindowPage"),
        ("confirm_dialog", "ConfirmDialogPage"),
        ("settings panel", "SettingsPanelPage"),
        ("a-b-c", "ABCPage"),
    ],
)
def test_behavior_class_name_pascals_and_appends_page(doc_name, expected):
    assert behavior_class_name(StubDoc(name=doc_name)) == expected


def test_behavior_class_name_falls_back_to_window_page():
    assert behavior_class_name(None) == "WindowPage"
    assert behavior_class_name(StubDoc(name="")) == "WindowPage"
    assert behavior_class_name(StubDoc(name="!!!")) == "WindowPage"


# ---- ensure_scripts_root -------------------------------------------------

def test_ensure_scripts_root_creates_dirs_and_init_files(tmp_path):
    project_file = tmp_path / "demo.ctkproj"
    project_file.write_text("{}", encoding="utf-8")

    page_dir = ensure_scripts_root(project_file)

    assert page_dir == tmp_path / "assets" / "scripts" / "demo"
    assert page_dir.is_dir()
    assert (tmp_path / "assets" / "scripts" / "__init__.py").is_file()
    assert (page_dir / "__init__.py").is_file()


def test_ensure_scripts_root_idempotent(tmp_path):
    project_file = tmp_path / "demo.ctkproj"
    project_file.write_text("{}", encoding="utf-8")

    first = ensure_scripts_root(project_file)
    # Hand-edit the top __init__ to verify a re-call does not overwrite.
    top_init = tmp_path / "assets" / "scripts" / "__init__.py"
    top_init.write_text("# hand-edited", encoding="utf-8")

    second = ensure_scripts_root(project_file)

    assert first == second
    assert top_init.read_text(encoding="utf-8") == "# hand-edited"


def test_ensure_scripts_root_none_when_unsaved():
    assert ensure_scripts_root(None) is None


# ---- archive_dir ---------------------------------------------------------

def test_archive_dir_creates_subfolder(tmp_path):
    project_file = tmp_path / "demo.ctkproj"
    project_file.write_text("{}", encoding="utf-8")

    target = archive_dir(project_file)

    assert target == (
        tmp_path / "assets" / "scripts_archive" / "demo"
    )
    assert target.is_dir()


def test_archive_dir_idempotent(tmp_path):
    project_file = tmp_path / "demo.ctkproj"
    project_file.write_text("{}", encoding="utf-8")

    first = archive_dir(project_file)
    sentinel = first / "marker.txt"
    sentinel.write_text("x", encoding="utf-8")

    second = archive_dir(project_file)

    assert first == second
    assert sentinel.is_file()


def test_archive_dir_none_when_unsaved():
    assert archive_dir(None) is None
