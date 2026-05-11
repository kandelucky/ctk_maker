"""Page-scoped variable system — Phase 1 of the visual scripting plan.

Each page carries a flat list of named, typed shared values
(``str`` / ``int`` / ``float`` / ``bool`` / ``color``). Widgets bind
to a variable via a ``var:<uuid>`` token written into the property
slot; the runtime resolves the token to a shared ``tk.Variable``
instance so multiple widgets bound to the same variable stay in sync
without any custom wiring (Tkinter's built-in ``textvariable`` /
``variable`` mechanism does the work for us).

Globals are page-scoped — the active page's ``project.variables``
holds them; switching pages reloads a different set. Locals are
window-scoped on ``Document.local_variables``. There is no
cross-page variable scope — pages export as independent ``.py``
files and don't talk to each other at runtime.

``color`` values flow as hex strings (``#rrggbb``) through StringVars,
identical to ``str`` at runtime — the type tag only changes the
editor surface (swatch + picker) and the bind-picker filtering for
color-typed properties.

Identity is the UUID — renaming a variable updates the display name
but never breaks existing bindings.
"""

from __future__ import annotations

import tkinter as tk
import uuid
from dataclasses import dataclass, field
from typing import Literal

VAR_TYPES = ("str", "int", "float", "bool", "color")
VarType = Literal["str", "int", "float", "bool", "color"]

COLOR_DEFAULT = "#000000"
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")

VAR_SCOPES = ("global", "local")
VarScope = Literal["global", "local"]

VAR_TOKEN_PREFIX = "var:"


