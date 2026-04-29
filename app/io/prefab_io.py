"""Read / write ``.ctkprefab`` files — user-wide saved widget bundles
that ship across projects.

A ``.ctkprefab`` is a ZIP archive holding a single ``prefab.json``
(Phase A). Phase B will add a sibling ``assets/`` folder for bundled
images / fonts and a ``variables`` block in the JSON.

Schema (v1):
    {
      "schema_version": 1,
      "type": "fragment" | "window",
      "name": "Login Card",
      "created_at": "2026-04-29T12:00:00",
      "ctk_maker_version": "1.2.0",
      "view_size": {"w": 320, "h": 240},
      "nodes": [ /* WidgetNode dicts */ ],
      "variables": [],
      "assets": []
    }

Variable bindings (``var:<uuid>`` tokens) are stripped to their
current literal values on save — Phase A keeps prefabs portable
across projects whose variable namespaces are unrelated. Phase B
will bundle window-local variables and remap bindings on insert.
"""

from __future__ import annotations

import datetime
import json
import uuid
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.logger import log_error
from app.core.prefab_paths import PREFAB_EXT
from app.core.variables import is_var_token, parse_var_token
from app.core.widget_node import WidgetNode

if TYPE_CHECKING:
    from app.core.project import Project

SCHEMA_VERSION = 1
PAYLOAD_FILENAME = "prefab.json"

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
) -> None:
    """Write the given root WidgetNodes as a ``.ctkprefab`` zip at
    ``target_path``. Caller is responsible for path validation
    (folder exists, no overwrite).
    """
    snapshots = [_strip_var_tokens(n.to_dict(), project) for n in nodes]
    view_size = _compute_view_size(nodes)
    try:
        from app import __version__ as app_version
    except ImportError:
        app_version = "unknown"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "type": TYPE_FRAGMENT,
        "name": name,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "ctk_maker_version": app_version,
        "view_size": {"w": view_size[0], "h": view_size[1]},
        "nodes": snapshots,
        "variables": [],
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


def count_var_bindings(nodes: list[WidgetNode]) -> int:
    """How many ``var:<uuid>`` token bindings would be stripped if
    these nodes were saved as a prefab. Used by the save dialog to
    show a single up-front warning instead of per-property prompts.
    """
    count = 0

    def walk(node_dict: dict) -> None:
        nonlocal count
        for value in node_dict.get("properties", {}).values():
            if is_var_token(value):
                count += 1
        for child in node_dict.get("children", []):
            walk(child)

    for node in nodes:
        walk(node.to_dict())
    return count


def _strip_var_tokens(node_dict: dict, project: "Project") -> dict:
    """Recursively replace every ``var:<uuid>`` property value with the
    variable's current literal value. Tokens pointing at deleted
    variables are removed entirely — descriptor falls back to its
    declared default at instantiation time.
    """
    properties = node_dict.get("properties", {})
    cleaned_props: dict = {}
    for key, value in properties.items():
        var_id = parse_var_token(value)
        if var_id is None:
            cleaned_props[key] = value
            continue
        tk_var = project.get_tk_var(var_id) if project is not None else None
        if tk_var is None:
            continue
        try:
            cleaned_props[key] = tk_var.get()
        except Exception:
            log_error(f"prefab strip var {var_id}")
    node_dict["properties"] = cleaned_props
    node_dict["children"] = [
        _strip_var_tokens(c, project)
        for c in node_dict.get("children", [])
    ]
    return node_dict


def _compute_view_size(nodes: list[WidgetNode]) -> tuple[int, int]:
    """Bounding box of root nodes' x / y / width / height. Used by the
    Phase D preview window to pick a sensible initial size; doesn't
    affect insert behaviour.
    """
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
    """Read the full ``prefab.json``. Returns ``None`` on any failure
    (corrupt zip, missing payload, JSON error).
    """
    try:
        with zipfile.ZipFile(path, "r") as zf:
            with zf.open(PAYLOAD_FILENAME) as fh:
                return json.load(fh)
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
        log_error(f"prefab load {path}")
        return None


def load_metadata(path: Path) -> dict | None:
    """Lightweight header read for tree display — same as
    ``load_payload`` for now (the file is small enough not to matter)
    but kept distinct so the prefab tree can later switch to a
    summary-only path if metadata gets fatter.
    """
    payload = load_payload(path)
    if payload is None:
        return None
    return {
        "type": payload.get("type", TYPE_FRAGMENT),
        "name": payload.get("name", path.stem),
        "node_types": _summarise_node_types(payload.get("nodes", [])),
    }


def _summarise_node_types(node_dicts: list[dict]) -> list[str]:
    """Top-level widget types in the fragment, in tree order. Used by
    the panel row to show e.g. ``(CTkButton)`` for a single-widget
    fragment or ``(Frame, …)`` for a multi-root one.
    """
    return [n.get("widget_type", "?") for n in node_dicts]


# ---------------------------------------------------------------------------
# Instantiate
# ---------------------------------------------------------------------------
def instantiate_fragment(
    payload: dict, drop_offset: tuple[int, int],
) -> list[WidgetNode]:
    """Build live ``WidgetNode`` trees from a prefab payload.

    Every node (including descendants) gets a fresh UUID — the prefab
    file's IDs are throwaway handles. Root-level x / y are shifted by
    ``drop_offset`` so the cursor lands inside the prefab's original
    bounding box rather than at its top-left origin.
    """
    nodes: list[WidgetNode] = []
    dx, dy = drop_offset
    for raw in payload.get("nodes", []):
        node = WidgetNode.from_dict(raw)
        _reassign_ids(node)
        if dx or dy:
            node.properties["x"] = int(node.properties.get("x", 0) or 0) + dx
            node.properties["y"] = int(node.properties.get("y", 0) or 0) + dy
        nodes.append(node)
    return nodes


def _reassign_ids(node: WidgetNode) -> None:
    node.id = str(uuid.uuid4())
    for child in node.children:
        _reassign_ids(child)
