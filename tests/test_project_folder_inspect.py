"""Tests for ``inspect_picked_folder`` — the folder-pick Open flow
classifier. Pure-Python, no Tk.
"""
from __future__ import annotations

import json

from app.core.project_folder import (
    PROJECT_META_FILE,
    PROJECT_META_VERSION,
    inspect_picked_folder,
)


def _write_meta(folder, name="P", page_file="main.ctkproj"):
    meta = {
        "version": PROJECT_META_VERSION,
        "name": name,
        "active_page": "abc",
        "pages": [{"id": "abc", "file": page_file, "name": name}],
    }
    (folder / PROJECT_META_FILE).write_text(
        json.dumps(meta), encoding="utf-8",
    )


def test_none_for_falsy_input():
    assert inspect_picked_folder(None).kind == "none"
    assert inspect_picked_folder("").kind == "none"


def test_none_for_nonexistent_path(tmp_path):
    missing = tmp_path / "nope"
    result = inspect_picked_folder(missing)
    assert result.kind == "none"
    assert "Not a folder" in result.message


def test_multi_page_when_project_json_present(tmp_path):
    _write_meta(tmp_path)
    result = inspect_picked_folder(tmp_path)
    assert result.kind == "multi_page"
    assert result.folder == tmp_path


def test_legacy_single_when_one_ctkproj(tmp_path):
    page = tmp_path / "demo.ctkproj"
    page.write_text("{}", encoding="utf-8")
    result = inspect_picked_folder(tmp_path)
    assert result.kind == "legacy_single"
    assert result.page_path == page


def test_ambiguous_when_multiple_ctkproj(tmp_path):
    a = tmp_path / "a.ctkproj"
    b = tmp_path / "b.ctkproj"
    a.write_text("{}", encoding="utf-8")
    b.write_text("{}", encoding="utf-8")
    result = inspect_picked_folder(tmp_path)
    assert result.kind == "ambiguous"
    assert sorted(p.name for p in result.candidates) == ["a.ctkproj", "b.ctkproj"]


def test_none_for_empty_folder(tmp_path):
    result = inspect_picked_folder(tmp_path)
    assert result.kind == "none"
    assert "isn't a CTkMaker project" in result.message


def test_none_for_unrelated_folder(tmp_path):
    (tmp_path / "readme.txt").write_text("hi", encoding="utf-8")
    (tmp_path / "src").mkdir()
    result = inspect_picked_folder(tmp_path)
    assert result.kind == "none"


def test_multi_page_wins_over_loose_ctkproj(tmp_path):
    """If both project.json and a stray .ctkproj exist at the root,
    treat it as multi-page — the manifest is authoritative.
    """
    _write_meta(tmp_path)
    (tmp_path / "stray.ctkproj").write_text("{}", encoding="utf-8")
    result = inspect_picked_folder(tmp_path)
    assert result.kind == "multi_page"


def test_does_not_recurse(tmp_path):
    """A .ctkproj nested in a subfolder should not satisfy the
    legacy-single classification — the user picked *this* folder.
    """
    sub = tmp_path / "nested"
    sub.mkdir()
    (sub / "demo.ctkproj").write_text("{}", encoding="utf-8")
    result = inspect_picked_folder(tmp_path)
    assert result.kind == "none"
