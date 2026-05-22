"""Behavior-file mutations — annotation / import / method-stub edits.

Text-based whenever a write touches user content (Decision K=B) so
blank lines + comments survive. AST is used for *finding* the right
spot; the actual splice is line-list slicing.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app.io.scripts._internals import (
    _detect_body_indent,
    _find_class,
    _read_source,
)


def ensure_imports_in_behavior_file(
    file_path: str | Path,
    imports: list[tuple[str, str]],
) -> bool:
    """Make sure each ``(module, name)`` import in ``imports`` is
    present in the file. Adds missing ones at the top — after the
    module docstring + any ``from __future__`` lines, before the
    first regular statement. Existing imports are detected via AST
    so duplicate adds don't accumulate.

    Returns ``True`` on success (even when no edits were needed).
    Returns ``False`` for missing files / parse failures / write
    errors.
    """
    path = Path(file_path)
    source = _read_source(path)
    if source is None:
        return False
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    # Collect existing ``from <module> import <name>`` pairs so we
    # know which entries to skip.
    existing: set[tuple[str, str]] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.ImportFrom) and stmt.module:
            for alias in stmt.names:
                # Use the original name (not asname) — the dialog
                # always writes plain ``ref`` / ``CTkLabel`` so an
                # ``import as`` alias would still need its own row.
                existing.add((stmt.module, alias.name))
    missing = [
        (m, n) for m, n in imports if (m, n) not in existing
    ]
    if not missing:
        return True
    # Pick the insertion line: after the module docstring (when
    # present) and after any ``from __future__ import …`` lines.
    # Anchor on the first non-future, non-docstring top-level
    # statement.
    insert_at_line = 1
    if tree.body:
        first = tree.body[0]
        # Module docstring lands as Expr(Constant(str)) at body[0].
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            insert_at_line = (first.end_lineno or 1) + 1
    # Skip ``from __future__`` block — those must remain first.
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.ImportFrom)
            and stmt.module == "__future__"
        ):
            insert_at_line = max(
                insert_at_line, (stmt.end_lineno or 1) + 1,
            )
    lines = source.splitlines()
    # Group imports by module so multiple ``from X import a, b`` land
    # together — matches PEP 8 stylistic preference.
    by_module: dict[str, list[str]] = {}
    for module, name in missing:
        by_module.setdefault(module, []).append(name)
    new_blocks: list[str] = []
    # Add a blank line above the import block when the slot it
    # lands in isn't already empty — avoids welding the new lines
    # to whatever comes right above (docstring close-quote, future
    # import, etc.).
    if insert_at_line - 1 < len(lines):
        prev_line = lines[insert_at_line - 1 - 1] if (
            insert_at_line - 1 - 1 >= 0
        ) else ""
        if prev_line.strip():
            new_blocks.append("")
    for module, names in by_module.items():
        joined = ", ".join(names)
        new_blocks.append(f"from {module} import {joined}")
    # Trailing blank line so the class definition below has its
    # usual two-line spacing.
    if (
        insert_at_line - 1 < len(lines)
        and lines[insert_at_line - 1].strip()
    ):
        new_blocks.append("")
    insert_idx = max(0, insert_at_line - 1)
    new_lines = lines[:insert_idx] + new_blocks + lines[insert_idx:]
    new_source = "\n".join(new_lines)
    if source.endswith("\n") and not new_source.endswith("\n"):
        new_source += "\n"
    try:
        path.write_text(new_source, encoding="utf-8")
    except OSError:
        return False
    return True


def ensure_relative_import_in_behavior_file(
    file_path: str | Path,
    level: int,
    module: str,
    name: str,
) -> bool:
    """Make sure ``from <"."*level><module> import <name>`` is
    present in the file. Idempotent: scans existing ImportFrom AST
    nodes by level + module + name tuple before deciding to write.

    The ``level`` arg is the number of leading dots (1 = ``.``,
    2 = ``..``); ``module`` may be empty when the relative import
    targets the package itself (``from .. import foo`` style) but
    Phase 3 only uses the ``from .._runtime import ref`` variant
    so the helper requires a non-empty submodule name.

    Insertion lands right after the docstring + future imports —
    same anchor logic ``ensure_imports_in_behavior_file`` uses for
    absolute imports — so a freshly created behavior file ends up
    with imports clustered cleanly at the top.
    """
    if not module:
        return False
    path = Path(file_path)
    source = _read_source(path)
    if source is None:
        return False
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.ImportFrom)
            and (stmt.level or 0) == level
            and stmt.module == module
        ):
            for alias in stmt.names:
                if alias.name == name:
                    return True
    insert_at_line = 1
    if tree.body:
        first = tree.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            insert_at_line = (first.end_lineno or 1) + 1
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.ImportFrom)
            and stmt.module == "__future__"
        ):
            insert_at_line = max(
                insert_at_line, (stmt.end_lineno or 1) + 1,
            )
    lines = source.splitlines()
    new_blocks: list[str] = []
    if insert_at_line - 1 - 1 >= 0:
        prev_line = lines[insert_at_line - 1 - 1]
        if prev_line.strip():
            new_blocks.append("")
    dots = "." * max(1, level)
    new_blocks.append(f"from {dots}{module} import {name}")
    if (
        insert_at_line - 1 < len(lines)
        and lines[insert_at_line - 1].strip()
    ):
        new_blocks.append("")
    insert_idx = max(0, insert_at_line - 1)
    new_lines = lines[:insert_idx] + new_blocks + lines[insert_idx:]
    new_source = "\n".join(new_lines)
    if source.endswith("\n") and not new_source.endswith("\n"):
        new_source += "\n"
    try:
        path.write_text(new_source, encoding="utf-8")
    except OSError:
        return False
    return True


def delete_method_from_file(
    file_path: str | Path,
    class_name: str,
    method_name: str,
) -> bool:
    """Text-based method removal (Decision K=B — preserves user's
    blank lines + comments that ``ast.unparse`` round-trip would
    drop). Walks the source line-by-line, detects the ``def`` line
    indent, then drops every following line that's blank, more
    indented than the def, or empty until the next non-blank line
    sits at the def's indent or shallower. Returns ``True`` when
    the method was found + removed, ``False`` for missing files /
    parse failures / when the method isn't there.
    """
    path = Path(file_path)
    source = _read_source(path)
    if source is None:
        return False
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    target = _find_class(tree, class_name)
    if target is None:
        return False
    func = None
    for stmt in target.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if stmt.name == method_name:
                func = stmt
                break
    if func is None:
        return False
    lines = source.splitlines()
    start = func.lineno - 1
    # Include any leading decorator lines so we don't strand them
    # alone above the slot we're cutting.
    if func.decorator_list:
        first_dec = min(d.lineno for d in func.decorator_list) - 1
        start = min(start, first_dec)
    # ``end_lineno`` is 1-based and inclusive of the last body
    # line. ast tracks the body proper but ignores trailing blank
    # lines that visually belong to the method — sweep them too so
    # the file doesn't end up with stranded gaps.
    end = (func.end_lineno or len(lines)) - 1
    while end + 1 < len(lines) and not lines[end + 1].strip():
        end += 1
    new_lines = lines[:start] + lines[end + 1:]
    new_source = "\n".join(new_lines)
    if source.endswith("\n") and not new_source.endswith("\n"):
        new_source += "\n"
    try:
        path.write_text(new_source, encoding="utf-8")
    except OSError:
        return False
    return True


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
# Method-name resolution
# ---------------------------------------------------------------------
def slugify_method_part(text: str) -> str:
    """Lowercase, strip every non-``[a-z0-9_]`` character, prefix
    underscore when the result starts with a digit. Empty input falls
    back to ``"x"`` so the caller always gets a usable identifier
    fragment.

    Used to turn widget / window display names into method-name parts
    that Python's grammar accepts.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", text or "").strip("_").lower()
    if not cleaned:
        return "x"
    if cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned


