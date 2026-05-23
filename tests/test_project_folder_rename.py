"""Tests for ``rename_page`` — page-file rename + meta update.
Pure-Python, no Tk.
"""
from __future__ import annotations

import json

from app.core.project_folder import (
    PROJECT_META_FILE,
    PROJECT_META_VERSION,
    rename_page,
)


def _bootstrap_project(folder, page_file="buttons.ctkproj", page_name="buttons"):
    """Write a minimal multi-page project skeleton with one page."""
    pages_dir = folder / "assets" / "pages"
    pages_dir.mkdir(parents=True)
    (pages_dir / page_file).write_text("{}", encoding="utf-8")
    meta = {
        "version": PROJECT_META_VERSION,
        "name": "T",
        "active_page": "p1",
        "pages": [{"id": "p1", "file": page_file, "name": page_name}],
    }
    (folder / PROJECT_META_FILE).write_text(
        json.dumps(meta), encoding="utf-8",
    )


def _read_entry(folder):
    meta = json.loads((folder / PROJECT_META_FILE).read_text(encoding="utf-8"))
    return meta["pages"][0]


def test_rename_page_renames_file_and_meta(tmp_path):
    _bootstrap_project(tmp_path)
    rename_page(tmp_path, "p1", "buttons_showcase")

    new_page = tmp_path / "assets" / "pages" / "buttons_showcase.ctkproj"
    assert new_page.is_file()
    assert not (tmp_path / "assets" / "pages" / "buttons.ctkproj").exists()
    entry = _read_entry(tmp_path)
    assert entry["file"] == "buttons_showcase.ctkproj"
    assert entry["name"] == "buttons_showcase"


def test_rename_page_no_scripts_folder_is_noop(tmp_path):
    _bootstrap_project(tmp_path)
    # Rename must succeed without any assets/scripts/ folder present.
    rename_page(tmp_path, "p1", "buttons_showcase")

    new_page = tmp_path / "assets" / "pages" / "buttons_showcase.ctkproj"
    assert new_page.is_file()


def test_rename_page_display_name_only_keeps_file(tmp_path):
    # Slug unchanged (only display name differs) — the .ctkproj file
    # stays put while the meta display name updates.
    _bootstrap_project(tmp_path, page_file="buttons.ctkproj", page_name="Old")
    rename_page(tmp_path, "p1", "Buttons")

    assert (tmp_path / "assets" / "pages" / "buttons.ctkproj").is_file()
    entry = _read_entry(tmp_path)
    assert entry["name"] == "Buttons"
    assert entry["file"] == "buttons.ctkproj"
