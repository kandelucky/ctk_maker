"""Read-only AST inspection of behavior files.

Surfaces:
- method names + line numbers (``parse_handler_methods``,
  ``find_handler_method``)
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

# Lifecycle methods on the behavior class — never user-bindable handlers.
# Kept out of the Function picker so they don't clutter the dropdown.
# ``setup(self, window)`` happens to signature-match ``bind`` events
# (one arg after self, default-allowed) so without this filter it leaks
# into every Label/Entry/Textbox bind dropdown.
_RESERVED_BEHAVIOR_METHODS: frozenset[str] = frozenset({"setup"})


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


def parse_handler_methods_compatible(
    file_path: str | Path,
    class_name: str,
    wiring_kind: str,
) -> list[str]:
    """Return method names suitable for binding to an event of the
    given ``wiring_kind`` (``"command"`` or ``"bind"``).

    Two filters apply:

    * **Visibility** — only public methods (name doesn't start with
      ``_``). Mirrors the Unity Inspector convention; private and
      dunder helpers stay out of the dropdown.
    * **Signature compatibility** — the method must accept the
      argument shape the runtime invocation passes:
        * ``command`` events call ``method()`` (no args after self).
          Required arg count after ``self`` must equal 0.
        * ``bind`` events call ``method(event)`` (one arg after
          self). The method must accept at least one positional
          slot after ``self`` (either required or with a default);
          required arg count after ``self`` must be 1 or 0 (with
          a slot reserved for ``event``).

    Empty list on missing file / syntax error / unknown
    ``wiring_kind`` — same robustness contract as
    ``parse_handler_methods``.
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
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if stmt.name.startswith("_"):
            continue
        if stmt.name in _RESERVED_BEHAVIOR_METHODS:
            continue
        if _signature_matches_event(stmt, wiring_kind):
            names.append(stmt.name)
    return names


def _signature_matches_event(
    fn: ast.FunctionDef | ast.AsyncFunctionDef, wiring_kind: str,
) -> bool:
    pos = list(fn.args.args)
    if not pos:
        return False
    # Drop ``self`` — instance methods on a behavior class always
    # have it as the first positional arg.
    pos = pos[1:]
    required = max(0, len(pos) - len(fn.args.defaults))
    if wiring_kind == "command":
        return required == 0
    if wiring_kind == "bind":
        return len(pos) >= 1 and required <= 1
    return False


def parse_module_functions(
    file_path: str | Path,
    wiring_kind: str | None = None,
    command_value: bool = False,
) -> list[str]:
    """Return public top-level function names from a library script.

    Three filters apply:

    * **Top-level only** — class methods and nested functions are
      skipped (event handlers call ``module.func()``, not classes).
    * **Visibility** — name doesn't start with ``_`` (Python
      convention; mirrors ``parse_handler_methods_compatible``).
    * **Sync only** — ``async def`` is dropped (Tk event callbacks
      can't ``await``; an attached script wanting async logic
      wraps it manually in a sync entry point).

    ``wiring_kind`` (optional): when ``"command"`` or ``"bind"``,
    also filter by signature compatibility under the direct-binding
    convention (see ``_module_function_matches``). ``command_value``
    marks a value-passing command (slider / combo / option /
    segmented) so its functions are required to accept the value.

    Empty on missing file / syntax error / no public functions.
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
        if not isinstance(stmt, ast.FunctionDef):
            continue
        if stmt.name.startswith("_"):
            continue
        if wiring_kind is not None and not _module_function_matches(
            stmt, wiring_kind, command_value,
        ):
            continue
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


def _module_function_matches(
    fn: ast.FunctionDef, wiring_kind: str, command_value: bool = False,
) -> bool:
    """Signature-compat check for module-level functions under the
    direct-binding calling convention. Module functions have no
    implicit ``self``, so the window is an explicit first parameter.
    The export passes a fixed number of positional args per shape:

    - ``bind`` → ``func(window, event)`` — 2 args.
    - ``command`` + ``command_value`` → ``func(window, value)`` — 2.
    - ``command`` (argless) → ``func(window)`` — 1.
    - ``lifecycle`` → ``func(window)`` — 1 (on_setup / on_close).

    A function matches when it can be called with exactly that many
    positionals: ``len(pos) >= need`` with ``required <= need``, or a
    ``*args`` catch-all. So a 1-arg function no longer qualifies for a
    bind / value-command (the extra arg would be dropped), and an
    argless function no longer qualifies for any shape (the window
    would be dropped).
    """
    if wiring_kind == "bind":
        need = 2
    elif wiring_kind == "command":
        need = 2 if command_value else 1
    elif wiring_kind == "lifecycle":
        need = 1
    else:
        return False
    pos = list(fn.args.args)
    required = max(0, len(pos) - len(fn.args.defaults))
    if fn.args.vararg is not None:
        return required <= need
    return len(pos) >= need and required <= need


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
