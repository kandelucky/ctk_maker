"""Default-skip filter (v1.10.0) — exporter omits kwargs whose value
already matches both the descriptor's default AND CTk's constructor
default.

Pre-1.10.0 the exporter emitted every key from ``node.properties``,
which is a full copy of ``descriptor.default_properties`` populated
at widget-add time. A 130-widget Showcase project produced a 2911-line
``.py`` (vs 165 for an equivalent hand-written CTk script) and ran
~2× slower on startup + scaling-toggle. The slowdown traced to the
per-widget ``ctk.CTkFont(...)`` instances (each registers a
``<<RefreshFonts>>`` listener) and the explicit ``width=``/``height=``
kwargs that block CTk's lazy Canvas sizing.

This module covers:
  - ``_ctk_constructor_defaults``: the inspect.signature catalog
  - ``_kwarg_matches_defaults``: the three-way agreement gate
  - ``_font_props_at_default``: the all-defaults font-skip predicate
  - ``generate_code``: end-to-end snapshot for a default CTkButton
"""

from __future__ import annotations

import pytest

from app.core.document import Document
from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.io import code_exporter
from app.io.code_exporter import (
    _CTK_DEFAULT_MISSING,
    _ctk_constructor_defaults,
    _font_props_at_default,
    _kwarg_matches_defaults,
    generate_code,
)
from app.widgets.registry import get_descriptor


@pytest.fixture(autouse=True)
def _reset_exporter_state():
    code_exporter._VAR_NAME_FALLBACKS = []
    code_exporter._NAME_MAP_CACHE = {}
    yield
    code_exporter._VAR_NAME_FALLBACKS = []
    code_exporter._NAME_MAP_CACHE = {}


# ---------------------------------------------------------------------
# _ctk_constructor_defaults — inspect.signature catalog
# ---------------------------------------------------------------------
def test_catalog_returns_ctk_button_defaults():
    defaults = _ctk_constructor_defaults("CTkButton")
    # CTkButton's __init__ exposes these defaults — values are CTk's,
    # not Maker's (height=28 vs Maker's 32 is the canonical example).
    assert defaults["width"] == 140
    assert defaults["height"] == 28
    assert defaults["state"] == "normal"
    assert defaults["hover"] is True
    assert defaults["compound"] == "left"
    assert defaults["anchor"] == "center"


def test_catalog_returns_empty_for_unknown_class():
    # Custom widgets like CircleLabel aren't on the customtkinter
    # module — the catalog falls back to {} so emit-everything
    # behavior is preserved.
    assert _ctk_constructor_defaults("CircleLabel") == {}
    assert _ctk_constructor_defaults("NotAClass") == {}


def test_catalog_caches_per_class():
    code_exporter._CTK_CONSTRUCTOR_DEFAULTS_CACHE.clear()
    first = _ctk_constructor_defaults("CTkButton")
    second = _ctk_constructor_defaults("CTkButton")
    assert first is second  # identity check — same dict object


# ---------------------------------------------------------------------
# _kwarg_matches_defaults — three-way agreement gate
# ---------------------------------------------------------------------
def test_skip_when_all_three_agree():
    maker = {"hover": True}
    ctk = {"hover": True}
    assert _kwarg_matches_defaults("hover", True, maker, ctk) is True


def test_emit_when_value_diverges_from_maker_default():
    # User changed hover from True → False; Maker default is True.
    maker = {"hover": True}
    ctk = {"hover": True}
    assert _kwarg_matches_defaults("hover", False, maker, ctk) is False


def test_emit_when_maker_default_diverges_from_ctk():
    # Maker says height=32, CTk says 28 — value matches Maker but
    # NOT CTk, so emit forces height=32 in the generated file.
    maker = {"height": 32}
    ctk = {"height": 28}
    assert _kwarg_matches_defaults("height", 32, maker, ctk) is False


