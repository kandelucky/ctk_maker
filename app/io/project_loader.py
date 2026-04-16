"""Load a Project from a JSON file written by project_saver.

Handles version 1 (single-document) and version 2 (multi-document)
formats, upgrading v1 on read so the in-memory Project is always
the new shape. Raises ProjectLoadError with a user-facing message
on any failure so the UI can show it cleanly.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.document import (
    DEFAULT_WINDOW_PROPERTIES,
    Document,
)
from app.core.project import Project
from app.core.widget_node import WidgetNode

SUPPORTED_VERSIONS = {1, 2}


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

    if version == 1:
        documents = _documents_from_v1(data)
    else:
        documents = _documents_from_v2(data)

    if not documents:
        raise ProjectLoadError("Project file has no documents.")

    # v0.0.10 shipped with ``layout_type == "pack"`` and a per-child
    # ``pack_side``. v0.0.11 split pack into ``vbox`` / ``hbox`` and
    # removed pack_side — rewrite both on load so older projects
    # round-trip cleanly.
    _migrate_layout_types(documents)

    name = data.get("name")
    if isinstance(name, str) and name.strip():
        project.name = name.strip()

    # Tear down whatever is currently in the project so every
    # listener sees the old widgets removed one by one. Afterwards
    # replace the document list with the freshly-parsed set and
    # replay every widget via add_widget so the workspace /
    # inspectors render them.
    _clear_existing_widgets(project)
    project.documents = documents
    active_id = data.get("active_document")
    if isinstance(active_id, str) and any(
        d.id == active_id for d in documents
    ):
        project.active_document_id = active_id
    else:
        project.active_document_id = documents[0].id

    # Add widgets per document via the event-emitting add_widget path
    # so the workspace gets ``widget_added`` for each node. We
    # temporarily detach the children from each root, then re-add
    # them so the event stream covers the full subtree.
    project.event_bus.publish(
        "active_document_changed", project.active_document_id,
    )
    for doc in documents:
        # add_widget writes into self.active_document.root_widgets,
        # so align active before populating each doc.
        project.active_document_id = doc.id
        project.event_bus.publish("active_document_changed", doc.id)
        roots_to_add = list(doc.root_widgets)
        doc.root_widgets = []
        for node in roots_to_add:
            _add_recursive(project, node, parent_id=None)
    project.active_document_id = active_id if (
        isinstance(active_id, str)
        and any(d.id == active_id for d in documents)
    ) else documents[0].id
    project.event_bus.publish(
        "active_document_changed", project.active_document_id,
    )

    # Restore monotonic name counters AFTER widgets are added so
    # auto-naming doesn't double-count the freshly inserted nodes.
    counters = data.get("name_counters")
    if isinstance(counters, dict):
        project._name_counters = {
            str(k): int(v) for k, v in counters.items()
            if isinstance(v, (int, float))
        }


def _clear_existing_widgets(project: Project) -> None:
    for doc in list(project.documents):
        for node in list(doc.root_widgets):
            project.remove_widget(node.id)


def _documents_from_v1(data: dict) -> list[Document]:
    widgets = data.get("widgets")
    if not isinstance(widgets, list):
        raise ProjectLoadError("v1 file missing 'widgets' array.")
    doc_meta = data.get("document") or {}
    window = data.get("window") or {}
    try:
        width = int(doc_meta.get("width", 800))
        height = int(doc_meta.get("height", 600))
    except (TypeError, ValueError):
        width, height = 800, 600
    window_props = {
        k: window.get(k, v) for k, v in DEFAULT_WINDOW_PROPERTIES.items()
    }
    doc = Document(
        name="Main Window",
        width=width,
        height=height,
        window_properties=window_props,
    )
    for i, raw in enumerate(widgets):
        if not isinstance(raw, dict):
            raise ProjectLoadError(f"widgets[{i}] is not an object.")
        try:
            doc.root_widgets.append(WidgetNode.from_dict(raw))
        except KeyError as exc:
            raise ProjectLoadError(
                f"widgets[{i}] missing field: {exc}"
            ) from exc
    return [doc]


def _documents_from_v2(data: dict) -> list[Document]:
    docs_raw = data.get("documents")
    if not isinstance(docs_raw, list):
        raise ProjectLoadError("v2 file missing 'documents' array.")
    documents: list[Document] = []
    for i, raw in enumerate(docs_raw):
        if not isinstance(raw, dict):
            raise ProjectLoadError(f"documents[{i}] is not an object.")
        try:
            documents.append(Document.from_dict(raw))
        except (KeyError, TypeError, ValueError) as exc:
            raise ProjectLoadError(
                f"documents[{i}] failed to load: {exc}"
            ) from exc
    return documents


def _migrate_layout_types(documents: list[Document]) -> None:
    """In-place upgrade of legacy ``pack`` containers. A ``pack``
    parent with any child whose ``pack_side`` is ``left`` / ``right``
    becomes ``hbox``; everything else becomes ``vbox`` (tk pack's
    default side was ``top``). The ``pack_side`` key is dropped off
    every child so the new schema stays clean.
    """
    for doc in documents:
        wp = doc.window_properties or {}
        if wp.get("layout_type") == "pack":
            wp["layout_type"] = _infer_pack_direction(doc.root_widgets)
        for root in doc.root_widgets:
            _migrate_node_layout(root)


def _migrate_node_layout(node: WidgetNode) -> None:
    props = node.properties
    if props.get("layout_type") == "pack":
        props["layout_type"] = _infer_pack_direction(node.children)
    props.pop("pack_side", None)
    # v0.0.11 → v0.0.12: the per-child pack_fill / pack_expand /
    # pack_padx / pack_pady fan-out collapses into a single
    # ``stretch`` hint on the child and a ``layout_spacing`` on the
    # parent. Legacy keys are dropped after translation.
    _migrate_child_pack_to_stretch(props)
    for child in node.children:
        _migrate_node_layout(child)


def _migrate_child_pack_to_stretch(props: dict) -> None:
    has_legacy = any(
        k in props for k in (
            "pack_fill", "pack_expand", "pack_padx", "pack_pady",
        )
    )
    if not has_legacy:
        return
    expand = bool(props.get("pack_expand"))
    fill = props.get("pack_fill") or "none"
    if "stretch" not in props:
        if expand:
            props["stretch"] = "grow"
        elif fill != "none":
            props["stretch"] = "fill"
        else:
            props["stretch"] = "fixed"
    for key in ("pack_fill", "pack_expand", "pack_padx", "pack_pady"):
        props.pop(key, None)


def _infer_pack_direction(children: list[WidgetNode]) -> str:
    for child in children:
        side = child.properties.get("pack_side")
        if side in ("left", "right"):
            return "hbox"
    return "vbox"


def _add_recursive(
    project: Project, node: WidgetNode, parent_id: str | None,
) -> None:
    """Add ``node`` to the currently active document via the event-
    emitting ``add_widget`` path, then recursively add its descendants.
    Caller is responsible for aligning ``project.active_document_id``
    to the document that should receive these roots.
    """
    children_copy = list(node.children)
    node.children = []
    node.parent = None
    project.add_widget(node, parent_id=parent_id)
    for child in children_copy:
        child.parent = None
        _add_recursive(project, child, parent_id=node.id)
