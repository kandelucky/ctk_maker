"""Load a Project from a JSON file written by project_saver.

Handles version 1 (single-document) and version 2 (multi-document)
formats, upgrading v1 on read so the in-memory Project is always
the new shape. Raises ProjectLoadError with a user-facing message
on any failure so the UI can show it cleanly.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.assets import is_asset_token, resolve_asset_token
from app.core.document import (
    DEFAULT_WINDOW_PROPERTIES,
    Document,
)
from app.core.project import Project
from app.core.widget_node import WidgetNode

SUPPORTED_VERSIONS = {1, 2}


class ProjectLoadError(Exception):
    pass


def load_project(
    project: Project, path: str | Path, root=None,
) -> None:
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as exc:
        raise ProjectLoadError(
            "The project file could not be opened.\n\n"
            f"File: {path.name}\n"
            "It may have been moved, renamed, or is locked by another "
            "program. Check the file exists and try again."
        ) from exc
    except json.JSONDecodeError as exc:
        from app.io.project_saver import backup_path_for
        bak = backup_path_for(path)
        if bak.exists():
            recovery = (
                f"The previous save is kept at {bak.name} (sibling of "
                f"this file). Rename it to {path.name} or open it "
                "directly to recover the last good copy."
            )
        else:
            recovery = (
                "No backup file is sitting next to this one — the "
                "project was likely saved only once before the corruption."
            )
        raise ProjectLoadError(
            "The project file appears to be damaged.\n\n"
            f"File: {path.name}\n"
            f"Detail: {exc.msg} (line {exc.lineno})\n\n"
            "This can happen if the file was edited by hand or the save "
            "was interrupted.\n\n"
            f"{recovery}"
        ) from exc

    if not isinstance(data, dict):
        raise ProjectLoadError(
            "This file is not a CTkMaker project.\n\n"
            f"File: {path.name}\n"
            "Expected a project object at the top of the file. "
            "Pick a valid .ctkproj file to open."
        )

    version = data.get("version")
    if version not in SUPPORTED_VERSIONS:
        supported = ", ".join(str(v) for v in sorted(SUPPORTED_VERSIONS))
        raise ProjectLoadError(
            "This project was saved by a different version of the "
            "builder.\n\n"
            f"File version: {version!r}\n"
            f"This build supports: {supported}\n\n"
            "Update CTkMaker to the latest release, or open "
            "the file with the version it was saved in."
        )

    if version == 1:
        documents = _documents_from_v1(data)
    else:
        documents = _documents_from_v2(data)

    if not documents:
        raise ProjectLoadError("Project file has no documents.")

    # Resolve any ``asset:images/x.png`` tokens to absolute paths
    # against the loaded project's folder so descriptors keep seeing
    # plain absolute strings in memory. Token form is restored on
    # save by ``project_saver._tokenize_image_paths``.
    _resolve_image_tokens(documents, path)

    # v0.0.10 shipped with ``layout_type == "pack"`` and a per-child
    # ``pack_side``. v0.0.11 split pack into ``vbox`` / ``hbox`` and
    # removed pack_side — rewrite both on load so older projects
    # round-trip cleanly.
    _migrate_layout_types(documents)

    name = data.get("name")
    if isinstance(name, str) and name.strip():
        project.name = name.strip()

    # Project-level font cascade. Missing key → empty cascade
    # (legacy / never-set state). The dict is straight-up applied;
    # ``set_active_project_defaults`` is wired through main_window
    # at ``_set_current_path`` time so listeners pick it up.
    raw_defaults = data.get("font_defaults")
    project.font_defaults = (
        {str(k): str(v) for k, v in raw_defaults.items() if v}
        if isinstance(raw_defaults, dict) else {}
    )
    raw_system = data.get("system_fonts")
    project.system_fonts = (
        sorted({str(f) for f in raw_system if f})
        if isinstance(raw_system, list) else []
    )

    # Prime the font system BEFORE any widget is added — otherwise
    # CTkFont(family=...) calls inside widget construction resolve
    # against an empty cascade (defaults stale from the previous
    # project) and Tk hasn't yet been told about bundled .ttfs from
    # this project's assets/fonts/. The exported runtime gets this
    # right by registering fonts at the top of __init__; the
    # in-builder load path needs the same ordering.
    from app.core.fonts import (
        register_project_fonts, set_active_project_defaults,
    )
    if root is not None:
        register_project_fonts(path, root=root)
    set_active_project_defaults(project.font_defaults)

    # Tear down whatever is currently in the project so every
    # listener sees the old widgets removed one by one. Afterwards
    # replace the document list with the freshly-parsed set and
    # replay every widget via add_widget so the workspace /
    # inspectors render them.
    _clear_existing_widgets(project)
    # Drop the previous project's undo/redo stack — the commands
    # reference widget IDs that no longer exist, so Ctrl+Z after load
    # would either crash or resurrect ghosts from the old project.
    project.history.clear()
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

    # Name counters are now per-document (Document.name_counters) and
    # round-trip through Document.from_dict / to_dict. Legacy v1 files
    # with a top-level "name_counters" dict are ignored — new widgets
    # added into a legacy project will restart from 0 for each doc.
    # Harmless: the first new widget inherits the base name; rename
    # as needed.


def _clear_existing_widgets(project: Project) -> None:
    for doc in list(project.documents):
        for node in list(doc.root_widgets):
            project.remove_widget(node.id)


def _resolve_image_tokens(documents, project_file) -> None:
    for doc in documents:
        for node in doc.root_widgets:
            _resolve_token_in_node(node, project_file)


def _resolve_token_in_node(node: WidgetNode, project_file) -> None:
    img = node.properties.get("image")
    if isinstance(img, str) and is_asset_token(img):
        resolved = resolve_asset_token(img, project_file)
        if resolved is not None:
            node.properties["image"] = str(resolved)
    for child in node.children:
        _resolve_token_in_node(child, project_file)


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

    v0.0.12 grid spans (``grid_rowspan`` / ``grid_columnspan``) and
    per-child grid padding (``grid_padx`` / ``grid_pady``) are
    dropped on load — v0.0.13 simplified the grid schema to
    row/column/sticky only. ``grid_row`` / ``grid_column`` /
    ``grid_sticky`` stay as-is so the user's cell layout survives.
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
    # v0.0.12 → v0.0.13: drop span + per-cell padding keys.
    for key in (
        "grid_rowspan", "grid_columnspan",
        "grid_padx", "grid_pady",
    ):
        props.pop(key, None)
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
