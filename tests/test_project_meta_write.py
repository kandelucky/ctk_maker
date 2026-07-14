"""Tests for ``write_project_meta`` — atomic ``project.json`` writes
with ``.bak`` rotation. Pure-Python, no Tk.
"""
from __future__ import annotations

import json

from app.core.project_folder import (
    PROJECT_META_VERSION,
    write_project_meta,
)


def _meta(name="Demo"):
    return {
        "version": PROJECT_META_VERSION,
        "name": name,
        "active_page": "abc",
        "pages": [{"id": "abc", "file": "main.ctkproj", "name": "Main"}],
    }


def test_fresh_write_creates_no_bak(tmp_path):
    write_project_meta(tmp_path, _meta())
    assert (tmp_path / "project.json").exists()
    assert not (tmp_path / "project.json.bak").exists()


def test_identical_rewrite_creates_no_bak(tmp_path):
    # The New Project flow saves twice back-to-back with the same data.
    write_project_meta(tmp_path, _meta())
    write_project_meta(tmp_path, _meta())
    assert not (tmp_path / "project.json.bak").exists()


def test_changed_rewrite_rotates_previous_to_bak(tmp_path):
    write_project_meta(tmp_path, _meta("Old"))
    write_project_meta(tmp_path, _meta("New"))
    bak = tmp_path / "project.json.bak"
    assert bak.exists()
    assert json.loads(bak.read_text(encoding="utf-8"))["name"] == "Old"
    current = tmp_path / "project.json"
    assert json.loads(current.read_text(encoding="utf-8"))["name"] == "New"


def test_identical_rewrite_keeps_older_bak(tmp_path):
    write_project_meta(tmp_path, _meta("Old"))
    write_project_meta(tmp_path, _meta("New"))
    write_project_meta(tmp_path, _meta("New"))
    bak = tmp_path / "project.json.bak"
    assert json.loads(bak.read_text(encoding="utf-8"))["name"] == "Old"
