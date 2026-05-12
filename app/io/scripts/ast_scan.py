"""Read-only AST inspection of behavior files.

Surfaces:
- method names + line numbers (``parse_handler_methods``,
  ``find_handler_method``)
- ``ref[<Type>]`` annotations (``parse_object_reference_fields``,
  ``existing_object_reference_names``)
- one-line docstrings per method (``parse_method_docstrings``)

All entry points are robust to missing files / syntax errors — they
return empty containers / ``None`` rather than raising so caller code
keeps the builder responsive even when the user's behavior file is
mid-edit and unparseable.
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
