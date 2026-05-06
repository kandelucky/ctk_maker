"""Read / write the per-window behavior file.

A behavior file holds the user-written Python that backs widget event
handlers. CTkMaker generates method skeletons; the user writes the
bodies in their own editor. The file lives at
``<project>/assets/scripts/<page>/<window>.py`` (one per Document)
and is imported by exported code as
``from assets.scripts.<page>.<window> import <WindowName>Page``.

Object References (v1.10.8+) — annotated class attributes typed as
``ref[<WidgetType>]`` declare Inspector slots that pair with entries
in the document's ``local_object_references``. Resolution happens at
export time via ``self._behavior.<field> = self.<widget_var>`` lines
after ``_build_ui()``. The ``ref`` marker class lives in an
auto-generated ``assets/scripts/_runtime.py`` so behavior files stay
importable outside CTkMaker (IDE typing, standalone tests, etc.).

Public API:
- ``load_or_create_behavior_file(project_path, document)`` — return
  the .py path, creating ``assets/scripts/<page>/`` + a class
  skeleton if missing
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
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from app.core.script_paths import (
    behavior_class_name,
    behavior_file_path,
    ensure_scripts_root,
    scripts_root,
    slugify_window_name,
)

# Skeleton template written on first handler attach (or eager on
# document creation). Plain string — no f-string at module level so
# the literal ``{class_name}`` markers stay intact for ``.format``
# at call time.
_SKELETON_TEMPLATE = '''"""Behavior file for the {window_label} window.

Methods here run in response to widget events. CTkMaker stubs new
methods automatically — fill in the bodies here. Each method maps
to a handler binding configured in the Properties panel.

