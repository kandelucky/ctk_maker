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
from app.core.project_folder import (
    ProjectMetaError, find_active_page_entry, find_project_root,
    migrate_page_sidecars, page_file_path, pages_dir,
    read_project_meta, write_project_meta,
)
from app.core.widget_node import WidgetNode

SUPPORTED_VERSIONS = {1, 2}


class ProjectLoadError(Exception):
    pass


def load_project(
    project: Project, path: str | Path, root=None,
) -> None:
    """Load a project off disk and populate ``project`` in place.

    Accepts either:
    - a path to a ``.ctkproj`` page file (multi-page projects + legacy
      single-file projects)
    - a path to a project folder containing ``project.json``

    For multi-page projects the loader walks up to ``project.json``,
    reads project-level metadata (name, page list, font cascade) and
    then loads the active page's ``.ctkproj``. For legacy projects
    everything comes from the single ``.ctkproj``.
    """
    path = Path(path)
    multi_page_meta: dict | None = None
    project_folder: Path | None = None

    # Multi-page detection: either ``path`` itself is a folder with
    # project.json, or the .ctkproj's parent walk-up finds it. In the
    # second case we may be pointing at a non-active page — load the
    # page the user picked, but read project-level metadata from
    # project.json so font cascade + page list stay project-wide.
    if path.is_dir():
        candidate = path / "project.json"
        if candidate.is_file():
            project_folder = path
    if project_folder is None:
        # Walk up regardless of extension — covers .ctkproj page
        # picks AND .autosave restores (which load a sidecar file
        # nested under <root>/.autosave/<id>.json but still belong
        # to the multi-page project).
        project_folder = find_project_root(path)

    if project_folder is not None:
        try:
            multi_page_meta = read_project_meta(project_folder)
        except ProjectMetaError as exc:
            raise ProjectLoadError(
                f"project.json could not be loaded.\n\n{exc}",
            ) from exc

    # Resolve the actual page file to read. Folder-only path or a
    # picked .ctkproj that isn't in the page list both fall back to
    # the active page from project.json.
    # Migrate any legacy sibling .bak / .autosave files into the
    # new id-keyed sidecar folders. Idempotent — no-op when the
    # project has been opened by this build before.
    if multi_page_meta is not None and project_folder is not None:
        try:
            migrate_page_sidecars(project_folder)
        except Exception:
            from app.core.logger import log_error as _log
            _log("migrate_page_sidecars on load")

        # Prune ghost pages — entries in project.json whose .ctkproj
        # files were deleted from outside the app (Explorer drag-to-
        # trash, manual cleanup). Without this the user gets a
        # cryptic "file not found" error on the next switch attempt.
        # If the active page itself is missing, fall back to the
        # first living one. Zero living pages → user-facing error.
        modified, _dropped, _active_changed = _prune_missing_pages(
            project_folder, multi_page_meta,
        )
        if modified:
            try:
                write_project_meta(project_folder, multi_page_meta)
            except ProjectMetaError:
                from app.core.logger import log_error as _log
                _log("project.json prune write")
        if not multi_page_meta.get("pages"):
            raise ProjectLoadError(
                "All page files for this project are missing on disk.\n\n"
                "The project folder was probably moved or its "
                "``assets/pages/`` contents were deleted from outside "
                "the app.\n\n"
                "Try recovering individual pages from "
                "``.backups/`` (one ``.ctkproj.bak`` per page) — "
                "rename one back into ``assets/pages/`` and reopen."
            )

    if multi_page_meta is not None:
        if path.is_dir():
            entry = find_active_page_entry(multi_page_meta)
            if entry is None or not entry.get("file"):
                raise ProjectLoadError(
                    "project.json has no active page.",
                )
            page_path = page_file_path(project_folder, entry["file"])
        else:
            page_path = path
            # If the user picked a page that isn't the active one,
            # update the meta in-memory so project.active_page_id
            # reflects what we actually load.
            picked_filename = path.name
            entry_match = next(
                (
                    p for p in multi_page_meta.get("pages", [])
                    if isinstance(p, dict) and p.get("file") == picked_filename
                ),
                None,
            )
            if entry_match is not None:
                multi_page_meta["active_page"] = entry_match.get("id")
        path = Path(page_path)

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

    # Multi-page mode: project-level fields come from project.json
    # (authoritative). Legacy mode: they come from the .ctkproj.
    if multi_page_meta is not None:
        meta_source: dict = multi_page_meta
    else:
        meta_source = data
    name = meta_source.get("name")
    if isinstance(name, str) and name.strip():
        project.name = name.strip()

    # Project-level font cascade. Missing key → empty cascade
    # (legacy / never-set state). The dict is straight-up applied;
    # ``set_active_project_defaults`` is wired through main_window
    # at ``_set_current_path`` time so listeners pick it up.
    raw_defaults = meta_source.get("font_defaults")
    project.font_defaults = (
        {str(k): str(v) for k, v in raw_defaults.items() if v}
        if isinstance(raw_defaults, dict) else {}
    )
    raw_system = meta_source.get("system_fonts")
    project.system_fonts = (
        sorted({str(f) for f in raw_system if f})
        if isinstance(raw_system, list) else []
    )

    # Phase 1: project-level shared variables. Missing key → empty
    # list (legacy projects + never-declared state). Tk vars stay
    # lazy — they're built on first ``get_tk_var`` call.
    from app.core.variables import VariableEntry
    raw_vars = meta_source.get("variables")
    project.variables = (
        [VariableEntry.from_dict(d) for d in raw_vars if isinstance(d, dict)]
        if isinstance(raw_vars, list) else []
    )
    project.reset_tk_vars()

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
    # Wire up multi-page metadata so save_project knows to also
    # rewrite project.json + so future page-switch UI has the list
    # in memory. Legacy single-file projects clear these fields.
    if multi_page_meta is not None and project_folder is not None:
        project.folder_path = str(project_folder)
        raw_pages = multi_page_meta.get("pages") or []
        project.pages = [
            {
                "id": p.get("id"),
                "file": p.get("file"),
                "name": p.get("name", ""),
            }
            for p in raw_pages if isinstance(p, dict)
        ]
        project.active_page_id = multi_page_meta.get("active_page")
    else:
        project.folder_path = None
        project.pages = []
        project.active_page_id = None
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

    # Group hygiene — drop ``group_id`` on widgets whose group spans
    # multiple parents or whose shared parent is a layout container.
    # The Group action enforces these invariants at creation time but
    # external edits (or older builds) might not, so the loader
    # cleans up on the way in.
    _drop_invalid_groups(project)

    # Cross-document binding repair: pre-1.2.0 reparent paths skipped
    # the local-variable migration, leaving widgets in doc B bound to
    # locals owned by doc A. Walk every widget and migrate bindings
    # to its containing doc — this copies the affected vars into the
    # right doc with fresh UUIDs and rewrites the tokens. The
    # migrate helper publishes a single ``local_variables_migrated``
    # event per call so MainWindow shows one toast per repaired doc.
    _repair_cross_doc_local_bindings(project)

    # Name counters are now per-document (Document.name_counters) and
    # round-trip through Document.from_dict / to_dict. Legacy v1 files
    # with a top-level "name_counters" dict are ignored — new widgets
    # added into a legacy project will restart from 0 for each doc.
    # Harmless: the first new widget inherits the base name; rename
    # as needed.


