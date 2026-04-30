"""Read / write the per-page behavior file.

A behavior file holds the user-written Python that backs widget event
handlers. CTkMaker generates method skeletons; the user writes the
bodies in their own editor. The file lives at
``<project>/scripts/<page>.py`` and is imported by exported code as
``from .scripts.<page> import <PageClass>``.

Public API:
- ``load_or_create_behavior_file(project_path)`` — return the .py path,
  creating ``scripts/`` + a class skeleton if missing
- ``parse_handler_methods(file_path, class_name)`` — list method names
  on the named top-level class. Robust to syntax errors (returns ``[]``)
- ``add_handler_stub(file_path, class_name, method_name, signature)`` —
  append ``def <name><sig>: pass`` to the class. Returns the new
  method's 1-based line number, or ``None`` on failure
- ``find_handler_method(file_path, class_name, method_name)`` —
  1-based line of an existing method, or ``None``

The AST scan only looks at top-level ``ClassDef`` nodes. Decorated /
async / nested defs are surfaced as method names too — the user's
free to use them, we don't try to be opinionated about Python style
inside their file. Syntax errors anywhere in the source mean we
return empty / None rather than crashing the builder.
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.core.script_paths import (
    behavior_class_name,
    behavior_file_path,
    behavior_file_stem,
    ensure_scripts_root,
)

# Skeleton template written on first handler attach. Plain string —
# no f-string at module level so the literal ``{class_name}`` markers
# stay intact for ``.format`` at call time.
_SKELETON_TEMPLATE = '''"""Behavior file for the {page_label} page.

Methods here run in response to widget events. CTkMaker stubs new
methods automatically when you right-click a widget → Add handler;
fill in the bodies here. Each method maps to a handler binding
configured in the Properties panel.
"""


class {class_name}:
    def setup(self, window):
        """Called once on page load. Stash references you'll need."""
        self.window = window
'''


def load_or_create_behavior_file(
    project_file_path: str | Path | None,
) -> Path | None:
    """Return the behavior-file path, creating the scripts/ folder
    and writing a class skeleton if the .py is missing. ``None`` for
    unsaved projects.
    """
    if not project_file_path:
        return None
    if ensure_scripts_root(project_file_path) is None:
        return None
    file_path = behavior_file_path(project_file_path)
    if file_path is None:
        return None
    if file_path.exists():
        return file_path
    skeleton = _SKELETON_TEMPLATE.format(
        class_name=behavior_class_name(project_file_path),
        page_label=behavior_file_stem(project_file_path),
    )
    try:
        file_path.write_text(skeleton, encoding="utf-8")
    except OSError:
        return None
    return file_path


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


def find_handler_method(
    file_path: str | Path,
    class_name: str,
    method_name: str,
) -> int | None:
    """1-based line of ``def <method>`` inside ``<class>``, or
    ``None`` when missing / unparseable.
    """
    source = _read_source(file_path)
    if source is None:
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    target = _find_class(tree, class_name)
    if target is None:
        return None
    for stmt in target.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if stmt.name == method_name:
                return stmt.lineno
    return None


def add_handler_stub(
    file_path: str | Path,
    class_name: str,
    method_name: str,
    signature: str = "(self)",
) -> int | None:
    """Append ``def <method><signature>: pass`` to the named class.
    No-op when the method already exists — its existing line is
    returned. Returns ``None`` on read/parse/write failure or when
    the class isn't found.

    Insertion lands at the end of the class body, indented to match
    existing body statements (defaults to four spaces when the body
    is empty / only ``pass``).
    """
    path = Path(file_path)
    source = _read_source(path)
    if source is None:
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    target = _find_class(tree, class_name)
    if target is None:
        return None
    # Already present — return the existing method's line and don't
    # mutate the file. Caller treats "already there" the same as a
    # successful add.
    for stmt in target.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if stmt.name == method_name:
                return stmt.lineno

    lines = source.splitlines()
    body_indent = _detect_body_indent(target, lines)
    new_block = [
        "",
        f"{body_indent}def {method_name}{signature}:",
        f"{body_indent}    pass",
    ]
    # ``end_lineno`` is 1-based and points at the last line OF the
    # class body. Inserting at the same 0-based index puts the new
    # block right after that final line, still under the class
    # because the indent matches body_indent.
    insertion_idx = (target.end_lineno or len(lines))
    new_lines = lines[:insertion_idx] + new_block + lines[insertion_idx:]
    new_source = "\n".join(new_lines)
    if not new_source.endswith("\n"):
        new_source += "\n"
    try:
        path.write_text(new_source, encoding="utf-8")
    except OSError:
        return None
    # The blank line goes at insertion_idx; the ``def`` follows it.
    return insertion_idx + 2


# ---------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------
def _read_source(file_path: str | Path) -> str | None:
    try:
        return Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return None


def _find_class(tree: ast.Module, class_name: str) -> ast.ClassDef | None:
    for top in tree.body:
        if isinstance(top, ast.ClassDef) and top.name == class_name:
            return top
    return None


def _detect_body_indent(
    cls: ast.ClassDef, lines: list[str],
) -> str:
    """Use the first body statement's leading whitespace as our indent.
    Empty / pass-only classes fall back to four spaces — Python's
    PEP 8 default and what the skeleton template emits.
    """
    if not cls.body:
        return "    "
    first = cls.body[0]
    line_idx = first.lineno - 1
    if line_idx < 0 or line_idx >= len(lines):
        return "    "
    raw = lines[line_idx]
    stripped = raw.lstrip()
    return raw[: len(raw) - len(stripped)] or "    "
