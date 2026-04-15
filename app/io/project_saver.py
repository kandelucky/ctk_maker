"""Save a Project to disk as JSON.

File format (version 2 — multi-document):
    {
        "version": 2,
        "name": "...",
        "active_document": "<uuid>",
        "documents": [
            {
                "id": "<uuid>",
                "name": "Main Window",
                "width": 800, "height": 600,
                "canvas_x": 0, "canvas_y": 0,
                "is_toplevel": false,
                "window_properties": {...},
                "widgets": [...]
            },
            ...
        ],
        "name_counters": {...}
    }

Version 1 files (single-document) are still loadable — the loader
wraps their top-level ``widgets`` / ``document`` / ``window`` blocks
into a one-entry ``documents`` list. Writes always use version 2.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.project import Project

FILE_VERSION = 2


def project_to_dict(project: Project) -> dict:
    return {
        "version": FILE_VERSION,
        "name": project.name,
        "active_document": project.active_document_id,
        "documents": [doc.to_dict() for doc in project.documents],
        "name_counters": dict(project._name_counters),
    }


def save_project(project: Project, path: str | Path) -> None:
    path = Path(path)
    data = project_to_dict(project)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
