"""Multi-page project folder helpers.

A CTkMaker project on disk is a folder, marked by a top-level
``project.json``. Inside ``assets/pages/`` lives one or more
``.ctkproj`` files — each is one **Page** (a complete UI: main
window + its dialogs). Pages share the project's asset pool
(fonts/images/icons) so a Login page and Dashboard page can both
reference the same logo without duplicating files.

    MyProject/
        project.json                  ← marker + page list + project name
        assets/
            pages/
                main.ctkproj          ← page 1
                login.ctkproj         ← page 2
            fonts/
            images/
            icons/
        .backups/   (future)
        .autosave/  (future)

Legacy projects (a lone ``.ctkproj`` with a sibling ``assets/``)
keep working — ``find_project_root`` returns ``None`` for them,
and the loader/saver fall back to single-file behaviour.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from app.core.logger import log_error
from app.core.paths import ASSETS_DIR_NAME

PROJECT_META_FILE = "project.json"
PROJECT_META_VERSION = 1

# Pages folder lives inside ``assets/`` so the user-facing structure
# treats reusable UI templates the same as fonts/images — everything
# this project owns sits in one place.
PAGES_SUBDIR = "pages"

# Filename suffix appended to project.json on bak rotation, mirroring
# the .ctkproj.bak convention so the recovery story stays uniform.
PROJECT_META_BAK_SUFFIX = ".bak"

# Hidden sidecar folders at the project root. Dot-prefix mirrors
# Unity's `.git/`, `.vs/` convention — Windows Explorer dims them,
# the asset tree filters them out, and they live next to assets/
# rather than polluting it. Per-page sidecars are keyed by page
# id so a page rename doesn't orphan its history.
BACKUPS_SUBDIR = ".backups"
AUTOSAVE_SUBDIR = ".autosave"


class ProjectMetaError(Exception):
    """Raised when project.json can't be parsed or is structurally invalid."""


def project_meta_path(folder: str | Path) -> Path:
    return Path(folder) / PROJECT_META_FILE


def pages_dir(folder: str | Path) -> Path:
    return Path(folder) / ASSETS_DIR_NAME / PAGES_SUBDIR


def page_file_path(folder: str | Path, page_filename: str) -> Path:
    return pages_dir(folder) / page_filename


def backups_dir(folder: str | Path) -> Path:
    return Path(folder) / BACKUPS_SUBDIR


def autosave_dir(folder: str | Path) -> Path:
    return Path(folder) / AUTOSAVE_SUBDIR


def page_backup_path(folder: str | Path, page_id: str) -> Path:
    """``<root>/.backups/<page_id>.ctkproj.bak`` — one rotation slot
    per page, id-keyed so renames don't orphan the backup."""
    return backups_dir(folder) / f"{page_id}.ctkproj.bak"


def page_autosave_path(folder: str | Path, page_id: str) -> Path:
    """``<root>/.autosave/<page_id>.json`` — id-keyed for the same
    reason. ``.json`` extension (not .autosave) so Windows lights
    it up with a code editor when the user inspects it manually."""
    return autosave_dir(folder) / f"{page_id}.json"


def find_page_id_by_file(folder: str | Path, page_filename: str) -> str | None:
    """Look up a page id from its on-disk filename via project.json.
    Used by the saver / autosave to pick the sidecar slot for the
    current page without holding a reference to the in-memory
    Project object.
    """
    try:
        meta = read_project_meta(folder)
    except ProjectMetaError:
        return None
    for p in meta.get("pages") or []:
        if isinstance(p, dict) and p.get("file") == page_filename:
            return p.get("id")
    return None


def find_project_root(any_path: str | Path | None) -> Path | None:
    """Walk up from ``any_path`` looking for the nearest ``project.json``.

    Returns the folder that contains it, or ``None`` if nothing is
    found before hitting the filesystem root. Used by the asset
    resolver so a page .ctkproj nested at ``<root>/assets/pages/``
    still maps ``asset:images/foo.png`` to ``<root>/assets/images/``.

    Stops at filesystem root or after 12 levels (defensive — keeps
    the search bounded for paths that aren't inside any project).
    """
    if any_path is None:
        return None
    p = Path(any_path)
    if p.is_file():
        p = p.parent
    for _ in range(12):
        if (p / PROJECT_META_FILE).is_file():
            return p
        if p.parent == p:
            return None
        p = p.parent
    return None


def is_multi_page_project(scene_path: str | Path | None) -> bool:
    """``True`` if ``scene_path`` lives inside a multi-page project
    (i.e. ``find_project_root`` finds a ``project.json`` somewhere
    above it). Legacy single-file projects return ``False``.
    """
    return find_project_root(scene_path) is not None


