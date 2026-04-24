"""Asset token + copy helpers for project-portable image references.

A project's images live inside ``<project_folder>/assets/images/`` and
are referenced in the project JSON via ``asset:images/<filename>``
tokens. Tokens stay portable: moving the project folder, sending the
exported `.py` to another machine, or renaming the source file on
disk all work because the runtime resolves the token through the
project's own folder rather than an absolute path baked into the JSON.

Token <-> absolute path conversions happen at the save/load boundary
(see ``project_saver`` / ``project_loader``) so widget descriptors
keep seeing plain absolute paths in memory and don't need to know
the asset system exists.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from app.core.paths import ASSETS_DIR_NAME

ASSET_PREFIX = "asset:"


def is_asset_token(value) -> bool:
    return isinstance(value, str) and value.startswith(ASSET_PREFIX)


def parse_asset_token(token: str) -> str:
    """Return the assets-relative path inside the token (e.g.
    ``images/photo.png``).
    """
    return token[len(ASSET_PREFIX):]


def make_asset_token(rel_path: str) -> str:
    """Wrap an assets-relative path as a token. Always uses forward
    slashes so JSON stays platform-stable.
    """
    return ASSET_PREFIX + rel_path.replace("\\", "/")


def resolve_asset_token(
    token: str, project_file: str | Path | None,
) -> Path | None:
    """Convert ``asset:images/photo.png`` to an absolute path inside
    the project folder. Returns ``None`` if no project path is known
    (untitled state) or the token is malformed.
    """
    if not is_asset_token(token) or not project_file:
        return None
    rel = parse_asset_token(token)
    if not rel:
        return None
    return Path(project_file).parent / ASSETS_DIR_NAME / rel


def absolute_to_token(
    abs_path: str | Path, project_file: str | Path | None,
) -> str | None:
    """If ``abs_path`` lives inside ``<project>/assets/``, return the
    matching token. Otherwise ``None`` — the caller decides whether
    to leave the absolute path alone or refuse the save.
    """
    if not project_file or not abs_path:
        return None
    project_assets = Path(project_file).parent / ASSETS_DIR_NAME
    try:
        rel = Path(abs_path).resolve().relative_to(
            project_assets.resolve(),
        )
    except (OSError, ValueError):
        return None
    return make_asset_token(str(rel).replace("\\", "/"))


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_to_assets(
    src: str | Path,
    project_file: str | Path,
    subdir: str = "images",
) -> str:
    """Copy ``src`` into ``<project>/assets/<subdir>/`` (deduped by
    SHA256 — same content reuses the existing entry) and return the
    matching ``asset:<subdir>/<filename>`` token.

    Filename collisions resolve with a `_2`, `_3` suffix before the
    extension when the existing file at the same name has different
    content.
    """
    src = Path(src)
    target_dir = Path(project_file).parent / ASSETS_DIR_NAME / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    sha = sha256_of_file(src)
    # Dedupe: if a same-content file already lives here, reuse it.
    for existing in target_dir.iterdir():
        if not existing.is_file():
            continue
        try:
            if sha256_of_file(existing) == sha:
                return make_asset_token(f"{subdir}/{existing.name}")
        except OSError:
            continue
    # Pick a unique filename (handle collisions by suffix).
    dst = target_dir / src.name
    if dst.exists():
        stem = dst.stem
        suffix = dst.suffix
        n = 2
        while True:
            dst = target_dir / f"{stem}_{n}{suffix}"
            if not dst.exists():
                break
            n += 1
    shutil.copy2(src, dst)
    return make_asset_token(f"{subdir}/{dst.name}")
