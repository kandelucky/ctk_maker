"""Filesystem path conventions for CTkMaker projects.

A project on disk is a folder, not a single file:

    <ProjectsRoot>/<ProjectName>/
        <ProjectName>.ctkproj          # JSON state
        <ProjectName>.ctkproj.bak      # rotated backup (Layer 1)
        <ProjectName>.ctkproj.autosave # autosave (Layer 3, when dirty)
        assets/                        # project-local assets
            images/
            fonts/
            sounds/

`<ProjectsRoot>` defaults to `~/Documents/CTkMaker/` and can be
changed per-project via the New Project dialog. The folder is auto-
created on first New Project.
"""

from __future__ import annotations

from pathlib import Path

PROJECTS_ROOT_NAME = "CTkMaker"
ASSETS_DIR_NAME = "assets"
# Default folders auto-created on first save / project init. Sounds
# was here for v0.0.x but pulled until the audio playback story is
# real — no point shipping an empty folder users have to delete to
# clean up. Re-add when a CTkAudioPlayer / sound widget actually
# lands.
ASSET_SUBDIRS = ("images", "fonts")


def get_default_projects_dir() -> Path:
    """Return ``~/Documents/CTkMaker/``. Ensures the directory exists.

    Used as the default ``Save to`` location in the New Project
    dialog. Existing legacy projects on Desktop / elsewhere keep
    working — this path is just the suggested home for new ones.
    """
    docs = Path.home() / "Documents"
    root = docs / PROJECTS_ROOT_NAME
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Permission flip or read-only Documents — fall back to home
        # so the dialog still has somewhere to point at.
        root = Path.home() / PROJECTS_ROOT_NAME
        root.mkdir(parents=True, exist_ok=True)
    return root


def project_folder(parent_dir: str | Path, name: str) -> Path:
    """``<parent_dir>/<name>/`` — does not create."""
    return Path(parent_dir) / name


def project_file_in_folder(folder: str | Path, name: str) -> Path:
    """``<folder>/<name>.ctkproj`` — does not create."""
    return Path(folder) / f"{name}.ctkproj"


def assets_dir(project_file: str | Path) -> Path:
    """``<project_folder>/assets/`` for a given project file path.
    Caller decides whether to create.
    """
    return Path(project_file).parent / ASSETS_DIR_NAME


def ensure_project_folder(folder: str | Path) -> Path:
    """Create the project folder + ``assets/`` skeleton if missing.

    Idempotent. Returns the folder path.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    assets = folder / ASSETS_DIR_NAME
    assets.mkdir(exist_ok=True)
    for sub in ASSET_SUBDIRS:
        (assets / sub).mkdir(exist_ok=True)
    return folder
