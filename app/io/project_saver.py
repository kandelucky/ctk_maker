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
    """Serialise the in-memory project to the ``.ctkproj`` page file
    schema.

    Variables and object references are page-scoped — each page owns
    its own set, so both lists go in every page's ``.ctkproj``.
    Truly project-level metadata (``name``, ``font_defaults``,
    ``system_fonts``) lives in ``project.json`` for multi-page
    projects and is omitted here.

    Legacy single-file projects (``folder_path is None``) still emit
    project-level fields so the lone ``.ctkproj`` round-trips on its
    own.
    """
    data: dict = {
        "version": FILE_VERSION,
        "active_document": project.active_document_id,
        "documents": [doc.to_dict() for doc in project.documents],
        "variables": [
            v.to_dict() for v in (project.variables or [])
        ],
        "object_references": [
            r.to_dict() for r in (project.object_references or [])
        ],
    }
    if not project.folder_path:
        data["name"] = project.name
        data["font_defaults"] = dict(project.font_defaults or {})
        data["system_fonts"] = sorted(set(project.system_fonts or []))
    # Convert any in-assets absolute image paths to portable tokens
    # so the saved JSON survives a project-folder move.
    if project.path:
        _tokenize_image_paths(data, project.path)
    return data


def project_meta_to_dict(project: Project) -> dict:
    """Serialise multi-page project metadata for ``project.json``.

    Pulls ``name`` / ``font_defaults`` / ``system_fonts`` from the
    in-memory project (these are project-level, not page-level) and
    pairs them with the page list. ``active_page`` is whichever id
    is currently in memory. Variables and object references are
    page-scoped — they live in each page's ``.ctkproj``, not here.
    """
    from app.core.project_folder import PROJECT_META_VERSION
    return {
        "version": PROJECT_META_VERSION,
        "name": project.name,
        "active_page": project.active_page_id,
        "pages": [
            {
                "id": p.get("id"),
                "file": p.get("file"),
                "name": p.get("name", ""),
            }
            for p in (project.pages or [])
            if isinstance(p, dict)
        ],
        "font_defaults": dict(project.font_defaults or {}),
        "system_fonts": sorted(set(project.system_fonts or [])),
    }


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
    """Write the active page's ``.ctkproj`` and, in multi-page mode,
    also rewrite ``project.json`` so any project-level metadata
    edits made in this session land alongside the page state.
    """
    path = Path(path)
    data = project_to_dict(project)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_error("save_project parent mkdir")
    # If a previous save exists at this path, atomically rotate it to
    # the backup slot before overwriting. One generation only; next
    # save's rotation replaces the existing .bak. If the write below
    # fails (disk full, permission flip), the .bak still holds the
    # last good copy and the user can recover by renaming it back.
    #
    # Multi-page projects keep the backup in ``<root>/.backups/`` so
    # ``assets/pages/`` doesn't accumulate sidecar files. Legacy
    # projects (no project.json) keep the sibling .bak.
    if path.exists():
        bak = _resolve_bak_target(project, path)
        try:
            bak.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, bak)
        except OSError:
            log_error("save_project bak rotate")
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    # Multi-page mode: rewrite project.json so name + font cascade +
    # page list stay in sync with the page write we just performed.
    if project.folder_path:
        from app.core.project_folder import (
            ProjectMetaError, write_project_meta,
        )
        try:
            write_project_meta(
                project.folder_path, project_meta_to_dict(project),
            )
        except ProjectMetaError:
            log_error("save_project write project.json")


def _resolve_bak_target(project: Project, page_path: Path) -> Path:
    """Pick the backup destination for an upcoming save. Multi-page
    projects use the per-project ``.backups/`` folder keyed by page
    id; legacy projects keep the sibling ``.bak`` so existing
    recovery flows for older files still work without conversion.
    """
    folder = project.folder_path
    if folder:
        from app.core.project_folder import (
            find_page_id_by_file, page_backup_path,
        )
        page_id = find_page_id_by_file(folder, page_path.name)
        if page_id:
            return page_backup_path(folder, page_id)
    return page_path.with_name(page_path.name + BAK_SUFFIX)


def backup_path_for(
    path: str | Path, project: Project | None = None,
) -> Path:
    """Return the ``.bak`` path that ``save_project`` writes for a
    given page file. Used by the damaged-project dialog to point
    the user at the right recovery file.

    For multi-page projects callers pass the in-memory ``Project``
    so the resolver knows the page id. Without it, falls back to
    walking the disk to find ``project.json`` + the matching id.
    Legacy projects always use the sibling ``.bak``.
    """
    page_path = Path(path)
    if project is not None and project.folder_path:
        return _resolve_bak_target(project, page_path)
    # Fall back to a disk-walk lookup so callers that only have
    # the page path (no Project handle) still get the right slot.
    from app.core.project_folder import (
        find_page_id_by_file, find_project_root, page_backup_path,
    )
    folder = find_project_root(page_path)
    if folder is not None:
        page_id = find_page_id_by_file(folder, page_path.name)
        if page_id:
            return page_backup_path(folder, page_id)
    return page_path.with_name(page_path.name + BAK_SUFFIX)
