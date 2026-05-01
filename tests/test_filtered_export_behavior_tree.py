"""Filtered exports (Quick Export, "use filter" in Export dialog)
ship the per-window behavior subtree alongside the .py.

Pre-1.9.9 ``asset_filter`` was built by ``collect_used_assets``,
which only walks widget property tokens for images / fonts. Phase
2 / 3 behavior files (``assets/scripts/<page>/<window>.py``,
``_runtime.py``, ``__init__.py`` chain) and any sibling helper
modules the user wrote next to the behavior file fell out of the
copy. The exported ``.py`` then emitted ``from assets.scripts.
<page>.<window> import …`` against an asset folder that lacked
the entire scripts subtree → ``ModuleNotFoundError`` at first
run.

These tests build a minimal multi-page project on disk, run a
filtered export, and assert the behavior tree travels.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.io.code_exporter import export_project


# ---------------------------------------------------------------------
# Fixture: a saved-on-disk project with one page that has handlers
# ---------------------------------------------------------------------
def _bootstrap_project(tmp_path: Path) -> Path:
    """Lay out a multi-page project root the loader will accept,
    then return the path to the active page's ``.ctkproj``.
    """
    root = tmp_path / "MyProj"
    pages = root / "assets" / "pages"
    scripts = root / "assets" / "scripts"
    page_scripts = scripts / "login"
    pages.mkdir(parents=True)
    page_scripts.mkdir(parents=True)

    (root / "project.json").write_text(
        json.dumps({
            "version": 1,
            "name": "MyProj",
            "active_page": "page1",
            "pages": [
                {"id": "page1", "file": "login.ctkproj", "name": "Login"},
            ],
            "font_defaults": {},
            "system_fonts": [],
            "variables": [],
        }),
        encoding="utf-8",
    )
    (scripts / "__init__.py").write_text("", encoding="utf-8")
    (scripts / "_runtime.py").write_text(
        "class ref:\n    pass\n", encoding="utf-8",
    )
    (page_scripts / "__init__.py").write_text("", encoding="utf-8")
    (page_scripts / "login.py").write_text(
        "from .helpers import greet\n\n"
        "class LoginPage:\n"
        "    def setup(self, window):\n"
        "        self.window = window\n"
        "    def on_btn_click(self):\n"
        "        greet()\n",
        encoding="utf-8",
    )
    # Sibling helper module the behavior file imports — must travel
    # alongside the .py because the exporter doesn't statically
    # analyse the behavior file's own imports.
    (page_scripts / "helpers.py").write_text(
        "def greet():\n    print('hi')\n", encoding="utf-8",
    )
    # Stale bytecode the export should NOT carry over.
    (page_scripts / "__pycache__").mkdir()
    (page_scripts / "__pycache__" / "login.cpython-311.pyc").write_bytes(
        b"stale",
    )

    page_path = pages / "login.ctkproj"
    page_path.write_text(
        json.dumps({
            "version": 2,
            "documents": [{
                "id": "doc1",
                "name": "Login",
                "is_toplevel": False,
                "width": 320,
                "height": 240,
                "window_properties": {},
                "widgets": [{
                    "id": "btn1",
                    "name": "submit_btn",
                    "widget_type": "CTkButton",
                    "properties": {
                        "x": 10, "y": 10, "width": 100, "height": 32,
                        "text": "Submit",
                    },
                    "children": [],
                    "handlers": {"command": ["on_btn_click"]},
                }],
            }],
        }),
        encoding="utf-8",
    )
    return page_path


def _load_project(page_path: Path) -> Project:
    from app.io.project_loader import load_project
    project = Project()
    load_project(project, str(page_path))
    project.path = str(page_path)
    return project


# ---------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------
def test_filtered_export_copies_behavior_tree(tmp_path):
    page_path = _bootstrap_project(tmp_path)
    project = _load_project(page_path)
    out = tmp_path / "out" / "Login.py"
    out.parent.mkdir(parents=True)

    # Empty filter — pre-1.9.9 this dropped the entire scripts subtree.
    export_project(
        project, str(out),
        single_document_id=project.documents[0].id,
        asset_filter=set(),
    )
    expected = [
        out.parent / "assets" / "scripts" / "__init__.py",
        out.parent / "assets" / "scripts" / "_runtime.py",
        out.parent / "assets" / "scripts" / "login" / "__init__.py",
        out.parent / "assets" / "scripts" / "login" / "login.py",
        out.parent / "assets" / "scripts" / "login" / "helpers.py",
    ]
    for p in expected:
        assert p.is_file(), f"missing in export: {p.relative_to(out.parent)}"


def test_filtered_export_skips_pycache(tmp_path):
    page_path = _bootstrap_project(tmp_path)
    project = _load_project(page_path)
    out = tmp_path / "out" / "Login.py"
    out.parent.mkdir(parents=True)
    export_project(
        project, str(out),
        single_document_id=project.documents[0].id,
        asset_filter=set(),
    )
    pycache_dir = (
        out.parent / "assets" / "scripts" / "login" / "__pycache__"
    )
    assert not pycache_dir.exists(), (
        "stale __pycache__ should not travel with a filtered export"
    )


def test_filtered_export_no_behavior_skips_copy(tmp_path):
    """When the doc carries no handlers AND no Behavior Field
    values, the copy is a no-op — the empty filter export shouldn't
    drag in scripts the runtime won't import.
    """
    page_path = _bootstrap_project(tmp_path)
    project = _load_project(page_path)
    # Strip handlers from every widget so the doc no longer needs
    # behavior plumbing.

    def _strip(node: WidgetNode) -> None:
        node.handlers = {}
        for c in node.children:
            _strip(c)

    for doc in project.documents:
        for root in doc.root_widgets:
            _strip(root)

    out = tmp_path / "out" / "Login.py"
    out.parent.mkdir(parents=True)
    export_project(
        project, str(out),
        single_document_id=project.documents[0].id,
        asset_filter=set(),
    )
    scripts_dir = out.parent / "assets" / "scripts"
    assert not scripts_dir.exists(), (
        "filter-only export shouldn't ship scripts when the doc has "
        "no handlers / fields"
    )


def test_unfiltered_export_unchanged_by_helper(tmp_path):
    """Sanity check — when ``asset_filter is None`` the legacy whole-
    tree copy still runs and the helper's branch is bypassed.
    """
    page_path = _bootstrap_project(tmp_path)
    project = _load_project(page_path)
    out = tmp_path / "out" / "Login.py"
    out.parent.mkdir(parents=True)
    export_project(
        project, str(out),
        single_document_id=project.documents[0].id,
        asset_filter=None,
    )
    # Whole-tree copytree pulls every file under assets/, including
    # the behavior subtree. Verify the same files land.
    assert (
        out.parent / "assets" / "scripts" / "login" / "login.py"
    ).is_file()
    assert (
        out.parent / "assets" / "scripts" / "login" / "helpers.py"
    ).is_file()
