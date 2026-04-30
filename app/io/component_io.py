"""Read / write ``.ctkcomp`` files — saved widget bundles per project.

A ``.ctkcomp`` is a ZIP archive holding a single ``component.json``.
Phase B will add a sibling ``assets/`` folder for bundled images /
fonts.

Schema (v1):
    {
      "schema_version": 1,
      "type": "fragment" | "window",
      "name": "Login Card",
      "created_at": "2026-04-30T12:00:00",
      "ctk_maker_version": "1.3.1",
      "view_size": {"w": 320, "h": 240},
      "nodes": [ /* WidgetNode dicts */ ],
      "variables": [ /* {id, name, type, default} */ ],
      "assets": []
    }

Variable bundling: every resolvable ``var:<uuid>`` token (local OR
global) joins the bundle. On insert, all bundled vars land in the
target Window's local namespace (globals get demoted to locals so
the component is portable). Deleted-var tokens drop silently.
"""

from __future__ import annotations

import datetime
import json
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.component_paths import COMPONENT_EXT  # noqa: F401
from app.core.logger import log_error
from app.core.variables import (
    is_var_token, make_var_token, parse_var_token,
)
from app.core.widget_node import WidgetNode

if TYPE_CHECKING:
    from app.core.document import Document
    from app.core.project import Project
    from app.core.variables import VariableEntry

SCHEMA_VERSION = 1
PAYLOAD_FILENAME = "component.json"

TYPE_FRAGMENT = "fragment"
TYPE_WINDOW = "window"


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
def save_fragment(
    target_path: Path,
    name: str,
    nodes: list[WidgetNode],
    project: "Project",
    source_window_id: str | None,
    author: str = "",
) -> None:
    """Write the given root WidgetNodes as a ``.ctkcomp`` zip at
    ``target_path``. ``source_window_id`` is the Document id the
    selection came from (used as a hint; bundling treats local + global
    bindings the same way regardless). ``author`` is a free-form
    user-typed name stored in the payload — empty allowed.
    """
    snapshots, var_bundle = _process_nodes_for_save(
        nodes, project, source_window_id,
    )
    view_size = _compute_view_size(nodes)
    try:
        from app import __version__ as app_version
    except ImportError:
        app_version = "unknown"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "type": TYPE_FRAGMENT,
        "name": name,
        "author": author,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "ctk_maker_version": app_version,
        "view_size": {"w": view_size[0], "h": view_size[1]},
        "nodes": snapshots,
        "variables": var_bundle,
        "assets": [],
    }
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        target_path, "w", compression=zipfile.ZIP_DEFLATED,
    ) as zf:
        zf.writestr(
            PAYLOAD_FILENAME,
            json.dumps(payload, indent=2, ensure_ascii=False),
        )


def rewrite_payload_author(target_path: Path, author: str) -> None:
    """Repack a ``.ctkcomp`` zip with an updated ``author`` field —
    used by the Export dialog when the user changes the author at
    export time without touching the original file. The source file
    is read via ``load_payload`` and re-emitted at ``target_path``.
    """
    payload = load_payload(target_path)
    if payload is None:
        return
    payload["author"] = author
    with zipfile.ZipFile(
        target_path, "w", compression=zipfile.ZIP_DEFLATED,
    ) as zf:
        zf.writestr(
            PAYLOAD_FILENAME,
            json.dumps(payload, indent=2, ensure_ascii=False),
        )


def rewrite_payload_for_publish(
    target_path: Path,
    author: str,
    license_block: dict,
    category: str,
    description: str,
) -> None:
    """Repack a ``.ctkcomp`` zip with the publish-time fields: updated
    ``author``, an immutable ``license`` block recording the user's
    consent, plus ``category`` and ``description`` for library
    listing. Used by the Publish form.
    """
    payload = load_payload(target_path)
    if payload is None:
        return
    payload["author"] = author
    payload["license"] = license_block
    payload["category"] = category
    payload["description"] = description
    with zipfile.ZipFile(
        target_path, "w", compression=zipfile.ZIP_DEFLATED,
    ) as zf:
        zf.writestr(
            PAYLOAD_FILENAME,
            json.dumps(payload, indent=2, ensure_ascii=False),
        )


