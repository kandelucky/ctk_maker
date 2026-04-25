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

from app.core.assets import absolute_to_token, is_asset_token
from app.core.logger import log_error
from app.core.project import Project

FILE_VERSION = 2

# Filename suffix appended to the original file extension, e.g. a
# project saved as ``foo.ctkproj`` is backed up as
# ``foo.ctkproj.bak``. One generation kept; each save overwrites the
# previous .bak via atomic ``os.replace``.
BAK_SUFFIX = ".bak"


def project_to_dict(project: Project) -> dict:
    data = {
        "version": FILE_VERSION,
        "name": project.name,
        "active_document": project.active_document_id,
        "documents": [doc.to_dict() for doc in project.documents],
        # Project-level font cascade. Empty dict by default, so most
        # files won't have anything interesting here. Saved at the
        # top level rather than inside a document so it applies
        # across every form in the project.
        "font_defaults": dict(project.font_defaults or {}),
        # System fonts the user added to the project's font palette
        # (those that show up alongside imported .ttf files in the
        # font picker). Stored as a sorted, deduped list so file
        # diffs stay stable when the project is committed to git.
        "system_fonts": sorted(set(project.system_fonts or [])),
        # name_counters persist per-document now — each Document's
        # ``name_counters`` ends up in ``to_dict`` so reopening a
        # project keeps unique names while every Dialog keeps its own
        # sequence.
    }
    # Convert any in-assets absolute image paths to portable tokens
    # so the saved JSON survives a project-folder move.
    if project.path:
        _tokenize_image_paths(data, project.path)
    return data


def _tokenize_image_paths(data: dict, project_file: str) -> None:
    for doc in data.get("documents", []) or []:
        for w in doc.get("widgets", []) or []:
            _walk_widget_tokenize(w, project_file)


def _walk_widget_tokenize(w: dict, project_file: str) -> None:
    props = w.get("properties") or {}
    img = props.get("image")
    if (
        img and isinstance(img, str)
        and not is_asset_token(img)
    ):
        token = absolute_to_token(img, project_file)
        if token:
            props["image"] = token
    for child in w.get("children") or []:
        _walk_widget_tokenize(child, project_file)


def save_project(project: Project, path: str | Path) -> None:
    path = Path(path)
    data = project_to_dict(project)
    # Project folders are created up-front by the New Project flow,
    # but Save As to an arbitrary location might point at a missing
    # parent — make sure it exists before opening for write.
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_error("save_project parent mkdir")
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
