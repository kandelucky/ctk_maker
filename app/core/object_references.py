"""Object References — typed widget pointers for behavior code.

A v1.10.8 reframing of Phase 3 Behavior Fields. Each entry is a named
slot — global (project-wide, only Window/Dialog targets) or local
(per-document, only inner-widget targets) — that resolves at export
time to ``self._behavior.<name> = <expr>``. Behavior files reach the
referenced widget / window through ``self.<name>``.

Conceptually a sibling of ``VariableEntry``: same scope mechanic
(global / local), same access pattern in user code, different
payload — variables hold values, references hold pointers. The
Variables window (F11) shows both side-by-side, the Properties panel
toggles per-widget refs in one click.

Scope rules — enforced at validation time:

- ``target_type in ("Window", "Dialog")`` → only ``"global"`` scope.
  These point at top-level documents, which exist for the program's
  whole lifetime.
- Any other CTk widget type → only ``"local"`` scope. Inner widgets
  belong to one document; cross-document references would be
  phantoms when the target document isn't instantiated.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

REF_SCOPES = ("global", "local")
RefScope = Literal["global", "local"]

# Target types that live as top-level documents. Drives scope
# validation: these must be global, everything else must be local.
DOCUMENT_TARGET_TYPES = ("Window", "Dialog")

# Short labels to mirror Object Tree's `_TYPE_INITIALS`. Used by F11
# Object References panel + any other read-only display where the
# full ``CTkButton`` form is too long for the available column.
TYPE_SHORT_LABELS: dict[str, str] = {
    "CTkButton":          "Btn",
    "CTkLabel":           "Lbl",
    "CTkEntry":           "Ent",
    "CTkTextbox":         "Txt",
    "CTkCheckBox":        "Chk",
    "CTkRadioButton":     "Rad",
    "CTkSwitch":          "Sw",
    "CTkSegmentedButton": "Seg",
    "CTkSlider":          "Sld",
    "CTkProgressBar":     "Bar",
    "CTkComboBox":        "Cmb",
    "CTkOptionMenu":      "Opt",
    "CTkFrame":           "Frm",
    "CTkScrollableFrame": "ScF",
    "CTkTabview":         "Tab",
    "Image":              "Img",
    "Card":               "Crd",
    "CircularProgress":   "CPr",
    "Window":             "Win",
    "Dialog":             "Dlg",
}


def short_type_label(target_type: str) -> str:
    """Map ``CTkButton`` → ``Btn`` etc. Falls back to the input when
    the type isn't in the table — keeps display robust for custom
    widgets the table doesn't enumerate yet.
    """
    return TYPE_SHORT_LABELS.get(target_type, target_type)


@dataclass
class ObjectReferenceEntry:
    """One named slot pointing at a Document (global) or a widget
    (local). Identity is the UUID — renames touch only the display
    name; the binding survives.

    ``target_id`` is a Document.id when ``target_type`` is ``"Window"``
    or ``"Dialog"``, otherwise a WidgetNode.id inside the owning
    document. Empty string ``""`` means the slot is declared but not
    yet bound (Properties panel toggle hasn't been used; user
    declared the entry by hand in the Variables window).
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    target_type: str = "CTkLabel"
    scope: RefScope = "local"
    target_id: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "target_type": self.target_type,
            "scope": self.scope,
            "target_id": self.target_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ObjectReferenceEntry":
        e = cls()
        e.id = str(data.get("id") or uuid.uuid4())
        e.name = str(data.get("name") or "")
        e.target_type = str(data.get("target_type") or "CTkLabel")
        raw_scope = str(data.get("scope") or "local")
        e.scope = raw_scope if raw_scope in REF_SCOPES else "local"
        e.target_id = str(data.get("target_id") or "")
        return e


def required_scope_for(target_type: str) -> RefScope:
    """Map a target type to the only scope that's valid for it.
    Documents (Window / Dialog) are global; everything else is local.
    """
    if target_type in DOCUMENT_TARGET_TYPES:
        return "global"
    return "local"


def is_valid_python_identifier(name: str) -> bool:
    """True iff the name is a non-keyword Python identifier.
    The Variables window add / rename flows reject everything else
    so the generated ``self.<name>`` is always a clean attribute.
    """
    import keyword
    if not name or not isinstance(name, str):
        return False
    if not name.isidentifier():
        return False
    if keyword.iskeyword(name):
        return False
    return True


def suggest_ref_name(
    target_label: str,
    target_type: str,
    existing_names: set[str],
) -> str:
    """Pick a default identifier for a new reference. Prefers the
    widget's user-facing name (when it's a valid identifier), falls
    back to ``<lowercase_type>_ref``. Suffixes ``_2`` / ``_3`` when
    the chosen base collides with an existing reference name.
    """
    base = (target_label or "").strip()
    if not is_valid_python_identifier(base):
        base = target_type.lower()
        if base.startswith("ctk"):
            base = base[3:] or target_type.lower()
        base = base + "_ref"
    if base not in existing_names:
        return base
    n = 2
    while f"{base}_{n}" in existing_names:
        n += 1
    return f"{base}_{n}"