# ---------------------------------------------------------------------
# Folder-pick inspection (Open-as-folder UX)
# ---------------------------------------------------------------------
class PickedFolderResult:
    """What a folder the user picked in the Open dialog actually is.

    ``kind`` distinguishes:
        ``"multi_page"``    — has ``project.json``; ``folder`` is the
                               root and the loader can take it as-is.
        ``"legacy_single"`` — no ``project.json`` but exactly one
                               ``.ctkproj`` at the root; ``page_path``
                               points at it.
        ``"ambiguous"``     — no ``project.json`` and >1 ``.ctkproj``
                               at the root; ``candidates`` lists them
                               so the caller can prompt.
        ``"none"``          — neither marker found; not a CTkMaker
                               project folder. ``message`` carries a
                               user-facing hint.
    """

    __slots__ = ("kind", "folder", "page_path", "candidates", "message")

    def __init__(
        self,
        kind: str,
        folder: Path | None = None,
        page_path: Path | None = None,
        candidates: list[Path] | None = None,
        message: str = "",
    ) -> None:
        self.kind = kind
        self.folder = folder
        self.page_path = page_path
        self.candidates = candidates or []
        self.message = message


def inspect_picked_folder(folder: str | Path | None) -> PickedFolderResult:
    """Classify a folder picked in the Open dialog.

    Used by File → Open and the Welcome dialog so the user can pick
    a project folder instead of hunting for the right ``.ctkproj``
    inside ``assets/pages/``.
    """
    if not folder:
        return PickedFolderResult(
            "none", message="No folder selected.",
        )
    p = Path(folder)
    if not p.is_dir():
        return PickedFolderResult(
            "none",
            folder=p,
            message=f"Not a folder:\n{p}",
        )
    if (p / PROJECT_META_FILE).is_file():
        return PickedFolderResult("multi_page", folder=p)
    # No project.json — fall back to legacy single-file detection by
    # listing .ctkproj files at the root only (we don't recurse —
    # the user picked *this* folder, not its descendants).
    try:
        ctkproj_files = sorted(
            entry for entry in p.iterdir()
            if entry.is_file() and entry.suffix.lower() == ".ctkproj"
        )
    except OSError as exc:
        return PickedFolderResult(
            "none",
            folder=p,
            message=f"Could not read folder:\n{exc}",
        )
    if len(ctkproj_files) == 1:
        return PickedFolderResult(
            "legacy_single", folder=p, page_path=ctkproj_files[0],
        )
    if len(ctkproj_files) > 1:
        return PickedFolderResult(
            "ambiguous", folder=p, candidates=ctkproj_files,
        )
    return PickedFolderResult(
        "none",
        folder=p,
        message=(
            "This folder isn't a CTkMaker project.\n\n"
            "A project folder contains a 'project.json' marker "
            "(multi-page projects) or a single '.ctkproj' file "
            "(legacy single-file projects)."
        ),
    )


# ---------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------
def read_project_meta(folder: str | Path) -> dict:
    """Load ``project.json`` from ``folder``. Raises ``ProjectMetaError``
    on missing file, JSON parse failure, or schema mismatch.
    """
    path = project_meta_path(folder)
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError as exc:
        raise ProjectMetaError(
            f"project.json could not be opened: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ProjectMetaError(
            f"project.json is damaged: {exc.msg} (line {exc.lineno})"
        ) from exc
    if not isinstance(data, dict):
        raise ProjectMetaError("project.json must contain an object.")
    version = data.get("version")
    if version != PROJECT_META_VERSION:
        raise ProjectMetaError(
            f"project.json version {version!r} is not supported "
            f"(expected {PROJECT_META_VERSION})."
        )
    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ProjectMetaError("project.json has no pages.")
    return data


