"""Unit tests for the page-delete script disposal helpers
``list_page_scripts`` + ``recycle_page_scripts`` (app/io/scripts/paths).

Pure-Python, no Tk. ``send2trash`` is monkeypatched to a hermetic
delete so the real OS Recycle Bin is never touched — the tests only
care which paths get handed to disposal and how the folder sweep
behaves.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.io.scripts import list_page_scripts, recycle_page_scripts


def _make_project(tmp_path: Path) -> Path:
    """Build a realistic saved-project layout and return the page's
    ``.ctkproj`` path (what the helpers take as input).

        tmp_path/
            project.json                 # so find_project_root resolves
            assets/pages/main.ctkproj
            assets/scripts/_runtime.py   # shared — must never be touched
            assets/scripts/main/
                __init__.py              # plumbing
                rosetta.py               # user script (2 methods)
                helper.py                # user script (1 method)
                __pycache__/x.pyc        # plumbing
    """
    (tmp_path / "project.json").write_text("{}", encoding="utf-8")
    pages = tmp_path / "assets" / "pages"
    pages.mkdir(parents=True)
    page_path = pages / "main.ctkproj"
    page_path.write_text("{}", encoding="utf-8")

    scripts = tmp_path / "assets" / "scripts"
    page_dir = scripts / "main"
    page_dir.mkdir(parents=True)
    (scripts / "_runtime.py").write_text("class ref: ...\n", encoding="utf-8")
    (page_dir / "__init__.py").write_text("", encoding="utf-8")
    (page_dir / "rosetta.py").write_text(
        "class RosettaPage:\n"
        "    def setup(self, w): ...\n"
        "    def on_click(self): ...\n",
        encoding="utf-8",
    )
    (page_dir / "helper.py").write_text(
        "class HelperPage:\n    def setup(self, w): ...\n",
        encoding="utf-8",
    )
    cache = page_dir / "__pycache__"
    cache.mkdir()
    (cache / "rosetta.cpython-314.pyc").write_bytes(b"\x00")
    return page_path


@pytest.fixture
def fake_trash(monkeypatch):
    """Replace ``send2trash.send2trash`` with a hermetic delete that
    records the paths it was asked to dispose of.
    """
    trashed: list[str] = []

    def _trash(path):
        p = Path(path)
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        trashed.append(p.name)

    monkeypatch.setattr("send2trash.send2trash", _trash)
    return trashed


# --------------------------------------------------------------------
# list_page_scripts

def test_list_returns_user_scripts_with_counts(tmp_path):
    page_path = _make_project(tmp_path)
    scripts = dict((f, (m, ln)) for f, m, ln in list_page_scripts(page_path))
    # Plumbing + the shared runtime never show up.
    assert set(scripts) == {"rosetta.py", "helper.py"}
    assert scripts["rosetta.py"][0] == 2   # setup + on_click
    assert scripts["helper.py"][0] == 1    # setup
    assert scripts["rosetta.py"][1] == 3   # line count


def test_list_empty_when_folder_missing(tmp_path):
    (tmp_path / "project.json").write_text("{}", encoding="utf-8")
    pages = tmp_path / "assets" / "pages"
    pages.mkdir(parents=True)
    page_path = pages / "ghost.ctkproj"
    page_path.write_text("{}", encoding="utf-8")
    assert list_page_scripts(page_path) == []


# --------------------------------------------------------------------
# recycle_page_scripts

def test_recycle_selected_keeps_unselected_and_runtime(tmp_path, fake_trash):
    page_path = _make_project(tmp_path)
    page_dir = tmp_path / "assets" / "scripts" / "main"

    count = recycle_page_scripts(page_path, ["rosetta.py"])

    assert count == 1
    assert not (page_dir / "rosetta.py").exists()      # gone
    assert (page_dir / "helper.py").exists()           # kept
    assert (page_dir / "__init__.py").exists()         # folder kept
    # Shared runtime in the parent scripts root is untouched.
    assert (tmp_path / "assets" / "scripts" / "_runtime.py").exists()


def test_recycle_all_sweeps_whole_folder(tmp_path, fake_trash):
    page_path = _make_project(tmp_path)
    page_dir = tmp_path / "assets" / "scripts" / "main"

    count = recycle_page_scripts(page_path, ["rosetta.py", "helper.py"])

    assert count == 2
    # No user .py left → folder (plumbing + __pycache__) is swept too.
    assert not page_dir.exists()
    # Sibling shared runtime survives the folder sweep.
    assert (tmp_path / "assets" / "scripts" / "_runtime.py").exists()


def test_recycle_empty_selection_is_noop(tmp_path, fake_trash):
    page_path = _make_project(tmp_path)
    page_dir = tmp_path / "assets" / "scripts" / "main"

    count = recycle_page_scripts(page_path, [])

    assert count == 0
    assert (page_dir / "rosetta.py").exists()
    assert (page_dir / "helper.py").exists()
    assert page_dir.exists()


def test_recycle_ignores_plumbing_and_path_escapes(tmp_path, fake_trash):
    page_path = _make_project(tmp_path)
    page_dir = tmp_path / "assets" / "scripts" / "main"

    # __init__.py is plumbing (never offered); the traversal name must
    # not escape the page folder.
    count = recycle_page_scripts(
        page_path, ["__init__.py", "../_runtime.py"],
    )

    assert count == 0
    assert (page_dir / "__init__.py").exists()
    assert (tmp_path / "assets" / "scripts" / "_runtime.py").exists()


def test_recycle_missing_folder_returns_zero(tmp_path, fake_trash):
    (tmp_path / "project.json").write_text("{}", encoding="utf-8")
    pages = tmp_path / "assets" / "pages"
    pages.mkdir(parents=True)
    page_path = pages / "ghost.ctkproj"
    page_path.write_text("{}", encoding="utf-8")
    assert recycle_page_scripts(page_path, ["whatever.py"]) == 0