def count_bindings_to_bundle(
    nodes: list[WidgetNode],
    project: "Project",
) -> int:
    """How many ``var:<uuid>`` bindings will travel with the component.
    Resolvable bindings (local + global) all bundle as locals on the
    target Window; deleted-var tokens are uncountable here and just
    get dropped silently on save.
    """
    seen: set[str] = set()

    def walk(node_dict: dict) -> None:
        for value in node_dict.get("properties", {}).values():
            var_id = parse_var_token(value)
            if var_id is None:
                continue
            if project.find_document_for_variable(var_id) is not None:
                seen.add(var_id)
                continue
            for v in project.variables:
                if v.id == var_id:
                    seen.add(var_id)
                    break
        for child in node_dict.get("children", []):
            walk(child)

    for node in nodes:
        walk(node.to_dict())
    return len(seen)


def _resolve_var_for_bundle(
    project: "Project", var_id: str,
) -> "VariableEntry | None":
    owner = project.find_document_for_variable(var_id)
    if owner is not None:
        for v in owner.local_variables:
            if v.id == var_id:
                return v
    for v in project.variables:
        if v.id == var_id:
            return v
    return None


def _process_nodes_for_save(
    nodes: list[WidgetNode],
    project: "Project",
    source_window_id: str | None,
) -> tuple[list[dict], list[dict]]:
    """Single recursive walk that produces cleaned node snapshots and
    the variable bundle. Every resolvable ``var:<uuid>`` token —
    whether local or global at source — joins the bundle as a local
    var (insert promotes them to the target Window's namespace).
    Deleted-var tokens drop silently.
    """
    bundle: dict[str, dict] = {}

    def process(node_dict: dict) -> dict:
        cleaned: dict = {}
        for key, value in node_dict.get("properties", {}).items():
            var_id = parse_var_token(value)
            if var_id is None:
                cleaned[key] = value
                continue
            entry = _resolve_var_for_bundle(project, var_id)
            if entry is None:
                continue
            if var_id not in bundle:
                bundle[var_id] = {
                    "id": entry.id,
                    "name": entry.name,
                    "type": entry.type,
                    "default": entry.default,
                }
            cleaned[key] = value
        node_dict["properties"] = cleaned
        node_dict["children"] = [
            process(c) for c in node_dict.get("children", [])
        ]
        return node_dict

    snapshots = [process(n.to_dict()) for n in nodes]
    return snapshots, list(bundle.values())


