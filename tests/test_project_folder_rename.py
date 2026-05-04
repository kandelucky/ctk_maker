"""Tests for ``rename_page`` — page rename + sidecar / scripts
folder migration. Pure-Python, no Tk.
"""
from __future__ import annotations

import json

import pytest

from app.core.project_folder import (
    PROJECT_META_FILE,
    PROJECT_META_VERSION,
    ProjectMetaError,
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


def test_rename_page_migrates_scripts_folder(tmp_path):
    _bootstrap_project(tmp_path)
    scripts = tmp_path / "assets" / "scripts" / "buttons"
    scripts.mkdir(parents=True)
    (scripts / "dialog.py").write_text("REAL", encoding="utf-8")
    (scripts / "__init__.py").write_text("", encoding="utf-8")

    rename_page(tmp_path, "p1", "buttons_showcase")

    new_dir = tmp_path / "assets" / "scripts" / "buttons_showcase"
    assert new_dir.is_dir()
    assert (new_dir / "dialog.py").read_text(encoding="utf-8") == "REAL"
    assert not scripts.exists()


def test_rename_page_migrates_archive_folder(tmp_path):
    _bootstrap_project(tmp_path)
    archive = tmp_path / "assets" / "scripts_archive" / "buttons"
    archive.mkdir(parents=True)
    (archive / "old_handler.py").write_text("ARCHIVED", encoding="utf-8")

    rename_page(tmp_path, "p1", "buttons_showcase")

    new_dir = tmp_path / "assets" / "scripts_archive" / "buttons_showcase"
    assert new_dir.is_dir()
    assert (new_dir / "old_handler.py").read_text(encoding="utf-8") == "ARCHIVED"
    assert not archive.exists()


def test_rename_page_no_scripts_folder_is_noop(tmp_path):
    _bootstrap_project(tmp_path)
    # No assets/scripts/ at all — rename must succeed without error.
    rename_page(tmp_path, "p1", "buttons_showcase")

    new_page = tmp_path / "assets" / "pages" / "buttons_showcase.ctkproj"
    assert new_page.is_file()


def test_rename_page_overwrites_stub_target(tmp_path):
    _bootstrap_project(tmp_path)
    src = tmp_path / "assets" / "scripts" / "buttons"
    src.mkdir(parents=True)
    (src / "dialog.py").write_text("REAL", encoding="utf-8")
    # Pre-existing target with only an empty __init__.py — the stub
    # shape ``ensure_scripts_root`` produces. Must be cleanly
    # replaced by the source dir's real content.
    stub_target = tmp_path / "assets" / "scripts" / "buttons_showcase"
    stub_target.mkdir(parents=True)
    (stub_target / "__init__.py").write_text("", encoding="utf-8")

    rename_page(tmp_path, "p1", "buttons_showcase")

    assert (stub_target / "dialog.py").read_text(encoding="utf-8") == "REAL"
    assert not src.exists()


def test_rename_page_target_with_real_files_raises(tmp_path):
    _bootstrap_project(tmp_path)
    src = tmp_path / "assets" / "scripts" / "buttons"
    src.mkdir(parents=True)
    (src / "dialog.py").write_text("REAL", encoding="utf-8")
    # Target already holds non-stub content — refuse to clobber.
    target = tmp_path / "assets" / "scripts" / "buttons_showcase"
    target.mkdir(parents=True)
    (target / "existing.py").write_text("OTHER", encoding="utf-8")

    with pytest.raises(ProjectMetaError, match="not empty"):
        rename_page(tmp_path, "p1", "buttons_showcase")

    # .ctkproj must still hold the old name — the conflict happens
    # before the page-file rename, so the operation is atomic.
    assert (tmp_path / "assets" / "pages" / "buttons.ctkproj").is_file()
    assert not (tmp_path / "assets" / "pages" / "buttons_showcase.ctkproj").exists()
    # Source scripts dir untouched too.
    assert (src / "dialog.py").read_text(encoding="utf-8") == "REAL"


def test_rename_page_display_name_only_skips_migration(tmp_path):
    # Slug unchanged (only display name differs) — ``rename_page``
    # short-circuits to the name-only branch, so scripts folder
    # migration shouldn't fire even if the source dir exists.
    _bootstrap_project(tmp_path, page_file="buttons.ctkproj", page_name="Old")
    src = tmp_path / "assets" / "scripts" / "buttons"
    src.mkdir(parents=True)
    (src / "dialog.py").write_text("REAL", encoding="utf-8")

    rename_page(tmp_path, "p1", "Buttons")

    # Slug "buttons" stays the same; folder must remain.
    assert (src / "dialog.py").read_text(encoding="utf-8") == "REAL"