def test_emit_when_kwarg_missing_from_ctk_signature():
    # Maker's ``border_enabled`` is a node-only synthesized property —
    # CTk has no such kwarg. Skip must NOT fire (that catalog miss
    # would otherwise let an in-Maker default leak through unchanged).
    maker = {"border_enabled": False}
    ctk = {}  # no border_enabled key
    assert _kwarg_matches_defaults(
        "border_enabled", False, maker, ctk,
    ) is False


def test_emit_when_kwarg_missing_from_maker_default():
    # Some properties get appended via export_kwarg_overrides without
    # a descriptor default (e.g. dynamic_resizing). Skip is unsafe.
    maker = {}
    ctk = {"dynamic_resizing": True}
    assert _kwarg_matches_defaults(
        "dynamic_resizing", True, maker, ctk,
    ) is False


# ---------------------------------------------------------------------
# _font_props_at_default — all-defaults font-skip predicate
# ---------------------------------------------------------------------
def test_font_default_when_all_knobs_at_default():
    props = {
        "font_family": None,
        "font_size": 13,
        "font_bold": False,
        "font_italic": False,
        "font_underline": False,
        "font_overstrike": False,
    }
    assert _font_props_at_default(props) is True


def test_font_not_default_when_size_changed():
    props = {"font_size": 20}
    assert _font_props_at_default(props) is False


def test_font_not_default_when_bold():
    props = {"font_size": 13, "font_bold": True}
    assert _font_props_at_default(props) is False


def test_font_not_default_when_family_set():
    props = {"font_family": "Comic Sans MS", "font_size": 13}
    assert _font_props_at_default(props) is False


def test_font_default_when_props_empty():
    # CTkScrollableFrame's family-only descriptor: no font_size,
    # no other knobs — defaults predicate must accept empty dict
    # (callers that don't carry font knobs aren't covered by this
    # branch anyway, but the predicate should be permissive).
    assert _font_props_at_default({}) is True


# ---------------------------------------------------------------------
# generate_code — end-to-end snapshot
# ---------------------------------------------------------------------
def _add_default_button(project: Project, name: str = "btn") -> WidgetNode:
    desc = get_descriptor("CTkButton")
    btn = WidgetNode(widget_type="CTkButton")
    btn.name = name
    # Mimic a fresh palette-drop: properties = full descriptor
    # default copy. This is exactly what AddWidgetCommand stores.
    btn.properties = dict(desc.default_properties)
    project.active_document.root_widgets.append(btn)
    return btn


def test_default_button_emits_minimal_kwargs():
    project = Project()
    _add_default_button(project, "btn")
    src = generate_code(project)

    # All-defaults button must NOT carry these — value matches both
    # Maker and CTk defaults, skip is safe.
    assert "state=" not in src
    assert "hover=True" not in src
    assert "compound=" not in src
    assert "anchor='center'" not in src and 'anchor="center"' not in src

    # height=32 (Maker) ≠ 28 (CTk) → emit is mandatory.
    assert "height=32" in src

    # font kwarg should be omitted: every font_* knob is at Maker
    # default, so CTk's theme-resolved default font kicks in.
    assert "ctk.CTkFont(" not in src

    # corner_radius=6 (Maker) ≠ None (CTk) → emit.
    assert "corner_radius=6" in src


def test_user_changed_property_still_emits():
    project = Project()
    btn = _add_default_button(project, "btn")
    btn.properties["hover"] = False  # user toggled off
    src = generate_code(project)
    # Skip must NOT fire — value diverges from defaults.
    assert "hover=False" in src


def test_user_changed_font_emits_ctkfont():
    project = Project()
    btn = _add_default_button(project, "btn")
    btn.properties["font_bold"] = True  # user enabled bold
    src = generate_code(project)
    # Font knob diverges from default → CTkFont must emit.
    assert "ctk.CTkFont(" in src
    assert 'weight="bold"' in src
