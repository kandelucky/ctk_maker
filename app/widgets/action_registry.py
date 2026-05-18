"""Action allowlist for widget-to-widget direct calls in event slots.

When a Properties-panel event slot picks an Object Reference target,
the dropdown shows methods sourced from this registry rather than
``inspect.signature`` — the latter surfaces every Tk-inherited
method (``place``, ``bind``, ``after``, …) which would force noisy
runtime filtering. A curated allowlist keeps the dropdown clean,
mirrors the existing ``BINDING_WIRINGS`` pattern in
``app/core/variables.py``, and lets us assign friendly labels
(``"set text"``) that don't have to match the underlying method
name (``configure``).

See ``docs/plans/event_binding.md`` for the wider plan.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ActionParam:
    """One parameter of a callable action.

    Only zero- and one-parameter actions are exposed in v1 of the
    plan; multi-parameter methods (e.g. ``CTkEntry.delete(0, "end")``)
    stay out — users who need them write a behavior method that
    calls the widget directly.

    ``kwarg`` controls export shape: ``True`` emits ``name=value``,
    ``False`` emits a bare positional. ``default`` seeds the static
    parameter input in the Properties panel.
    """
    name: str
    type: str  # "str" | "int" | "float" | "bool"
    default: Any = ""
    kwarg: bool = False


@dataclass(frozen=True)
class ActionEntry:
    """One callable action on a widget type.

    ``name`` is the actual Python method on the widget instance
    (``"configure"``). ``label`` is the friendly string shown in the
    Properties-panel dropdown (``"set text"``) — they don't have to
    match. The exporter writes the actual ``name`` into the lambda.
    """
    name: str
    label: str
    params: tuple[ActionParam, ...] = field(default_factory=tuple)


WIDGET_ACTION_METHODS: dict[str, list[ActionEntry]] = {
    "CTkLabel": [
        ActionEntry(
            name="configure",
            label="set text",
            params=(ActionParam(name="text", type="str", kwarg=True),),
        ),
    ],
}


def actions_for(widget_type: str) -> list[ActionEntry]:
    """All allowlisted actions for a widget type. Empty when the
    type has no entry yet — the dropdown shows no methods for that
    Object Reference; the user picks a different ref or wires the
    behavior method by hand.
    """
    return WIDGET_ACTION_METHODS.get(widget_type, [])


def find_action(widget_type: str, method_name: str) -> ActionEntry | None:
    """Resolve a stored ref_call's method name back to its allowlist
    entry. ``None`` means the binding is stale — the allowlist no
    longer exposes this method (e.g. an action was removed in a
    later CTkMaker version). The exporter drops these and emits a
    warning, same as missing behavior methods.
    """
    for entry in WIDGET_ACTION_METHODS.get(widget_type, ()):
        if entry.name == method_name:
            return entry
    return None
