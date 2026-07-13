"""Row assembly for the Properties panel's Script Variables group.

Combines three pure layers into the data the panel renders (and the
picker fills):

- ``parse_exposed_variables`` — the ``name: tk.StringVar`` fields a
  CTkScript class exposes (AST, no import).
- a component's ``var_bindings`` — the field → variable UUID the user
  already picked.
- ``eligible_variables`` — the project variables a field of that type
  may bind to (globals + the window's locals, type-filtered).

Pure data — no Tk. See docs/plans/archive/script_variable_binding.md.
"""
from __future__ import annotations

from pathlib import Path

from app.core.variables import VariableEntry, eligible_variables
from app.io.scripts.ast_scan import parse_exposed_variables


def build_variable_rows(
    components: list[dict],
    scripts_dir: str | Path | None,
    globals_: list[VariableEntry],
    locals_: list[VariableEntry],
) -> list[dict]:
    """One row per exposed variable field across ``components``.

    ``components`` are the attached-component dicts of the selected
    object (widget- or window-scope); ``scripts_dir`` is the project's
    ``scripts/`` folder; ``globals_`` / ``locals_`` are the variable
    scopes the script may reach (project globals + the owning window's
    locals — Q2).

    Each row::

        {
          "class": <ClassName>, "script": <rel path>,
          "field": <field name>, "var_type": <str|int|float|bool>,
          "bound_id": <variable UUID or None>,   # current binding
          "eligible": [VariableEntry, ...],        # type-filtered choices
        }

    Components missing ``script`` / ``class`` are skipped; a script with
    no exposed fields contributes no rows. Order follows ``components``,
    then the field order in the source file.
    """
    rows: list[dict] = []
    for comp in components:
        cls = comp.get("class")
        script_rel = comp.get("script")
        if not cls or not script_rel:
            continue
        bindings = comp.get("var_bindings") or {}
        fields = (
            parse_exposed_variables(Path(scripts_dir) / script_rel, cls)
            if scripts_dir else []
        )
        for field, var_type in fields:
            rows.append({
                "class": cls,
                "script": script_rel,
                "field": field,
                "var_type": var_type,
                "bound_id": bindings.get(field),
                "eligible": eligible_variables(globals_, locals_, var_type),
            })
    return rows
