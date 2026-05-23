"""Generate a runnable Python source file from a Project.

Multi-document projects emit one class per document:

- The first document (``is_toplevel=False``) becomes a ``ctk.CTk``
  subclass and is the ``__main__`` entry point.
- Every other document becomes a ``ctk.CTkToplevel`` subclass and is
  left for user code to open with ``SomeDialog(self)``.

Widgets live on the class instance as attributes so event handlers
added later can reach them via ``self``. The per-class
``_build_ui`` method does all the widget construction; ``__init__``
just sets window metadata and calls it.

Per-widget convention (matches ``WidgetDescriptor.transform_properties``):

- Keys in ``descriptor._NODE_ONLY_KEYS`` are stripped from kwargs
  (still used for ``place(x=x, y=y)`` and image size).
- ``button_enabled`` / ``state_disabled`` → ``state="disabled"/"normal"``.
- ``font_*`` keys → ``font=ctk.CTkFont(...)``.
- ``image`` path → ``image=ctk.CTkImage(...)`` with a PIL source.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from app.core.document import Document
from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.widgets.layout_schema import (
    DEFAULT_LAYOUT_TYPE,
    LAYOUT_CONTAINER_DEFAULTS,
    LAYOUT_DEFAULTS,
    LAYOUT_NODE_ONLY_KEYS,
    grid_effective_dims,
    normalise_layout_type,
    pack_side_for,
)
from app.widgets.registry import get_descriptor

DEFAULT_APPEARANCE_MODE = "dark"
INDENT = "    "

from app.io.code_exporter._utils import (
    _class_name_for,
    _py_literal,
    _slug,
)

# Module-level project-path stash so the per-image emit helpers can
# rewrite an in-assets absolute path to a relative ``assets/...``
# path without threading project context through every call site.
# Set at the top of ``export_project`` and cleared on the way out.
_CURRENT_PROJECT_PATH: str | None = None


from app.io.code_exporter.preview_screenshot import (
    _PREVIEW_SCREENSHOT_TEMPLATE,
    _preview_screenshot_lines,
)


_INCLUDE_DESCRIPTIONS_DEFAULT = True

# Phase 1 binding plumbing. Set by ``generate_code`` for the duration
# of a single export so ``_emit_widget`` can resolve ``var:<uuid>``
# tokens. Two layers:
#
#   ``_GLOBAL_VAR_ATTR``  — project-wide ``var_id → "var_<name>"``.
#       Stable across every class in the export so globals declared
#       on the main window are reachable as ``self.master.var_X``
#       from Toplevels.
#
#   ``_VAR_ID_TO_ATTR``   — per-class context. Set fresh inside each
#       ``_emit_class`` to ``var_id → "self.var_X"`` /
#       ``"self.master.var_X"`` so widget kwargs use the right form
#       for whichever class is currently being emitted.
_EXPORT_PROJECT = None
# CTkScript model — the component records (`_collect_doc_components`)
# for the document currently being emitted. Set in ``_emit_class_body``
# so ``_emit_handler_lines`` (running deep inside the subtree walk) can
# resolve ``script_call`` bindings to ``self._script_N.<method>``.
# ``None`` / empty when the doc has no attached components.
_CURRENT_DOC_COMPONENTS: list | None = None
# Phase 3 — populated at top of ``_generate_code_inner`` so
# ``_emit_handler_lines`` can skip stale handler bindings whose
# methods no longer exist in the per-window behavior file. Maps
# ``Document.id`` → set of method names defined on the doc's
# behavior class. Populated lazily; missing entry = "couldn't
# scan the file" (treated as "all bindings allowed", matching
# pre-1.8.3 behaviour so projects without behavior files still
# export cleanly).
_GLOBAL_VAR_ATTR: dict = {}
_VAR_ID_TO_ATTR: dict = {}
# Var-name fallbacks the exporter applied during this run because the
# user-set Properties-panel "Name" was empty / invalid / a duplicate.
# Tuples are ``(doc_name, intended, fallback, reason)``; reset at the
# start of each ``generate_code`` call. Surfaced via
# ``get_var_name_fallbacks()`` so launchers (F5 preview, export
# dialog) can show the user which names were silently rewritten.
_VAR_NAME_FALLBACKS: list[tuple[str, str, str, str]] = []
# Per-doc memoisation for ``_resolve_var_names`` so the resolver
# runs once per ``generate_code`` call per doc — keeps the
# ``_emit_subtree`` walk consistent without recomputing (and
# without double-recording warnings).
_NAME_MAP_CACHE: dict[str, dict[str, str]] = {}
# Static reserved set — names the exporter itself emits on the window
# class. Joined at check time with the lazy ``_ctk_inherited_names()``
# set below so user-set widget names can't shadow Tk root methods like
# ``title`` / ``geometry`` / ``mainloop`` / ``destroy`` / ``bind`` /
# ``configure`` / ``after`` / ``protocol`` / ``winfo_*`` / ``wm_*``,
# whose silent override breaks anything that touches the window
# (CTkScrollableDropdown calling ``root.title()``, CTk's own
# scaling, ``__init__`` calling ``self.geometry(...)``, etc.).
_RESERVED_VAR_NAMES = frozenset({
    "_build_ui",
})
_CTK_INHERITED_NAMES_CACHE: frozenset[str] | None = None


def _ctk_inherited_names() -> frozenset[str]:
    """Every non-dunder attribute on ``ctk.CTk`` ∪ ``ctk.CTkToplevel``,
    lazily computed once per process. Joined with
    ``_RESERVED_VAR_NAMES`` at validation time so the resolver
    rejects user-set widget Names that would shadow inherited
    methods. Pulled lazily to keep ``code_exporter`` import-free of
    CustomTkinter when nothing's actually exporting (test suites,
    cold imports).

    Filters dunders (``__init__``, ``__class__``, …) — those bounce
    on ``str.isidentifier`` ∪ private-by-convention rules anyway, no
    extra value in flagging them as "reserved". Single-underscore
    names (``_widget_scaling``, ``_apply_appearance_mode``) DO stay
    in the set — CTk's runtime touches them and a name collision
    would break appearance switching / DPI scaling silently.
    """
    global _CTK_INHERITED_NAMES_CACHE
    if _CTK_INHERITED_NAMES_CACHE is None:
        try:
            import customtkinter as _ctk
            names = (
                {n for n in dir(_ctk.CTk) if not n.startswith("__")}
                | {
                    n for n in dir(_ctk.CTkToplevel)
                    if not n.startswith("__")
                }
            )
        except Exception:
            names = set()
        _CTK_INHERITED_NAMES_CACHE = frozenset(names)
    return _CTK_INHERITED_NAMES_CACHE


from app.io.code_exporter.ctk_defaults import (
    _CTK_CONSTRUCTOR_DEFAULTS_CACHE,
    _CTK_DEFAULT_MISSING,
    _ctk_constructor_defaults,
    _kwarg_matches_defaults,
)


def _font_props_at_default(props: dict) -> bool:
    """True iff every font_* property is at its Maker default.

    When all six font knobs (family / size / bold / italic / underline /
    overstrike) match the descriptor default, the emitted CTkFont
    instance carries no information CTk's theme-resolved default font
    doesn't already supply — we can omit the ``font=`` kwarg entirely.
    Saves the per-widget ``ctk.CTkFont(...)`` instantiation + its
    ``<<RefreshFonts>>`` listener registration; on a 130-widget Showcase
    that's 130 listener calls per scaling/appearance change.
    """
    if _resolve_export_raw(props, "font_family"):
        return False
    if _safe_int(props.get("font_size", 13) or 13, 13) != 13:
        return False
    if _resolve_export_raw(props, "font_bold"):
        return False
    if _resolve_export_raw(props, "font_italic"):
        return False
    if _resolve_export_raw(props, "font_underline"):
        return False
    if _resolve_export_raw(props, "font_overstrike"):
        return False
    return True


def _is_non_textvariable_var_binding(
    widget_type: str, prop_key: str, value,
) -> bool:
    """True when a property's value is a ``var:<uuid>`` token AND the
    (widget, property) pair has no entry in ``BINDING_WIRINGS`` —
    i.e. the binding can't be wired through Tk's native
    ``textvariable=``/``variable=`` so it falls into the auto-trace
    fallback path. Used both at scan-time (to gate helper-function
    emission) and at emission-time.
    """
    from app.core.variables import BINDING_WIRINGS, parse_var_token
    if parse_var_token(value) is None:
        return False
    return (widget_type, prop_key) not in BINDING_WIRINGS


def _project_needs_auto_trace_helper(scoped_widgets) -> bool:
    """True when at least one widget in the export scope has a var
    binding that the auto-trace path will actually emit.

    Mirrors the gate ``_emit_auto_trace_bindings`` applies: bindings
    whose key isn't in the widget's CTk ``configure(...)`` signature
    are skipped (they'd crash at runtime), so projects whose only
    cosmetic bindings target Maker-only keys don't drag the helper
    function in.
    """
    for w in scoped_widgets:
        allowed = _ctk_configure_keys_for(w.widget_type)
        for key, val in (w.properties or {}).items():
            if not _is_non_textvariable_var_binding(w.widget_type, key, val):
                continue
            # Textbox content goes through ``_bind_var_to_textbox`` and
            # has its own helper gate; here we only care about whether
            # the configure-style helper is needed.
            if w.widget_type == "CTkTextbox" and key == "initial_text":
                continue
            if allowed is not None and key not in allowed:
                continue
            return True
    return False


def _project_needs_pack_balance(docs_to_emit, scoped_widgets) -> bool:
    """True when any vbox/hbox container with ≥1 child exists in
    the export scope. Both window-level layouts (Document) and
    nested containers count — both bind ``<Configure>`` to the
    flex-shrink helper. Pure ``place``/``grid`` projects skip
    the helper emission so generated files stay lean.
    """
    for doc in docs_to_emit:
        doc_layout = normalise_layout_type(
            (doc.window_properties or {}).get("layout_type"),
        )
        if doc_layout in ("vbox", "hbox") and doc.root_widgets:
            return True
    for w in scoped_widgets:
        layout = normalise_layout_type(
            (w.properties or {}).get("layout_type"),
        )
        if layout in ("vbox", "hbox") and w.children:
            return True
    return False


def _project_needs_auto_trace_font_helper(scoped_widgets) -> bool:
    """True when any widget in the export scope has a var binding on
    a font composite key (``font_bold`` / ``font_italic`` /
    ``font_size`` / ``font_family``). Mirrors the gate
    ``_emit_auto_trace_bindings`` applies for those keys, so projects
    without font-composite bindings don't drag in the helper.
    """
    for w in scoped_widgets:
        for key, val in (w.properties or {}).items():
            if key not in _FONT_COMPOSITE_TO_ATTR:
                continue
            if _is_non_textvariable_var_binding(
                w.widget_type, key, val,
            ):
                return True
    return False


def _project_needs_auto_trace_state_helper(scoped_widgets) -> bool:
    """True when any widget in the export scope has a var binding on
    ``button_enabled`` (or any other Maker-only bool→state composite).
    Mirrors ``_STATE_COMPOSITE_KEYS`` membership.
    """
    for w in scoped_widgets:
        for key, val in (w.properties or {}).items():
            if key not in _STATE_COMPOSITE_KEYS:
                continue
            if _is_non_textvariable_var_binding(
                w.widget_type, key, val,
            ):
                return True
    return False


def _project_needs_auto_trace_label_enabled_helper(scoped_widgets) -> bool:
    """True when any CTkLabel in the export scope has ``label_enabled``
    bound to a variable. Distinct from the generic state helper because
    Label doesn't use ``state="disabled"`` (Tk's native paints a stipple
    wash over images) — it swaps ``text_color`` manually.
    """
    for w in scoped_widgets:
        if w.widget_type != "CTkLabel":
            continue
        val = (w.properties or {}).get("label_enabled")
        if _is_non_textvariable_var_binding(
            w.widget_type, "label_enabled", val,
        ):
            return True
    return False


def _project_needs_auto_trace_font_wrap_helper(scoped_widgets) -> bool:
    """True when any CTkLabel in the export scope has ``font_wrap``
    bound to a variable. CTkButton has no wrap analogue, so this is
    CTkLabel-only.
    """
    for w in scoped_widgets:
        if w.widget_type != "CTkLabel":
            continue
        val = (w.properties or {}).get("font_wrap")
        if _is_non_textvariable_var_binding(
            w.widget_type, "font_wrap", val,
        ):
            return True
    return False


def _project_needs_auto_trace_font_autofit_helper(scoped_widgets) -> bool:
    """True when any CTkLabel in the export scope has ``font_autofit``
    bound to a variable. Brings the full autofit algorithm into the
    runtime helper block.
    """
    for w in scoped_widgets:
        if w.widget_type != "CTkLabel":
            continue
        val = (w.properties or {}).get("font_autofit")
        if _is_non_textvariable_var_binding(
            w.widget_type, "font_autofit", val,
        ):
            return True
    return False


def _project_needs_auto_trace_place_coord_helper(scoped_widgets) -> bool:
    """True when any widget in the export scope has ``x`` or ``y``
    bound to a variable.
    """
    for w in scoped_widgets:
        props = w.properties or {}
        for key in _PLACE_COORD_KEYS:
            if _is_non_textvariable_var_binding(
                w.widget_type, key, props.get(key),
            ):
                return True
    return False


def _project_needs_auto_trace_image_rebuild_helper(scoped_widgets) -> bool:
    """True when any widget has an image param (``image`` /
    ``image_width`` / ``image_height`` / ``preserve_aspect`` /
    ``image_color`` / ``image_color_disabled``) bound to a variable AND
    has an image set. Gates the shared block of image bind helpers.
    """
    for w in scoped_widgets:
        props = w.properties or {}
        if not props.get("image"):
            continue
        for key in _IMAGE_REBUILD_KEYS:
            if _is_non_textvariable_var_binding(
                w.widget_type, key, props.get(key),
            ):
                return True
    return False


def _project_needs_auto_trace_textbox_helper(scoped_widgets) -> bool:
    """True when at least one CTkTextbox has a var binding on a
    property whose update path is delete-then-insert rather than
    ``configure(prop=…)``. Currently scoped to ``initial_text`` —
    Textbox content. Other Textbox properties (state, etc.) go
    through the normal configure helper.
    """
    for w in scoped_widgets:
        if w.widget_type != "CTkTextbox":
            continue
        for key, val in (w.properties or {}).items():
            if key != "initial_text":
                continue
            if _is_non_textvariable_var_binding(
                w.widget_type, key, val,
            ):
                return True
    return False


from app.io.code_exporter.auto_trace_templates import (
    _FONT_COMPOSITE_TO_ATTR,
    _IMAGE_REBUILD_KEYS,
    _PLACE_COORD_KEYS,
    _STATE_COMPOSITE_KEYS,
)


def _ctk_configure_keys_for(widget_type: str) -> frozenset[str] | None:
    """Kwargs CTk's ``configure(...)`` accepts for the descriptor with
    the given ``widget_type``, derived from its CTk class's
    ``__init__`` signature.

    Returns ``None`` for descriptors that don't resolve to a CTk
    class (custom widgets like ``CircularProgress`` whose runtime
    isn't a CTk subclass) — callers should fall through to the
    pre-allowlist behaviour for those, since we have no
    authoritative kwarg list.

    Used by the auto-trace gate to skip Maker-only properties that
    composite into the widget at construction time (font_* rolled
    into ``CTkFont``, ``label_enabled`` → ``state=…``, ``image_color``
    baked into a tinted ``CTkImage``, ``dropdown_*`` passed to
    ``ScrollableDropdown.__init__``, …). CTk's runtime ``configure``
    raises ``ValueError`` on those keys, so emitting an auto-trace
    line for them turns into a guaranteed crash on first paint.
    """
    descriptor = get_descriptor(widget_type)
    if descriptor is None:
        return None
    primary = getattr(descriptor, "ctk_class_name", "") or ""
    defaults = _ctk_constructor_defaults(primary) if primary else {}
    if not defaults:
        fallback = getattr(descriptor, "type_name", "") or ""
        if fallback and fallback != primary:
            defaults = _ctk_constructor_defaults(fallback)
    if not defaults:
        return None
    return frozenset(defaults.keys())


def _emit_auto_trace_bindings(node, full_name: str) -> list[str]:
    """Phase 3 — produce ``_bind_var_to_widget`` / ``_bind_var_to_textbox``
    / ``_bind_var_to_font`` call lines for every property on ``node``
    that's bound to a variable but NOT in ``BINDING_WIRINGS``. Each
    line wires a ``trace_add`` listener that mirrors ``var.set(…)``
    calls into the appropriate Maker-side or CTk-side update path.

    Font composites (``font_bold`` / ``font_italic`` / ``font_size``
    / ``font_family``) route through ``_bind_var_to_font`` — Maker
    decomposes them into a single ``CTkFont`` at construction, so
    they aren't valid ``configure()`` kwargs but the helper rebuilds
    the font in place.

    Other Maker-only composites (``label_enabled`` / ``font_autofit``
    / ``image_color`` / ``dropdown_*`` …) still fall through the
    allowlist gate — they need their own per-composite rebuilders
    (planned phases 2 / 3 of live composite bindings).

    Custom widgets that don't resolve to a CTk class
    (``_ctk_configure_keys_for`` returns ``None``) bypass the
    allowlist — the v1.9.5 emit-everything behaviour holds for them.

    Returns an empty list when the widget has no qualifying
    bindings — preserves the pre-1.9.5 emit shape for widgets that
    only carry textvariable-mapped bindings (CTkLabel, CTkSlider,
    CTkSwitch, …).
    """
    from app.core.variables import parse_var_token
    if _EXPORT_PROJECT is None:
        return []
    allowed = _ctk_configure_keys_for(node.widget_type)
    out: list[str] = []
    # A CTkLabel with a tinted image has no native ``image_color_disabled``
    # kwarg (Tk's disabled render washes the image, so the editor never
    # sets ``state="disabled"``) — it gets a single resolved
    # ``image_color``. When image_color / image_color_disabled /
    # label_enabled is var-bound, emit a one-time ``_maker_label_tint``
    # dict so the tint bind helpers can re-resolve the active colour.
    # Button / Image widgets need no such dict — their tint bindings
    # configure the native kwargs directly.
    props_for_state = node.properties or {}
    if node.widget_type == "CTkLabel" and props_for_state.get("image"):
        if any(
            _is_non_textvariable_var_binding(
                node.widget_type, key, props_for_state.get(key),
            )
            for key in ("image_color", "image_color_disabled",
                        "label_enabled")
        ):
            _ic = _resolve_export_raw(props_for_state, "image_color", None)
            _icd = _resolve_export_raw(
                props_for_state, "image_color_disabled", None,
            )
            init_color = _ic if (_ic and _ic != "transparent") else None
            init_color_disabled = (
                _icd if (_icd and _icd != "transparent") else None
            )
            init_enabled = bool(
                _resolve_export_raw(
                    props_for_state, "label_enabled", True,
                )
            )
            out.append(
                f"{full_name}._maker_label_tint = "
                f"{{'color': {_py_literal(init_color)}, "
                f"'color_disabled': {_py_literal(init_color_disabled)}, "
                f"'enabled': {init_enabled!r}}}"
            )
    for key, val in (node.properties or {}).items():
        if not _is_non_textvariable_var_binding(node.widget_type, key, val):
            continue
        var_id = parse_var_token(val)
        if var_id is None:
            continue
        var_attr = _VAR_ID_TO_ATTR.get(var_id)
        if var_attr is None:
            continue
        # Textbox content uses the delete+insert helper because the
        # widget has no ``configure(text=…)`` slot. The configure
        # allowlist doesn't apply here — the helper's update path is
        # ``tb.delete(...); tb.insert(...)``, not configure().
        if node.widget_type == "CTkTextbox" and key == "initial_text":
            out.append(
                f"ctk.bind_var_to_textbox({var_attr}, {full_name})",
            )
            continue
        # Font composites route through their dedicated rebuilder —
        # CTk's configure() doesn't accept these keys, but they live-
        # update by rebuilding the widget's CTkFont in place.
        font_attr = _FONT_COMPOSITE_TO_ATTR.get(key)
        if font_attr is not None:
            out.append(
                f'ctk.bind_var_to_font({var_attr}, {full_name}, "{font_attr}")',
            )
            continue
        # ``button_enabled`` — bool var maps to CTk's ``state`` enum.
        # Routed through the state helper because the var holds
        # True/False, not "normal"/"disabled".
        if key in _STATE_COMPOSITE_KEYS:
            out.append(
                f"ctk.bind_var_to_state({var_attr}, {full_name})",
            )
            continue
        # ``label_enabled`` (CTkLabel only) — bool var maps to a
        # text_color swap. Both colors are captured as literals at
        # emit time so toggling back to enabled restores the original
        # text_color rather than reading whatever the widget currently
        # has (which would be the disabled color after the first flip).
        if key == "label_enabled" and node.widget_type == "CTkLabel":
            props = node.properties or {}
            on_val = (
                _resolve_export_raw(props, "text_color", "#ffffff")
                or "#ffffff"
            )
            off_val = (
                _resolve_export_raw(
                    props, "text_color_disabled", "#a0a0a0",
                )
                or "#a0a0a0"
            )
            out.append(
                f"ctk.bind_var_to_label_enabled({var_attr}, {full_name}, "
                f"{_py_literal(on_val)}, {_py_literal(off_val)})",
            )
            continue
        # ``font_wrap`` (CTkLabel only) — bool var drives wraplength
        # derivation from the widget's current width.
        if key == "font_wrap" and node.widget_type == "CTkLabel":
            out.append(
                f"ctk.bind_var_to_font_wrap({var_attr}, {full_name})",
            )
            continue
        # ``font_autofit`` (CTkLabel only) — bool var toggles binary-
        # search font sizing. The "off" font size is captured at emit
        # time as a literal so the helper can restore it on toggle.
        if key == "font_autofit" and node.widget_type == "CTkLabel":
            props = node.properties or {}
            shadow_size = props.get("_font_size_pre_autofit")
            base_size = props.get("font_size")
            size_off = shadow_size if shadow_size else base_size
            try:
                size_off_int = int(size_off or 13)
            except (TypeError, ValueError):
                size_off_int = 13
            out.append(
                f"ctk.bind_var_to_font_autofit({var_attr}, {full_name}, "
                f"{size_off_int})",
            )
            continue
        # ``x`` / ``y`` — number var drives place_configure on that axis.
        if key in _PLACE_COORD_KEYS:
            out.append(
                f'ctk.bind_var_to_place_coord({var_attr}, {full_name}, "{key}")',
            )
            continue
        # Image params — when var-bound, drive a live update on the
        # widget's native image kwargs or its CTkImage (fork >= 5.4.4-
        # 5.4.5). CTkLabel routes its tint through ``_maker_label_tint``
        # (it has no native ``image_color_disabled`` kwarg); CTkButton /
        # Image configure the native kwargs directly.
        if key in _IMAGE_REBUILD_KEYS:
            props = node.properties or {}
            if not props.get("image"):
                # No image set — nothing to update.
                continue
            if key == "image":
                out.append(
                    f"ctk.bind_var_to_image_path({var_attr}, {full_name})",
                )
            elif key == "image_width":
                out.append(
                    f'ctk.bind_var_to_image_size({var_attr}, {full_name}, "width")',
                )
            elif key == "image_height":
                out.append(
                    f'ctk.bind_var_to_image_size({var_attr}, {full_name}, "height")',
                )
            elif key == "preserve_aspect":
                out.append(
                    f"ctk.bind_var_to_preserve_aspect({var_attr}, {full_name})",
                )
            elif key == "image_color":
                if node.widget_type == "CTkLabel":
                    out.append(
                        f'ctk.bind_var_to_label_image_tint({var_attr}, {full_name}, "color")',
                    )
                else:
                    out.append(
                        f"ctk.bind_var_to_image_color({var_attr}, {full_name})",
                    )
            elif key == "image_color_disabled":
                if node.widget_type == "CTkLabel":
                    out.append(
                        f'ctk.bind_var_to_label_image_tint({var_attr}, {full_name}, "color_disabled")',
                    )
                elif "button_enabled" in props:
                    out.append(
                        f"ctk.bind_var_to_image_color_disabled({var_attr}, {full_name})",
                    )
                # else: widget has no image_color_disabled kwarg — skip
            continue
        if allowed is not None and key not in allowed:
            continue
        out.append(
            f'ctk.bind_var_to_widget({var_attr}, {full_name}, "{key}")',
        )
    return out


def _resolve_var_tokens_to_values(properties: dict) -> dict:
    """Return a copy of ``properties`` with every ``var:<uuid>`` token
    replaced by the variable's current default value. Used before
    handing props to a descriptor's ``export_state`` so post-init
    ``.insert()``/``.set()`` lines render the value, not the raw
    token. Variables that can't be resolved (stale binding, no
    project context) drop to an empty string — same fallback the
    constructor-kwarg path uses.
    """
    from app.core.variables import parse_var_token
    if _EXPORT_PROJECT is None:
        return properties
    resolved: dict | None = None
    for key, val in properties.items():
        var_id = parse_var_token(val)
        if var_id is None:
            continue
        entry = _EXPORT_PROJECT.get_variable(var_id)
        replacement: object = ""
        if entry is not None:
            replacement = _entry_default_as_value(entry)
        if resolved is None:
            resolved = dict(properties)
        resolved[key] = replacement
    return resolved if resolved is not None else properties


def _resolve_export_raw(props: dict, key: str, default=None):
    """Read ``props[key]``, resolving any ``var:<uuid>`` token to its
    bound variable's typed literal default.

    Read-ahead helpers (``_font_props_at_default``, dropdown kwargs,
    ``bool(props.get("button_enabled"))``, …) coerce property values
    to int/bool/float outside the main loop in ``_emit_widget`` —
    where the per-key var-resolution already runs. Without this
    resolve step those helpers crash on ``int('var:<uuid>')`` or
    silently treat a non-empty token string as ``True``.

    Stale bindings (variable deleted) and missing project context
    fall back to ``default`` so callers can keep their existing
    ``... or fallback`` idioms.
    """
    from app.core.variables import parse_var_token
    raw = props.get(key, default)
    var_id = parse_var_token(raw)
    if var_id is None:
        return raw
    entry = (
        _EXPORT_PROJECT.get_variable(var_id)
        if _EXPORT_PROJECT is not None else None
    )
    if entry is None:
        return default
    return _entry_default_as_value(entry)


def _build_global_var_attrs(project) -> dict:
    """Stable ``var_id → "var_<name>"`` for the project's globals.

    Names sanitised to Python identifiers + deduped against each
    other so two globals with the same display name don't collide
    in generated code. Used by every class in the export — the main
    window emits ``self.<attr>``, Toplevels reference
    ``self.master.<attr>``.
    """
    from app.core.variables import sanitize_var_name
    mapping: dict = {}
    used: set = set()
    for v in project.variables or []:
        base = sanitize_var_name(v.name) or "var"
        candidate = f"var_{base}"
        i = 2
        while candidate in used:
            candidate = f"var_{base}_{i}"
            i += 1
        used.add(candidate)
        mapping[v.id] = candidate
    return mapping


def _build_class_var_map(project, doc, force_main: bool) -> dict:
    """Per-class ``var_id → attr_ref`` used by widget-kwarg emission.

    Globals are reachable everywhere; the ref form depends on whether
    the current class owns them (``self.var_X``) or merely consumes
    them from its master (``self.master.var_X``). Locals are reachable
    only from their owner doc and always emit as ``self.var_X``.

    ``force_main=True`` flattens globals into the current class as if
    they were locals — single-document export of a Toplevel needs
    them attached to ``self`` so the file runs standalone.
    """
    from app.core.variables import sanitize_var_name
    mapping: dict = {}
    used_attrs: set = set(_GLOBAL_VAR_ATTR.values())
    is_main_class = force_main or not doc.is_toplevel
    for v in project.variables or []:
        attr = _GLOBAL_VAR_ATTR.get(v.id)
        if attr is None:
            continue
        if is_main_class:
            mapping[v.id] = f"self.{attr}"
        else:
            mapping[v.id] = f"self.master.{attr}"
    # Local attribute names dedupe against the global pool so a local
    # named identically to a global (allowed across scopes) doesn't
    # shadow the master ref or collide on the same class.
    for v in (doc.local_variables or []):
        base = sanitize_var_name(v.name) or "var"
        candidate = f"var_{base}"
        i = 2
        while candidate in used_attrs:
            candidate = f"var_{base}_{i}"
            i += 1
        used_attrs.add(candidate)
        mapping[v.id] = f"self.{candidate}"
    return mapping


def _format_var_value_lit(v) -> str:
    """Convert a VariableEntry's stored default into a Python literal
    suitable for ``tk.<Type>Var(value=...)``. Falls back to a safe
    zero-equivalent on type-mismatch so the export never raises at
    write time.
    """
    if v.type == "str":
        return repr(v.default)
    if v.type == "int":
        try:
            return str(int(v.default))
        except (TypeError, ValueError):
            return "0"
    if v.type == "float":
        try:
            return str(float(v.default))
        except (TypeError, ValueError):
            return "0.0"
    if v.type == "bool":
        return "True" if v.default == "True" else "False"
    return repr(v.default)


_TYPE_TO_TK_CLASS = {
    "str": "tk.StringVar",
    "int": "tk.IntVar",
    "float": "tk.DoubleVar",
    "bool": "tk.BooleanVar",
}


def _emit_class_variables(project, doc, force_main: bool) -> list[str]:
    """Emit the variable-declaration block for one class's
    ``_build_ui``.

    Globals appear here only on the main window class (or any class
    when ``force_main`` is set, so a single-doc Toplevel export keeps
    them). Locals always belong to their owner class. Empty list when
    nothing applies.
    """
    if not project:
        return []
    is_main_class = force_main or not doc.is_toplevel
    out: list[str] = []
    if is_main_class and project.variables:
        out.append("# Project variables — shared state across widgets.")
        for v in project.variables:
            attr = _GLOBAL_VAR_ATTR.get(v.id)
            if attr is None:
                continue
            cls = _TYPE_TO_TK_CLASS.get(v.type, "tk.StringVar")
            out.append(
                f"self.{attr} = {cls}(value={_format_var_value_lit(v)})",
            )
        out.append("")
    locals_for_doc = doc.local_variables or []
    if locals_for_doc:
        out.append("# Local variables — scoped to this window only.")
        for v in locals_for_doc:
            ref = _VAR_ID_TO_ATTR.get(v.id)
            if not ref or not ref.startswith("self."):
                continue
            attr = ref[len("self."):]
            cls = _TYPE_TO_TK_CLASS.get(v.type, "tk.StringVar")
            out.append(
                f"self.{attr} = {cls}(value={_format_var_value_lit(v)})",
            )
        out.append("")
    return out


def _preview_globals_on_host_lines(
    project, host_var: str, indent: str,
) -> list[str]:
    """Mirror project-global vars onto a bare-CTk preview host.

    The Toplevel-preview branch instantiates ``app = ctk.CTk()``
    instead of the main window class, so the main class's
    ``self.var_X`` declarations never run. A previewed Toplevel
    referencing ``self.master.var_X`` would then crash on the
    first var-bound widget — declare the same vars on ``app``
    directly so the lookup chain resolves.
    """
    if not project or not project.variables:
        return []
    out: list[str] = [f"{indent}# Project variables for preview host."]
    for v in project.variables:
        attr = _GLOBAL_VAR_ATTR.get(v.id)
        if attr is None:
            continue
        cls = _TYPE_TO_TK_CLASS.get(v.type, "tk.StringVar")
        out.append(
            f"{indent}{host_var}.{attr} = "
            f"{cls}(value={_format_var_value_lit(v)})",
        )
    return out


def _entry_default_as_value(entry):
    """Convert a VariableEntry's stored string default into the right
    Python value for its declared type. Used for unwired bindings —
    where the runtime can't pass a live ``tk.Variable`` so the
    exporter substitutes the variable's current value as a literal.
    """
    if entry is None:
        return None
    if entry.type == "int":
        try:
            return int(entry.default)
        except (TypeError, ValueError):
            return 0
    if entry.type == "float":
        try:
            return float(entry.default)
        except (TypeError, ValueError):
            return 0.0
    if entry.type == "bool":
        return entry.default == "True"
    return entry.default


def export_project(
    project: Project, path: str | Path,
    preview_dialog_id: str | None = None,
    single_document_id: str | None = None,
    as_zip: bool = False,
    asset_filter: set[Path] | None = None,
    inject_preview_screenshot: bool = False,
    include_descriptions: bool = True,
) -> None:
    """Generate a runnable .py from ``project`` at ``path``.

    ``asset_filter`` (P5): when given, only the listed asset files
    are copied next to the .py — useful for per-page exports where
    the rest of the shared asset pool shouldn't ship. ``None``
    keeps the legacy behaviour (whole ``assets/`` copied).
    """
    if as_zip:
        # Run the normal export into a tempdir, then zip the whole
        # tree (Python file + bundled assets/ + scrollable_dropdown
        # helper if present) into the user's chosen .zip path.
        import tempfile
        import zipfile
        out_zip = Path(path)
        if out_zip.suffix.lower() != ".zip":
            out_zip = out_zip.with_suffix(".zip")
        py_name = out_zip.with_suffix(".py").name
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            export_project(
                project, tmp_path / py_name,
                preview_dialog_id=preview_dialog_id,
                single_document_id=single_document_id,
                as_zip=False,
                asset_filter=asset_filter,
                include_descriptions=include_descriptions,
            )
            with zipfile.ZipFile(
                out_zip, "w", zipfile.ZIP_DEFLATED,
            ) as zf:
                for entry in sorted(tmp_path.rglob("*")):
                    if entry.is_file():
                        zf.write(entry, entry.relative_to(tmp_path))
        return
    global _CURRENT_PROJECT_PATH
    _CURRENT_PROJECT_PATH = project.path
    # Sync the cascade module so ``resolve_effective_family`` returns
    # the right family during export, even if the caller is operating
    # on a project that isn't the one currently loaded into the
    # main window (headless export, batch tooling).
    from app.core.fonts import set_active_project_defaults
    set_active_project_defaults(project.font_defaults)
    try:
        source = generate_code(
            project,
            preview_dialog_id=preview_dialog_id,
            single_document_id=single_document_id,
            inject_preview_screenshot=inject_preview_screenshot,
            include_descriptions=include_descriptions,
        )
    finally:
        _CURRENT_PROJECT_PATH = None
    out = Path(path)
    out.write_text(source, encoding="utf-8")
    # Copy the project's `assets/` folder next to the exported file
    # so the relative `assets/images/x.png` paths emitted in the
    # generated code resolve correctly when the user runs it.
    if project.path:
        from app.core.assets import project_assets_dir
        src_assets = project_assets_dir(project.path)
        if src_assets is None:
            src_assets = Path(project.path).parent / "assets"
        if src_assets.exists():
            try:
                if asset_filter is None:
                    shutil.copytree(
                        src_assets, out.parent / "assets",
                        dirs_exist_ok=True,
                    )
                else:
                    # Copy only the explicitly-listed asset files,
                    # preserving the relative path inside assets/ so
                    # ``asset:images/foo.png`` references the runtime
                    # generates still resolve.
                    src_resolved = src_assets.resolve()
                    for src_file in asset_filter:
                        try:
                            rel = Path(src_file).resolve().relative_to(
                                src_resolved,
                            )
                        except (OSError, ValueError):
                            continue
                        dst = out.parent / "assets" / rel
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            shutil.copy2(src_file, dst)
                        except OSError:
                            pass
            except OSError:
                pass
    # Side-car the ScrollableDropdown helper next to the export when
    # any ComboBox / OptionMenu is in the project — the import in the
    # generated code resolves it via the export directory.
    if _project_uses_scrollable_dropdown(project, single_document_id):
        helper_src = Path(
            __file__,
        ).resolve().parent.parent.joinpath(
            "widgets", "scrollable_dropdown.py",
        ).read_text(encoding="utf-8")
        out.with_name("scrollable_dropdown.py").write_text(
            helper_src, encoding="utf-8",
        )
    # CTkScript model — when any component is attached, ship the
    # ``CTkScript`` base as ``ctkmaker.py`` beside the export (so user
    # scripts' ``from ctkmaker import CTkScript`` resolves with no pip
    # install) and copy the project's top-level ``scripts/`` folder into
    # the bundle, with package markers so ``from scripts.<mod> import``
    # resolves. Self-contained build.
    if _project_uses_components(project, single_document_id):
        out.with_name("ctkmaker.py").write_text(
            _ctkscript_base_source(), encoding="utf-8",
        )
        if project.path:
            from app.core.project_folder import find_project_root
            root = find_project_root(project.path)
            src_scripts = (
                (root / "scripts") if root is not None
                else Path(project.path).parent / "scripts"
            )
            if src_scripts.is_dir():
                dst_scripts = out.parent / "scripts"
                try:
                    shutil.copytree(
                        src_scripts, dst_scripts, dirs_exist_ok=True,
                    )
                except OSError:
                    pass
                from app.io.library_scripts import write_package_markers_in
                write_package_markers_in(dst_scripts)


def _project_uses_custom_fonts(
    project: Project, scoped_widgets,
) -> bool:
    """Trigger font-registration plumbing when the project bundles
    custom font files OR any widget / cascade default points at a
    family that isn't a built-in (Tk's defaults always work without
    tkextrafont). Bundled files in ``assets/fonts/`` ship with the
    export, so the runtime needs the helper to load them.
    """
    if project.path:
        from app.core.assets import project_assets_dir
        assets = project_assets_dir(project.path)
        if assets is None:
            assets = Path(project.path).parent / "assets"
        fonts_dir = assets / "fonts"
        if fonts_dir.exists():
            for f in fonts_dir.iterdir():
                if f.is_file() and f.suffix.lower() in (".ttf", ".otf", ".ttc"):
                    return True
    if any(w.properties.get("font_family") for w in scoped_widgets):
        return True
    if any(project.font_defaults.values()):
        return True
    return False


def _project_uses_scrollable_dropdown(
    project: Project, single_document_id: str | None,
) -> bool:
    if single_document_id:
        doc = project.get_document(single_document_id)
        docs = [doc] if doc is not None else []
    else:
        docs = list(project.documents)
    for doc in docs:
        for root in doc.root_widgets:
            if root.widget_type in ("CTkComboBox", "CTkOptionMenu"):
                return True
            for desc in _iter_descendants(root):
                if desc.widget_type in ("CTkComboBox", "CTkOptionMenu"):
                    return True
    return False


def _project_uses_components(
    project: Project, single_document_id: str | None,
) -> bool:
    """True when any document or widget carries an attached CTkScript
    component — gates the ``ctkmaker.py`` base sidecar + ``scripts/``
    copy in the export."""
    if single_document_id:
        doc = project.get_document(single_document_id)
        docs = [doc] if doc is not None else []
    else:
        docs = list(project.documents)
    for doc in docs:
        if getattr(doc, "attached_components", None):
            return True
        for root in doc.root_widgets:
            if getattr(root, "attached_components", None):
                return True
            for desc in _iter_descendants(root):
                if getattr(desc, "attached_components", None):
                    return True
    return False


def generate_code(
    project: Project,
    preview_dialog_id: str | None = None,
    single_document_id: str | None = None,
    inject_preview_screenshot: bool = False,
    include_descriptions: bool = True,
) -> str:
    """Generate the project's ``.py`` source.

    When ``preview_dialog_id`` names one of the Toplevel documents,
    the ``__main__`` block is rewritten to open JUST that dialog on top
    of a withdrawn root — used by the per-dialog "▶ Preview" button in
    the canvas chrome so the designer can test a Toplevel in isolation
    without wiring a real event handler. All classes are still emitted
    unchanged so dialog-to-dialog references would resolve; only the
    ``__main__`` entry point differs.

    When ``single_document_id`` names any document (main window or
    Toplevel), only THAT document is emitted, and the class subclasses
    ``ctk.CTk`` regardless of the document's ``is_toplevel`` flag —
    the exported file is a standalone runnable app. Useful for the
    per-dialog Export button in the chrome, or the "Export active
    document" File-menu entry.

    ``include_descriptions`` (Phase 0 AI bridge): when True, the
    exporter emits each widget's ``description`` meta-property as a
    Python comment above its constructor so an AI can be handed the
    file and fill in the missing logic. Set False for clean
    production code.
    """
    global _INCLUDE_DESCRIPTIONS_DEFAULT, _EXPORT_PROJECT
    global _GLOBAL_VAR_ATTR, _VAR_ID_TO_ATTR
    global _VAR_NAME_FALLBACKS, _NAME_MAP_CACHE
    _prev = (
        _INCLUDE_DESCRIPTIONS_DEFAULT, _EXPORT_PROJECT,
        _GLOBAL_VAR_ATTR, _VAR_ID_TO_ATTR,
    )
    _INCLUDE_DESCRIPTIONS_DEFAULT = include_descriptions
    _EXPORT_PROJECT = project
    _GLOBAL_VAR_ATTR = _build_global_var_attrs(project)
    # Per-class map is rebuilt inside ``_emit_class``; start empty.
    _VAR_ID_TO_ATTR = {}
    # Reset the var-name fallback log + DFS-walk memoisation so this
    # export run starts from a clean slate. The log survives past
    # ``generate_code`` so launchers can read it via
    # ``get_var_name_fallbacks()`` after the export.
    _VAR_NAME_FALLBACKS = []
    _NAME_MAP_CACHE = {}
    try:
        return _generate_code_inner(
            project,
            preview_dialog_id=preview_dialog_id,
            single_document_id=single_document_id,
            inject_preview_screenshot=inject_preview_screenshot,
        )
    finally:
        (
            _INCLUDE_DESCRIPTIONS_DEFAULT,
            _EXPORT_PROJECT,
            _GLOBAL_VAR_ATTR,
            _VAR_ID_TO_ATTR,
        ) = _prev


def _generate_code_inner(
    project: Project,
    preview_dialog_id: str | None = None,
    single_document_id: str | None = None,
    inject_preview_screenshot: bool = False,
) -> str:
    # Single-document export narrows the widget scan + class emission
    # to just the requested document. Image scans must also respect
    # the filter so the PIL helper / tint import only lands when THIS
    # doc actually uses them.
    if single_document_id:
        target_doc = project.get_document(single_document_id)
        docs_to_emit = [target_doc] if target_doc is not None else []
    else:
        docs_to_emit = list(project.documents)

    def _doc_widgets(docs):
        for doc in docs:
            for root in doc.root_widgets:
                yield root
                yield from _iter_descendants(root)

    scoped_widgets = list(_doc_widgets(docs_to_emit))
    needs_pil = any(w.properties.get("image") for w in scoped_widgets)
    # ComboBox + OptionMenu wear our ScrollableDropdown helper for a
    # scrollable popup that matches the parent's pixel width.
    needs_scrollable_dropdown = any(
        w.widget_type in ("CTkComboBox", "CTkOptionMenu")
        for w in scoped_widgets
    )
    # Any radio with a non-empty `group` triggers a tk.StringVar
    # import + per-group declaration so radios in the same group
    # actually deselect each other in the runtime app.
    has_local_vars = any(
        bool(d.local_variables) for d in docs_to_emit
    )
    needs_circular_progress = any(
        w.widget_type == "CircularProgress" for w in scoped_widgets
    )
    needs_tk_import = (
        bool(project.variables)
        or has_local_vars
        or needs_circular_progress
        or any(
            w.widget_type == "CTkRadioButton"
            and str(w.properties.get("group") or "").strip()
            for w in scoped_widgets
        )
        # CTkScrollableFrame with place layout needs a manual
        # ``tk.Frame.configure(inner, width=, height=)`` to size its
        # inner content frame — see _emit_subtree for the why.
        or any(
            w.widget_type == "CTkScrollableFrame"
            and w.properties.get("layout_type") == "place"
            and w.children
            for w in scoped_widgets
        )
    )
    needs_font_register = _project_uses_custom_fonts(project, scoped_widgets)
    needs_auto_trace_helper = _project_needs_auto_trace_helper(scoped_widgets)
    needs_auto_trace_textbox = _project_needs_auto_trace_textbox_helper(
        scoped_widgets,
    )
    needs_auto_trace_font = _project_needs_auto_trace_font_helper(
        scoped_widgets,
    )
    needs_auto_trace_state = _project_needs_auto_trace_state_helper(
        scoped_widgets,
    )
    needs_auto_trace_label_enabled = (
        _project_needs_auto_trace_label_enabled_helper(scoped_widgets)
    )
    needs_auto_trace_font_wrap = (
        _project_needs_auto_trace_font_wrap_helper(scoped_widgets)
    )
    needs_auto_trace_font_autofit = (
        _project_needs_auto_trace_font_autofit_helper(scoped_widgets)
    )
    needs_auto_trace_place_coord = (
        _project_needs_auto_trace_place_coord_helper(scoped_widgets)
    )
    needs_auto_trace_image_rebuild = (
        _project_needs_auto_trace_image_rebuild_helper(scoped_widgets)
    )
    # v1.10.2: emit the flex-shrink runtime helper when any container
    # uses vbox/hbox with at least one child. Window-level layout
    # counts too — the document body may be the parent of the row.
    needs_pack_balance = _project_needs_pack_balance(
        docs_to_emit, scoped_widgets,
    )

    lines: list[str] = [
        "# Generated by CTkMaker",
        "",
        "import customtkinter as ctk",
    ]
    if needs_tk_import:
        lines.append("import tkinter as tk")
    if needs_pil:
        lines.append("from PIL import Image")
    if needs_scrollable_dropdown:
        lines.append("from scrollable_dropdown import ScrollableDropdown")
    if needs_font_register:
        lines.append("from pathlib import Path")
    lines.append("")

    # Phase 3 — auto-trace helpers for var bindings that don't map to
    # Tk's native ``textvariable=``/``variable=``. As of CTkMaker
    # v1.31.14 + ctkmaker-core 5.4.17, the helper bodies live in the
    # fork at ``customtkinter.bindings``; exports just call
    # ``ctk.bind_var_to_*(...)`` and ``ctk.balance_pack(...)``. No
    # per-helper preamble is needed here.

    if needs_circular_progress:
        lines.extend(_circular_progress_class_lines())
        lines.append("")

    used_class_names: set[str] = set()
    class_names: list[tuple[Document, str]] = []
    for index, doc in enumerate(docs_to_emit):
        cls_name = _class_name_for(doc, index, used_class_names)
        used_class_names.add(cls_name)
        class_names.append((doc, cls_name))

    # CTkScript model — import each attached component class from the
    # project's top-level ``scripts/`` folder. Gathered across every
    # document (window-level + per-widget components) and deduped by
    # (module, class) so a component reused on many objects imports
    # once. Empty for projects with no components — no lines emitted.
    component_imports: list[tuple[str, str]] = []
    seen_components: set[tuple[str, str]] = set()
    for doc, _cls in class_names:
        comp_sources = list(getattr(doc, "attached_components", []) or [])
        stack = list(doc.root_widgets)
        while stack:
            node = stack.pop()
            comp_sources.extend(getattr(node, "attached_components", []) or [])
            stack.extend(node.children)
        for comp in comp_sources:
            module = _component_module_path(comp.get("script", ""))
            cls = comp.get("class", "")
            if not module or not cls:
                continue
            key = (module, cls)
            if key in seen_components:
                continue
            seen_components.add(key)
            component_imports.append(key)
    if component_imports:
        for module, cls in component_imports:
            lines.append(f"from scripts.{module} import {cls}")
        lines.append("")

    # In single-document mode, force the class to subclass ctk.CTk so
    # the exported file is a standalone runnable app — even if the
    # source document is a CTkToplevel in the multi-doc project.
    force_main = bool(single_document_id)
    for doc, cls_name in class_names:
        lines.extend(_emit_class(
            doc, cls_name, force_main=force_main,
            register_fonts=needs_font_register,
        ))
        lines.append("")
        lines.append("")

    preview_match: tuple[Document, str] | None = None
    if preview_dialog_id and not single_document_id:
        for doc, cls in class_names:
            if doc.id == preview_dialog_id and doc.is_toplevel:
                preview_match = (doc, cls)
                break

    lines.append('if __name__ == "__main__":')
    lines.append(f'{INDENT}ctk.set_appearance_mode("{DEFAULT_APPEARANCE_MODE}")')

    if preview_match is not None:
        preview_doc, preview_cls = preview_match
        var = _slug(preview_doc.name) or "dialog"
        lines.append(f"{INDENT}# Dialog-only preview — hidden root host.")
        lines.append(f"{INDENT}app = ctk.CTk()")
        lines.append(f"{INDENT}app.withdraw()")
        # The bare ctk.CTk() host bypasses the main window class, so
        # custom fonts must be registered against it directly — without
        # this the dialog falls back to Tk defaults even though the
        # builder canvas renders the same widget with the right family.
        if needs_font_register:
            lines.append(
                f"{INDENT}ctk.register_project_fonts("
                f'app, Path(__file__).resolve().parent / "assets" / "fonts")'
            )
        # Bypassing the main class also skips its global-var
        # declarations, so the previewed Toplevel's
        # ``self.master.var_X`` lookup would fail. Mirror the
        # declarations onto the bare host before instantiation.
        lines.extend(
            _preview_globals_on_host_lines(_EXPORT_PROJECT, "app", INDENT),
        )
        lines.append(f"{INDENT}{var} = {preview_cls}(app)")
        if inject_preview_screenshot:
            lines.extend(_preview_screenshot_lines(target=var))
        lines.append(f"{INDENT}app.wait_window({var})")
    else:
        first_doc, first_class = class_names[0]
        lines.append(f"{INDENT}app = {first_class}()")
        # Comment out the way to open any Toplevel dialogs so the user
        # can copy the line into an event handler when they want to.
        for doc, cls in class_names[1:]:
            var = _slug(doc.name) or "dialog"
            lines.append(
                f"{INDENT}# {var} = {cls}(app)  "
                f"# open the '{doc.name}' dialog",
            )
        if inject_preview_screenshot:
            lines.extend(_preview_screenshot_lines(target="app"))
        lines.append(f"{INDENT}app.mainloop()")
    lines.append("")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Class + widget emission
# ----------------------------------------------------------------------
def get_var_name_fallbacks() -> list[tuple[str, str, str, str]]:
    """Return ``(doc_name, intended, fallback, reason)`` rows for
    every user-set widget Name the most recent export had to drop.
    Reasons: ``duplicate``, ``Python keyword``, ``not a valid Python
    identifier``, ``reserved by exported code``. Empty when every
    user name made it through cleanly. Read by F5 preview / export
    dialog launchers to show a pre-spawn notice — without one, a
    behavior file's ``self.window.<user_name>`` reference would
    raise ``AttributeError`` at runtime with no hint why.
    """
    return list(_VAR_NAME_FALLBACKS)


def _emit_handler_lines(
    node: WidgetNode, full_name: str,
) -> tuple[tuple[str, str] | None, list[str]]:
    """Resolve a widget's ``handlers`` mapping into:
    - one optional ``("command", "<expr>")`` kwarg tuple to fold into
      the constructor call (command-style events: CTkButton, Slider,
      ComboBox, OptionMenu, SegmentedButton, Switch, CheckBox,
      RadioButton).
    - a list of post-construction lines for bind-style events
      (CTkEntry / CTkTextbox <Return>, <KeyRelease>, <FocusOut>).

    Single method → bare reference (``self._script_N.foo``); multiple
    methods on the same event → lambda chain so every method fires
    in order. Bind-style events use ``add="+"`` so each method gets
    its own bind call without clobbering the previous one.

    Only ``script_call`` (CTkScript) handler entries are emitted.

    Empty ``handlers`` → returns ``(None, [])`` and no plumbing is
    emitted at all.
    """
    if not node.handlers:
        return None, []
    from app.widgets.event_registry import event_by_key
    command_kwarg: tuple[str, str] | None = None
    post_lines: list[str] = []
    # CTkScript model — components for the document being emitted, so
    # ``script_call`` bindings on this node resolve to the right
    # ``self._script_N`` instance. Empty for docs with no components.
    records = _CURRENT_DOC_COMPONENTS or []
    owner_id = node.id
    for key in node.handlers:
        entries = [
            e for e in node.handlers.get(key, [])
            if isinstance(e, dict) and e.get("kind") == "script_call"
        ]
        if not entries:
            continue
        entry = event_by_key(node.widget_type, key)
        if entry is None:
            # Stale binding — registry doesn't list this event for the
            # widget any more. Skip silently rather than emit broken
            # code; the Properties panel surfaces the dangling row.
            continue
        if entry.wiring_kind == "command":
            # Value-commands (slider / combo / option / segmented)
            # hand CTk's value through to the user's function as the
            # native arg; argless commands (button, switch, ...) pass
            # only the window.
            value_param = "v" if entry.command_passes_value else None
            command_kwarg = (
                "command",
                _format_handler_entries(
                    entries, value_param, records, owner_id,
                ),
            )
        elif entry.wiring_kind == "bind":
            seq = key.split(":", 1)[1] if ":" in key else key
            for ent in entries:
                # CTkScript method — context is self.widget /
                # self.window, so the Tk event is dropped (read
                # state off the widget instead). Skip if the
                # component can't be resolved in this doc.
                expr = _format_script_call(ent, records, owner_id)
                if expr is None:
                    continue
                post_lines.append(
                    f'{full_name}.bind('
                    f'"{seq}", lambda e: {expr}(), add="+")',
                )
    return command_kwarg, post_lines


def _format_handler_entries(
    entries: list,
    value_param: str | None = None,
    records: list | None = None,
    owner_id=None,
) -> str:
    """Render an ordered list of handler entries as the source for
    a ``command=`` kwarg.

    ``value_param`` is the native arg CTk passes to value-commands
    (``"v"`` for slider / combo / option / segmented) or ``None`` for
    argless commands (button, switch, checkbox, radio). It drives the
    lambda head.

    A single CTkScript method on an argless command stays a bare
    reference (``command=self._script_0.bump``) — CTk forwards its
    native arg directly, so no wrapper is needed. Anything else wraps
    in a tuple-style lambda so fan-out is visible at the call site.
    """
    records = records or []
    # Single CTkScript method on an argless command → bare reference
    # (``command=self._script_0.bump``); CTk calls it with no args,
    # matching the no-parameter ``def bump(self):`` convention.
    if (
        len(entries) == 1
        and isinstance(entries[0], dict)
        and entries[0].get("kind") == "script_call"
        and value_param is None
    ):
        expr = _format_script_call(entries[0], records, owner_id)
        if expr is not None:
            return expr
    parts: list[str] = []
    for entry in entries:
        # CTkScript method — no native arg (context via self.*).
        expr = _format_script_call(entry, records, owner_id)
        if expr is not None:
            parts.append(f"{expr}()")
    head = f"lambda {value_param}: " if value_param else "lambda: "
    return f"{head}({', '.join(parts)})"


# ---------------------------------------------------------------------
# CTkScript model — export engine (docs/plans/script_optimization.md)
#
# Pure helpers that turn a document's attached components + script_call
# bindings into runnable code. Wiring order in the window class:
#   1. instantiate every component BEFORE _build_ui() so event bindings
#      can reference ``self._script_N.<method>``;
#   2. _build_ui() emits the widgets + the event references;
#   3. after _build_ui(): inject scope (self.widget / self.window) now
#      that widgets exist, then call on_start on each component;
#   4. WM_DELETE_WINDOW: call on_close on each, then destroy.
# ---------------------------------------------------------------------
def _ctkscript_base_source() -> str:
    """The ``CTkScript`` base-class definition as text, for the exporter
    to inline into a self-contained build (no ``pip install``)."""
    import inspect

    from app.io.scripts.ctk_script import CTkScript

    return inspect.getsource(CTkScript)


def _component_module_path(script: str) -> str:
    """Map a ``scripts/``-relative file path to a dotted module path
    for the import statement — ``counter.py`` → ``counter``,
    ``sub/auth.py`` → ``sub.auth``. Empty input → empty (caller skips).
    """
    if not script:
        return ""
    stem = script[:-3] if script.endswith(".py") else script
    return stem.replace("\\", "/").strip("/").replace("/", ".")


def _collect_doc_components(doc, id_to_var: dict) -> list[dict]:
    """Component records for a document, in stable order — window
    components first, then widgets in DFS (pre-order). Each record::

        {var, scope, target, script, class, owner_id,
         var_bindings, field_values, fields}

    ``var`` is the instance attribute the window holds the component on
    (``_script_0`` ...); ``scope`` is ``"window"`` / ``"widget"``;
    ``target`` is the expression injected as the component's context
    (``self`` for window, ``self.<varname>`` for a widget); ``owner_id``
    is ``None`` for window components, else the widget id. ``fields`` is
    the script class's exposed ``[(name, var_type)]`` (AST), so the
    exporter can inject every field (bound / inline / default).
    """
    from pathlib import Path

    from app.core.script_paths import user_scripts_dir
    from app.io.scripts import parse_exposed_variables
    scripts_dir = (
        user_scripts_dir(getattr(_EXPORT_PROJECT, "path", None))
        if _EXPORT_PROJECT is not None else None
    )

    def _fields_for(script_rel, cls):
        if not scripts_dir or not script_rel or not cls:
            return []
        return parse_exposed_variables(Path(scripts_dir) / script_rel, cls)

    records: list[dict] = []
    counter = 0

    def _add(comps, scope, target, owner_id):
        nonlocal counter
        for comp in comps or []:
            script_rel = comp.get("script", "")
            cls = comp.get("class", "")
            records.append({
                "var": f"_script_{counter}",
                "scope": scope,
                "target": target,
                "script": script_rel,
                "class": cls,
                "owner_id": owner_id,
                "var_bindings": comp.get("var_bindings") or {},
                "field_values": comp.get("field_values") or {},
                "fields": _fields_for(script_rel, cls),
            })
            counter += 1

    _add(getattr(doc, "attached_components", None), "window", "self", None)
    stack = list(reversed(list(doc.root_widgets)))
    while stack:
        node = stack.pop()
        var_name = id_to_var.get(node.id, node.id)
        _add(
            getattr(node, "attached_components", None),
            "widget", f"self.{var_name}", node.id,
        )
        stack.extend(reversed(list(node.children)))
    return records


def _resolve_component_var(
    records: list[dict], owner_id, class_name: str, scope=None,
) -> str | None:
    """Instance var for a ``script_call``, honoring the entry's scope:

    * ``scope="widget"`` → only a component on ``owner_id`` (the widget),
    * ``scope="window"`` → only a window component,
    * ``scope=None`` (legacy entries) → owner first, then window.

    ``None`` when unresolved (the caller drops the binding)."""
    def _owner():
        return next(
            (
                r["var"] for r in records
                if r["class"] == class_name and r["owner_id"] == owner_id
            ),
            None,
        )

    def _window():
        return next(
            (
                r["var"] for r in records
                if r["class"] == class_name and r["scope"] == "window"
            ),
            None,
        )

    if scope == "widget":
        return _owner()
    if scope == "window":
        return _window()
    return _owner() or _window()


def _emit_component_init_lines(records: list[dict]) -> list[str]:
    """``self._script_N = ClassName()`` — emitted before _build_ui()."""
    return [
        f"{INDENT}{INDENT}self.{r['var']} = {r['class']}()"
        for r in records if r["class"]
    ]


def _field_value_literal(ftype: str, value: str) -> str:
    """A Python literal for an inline field value, by the field's tk
    Variable type. ``str`` / ``color`` → quoted; ``bool`` →
    ``True`` / ``False``; ``int`` / ``float`` → numeric with a safe
    fallback when the user-typed string is malformed."""
    raw = str(value).strip()
    if ftype == "bool":
        return "True" if raw.lower() in ("true", "1", "yes") else "False"
    if ftype == "int":
        try:
            return str(int(raw))
        except (ValueError, TypeError):
            return "0"
    if ftype == "float":
        try:
            return repr(float(raw))
        except (ValueError, TypeError):
            return "0.0"
    return repr(str(value))  # str / color / unknown → quoted


def _emit_component_post_lines(records: list[dict]) -> list[str]:
    """After _build_ui(): inject each component's scope, then every
    exposed field, then call ``on_start``.

    Each field is injected with its chosen source:

    * bound variable → ``self.var_X`` (per-class ``_VAR_ID_TO_ATTR`` —
      ``self.var_X`` or ``self.master.var_X``); a stale binding
      (variable deleted) falls back to a fresh default so the field is
      always set (Q7),
    * inline literal  → ``tk.<Type>Var(value=<lit>)``,
    * neither         → ``tk.<Type>Var()`` (type default).

    Order matters at runtime: scope + fields must be set before
    ``on_start`` so user setup code can use them.
    """
    inject = [
        f"{INDENT}{INDENT}self.{r['var']}."
        f"{'widget' if r['scope'] == 'widget' else 'window'} = {r['target']}"
        for r in records if r["class"]
    ]
    field_inject: list[str] = []
    for r in records:
        if not r["class"]:
            continue
        var_b = r.get("var_bindings") or {}
        val_b = r.get("field_values") or {}
        for fname, ftype in r.get("fields") or []:
            tk_cls = _TYPE_TO_TK_CLASS.get(ftype, "tk.StringVar")
            if fname in var_b:
                attr = _VAR_ID_TO_ATTR.get(var_b[fname])
                rhs = attr if attr is not None else f"{tk_cls}()"
            elif fname in val_b:
                rhs = f"{tk_cls}(value={_field_value_literal(ftype, val_b[fname])})"
            else:
                rhs = f"{tk_cls}()"
            field_inject.append(
                f"{INDENT}{INDENT}self.{r['var']}.{fname} = {rhs}",
            )
    starts = [
        f"{INDENT}{INDENT}self.{r['var']}.on_start()"
        for r in records if r["class"]
    ]
    return inject + field_inject + starts


def _emit_component_close_lines(records: list[dict]) -> list[str]:
    """WM_DELETE_WINDOW: on_close on each component, then destroy."""
    live = [r for r in records if r["class"]]
    if not live:
        return []
    calls = ", ".join(f"self.{r['var']}.on_close()" for r in live)
    return [
        f'{INDENT}{INDENT}self.protocol("WM_DELETE_WINDOW", '
        f'lambda: ({calls}, self.destroy()))',
    ]


def _format_script_call(entry: dict, records: list[dict], owner_id) -> str | None:
    """Bare reference to a ``script_call`` target —
    ``self._script_N.<method>`` — or ``None`` when the component can't
    be resolved. Used as a ``command=`` value or wrapped for a bind."""
    var = _resolve_component_var(
        records, owner_id, entry.get("class", ""), entry.get("scope"),
    )
    method = entry.get("method", "")
    if var is None or not method:
        return None
    return f"self.{var}.{method}"


def _resolve_var_names(doc: Document) -> dict[str, str]:
    """Walk a doc's widget tree DFS and produce the canonical
    ``{widget_id: var_name}`` map for every node. Single source of
    truth used by ``_emit_subtree`` (live emission) so the naming
    stays consistent across the export.

    Naming priority per node:
    1. ``node.name`` (user-set in the Properties panel) when it's a
       valid Python identifier and not a Python keyword and not in
       ``_RESERVED_VAR_NAMES``. Lets ``self.window.<user_name>``
       references in behavior files actually resolve.
    2. ``<type>_<N>`` counter fallback (``button_1`` / ``label_3`` /
       …) — the legacy default.

    Per-doc duplicate handling: first emission wins, second + later
    occurrences of the same name auto-suffix ``_2`` / ``_3`` (mirrors
    the variables-window naming convention). Counter-fallback
    candidates that would collide with a user-set name bump the
    counter forward until they land on something free.

    Drops are recorded in ``_VAR_NAME_FALLBACKS`` so the launcher can
    surface them — ``intended`` is the original name (or empty when
    no user intent), ``fallback`` is what we emitted, ``reason`` is
    one of ``duplicate`` / ``Python keyword`` / ``not a valid Python
    identifier`` / ``reserved by exported code``.

    Memoised per ``generate_code`` call via ``_NAME_MAP_CACHE`` so
    repeat calls (Phase 3 replay path) don't double-record warnings.
    """
    import keyword as _kw

    cached = _NAME_MAP_CACHE.get(doc.id)
    if cached is not None:
        return cached

    counts: dict[str, int] = {}
    taken: set[str] = set()
    id_map: dict[str, str] = {}
    doc_label = str(getattr(doc, "name", "") or "Window")

    inherited = _ctk_inherited_names()

    def _bad_reason(name: str) -> str | None:
        if not name.isidentifier():
            return "not a valid Python identifier"
        if _kw.iskeyword(name):
            return "Python keyword"
        if name in _RESERVED_VAR_NAMES or name in inherited:
            return "reserved by exported code"
        return None

    def _counter_fallback(node: WidgetNode) -> str:
        base = node.widget_type.replace("CTk", "").lower() or "widget"
        counts[base] = counts.get(base, 0) + 1
        candidate = f"{base}_{counts[base]}"
        # User may have already grabbed ``button_2`` as an explicit
        # widget name. Bump the counter forward instead of stomping
        # on it.
        while candidate in taken:
            counts[base] += 1
            candidate = f"{base}_{counts[base]}"
        return candidate

    def walk(node: WidgetNode) -> None:
        intent = (node.name or "").strip()
        if intent:
            reason = _bad_reason(intent)
            if reason is None:
                if intent in taken:
                    n = 2
                    while f"{intent}_{n}" in taken:
                        n += 1
                    final = f"{intent}_{n}"
                    _VAR_NAME_FALLBACKS.append(
                        (doc_label, intent, final, "duplicate"),
                    )
                else:
                    final = intent
            else:
                final = _counter_fallback(node)
                _VAR_NAME_FALLBACKS.append(
                    (doc_label, intent, final, reason),
                )
        else:
            final = _counter_fallback(node)
        taken.add(final)
        id_map[node.id] = final
        for child in node.children:
            walk(child)

    for root in doc.root_widgets:
        walk(root)
    _NAME_MAP_CACHE[doc.id] = id_map
    return id_map


def _iter_descendants(node):
    """DFS walk — yields every descendant of ``node`` (not ``node``
    itself). Mirrors ``project.iter_all_widgets`` but scoped to a
    single subtree for single-document export.
    """
    for child in node.children:
        yield child
        yield from _iter_descendants(child)


def _collect_radio_groups(
    root_widgets: list,
) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    """Walk every widget in the doc and group radios by their `group`
    name. Returns:

    - ``radio_var_map``: ``{node.id: (var_attr, value_string)}`` —
      the StringVar attribute the radio's ``variable=`` kwarg points
      to plus the unique value the ``value=`` kwarg holds.
    - ``group_to_var_attr``: ``{group_name: var_attr}`` — feeds the
      one-shot ``self._rg_<slug> = tk.StringVar(...)`` declarations
      emitted at the top of ``_build_ui``.

    Empty / whitespace-only group names are treated as standalone
    radios and skipped.
    """
    by_group: dict[str, list] = {}

    def walk(nodes):
        for n in nodes:
            if n.widget_type == "CTkRadioButton":
                grp = str(n.properties.get("group") or "").strip()
                if grp:
                    by_group.setdefault(grp, []).append(n)
            walk(n.children)

    walk(root_widgets)

    radio_var_map: dict[str, tuple[str, str]] = {}
    group_to_var_attr: dict[str, str] = {}
    for group, nodes in by_group.items():
        var_attr = f"self._rg_{_slug(group) or 'group'}"
        group_to_var_attr[group] = var_attr
        for i, node in enumerate(nodes):
            radio_var_map[node.id] = (var_attr, f"r{i + 1}")
    return radio_var_map, group_to_var_attr


def _emit_class(
    doc: Document, class_name: str, force_main: bool = False,
    register_fonts: bool = False,
) -> list[str]:
    # ``force_main`` is True for single-document export: the class
    # subclasses ``ctk.CTk`` even when the source doc is a Toplevel,
    # so the exported file runs as a standalone app. It also flips
    # globals into "owned by this class" mode so the file's variables
    # land on ``self`` instead of being orphaned ``self.master.*``
    # references.
    global _VAR_ID_TO_ATTR
    _prev_var_map = _VAR_ID_TO_ATTR
    _VAR_ID_TO_ATTR = _build_class_var_map(
        _EXPORT_PROJECT, doc, force_main,
    )
    try:
        return _emit_class_body(
            doc, class_name, force_main, register_fonts,
        )
    finally:
        _VAR_ID_TO_ATTR = _prev_var_map


def _emit_class_body(
    doc: Document, class_name: str, force_main: bool,
    register_fonts: bool,
) -> list[str]:
    global _CURRENT_DOC_COMPONENTS
    # CTkScript model — components attached to this window / its widgets.
    # Computed once: drives instantiation (before _build_ui), scope
    # injection + on_start (after), on_close, and script_call
    # resolution during the subtree walk. Empty for docs with none.
    _doc_components = _collect_doc_components(doc, _resolve_var_names(doc))
    if force_main or not doc.is_toplevel:
        base = "ctk.CTk"
    else:
        base = "ctk.CTkToplevel"
    lines: list[str] = []
    # Phase 0 AI bridge: prepend the document's plain-language
    # description as comments above the class definition. Same
    # gate as widget descriptions — toggled via ``include_descriptions``
    # on ``export_project`` / ``generate_code`` so the user can
    # choose clean production code.
    if _INCLUDE_DESCRIPTIONS_DEFAULT:
        doc_desc = (getattr(doc, "description", "") or "").strip()
        if doc_desc:
            for line in doc_desc.splitlines() or [doc_desc]:
                lines.append(f"# {line}")
    lines.append(f"class {class_name}({base}):")
    if base == "ctk.CTkToplevel":
        lines.append(f"{INDENT}def __init__(self, master=None):")
        lines.append(f"{INDENT}{INDENT}super().__init__(master)")
    else:
        lines.append(f"{INDENT}def __init__(self):")
        lines.append(f"{INDENT}{INDENT}super().__init__()")
        # Custom fonts must register against this Tk root before any
        # widget's CTkFont(family=...) resolves — Toplevels share the
        # parent root so they don't repeat the call.
        if register_fonts:
            lines.append(
                f"{INDENT}{INDENT}ctk.register_project_fonts("
                f'self, Path(__file__).resolve().parent / "assets" / "fonts")',
            )

    title = str(doc.name or "Window").replace('"', '\\"')
    geometry = f"{doc.width}x{doc.height}"
    lines.append(f'{INDENT}{INDENT}self.title("{title}")')
    lines.append(f'{INDENT}{INDENT}self.geometry("{geometry}")')

    win = doc.window_properties or {}
    resizable_x = bool(win.get("resizable_x", True))
    resizable_y = bool(win.get("resizable_y", True))
    if not (resizable_x and resizable_y):
        lines.append(
            f"{INDENT}{INDENT}self.resizable("
            f"{resizable_x}, {resizable_y})",
        )
    if bool(win.get("frameless", False)):
        lines.append(f"{INDENT}{INDENT}self.overrideredirect(True)")
    fg_color = win.get("fg_color")
    if fg_color and fg_color != "transparent":
        lines.append(
            f'{INDENT}{INDENT}self.configure(fg_color="{fg_color}")',
        )
    # CTkScript components — instantiate BEFORE _build_ui() so widget
    # event bindings can reference ``self._script_N.<method>``. Scope
    # (self.widget / self.window) is injected after the build.
    lines.extend(_emit_component_init_lines(_doc_components))
    lines.append(f"{INDENT}{INDENT}self._build_ui()")
    # CTkScript components — widgets exist now: inject each component's
    # scope (self.widget / self.window), call on_start, and wire
    # on_close to WM_DELETE_WINDOW.
    lines.extend(_emit_component_post_lines(_doc_components))
    lines.extend(_emit_component_close_lines(_doc_components))
    lines.append("")
    lines.append(f"{INDENT}def _build_ui(self):")

    # Pre-compute every widget's var name in DFS order. Threads the
    # user-set Properties-panel "Name" through to the emitted
    # ``self.<var> = ctk.<Type>(...)`` line so a window-scoped
    # CTkScript can reference widgets as ``self.window.<user_name>``
    # instead of the legacy ``<type>_<N>`` shape.
    id_to_var = _resolve_var_names(doc)
    # Expose components to ``_emit_handler_lines`` for the duration of
    # the subtree walk so ``script_call`` bindings resolve to the right
    # ``self._script_N`` instance; cleared before return.
    _CURRENT_DOC_COMPONENTS = _doc_components
    body_lines: list[str] = []
    # Phase 1.5 binding: shared variables come BEFORE widget
    # construction so any constructor below can reference
    # ``self.var_<name>`` for ``textvariable=`` / ``variable=``
    # kwargs. Globals only land on the main window class (or anywhere
    # under ``force_main``); locals attach to their owning class.
    body_lines.extend(
        _emit_class_variables(_EXPORT_PROJECT, doc, force_main),
    )
    radio_var_map, group_to_var_attr = _collect_radio_groups(
        doc.root_widgets,
    )
    if group_to_var_attr:
        body_lines.append(
            "# Shared StringVar per radio group — couples selection",
        )
        body_lines.append(
            "# across radios that share a `group` name.",
        )
        for group, var_attr in group_to_var_attr.items():
            body_lines.append(f'{var_attr} = tk.StringVar(value="")')
        body_lines.append("")
    if not doc.root_widgets:
        body_lines.append("pass")
    else:
        doc_props = doc.window_properties or {}
        doc_layout = normalise_layout_type(doc_props.get("layout_type"))
        try:
            doc_spacing = int(
                doc_props.get(
                    "layout_spacing",
                    LAYOUT_CONTAINER_DEFAULTS["layout_spacing"],
                ) or 0,
            )
        except (TypeError, ValueError):
            doc_spacing = 0
        # Window itself needs propagate(False) for non-place layouts
        # — otherwise pack/grid children would shrink self to their
        # natural size on first frame, defeating self.geometry("WxH").
        doc_rows = doc_cols = 1
        if doc_layout == "grid":
            doc_rows, doc_cols = grid_effective_dims(
                len(doc.root_widgets), doc_props,
            )
        if doc_layout != DEFAULT_LAYOUT_TYPE:
            body_lines.append("self.pack_propagate(False)")
            body_lines.append("self.grid_propagate(False)")
            if doc_layout == "grid":
                for rr in range(doc_rows):
                    body_lines.append(
                        f'self.grid_rowconfigure({rr}, weight=1, uniform="row")',
                    )
                for cc in range(doc_cols):
                    body_lines.append(
                        f'self.grid_columnconfigure({cc}, weight=1, uniform="col")',
                    )
            body_lines.append("")
        for idx, node in enumerate(doc.root_widgets):
            _emit_subtree(
                node,
                master_var="self",
                lines=body_lines,
                id_to_var=id_to_var,
                instance_prefix="self.",
                parent_layout=doc_layout,
                parent_spacing=doc_spacing,
                child_index=idx,
                parent_cols=doc_cols,
                parent_rows=doc_rows,
                radio_var_map=radio_var_map,
            )
        # v1.10.2 flex-shrink: window-level vbox/hbox needs the same
        # <Configure> bind that nested containers get in _emit_subtree.
        if doc_layout in ("vbox", "hbox") and doc.root_widgets:
            _balance_axis = "height" if doc_layout == "vbox" else "width"
            body_lines.append(
                f"self.bind("
                f"\"<Configure>\", "
                f"lambda _e: "
                f"ctk.balance_pack(self, {_balance_axis!r}))",
            )
    for line in body_lines:
        lines.append(f"{INDENT}{INDENT}{line}" if line else "")
    _CURRENT_DOC_COMPONENTS = None
    return lines


def _emit_subtree(
    node: WidgetNode,
    master_var: str,
    lines: list[str],
    id_to_var: dict[str, str],
    instance_prefix: str = "",
    parent_layout: str = DEFAULT_LAYOUT_TYPE,
    parent_spacing: int = 0,
    child_index: int = 0,
    parent_cols: int = 1,
    parent_rows: int = 1,
    radio_var_map: dict[str, tuple[str, str]] | None = None,
) -> None:
    var_name = id_to_var[node.id]
    lines.extend(
        _emit_widget(
            node, var_name, master_var, instance_prefix,
            parent_layout, parent_spacing, child_index,
            parent_cols, parent_rows,
            radio_var_map=radio_var_map,
        ),
    )
    lines.append("")
    child_master = f"{instance_prefix}{var_name}"
    child_layout = normalise_layout_type(
        node.properties.get("layout_type", DEFAULT_LAYOUT_TYPE),
    )
    # Compute this node's own effective grid dims so its children
    # know which column count to flow into.
    child_rows = child_cols = 1
    if child_layout == "grid":
        child_rows, child_cols = grid_effective_dims(
            len(node.children), node.properties,
        )
    # Containers with a non-place layout must freeze their configured
    # size: tk's default ``propagate(True)`` makes pack/grid parents
    # shrink to fit their children, which would collapse a Frame
    # built at 240×180 down to the natural size of whatever vbox
    # children it holds. Builder canvas already does this at widget
    # creation — the exported runtime needs it too.
    if (
        child_layout != DEFAULT_LAYOUT_TYPE and node.children
        and node.widget_type != "CTkScrollableFrame"
    ):
        # CTkScrollableFrame overrides ``grid_propagate`` to take no
        # positional args (it delegates to its outer ``_parent_frame``)
        # — ``grid_propagate(False)`` would raise ``TypeError`` at
        # runtime. Pinning is handled in SF's own ``export_state``
        # via ``_parent_frame.grid_propagate(False)``.
        lines.append(f"{child_master}.pack_propagate(False)")
        lines.append(f"{child_master}.grid_propagate(False)")
        if child_layout == "grid":
            for rr in range(child_rows):
                lines.append(
                    f'{child_master}.grid_rowconfigure({rr}, weight=1, uniform="row")',
                )
            for cc in range(child_cols):
                lines.append(
                    f'{child_master}.grid_columnconfigure({cc}, weight=1, uniform="col")',
                )
        lines.append("")
    elif (
        node.widget_type == "CTkScrollableFrame"
        and child_layout == DEFAULT_LAYOUT_TYPE
        and node.children
    ):
        # CTkScrollableFrame's inner ``tk.Frame`` (where children
        # actually live) only auto-grows from pack/grid kids — place
        # children leave it 0×0, so they render outside the canvas's
        # visible window. Compute the bbox of all place children at
        # export time and pin the inner frame to that size; the
        # frame's own ``<Configure>`` bind then updates the canvas's
        # scrollregion. ``CTkScrollableFrame.configure`` is overridden
        # to retarget the outer viewport canvas, so go through
        # ``tk.Frame.configure`` to actually hit the inner frame.
        max_w = _safe_int(node.properties.get("width", 0) or 0, 0)
        max_h = _safe_int(node.properties.get("height", 0) or 0, 0)
        for child in node.children:
            cx = _safe_int(child.properties.get("x", 0) or 0, 0)
            cy = _safe_int(child.properties.get("y", 0) or 0, 0)
            cw = _safe_int(child.properties.get("width", 0) or 0, 0)
            ch = _safe_int(child.properties.get("height", 0) or 0, 0)
            if cx + cw > max_w:
                max_w = cx + cw
            if cy + ch > max_h:
                max_h = cy + ch
        if max_w > 0 and max_h > 0:
            # CTk applies widget-scaling (DPI awareness) to the
            # outer viewport canvas at runtime, so the unscaled
            # bbox we computed at export time would leave the inner
            # frame shorter than the scaled viewport on hi-DPI
            # displays — scrolling never activates. Multiply by the
            # widget-scaling factor at runtime via the CTk helper.
            lines.append(
                f"_sf_scale = {child_master}._get_widget_scaling()",
            )
            lines.append(
                f"tk.Frame.configure({child_master}, "
                f"width=int({max_w} * _sf_scale), "
                f"height=int({max_h} * _sf_scale))",
            )
            lines.append(f"{child_master}.pack_propagate(False)")
            lines.append("")
    child_spacing = _safe_int(
        node.properties.get(
            "layout_spacing",
            LAYOUT_CONTAINER_DEFAULTS["layout_spacing"],
        ) or 0,
        0,
    )
    is_tabview = node.widget_type == "CTkTabview"
    tab_names_for_fallback: list[str] = []
    if is_tabview:
        raw = node.properties.get("tab_names") or ""
        tab_names_for_fallback = [
            ln.strip() for ln in str(raw).splitlines() if ln.strip()
        ] or ["Tab 1"]
    for idx, child in enumerate(node.children):
        if is_tabview:
            slot = getattr(child, "parent_slot", None)
            if not slot or slot not in tab_names_for_fallback:
                slot = tab_names_for_fallback[0]
            child_master_for_child = f"{child_master}.tab({slot!r})"
        else:
            child_master_for_child = child_master
        _emit_subtree(
            child,
            master_var=child_master_for_child,
            lines=lines,
            id_to_var=id_to_var,
            instance_prefix=instance_prefix,
            parent_layout=child_layout,
            parent_spacing=child_spacing,
            child_index=idx,
            parent_cols=child_cols,
            parent_rows=child_rows,
            radio_var_map=radio_var_map,
        )

    # v1.10.2 flex-shrink: bind the container's <Configure> so the
    # runtime helper redistributes pack children's main-axis size
    # whenever the container resizes (initial map fires <Configure>
    # too — covers first paint without an extra after_idle call).
    # CTkScrollableFrame needs add="+" — its __init__ already binds
    # <Configure> to update the inner canvas's scrollregion, and a
    # plain bind() would replace it (default add=None), leaving the
    # scrollbar with no content bbox to size against. The +variant
    # lets both fire so grow children get their flex slot AND the
    # scrollregion stays accurate. The helper itself works on SF
    # because SF inherits tk.Frame as its inner content frame —
    # children pack onto SF directly and SF.pack_slaves() returns
    # them.
    if (
        child_layout in ("vbox", "hbox") and node.children
        and not is_tabview
    ):
        _balance_axis = "height" if child_layout == "vbox" else "width"
        _bind_extra = (
            ', add="+"'
            if node.widget_type == "CTkScrollableFrame" else ""
        )
        lines.append(
            f"{child_master}.bind("
            f"\"<Configure>\", "
            f"lambda _e, _c={child_master}: "
            f"ctk.balance_pack(_c, {_balance_axis!r})"
            f"{_bind_extra})",
        )
        lines.append("")


def _emit_widget(
    node: WidgetNode,
    var_name: str,
    master_var: str,
    instance_prefix: str = "",
    parent_layout: str = DEFAULT_LAYOUT_TYPE,
    parent_spacing: int = 0,
    child_index: int = 0,
    parent_cols: int = 1,
    parent_rows: int = 1,
    radio_var_map: dict[str, tuple[str, str]] | None = None,
) -> list[str]:
    descriptor = get_descriptor(node.widget_type)
    if descriptor is None:
        return [f"# unknown widget type: {node.widget_type}"]

    props = node.properties
    node_only: set[str] = getattr(descriptor, "_NODE_ONLY_KEYS", set())
    font_keys: set[str] = getattr(descriptor, "_FONT_KEYS", set())
    shadow_keys: set[str] = getattr(descriptor, "_SHADOW_KEYS", set())
    multiline_list_keys: set[str] = getattr(
        descriptor, "multiline_list_keys", set(),
    )
    overrides: dict = descriptor.export_kwarg_overrides(props)

    # v1.10.0 default-skip catalog: drop kwargs whose value already
    # matches BOTH the descriptor's default AND the CTk constructor's
    # default. Resolution order:
    #   1. descriptor.ctk_class_name — direct CTk wrappers (CTkLabel,
    #      CTkSwitch, …) hit the catalog on the first try.
    #   2. descriptor.type_name — fallback for when ctk_class_name names
    #      a class not on the customtkinter module (a custom subclass):
    #      type_name pulls the CTk parent's signature, the right
    #      reference for the skip gate.
    #   3. None of the above resolves → ctk_defaults stays empty and
    #      _kwarg_matches_defaults short-circuits to False everywhere,
    #      preserving pre-v1.10.0 emit-everything behavior for fully
    #      custom widgets like ``CircularProgress``.
    maker_defaults: dict = getattr(descriptor, "default_properties", {})
    ctk_defaults: dict = {}
    _ctk_class_primary = getattr(descriptor, "ctk_class_name", "")
    if _ctk_class_primary:
        ctk_defaults = _ctk_constructor_defaults(_ctk_class_primary)
    if not ctk_defaults:
        _ctk_class_fallback = getattr(descriptor, "type_name", "")
        if _ctk_class_fallback and _ctk_class_fallback != _ctk_class_primary:
            ctk_defaults = _ctk_constructor_defaults(_ctk_class_fallback)

    from app.core.variables import BINDING_WIRINGS, parse_var_token

    kwargs: list[tuple[str, str]] = []
    # Wired bindings — emitted at the end so the kwarg order doesn't
    # matter for CTk's __init__, but kept in a separate list because
    # their values are attribute references (not Python literals) and
    # ``_py_literal`` would mangle them.
    var_kwargs: list[tuple[str, str]] = []
    # Properties whose binding routed to a constructor kwarg via
    # ``var_kwargs``. Tracked separately so the descriptor's
    # ``export_state`` (post-init ``.insert(0, …)`` / ``.set(…)``
    # / ``.select()`` lines) skips them — the textvariable kwarg
    # already wires the runtime, and emitting a literal token on top
    # would either insert ``var:<uuid>`` text or fight the live var.
    wired_bound_keys: set[str] = set()

    for key, val in props.items():
        # pack_* / grid_* / layout_type live on the node for export,
        # never as CTk constructor kwargs.
        if key in LAYOUT_NODE_ONLY_KEYS:
            continue
        # Phase 1 binding: ``var:<uuid>`` token. Resolve BEFORE the
        # node_only / font / image filter so wired bindings on
        # editor-only properties (CTkEntry.initial_value,
        # CTkSlider.initial_value, CTkSwitch.initially_checked, …)
        # can still emit the matching textvariable / variable kwarg
        # — those properties live in NODE_ONLY because they aren't
        # CTk constructor args, but the BINDING_WIRINGS table maps
        # them onto the kwargs CTk does accept.
        var_id = parse_var_token(val)
        if var_id is not None:
            wiring = BINDING_WIRINGS.get((node.widget_type, key))
            if wiring and var_id in _VAR_ID_TO_ATTR:
                var_kwargs.append((wiring, _VAR_ID_TO_ATTR[var_id]))
                wired_bound_keys.add(key)
                continue
            entry = (
                _EXPORT_PROJECT.get_variable(var_id)
                if _EXPORT_PROJECT is not None else None
            )
            if entry is not None:
                val = _entry_default_as_value(entry)
            else:
                continue  # stale binding — drop the kwarg entirely
        # Standard skip filter applies to non-binding (or
        # literal-substituted) values only.
        if (
            key in node_only
            or key in font_keys
            or key in shadow_keys
            or key == "image"
        ):
            continue
        if key in overrides:
            val = overrides[key]
        if key in multiline_list_keys:
            lines_list = [
                ln for ln in str(val or "").splitlines() if ln.strip()
            ] or [""]
            kwargs.append((key, _py_literal(lines_list)))
            continue
        # v1.10.0 default-skip: omit kwargs whose value already matches
        # both Maker's descriptor default AND CTk's constructor default.
        # Override-bound keys still emit — overrides intentionally
        # rewrite the value (e.g. CTkOptionMenu's dynamic_resizing=False).
        if (
            key not in overrides
            and _kwarg_matches_defaults(
                key, val, maker_defaults, ctk_defaults,
            )
        ):
            continue
        kwargs.append((key, _py_literal(val)))
    # Override-only keys: descriptors can inject runtime-only kwargs
    # (e.g. CTkSegmentedButton / CTkOptionMenu's
    # ``dynamic_resizing=False`` that pins the widget's width to what
    # the builder set) by returning them from ``export_kwarg_overrides``
    # without an entry in ``properties``. Without this fan-out, the
    # exported file would miss those kwargs and fall back to CTk's
    # auto-resize default — visible bug: a 600px segmented button
    # exported as 80px because CTk re-fits to content.
    emitted = {k for k, _ in kwargs}
    for key, val in overrides.items():
        if (
            key in emitted
            or key in node_only
            or key in font_keys
            or key in shadow_keys
        ):
            continue
        if key in LAYOUT_NODE_ONLY_KEYS:
            continue
        kwargs.append((key, _py_literal(val)))

    # CTkTabview's `anchor` (and `tab_stretch`) are derived from the
    # node-only `tab_position` / `tab_anchor` pair by the descriptor's
    # `export_kwarg_overrides`, which the override fan-out above already
    # emitted — so the exported tab-bar placement matches the editor
    # preview (both share `_TAB_ANCHOR_MAP`).

    if "button_enabled" in props:
        # CTkEntry adds a `readonly` boolean that wins over disabled.
        if props.get("readonly"):
            state_src: str | None = '"readonly"'
        elif not props.get("button_enabled", True):
            state_src = '"disabled"'
        else:
            # v1.10.0: ``state="normal"`` is CTk's constructor default,
            # so omit the kwarg — same runtime behavior, smaller emit.
            state_src = None
        if state_src is not None:
            kwargs.append(("state", state_src))

    # Group-coupled radio: thread the shared StringVar + the unique
    # value through the constructor. CTkRadioButton accepts both only
    # in __init__, never via configure.
    if (
        node.widget_type == "CTkRadioButton"
        and radio_var_map is not None
        and node.id in radio_var_map
    ):
        var_attr, value = radio_var_map[node.id]
        kwargs.append(("variable", var_attr))
        kwargs.append(("value", f'"{value}"'))
    elif "state_disabled" in props:
        # v1.10.0: only emit when actually disabled — "normal" is CTk's
        # constructor default and skipping leaves the runtime identical.
        if props.get("state_disabled"):
            kwargs.append(("state", '"disabled"'))

    # CTkEntry password masking → `show="•"` kwarg.
    if props.get("password"):
        kwargs.append(("show", '"•"'))

    if "border_enabled" in props and not props.get("border_enabled"):
        kwargs = [
            (k, '0' if k == "border_width" else v) for k, v in kwargs
        ]

    if font_keys and any(k in props for k in font_keys):
        from app.core.fonts import resolve_effective_family
        effective_family = resolve_effective_family(
            node.widget_type, props.get("font_family"),
        )
        # Most widgets attach the font to ``font``; CTkScrollableFrame
        # exposes ``label_font`` for its header instead. Descriptors
        # set ``font_kwarg`` to control which kwarg the exporter emits.
        # Skip emitting altogether when no family resolved AND the
        # descriptor only carries font_family (size/weight knobs would
        # still want a default-sized CTkFont; ScrollableFrame doesn't).
        font_kwarg_name = getattr(descriptor, "font_kwarg", "font")
        if font_kwarg_name is None:
            # Descriptor handles font emission itself (e.g. CTkTabview
            # writes ``_segmented_button.configure(font=...)`` from
            # export_state because its __init__ has no ``font`` kwarg).
            pass
        elif (
            font_kwarg_name == "label_font"
            and not effective_family
        ):
            pass  # leave label_font unset → CTk theme picks default
        elif (
            not effective_family
            and _font_props_at_default(props)
        ):
            # v1.10.0: every font knob at Maker/CTk default — omit the
            # kwarg so CTk's theme-resolved default font kicks in. Saves
            # one CTkFont instance + one ``<<RefreshFonts>>`` listener
            # per widget; on a Showcase-class project (130 widgets)
            # that's the dominant scaling-toggle latency cost.
            pass
        else:
            kwargs.append(
                (font_kwarg_name, _font_source(props, effective_family)),
            )

    image_path = props.get("image")
    # Generic pre-/post-constructor line hooks (currently unused by the
    # image path — the native tint kwargs land inline below).
    pre_lines: list[str] = []
    post_image_lines: list[str] = []
    inline_image = getattr(descriptor, "image_inline_kwarg", True)
    if image_path and not inline_image:
        # Descriptor builds the image off-band (e.g. Card's inner
        # CTkLabel via ``export_state``) — don't auto-emit
        # ``image=`` / ``compound=`` to the constructor since the
        # underlying CTk class wouldn't accept them.
        image_path = None
    if image_path:
        kwargs.append(("image", _image_source(props, image_path)))
        if "compound" not in props:
            kwargs.append(("compound", '"left"'))
        # image_color / image_color_disabled tint the widget's image
        # natively (fork >= 5.4.5). ``transparent`` is the colour-
        # editor's "cleared" sentinel — normalise it to None (no tint);
        # emit only non-None values so an untinted widget keeps CTk's
        # default.
        def _active(c):
            return c if c and c != "transparent" else None
        if "button_enabled" in props:
            # CTkButton emits ``state=`` (above), so hand the widget
            # both colours and let the fork swap between them on state.
            image_color = _active(
                _resolve_export_raw(props, "image_color"),
            )
            image_color_disabled = _active(
                _resolve_export_raw(props, "image_color_disabled"),
            )
        else:
            # CTkLabel / Image never get ``state="disabled"`` (Tk's
            # native disabled render washes a stipple over the image),
            # so resolve the active tint here from label_enabled —
            # mirrors what the editor descriptor does.
            image_color_disabled = None
            if (
                "label_enabled" in props
                and not bool(
                    _resolve_export_raw(props, "label_enabled"),
                )
            ):
                image_color = (
                    _active(
                        _resolve_export_raw(
                            props, "image_color_disabled",
                        ),
                    )
                    or _active(
                        _resolve_export_raw(props, "image_color"),
                    )
                )
            else:
                image_color = _active(
                    _resolve_export_raw(props, "image_color"),
                )
        if image_color:
            kwargs.append(
                ("image_color", _py_literal(image_color)),
            )
        if image_color_disabled:
            kwargs.append(
                (
                    "image_color_disabled",
                    _py_literal(image_color_disabled),
                ),
            )

    ctk_class = (
        getattr(descriptor, "ctk_class_name", "") or node.widget_type
    )
    is_ctk_class_for_node = bool(getattr(descriptor, "is_ctk_class", True))
    full_name = f"{instance_prefix}{var_name}"
    # Phase 0 AI bridge: prepend the widget's plain-language description
    # as comments above its constructor call. Empty descriptions skip.
    # Toggled via ``include_descriptions`` on ``export_project`` /
    # ``generate_code`` so the user can choose clean production code.
    description_lines: list[str] = []
    if _INCLUDE_DESCRIPTIONS_DEFAULT:
        desc = (getattr(node, "description", "") or "").strip()
        if desc:
            for line in desc.splitlines() or [desc]:
                description_lines.append(f"# {line}")
    lines: list[str] = description_lines + list(pre_lines)
    # Phase 2 — fold event handler bindings into the constructor or
    # collect them as post-init ``.bind(...)`` lines. Inspecting the
    # node's ``handlers`` mapping against the widget's event registry
    # lets us route command-style events to a kwarg (so the runtime
    # call is single-pass) and bind-style events to ``widget.bind``
    # statements emitted after the constructor.
    command_kwarg, post_handler_lines = _emit_handler_lines(
        node, full_name,
    )
    if command_kwarg is not None:
        kwargs.append(command_kwarg)

    class_prefix = "ctk." if is_ctk_class_for_node else ""
    lines.append(f"{full_name} = {class_prefix}{ctk_class}(")
    lines.append(f"    {master_var},")
    for key, src in kwargs:
        lines.append(f"    {key}={src},")
    # Wired bindings come last; their ``src`` is already a Python
    # expression (``self.var_X``) so it's emitted verbatim, no
    # ``_py_literal`` quoting.
    for key, src in var_kwargs:
        lines.append(f"    {key}={src},")
    lines.append(")")

    # Auto icon-state wiring lands right after construction so a later
    # configure(state=...) — whether from a handler, a behavior file, or
    # a binding trace — picks the matching tinted image without any
    # caller-side bookkeeping.
    lines.extend(post_image_lines)

    lines.append(
        _geometry_call(
            full_name, props, parent_layout, parent_spacing,
            child_index, parent_cols, parent_rows,
        ),
    )

    # v1.10.2 flex-shrink: tag pack children with content-min floor +
    # user-fixed flag so the runtime ``_ctkmaker_balance_pack`` helper
    # knows how to redistribute when the container resizes. Skipped
    # for grid/place — only pack participates in the auto-shrink loop.
    # Both ``fixed`` and ``fill`` mark the child as user-controlled on
    # the main axis (helper skips them); only ``grow`` is auto-sized.
    _normalised_parent = normalise_layout_type(parent_layout)
    if _normalised_parent in ("vbox", "hbox"):
        from app.widgets.content_min import content_min_axis
        _axis = "height" if _normalised_parent == "vbox" else "width"
        _min = content_min_axis(node, _axis)
        lines.append(f"{full_name}._ctkmaker_min = {_min}")
        if str(props.get("stretch", "fixed")) in ("fixed", "fill"):
            lines.append(f"{full_name}._ctkmaker_fixed = True")
        # Image is a CTkLabel + CTkImage; the helper needs to resize
        # the embedded CTkImage, not just the label box. Marker tells
        # _ctkmaker_balance_pack to reach through to widget._image.
        if node.widget_type == "Image":
            lines.append(f"{full_name}._ctkmaker_image = True")

    # Phase 2 — bind-style events (CTkEntry / CTkTextbox <Return> etc.)
    # land here, AFTER geometry so the widget is fully constructed and
    # its underlying tk widget exists for ``widget.bind``. Multiple
    # methods on the same sequence chain through ``add="+"`` so they
    # all fire in registration order.
    lines.extend(post_handler_lines)
    # Strip wired-bound keys before handing props to ``export_state``
    # so descriptors don't emit ``.insert(0, 'var:<uuid>')`` /
    # ``.set('var:<uuid>')`` / ``.select()`` lines for properties the
    # constructor's textvariable kwarg already drives.
    if wired_bound_keys:
        state_props = {
            k: v for k, v in props.items() if k not in wired_bound_keys
        }
    else:
        state_props = props
    # Phase 3 — resolve any remaining ``var:<uuid>`` tokens in
    # ``state_props`` to the variable's current value so the
    # descriptor's post-init lines (``.insert("1.0", …)``,
    # ``.set(…)``, etc.) render with real text instead of a literal
    # token. The auto-trace bindings emitted below take care of
    # later runtime updates.
    state_props = _resolve_var_tokens_to_values(state_props)
    lines.extend(descriptor.export_state(full_name, state_props))
    # Phase 3 — auto-trace bindings for properties that have a
    # ``var:<uuid>`` token but no entry in ``BINDING_WIRINGS``.
    # CTkButton.text, CTkButton.fg_color, CTkTextbox content etc.
    # all fall here. Helper functions (emitted at module level when
    # any project widget needs them) take care of the actual
    # ``trace_add`` plumbing; this site just calls the right one
    # with the variable + widget reference.
    lines.extend(_emit_auto_trace_bindings(node, full_name))
    # ScrollableDropdown side-car wiring for ComboBox + OptionMenu. The
    # helper class lives in scrollable_dropdown.py beside this file.
    if node.widget_type in ("CTkComboBox", "CTkOptionMenu"):
        lines.extend(_scrollable_dropdown_lines(full_name, props))
    # Group-coupled radio: prime the shared StringVar when this radio
    # is the one the user marked as initially checked. Standalone
    # radios fall through to the descriptor's plain `.select()` line.
    if (
        node.widget_type == "CTkRadioButton"
        and radio_var_map is not None
        and node.id in radio_var_map
        and props.get("initially_checked")
    ):
        var_attr, value = radio_var_map[node.id]
        lines.append(f'{var_attr}.set("{value}")')
    return lines


def _scrollable_dropdown_lines(var_name: str, props: dict) -> list[str]:
    bw = _safe_int(props.get("dropdown_border_width", 1), 1)
    if not _resolve_export_raw(props, "dropdown_border_enabled", True):
        bw = 0
    kwargs = [
        ("fg_color", _resolve_export_raw(
            props, "dropdown_fg_color", "#2b2b2b",
        )),
        ("text_color", _resolve_export_raw(
            props, "dropdown_text_color", "#dce4ee",
        )),
        ("hover_color", _resolve_export_raw(
            props, "dropdown_hover_color", "#3a3a3a",
        )),
        ("offset", _safe_int(props.get("dropdown_offset", 4), 4)),
        ("button_align", _resolve_export_raw(
            props, "dropdown_button_align", "center",
        )),
        ("max_visible", _safe_int(props.get("dropdown_max_visible", 8), 8)),
        ("border_width", bw),
        ("border_color", _resolve_export_raw(
            props, "dropdown_border_color", "#3c3c3c",
        )),
        ("corner_radius", _safe_int(
            props.get("dropdown_corner_radius", 6), 6,
        )),
    ]
    lines = [
        f"{var_name}._scrollable_dropdown = ScrollableDropdown(",
        f"    {var_name},",
        # Reuse the parent's resolved CTkFont so popup items render
        # with the cascade-selected family, not Tk's default.
        f'    font={var_name}.cget("font"),',
    ]
    for k, v in kwargs:
        lines.append(f"    {k}={_py_literal(v)},")
    lines.append(")")
    return lines


def _geometry_call(
    full_name: str, props: dict, parent_layout: str,
    parent_spacing: int = 0, child_index: int = 0,
    parent_cols: int = 1, parent_rows: int = 1,
) -> str:
    layout = normalise_layout_type(parent_layout)
    side = pack_side_for(layout)
    if side is not None:
        parts: list[str] = [f'side="{side}"']
        stretch = str(props.get("stretch", LAYOUT_DEFAULTS["stretch"]))
        if stretch == "fill":
            cross = "y" if layout == "hbox" else "x"
            parts.append(f'fill="{cross}"')
        elif stretch == "grow":
            parts.append('fill="both"')
            parts.append("expand=True")
        half = parent_spacing // 2
        if half > 0:
            if layout == "hbox":
                parts.append(f"padx={half}")
            else:
                parts.append(f"pady={half}")
        return f"{full_name}.pack({', '.join(parts)})"
    if layout == "grid":
        row = _safe_int(
            props.get("grid_row", LAYOUT_DEFAULTS["grid_row"]), 0,
        )
        col = _safe_int(
            props.get("grid_column", LAYOUT_DEFAULTS["grid_column"]), 0,
        )
        parts = [f"row={row}", f"column={col}"]
        sticky = props.get("grid_sticky", LAYOUT_DEFAULTS["grid_sticky"])
        if sticky:
            parts.append(f'sticky="{sticky}"')
        half = parent_spacing // 2
        if half > 0:
            parts.append(f"padx={half}")
            parts.append(f"pady={half}")
        return f"{full_name}.grid({', '.join(parts)})"
    # place — default
    x = _safe_int(props.get("x"), 0)
    y = _safe_int(props.get("y"), 0)
    return f"{full_name}.place(x={x}, y={y})"


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _font_source(props: dict, family: str | None = None) -> str:
    parts: list[str] = []
    if family:
        # ``repr`` handles quote escaping for unusual family names —
        # e.g. ``"Comic Sans MS"`` round-trips to a Python literal
        # safely without manual escaping.
        parts.append(f"family={family!r}")
    # Descriptors that don't expose ``font_size`` (e.g.
    # CTkScrollableFrame's family-only label font) skip the
    # size / weight / slant block so the generated CTkFont keeps
    # CTk's theme defaults instead of forcing 13/normal/roman.
    if "font_size" in props:
        size = _safe_int(props.get("font_size"), 13)
        weight = (
            '"bold"' if _resolve_export_raw(props, "font_bold") else '"normal"'
        )
        slant = (
            '"italic"' if _resolve_export_raw(props, "font_italic")
            else '"roman"'
        )
        parts.extend([f"size={size}", f"weight={weight}", f"slant={slant}"])
        if _resolve_export_raw(props, "font_underline"):
            parts.append("underline=True")
        if _resolve_export_raw(props, "font_overstrike"):
            parts.append("overstrike=True")
    return f"ctk.CTkFont({', '.join(parts)})"


def _path_for_export(image_path: str) -> str:
    """Convert an in-assets absolute path to ``assets/<rel>`` so the
    exported file references the asset via the sibling ``assets/``
    folder we copy next to it. Out-of-assets paths stay absolute.

    Asset tokens (``asset:images/foo.png``) survive a save/load cycle
    and may also appear after edge cases — handle them up front by
    parsing straight to the ``assets/<rel>`` form, since the token
    already encodes the relative path inside the project's assets.
    """
    if not image_path:
        return ""
    from app.core.assets import is_asset_token, parse_asset_token
    if is_asset_token(image_path):
        return f"assets/{parse_asset_token(image_path)}"
    if not _CURRENT_PROJECT_PATH:
        return str(image_path).replace("\\", "/")
    from app.core.assets import project_assets_dir
    project_assets = project_assets_dir(_CURRENT_PROJECT_PATH)
    if project_assets is None:
        project_assets = Path(_CURRENT_PROJECT_PATH).parent / "assets"
    try:
        rel = Path(image_path).resolve().relative_to(
            project_assets.resolve(),
        )
        return f"assets/{str(rel).replace(chr(92), '/')}"
    except (OSError, ValueError):
        return str(image_path).replace("\\", "/")


def _image_source(props: dict, image_path: str) -> str:
    # ``image`` may itself be var-bound — emit the variable's current
    # value as the static path; _bind_var_to_image_path swaps it live.
    image_path = _resolve_export_raw(props, "image", image_path) or image_path
    if "image_width" in props or "image_height" in props:
        iw = _safe_int(props.get("image_width"), 20)
        ih = _safe_int(props.get("image_height"), 20)
    else:
        iw = _safe_int(props.get("width"), 64)
        ih = _safe_int(props.get("height"), 64)
    # Normalise path separators to forward slashes so the exported file
    # reads consistently regardless of whether the path came from a
    # filedialog (Unix-style on Windows) or was typed with backslashes.
    # Both work in Python on Windows, but mixing both in one file looks
    # sloppy and trips cross-platform readers.
    normalised_path = _path_for_export(image_path)
    path_src = _py_literal(normalised_path)
    # preserve_aspect contain-fits the icon inside (iw, ih) natively
    # (fork >= 5.4.4); image_color / image_color_disabled tint it
    # widget-side — both are emitted as constructor kwargs by the
    # caller, so this builds a plain CTkImage. Emit preserve_aspect
    # only when True (CTkImage's default is False).
    aspect = bool(_resolve_export_raw(props, "preserve_aspect"))
    aspect_src = ", preserve_aspect=True" if aspect else ""
    return (
        f"ctk.CTkImage("
        f"light_image=Image.open({path_src}), "
        f"dark_image=Image.open({path_src}), "
        f"size=({iw}, {ih}){aspect_src})"
    )


from app.io.code_exporter.runtime_helpers import (
    _circular_progress_class_lines,
)


def _safe_int(val, default: int) -> int:
    """Coerce ``val`` to int; fall back to ``default`` on failure.

    Resolves a ``var:<uuid>`` token first — without this, every
    ``_safe_int(props.get(key), default)`` callsite (font size,
    image size, x/y, grid row/col) would silently fall back to the
    default whenever the property was bound to an int/float
    variable, instead of using the variable's current value.
    """
    from app.core.variables import parse_var_token
    var_id = parse_var_token(val)
    if var_id is not None:
        entry = (
            _EXPORT_PROJECT.get_variable(var_id)
            if _EXPORT_PROJECT is not None else None
        )
        if entry is None:
            return default
        val = _entry_default_as_value(entry)
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