def collect_used_method_names(document) -> set[str]:
    """Walk one Document's widget tree and return every method name
    currently bound to a handler. Per-window scoping (Decision #13)
    means collisions are checked only within this Document — each
    window owns its own behavior class.
    """
    used: set[str] = set()
    if document is None:
        return used
    _walk_collect_handlers(document.root_widgets, used)
    return used


def _walk_collect_handlers(nodes, used: set[str]) -> None:
    for n in nodes:
        for methods in n.handlers.values():
            for m in methods:
                if m:
                    used.add(m)
        _walk_collect_handlers(n.children, used)


def suggest_method_name(node, event_entry, document) -> str:
    """Smart naming (Decision #15):
    - Default: ``on_<widget_slug>_<verb>``.
    - On collision within the window's own bound methods, append
      ``_2`` / ``_3`` until free. No cross-window prefix — per-window
      classes mean each Document has its own namespace.

    ``event_entry`` is an ``EventEntry`` from
    ``app.widgets.event_registry``. ``document`` is the Document the
    widget belongs to.
    """
    widget_part = slugify_method_part(node.name or node.widget_type)
    verb = event_entry.verb
    base = f"on_{widget_part}_{verb}"
    used = collect_used_method_names(document)
    if base not in used:
        return base
    n = 2
    while f"{base}_{n}" in used:
        n += 1
    return f"{base}_{n}"