def _repair_cross_doc_local_bindings(project) -> None:
    """One-shot scan over all widgets after a load.

    For every root widget, ask the project to migrate any local
    bindings whose owning doc differs from the widget's doc. The
    migrate helper is idempotent (no-op when bindings already line up)
    and publishes ``local_variables_migrated`` only when something
    actually moved, so a clean project produces no toast.

    Old project files (saved before the cross-doc reparent migration
    landed) ride this path on first open — affected widgets get their
    local vars copied into the doc they actually live in, and the
    chips start resolving against same-doc storage.
    """
    for doc in project.documents:
        for root in list(doc.root_widgets):
            project.migrate_local_var_bindings(root, doc)


def _drop_invalid_groups(project) -> None:
    """Strip ``group_id`` from widgets whose group violates the
    same-parent / non-layout-container invariant. Silent — invalid
    groups are quietly cleared rather than reported, on the
    assumption that whatever produced them is upstream of the user.
    """
    from app.widgets.layout_schema import is_layout_container
    by_group: dict = {}
    for node in project.iter_all_widgets():
        gid = getattr(node, "group_id", None)
        if not gid:
            continue
        by_group.setdefault(gid, []).append(node)
    for gid, members in by_group.items():
        parents = {
            (m.parent.id if m.parent is not None else None)
            for m in members
        }
        invalid = len(parents) > 1
        if not invalid:
            parent_node = members[0].parent
            invalid = (
                parent_node is not None
                and is_layout_container(parent_node.properties)
            )
        if invalid:
            for m in members:
                m.group_id = None


def _prune_missing_pages(
    project_folder, meta: dict,
) -> tuple[bool, int, bool]:
    """Drop entries from ``meta["pages"]`` whose ``.ctkproj`` files
    don't exist on disk. If the active page was among them, fall
    back to the first surviving page.

    Returns ``(modified, dropped_count, active_changed)`` so the
    caller can decide whether to rewrite ``project.json``.
    """
    pdir = pages_dir(project_folder)
    original_pages = list(meta.get("pages") or [])
    living: list[dict] = []
    for entry in original_pages:
        if not isinstance(entry, dict):
            continue
        page_filename = entry.get("file")
        if not page_filename:
            continue
        if (pdir / page_filename).is_file():
            living.append(entry)
    dropped = len(original_pages) - len(living)
    if dropped == 0 and len(living) == len(original_pages):
        return (False, 0, False)
    meta["pages"] = living
    active_changed = False
    if living:
        active_id = meta.get("active_page")
        if not any(p.get("id") == active_id for p in living):
            meta["active_page"] = living[0].get("id")
            active_changed = True
    else:
        meta["active_page"] = None
    return (True, dropped, active_changed)


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