def write_project_meta(folder: str | Path, data: dict) -> None:
    """Atomically write ``project.json``. Rotates the previous file
    to ``project.json.bak`` first so a corrupted write still leaves
    a recoverable copy.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = project_meta_path(folder)
    if target.exists():
        bak = target.with_name(target.name + PROJECT_META_BAK_SUFFIX)
        try:
            os.replace(target, bak)
        except OSError:
            log_error("write_project_meta bak rotate")
    try:
        with target.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        raise ProjectMetaError(
            f"project.json could not be written: {exc}"
        ) from exc


# ---------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------
def bootstrap_project_folder(
    parent_dir: str | Path,
    project_name: str,
    first_page_name: str = "Main",
) -> tuple[Path, dict, Path]:
    """Create a fresh project folder + asset skeleton + a single empty
    page reference. Returns ``(folder, meta_dict, page_path)``.

    The first page's ``.ctkproj`` is **not** written here — the caller
    (main_window's New Project flow) calls ``save_project`` after
    seeding the in-memory ``Project``. We return the path so it can
    pass it through.

    Raises ``OSError`` if the folder already exists or can't be
    created — the caller decides how to surface that to the user.
    """
    folder = Path(parent_dir) / project_name
    if folder.exists():
        raise OSError(f"Folder already exists: {folder}")
    folder.mkdir(parents=True)
    assets = folder / ASSETS_DIR_NAME
    assets.mkdir()
    for sub in (PAGES_SUBDIR, "fonts", "images", "icons"):
        (assets / sub).mkdir()

    page_id = uuid.uuid4().hex
    page_filename = "main.ctkproj"
    page_path = pages_dir(folder) / page_filename
    meta = {
        "version": PROJECT_META_VERSION,
        "name": project_name,
        "active_page": page_id,
        "pages": [
            {"id": page_id, "file": page_filename, "name": first_page_name},
        ],
        "font_defaults": {},
        "system_fonts": [],
    }
    write_project_meta(folder, meta)
    return folder, meta, page_path


def seed_multi_page_meta_from_disk(project, page_path: str | Path) -> bool:
    """Populate ``project.folder_path`` / ``pages`` / ``active_page_id``
    by reading ``project.json`` that walks up from ``page_path``.

    Returns ``True`` when the project.json was found and applied,
    ``False`` for legacy single-file paths. Used by the New Project
    flow so the first ``save_project`` sees the fields and rewrites
    project.json alongside the page.
    """
    folder = find_project_root(page_path)
    if folder is None:
        return False
    try:
        meta = read_project_meta(folder)
    except ProjectMetaError:
        return False
    project.folder_path = str(folder)
    raw_pages = meta.get("pages") or []
    project.pages = [
        {
            "id": p.get("id"),
            "file": p.get("file"),
            "name": p.get("name", ""),
        }
        for p in raw_pages if isinstance(p, dict)
    ]
    project.active_page_id = meta.get("active_page")
    return True


def find_active_page_entry(meta: dict) -> dict | None:
    """Return the page dict matching ``meta["active_page"]``, or the
    first page if the active id has drifted (defensive recovery).
    """
    active_id = meta.get("active_page")
    pages = meta.get("pages") or []
    for p in pages:
        if isinstance(p, dict) and p.get("id") == active_id:
            return p
    return pages[0] if pages else None


# ---------------------------------------------------------------------
# Page CRUD (P3)
# ---------------------------------------------------------------------
def slugify_page_name(name: str) -> str:
    """Convert a user-facing page name (``"Login Screen"``) into a
    filename-safe slug (``"login_screen"``). Strips forbidden chars,
    collapses whitespace to underscores, lowercases. Empty fallback
    returns ``"page"`` so callers always have something to work with.
    """
    import re
    cleaned = re.sub(r'[\\/:*?"<>|]', "", name).strip()
    cleaned = re.sub(r"\s+", "_", cleaned).lower()
    return cleaned or "page"


def _unique_filename(folder: Path, base: str, ext: str = ".ctkproj") -> str:
    """Return a filename inside ``folder`` that doesn't collide.
    ``base`` already-slugified; appends ``_2`` / ``_3`` until free.
    """
    candidate = f"{base}{ext}"
    if not (folder / candidate).exists():
        return candidate
    n = 2
    while True:
        candidate = f"{base}_{n}{ext}"
        if not (folder / candidate).exists():
            return candidate
        n += 1


def _empty_page_data(name: str) -> dict:
    """Build the minimal v2 .ctkproj payload for a fresh page.
    Mirrors what ``project_to_dict`` would emit for a brand-new
    Project, but without needing to instantiate Project itself.
    """
    from app.core.document import (
        DEFAULT_DOCUMENT_HEIGHT, DEFAULT_DOCUMENT_WIDTH,
        DEFAULT_WINDOW_PROPERTIES, Document,
    )
    doc = Document(
        name=name,
        width=DEFAULT_DOCUMENT_WIDTH,
        height=DEFAULT_DOCUMENT_HEIGHT,
        window_properties=dict(DEFAULT_WINDOW_PROPERTIES),
    )
    return {
        "version": 2,
        "name": name,
        "active_document": doc.id,
        "documents": [doc.to_dict()],
        "font_defaults": {},
        "system_fonts": [],
    }


def _page_name_taken(meta: dict, name: str, exclude_id: str | None = None) -> bool:
    """Case-insensitive check for a duplicate page display name in
    ``meta``. ``exclude_id`` skips one entry — used by rename so
    "rename to current name" doesn't trip the guard.
    """
    target = name.strip().lower()
    for p in (meta.get("pages") or []):
        if not isinstance(p, dict):
            continue
        if p.get("id") == exclude_id:
            continue
        if (p.get("name") or "").strip().lower() == target:
            return True
    return False


def add_page(folder: str | Path, name: str) -> dict:
    """Create a new empty page in the project folder.

    Generates a UUID, slugged filename, writes an empty page
    ``.ctkproj`` and updates ``project.json`` to include it.
    Raises ``ProjectMetaError`` if a page with the same name
    already exists (case-insensitive).
    Returns the new page entry dict (``{id, file, name}``).
    """
    folder = Path(folder)
    meta = read_project_meta(folder)
    if _page_name_taken(meta, name):
        raise ProjectMetaError(
            f"A page named '{name}' already exists in this project.",
        )
    pdir = pages_dir(folder)
    pdir.mkdir(parents=True, exist_ok=True)
    slug = slugify_page_name(name)
    filename = _unique_filename(pdir, slug)
    page_id = uuid.uuid4().hex
    entry = {"id": page_id, "file": filename, "name": name}

    # Write the page file BEFORE touching project.json so a partial
    # failure leaves project.json unchanged (no dangling reference).
    page_path = pdir / filename
    with page_path.open("w", encoding="utf-8") as f:
        json.dump(_empty_page_data(name), f, indent=2, ensure_ascii=False)

    pages = list(meta.get("pages") or [])
    pages.append(entry)
    meta["pages"] = pages
    write_project_meta(folder, meta)
    return entry


def rename_page(
    folder: str | Path, page_id: str, new_name: str,
) -> dict:
    """Rename a page (both the user-facing ``name`` and the on-disk
    ``.ctkproj`` filename). Returns the updated entry, or raises
    ``ProjectMetaError`` if the page id isn't found.
    """
    folder = Path(folder)
    meta = read_project_meta(folder)
    pages = list(meta.get("pages") or [])
    target_idx = next(
        (i for i, p in enumerate(pages) if p.get("id") == page_id), -1,
    )
    if target_idx < 0:
        raise ProjectMetaError(f"Page {page_id} not found.")
    if _page_name_taken(meta, new_name, exclude_id=page_id):
        raise ProjectMetaError(
            f"A page named '{new_name}' already exists in this project.",
        )
    entry = dict(pages[target_idx])
    old_filename = entry.get("file") or ""
    new_slug = slugify_page_name(new_name)
    pdir = pages_dir(folder)
    if old_filename and Path(old_filename).stem == new_slug:
        # Slug unchanged — only the display name moves.
        entry["name"] = new_name
    else:
        new_filename = _unique_filename(pdir, new_slug)
        old_path = pdir / old_filename
        new_path = pdir / new_filename
        old_stem = Path(old_filename).stem
        new_stem = Path(new_filename).stem
        # Behavior scripts live filename-keyed under
        # ``assets/scripts/<stem>/`` (Phase 2) and
        # ``assets/scripts_archive/<stem>/``. Migrate first so a
        # blocked migration (target dir holding real handler code)
        # surfaces before the visible .ctkproj rename — keeps the
        # operation atomic from the user's perspective.
        from app.core.script_paths import (
            ScriptsMigrationConflict, migrate_page_scripts_folders,
        )
        try:
            migrate_page_scripts_folders(folder, old_stem, new_stem)
        except ScriptsMigrationConflict as exc:
            raise ProjectMetaError(str(exc)) from exc
        if old_path.is_file():
            os.replace(old_path, new_path)
        # Page sidecars (.bak / .autosave) are id-keyed in the
        # multi-page layout (see ``page_backup_path`` /
        # ``page_autosave_path``), so a rename leaves them in place
        # — id is stable. Defensively clean any legacy sibling
        # files that pre-date the migration so the renamed page
        # isn't shadowed by an old name's leftover.
        for suffix in (".bak", ".autosave"):
            stale = pdir / (old_filename + suffix)
            if stale.is_file():
                try:
                    stale.unlink()
                except OSError:
                    log_error(f"rename_page drop legacy {suffix}")
        entry["file"] = new_filename
        entry["name"] = new_name
    pages[target_idx] = entry
    meta["pages"] = pages
    write_project_meta(folder, meta)
    return entry


def delete_page(folder: str | Path, page_id: str) -> str | None:
    """Delete a page and its file. Refuses to delete the last page
    (a project must always have at least one). Returns the new
    active page id (caller switches to it if the deleted page was
    the active one), or ``None`` if the deletion was refused.

    Raises ``ProjectMetaError`` if the page id isn't found.
    """
    folder = Path(folder)
    meta = read_project_meta(folder)
    pages = list(meta.get("pages") or [])
    if len(pages) <= 1:
        return None
    target_idx = next(
        (i for i, p in enumerate(pages) if p.get("id") == page_id), -1,
    )
    if target_idx < 0:
        raise ProjectMetaError(f"Page {page_id} not found.")
    entry = pages[target_idx]
    pdir = pages_dir(folder)
    page_path = pdir / (entry.get("file") or "")
    try:
        page_path.unlink(missing_ok=True)
    except OSError:
        log_error("delete_page unlink")
    # Sidecar cleanup — if the user reopens an old recovery file
    # after deletion, it would resurrect a phantom page in confusing
    # ways. Easier to drop them with the page itself. Cover both the
    # current id-keyed locations (.backups/, .autosave/) and the
    # legacy sibling files that pre-date the migration.
    deleted_id = entry.get("id") or ""
    for side in (
        page_backup_path(folder, deleted_id),
        page_autosave_path(folder, deleted_id),
        pdir / ((entry.get("file") or "") + ".bak"),
        pdir / ((entry.get("file") or "") + ".autosave"),
    ):
        try:
            side.unlink(missing_ok=True)
        except OSError:
            pass

    pages.pop(target_idx)
    meta["pages"] = pages
    # Re-pick active if we just removed it. Pick the previous page
    # in the list so the user lands somewhere visually adjacent.
    new_active = meta.get("active_page")
    if new_active == page_id:
        fallback_idx = max(0, target_idx - 1)
        new_active = pages[fallback_idx].get("id")
        meta["active_page"] = new_active
    write_project_meta(folder, meta)
    return new_active


def duplicate_page(
    folder: str | Path, page_id: str, new_name: str | None = None,
) -> dict:
    """Copy a page on disk and add a new entry to project.json.
    The new page gets a fresh UUID; the .ctkproj contents are a
    byte-for-byte copy of the source so widget IDs etc. carry over
    (deeply duplicating widget IDs is the caller's job if needed —
    for P3 the file copy is enough since each page is independent).
    """
    folder = Path(folder)
    meta = read_project_meta(folder)
    pages = list(meta.get("pages") or [])
    src_idx = next(
        (i for i, p in enumerate(pages) if p.get("id") == page_id), -1,
    )
    if src_idx < 0:
        raise ProjectMetaError(f"Page {page_id} not found.")
    src_entry = pages[src_idx]
    src_filename = src_entry.get("file") or ""
    src_path = pages_dir(folder) / src_filename
    if not src_path.is_file():
        raise ProjectMetaError(f"Page file missing on disk: {src_filename}")

    base_name = new_name or f"{src_entry.get('name', 'Page')} Copy"
    # Auto-suffix to dodge same-name collisions: "Login Copy",
    # "Login Copy 2", "Login Copy 3", ... so duplicating the same
    # page repeatedly never trips the same-name guard.
    name = base_name
    n = 2
    while _page_name_taken(meta, name):
        name = f"{base_name} {n}"
        n += 1
    slug = slugify_page_name(name)
    pdir = pages_dir(folder)
    new_filename = _unique_filename(pdir, slug)
    new_path = pdir / new_filename
    import shutil
    shutil.copy2(src_path, new_path)

    new_entry = {
        "id": uuid.uuid4().hex,
        "file": new_filename,
        "name": name,
    }
    pages.insert(src_idx + 1, new_entry)
    meta["pages"] = pages
    write_project_meta(folder, meta)
    return new_entry


def convert_legacy_to_multi_page(scene_path: str | Path) -> Path:
    """Promote a single-file legacy ``.ctkproj`` project to the
    multi-page folder format.

    Layout transition:
        <folder>/MyProj.ctkproj            → <folder>/assets/pages/<slug>.ctkproj
        <folder>/MyProj.ctkproj.bak        → moved alongside
        <folder>/MyProj.ctkproj.autosave   → moved alongside
        <folder>/assets/                   → unchanged (already exists)
        + <folder>/project.json            → newly written

    Project-level fields (name / font_defaults / system_fonts) are
    pulled out of the .ctkproj's JSON and lifted into project.json;
    the page file keeps its v2 schema as-is so single-page state
    round-trips without further mutation.

    Returns the new page path. Raises ``ProjectMetaError`` /
    ``OSError`` on failure (caller surfaces to UI). Best-effort
    safety net: a ``.preconvert.bak`` copy of the original .ctkproj
    is left next to the source so a failed move can be recovered.
    """
    import shutil
    src = Path(scene_path)
    if not src.is_file() or src.suffix.lower() != ".ctkproj":
        raise ProjectMetaError(f"Not a .ctkproj file: {src}")
    folder = src.parent
    if (folder / PROJECT_META_FILE).is_file():
        raise ProjectMetaError(
            "This project is already in multi-page format.",
        )

    # Read project-level fields out of the legacy file so we can
    # lift them into project.json. Page file stays the same shape.
    try:
        with src.open("r", encoding="utf-8") as f:
            page_data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectMetaError(
            f"Could not read .ctkproj for conversion: {exc}",
        ) from exc

    project_name = (page_data.get("name") or src.stem).strip() or src.stem
    font_defaults = page_data.get("font_defaults") or {}
    system_fonts = page_data.get("system_fonts") or []

    # Pre-flight backup so a partial move is recoverable. Same
    # name pattern across builds so the recovery dialog can find it.
    preconvert_bak = src.with_name(src.name + ".preconvert.bak")
    try:
        shutil.copy2(src, preconvert_bak)
    except OSError:
        log_error("convert preconvert backup")

    # Create the new pages folder + asset skeleton (idempotent —
    # paths.ensure_project_folder behaviour mirrored here so we
    # don't accidentally clobber subfolders the user created).
    assets = folder / ASSETS_DIR_NAME
    assets.mkdir(exist_ok=True)
    pdir = pages_dir(folder)
    pdir.mkdir(parents=True, exist_ok=True)
    for sub in ("fonts", "images", "icons"):
        (assets / sub).mkdir(exist_ok=True)

    # Move the .ctkproj + sidecars into pages/. Slug from project
    # name (not source filename) so the canonical page filename
    # follows the same convention New Page uses.
    slug = slugify_page_name(project_name)
    new_filename = _unique_filename(pdir, slug)
    new_page_path = pdir / new_filename
    moved_files: list[tuple[Path, Path]] = []
    try:
        os.replace(src, new_page_path)
        moved_files.append((src, new_page_path))
        for suffix in (".bak", ".autosave"):
            old_side = src.with_name(src.name + suffix)
            if old_side.is_file():
                new_side = new_page_path.with_name(
                    new_page_path.name + suffix,
                )
                os.replace(old_side, new_side)
                moved_files.append((old_side, new_side))
    except OSError as exc:
        # Roll back any successful moves so the user's filesystem
        # doesn't end up half-converted.
        for original, moved_to in reversed(moved_files):
            try:
                os.replace(moved_to, original)
            except OSError:
                log_error("convert rollback")
        raise ProjectMetaError(
            f"Conversion failed during file move: {exc}",
        ) from exc

    # Write project.json. UUID for the page id matches the New
    # Project flow so consumer code doesn't need to special-case
    # converted projects.
    page_id = uuid.uuid4().hex
    meta = {
        "version": PROJECT_META_VERSION,
        "name": project_name,
        "active_page": page_id,
        "pages": [
            {"id": page_id, "file": new_filename, "name": project_name},
        ],
        "font_defaults": dict(font_defaults),
        "system_fonts": sorted({str(f) for f in system_fonts if f}),
    }
    try:
        write_project_meta(folder, meta)
    except ProjectMetaError:
        # project.json write failed — roll back the file moves so
        # the project doesn't end up with a missing meta + nested
        # page state the loader can't reach.
        for original, moved_to in reversed(moved_files):
            try:
                os.replace(moved_to, original)
            except OSError:
                log_error("convert rollback after meta fail")
        raise
    return new_page_path


def migrate_page_sidecars(folder: str | Path) -> int:
    """Move legacy sibling ``.bak`` / ``.autosave`` files out of
    ``assets/pages/`` into the per-project ``.backups/`` and
    ``.autosave/`` folders, keyed by page id.

    Idempotent — files already in the new location are left alone,
    and missing sidecars are simply skipped. Returns the number of
    files actually moved (for caller logging / diagnostics).

    Run on every multi-page project load. The cost is one
    directory listing + zero or more renames; in practice this is
    a no-op after the first time.
    """
    folder = Path(folder)
    pdir = pages_dir(folder)
    if not pdir.is_dir():
        return 0
    try:
        meta = read_project_meta(folder)
    except ProjectMetaError:
        return 0
    file_to_id: dict[str, str] = {
        (p.get("file") or ""): p.get("id") or ""
        for p in (meta.get("pages") or [])
        if isinstance(p, dict)
    }
    moved = 0
    bdir = backups_dir(folder)
    adir = autosave_dir(folder)
    for entry in pdir.iterdir():
        if not entry.is_file():
            continue
        for suffix, target_dir, dest_name_fn in (
            (
                ".bak", bdir,
                lambda pid: f"{pid}.ctkproj.bak",
            ),
            (
                ".autosave", adir,
                lambda pid: f"{pid}.json",
            ),
        ):
            if not entry.name.endswith(suffix):
                continue
            page_filename = entry.name[: -len(suffix)]
            page_id = file_to_id.get(page_filename)
            if not page_id:
                # Sidecar for a page that's no longer in
                # project.json — stale leftover, drop it.
                try:
                    entry.unlink()
                except OSError:
                    log_error("migrate_page_sidecars unlink stale")
                continue
            target_dir.mkdir(parents=True, exist_ok=True)
            dest = target_dir / dest_name_fn(page_id)
            try:
                os.replace(entry, dest)
                moved += 1
            except OSError:
                log_error(f"migrate_page_sidecars move {suffix}")
            break
    return moved


def _walk_subtree(node):
    """DFS top-down generator over a widget node + its descendants.
    Mirrors Project._walk_tree but at single-node granularity so
    document-scoped collectors can iterate just one form's tree."""
    yield node
    for child in node.children or []:
        yield from _walk_subtree(child)


def _walk_widget_tokens(node) -> set[str]:
    """Collect every ``asset:...`` token referenced by ``node`` and
    its descendants. Walks the property dict scalars only —
    list / dict properties don't currently carry asset references in
    the schema, but if they do later the recursion is easy to extend.
    """
    from app.core.assets import is_asset_token
    found: set[str] = set()
    for value in (node.properties or {}).values():
        if isinstance(value, str) and is_asset_token(value):
            found.add(value)
    for child in node.children or []:
        found.update(_walk_widget_tokens(child))
    return found


def collect_used_assets(project, document_id: str | None = None) -> set[Path]:
    """Return the absolute paths of every asset file the *active
    page* of ``project`` references.

    Covers two reference kinds:
    1. Image / icon tokens (``asset:images/x.png``) directly stored
       in widget properties — resolved via ``resolve_asset_token``.
    2. Font families referenced via ``font_family`` property + the
       project-level cascade — resolved against ``assets/fonts/``
       file inventory by family name.

    ``document_id``: when given, walk only that document's widgets
    instead of every document on the page. Used by Quick Export so
    the .py for one Dialog ships only its own assets, not every
    asset referenced by sibling forms in the same page.

    Used by Save Page to New Project / Export Page (P5) so the
    bundle ships only the files this page actually needs, not the
    entire shared asset pool.
    """
    from app.core.assets import resolve_asset_token
    from app.core.fonts import list_project_fonts
    used: set[Path] = set()

    # Pick the iterable: whole project (every document) or just the
    # one document the caller named. Document iter walks the doc's
    # root_widgets tree DFS-style.
    def _iter_widgets():
        if document_id is None:
            yield from project.iter_all_widgets()
            return
        target = project.get_document(document_id)
        if target is None:
            return
        for root in target.root_widgets:
            yield from _walk_subtree(root)

    tokens: set[str] = set()
    families_seen: set[str] = set()
    for node in _iter_widgets():
        for token in _walk_widget_tokens(node):
            tokens.add(token)
        fam = (node.properties or {}).get("font_family")
        if isinstance(fam, str) and fam.strip():
            families_seen.add(fam.strip())
    # Project-level font cascade also pulls families into the
    # rendering set even when no widget overrides them explicitly.
    for fam in (project.font_defaults or {}).values():
        if isinstance(fam, str) and fam.strip():
            families_seen.add(fam.strip())

    # ``project.path`` is the active page .ctkproj — but that field
    # may not be set during programmatic flows (e.g. extract before
    # the loader runs). Fall back to the project folder's
    # project.json so the resolver still locates assets/.
    resolve_anchor = project.path or (
        project_meta_path(project.folder_path)
        if project.folder_path else None
    )
    for token in tokens:
        resolved = resolve_asset_token(token, resolve_anchor)
        if resolved is not None and resolved.exists():
            used.add(resolved.resolve())

    # Font family → file lookup. ``list_project_fonts`` returns
    # (family, path) for every .ttf/.otf in assets/, so we just
    # filter by family name. Skips system fonts (no matching file).
    if families_seen and resolve_anchor:
        for family, path in list_project_fonts(resolve_anchor):
            if family in families_seen and path.is_file():
                used.add(path.resolve())

    return used


def clone_project_folder(
    source_folder: str | Path,
    parent_dir: str | Path,
    new_name: str,
) -> Path:
    """Duplicate an entire project folder to ``<parent_dir>/<new_name>``.

    Copies project.json + assets/ + .backups/ + .autosave/ verbatim
    so the destination is a fully working multi-page project. The
    ``name`` field in project.json is rewritten to ``new_name`` so
    the duplicate doesn't masquerade as the original.

    Raises ``OSError`` if the destination folder already exists or
    can't be created. Caller surfaces the error to the user.
    """
    import shutil
    src = Path(source_folder)
    dest = Path(parent_dir) / new_name
    if dest.exists():
        raise OSError(f"Destination folder already exists: {dest}")
    shutil.copytree(src, dest)
    # Update project.json's name to match the new folder so the
    # duplicate carries a distinct identity. Pages list + ids are
    # left intact — they're internal references, no rename needed.
    try:
        meta = read_project_meta(dest)
        meta["name"] = new_name
        write_project_meta(dest, meta)
    except ProjectMetaError:
        log_error("clone_project_folder rename project.json")
    return dest


def extract_page_to_new_project(
    project,
    parent_dir: str | Path,
    new_name: str,
) -> Path:
    """Save the in-memory active page as a brand-new multi-page
    project at ``<parent_dir>/<new_name>``. Only assets referenced
    by the page travel with it — the rest of the source project's
    asset pool is left behind.

    Returns the new page's ``.ctkproj`` path so the caller can
    open it as the next active project.
    """
    import shutil
    from app.io.project_saver import save_project
    used = collect_used_assets(project)
    dest_folder, _, dest_page_path = bootstrap_project_folder(
        parent_dir, new_name,
    )
    # Copy each used asset into the matching subfolder under the
    # new project's assets/. Layout mirrors the source so
    # ``asset:images/foo.png`` tokens still resolve.
    src_assets_root: Path | None = None
    if project.path:
        from app.core.assets import project_assets_dir
        src_assets_root = project_assets_dir(project.path)
    if src_assets_root is None and project.folder_path:
        src_assets_root = Path(project.folder_path) / ASSETS_DIR_NAME
    dest_assets = dest_folder / ASSETS_DIR_NAME
    for src_file in used:
        if src_assets_root is None:
            continue
        try:
            rel = src_file.relative_to(src_assets_root.resolve())
        except ValueError:
            # Asset somehow lives outside the project pool — skip
            # rather than copy random files into the new project.
            continue
        target = dest_assets / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src_file, target)
        except OSError:
            log_error(f"extract_page copy {rel}")
    # Now save the in-memory project state into the new page file.
    # We mutate the live project briefly to point at the new
    # destination, then restore the originals. Avoids creating a
    # parallel Project class just to serialise.
    saved_path = project.path
    saved_folder = project.folder_path
    saved_pages = list(project.pages or [])
    saved_active = project.active_page_id
    saved_name = project.name
    try:
        project.path = str(dest_page_path)
        project.folder_path = str(dest_folder)
        # Re-seed metadata from the just-bootstrapped project.json
        # so save_project rewrites both files at the new location.
        seed_multi_page_meta_from_disk(project, str(dest_page_path))
        # Project name on the destination — match the folder.
        project.name = new_name
        save_project(project, str(dest_page_path))
    finally:
        # Restore in-memory state so the source project keeps
        # working when the caller decides not to switch over.
        project.path = saved_path
        project.folder_path = saved_folder
        project.pages = saved_pages
        project.active_page_id = saved_active
        project.name = saved_name
    return dest_page_path


def set_active_page(folder: str | Path, page_id: str) -> None:
    """Update ``project.json``'s ``active_page`` field. Used when
    switching pages so the next open lands on the right page.
    """
    folder = Path(folder)
    meta = read_project_meta(folder)
    if not any(
        isinstance(p, dict) and p.get("id") == page_id
        for p in (meta.get("pages") or [])
    ):
        raise ProjectMetaError(f"Page {page_id} not in project.")
    meta["active_page"] = page_id
    write_project_meta(folder, meta)