def _compute_view_size(nodes: list[WidgetNode]) -> tuple[int, int]:
    if not nodes:
        return (0, 0)
    max_x = max_y = 0
    for n in nodes:
        x = int(n.properties.get("x", 0) or 0)
        y = int(n.properties.get("y", 0) or 0)
        w = int(n.properties.get("width", 0) or 0)
        h = int(n.properties.get("height", 0) or 0)
        max_x = max(max_x, x + w)
        max_y = max(max_y, y + h)
    return (max_x, max_y)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def load_payload(path: Path) -> dict | None:
    """Read the full ``component.json``. Returns ``None`` on failure."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            with zf.open(PAYLOAD_FILENAME) as fh:
                return json.load(fh)
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
        log_error(f"component load {path}")
        return None


def load_metadata(path: Path) -> dict | None:
    payload = load_payload(path)
    if payload is None:
        return None
    view_size = payload.get("view_size") or {}
    return {
        "type": payload.get("type", TYPE_FRAGMENT),
        "name": payload.get("name", path.stem),
        "author": payload.get("author", ""),
        "created_at": payload.get("created_at", ""),
        "view_w": int(view_size.get("w", 0) or 0),
        "view_h": int(view_size.get("h", 0) or 0),
        "node_types": _summarise_node_types(payload.get("nodes", [])),
        "license": payload.get("license"),
    }


def _summarise_node_types(node_dicts: list[dict]) -> list[str]:
    return [n.get("widget_type", "?") for n in node_dicts]


# ---------------------------------------------------------------------------
# Variable conflict resolution
# ---------------------------------------------------------------------------
@dataclass
class VarConflict:
    """A bundled variable whose name already exists in the target
    Window with a different type. The user picks Rename or Skip via
    the conflict dialog; the chosen resolution is written back into
    this object before ``apply_var_resolutions`` runs.
    """
    bundle: dict
    existing_id: str
    existing_type: str
    resolution: str = "rename"   # "rename" | "skip"
    new_name: str = ""


@dataclass
class VarPlan:
    auto: list[dict] = field(default_factory=list)
    conflicts: list[VarConflict] = field(default_factory=list)


def analyze_var_conflicts(
    payload: dict, target_window: "Document",
) -> VarPlan:
    """Classify each bundled variable against the target Window's
    locals: ``reuse`` (full match), ``create`` (no name match), or
    ``conflict`` (same name, different type — needs the dialog).
    """
    plan = VarPlan()
    for bundle in payload.get("variables", []):
        existing = _find_local_by_name(target_window, bundle.get("name", ""))
        if existing is None:
            plan.auto.append({"bundle": bundle, "action": "create"})
        elif existing.type == bundle.get("type"):
            plan.auto.append({
                "bundle": bundle,
                "action": "reuse",
                "existing_id": existing.id,
            })
        else:
            plan.conflicts.append(VarConflict(
                bundle=bundle,
                existing_id=existing.id,
                existing_type=existing.type,
                new_name=bundle.get("name", "") + "_2",
            ))
    return plan


def _find_local_by_name(window, name: str):
    for v in window.local_variables:
        if v.name == name:
            return v
    return None


def apply_var_resolutions(
    project: "Project",
    target_window: "Document",
    plan: VarPlan,
) -> dict[str, str | None]:
    """Materialise the plan: reuse existing UUIDs, create new locals
    for fresh names, honour Rename / Skip on the conflicts. Returns
    ``{old_uuid: new_uuid_or_None}``. ``None`` means the binding was
    skipped — ``_rewrite_var_tokens`` will drop the token entirely.
    """
    uuid_map: dict[str, str | None] = {}
    for entry in plan.auto:
        bundle = entry["bundle"]
        if entry["action"] == "reuse":
            uuid_map[bundle["id"]] = entry["existing_id"]
        else:
            new_var = project.add_variable(
                name=bundle["name"],
                var_type=bundle.get("type", "str"),
                default=bundle.get("default", ""),
                scope="local",
                document_id=target_window.id,
            )
            uuid_map[bundle["id"]] = new_var.id
    for conflict in plan.conflicts:
        bundle = conflict.bundle
        if conflict.resolution == "skip":
            uuid_map[bundle["id"]] = None
            continue
        new_var = project.add_variable(
            name=conflict.new_name,
            var_type=bundle.get("type", "str"),
            default=bundle.get("default", ""),
            scope="local",
            document_id=target_window.id,
        )
        uuid_map[bundle["id"]] = new_var.id
    return uuid_map


# ---------------------------------------------------------------------------
# Instantiate
# ---------------------------------------------------------------------------
def instantiate_fragment(
    payload: dict,
    drop_offset: tuple[int, int],
    var_uuid_map: dict[str, str | None] | None = None,
) -> list[WidgetNode]:
    """Build live ``WidgetNode`` trees from a component payload."""
    nodes: list[WidgetNode] = []
    dx, dy = drop_offset
    for raw in payload.get("nodes", []):
        if var_uuid_map is not None:
            _rewrite_var_tokens(raw, var_uuid_map)
        node = WidgetNode.from_dict(raw)
        _reassign_ids(node)
        if dx or dy:
            node.properties["x"] = int(node.properties.get("x", 0) or 0) + dx
            node.properties["y"] = int(node.properties.get("y", 0) or 0) + dy
        nodes.append(node)
    return nodes


def _rewrite_var_tokens(
    node_dict: dict, uuid_map: dict[str, str | None],
) -> None:
    cleaned: dict = {}
    for key, value in node_dict.get("properties", {}).items():
        if not is_var_token(value):
            cleaned[key] = value
            continue
        var_id = parse_var_token(value)
        if var_id not in uuid_map:
            cleaned[key] = value
            continue
        new_id = uuid_map[var_id]
        if new_id is None:
            continue
        cleaned[key] = make_var_token(new_id)
    node_dict["properties"] = cleaned
    for child in node_dict.get("children", []):
        _rewrite_var_tokens(child, uuid_map)


def _reassign_ids(node: WidgetNode) -> None:
    node.id = str(uuid.uuid4())
    for child in node.children:
        _reassign_ids(child)