To bind a widget as an Inspector slot, declare a ``ref[<WidgetType>]``
annotation on the class (e.g. ``target_label: ref[CTkLabel]``) and
add a matching entry in the Properties panel's Object References
group. Import ``ref`` from the auto-generated ``_runtime`` module
and the widget class from ``customtkinter``.
"""


class {class_name}:
    def setup(self, window):
        """Called once after the UI is built and Object References
        are wired. ``self.<field>`` slots and ``window.<widget>``
        attributes are both available at this point.
        """
        self.window = window
'''


def load_or_create_behavior_file(
    project_file_path: str | Path | None,
    document=None,
) -> Path | None:
    """Return the behavior-file path, creating the page subfolder and
    writing a class skeleton if the .py is missing. ``None`` for
    unsaved projects.

    ``document`` controls the filename + class name (per-window
    scope, Decision #13). When ``document`` is ``None`` the call is
    a no-op probe — useful for callers that just want to know
    whether the file would land in a writable location.
    """
    if not project_file_path:
        return None
    if ensure_scripts_root(project_file_path) is None:
        return None
    # Drop ``_runtime.py`` next to the per-page subfolders so Object
    # Reference annotations (``target: ref[CTkLabel]``) have an
    # importable ``ref`` marker. Idempotent: existing file is left
    # untouched. Runs on every behavior-file create so older projects
    # pick it up the first time the user adds any handler without a
    # separate migration step.
    ensure_runtime_helpers(project_file_path)
    file_path = behavior_file_path(project_file_path, document)
    if file_path is None:
        return None
    if file_path.exists():
        return file_path
    window_label = (
        getattr(document, "name", None) or "Window"
    )
    skeleton = _SKELETON_TEMPLATE.format(
        class_name=behavior_class_name(document),
        window_label=window_label,
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


# ---------------------------------------------------------------------
# Object Reference annotation parser (v1.10.8+)
#
# Reserved — currently no callers. The legacy Behavior Field add
# dialog consumed ``parse_object_reference_fields`` and
# ``existing_object_reference_names`` for live introspection of
# annotated attributes; the modern Object Reference flow tracks
# existing names via ``doc.local_object_references`` directly and
# generates new names via ``app.core.object_references.suggest_ref_name``.
# Keep these helpers around for a future orphan-detection /
# annotation-reconcile feature that would AST-scan the .py file and
# surface mismatches between annotations and the model
# (e.g., the U3-style stale-annotation diagnostic).
# ---------------------------------------------------------------------
class FieldSpec:
    """One Inspector-bindable annotation found on a behavior class.

    ``name`` is the Python attribute name; ``type_name`` is the
    referenced widget type (e.g., ``"CTkLabel"``) extracted from
    ``ref[<TypeName>]``; ``lineno`` is the 1-based source line for
    F7-style jump (0 when unknown).
    """

    __slots__ = ("name", "type_name", "lineno")

    def __init__(self, name: str, type_name: str, lineno: int = 0) -> None:
        self.name = name
        self.type_name = type_name
        self.lineno = lineno


def parse_object_reference_fields(
    file_path: str | Path,
    class_name: str,
) -> list[FieldSpec]:
    """Scan a behavior file for ``<name>: ref[<TypeName>]`` annotations
    on the named top-level class. Returns one ``FieldSpec`` per match
    in source order. Empty list when the file's missing, unparseable,
    the class isn't there, or no ref-annotations were declared.

    The scanner only recognises the bare ``ref[<Name>]`` shape — bare
    type hints (``target: CTkLabel``) and ``Optional[ref[CTkLabel]]``
    style wraps are intentionally ignored so the user can still keep
    plain Python typing on attributes without exposing them as
    Inspector slots.
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
    out: list[FieldSpec] = []
    for stmt in target.body:
        if not isinstance(stmt, ast.AnnAssign):
            continue
        if not isinstance(stmt.target, ast.Name):
            continue
        type_name = _extract_ref_type(stmt.annotation)
        if type_name is None:
            continue
        out.append(FieldSpec(stmt.target.id, type_name, stmt.lineno))
    return out


def _extract_ref_type(annotation: ast.expr) -> str | None:
    """Return the inner type name from ``ref[<Name>]``. ``None`` when
    the annotation isn't a ref subscript or the slice isn't a bare
    ``Name`` node — anything more elaborate (parametrised generics,
    string literals, attribute access) falls outside the supported
    surface for v1.
    """
    if not isinstance(annotation, ast.Subscript):
        return None
    value = annotation.value
    if not isinstance(value, ast.Name) or value.id != "ref":
        return None
    slice_node = annotation.slice
    if isinstance(slice_node, ast.Name):
        return slice_node.id
    return None


def existing_object_reference_names(
    file_path: str | Path,
    class_name: str,
) -> set[str]:
    """Names of every annotated attribute on the named class — both
    the ``ref`` slots Phase 3 cares about + plain typed attributes
    the user might have declared. Used by the Add Field dialog to
    detect collisions before writing a new annotation. Robust to
    syntax errors / missing files (returns ``set()``).
    """
    source = _read_source(file_path)
    if source is None:
        return set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    target = _find_class(tree, class_name)
    if target is None:
        return set()
    out: set[str] = set()
    for stmt in target.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(
            stmt.target, ast.Name,
        ):
            out.add(stmt.target.id)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Methods can collide with fields — the runtime would
            # silently shadow one with the other. Treat them as
            # blocked names so the dialog refuses both directions.
            out.add(stmt.name)
    return out


def add_object_reference_annotation(
    file_path: str | Path,
    class_name: str,
    field_name: str,
    type_name: str,
) -> bool:
    """Insert ``<field_name>: ref[<type_name>]`` near the top of the
    named class, preserving the user's blank lines + comments.

    Insertion strategy: land the annotation right above the first
    method of the class. When the class has no methods (just a
    ``pass`` placeholder or only annotations), append at the end of
    the class body. Indent is detected from the first body
    statement and falls back to four spaces for empty classes.

    Idempotent — returns ``True`` unconditionally on success even
    when the field already existed (caller checks
    ``existing_object_reference_names`` first to surface the collision
    to the user). Returns ``False`` for missing files / parse
    failures / write errors.
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
    lines = source.splitlines()
    body_indent = _detect_body_indent(target, lines)
    annotation_line = (
        f"{body_indent}{field_name}: ref[{type_name}]"
    )
    # Find the first FunctionDef so we can drop the annotation right
    # above the methods cluster. Python's stdlib styling puts
    # annotated attributes at the top of the class body — matching
    # that convention keeps generated + hand-written code visually
    # consistent.
    first_method = None
    for stmt in target.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            first_method = stmt
            break
    if first_method is not None:
        insert_idx = first_method.lineno - 1
        # ast tracks decorators as separate top-of-method anchors —
        # the actual visible "def" line might come after them. Pick
        # the earliest line so we don't tunnel between a decorator
        # and its function.
        if first_method.decorator_list:
            first_dec = min(
                d.lineno for d in first_method.decorator_list
            )
            insert_idx = first_dec - 1
        # Drop the annotation + a blank line so it doesn't touch the
        # def below; cleaner read in the editor.
        new_lines = (
            lines[:insert_idx]
            + [annotation_line, ""]
            + lines[insert_idx:]
        )
    else:
        # Empty / placeholder body — replace any trailing ``pass``
        # statement with the annotation, otherwise append. Either
        # way the annotation lands inside the class body because
        # body_indent matches.
        end_idx = (target.end_lineno or len(lines))
        # Trim a trailing blank line so the new annotation joins
        # the class body cleanly.
        prev = lines[end_idx - 1] if end_idx <= len(lines) else ""
        if prev.strip() == "pass":
            new_lines = (
                lines[:end_idx - 1]
                + [annotation_line]
                + lines[end_idx:]
            )
        else:
            new_lines = (
                lines[:end_idx]
                + [annotation_line]
                + lines[end_idx:]
            )
    new_source = "\n".join(new_lines)
    if source.endswith("\n") and not new_source.endswith("\n"):
        new_source += "\n"
    try:
        path.write_text(new_source, encoding="utf-8")
    except OSError:
        return False
    return True


def delete_object_reference_annotation(
    file_path: str | Path,
    class_name: str,
    field_name: str,
) -> bool:
    """Remove a single ``<field_name>: <annotation>`` line from the
    named class. Text-based delete (Decision K=B) — preserves the
    user's blank lines + comments inside the class. Returns
    ``True`` when a line was removed, ``False`` for missing files /
    parse failures / when the annotation isn't there.
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
    ann = None
    for stmt in target.body:
        if (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.target.id == field_name
        ):
            ann = stmt
            break
    if ann is None:
        return False
    lines = source.splitlines()
    start = ann.lineno - 1
    end = (ann.end_lineno or ann.lineno) - 1
    # Sweep one trailing blank line so the annotation block doesn't
    # leave a visible gap in the class body — keeps the code tidy
    # for users who delete several fields back-to-back.
    if end + 1 < len(lines) and not lines[end + 1].strip():
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


def suggest_object_reference_name(
    widget_name: str,
    widget_type: str,
    existing_names: set[str],
) -> str:
    """Slugify the widget's display name into a Python identifier
    suitable as a field name. Falls back to the widget's type when
    name is empty. Auto-suffixes ``_2`` / ``_3`` on collision so the
    dialog presents a name the user can accept or edit without
    triggering an error.

    Reserved — no current callers. The modern Object Reference flow
    uses ``app.core.object_references.suggest_ref_name`` which has
    different semantics (CTk-prefix stripping, slightly different
    fallback). Kept here for a future orphan-reconcile pass.
    """
    base_source = widget_name.strip() if widget_name else ""
    if not base_source:
        # CTkLabel → ctk_label; Image → image
        base_source = widget_type
    base = slugify_method_part(base_source)
    if base not in existing_names:
        return base
    n = 2
    while f"{base}_{n}" in existing_names:
        n += 1
    return f"{base}_{n}"


# ---------------------------------------------------------------------
# Runtime helpers — `ref` marker class shipped with each project
# ---------------------------------------------------------------------
_RUNTIME_MODULE_NAME = "_runtime.py"
_RUNTIME_TEMPLATE = '''"""CTkMaker behavior-runtime helpers — auto-generated.

The ``ref`` marker lets behavior files declare Inspector-bindable
attributes without forcing a CTkMaker package install. CTkMaker
detects ``<name>: ref[<WidgetType>]`` annotations at parse time and
exposes them as widget picker slots in the Properties panel; the
exported app then assigns the real widget to each slot at runtime.

Edits to this file are overwritten when CTkMaker regenerates it.
"""
from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class ref(Generic[T]):
    """Inspector-bindable widget reference marker.

    Has no runtime behavior on its own — annotations of the form
    ``target: ref[CTkLabel]`` are resolved by the exporter into
    ``self._behavior.target = self.<widget_var>`` assignments after
    the UI is built.
    """

    pass
'''


def ensure_runtime_helpers(
    project_file_path: str | Path | None,
) -> Path | None:
    """Write ``<project>/assets/scripts/_runtime.py`` if missing.
    Idempotent — does not overwrite an existing file (so user edits
    survive even though the docstring warns otherwise; a future
    "regenerate runtime" command can clobber explicitly). Returns
    the runtime-file path on success, ``None`` for unsaved projects
    or write failures.
    """
    if not project_file_path:
        return None
    # Run ensure_scripts_root() for the side effect of creating the
    # __init__.py at both ``scripts/`` and ``scripts/<page>/`` so the
    # ``from assets.scripts.<page>.<window>`` import resolves; its
    # return value is the per-page subfolder, which is the wrong
    # level for ``_runtime.py``. Drop the helper at the parent root
    # so behavior files' ``from .._runtime import ref`` resolves.
    if ensure_scripts_root(project_file_path) is None:
        return None
    root = scripts_root(project_file_path)
    if root is None:
        return None
    runtime_path = root / _RUNTIME_MODULE_NAME
    if runtime_path.exists():
        return runtime_path
    try:
        runtime_path.write_text(_RUNTIME_TEMPLATE, encoding="utf-8")
    except OSError:
        return None
    return runtime_path


def parse_method_docstrings(
    file_path: str | Path,
    class_name: str,
) -> dict[str, str]:
    """Return ``{method_name: first_docstring_line}`` for every
    method on the named class that carries a docstring. Used by the
    Properties panel "Events" group to surface a human description
    next to each bound method ("Reset login form" beats
    "on_button_click_2"). Methods without a docstring are absent
    from the map — the caller falls back to the bare method name.
    Robust to syntax errors / missing files (returns ``{}``).
    """
    source = _read_source(file_path)
    if source is None:
        return {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    target = _find_class(tree, class_name)
    if target is None:
        return {}
    out: dict[str, str] = {}
    for stmt in target.body:
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(stmt)
        if not doc:
            continue
        first = doc.strip().splitlines()[0].strip()
        if first:
            out[stmt.name] = first
    return out


def rename_behavior_file_and_class(
    project_file_path: str | Path | None,
    old_name: str,
    new_name: str,
) -> Path | None:
    """Phase 2 Step 3 — rename ``<page>/<old_slug>.py`` →
    ``<page>/<new_slug>.py`` and rewrite ``class <OldName>Page`` →
    ``class <NewName>Page`` inside the file. Returns the new path
    on success, ``None`` when the source file doesn't exist (legacy
    docs that never gained a behavior file) or the rename hit a
    collision / write error.

    The class rewrite uses a plain string replace against the
    expected ``class <Old>Page`` token rather than an AST round-trip
    so the user's blank lines + comments survive untouched.
    """
    from app.core.script_paths import (
        behavior_class_name,
        behavior_file_path,
        slugify_window_name,
    )

    class _Stub:
        def __init__(self, name: str):
            self.name = name

    old_path = behavior_file_path(project_file_path, _Stub(old_name))
    new_path = behavior_file_path(project_file_path, _Stub(new_name))
    if old_path is None or new_path is None:
        return None
    if not old_path.exists():
        return None
    if slugify_window_name(old_name) == slugify_window_name(new_name):
        # Display-name change that collapses to the same slug — no
        # rename needed, but still rewrite the class declaration so
        # the PascalCase identifier matches the user's intent.
        try:
            source = old_path.read_text(encoding="utf-8")
        except OSError:
            return None
        old_class = behavior_class_name(_Stub(old_name))
        new_class = behavior_class_name(_Stub(new_name))
        if old_class != new_class:
            updated = source.replace(
                f"class {old_class}", f"class {new_class}", 1,
            )
            try:
                old_path.write_text(updated, encoding="utf-8")
            except OSError:
                return None
        return old_path
    if new_path.exists():
        # Target slug already in use — refuse to clobber the
        # collision. The caller surfaces this as a no-op; the user
        # ends up with two files until they manually reconcile.
        return None
    try:
        source = old_path.read_text(encoding="utf-8")
    except OSError:
        return None
    old_class = behavior_class_name(_Stub(old_name))
    new_class = behavior_class_name(_Stub(new_name))
    updated = source.replace(
        f"class {old_class}", f"class {new_class}", 1,
    )
    try:
        new_path.write_text(updated, encoding="utf-8")
        old_path.unlink()
    except OSError:
        return None
    return new_path


def recycle_behavior_file(
    project_file_path: str | Path | None,
    doc_name: str,
) -> bool:
    """Send ``<page>/<window>.py`` to the OS recycle bin (Phase 2
    Step 3 default). Returns ``True`` on success, ``False`` when
    the file doesn't exist or send2trash fails — caller surfaces
    the failure as a toast so the window deletion can still
    proceed (orphan files clean up via "Save copy" path next time).
    """
    from app.core.script_paths import behavior_file_path

    class _Stub:
        def __init__(self, name: str):
            self.name = name

    src = behavior_file_path(project_file_path, _Stub(doc_name))
    if src is None or not src.exists():
        return False
    try:
        # send2trash is a tiny pure-Python module — Windows uses
        # IFileOperation, macOS uses Foundation, Linux walks the
        # XDG trash spec. Cross-platform recovery without the user
        # opening a "Restore" dialog inside the builder.
        import send2trash
        send2trash.send2trash(str(src))
        return True
    except (OSError, ImportError):
        return False


def save_behavior_file_copy(
    project_file_path: str | Path | None,
    doc_name: str,
    target_path: str | Path,
) -> Path | None:
    """Move ``<page>/<window>.py`` to ``target_path`` (typically
    inside ``<project>/assets/scripts_archive/``), auto-suffixing
    ``_2`` / ``_3`` on filename collision. Returns the archived
    path or ``None`` when the source file doesn't exist or the
    move failed. The original file is removed — this is a "save
    + delete" round-trip, not a copy — so the active scripts
    folder stays clean.
    """
    from app.core.script_paths import behavior_file_path

    class _Stub:
        def __init__(self, name: str):
            self.name = name

    src = behavior_file_path(project_file_path, _Stub(doc_name))
    if src is None or not src.exists():
        return None
    dst = Path(target_path)
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    final = dst
    if final.exists():
        base = dst.stem
        suffix = dst.suffix
        n = 2
        candidate = dst.with_name(f"{base}_{n}{suffix}")
        while candidate.exists():
            n += 1
            candidate = dst.with_name(f"{base}_{n}{suffix}")
        final = candidate
    try:
        shutil.move(str(src), str(final))
    except OSError:
        return None
    return final


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


# ---------------------------------------------------------------------
# Editor launch
# ---------------------------------------------------------------------
# Well-known Windows install paths for editors that ship a launcher
# script. Probed in order; the first existing entry wins. Maps the
# bare token the user types in Settings (``code``, ``code-insiders``)
# to the actual ``.cmd`` / ``.exe`` on disk so we don't fall victim
# to PATH ambiguity (Git Bash / MinGW / MSYS2 all ship a ``code``
# that's not VS Code).
_EDITOR_KNOWN_PATHS: dict[str, tuple[str, ...]] = {
    "code": (
        r"%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd",
        r"%PROGRAMFILES%\Microsoft VS Code\bin\code.cmd",
        r"%PROGRAMFILES(X86)%\Microsoft VS Code\bin\code.cmd",
    ),
    "code-insiders": (
        r"%LOCALAPPDATA%\Programs\Microsoft VS Code Insiders\bin\code-insiders.cmd",
        r"%PROGRAMFILES%\Microsoft VS Code Insiders\bin\code-insiders.cmd",
    ),
    "subl": (
        r"%PROGRAMFILES%\Sublime Text\subl.exe",
        r"%PROGRAMFILES(X86)%\Sublime Text\subl.exe",
    ),
    "notepad++": (
        r"%PROGRAMFILES%\Notepad++\notepad++.exe",
        r"%PROGRAMFILES(X86)%\Notepad++\notepad++.exe",
    ),
    # PyCharm's bin folder lives under a versioned directory; the
    # Toolbox install also nests by channel + version. Probing every
    # combination is brittle, so we only list the JetBrains-default
    # paths the standard installer drops + the ``%LOCALAPPDATA%``
    # JetBrains Toolbox shim that some users add to PATH manually.
    "pycharm64": (
        r"%PROGRAMFILES%\JetBrains\PyCharm Community Edition\bin\pycharm64.exe",
        r"%PROGRAMFILES%\JetBrains\PyCharm\bin\pycharm64.exe",
        r"%LOCALAPPDATA%\JetBrains\Toolbox\scripts\pycharm.cmd",
    ),
}


def resolve_project_root_for_editor(project) -> str | None:
    """Project-folder path the external editor should open as a
    workspace, or ``None`` for unsaved / legacy single-file
    projects. Lets VS Code / PyCharm / Sublime activate their
    project-aware features (Python interpreter resolution, etc.)
    when CTkMaker hands them the behavior file.
    """
    path = getattr(project, "path", None)
    if not path:
        return None
    from app.core.project_folder import find_project_root
    root = find_project_root(path)
    if root is not None:
        return str(root)
    # Legacy single-file projects keep ``assets/scripts/`` next to
    # the .ctkproj — open that folder instead so VS Code still
    # gets a workspace context to run the Python tooling against.
    return str(Path(path).parent)


def _resolve_editor_binary(name: str) -> str | None:
    """Look up a bare editor command name on disk. Tries the
    well-known Windows install paths first (defeats Git Bash /
    MinGW / Cygwin shadowing), then falls back to ``shutil.which``
    for paths that do live on PATH legitimately. Names with path
    separators are returned as-is — the user explicitly pinned a
    full path and we shouldn't second-guess it.
    """
    if not name:
        return None
    if "/" in name or "\\" in name:
        return name if Path(name).exists() else None
    lookup_key = name.lower()
    for raw in _EDITOR_KNOWN_PATHS.get(lookup_key, ()):
        candidate = os.path.expandvars(raw)
        if Path(candidate).exists():
            return candidate
    return shutil.which(name) or shutil.which(f"{name}.cmd")


def launch_editor(
    file_path: str | Path,
    line: int | None = None,
    editor_command: str | None = None,
    project_root: str | Path | None = None,
) -> bool:
    """Open ``file_path`` in the user's editor, jumping to ``line``
    when the editor supports it. Returns ``True`` on success.

    Resolution order (Decision #1 = C — settings + OS-default
    fallback):

    1. ``editor_command`` — user-configured template from
       ``settings.json:editor_command``. Substitutes ``{file}`` and
       ``{line}`` placeholders. Empty / missing → fall through.
    2. ``code -g <file>:<line>`` — VS Code, when ``code`` (or
       ``code.cmd`` on Windows) is on PATH. Best UX because of the
       line jump.
    3. ``os.startfile(file)`` — Windows default file association
       (notepad, IDLE, whatever the user picked for ``.py``).
    4. Last resort: return ``False`` so the caller can surface a
       "couldn't open editor" toast.
    """
    file_path = str(file_path)
    folder = str(project_root) if project_root else ""
    if editor_command:
        # Strip the ``:{line}`` / ``--line {line}`` / ``-n{line}``
        # tail when no line number is available — every editor has
        # its own grammar for "no line", and the safe answer across
        # all of them is to just open the file. Pattern: split on
        # ``{line}`` and trim whitespace + colons / dashes from the
        # right of the head before stitching together with the tail
        # (which is usually the closing ``"`` or empty).
        try:
            template = editor_command
            if line is None and "{line}" in template:
                head, _, tail = template.partition("{line}")
                head = head.rstrip(": -+,")
                template = head + tail
            # ``{python}`` resolves to the interpreter running
            # CTkMaker. Used by the IDLE preset so the call works
            # whether the system has ``python`` on PATH (Windows),
            # ``python3`` (mac/Ubuntu), or only the bundled
            # py-launcher install — sys.executable is always right.
            cmd = template.format(
                file=file_path,
                line=line if line is not None else "",
                folder=folder,
                python=f'"{sys.executable}"',
            )
            # Bare-name editor binaries (``code``, ``code-insiders``,
            # ``subl``, ``notepad++``, …) collide with unrelated
            # tools that ship the same name — Git Bash / MinGW /
            # MSYS2 / Cygwin all carry their own ``code`` that
            # rejects ``-g``. Tokenise the formatted command and
            # resolve the first arg to its real path before
            # spawning, bypassing cmd.exe's PATH lookup. Falls back
            # to the legacy shell=True path on any tokenise failure.
            try:
                tokens = shlex.split(cmd, posix=False)
            except ValueError:
                tokens = []
            if tokens:
                first = tokens[0].strip('"')
                resolved = _resolve_editor_binary(first)
                if resolved:
                    argv = [resolved] + [
                        t.strip('"') for t in tokens[1:]
                    ]
                    print(f"[editor] launching argv: {argv}")
                    subprocess.Popen(argv)
                    return True
            print(f"[editor] launching shell form: {cmd}")
            subprocess.Popen(cmd, shell=True)
            return True
        except (OSError, KeyError, IndexError) as exc:
            print(f"[editor] command failed: {exc}")
    # Auto fallback chain: VS Code → Notepad++ (Windows) → IDLE.
    # Every Python install ships IDLE, so this list always ends in
    # something runnable — the user never gets a "couldn't open
    # editor" toast as long as they're running CTkMaker itself.
    code_exe = _resolve_editor_binary("code")
    if code_exe:
        try:
            target = (
                f"{file_path}:{line}" if line is not None else file_path
            )
            argv = [code_exe]
            if folder:
                # Open the project folder as a workspace first so
                # VS Code can resolve imports / activate the Python
                # extension. ``-g`` then jumps to the method line
                # inside that workspace.
                argv.append(folder)
            argv.extend(["-g", target])
            print(f"[editor] auto VS Code: {argv}")
            subprocess.Popen(argv)
            return True
        except OSError as exc:
            print(f"[editor] auto VS Code failed: {exc}")
    npp_exe = _resolve_editor_binary("notepad++")
    if npp_exe:
        try:
            argv = [npp_exe]
            if line is not None:
                argv.append(f"-n{line}")
            argv.append(file_path)
            print(f"[editor] auto Notepad++: {argv}")
            subprocess.Popen(argv)
            return True
        except OSError as exc:
            print(f"[editor] auto Notepad++ failed: {exc}")
    # IDLE is the universal fallback — it ships with every Python
    # install (Windows / macOS / Ubuntu) and only needs ``sys.executable``
    # to run, so it works even when the user's PATH carries no
    # editor at all.
    try:
        argv = [sys.executable, "-m", "idlelib", file_path]
        print(f"[editor] auto IDLE: {argv}")
        subprocess.Popen(argv)
        return True
    except OSError as exc:
        print(f"[editor] auto IDLE failed: {exc}")
    if hasattr(os, "startfile"):
        try:
            os.startfile(file_path)  # type: ignore[attr-defined]
            return True
        except OSError:
            pass
    return False


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
