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
    _aspect_corrected_size,
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
# Phase 3 — populated at top of ``_generate_code_inner`` so
# ``_emit_handler_lines`` can skip stale handler bindings whose
# methods no longer exist in the per-window behavior file. Maps
# ``Document.id`` → set of method names defined on the doc's
# behavior class. Populated lazily; missing entry = "couldn't
# scan the file" (treated as "all bindings allowed", matching
# pre-1.8.3 behaviour so projects without behavior files still
# export cleanly).
_BEHAVIOR_METHODS_BY_DOC_ID: dict[str, set[str]] = {}
# Logged for the export caller — list of ``(doc_name, method_name)``
# tuples that the exporter skipped because the method wasn't found
# in the file. Caller can surface these as a warning before
# launching the subprocess.
_MISSING_BEHAVIOR_METHODS: list[tuple[str, str]] = []
_GLOBAL_VAR_ATTR: dict = {}
_VAR_ID_TO_ATTR: dict = {}
# v1.10.8 — doc.id → class name emitted in this generate_code run.
# Populated at the top of ``generate_code`` once class names are
# assigned, consumed by ``_emit_object_reference_lines`` so global
# Window/Dialog refs resolve to the right class symbol. Reset
# alongside the variable maps.
_DOC_ID_TO_CLASS: dict = {}
# Var-name fallbacks the exporter applied during this run because the
# user-set Properties-panel "Name" was empty / invalid / a duplicate.
# Tuples are ``(doc_name, intended, fallback, reason)``; reset at the
# start of each ``generate_code`` call. Surfaced via
# ``get_var_name_fallbacks()`` so launchers (F5 preview, export
# dialog) can show the user which names were silently rewritten.
_VAR_NAME_FALLBACKS: list[tuple[str, str, str, str]] = []
# v1.10.9 — mismatches between GUI Object References and the per-doc
# behavior file's ``<name>: ref[<Type>]`` annotations. Auto-stub paths
# (panel.py ``_maybe_write_ref_annotation`` + variables_window
# ``_maybe_rename_annotation``) cover the happy path; this scan
# catches the case where the user edited the .py manually and drifted
# from the GUI names — verbatim wiring means ``self.<ref_name>`` then
# stays unbound until the first widget interaction raises
# ``AttributeError``. Tuples are ``(doc_name, kind, ref_name, detail)``;
# ``kind`` is ``"missing_annotation"`` / ``"orphan_annotation"`` /
# ``"type_mismatch"``. Reset by ``_scan_ref_annotations_for_export``
# at the top of ``generate_code``. Surfaced via
# ``get_ref_annotation_issues()`` for F5 preview + export dialog.
_REF_ANNOTATION_ISSUES: list[tuple[str, str, str, str]] = []
# Per-doc memoisation for ``_resolve_var_names`` so the resolver
# runs once per ``generate_code`` call per doc — keeps the
# ``_emit_subtree`` walk and the ``_build_id_to_var_name`` Phase 3
# replay in lockstep without recomputing (and without double-
# recording warnings).
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
    "_behavior",
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
    """True when any widget has ``image`` / ``image_width`` /
    ``image_height`` / ``preserve_aspect`` bound to a variable AND
    has an image set. The single helper block covers all four
    image-rebuild bindings (they share ``_rebuild_image_for_widget``).
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
    _AUTO_TRACE_WIDGET_HELPER,
    _AUTO_TRACE_TEXTBOX_HELPER,
    _AUTO_TRACE_FONT_HELPER,
    _FONT_COMPOSITE_TO_ATTR,
    _IMAGE_REBUILD_KEYS,
    _PLACE_COORD_KEYS,
    _AUTO_TRACE_STATE_HELPER,
    _STATE_COMPOSITE_KEYS,
    _AUTO_TRACE_LABEL_ENABLED_HELPER,
    _AUTO_TRACE_FONT_WRAP_HELPER,
    _AUTO_TRACE_PLACE_COORD_HELPER,
    _AUTO_TRACE_IMAGE_REBUILD_HELPER,
    _AUTO_TRACE_FONT_AUTOFIT_HELPER,
    _PACK_BALANCE_HELPER,
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
    # Phase 3 — if any image-related composite has a var binding,
    # emit a one-time ``_maker_image_state`` dict init right at the
    # top so the per-key rebuilders share one state object. Static
    # values (the ones NOT bound) come from the widget's properties
    # at construction time.
    props_for_state = node.properties or {}
    has_image_rebuild_bind = any(
        key in _IMAGE_REBUILD_KEYS
        and _is_non_textvariable_var_binding(
            node.widget_type, key, props_for_state.get(key),
        )
        for key in _IMAGE_REBUILD_KEYS
    )
    # Also init the state dict when ``label_enabled`` /
    # ``button_enabled`` is bound and the widget has an image — so the
    # enabled rebuilder can flip ``state["enabled"]`` and pick between
    # ``color`` and ``color_disabled``. Without this, an enabled-only
    # binding wouldn't trigger the state-dict init and the image
    # rebuild path stays inactive.
    has_enabled_with_image = (
        props_for_state.get("image")
        and any(
            _is_non_textvariable_var_binding(
                node.widget_type, key, props_for_state.get(key),
            )
            for key in ("label_enabled", "button_enabled")
        )
    )
    if (has_image_rebuild_bind or has_enabled_with_image) and props_for_state.get("image"):
        try:
            init_w = int(
                _resolve_export_raw(props_for_state, "image_width", 20)
                or 20
            )
            init_h = int(
                _resolve_export_raw(props_for_state, "image_height", 20)
                or 20
            )
        except (TypeError, ValueError):
            init_w, init_h = 20, 20
        init_path = _resolve_export_raw(
            props_for_state, "image", ""
        ) or ""
        init_color = _resolve_export_raw(
            props_for_state, "image_color", None,
        )
        init_color_disabled = _resolve_export_raw(
            props_for_state, "image_color_disabled", None,
        )
        init_aspect = bool(
            _resolve_export_raw(
                props_for_state, "preserve_aspect", False,
            )
        )
        # Initial enabled state: prefer label_enabled if widget has it,
        # else button_enabled, else True. Mirrors the existing
        # ``_image_source`` color-pick logic.
        if "label_enabled" in props_for_state:
            init_enabled = bool(
                _resolve_export_raw(
                    props_for_state, "label_enabled", True,
                )
            )
        elif "button_enabled" in props_for_state:
            init_enabled = bool(
                _resolve_export_raw(
                    props_for_state, "button_enabled", True,
                )
            )
        else:
            init_enabled = True
        out.append(
            f"{full_name}._maker_image_state = "
            f"{{'path': {_py_literal(_path_for_export(init_path))}, "
            f"'width': {init_w}, 'height': {init_h}, "
            f"'color': {_py_literal(init_color)}, "
            f"'color_disabled': {_py_literal(init_color_disabled)}, "
            f"'enabled': {init_enabled!r}, "
            f"'aspect': {init_aspect!r}}}"
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
                f"_bind_var_to_textbox({var_attr}, {full_name})",
            )
            continue
        # Font composites route through their dedicated rebuilder —
        # CTk's configure() doesn't accept these keys, but they live-
        # update by rebuilding the widget's CTkFont in place.
        font_attr = _FONT_COMPOSITE_TO_ATTR.get(key)
        if font_attr is not None:
            out.append(
                f'_bind_var_to_font({var_attr}, {full_name}, "{font_attr}")',
            )
            continue
        # ``button_enabled`` — bool var maps to CTk's ``state`` enum.
        # Routed through the state helper because the var holds
        # True/False, not "normal"/"disabled".
        if key in _STATE_COMPOSITE_KEYS:
            out.append(
                f"_bind_var_to_state({var_attr}, {full_name})",
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
                f"_bind_var_to_label_enabled({var_attr}, {full_name}, "
                f"{_py_literal(on_val)}, {_py_literal(off_val)})",
            )
            continue
        # ``font_wrap`` (CTkLabel only) — bool var drives wraplength
        # derivation from the widget's current width.
        if key == "font_wrap" and node.widget_type == "CTkLabel":
            out.append(
                f"_bind_var_to_font_wrap({var_attr}, {full_name})",
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
                f"_bind_var_to_font_autofit({var_attr}, {full_name}, "
                f"{size_off_int})",
            )
            continue
        # ``x`` / ``y`` — number var drives place_configure on that axis.
        if key in _PLACE_COORD_KEYS:
            out.append(
                f'_bind_var_to_place_coord({var_attr}, {full_name}, "{key}")',
            )
            continue
        # Image rebuild family (path / size / preserve_aspect / color
        # / color_disabled) all share a single ``_maker_image_state``
        # dict on the widget. The dict is initialised once per widget
        # at the top of this function (the prelude above) when any of
        # these keys has a var binding; here we emit only the per-key
        # bind call.
        if key in _IMAGE_REBUILD_KEYS:
            props = node.properties or {}
            if not props.get("image"):
                # No image set — image rebuilds have nothing to load.
                continue
            if key == "image":
                out.append(
                    f"_bind_var_to_image_path({var_attr}, {full_name})",
                )
            elif key == "image_width":
                out.append(
                    f'_bind_var_to_image_size({var_attr}, {full_name}, "width")',
                )
            elif key == "image_height":
                out.append(
                    f'_bind_var_to_image_size({var_attr}, {full_name}, "height")',
                )
            elif key == "preserve_aspect":
                out.append(
                    f"_bind_var_to_preserve_aspect({var_attr}, {full_name})",
                )
            elif key == "image_color":
                out.append(
                    f'_bind_var_to_image_color_state({var_attr}, {full_name}, "color")',
                )
            elif key == "image_color_disabled":
                out.append(
                    f'_bind_var_to_image_color_state({var_attr}, {full_name}, "color_disabled")',
                )
            continue
        if allowed is not None and key not in allowed:
            continue
        out.append(
            f'_bind_var_to_widget({var_attr}, {full_name}, "{key}")',
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
                    # asset_filter is built from widget property
                    # tokens (image / font references) and doesn't
                    # see Phase 2 behavior files. Without the copy
                    # below, ``from assets.scripts.<page>.<window>
                    # import <Class>Page`` lines emitted by the
                    # exporter target a folder that doesn't exist
                    # next to the export → ModuleNotFoundError on
                    # first run. Walk every doc whose code was
                    # emitted and copy its behavior subtree
                    # alongside ``_runtime.py`` + the package
                    # ``__init__.py`` chain.
                    _copy_behavior_assets_for_filter(
                        project,
                        single_document_id,
                        src_assets,
                        out.parent / "assets",
                    )
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
    global _GLOBAL_VAR_ATTR, _VAR_ID_TO_ATTR, _DOC_ID_TO_CLASS
    global _VAR_NAME_FALLBACKS, _NAME_MAP_CACHE
    _prev = (
        _INCLUDE_DESCRIPTIONS_DEFAULT, _EXPORT_PROJECT,
        _GLOBAL_VAR_ATTR, _VAR_ID_TO_ATTR, _DOC_ID_TO_CLASS,
    )
    _INCLUDE_DESCRIPTIONS_DEFAULT = include_descriptions
    _EXPORT_PROJECT = project
    _GLOBAL_VAR_ATTR = _build_global_var_attrs(project)
    # Per-class map is rebuilt inside ``_emit_class``; start empty.
    _VAR_ID_TO_ATTR = {}
    # doc.id → class name; populated inside ``_generate_code_inner``
    # once class names are picked. Empty here so single-doc / no-doc
    # paths skip global-ref resolution cleanly.
    _DOC_ID_TO_CLASS = {}
    # Reset the var-name fallback log + DFS-walk memoisation so this
    # export run starts from a clean slate. The log survives past
    # ``generate_code`` so launchers can read it via
    # ``get_var_name_fallbacks()`` after the export — same lifecycle
    # as ``_MISSING_BEHAVIOR_METHODS``.
    _VAR_NAME_FALLBACKS = []
    _NAME_MAP_CACHE = {}
    # Pre-scan every doc's behavior file so handler bindings whose
    # methods got removed externally (user edited the .py manually,
    # AST scanner failed, etc.) are skipped instead of emitted as
    # ``self._behavior.<missing>`` references that crash the preview
    # at __init__ time.
    _scan_behavior_methods_for_export(project)
    _scan_ref_annotations_for_export(project)
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
            _DOC_ID_TO_CLASS,
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
    needs_tint = any(
        w.properties.get("image")
        and (
            w.properties.get("image_color")
            or w.properties.get("image_color_disabled")
        )
        for w in scoped_widgets
    )
    needs_icon_state = any(
        w.properties.get("image")
        and w.properties.get("image_color_disabled")
        and "button_enabled" in w.properties
        for w in scoped_widgets
    )
    needs_auto_hover_text = any(
        w.properties.get("text_hover") for w in scoped_widgets
    )
    # Right-click + non-Latin Ctrl router for every text-editable
    # widget. Triggered when the project includes any Entry, Textbox,
    # or ComboBox — those are the CTk widgets backed by tk.Entry /
    # tk.Text under the hood.
    needs_text_clipboard = any(
        w.widget_type in ("CTkEntry", "CTkTextbox", "CTkComboBox")
        for w in scoped_widgets
    )
    # ComboBox + OptionMenu wear our ScrollableDropdown helper for a
    # scrollable popup that matches the parent's pixel width.
    needs_scrollable_dropdown = any(
        w.widget_type in ("CTkComboBox", "CTkOptionMenu")
        for w in scoped_widgets
    )
    # CTkCheckBox / CTkRadioButton / CTkSwitch grid the box + label
    # in a hardcoded layout. ``text_position != "right"`` triggers
    # the helper that re-grids them so the label sits anywhere.
    # CTkCheckBox / CTkRadioButton (and later Switch) all share the
    # same internal _canvas + _text_label grid layout — one helper
    # handles the re-positioning for every one of them.
    needs_text_alignment = any(
        w.widget_type in ("CTkCheckBox", "CTkRadioButton", "CTkSwitch")
        and (
            (_resolve_export_raw(w.properties, "text_position", "right")
             or "right") != "right"
            or _safe_int(
                w.properties.get("text_spacing", 6) or 6, 6,
            ) != 6
        )
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
    needs_circle_button = any(
        w.widget_type == "CTkButton" for w in scoped_widgets
    )
    # Inlines CircleLabel for every project that contains a CTkLabel.
    # Future improvement: tighten this gate. CircleLabel carries two
    # fixes — a corner-radius padx fix (only observable when
    # ``2*corner_radius >= width``) and a unified event router (only
    # observable when the user calls ``bind()`` on the label). When a
    # label is used as a passive visual element with neither
    # condition met, ``ctk.CTkLabel(...)`` could be emitted directly
    # to keep exported scripts smaller. Detecting "no events" needs
    # static analysis of the user's behavior file, which today is a
    # 1-handler bridge — non-trivial; deferred.
    needs_circle_label = any(
        w.widget_type == "CTkLabel" for w in scoped_widgets
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
    lines.append("")

    if needs_font_register:
        lines.extend(_font_register_helper_lines())
        lines.append("")

    if needs_tint:
        lines.extend(_tint_helper_lines())
        lines.append("")

    # Phase 3 — auto-trace helpers for var bindings that don't map
    # to Tk's native ``textvariable=``/``variable=`` (e.g. CTkButton.
    # text, CTkButton.fg_color, CTkTextbox content). One helper per
    # update strategy, emitted only when the project actually needs
    # it so pure Phase 1.5 projects stay lean.
    if needs_auto_trace_helper:
        lines.extend(_AUTO_TRACE_WIDGET_HELPER.splitlines())
        lines.append("")
    if needs_auto_trace_textbox:
        lines.extend(_AUTO_TRACE_TEXTBOX_HELPER.splitlines())
        lines.append("")
    if needs_auto_trace_font:
        lines.extend(_AUTO_TRACE_FONT_HELPER.splitlines())
        lines.append("")
    if needs_auto_trace_state:
        lines.extend(_AUTO_TRACE_STATE_HELPER.splitlines())
        lines.append("")
    if needs_auto_trace_label_enabled:
        lines.extend(_AUTO_TRACE_LABEL_ENABLED_HELPER.splitlines())
        lines.append("")
    if needs_auto_trace_font_wrap:
        lines.extend(_AUTO_TRACE_FONT_WRAP_HELPER.splitlines())
        lines.append("")
    if needs_auto_trace_font_autofit:
        lines.extend(_AUTO_TRACE_FONT_AUTOFIT_HELPER.splitlines())
        lines.append("")
    if needs_auto_trace_place_coord:
        lines.extend(_AUTO_TRACE_PLACE_COORD_HELPER.splitlines())
        lines.append("")
    if needs_auto_trace_image_rebuild:
        lines.extend(_AUTO_TRACE_IMAGE_REBUILD_HELPER.splitlines())
        lines.append("")
    if needs_pack_balance:
        lines.extend(_PACK_BALANCE_HELPER.splitlines())
        lines.append("")

    if needs_icon_state:
        lines.extend(_icon_state_helper_lines())
        lines.append("")

    if needs_circular_progress:
        lines.extend(_circular_progress_class_lines())
        lines.append("")

    if needs_circle_button:
        lines.extend(_circle_button_class_lines())
        lines.append("")

    if needs_circle_label:
        lines.extend(_circle_label_class_lines())
        lines.append("")

    if needs_auto_hover_text:
        lines.extend(_auto_hover_text_helper_lines())
        lines.append("")

    if needs_text_clipboard:
        lines.extend(_text_clipboard_helper_lines())
        lines.append("")

    if needs_text_alignment:
        lines.extend(_align_text_label_helper_lines())
        lines.append("")

    used_class_names: set[str] = set()
    class_names: list[tuple[Document, str]] = []
    for index, doc in enumerate(docs_to_emit):
        cls_name = _class_name_for(doc, index, used_class_names)
        used_class_names.add(cls_name)
        class_names.append((doc, cls_name))
    # v1.10.8 — populate the global doc.id → class-name map so
    # _emit_object_reference_lines can resolve global Window/Dialog
    # refs to the right symbol. The map is reset at the top of
    # generate_code so we never carry state across runs.
    global _DOC_ID_TO_CLASS
    _DOC_ID_TO_CLASS = {doc.id: cls for doc, cls in class_names}

    # Phase 2 — emit ``from assets.scripts.<page>.<window> import
    # <WindowName>Page`` for every Document that actually binds at
    # least one handler. Skipping zero-handler docs keeps generated
    # code tidy + avoids ImportError on projects whose behavior file
    # was never materialised (e.g. user copied a .ctkproj without
    # the ``assets/scripts/`` folder). The behavior class instance
    # lands on ``self._behavior`` inside each window's __init__ —
    # see ``_emit_class_body``.
    behavior_imports: list[tuple[Document, str]] = []
    for doc, _cls in class_names:
        if _doc_needs_behavior(doc):
            behavior_imports.append((doc, _behavior_class_for_doc(doc)))
    if behavior_imports:
        from app.core.script_paths import (
            behavior_file_stem, slugify_window_name,
        )
        page_slug = behavior_file_stem(project.path)
        for doc, beh_cls in behavior_imports:
            window_slug = slugify_window_name(doc.name)
            lines.append(
                f"from assets.scripts.{page_slug}.{window_slug} "
                f"import {beh_cls}",
            )
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
    lines.append(f"{INDENT}import sys")
    lines.append(f'{INDENT}ctk.set_appearance_mode("{DEFAULT_APPEARANCE_MODE}")')
    # CTk ships only Roboto-Regular + Roboto-Medium (no Bold face), so
    # CTkFont(weight="bold") silently falls back to synthetic bold —
    # barely visible at large sizes. Mirror the editor's main.py patch
    # so the exported app uses Segoe UI on Windows where a real bold
    # face exists.
    lines.append(f'{INDENT}if sys.platform == "win32":')
    lines.append(
        f'{INDENT}{INDENT}'
        'ctk.ThemeManager.theme["CTkFont"]["family"] = "Segoe UI"'
    )

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
            lines.append(f"{INDENT}_register_project_fonts(app)")
        # Bypassing the main class also skips its global-var
        # declarations, so the previewed Toplevel's
        # ``self.master.var_X`` lookup would fail. Mirror the
        # declarations onto the bare host before instantiation.
        lines.extend(
            _preview_globals_on_host_lines(_EXPORT_PROJECT, "app", INDENT),
        )
        lines.append(f"{INDENT}{var} = {preview_cls}(app)")
        if needs_text_clipboard:
            lines.append(f"{INDENT}_setup_text_clipboard(app)")
        if inject_preview_screenshot:
            lines.extend(_preview_screenshot_lines(target=var))
        lines.append(f"{INDENT}app.wait_window({var})")
    else:
        first_doc, first_class = class_names[0]
        lines.append(f"{INDENT}app = {first_class}()")
        if needs_text_clipboard:
            lines.append(f"{INDENT}_setup_text_clipboard(app)")
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
def _scan_behavior_methods_for_export(project: Project) -> None:
    """Populate ``_BEHAVIOR_METHODS_BY_DOC_ID`` + reset the missing-
    methods log. Per-doc AST parse against ``parse_handler_methods``
    so ``_emit_handler_lines`` can answer "does method X exist on
    the behavior class" in O(1).

    Robust to unsaved projects (no path) and missing files (skip the
    doc — its handlers fall through to "no filter" so the
    pre-Phase-3 behaviour holds when files don't exist yet).
    """
    global _BEHAVIOR_METHODS_BY_DOC_ID, _MISSING_BEHAVIOR_METHODS
    _BEHAVIOR_METHODS_BY_DOC_ID = {}
    _MISSING_BEHAVIOR_METHODS = []
    project_path = getattr(project, "path", None)
    if not project_path:
        return
    from app.core.script_paths import (
        behavior_class_name, behavior_file_path,
    )
    from app.io.scripts import parse_handler_methods
    for doc in project.documents:
        file_path = behavior_file_path(project_path, doc)
        if file_path is None or not file_path.exists():
            continue
        methods = parse_handler_methods(
            file_path, behavior_class_name(doc),
        )
        _BEHAVIOR_METHODS_BY_DOC_ID[doc.id] = set(methods)


def _filter_handlers_to_existing_methods(
    node: WidgetNode, methods: list[str],
) -> list[str]:
    """Drop method names that the per-doc scanner couldn't find on
    the behavior class. Each drop appends to
    ``_MISSING_BEHAVIOR_METHODS`` so the caller can surface a "your
    behavior file is out of sync" warning to the user.

    No-op when no scan data exists for the doc — happens for
    unsaved projects or docs whose .py never materialised; in that
    case we keep the pre-1.8.3 "trust the model" behaviour so we
    don't break exports that worked before.
    """
    if _EXPORT_PROJECT is None:
        return methods
    doc = _EXPORT_PROJECT.find_document_for_widget(node.id)
    if doc is None:
        return methods
    available = _BEHAVIOR_METHODS_BY_DOC_ID.get(doc.id)
    if available is None:
        return methods
    kept: list[str] = []
    for m in methods:
        if m in available:
            kept.append(m)
        else:
            _MISSING_BEHAVIOR_METHODS.append((doc.name, m))
    return kept


def get_missing_behavior_methods() -> list[tuple[str, str]]:
    """Return the list of ``(doc_name, method_name)`` pairs the most
    recent export had to skip because the methods didn't exist in
    the behavior file. Read by the preview launchers to show a
    pre-spawn warning so the user knows why their button no longer
    fires what they bound.
    """
    return list(_MISSING_BEHAVIOR_METHODS)


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


def _scan_ref_annotations_for_export(project: Project) -> None:
    """Diff every doc's Object References against its behavior file's
    ``<name>: ref[<Type>]`` annotations. Populates
    ``_REF_ANNOTATION_ISSUES`` with one tuple per mismatch so launchers
    can warn the user before runtime would otherwise raise
    ``AttributeError`` on the first widget interaction.

    Three issue kinds:

    - ``missing_annotation`` — a local Object Reference declared in
      the Properties panel has no matching ``<name>: ref[<Type>]``
      line in the behavior class. The auto-stub (panel.py
      ``_maybe_write_ref_annotation``) usually keeps these in sync;
      reaching here means the user edited the .py manually and
      removed / renamed the annotation.
    - ``orphan_annotation`` — annotation present in the .py with no
      matching ref in either ``doc.local_object_references`` or the
      project-level globals. ``self.<name>`` stays unbound at runtime.
    - ``type_mismatch`` — both sides exist but disagree on the widget
      type (e.g., annotation says ``ref[CTkButton]`` but the GUI ref
      targets a ``CTkLabel``).

    Globals are only consulted to suppress ``orphan_annotation``
    warnings — they don't need a matching annotation on every doc
    that has access to them, so we never flag them as
    ``missing_annotation``.

    Robust to unsaved projects (skip — annotations live next to the
    saved project) and missing files (skip the doc — the annotation
    will be created next time the user opens the file).
    """
    global _REF_ANNOTATION_ISSUES
    _REF_ANNOTATION_ISSUES = []
    project_path = getattr(project, "path", None)
    if not project_path:
        return
    from app.core.script_paths import (
        behavior_class_name, behavior_file_path,
    )
    from app.io.scripts import parse_object_reference_fields
    global_names = {
        entry.name for entry in (project.object_references or [])
        if entry.name
    }
    for doc in project.documents:
        file_path = behavior_file_path(project_path, doc)
        if file_path is None or not file_path.exists():
            continue
        annotated = {
            field.name: field.type_name
            for field in parse_object_reference_fields(
                file_path, behavior_class_name(doc),
            )
        }
        locals_map = {
            entry.name: entry.target_type
            for entry in (doc.local_object_references or [])
            if entry.name
        }
        # Locals: warn on missing annotation + type mismatch. Verbatim
        # wiring means ``self.<entry.name>`` won't resolve unless the
        # behavior file declares the same name.
        for name, target_type in locals_map.items():
            ann_type = annotated.get(name)
            if ann_type is None:
                _REF_ANNOTATION_ISSUES.append(
                    (doc.name, "missing_annotation", name, target_type),
                )
            elif target_type and ann_type and ann_type != target_type:
                _REF_ANNOTATION_ISSUES.append(
                    (
                        doc.name, "type_mismatch", name,
                        f"annotation=ref[{ann_type}], "
                        f"reference target={target_type}",
                    ),
                )
        # Orphan annotations — the user typed a ref[...] line whose
        # name doesn't match any local OR global. Globals are checked
        # too so a shared ``main_window: ref[Window]`` annotation
        # doesn't fire a false positive.
        for name, ann_type in annotated.items():
            if name in locals_map or name in global_names:
                continue
            _REF_ANNOTATION_ISSUES.append(
                (doc.name, "orphan_annotation", name, ann_type),
            )


def get_ref_annotation_issues() -> list[tuple[str, str, str, str]]:
    """Return ``(doc_name, kind, ref_name, detail)`` rows for every
    mismatch the most recent export found between GUI Object
    References and the per-doc behavior file's ``ref[<Type>]``
    annotations. ``kind`` is one of ``"missing_annotation"`` /
    ``"orphan_annotation"`` / ``"type_mismatch"`` — see
    ``_scan_ref_annotations_for_export`` for the precise semantics.
    Empty list when every annotation lines up. Read by F5 preview /
    export dialog launchers to show a pre-spawn notice — without it
    the user only learns about the mismatch when the first widget
    interaction raises ``AttributeError``.
    """
    return list(_REF_ANNOTATION_ISSUES)


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

    Single method → bare reference (``self._behavior.foo``); multiple
    methods on the same event → lambda chain so every method fires
    in order. Bind-style events use ``add="+"`` so each method gets
    its own bind call without clobbering the previous one.

    Empty ``handlers`` → returns ``(None, [])`` and no plumbing is
    emitted at all.
    """
    if not node.handlers:
        return None, []
    from app.widgets.event_registry import event_by_key
    command_kwarg: tuple[str, str] | None = None
    post_lines: list[str] = []
    for key in node.handlers:
        methods = [m for m in node.handlers.get(key, []) if m]
        if not methods:
            continue
        # Phase 3 — drop handler entries whose methods don't exist
        # in the behavior file. Pre-1.8.3 these emitted as
        # ``self._behavior.<missing>`` and crashed the preview at
        # widget construction with AttributeError. Now the
        # exporter filters them; the binding silently disappears
        # for this run and the caller can warn the user via
        # ``get_missing_behavior_methods()``.
        methods = _filter_handlers_to_existing_methods(node, methods)
        if not methods:
            continue
        entry = event_by_key(node.widget_type, key)
        if entry is None:
            # Stale binding — registry doesn't list this event for the
            # widget any more. Skip silently rather than emit broken
            # code; the Properties panel surfaces the dangling row.
            continue
        if entry.wiring_kind == "command":
            command_kwarg = ("command", _format_method_chain(methods))
        elif entry.wiring_kind == "bind":
            seq = key.split(":", 1)[1] if ":" in key else key
            for method in methods:
                post_lines.append(
                    f'{full_name}.bind('
                    f'"{seq}", self._behavior.{method}, add="+")',
                )
    return command_kwarg, post_lines


def _format_method_chain(methods: list[str]) -> str:
    """Render an ordered list of behavior methods as the source for
    a ``command=`` kwarg. One method becomes a bare reference;
    several get wrapped in a lambda that calls each in turn so the
    fan-out is visible at the call site (no hidden registration).
    """
    if len(methods) == 1:
        return f"self._behavior.{methods[0]}"
    calls = ", ".join(f"self._behavior.{m}()" for m in methods)
    return f"lambda: ({calls})"


def _doc_has_handlers(doc: Document) -> bool:
    """True when at least one widget under ``doc`` has a non-empty
    handler list. Used to gate the per-window behavior import + the
    ``self._behavior = …`` lines in __init__ so docs without any
    bound events emit no Phase 2 plumbing.
    """
    for root in doc.root_widgets:
        if _node_has_handlers(root):
            return True
    return False


def _node_has_handlers(node: WidgetNode) -> bool:
    if any(node.handlers.get(k) for k in node.handlers):
        return True
    for child in node.children:
        if _node_has_handlers(child):
            return True
    return False


def _doc_needs_behavior(doc: Document) -> bool:
    """v1.10.8 — broader behavior-class gate. Returns True when the
    doc has bound handlers OR object-reference targets to wire (any
    target_id non-empty). Reference-only docs (declared refs, picked
    widgets, no event handlers) still require the
    ``self._behavior = X()`` instance so setup() can run + the
    reference assignments have a target.
    """
    if _doc_has_handlers(doc):
        return True
    if any(
        e.target_id for e in (doc.local_object_references or [])
    ):
        return True
    return False


def _copy_behavior_assets_for_filter(
    project,
    single_document_id: str | None,
    src_assets: Path,
    dst_assets: Path,
) -> None:
    """Bridge for the ``asset_filter`` export branch — Phase 2 / 3
    behavior files don't show up in ``collect_used_assets`` (which
    only walks widget property tokens for images + fonts), so an
    export with the filter on emits ``from assets.scripts.<page>.
    <window> import …`` against an ``assets/`` folder that's
    missing the entire scripts subtree. Result: ModuleNotFoundError
    at first run.

    The fix copies, for every emitted doc that needs a behavior
    class:

    - ``assets/scripts/__init__.py`` (top-level package marker)
    - ``assets/scripts/_runtime.py`` (Phase 3 ``ref`` marker)
    - ``assets/scripts/<page_slug>/`` recursively (sibling helper
      modules the user wrote — ``qr_encoder.py`` next to
      ``qr_live.py`` — ride along automatically because we copy
      the whole folder, not individual files)

    No-op when the project isn't saved, when ``scripts_root`` can't
    be located, or when no emitted doc actually needs behavior.
    Errors during individual copies are swallowed so a partial
    failure doesn't abort the rest of the export.
    """
    if not project.path:
        return
    from app.core.script_paths import page_scripts_dir, scripts_root
    if single_document_id:
        target = project.get_document(single_document_id)
        docs_to_check = [target] if target is not None else []
    else:
        docs_to_check = list(project.documents)
    if not any(d is not None and _doc_needs_behavior(d) for d in docs_to_check):
        return
    s_root = scripts_root(project.path)
    if s_root is None or not s_root.exists():
        return
    src_resolved = src_assets.resolve()

    # Skip ``__pycache__`` so the export bundle doesn't ship stale
    # bytecode that the user's Python version may reject. Match the
    # legacy whole-tree copytree fallback's silent ignore behaviour.
    _ignore_pyc = shutil.ignore_patterns("__pycache__", "*.pyc")

    def _copy_into_dst(src: Path) -> None:
        try:
            rel = src.resolve().relative_to(src_resolved)
        except (OSError, ValueError):
            return
        dst = dst_assets / rel
        try:
            if src.is_dir():
                shutil.copytree(
                    src, dst,
                    dirs_exist_ok=True,
                    ignore=_ignore_pyc,
                )
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        except OSError:
            pass

    for marker in (s_root / "__init__.py", s_root / "_runtime.py"):
        if marker.exists():
            _copy_into_dst(marker)
    page_dir = page_scripts_dir(project.path)
    if page_dir is not None and page_dir.is_dir():
        _copy_into_dst(page_dir)


def _resolve_var_names(doc: Document) -> dict[str, str]:
    """Walk a doc's widget tree DFS and produce the canonical
    ``{widget_id: var_name}`` map for every node. Single source of
    truth used by both ``_emit_subtree`` (live emission) and
    ``_build_id_to_var_name`` (Object Reference replay) so the two
    walks can never drift.

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


def _build_id_to_var_name(doc: Document) -> dict[str, str]:
    """Object Reference replay helper — alias of ``_resolve_var_names``
    so callers reading post-build assignments line up with whatever
    ``_emit_subtree`` actually emitted. Memoisation in
    ``_NAME_MAP_CACHE`` keeps this from re-walking the tree or
    duplicating user warnings.
    """
    return _resolve_var_names(doc)


def _emit_object_reference_lines(
    doc: Document,
    id_to_var: dict[str, str],
    instance_prefix: str,
) -> list[str]:
    """v1.10.8 — produce the ``self._behavior.<name> = <expr>`` lines
    that wire object-reference slots after ``_build_ui()`` returns.
    Reads from ``doc.local_object_references`` (local refs) and the
    project-level ``object_references`` (globals — Window/Dialog
    pointers). Skips entries whose target is missing in this export.

    Indentation is two levels (``__init__`` body inside ``class``);
    the caller appends them right after the ``self._build_ui()``
    call.
    """
    lines: list[str] = []
    for entry in doc.local_object_references or []:
        if not entry.target_id:
            continue
        var_name = id_to_var.get(entry.target_id)
        if not var_name:
            continue
        lines.append(
            f"{INDENT}{INDENT}self._behavior.{entry.name} = "
            f"{instance_prefix}{var_name}",
        )
    # Globals — Window/Dialog refs resolve to the class symbol the
    # current export emitted. Same-file class references mean no
    # imports are needed; missing target_id (unbound slot) or a
    # target that wasn't in this export (single-doc mode) are
    # silently skipped so the generated code stays runnable.
    project = _EXPORT_PROJECT
    if project is not None:
        for entry in project.object_references or []:
            if not entry.target_id:
                continue
            cls = _DOC_ID_TO_CLASS.get(entry.target_id)
            if not cls:
                continue
            lines.append(
                f"{INDENT}{INDENT}self._behavior.{entry.name} = {cls}",
            )
    return lines


def _behavior_class_for_doc(doc: Document) -> str:
    """Per-window behavior class name — ``<WindowSlug>Page``.
    Centralised here so the exporter, F5 preview, and the Properties
    panel agree on the symbol that lives in the user's .py file.
    """
    from app.core.script_paths import behavior_class_name
    return behavior_class_name(doc)


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
                f"{INDENT}{INDENT}_register_project_fonts(self)",
            )

    # Phase 2 — instantiate the per-window behavior class. Done
    # BEFORE _build_ui so widget constructor kwargs like
    # ``command=self._behavior.on_click`` can resolve. The actual
    # ``setup(self)`` call moves AFTER build + Phase 3 field
    # assignments so user code can lean on widgets + fields being
    # available — see the post-build block further down.
    if _doc_needs_behavior(doc):
        beh_cls = _behavior_class_for_doc(doc)
        lines.append(
            f"{INDENT}{INDENT}self._behavior = {beh_cls}()",
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
    lines.append(f"{INDENT}{INDENT}self._build_ui()")
    # Object Reference assignments must run AFTER _build_ui() since
    # they reference widgets created inside it. Per-doc id-to-var
    # map mirrors the naming the subtree walk emits, so the right-
    # hand sides line up with the actual ``self.<widget_var>``
    # attributes set during the build.
    if _doc_needs_behavior(doc) and (doc.local_object_references):
        id_to_var = _build_id_to_var_name(doc)
        field_lines = _emit_object_reference_lines(doc, id_to_var, "self.")
        lines.extend(field_lines)
    # ``setup()`` runs AFTER _build_ui + Object Reference assignments
    # so user code can reference both ``self.<widget>`` attributes
    # and the bound ``self._behavior.<field>`` slots without worrying
    # about ordering. Widget command kwargs captured
    # ``self._behavior.<method>`` during _build_ui; those bindings
    # are stable references whose call sites fire later.
    if _doc_needs_behavior(doc):
        lines.append(
            f"{INDENT}{INDENT}self._behavior.setup(self)",
        )
    lines.append("")
    lines.append(f"{INDENT}def _build_ui(self):")

    # Pre-compute every widget's var name in DFS order. Threads the
    # user-set Properties-panel "Name" through to the emitted
    # ``self.<var> = ctk.<Type>(...)`` line so behavior files can
    # reference widgets as ``self.window.<user_name>`` instead of
    # the legacy ``<type>_<N>`` shape. Same map fuels the Object
    # Reference replay above (memoised in ``_NAME_MAP_CACHE``).
    id_to_var = _resolve_var_names(doc)
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
                f"_ctkmaker_balance_pack(self, {_balance_axis!r}))",
            )
    for line in body_lines:
        lines.append(f"{INDENT}{INDENT}{line}" if line else "")
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
            f"_ctkmaker_balance_pack(_c, {_balance_axis!r})"
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
    #   2. descriptor.type_name — custom subclasses like ``CircleButton``
    #      (a CTkButton subclass set as ctk_class_name="CircleButton")
    #      miss the customtkinter module on lookup #1; falling back to
    #      type_name="CTkButton" pulls the parent's signature, which is
    #      the right reference for the skip gate.
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

    # CTkTabview: map node-only `tab_anchor` ("left"/"center"/"right")
    # onto CTk's `anchor` kwarg ("w"/"center"/"e"). Stored separately
    # from the generic 3x3 `anchor` picker used by Button / Label so
    # Tabview's simpler horizontal-only control gets its own dropdown.
    if node.widget_type == "CTkTabview":
        _tabview_anchor_map = {
            "left": "w", "center": "center", "right": "e",
        }
        ta = _tabview_anchor_map.get(
            props.get("tab_anchor", "center"), "center",
        )
        kwargs.append(("anchor", f'"{ta}"'))

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
    pre_lines: list[str] = []
    post_image_lines: list[str] = []
    # When a button has both an icon AND a disabled tint, emit TWO
    # CTkImages + a one-shot _wire_icon_state(...) call so any future
    # configure(state=...) auto-swaps the image. CTk's native state
    # change doesn't touch the image, so without the wire a disabled
    # tint variant would never appear at runtime.
    has_disabled_tint = bool(
        image_path
        and props.get("image_color_disabled")
        and "button_enabled" in props
    )
    inline_image = getattr(descriptor, "image_inline_kwarg", True)
    if image_path and not inline_image:
        # Descriptor builds the image off-band (e.g. Shape's inner
        # CTkLabel via ``export_state``) — don't auto-emit
        # ``image=`` / ``compound=`` to the constructor since the
        # underlying CTk class wouldn't accept them.
        image_path = None
    if image_path:
        if has_disabled_tint:
            on_attr = f"self.{var_name}_icon_on"
            off_attr = f"self.{var_name}_icon_off"
            # Normalise the colour-editor's "cleared" sentinel
            # ("transparent") to the same fallback as ``None`` so a
            # cleared field doesn't propagate ``"transparent"`` into
            # ``_tint_image`` and crash the export at hex-parse time.
            def _tint_or(c, fallback):
                return c if c and c != "transparent" else fallback
            on_src = _image_source_with_color(
                props, image_path,
                _tint_or(props.get("image_color"), "#ffffff"),
            )
            off_src = _image_source_with_color(
                props, image_path,
                _tint_or(props.get("image_color_disabled"), "#ffffff"),
            )
            pre_lines.append(f"{on_attr} = {on_src}")
            pre_lines.append(f"{off_attr} = {off_src}")
            start_attr = (
                on_attr if props.get("button_enabled", True) else off_attr
            )
            kwargs.append(("image", start_attr))
            post_image_lines.append(
                f"_wire_icon_state(self.{var_name}, "
                f"{on_attr}, {off_attr})",
            )
        else:
            kwargs.append(("image", _image_source(props, image_path)))
        if "compound" not in props:
            kwargs.append(("compound", '"left"'))

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
    if "image_width" in props or "image_height" in props:
        iw = _safe_int(props.get("image_width"), 20)
        ih = _safe_int(props.get("image_height"), 20)
        # Icon-mode contain-fit. Image-widget keeps its own width/height
        # branch below — different semantic, handled separately.
        iw, ih = _aspect_corrected_size(props, image_path, iw, ih)
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
    # image_color / image_color_disabled are builder-only PIL tints
    # (CTk doesn't expose a native image tint param). Pick between the
    # two based on the widget's enabled-flag — the builder's preview
    # does the same, so the exported file matches what the designer
    # saw. ``button_enabled`` (CTkButton et al.) and ``label_enabled``
    # (CTkLabel) carry identical tint semantics here; widgets without
    # either key fall through to the plain ``image_color``. Note: only
    # the PIL tint side is shared. Label deliberately does NOT also
    # emit ``state="disabled"`` (Tk Label's native disabled rendering
    # paints a stipple wash over the image); the manual color swap
    # below is what makes the label look disabled.
    #
    # ``transparent`` is the colour-editor's "cleared" sentinel — both
    # ``None`` and ``"transparent"`` mean "no tint", so we normalise
    # both away before falling through the OR chain. Without this, a
    # cleared ``image_color_disabled`` would propagate ``"transparent"``
    # into ``_tint_image`` and crash the export at hex-parse time.
    def _active(c):
        return c if c and c != "transparent" else None
    if (
        ("button_enabled" in props
         and not bool(_resolve_export_raw(props, "button_enabled")))
        or ("label_enabled" in props
            and not bool(_resolve_export_raw(props, "label_enabled")))
    ):
        color = (
            _active(_resolve_export_raw(props, "image_color_disabled"))
            or _active(_resolve_export_raw(props, "image_color"))
        )
    else:
        color = _active(_resolve_export_raw(props, "image_color"))
    if color:
        return (
            f"_tint_image({path_src}, {_py_literal(color)}, ({iw}, {ih}))"
        )
    return (
        f"ctk.CTkImage("
        f"light_image=Image.open({path_src}), "
        f"dark_image=Image.open({path_src}), "
        f"size=({iw}, {ih}))"
    )


def _image_source_with_color(
    props: dict, image_path: str, color: str,
) -> str:
    """Force a specific tint colour, regardless of ``button_enabled``.
    Used when the exporter emits BOTH the normal + disabled icon
    variants for a button that carries an ``image_color_disabled``.
    """
    if "image_width" in props or "image_height" in props:
        iw = _safe_int(props.get("image_width"), 20)
        ih = _safe_int(props.get("image_height"), 20)
        iw, ih = _aspect_corrected_size(props, image_path, iw, ih)
    else:
        iw = _safe_int(props.get("width"), 64)
        ih = _safe_int(props.get("height"), 64)
    normalised_path = _path_for_export(image_path)
    return (
        f"_tint_image({_py_literal(normalised_path)}, "
        f"{_py_literal(color)}, ({iw}, {ih}))"
    )


from app.io.code_exporter.runtime_helpers import (
    _circle_button_class_lines,
    _circle_label_class_lines,
    _circular_progress_class_lines,
    _icon_state_helper_lines,
    _align_text_label_helper_lines,
    _text_clipboard_helper_lines,
    _auto_hover_text_helper_lines,
    _font_register_helper_lines,
    _tint_helper_lines,
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


