"""CTk widget constructor default introspection.

Used by the export pipeline to skip kwargs whose value would already
match the CTk class's `__init__` default — keeps the generated `.py`
compact instead of carrying every Maker descriptor default through to
the user's runtime.
"""

from __future__ import annotations


# v1.10.0 — per-CTk-class cache of constructor default values, used by
# ``_emit_widget`` to skip kwargs whose value would already match the
# CTk default. Without this gate, every exported widget carries every
# default Maker holds in its descriptor — 130 widgets × ~25 kwargs each
# bloats the generated file 17× over a hand-written equivalent and
# triggers redundant Canvas redraws + per-widget CTkFont listeners.
# Built lazily via ``inspect.signature`` so the catalog tracks whatever
# CTk version the user has installed.
_CTK_CONSTRUCTOR_DEFAULTS_CACHE: dict[str, dict] = {}
_CTK_DEFAULT_MISSING = object()  # sentinel — class has no such kwarg


def _ctk_constructor_defaults(class_name: str) -> dict:
    """CTk widget class's ``__init__`` default values, by kwarg name.

    Resolves ``customtkinter.<class_name>`` and reads ``inspect.signature``
    once per class. Cached for the lifetime of the process. Returns an
    empty dict when the class can't be resolved (custom widgets that
    aren't CTk subclasses, or CTk import failures) — callers fall back
    to emitting every kwarg, preserving pre-v1.10.0 behavior.
    """
    if class_name in _CTK_CONSTRUCTOR_DEFAULTS_CACHE:
        return _CTK_CONSTRUCTOR_DEFAULTS_CACHE[class_name]
    defaults: dict = {}
    try:
        import inspect
        import customtkinter as _ctk
        cls = getattr(_ctk, class_name, None)
        if cls is not None:
            sig = inspect.signature(cls.__init__)
            defaults = {
                p.name: p.default
                for p in sig.parameters.values()
                if p.default is not inspect.Parameter.empty
            }
    except Exception:
        defaults = {}
    _CTK_CONSTRUCTOR_DEFAULTS_CACHE[class_name] = defaults
    return defaults


def _kwarg_matches_defaults(
    key: str,
    value,
    maker_defaults: dict,
    ctk_defaults: dict,
) -> bool:
    """True iff emitting ``key=value`` would be redundant.

    Skip is safe only when **all three** agree:
      1. ``key`` exists in the descriptor's default_properties.
      2. ``value`` equals the descriptor (Maker) default.
      3. ``key`` exists in CTk's __init__ AND ``value`` equals the
         CTk default.

    Maker default ≠ CTk default mismatch (e.g. ``CTkButton.height``:
    Maker=32, CTk=28) blocks the skip — otherwise the exported app
    would render at 28px while Maker preview shows 32px.
    """
    if key not in maker_defaults:
        return False
    if value != maker_defaults[key]:
        return False
    ctk_val = ctk_defaults.get(key, _CTK_DEFAULT_MISSING)
    if ctk_val is _CTK_DEFAULT_MISSING:
        return False
    return value == ctk_val
