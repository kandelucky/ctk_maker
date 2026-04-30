"""Component asset bundling — Phase B2.

Per-component asset packaging: when a saved fragment uses images
(via descriptor properties typed ``image``), those files travel
inside the ``.ctkcomp`` zip under ``assets/`` and are extracted into
a per-component folder under the target project's
``assets/components/<slug>/`` on insert.

Token format:
    bundle:<filename>

Inside an archive, asset filenames are flat (``assets/logo.png``).
Within-bundle name collisions are resolved at save time by suffixing
``_2``, ``_3`` etc. On insert, the whole bundle lands under a
freshly-named folder (``login-card``, then ``login-card_2`` etc.) so
assets from different components can't collide with each other or
with the user's own files in ``assets/images/``.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.assets import is_asset_token, resolve_asset_token
from app.core.logger import log_error
from app.widgets.registry import get_descriptor

if TYPE_CHECKING:
    pass

BUNDLE_PREFIX = "bundle:"
ARCHIVE_ASSETS_DIR = "assets"
PROJECT_COMPONENTS_DIRNAME = "components"


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------
def is_bundle_token(value) -> bool:
    return isinstance(value, str) and value.startswith(BUNDLE_PREFIX)


def parse_bundle_token(token: str) -> str:
    """Return the bare filename inside a bundle token."""
    return token[len(BUNDLE_PREFIX):]


def make_bundle_token(filename: str) -> str:
    return BUNDLE_PREFIX + filename


# ---------------------------------------------------------------------------
# Descriptor introspection — which properties carry asset paths
# ---------------------------------------------------------------------------
def image_prop_names(widget_type: str) -> list[str]:
    """Names of properties whose schema type is ``image`` for the
    given descriptor. Empty list when the descriptor isn't found or
    has no image properties.
    """
    desc = get_descriptor(widget_type)
    if desc is None:
        return []
    return [
        spec["name"] for spec in getattr(desc, "property_schema", [])
        if spec.get("type") == "image"
    ]


# ---------------------------------------------------------------------------
# Save side — discover + bundle
# ---------------------------------------------------------------------------
def _resolve_asset_value(value, project_file) -> Path | None:
    """Take an image-property value (absolute path, ``asset:`` token,
    or empty/None) and return the absolute path to the source file
    on disk. Returns ``None`` if the file doesn't exist or the value
    doesn't reference one.
    """
    if not value or not isinstance(value, str):
        return None
    if is_bundle_token(value):
        # Already a bundle token — happens when re-saving an inserted
        # component without first changing the image. The caller
        # treats it as "carry the existing token through" rather than
        # trying to resolve it back to disk here.
        return None
    if is_asset_token(value):
        resolved = resolve_asset_token(value, project_file)
        return resolved if resolved and resolved.exists() else None
    candidate = Path(value)
    return candidate if candidate.exists() else None


def _unique_archive_name(filename: str, used: set[str]) -> str:
    """Append ``_2``, ``_3`` etc. to disambiguate a within-bundle
    collision. ``used`` is the set of names already taken; the
    returned name is appended automatically.
    """
    if filename not in used:
        used.add(filename)
        return filename
    stem, dot, ext = filename.rpartition(".")
    if not dot:
        stem, ext = filename, ""
    n = 2
    while True:
        candidate = f"{stem}_{n}{('.' + ext) if ext else ''}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        n += 1


def collect_assets_from_nodes(
    node_dicts: list[dict], project_file,
) -> dict[str, str]:
    """Walk the node-dict tree, resolve every image property to a
    real file, and build a path-map ``{abs_path: archive_name}``.
    Within-bundle name collisions get ``_2``/``_3`` suffixes.
    """
    abs_to_name: dict[str, str] = {}
    used: set[str] = set()

    def walk(node: dict) -> None:
        widget_type = node.get("widget_type", "")
        image_props = image_prop_names(widget_type)
        if image_props:
            props = node.get("properties", {})
            for prop in image_props:
                resolved = _resolve_asset_value(props.get(prop), project_file)
                if resolved is None:
                    continue
                key = str(resolved)
                if key in abs_to_name:
                    continue
                archive_name = _unique_archive_name(resolved.name, used)
                abs_to_name[key] = archive_name
        for child in node.get("children", []):
            walk(child)

    for n in node_dicts:
        walk(n)
    return abs_to_name


def rewrite_image_props_to_bundle_tokens(
    node_dicts: list[dict], abs_to_name: dict[str, str],
    project_file,
) -> None:
    """In-place replacement: image-property values that match a
    discovered absolute path become ``bundle:<archive_name>`` tokens.
    Other values (empty, missing files, external paths we couldn't
    bundle) are left as-is.
    """
    def walk(node: dict) -> None:
        widget_type = node.get("widget_type", "")
        image_props = image_prop_names(widget_type)
        if image_props:
            props = node.get("properties", {})
            for prop in image_props:
                resolved = _resolve_asset_value(props.get(prop), project_file)
                if resolved is None:
                    continue
                archive_name = abs_to_name.get(str(resolved))
                if archive_name is None:
                    continue
                props[prop] = make_bundle_token(archive_name)
        for child in node.get("children", []):
            walk(child)

    for n in node_dicts:
        walk(n)


def write_assets_into_zip(
    zf: zipfile.ZipFile, abs_to_name: dict[str, str],
) -> list[dict]:
    """Copy every source file into the open zip under
    ``assets/<archive_name>``. Returns the assets manifest entries
    (id + size) to embed in ``component.json``.
    """
    manifest: list[dict] = []
    for abs_path, archive_name in abs_to_name.items():
        try:
            arc = f"{ARCHIVE_ASSETS_DIR}/{archive_name}"
            zf.write(abs_path, arc)
            try:
                size = Path(abs_path).stat().st_size
            except OSError:
                size = 0
            manifest.append({
                "id": archive_name,
                "kind": "image",
                "size_bytes": size,
            })
        except OSError:
            log_error(f"component_assets bundle {abs_path}")
    return manifest


def count_assets_in_nodes(
    node_dicts: list[dict], project_file,
) -> tuple[int, int]:
    """Returns ``(file_count, total_size_bytes)`` for the asset
    bundle the given fragment would produce. Used by the Save dialog
    hint. ``project_file`` lets ``asset:`` tokens resolve.
    """
    abs_to_name = collect_assets_from_nodes(node_dicts, project_file)
    total_bytes = 0
    for abs_path in abs_to_name:
        try:
            total_bytes += Path(abs_path).stat().st_size
        except OSError:
            pass
    return len(abs_to_name), total_bytes


# ---------------------------------------------------------------------------
# Insert side — extract + retarget
# ---------------------------------------------------------------------------
_SLUG_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def slugify_component_name(name: str) -> str:
    s = _SLUG_RE.sub("-", (name or "").strip()).strip("-")
    return s.lower() or "component"


def pick_unique_component_folder(parent: Path, base_slug: str) -> Path:
    """Return ``parent/<base_slug>`` (or ``_2``/``_3``...) for the
    first non-existing path. The folder is **not** created here —
    the caller decides when to ``mkdir``.
    """
    candidate = parent / base_slug
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        candidate = parent / f"{base_slug}_{n}"
        if not candidate.exists():
            return candidate
        n += 1


def extract_assets_to_folder(
    zf: zipfile.ZipFile, target_folder: Path,
) -> dict[str, Path]:
    """Extract every ``assets/*`` entry from the open zip into
    ``target_folder``, creating the folder if needed. Returns
    ``{archive_name: extracted_path}`` so the caller can rewrite
    bundle tokens to real paths.
    """
    target_folder.mkdir(parents=True, exist_ok=True)
    extracted: dict[str, Path] = {}
    prefix = ARCHIVE_ASSETS_DIR + "/"
    for entry in zf.infolist():
        if not entry.filename.startswith(prefix):
            continue
        archive_name = entry.filename[len(prefix):]
        if not archive_name or archive_name.endswith("/"):
            continue
        # Flat layout — we never store sub-folders inside assets/.
        # Strip any unexpected slashes defensively.
        flat_name = Path(archive_name).name
        out_path = target_folder / flat_name
        try:
            with zf.open(entry) as src, open(out_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted[archive_name] = out_path
        except OSError:
            log_error(
                f"component_assets extract {entry.filename} -> {out_path}",
            )
    return extracted


def rewrite_bundle_tokens_to_paths(
    node_dicts: list[dict], extracted: dict[str, Path],
) -> None:
    """In-place: every ``bundle:<filename>`` in an image property
    becomes the absolute path of the extracted file. Tokens that
    don't match a known asset (truncated archive, malformed token)
    are dropped — the property goes back to its descriptor default
    on next read by becoming an empty string.
    """
    def walk(node: dict) -> None:
        widget_type = node.get("widget_type", "")
        image_props = image_prop_names(widget_type)
        if image_props:
            props = node.get("properties", {})
            for prop in image_props:
                value = props.get(prop)
                if not is_bundle_token(value):
                    continue
                name = parse_bundle_token(value)
                target = extracted.get(name)
                props[prop] = str(target) if target else ""
        for child in node.get("children", []):
            walk(child)

    for n in node_dicts:
        walk(n)
