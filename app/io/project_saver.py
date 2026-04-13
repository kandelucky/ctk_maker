"""Save a Project to disk as JSON.

File format (version 1):
    {
        "version": 1,
        "widgets": [
            {"id": "...", "widget_type": "CTkButton", "properties": {...}, "children": []},
            ...
        ]
    }

The `version` field enables forward migration. Loader reads it and dispatches
to the appropriate migration path when new versions ship.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.project import Project

FILE_VERSION = 1


def project_to_dict(project: Project) -> dict:
    return {
        "version": FILE_VERSION,
        "widgets": [node.to_dict() for node in project.root_widgets],
    }


def save_project(project: Project, path: str | Path) -> None:
    path = Path(path)
    data = project_to_dict(project)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
