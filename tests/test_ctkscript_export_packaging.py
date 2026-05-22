"""Packaging: a project with attached CTkScript components ships a
self-contained build — the ``CTkScript`` base as ``ctkmaker.py`` and
the project's top-level ``scripts/`` folder (with package markers).
Component-less projects ship neither. See
docs/plans/script_optimization.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.core.project import Project
from app.io.code_exporter import export_project


def _bootstrap(tmp_path: Path, with_component: bool) -> Path:
    root = tmp_path / "MyProj"
    pages = root / "assets" / "pages"
    pages.mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "scripts" / "counter.py").write_text(
        "from ctkmaker import CTkScript\n\n"
        "class ClickCounter(CTkScript):\n"
        "    def bump(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    (root / "project.json").write_text(
        json.dumps({
            "version": 1, "name": "MyProj", "active_page": "page1",
            "pages": [{"id": "page1", "file": "main.ctkproj", "name": "Main"}],
            "font_defaults": {}, "system_fonts": [], "variables": [],
        }),
        encoding="utf-8",
    )
    widget = {
        "id": "btn1", "name": "my_button", "widget_type": "CTkButton",
        "properties": {
            "x": 10, "y": 10, "width": 100, "height": 32, "text": "Go",
        },
        "children": [],
    }
    if with_component:
        widget["attached_components"] = [
            {"script": "counter.py", "class": "ClickCounter"},
        ]
        widget["handlers"] = {
            "command": [
                {"kind": "script_call", "class": "ClickCounter", "method": "bump"},
            ],
        }
    (pages / "main.ctkproj").write_text(
        json.dumps({
            "version": 2,
            "documents": [{
                "id": "doc1", "name": "Main", "is_toplevel": False,
                "width": 320, "height": 240, "window_properties": {},
                "widgets": [widget],
            }],
        }),
        encoding="utf-8",
    )
    return pages / "main.ctkproj"


def _load(page_path: Path) -> Project:
    from app.io.project_loader import load_project
    project = Project()
    load_project(project, str(page_path))
    project.path = str(page_path)
    return project


def test_components_ship_base_and_scripts(tmp_path):
    page = _bootstrap(tmp_path, with_component=True)
    project = _load(page)
    out = tmp_path / "out" / "Main.py"
    out.parent.mkdir(parents=True)
    export_project(project, out)

    # Base sidecar present + self-contained (defines CTkScript).
    base = out.parent / "ctkmaker.py"
    assert base.is_file()
    assert "class CTkScript" in base.read_text(encoding="utf-8")

    # User scripts copied + made an importable package.
    assert (out.parent / "scripts" / "counter.py").is_file()
    assert (out.parent / "scripts" / "__init__.py").is_file()

    # Generated code imports the component class.
    assert (
        "from scripts.counter import ClickCounter"
        in out.read_text(encoding="utf-8")
    )


def test_no_components_ships_neither(tmp_path):
    page = _bootstrap(tmp_path, with_component=False)
    project = _load(page)
    out = tmp_path / "out" / "Main.py"
    out.parent.mkdir(parents=True)
    export_project(project, out)

    assert not (out.parent / "ctkmaker.py").exists()
    assert not (out.parent / "scripts").exists()
