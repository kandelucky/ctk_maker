"""CTkScript component resolution.

Which attached component a ``script_call`` binds to — shared by the
Properties panel, both event pickers, and (in spirit) the exporter's
``_resolve_component_var``. Keeping the rule in one place stops the
panel's "is this binding valid?" check from drifting away from what
export actually resolves.

Operates on plain model objects (``WidgetNode`` / ``Document``) via
duck-typed ``attached_components`` — no Tk, no parsing.
"""
from __future__ import annotations


def iter_script_call_targets(node, document) -> list[tuple[str, str, str]]:
    """``(script_rel, class_name, scope)`` for every CTkScript component
    bindable from ``node``'s events — the widget's own components (scope
    ``"widget"``) first, then the window's (scope ``"window"``). Drives
    both the panel and the workspace event pickers so they offer the
    same targets."""
    out: list[tuple[str, str, str]] = []
    for comp in (getattr(node, "attached_components", None) or []):
        cls, script = comp.get("class"), comp.get("script")
        if cls and script:
            out.append((script, cls, "widget"))
    for comp in (getattr(document, "attached_components", None) or []):
        cls, script = comp.get("class"), comp.get("script")
        if cls and script:
            out.append((script, cls, "window"))
    return out


def resolve_script_component(node, document, cls: str, scope=None):
    """The attached-component dict a ``script_call`` resolves to,
    honoring scope:

    * ``scope="widget"`` → only the owner widget's components,
    * ``scope="window"`` → only the document's,
    * ``scope=None`` (legacy entries with no stored scope) → widget
      first, then window — mirrors the exporter's fallback.

    Returns the ``{"script", "class"}`` dict, or ``None`` when nothing
    matches (the binding is orphaned)."""
    node_comps = getattr(node, "attached_components", None) or []
    doc_comps = getattr(document, "attached_components", None) or []

    def _find(comps):
        return next((c for c in comps if c.get("class") == cls), None)

    if scope == "window":
        return _find(doc_comps)
    if scope == "widget":
        return _find(node_comps)
    return _find(node_comps) or _find(doc_comps)
