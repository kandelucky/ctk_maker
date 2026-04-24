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
import os
from pathlib import Path

from app.core.logger import log_error
from app.core.project import Project

FILE_VERSION = 2

# Filename suffix appended to the original file extension, e.g. a
# project saved as ``foo.ctkproj`` is backed up as
# ``foo.ctkproj.bak``. One generation kept; each save overwrites the
# previous .bak via atomic ``os.replace``.
BAK_SUFFIX = ".bak"


def project_to_dict(project: Project) -> dict:
    return {
        "version": FILE_VERSION,
        "name": project.name,
        "active_document": project.active_document_id,
        "documents": [doc.to_dict() for doc in project.documents],
        # name_counters persist per-document now — each Document's
        # ``name_counters`` ends up in ``to_dict`` so reopening a
        # project keeps unique names while every Dialog keeps its own
        # sequence.
    }


def save_project(project: Project, path: str | Path) -> None:
    path = Path(path)
    data = project_to_dict(project)
    # If a previous save exists at this path, atomically rotate it to
    # ``<name>.ctkproj.bak`` before overwriting. One generation only;
    # next save's rotation replaces the existing .bak. If the write
    # below fails (disk full, permission flip), the .bak still holds
    # the last good copy and the user can recover by renaming it back.
    if path.exists():
        bak = path.with_name(path.name + BAK_SUFFIX)
        try:
            os.replace(path, bak)
        except OSError:
            log_error("save_project bak rotate")
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def backup_path_for(path: str | Path) -> Path:
    """Return the ``.bak`` path that ``save_project`` writes for a
    given project file. Used by the damaged-project dialog to point
    the user at the right recovery file.
    """
    path = Path(path)
    return path.with_name(path.name + BAK_SUFFIX)
