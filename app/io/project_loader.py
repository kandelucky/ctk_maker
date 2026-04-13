"""Load a Project from a JSON file written by project_saver.

Handles version dispatch (currently only v1) and raises ProjectLoadError
with a user-facing message on any failure so the UI can show it cleanly.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.project import Project
from app.core.widget_node import WidgetNode

SUPPORTED_VERSIONS = {1}


class ProjectLoadError(Exception):
    pass


def load_project(project: Project, path: str | Path) -> None:
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as exc:
        raise ProjectLoadError(f"Could not read file:\n{exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProjectLoadError(f"File is not valid JSON:\n{exc.msg}") from exc

    if not isinstance(data, dict):
        raise ProjectLoadError("File does not contain a project object.")

    version = data.get("version")
    if version not in SUPPORTED_VERSIONS:
        raise ProjectLoadError(
            f"Unsupported project version: {version!r}. "
            f"Supported: {sorted(SUPPORTED_VERSIONS)}."
        )

    widgets = data.get("widgets")
    if not isinstance(widgets, list):
        raise ProjectLoadError("Project file is missing a 'widgets' array.")

    nodes: list[WidgetNode] = []
    for i, raw in enumerate(widgets):
        if not isinstance(raw, dict):
            raise ProjectLoadError(f"widgets[{i}] is not an object.")
        try:
            nodes.append(WidgetNode.from_dict(raw))
        except KeyError as exc:
            raise ProjectLoadError(f"widgets[{i}] missing field: {exc}") from exc

    doc = data.get("document")
    if isinstance(doc, dict):
        try:
            dw = int(doc.get("width", project.document_width))
            dh = int(doc.get("height", project.document_height))
            project.resize_document(dw, dh)
        except (TypeError, ValueError):
            pass

    name = data.get("name")
    if isinstance(name, str) and name.strip():
        project.name = name.strip()

    _replace_widgets(project, nodes)


def _replace_widgets(project: Project, new_nodes: list[WidgetNode]) -> None:
    for existing in list(project.root_widgets):
        project.remove_widget(existing.id)
    for node in new_nodes:
        project.add_widget(node)