@dataclass
class VariableEntry:
    """One named, typed shared value.

    ``scope == "global"`` lives on ``Project.variables`` (page-scoped —
    one set per page, shared across that page's Main + Dialogs);
    ``scope == "local"`` lives on a single ``Document.local_variables``
    and is invisible to widgets in other documents. Identity is the
    UUID — token rewrites are needed only when copying a local across
    documents (each copy gets its own UUID).
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    type: VarType = "str"
    default: str = ""
    scope: VarScope = "global"

    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "default": self.default,
        }
        if self.scope != "global":
            result["scope"] = self.scope
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "VariableEntry":
        v = cls()
        v.id = str(data.get("id") or uuid.uuid4())
        v.name = str(data.get("name") or "")
        raw_type = str(data.get("type") or "str")
        v.type = raw_type if raw_type in VAR_TYPES else "str"
        v.default = str(data.get("default") or "")
        raw_scope = str(data.get("scope") or "global")
        v.scope = raw_scope if raw_scope in VAR_SCOPES else "global"
        return v


def make_var_token(var_id: str) -> str:
    """Wrap a variable UUID as a ``var:<uuid>`` reference token. Stored
    in widget property slots so loader / runtime / exporter can tell
    a binding apart from a literal value.
    """
    return f"{VAR_TOKEN_PREFIX}{var_id}"


def is_var_token(value) -> bool:
    """Return True iff ``value`` is a string starting with ``var:``."""
    return isinstance(value, str) and value.startswith(VAR_TOKEN_PREFIX)


def parse_var_token(value) -> str | None:
    """Extract the UUID from a ``var:<uuid>`` token, or return None
    when ``value`` is not a token. Lets call sites use one expression
    for both literal and bound branches.
    """
    if not is_var_token(value):
        return None
    return value[len(VAR_TOKEN_PREFIX):] or None


def make_tk_var(var_type: str, default: str) -> tk.Variable:
    """Build a fresh ``tk.Variable`` of the right subclass with the
    string ``default`` coerced into the variable's runtime type.
    Coercion failures fall through to the type's safe default
    ("" / 0 / 0.0 / False) so the runtime never crashes on a
    malformed user-typed default.
    """
    if var_type == "str":
        return tk.StringVar(value=default or "")
    if var_type == "int":
        try:
            return tk.IntVar(value=int((default or "0").strip() or 0))
        except (TypeError, ValueError):
            return tk.IntVar(value=0)
    if var_type == "float":
        try:
            return tk.DoubleVar(value=float((default or "0").strip() or 0.0))
        except (TypeError, ValueError):
            return tk.DoubleVar(value=0.0)
    if var_type == "bool":
        truthy = str(default).strip().lower() in (
            "true", "1", "yes", "on",
        )
        return tk.BooleanVar(value=truthy)
    if var_type == "color":
        return tk.StringVar(value=default or COLOR_DEFAULT)
    return tk.StringVar(value=default or "")


def is_valid_hex(text: str) -> bool:
    """``#rgb`` / ``#rrggbb`` only — no named colors. Same loose
    surface as ``int`` / ``float`` parsing: anything that doesn't fit
    falls back to a safe default at the call site.
    """
    if not text or not text.startswith("#"):
        return False
    body = text[1:]
    return len(body) in (3, 6) and all(c in _HEX_DIGITS for c in body)


def coerce_default_for_type(default: str, var_type: str) -> str:
    """Normalise a user-typed default into the canonical string form
    the runtime will see. Anything that doesn't parse drops to the
    type's safe default ("" / "0" / "0.0" / "False"). Pure string
    logic — no Tk root required, so model code can call this safely
    before any UI exists.
    """
    text = str(default or "").strip()
    if var_type == "str":
        return str(default or "")
    if var_type == "int":
        try:
            return str(int(text))
        except (TypeError, ValueError):
            return "0"
    if var_type == "float":
        try:
            return str(float(text))
        except (TypeError, ValueError):
            return "0.0"
    if var_type == "bool":
        truthy = text.lower() in ("true", "1", "yes", "on")
        return "True" if truthy else "False"
    if var_type == "color":
        return text if is_valid_hex(text) else COLOR_DEFAULT
    return str(default or "")


# ======================================================================
# Runtime binding wiring
# ======================================================================
#
# Maps ``(widget_type, property_name)`` → CTk constructor keyword.
# When a property is bound to a variable, the runtime passes the live
# ``tk.Variable`` instance to the widget under that keyword instead of
# emitting the literal value. Tkinter's built-in ``textvariable`` /
# ``variable`` then keeps every bound widget in sync automatically —
# no custom wiring needed.
#
# Properties NOT in this table can still be bound (the binding chip
# shows up, save/load round-trips), but at create-time the runtime
# falls back to writing the variable's CURRENT value as a literal.
# That covers cosmetic bindings (e.g. fg_color → some shared theme
# var) without needing per-property tk machinery.
BINDING_WIRINGS: dict[tuple[str, str], str] = {
    ("CTkLabel", "text"): "textvariable",
    ("CTkEntry", "initial_value"): "textvariable",
    ("CTkSlider", "initial_value"): "variable",
    ("CTkSwitch", "initially_checked"): "variable",
    ("CTkCheckBox", "initially_checked"): "variable",
    ("CTkSegmentedButton", "segment_initial"): "variable",
    ("CTkOptionMenu", "initial_value"): "variable",
    ("CTkComboBox", "initial_value"): "variable",
}


_PTYPE_VAR_COMPAT: dict[str, tuple[str, ...]] = {
    "boolean": ("bool", "int"),
    "number": ("int", "float"),
    # Color rows show ``color``-typed vars first (the typed surface)
    # but keep ``str`` as a fallback so existing string-hex bindings
    # made before the ``color`` type existed still appear and stay
    # editable.
    "color": ("color", "str"),
}


def compatible_var_types(ptype: str) -> tuple[str, ...]:
    """Variable types that can sensibly bind to a schema property of
    the given ``ptype``. Defaults to ``("str",)`` — most editor types
    (text, font, image, enum, anchor, etc.) want a StringVar. Number
    rows accept int / float; boolean rows accept bool / int (CTk's
    switch / checkbox use IntVar internally); color rows accept color
    + str (the typed surface plus the legacy string-hex flow).
    """
    return _PTYPE_VAR_COMPAT.get(ptype, ("str",))


def resolve_bindings(
    project, widget_type: str, properties: dict,
) -> tuple[dict, dict]:
    """Walk ``properties`` looking for ``var:<uuid>`` tokens.

    For tokens whose ``(widget_type, prop_name)`` has an entry in
    ``BINDING_WIRINGS`` (``textvariable`` / ``variable``-aware
    properties): strip the property from the returned ``cleaned`` dict
    and emit a ``{kwarg: tk.Variable}`` entry in ``extra_kwargs`` so
    the descriptor passes the live variable to CTk's constructor.

    For tokens without a wiring (cosmetic bindings — e.g. ``fg_color``
    bound to a shared StringVar): replace the token with the
    variable's current literal value so the descriptor sees a usable
    string. Tkinter has no ``colorvariable``-style mechanism for those
    properties, so updates to the variable won't propagate live —
    that's acceptable for Phase 1 (Phase 5 logic nodes can plumb
    arbitrary updates).

    Tokens pointing at a deleted variable: stripped from properties so
    the descriptor falls back to its declared default.
    """
    cleaned: dict = {}
    extra_kwargs: dict = {}
    for key, value in properties.items():
        var_id = parse_var_token(value)
        if var_id is None:
            cleaned[key] = value
            continue
        kwarg_name = BINDING_WIRINGS.get((widget_type, key))
        tk_var = (
            project.get_tk_var(var_id) if project is not None else None
        )
        if kwarg_name and tk_var is not None:
            extra_kwargs[kwarg_name] = tk_var
            # Strip the property — descriptor would otherwise try to
            # set a literal that conflicts with the textvariable /
            # variable kwarg.
            continue
        if tk_var is not None:
            # Cosmetic / unwired binding — drop in current value as
            # literal so the descriptor sees a usable string.
            try:
                cleaned[key] = tk_var.get()
            except Exception:
                pass
            continue
        # Variable was deleted — strip so descriptor uses its default.
    return cleaned, extra_kwargs


def sanitize_var_name(raw: str) -> str:
    """Best-effort sanitisation of a user-typed variable name to a
    Python identifier-ish string. Leaves the original alone if it's
    already valid; otherwise replaces non-identifier characters with
    underscores and ensures the first character is a letter or
    underscore. Empty / all-illegal input collapses to ``"var"``.
    """
    if raw and raw.isidentifier():
        return raw
    out_chars: list[str] = []
    for ch in raw:
        if ch.isalnum() or ch == "_":
            out_chars.append(ch)
        else:
            out_chars.append("_")
    cleaned = "".join(out_chars).strip("_")
    if not cleaned:
        return "var"
    if cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned
