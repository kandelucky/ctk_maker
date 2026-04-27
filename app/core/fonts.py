"""Custom font registration for CTkMaker projects.

Project fonts live inside ``<project>/assets/fonts/`` as raw .ttf /
.otf files. Tkinter cannot pick those up by file path — it only
knows fonts the OS / Tk already registered. ``tkextrafont`` is a
small Tcl extension that registers a font file with the running
Tk interpreter at runtime and exposes its family name(s) so
``CTkFont(family=...)`` can use it like any system font.

System-font lookup: ``resolve_system_font_path`` finds the on-disk
``.ttf`` for a given family name on Windows (via the Fonts registry
key). The font picker uses it so "+ Add system font" can copy the
file into the project's ``assets/fonts/`` folder rather than just
storing a bare reference — the project stays portable.

Lifecycle:

* On project load / save (when ``project.path`` becomes known),
  ``register_project_fonts`` walks the project's ``assets/fonts/``
  folder and loads every file. Files already loaded this session
  are skipped via the module-level cache.
* Family names are cached as ``{Path: family_name}`` so callers
  can map a project font filename back to the registered family
  if needed (currently unused — descriptors store the family name
  directly).

Graceful degradation: if ``tkextrafont`` import fails (the package
is missing or its native binary failed to load), every helper
returns an empty result and logs once. The Font picker still
shows system fonts — only project-bundled fonts are unavailable.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

from app.core.logger import log_error
from app.core.paths import ASSETS_DIR_NAME

FONT_EXTS = {".ttf", ".otf", ".ttc"}

_loaded_files: dict[Path, str] = {}
_extrafont_available: bool | None = None  # tri-state: None = unchecked

# Per-project font default cascade. Populated when a project loads;
# cleared when one closes / a new untitled would (we never reach that
# state today). Keys: "_all" (project-wide) and widget type_name
# strings ("CTkButton", "CTkLabel", ...). Resolved by
# ``resolve_effective_family`` — descriptors look up here so they
# don't need a back-reference to the Project instance.
_active_defaults: dict[str, str] = {}

ALL_DEFAULT_KEY = "_all"


def set_active_project_defaults(defaults: dict[str, str] | None) -> None:
    """Replace the active cascade. Called from project load + every
    time the user picks a font with scope=type/all in the picker.
    Empty dict resets the cascade to "no project defaults".
    """
    _active_defaults.clear()
    if defaults:
        _active_defaults.update(defaults)


def get_active_project_defaults() -> dict[str, str]:
    """Live snapshot of the cascade — callers should not mutate. Used
    by the picker to pre-select the right radio + show the current
    type/all default.
    """
    return dict(_active_defaults)


def resolve_effective_family(
    type_name: str | None, own_family: str | None,
) -> str | None:
    """Cascade: per-widget override > per-type default > project-wide
    default > Tk default (None).

    ``own_family`` is the value stored on the widget node — empty /
    ``None`` means "inherit". ``type_name`` is the descriptor's
    ``type_name`` (matched literally against keys in
    ``_active_defaults``); pass ``None`` when called outside a
    descriptor context to skip the per-type lookup.
    """
    if own_family:
        return own_family
    if type_name and _active_defaults.get(type_name):
        return _active_defaults[type_name]
    return _active_defaults.get(ALL_DEFAULT_KEY) or None


def purge_family_from_project(project, family: str) -> None:
    """Scrub every reference to ``family`` from the live project state
    after the underlying font file has been deleted. Without this,
    widgets keep pointing at a now-missing family and the canvas
    silently keeps drawing the cached glyphs until the next reload.

    - ``system_fonts`` entry removed
    - cascade defaults (``font_defaults``) pointing at the family cleared
    - per-widget ``font_family`` overrides cleared

    Caller is responsible for publishing ``font_defaults_changed`` so
    the workspace re-resolves cascades and rebuilds CTkFont objects.
    """
    if family in (project.system_fonts or []):
        project.system_fonts = [
            f for f in project.system_fonts if f != family
        ]
    new_defaults = {
        k: v for k, v in project.font_defaults.items() if v != family
    }
    if new_defaults != project.font_defaults:
        project.font_defaults = new_defaults
        set_active_project_defaults(new_defaults)
    for node in project.iter_all_widgets():
        if node.properties.get("font_family") == family:
            node.properties["font_family"] = None


def _check_extrafont() -> bool:
    """Probe tkextrafont once and cache the result."""
    global _extrafont_available
    if _extrafont_available is not None:
        return _extrafont_available
    try:
        import tkextrafont  # noqa: F401
        _extrafont_available = True
    except Exception:
        log_error("tkextrafont import")
        _extrafont_available = False
    return _extrafont_available


def register_font_file(
    path: str | Path, root: tk.Misc | None = None,
) -> str | None:
    """Register a single .ttf / .otf with the running Tk interpreter.

    Returns a family name to display in the picker. Resolution order:
    tkextrafont's reported family → PIL metadata (covers the
    ``already loaded`` case) → file stem as a last-resort label so
    the file at least shows up in the picker, even if Tk's actual
    family name for it can't be recovered. Same path passed twice in
    a session is a no-op — the cached family is returned.
    """
    path = Path(path).resolve()
    if path in _loaded_files:
        cached = _loaded_files[path]
        return cached if cached else None
    if not path.exists() or path.suffix.lower() not in FONT_EXTS:
        return None
    if not _check_extrafont():
        # No tkextrafont — fall back to PIL / stem so the file at
        # least appears in the picker (rendering will use Tk default
        # because the font isn't registered with the interpreter).
        family = _read_ttf_family(path) or path.stem
        _loaded_files[path] = family
        return family
    try:
        from tkextrafont import Font
        # Font(root, file=path) attaches to the given Tk root; if
        # omitted, uses the default root from tkinter._default_root.
        if root is not None:
            ef = Font(root, file=str(path))
        else:
            ef = Font(file=str(path))
        families = list(getattr(ef, "families", []) or [])
        family = families[0] if families else None
        if not family:
            # tkextrafont registered the file but didn't surface a
            # family — try metadata, then stem.
            family = _read_ttf_family(path) or path.stem
        _loaded_files[path] = family
        return family
    except Exception as exc:
        # tkextrafont raises ``Fontfile already loaded`` whenever the
        # exact file path was registered earlier this session — the
        # extension keeps its own registry independent of our cache,
        # and we can hit this on Save As / project re-open. The font
        # is in Tk; we just need its family name. Read it from the
        # .ttf metadata via PIL; if PIL also fails, use the file
        # stem so the user still sees the file in the picker.
        if "already loaded" in str(exc).lower():
            family = _read_ttf_family(path) or path.stem
            _loaded_files[path] = family
            return family
        log_error(f"register_font_file({path.name})")
        return None


def _read_ttf_family(path: Path) -> str | None:
    """Pull the font family name from a TrueType / OpenType file's
    own metadata. Used as a fallback when ``tkextrafont`` refuses to
    re-load a file we lost track of.
    """
    try:
        from PIL import ImageFont
        font = ImageFont.truetype(str(path), 12)
        names = font.getname()
        if names and names[0]:
            return str(names[0])
    except Exception:
        pass
    return None


def resolve_system_font_path(family: str) -> Path | None:
    """Locate the on-disk file backing a system-installed font family.
    Returns the absolute path to the regular face when known, or
    ``None`` if the family wasn't found / the OS isn't supported.

    Windows: walks the ``Fonts`` registry (HKLM and HKCU) for an
    entry whose face name (the bit before ``" (TrueType)"``) matches
    the requested family. Resolves the value to an absolute path
    under ``C:\\Windows\\Fonts`` when the registry stores just the
    filename.

    macOS / Linux: not implemented yet — returns ``None`` so the
    caller falls back to a ref-only registration.
    """
    import sys
    if sys.platform != "win32":
        return None
    try:
        import os
        import winreg
        target = family.strip().lower()
        windir = Path(os.environ.get("WINDIR", "C:\\Windows"))
        candidates: list[Path] = []
        for root_key, sub in (
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
            (winreg.HKEY_CURRENT_USER,
             r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
        ):
            try:
                key = winreg.OpenKey(root_key, sub)
            except OSError:
                continue
            try:
                count = winreg.QueryInfoKey(key)[1]
                for i in range(count):
                    name, value, _ = winreg.EnumValue(key, i)
                    # ``name`` looks like "Arial (TrueType)" or
                    # "Arial Bold (TrueType)" — the part before the
                    # parenthesis is the face name. Match the regular
                    # face exactly so we don't pick up a bold variant
                    # for a plain "Arial" request.
                    face = name.split("(")[0].strip().lower()
                    if face != target:
                        continue
                    if not isinstance(value, str) or not value:
                        continue
                    p = Path(value)
                    if not p.is_absolute():
                        p = windir / "Fonts" / value
                    if p.exists() and p.suffix.lower() in FONT_EXTS:
                        candidates.append(p)
            finally:
                winreg.CloseKey(key)
        # Prefer ``.ttf`` over ``.ttc`` (collections need a face index
        # which we don't have); fall back to whatever exists.
        for p in candidates:
            if p.suffix.lower() == ".ttf":
                return p
        return candidates[0] if candidates else None
    except Exception:
        log_error(f"resolve_system_font_path({family!r})")
        return None


def register_project_fonts(
    project_file: str | Path | None, root: tk.Misc | None = None,
) -> list[str]:
    """Walk ``<project>/assets/fonts/`` and register every font file.

    Returns the list of family names registered (or already cached).
    Untitled / missing project — returns empty list.
    """
    if not project_file:
        return []
    from app.core.assets import project_assets_dir
    assets = project_assets_dir(project_file)
    if assets is None:
        assets = Path(project_file).parent / ASSETS_DIR_NAME
    fonts_dir = assets / "fonts"
    if not fonts_dir.exists():
        return []
    families: list[str] = []
    for entry in sorted(fonts_dir.iterdir()):
        if not entry.is_file() or entry.suffix.lower() not in FONT_EXTS:
            continue
        family = register_font_file(entry, root=root)
        if family:
            families.append(family)
    return families


def list_project_fonts(
    project_file: str | Path | None,
    root: tk.Misc | None = None,
) -> list[tuple[str, Path]]:
    """Return ``(family_name, file_path)`` for every font file
    anywhere under the project's ``assets/`` folder. Recursive scan
    so user-organised folders (``assets/icons/``,
    ``assets/decorative/``) surface in the picker without needing the
    legacy fixed ``fonts/`` subfolder. Lazily registers freshly
    dropped-in files (drag-and-drop from the OS file manager between
    picker opens) so the dialog always reflects on-disk state. Falls
    back to the file stem when neither tkextrafont nor PIL can
    surface a family name — the file still appears in the picker,
    the user can still pick it, and rendering uses whatever Tk maps
    that string to.
    """
    if not project_file:
        return []
    from app.core.assets import project_assets_dir
    a_dir = project_assets_dir(project_file)
    if a_dir is None:
        a_dir = Path(project_file).parent / ASSETS_DIR_NAME
    if not a_dir.exists():
        return []
    out: list[tuple[str, Path]] = []
    for path in sorted(a_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in FONT_EXTS:
            continue
        resolved = path.resolve()
        family = _loaded_files.get(resolved)
        if not family:
            family = register_font_file(resolved, root=root) or path.stem
        out.append((family, path))
    return sorted(out, key=lambda t: t[0].lower())


def list_system_families(root: tk.Misc | None = None) -> list[str]:
    """Sorted list of system + already-registered font family names."""
    try:
        import tkinter.font as tkfont
        return sorted(set(tkfont.families(root)), key=str.lower)
    except Exception:
        log_error("list_system_families")
        return []
