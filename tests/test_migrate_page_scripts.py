"""Unit tests for ``migrate_page_scripts_folders`` — the per-page
scripts/ + scripts_archive/ subfolder rename helper used by
``rename_page``. Pure-Python, no Tk.
"""
from __future__ import annotations

import pytest

from app.core.script_paths import (
    ScriptsMigrationConflict,
    migrate_page_scripts_folders,
)


def test_migrate_moves_scripts_dir(tmp_path):
    src = tmp_path / "assets" / "scripts" / "old"
    src.mkdir(parents=True)
    (src / "handler.py").write_text("BODY", encoding="utf-8")

    migrate_page_scripts_folders(tmp_path, "old", "new")

    new = tmp_path / "assets" / "scripts" / "new"
    assert new.is_dir()
    assert (new / "handler.py").read_text(encoding="utf-8") == "BODY"
    assert not src.exists()


def test_migrate_moves_archive_dir(tmp_path):
    src = tmp_path / "assets" / "scripts_archive" / "old"
    src.mkdir(parents=True)
    (src / "h.py").write_text("X", encoding="utf-8")

    migrate_page_scripts_folders(tmp_path, "old", "new")

    new = tmp_path / "assets" / "scripts_archive" / "new"
    assert (new / "h.py").read_text(encoding="utf-8") == "X"


def test_migrate_noop_when_source_missing(tmp_path):
    # No scripts/ folder at all — must not raise.
    migrate_page_scripts_folders(tmp_path, "old", "new")
    assert not (tmp_path / "assets" / "scripts" / "new").exists()


def test_migrate_noop_when_stems_equal(tmp_path):
    src = tmp_path / "assets" / "scripts" / "same"
    src.mkdir(parents=True)
    (src / "h.py").write_text("KEEP", encoding="utf-8")

    migrate_page_scripts_folders(tmp_path, "same", "same")

    assert (src / "h.py").read_text(encoding="utf-8") == "KEEP"


def test_migrate_replaces_empty_target(tmp_path):
    src = tmp_path / "assets" / "scripts" / "old"
    src.mkdir(parents=True)
    (src / "h.py").write_text("REAL", encoding="utf-8")
    target = tmp_path / "assets" / "scripts" / "new"
    target.mkdir(parents=True)

    migrate_page_scripts_folders(tmp_path, "old", "new")

    assert (target / "h.py").read_text(encoding="utf-8") == "REAL"


def test_migrate_replaces_stub_init_only_target(tmp_path):
    src = tmp_path / "assets" / "scripts" / "old"
    src.mkdir(parents=True)
    (src / "h.py").write_text("REAL", encoding="utf-8")
    # Stub layout — single empty __init__.py — is the regen
    # baseline ``ensure_scripts_root`` writes; safe to overwrite.
    target = tmp_path / "assets" / "scripts" / "new"
    target.mkdir(parents=True)
    (target / "__init__.py").write_text("", encoding="utf-8")

    migrate_page_scripts_folders(tmp_path, "old", "new")

    assert (target / "h.py").read_text(encoding="utf-8") == "REAL"
    assert not (target / "__init__.py").exists()


def test_migrate_raises_when_target_has_real_files(tmp_path):
    src = tmp_path / "assets" / "scripts" / "old"
    src.mkdir(parents=True)
    (src / "h.py").write_text("REAL", encoding="utf-8")
    target = tmp_path / "assets" / "scripts" / "new"
    target.mkdir(parents=True)
    (target / "other.py").write_text("KEEPER", encoding="utf-8")

    with pytest.raises(ScriptsMigrationConflict):
        migrate_page_scripts_folders(tmp_path, "old", "new")

    # Both dirs untouched — caller can decide to retry.
    assert (src / "h.py").read_text(encoding="utf-8") == "REAL"
    assert (target / "other.py").read_text(encoding="utf-8") == "KEEPER"


def test_migrate_raises_when_target_has_nonempty_init(tmp_path):
    # An __init__.py with content (e.g. user added imports) is NOT
    # the regen stub baseline — must not be silently clobbered.
    src = tmp_path / "assets" / "scripts" / "old"
    src.mkdir(parents=True)
    (src / "h.py").write_text("REAL", encoding="utf-8")
    target = tmp_path / "assets" / "scripts" / "new"
    target.mkdir(parents=True)
    (target / "__init__.py").write_text("import x", encoding="utf-8")

    with pytest.raises(ScriptsMigrationConflict):
        migrate_page_scripts_folders(tmp_path, "old", "new")
