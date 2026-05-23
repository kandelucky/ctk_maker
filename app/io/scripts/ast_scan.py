"""Read-only AST inspection of CTkScript files.

Surfaces:
- method names on a class (``parse_handler_methods``) — feeds the
  event Function picker.
- ``CTkScript`` subclasses in a file / folder
  (``parse_ctkscript_classes`` / ``find_attachable_scripts``) — feeds
  the script attach picker.

All entry points are robust to missing files / syntax errors — they
return empty containers rather than raising so caller code keeps the
builder responsive even when the user's script is mid-edit and
unparseable.
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.io.scripts._internals import _find_class, _read_source


def parse_handler_methods(
    file_path: str | Path,
    class_name: str,
) -> list[str]:
    """Return every method name defined directly under the named
    top-level class. Empty list if the file's missing, unparseable, or
    the class isn't there.
    """
    source = _read_source(file_path)
    if source is None:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    target = _find_class(tree, class_name)
    if target is None:
        return []
    names: list[str] = []
    for stmt in target.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(stmt.name)
    return names


def parse_ctkscript_classes(file_path: str | Path) -> list[str]:
    """Return the names of every top-level class in ``file_path`` that
    subclasses ``CTkScript`` — the attachable behavior classes of the
    CTkScript model. Recognises both ``class X(CTkScript)`` and
    ``class X(ctkmaker.CTkScript)``. Empty on missing file / syntax
    error / none found (keeps the attach picker responsive mid-edit).
    """
    source = _read_source(file_path)
    if source is None:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    names: list[str] = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.ClassDef):
            continue
        for base in stmt.bases:
            if isinstance(base, ast.Name) and base.id == "CTkScript":
                names.append(stmt.name)
                break
            if isinstance(base, ast.Attribute) and base.attr == "CTkScript":
                names.append(stmt.name)
                break
    return names


def find_attachable_scripts(scripts_dir: str | Path | None) -> list[tuple[str, str]]:
    """Scan a ``scripts/`` folder for attachable CTkScript classes.
    Returns ``[(rel_path, class_name)]`` — ``rel_path`` is POSIX,
    relative to ``scripts_dir`` (``counter.py``, ``sub/auth.py``), one
    entry per ``CTkScript`` subclass found. Sorted by path then class.
    Empty when the folder is absent. Skips ``__init__.py`` /
    ``__pycache__``.
    """
    if not scripts_dir:
        return []
    root = Path(scripts_dir)
    if not root.is_dir():
        return []
    out: list[tuple[str, str]] = []
    for py in sorted(root.rglob("*.py")):
        if py.name == "__init__.py" or "__pycache__" in py.parts:
            continue
        rel = py.relative_to(root).as_posix()
        for cls in parse_ctkscript_classes(py):
            out.append((rel, cls))
    return out
