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

# Module-level project-path stash so the per-image emit helpers can
# rewrite an in-assets absolute path to a relative ``assets/...``
# path without threading project context through every call site.
# Set at the top of ``export_project`` and cleared on the way out.
_CURRENT_PROJECT_PATH: str | None = None


_PREVIEW_SCREENSHOT_TEMPLATE = '''\
# CTkMaker preview tools — title marker, orange ring, draggable F12 button.
import tkinter as _ctkmaker_tk

# --- Title + ring — make it obvious this is a preview, not the
# production window. 4 thin orange Frames at the edges (Tk's
# highlightthickness gets covered by CTk's full-area frame, so
# we draw the ring as real widgets and lift them above content).
_CTKMAKER_PREVIEW_ORANGE = "#ff8800"
try:
    _ctkmaker_orig_title = {target}.title()
except _ctkmaker_tk.TclError:
    _ctkmaker_orig_title = ""
{target}.title("\U0001F7E0 PREVIEW — " + (_ctkmaker_orig_title or "CTkMaker"))

_CTKMAKER_RING_THICKNESS = 2
_ctkmaker_ring = []           # [(frame, place_kwargs), ...] — kept so we
                              # can place_forget/place back during capture
                              # so the orange ring doesn't bleed into PNGs.
def _ctkmaker_build_ring():
    if _ctkmaker_ring:
        return
    sides = [
        dict(x=0, y=0, relwidth=1.0, height=_CTKMAKER_RING_THICKNESS),
        dict(x=0, rely=1.0, y=-_CTKMAKER_RING_THICKNESS,
             relwidth=1.0, height=_CTKMAKER_RING_THICKNESS),
        dict(x=0, y=0, width=_CTKMAKER_RING_THICKNESS, relheight=1.0),
        dict(relx=1.0, x=-_CTKMAKER_RING_THICKNESS, y=0,
             width=_CTKMAKER_RING_THICKNESS, relheight=1.0),
    ]
    for spec in sides:
        f = _ctkmaker_tk.Frame({target}, bg=_CTKMAKER_PREVIEW_ORANGE,
                               bd=0, highlightthickness=0)
        f.place(**spec)
        f.lift()
        _ctkmaker_ring.append((f, spec))

def _ctkmaker_hide_ring():
    for f, _ in _ctkmaker_ring:
        try:
            f.place_forget()
        except _ctkmaker_tk.TclError:
            pass

def _ctkmaker_show_ring():
    for f, spec in _ctkmaker_ring:
        try:
            f.place(**spec)
            f.lift()
        except _ctkmaker_tk.TclError:
            pass

def _ctkmaker_relift_ring(_event=None):
    for f, _ in _ctkmaker_ring:
        try:
            f.lift()
        except _ctkmaker_tk.TclError:
            pass

_ctkmaker_build_ring()
# Re-lift on every reconfigure so newly-placed children don't bury
# the ring. 150 ms gives child widgets time to settle on first paint.
{target}.after(150, _ctkmaker_relift_ring)

_ctkmaker_floater = _ctkmaker_tk.Toplevel({target})
_ctkmaker_floater.overrideredirect(True)
_ctkmaker_floater.attributes("-topmost", True)
_ctkmaker_floater.configure(bg="#1f1f1f", highlightthickness=1,
                            highlightbackground="#3a3a3a")
_ctkmaker_inner = _ctkmaker_tk.Frame(_ctkmaker_floater, bg="#1f1f1f",
                                     bd=0, highlightthickness=0)
_ctkmaker_inner.pack()
def _ctkmaker_make_btn(text):
    return _ctkmaker_tk.Button(
        _ctkmaker_inner, text=text,
        font=("Segoe UI", 9, "bold"), bg="#2d2d30", fg="#cccccc",
        activebackground="#3e3e42", activeforeground="#ffffff",
        bd=0, padx=10, pady=4,
        relief="flat",
    )

_ctkmaker_btn_save = _ctkmaker_make_btn(" 💾  Save  ·  F12 ")
_ctkmaker_btn_save.pack(side="left", padx=(0, 1))
_ctkmaker_btn_copy = _ctkmaker_make_btn(" 📋  Copy  ·  F11 ")
_ctkmaker_btn_copy.pack(side="left")

def _ctkmaker_toast(message):
    """Self-destroying Toplevel — bottom-centre of the target, 1500ms
    lifetime. Soft user feedback after Save / Copy actions so the
    user doesn't have to glance at the console.
    """
    try:
        toast = _ctkmaker_tk.Toplevel({target})
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg="#2d2d30", highlightthickness=1,
                        highlightbackground="#3a3a3a")
        lbl = _ctkmaker_tk.Label(
            toast, text=message,
            font=("Segoe UI", 9, "bold"),
            bg="#2d2d30", fg="#cccccc",
            padx=14, pady=6,
        )
        lbl.pack()
        toast.update_idletasks()
        tw = toast.winfo_reqwidth()
        th = toast.winfo_reqheight()
        x = {target}.winfo_rootx() + ({target}.winfo_width() - tw) // 2
        y = {target}.winfo_rooty() + {target}.winfo_height() - th - 24
        toast.geometry(f"+{{x}}+{{y}}")
        toast.after(1500, toast.destroy)
    except _ctkmaker_tk.TclError:
        pass

def _ctkmaker_capture():
    """Grab the target's client area as a PIL Image. Hides the
    floater + orange ring during the brief grab so neither bleeds
    into the saved PNG. Returns None on failure so callers degrade
    gracefully.
    """
    try:
        from PIL import ImageGrab
    except ImportError:
        print("Pillow not installed — cannot capture screen.")
        return None
    _ctkmaker_floater.withdraw()
    _ctkmaker_hide_ring()
    {target}.update_idletasks()
    {target}.update()
    x = {target}.winfo_rootx()
    y = {target}.winfo_rooty()
    w = {target}.winfo_width()
    h = {target}.winfo_height()
    try:
        return ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    finally:
        _ctkmaker_show_ring()
        _ctkmaker_floater.deiconify()

def _ctkmaker_screenshot_save(_event=None):
    img = _ctkmaker_capture()
    if img is None:
        return
    from tkinter import filedialog
    path = filedialog.asksaveasfilename(
        parent={target}, defaultextension=".png",
        filetypes=[("PNG image", "*.png")],
        initialfile="preview.png",
    )
    if path:
        img.save(path)
        print(f"Saved screenshot: {{path}}")
        _ctkmaker_toast("Screenshot saved")

def _ctkmaker_screenshot_copy(_event=None):
    """Copy the captured image to the system clipboard so the user can
    paste it directly into chat / docs / image editors. Windows-only —
    uses System.Windows.Forms.Clipboard via PowerShell so we don't add
    pywin32 as a dependency. On other platforms or on failure, the
    image stays at the temp path and the path is printed instead.
    """
    img = _ctkmaker_capture()
    if img is None:
        return
    import os, subprocess, sys, tempfile
    fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="ctkmaker_clip_")
    os.close(fd)
    img.save(tmp_path, "PNG")
    if sys.platform != "win32":
        print(f"Clipboard copy not supported on this platform — saved to: {{tmp_path}}")
        return
    ps_cmd = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        f"$img = [System.Drawing.Image]::FromFile('{{tmp_path}}'); "
        "[System.Windows.Forms.Clipboard]::SetImage($img); "
        "$img.Dispose()"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
        capture_output=True, text=True,
    )
    if proc.returncode == 0:
        print("Screenshot copied to clipboard.")
        _ctkmaker_toast("Copied to clipboard")
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    else:
        print(f"Clipboard copy failed: {{proc.stderr.strip()}}")
        print(f"Image saved to: {{tmp_path}}")
        _ctkmaker_toast("Clipboard copy failed — see console")

{target}.bind_all("<F12>", _ctkmaker_screenshot_save)
{target}.bind_all("<F11>", _ctkmaker_screenshot_copy)

# --- Drag — let the user reposition the button anywhere on screen.
# While unchanged, default top-right anchoring kicks in. Once dragged,
# the offset persists relative to the target window. Each button
# distinguishes click from drag via a 4-pixel threshold so a small
# wobble during click doesn't suppress the action.
_ctkmaker_user_offset = [None, None]
_ctkmaker_drag_press = [0, 0]
_ctkmaker_drag_origin = [0, 0]
_ctkmaker_was_dragged = [False]

def _ctkmaker_press(_e):
    _ctkmaker_was_dragged[0] = False
    _ctkmaker_drag_press[0] = _e.x_root
    _ctkmaker_drag_press[1] = _e.y_root
    _ctkmaker_drag_origin[0] = _ctkmaker_floater.winfo_rootx()
    _ctkmaker_drag_origin[1] = _ctkmaker_floater.winfo_rooty()

def _ctkmaker_drag(_e):
    dx = _e.x_root - _ctkmaker_drag_press[0]
    dy = _e.y_root - _ctkmaker_drag_press[1]
    if not _ctkmaker_was_dragged[0] and abs(dx) + abs(dy) > 4:
        _ctkmaker_was_dragged[0] = True
    if _ctkmaker_was_dragged[0]:
        nx = _ctkmaker_drag_origin[0] + dx
        ny = _ctkmaker_drag_origin[1] + dy
        _ctkmaker_floater.geometry(f"+{{nx}}+{{ny}}")

def _ctkmaker_release_factory(action):
    def _release(_e):
        if _ctkmaker_was_dragged[0]:
            try:
                _ctkmaker_user_offset[0] = (
                    _ctkmaker_floater.winfo_rootx() - {target}.winfo_rootx()
                )
                _ctkmaker_user_offset[1] = (
                    _ctkmaker_floater.winfo_rooty() - {target}.winfo_rooty()
                )
            except _ctkmaker_tk.TclError:
                pass
        else:
            action()
    return _release

for _btn, _action in (
    (_ctkmaker_btn_save, _ctkmaker_screenshot_save),
    (_ctkmaker_btn_copy, _ctkmaker_screenshot_copy),
):
    _btn.bind("<ButtonPress-1>", _ctkmaker_press, add="+")
    _btn.bind("<B1-Motion>", _ctkmaker_drag, add="+")
    _btn.bind("<ButtonRelease-1>", _ctkmaker_release_factory(_action), add="+")

def _ctkmaker_position_floater(_event=None):
    try:
        if not _ctkmaker_floater.winfo_exists():
            return
        {target}.update_idletasks()
        if _ctkmaker_user_offset[0] is not None:
            x = {target}.winfo_rootx() + _ctkmaker_user_offset[0]
            y = {target}.winfo_rooty() + _ctkmaker_user_offset[1]
        else:
            bw = _ctkmaker_floater.winfo_reqwidth()
            x = {target}.winfo_rootx() + {target}.winfo_width() - bw - 12
            y = {target}.winfo_rooty() + 8
        _ctkmaker_floater.geometry(f"+{{x}}+{{y}}")
    except _ctkmaker_tk.TclError:
        pass

{target}.bind("<Configure>", _ctkmaker_position_floater, add="+")
{target}.after(120, _ctkmaker_position_floater)

def _ctkmaker_close_floater(_event=None):
    try:
        _ctkmaker_floater.destroy()
    except _ctkmaker_tk.TclError:
        pass

{target}.bind("<Destroy>", _ctkmaker_close_floater, add="+")
print("[CTkMaker preview] F12 / Save → file. F11 / Copy → clipboard. "
      "Drag a button to reposition.")
'''


def _preview_screenshot_lines(target: str) -> list[str]:
    """Inject the floating screenshot button + F12 hotkey into the
    __main__ block when the file is being run as a CTkMaker preview
    (NOT a real export). ``target`` is the variable name of the
    visible window — ``app`` for the main-window preview, the dialog
    instance for dialog previews. The floater hides itself during
    capture so it doesn't appear in the saved PNG.
    """
    body = _PREVIEW_SCREENSHOT_TEMPLATE.format(target=target)
    return [INDENT + line for line in body.splitlines()]


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
# Var-name fallbacks the exporter applied during this run because the
# user-set Properties-panel "Name" was empty / invalid / a duplicate.
# Tuples are ``(doc_name, intended, fallback, reason)``; reset at the
# start of each ``generate_code`` call. Surfaced via
# ``get_var_name_fallbacks()`` so launchers (F5 preview, export
# dialog) can show the user which names were silently rewritten.
_VAR_NAME_FALLBACKS: list[tuple[str, str, str, str]] = []
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
    binding to a property NOT covered by ``BINDING_WIRINGS``. Drives
    the auto-trace helper-function emission so projects without any
    such bindings keep their generated file lean.
    """
    for w in scoped_widgets:
        for key, val in (w.properties or {}).items():
            if _is_non_textvariable_var_binding(w.widget_type, key, val):
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


_AUTO_TRACE_WIDGET_HELPER = '''def _bind_var_to_widget(var, widget, prop):
    """Mirror ``var.get()`` into ``widget.configure(prop=…)`` whenever
    the variable changes. Initial sync on attach so the widget paints
    the var's current value even if the constructor kwarg already set
    it to the same literal.
    """
    def _update(*_):
        widget.configure(**{prop: var.get()})
    var.trace_add("write", _update)
    _update()
'''

_AUTO_TRACE_TEXTBOX_HELPER = '''def _bind_var_to_textbox(var, tb):
    """Mirror ``var.get()`` into a CTkTextbox's content via
    delete+insert. CTkTextbox has no ``textvariable=`` support, so
    every change rewrites the whole buffer.
    """
    def _update(*_):
        tb.delete("1.0", "end")
        tb.insert("1.0", var.get())
    var.trace_add("write", _update)
    _update()
'''


def _emit_auto_trace_bindings(node, full_name: str) -> list[str]:
    """Phase 3 — produce ``_bind_var_to_widget`` / ``_bind_var_to_textbox``
    call lines for every property on ``node`` that's bound to a
    variable but NOT in ``BINDING_WIRINGS``. Each line wires a
    ``trace_add`` listener that mirrors ``var.set(…)`` calls into a
    runtime ``configure`` (or ``delete``+``insert`` for Textbox).

    Returns an empty list when the widget has no qualifying
    bindings — preserves the pre-1.9.5 emit shape for widgets that
    only carry textvariable-mapped bindings (CTkLabel, CTkSlider,
    CTkSwitch, …).
    """
    from app.core.variables import parse_var_token
    if _EXPORT_PROJECT is None:
        return []
    out: list[str] = []
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
        # widget has no ``configure(text=…)`` slot. Other widgets +
        # other Textbox properties go through the configure helper.
        if node.widget_type == "CTkTextbox" and key == "initial_text":
            out.append(
                f"_bind_var_to_textbox({var_attr}, {full_name})",
            )
        else:
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
            (w.properties.get("text_position", "right") or "right") != "right"
            or int(w.properties.get("text_spacing", 6) or 6) != 6
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

    if needs_icon_state:
        lines.extend(_icon_state_helper_lines())
        lines.append("")

    if needs_circular_progress:
        lines.extend(_circular_progress_class_lines())
        lines.append("")

    if needs_circle_button:
        lines.extend(_circle_button_class_lines())
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
    lines.append(f'{INDENT}ctk.set_appearance_mode("{DEFAULT_APPEARANCE_MODE}")')

    if preview_match is not None:
        preview_doc, preview_cls = preview_match
        var = _slug(preview_doc.name) or "dialog"
        lines.append(f"{INDENT}# Dialog-only preview — hidden root host.")
        lines.append(f"{INDENT}app = ctk.CTk()")
        lines.append(f"{INDENT}app.withdraw()")
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
    """Phase 3 — broader behavior-class gate. Returns True when the
    doc has either bound handlers OR Behavior Field values to wire.
    Field-only docs (declared annotations, picked widgets, no event
    handlers) still require the ``self._behavior = X()`` instance so
    setup() can run + the field assignments have a target.
    """
    if _doc_has_handlers(doc):
        return True
    if doc.behavior_field_values:
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
    ``_build_id_to_var_name`` (Phase 3 Behavior Field replay) so the
    two walks can never drift.

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
    """Phase 3 Behavior Fields replay — alias of
    ``_resolve_var_names`` so callers reading post-build assignments
    line up with whatever ``_emit_subtree`` actually emitted.
    Memoisation in ``_NAME_MAP_CACHE`` keeps this from re-walking the
    tree or duplicating user warnings.
    """
    return _resolve_var_names(doc)


def _emit_behavior_field_lines(
    doc: Document,
    id_to_var: dict[str, str],
    instance_prefix: str,
) -> list[str]:
    """Phase 3 — produce the ``self._behavior.<field> = <expr>`` lines
    that wire Inspector slots after ``_build_ui()`` returns. Skips
    bindings whose target widget no longer exists (silent drop —
    panel already shows ``(missing widget)`` so the user has been
    warned in the editor).

    Indentation is two levels (``__init__`` body inside ``class``);
    the caller appends them right after the ``self._build_ui()``
    call.
    """
    if not doc.behavior_field_values:
        return []
    lines: list[str] = []
    for field_name, widget_id in doc.behavior_field_values.items():
        var_name = id_to_var.get(widget_id)
        if not var_name:
            continue
        lines.append(
            f"{INDENT}{INDENT}self._behavior.{field_name} = "
            f"{instance_prefix}{var_name}",
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
    # Phase 3 — Behavior Field assignments must run AFTER _build_ui()
    # since they reference widgets created inside it. Per-doc id-to-
    # var map mirrors the naming the subtree walk emits, so the
    # right-hand sides line up with the actual ``self.<widget_var>``
    # attributes set during the build.
    if _doc_needs_behavior(doc) and doc.behavior_field_values:
        id_to_var = _build_id_to_var_name(doc)
        field_lines = _emit_behavior_field_lines(doc, id_to_var, "self.")
        lines.extend(field_lines)
    # Phase 2 setup() — runs AFTER _build_ui + Phase 3 field
    # assignments so user code can reference both ``self.<widget>``
    # attributes and the bound ``self._behavior.<field>`` slots
    # without worrying about ordering. Widget command kwargs
    # captured ``self._behavior.<method>`` during _build_ui; those
    # bindings are stable references whose call sites fire later.
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
    # the legacy ``<type>_<N>`` shape. Same map fuels the Phase 3
    # Behavior Field replay above (memoised in ``_NAME_MAP_CACHE``).
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
        try:
            max_w = int(node.properties.get("width", 0) or 0)
            max_h = int(node.properties.get("height", 0) or 0)
        except (TypeError, ValueError):
            max_w = max_h = 0
        for child in node.children:
            try:
                cx = int(child.properties.get("x", 0) or 0)
                cy = int(child.properties.get("y", 0) or 0)
                cw = int(child.properties.get("width", 0) or 0)
                ch = int(child.properties.get("height", 0) or 0)
            except (TypeError, ValueError):
                continue
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
    try:
        child_spacing = int(
            node.properties.get(
                "layout_spacing",
                LAYOUT_CONTAINER_DEFAULTS["layout_spacing"],
            ) or 0,
        )
    except (TypeError, ValueError):
        child_spacing = 0
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
    multiline_list_keys: set[str] = getattr(
        descriptor, "multiline_list_keys", set(),
    )
    overrides: dict = descriptor.export_kwarg_overrides(props)

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
        if key in node_only or key in font_keys or key == "image":
            continue
        if key in overrides:
            val = overrides[key]
        if key in multiline_list_keys:
            lines_list = [
                ln for ln in str(val or "").splitlines() if ln.strip()
            ] or [""]
            kwargs.append((key, _py_literal(lines_list)))
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
        if key in emitted or key in node_only or key in font_keys:
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
            state_src = '"readonly"'
        elif not props.get("button_enabled", True):
            state_src = '"disabled"'
        else:
            state_src = '"normal"'
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
        state_src = (
            '"disabled"' if props.get("state_disabled") else '"normal"'
        )
        kwargs.append(("state", state_src))

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
        else:
            kwargs.append(
                (font_kwarg_name, _font_source(props, effective_family)),
            )

    image_path = props.get("image")
    pre_lines: list[str] = []
    # When a button has both an icon AND a disabled tint, emit TWO
    # CTkImages + a heads-up comment so the user can call
    # _apply_icon_state(...) from their state-change code. CTk swaps
    # text_color on state but not image, so this is the only clean
    # way to get a true disabled-looking icon.
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
            # Store both tinted variants on ``self`` so they stay
            # accessible for _apply_icon_state(...) from any later
            # state-change code the user writes.
            on_attr = f"self.{var_name}_icon_on"
            off_attr = f"self.{var_name}_icon_off"
            on_src = _image_source_with_color(
                props, image_path,
                props.get("image_color") or "#ffffff",
            )
            off_src = _image_source_with_color(
                props, image_path, props.get("image_color_disabled"),
            )
            pre_lines.append(
                f"# Icon has a disabled-state colour. Call "
                f"_apply_icon_state(self.{var_name},",
            )
            pre_lines.append(
                f"# {on_attr}, {off_attr}, new_state) "
                f"when you toggle state.",
            )
            pre_lines.append(f"{on_attr} = {on_src}")
            pre_lines.append(f"{off_attr} = {off_src}")
            start_attr = (
                on_attr if props.get("button_enabled", True) else off_attr
            )
            kwargs.append(("image", start_attr))
        else:
            kwargs.append(("image", _image_source(props, image_path)))
        if "compound" not in props:
            kwargs.append(("compound", '"left"'))

    ctk_class = (
        getattr(descriptor, "ctk_class_name", "") or node.widget_type
    )
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

    class_prefix = (
        "ctk." if getattr(descriptor, "is_ctk_class", True) else ""
    )
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

    lines.append(
        _geometry_call(
            full_name, props, parent_layout, parent_spacing,
            child_index, parent_cols, parent_rows,
        ),
    )

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
    bw = int(props.get("dropdown_border_width", 1))
    if not props.get("dropdown_border_enabled", True):
        bw = 0
    kwargs = [
        ("fg_color", props.get("dropdown_fg_color", "#2b2b2b")),
        ("text_color", props.get("dropdown_text_color", "#dce4ee")),
        ("hover_color", props.get("dropdown_hover_color", "#3a3a3a")),
        ("offset", int(props.get("dropdown_offset", 4))),
        ("button_align", props.get("dropdown_button_align", "center")),
        ("max_visible", int(props.get("dropdown_max_visible", 8))),
        ("border_width", bw),
        ("border_color", props.get("dropdown_border_color", "#3c3c3c")),
        ("corner_radius", int(props.get("dropdown_corner_radius", 6))),
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
def _class_name_for(
    doc: Document, index: int, used: set[str],
) -> str:
    slug = _slug(doc.name)
    if slug:
        parts = [p for p in slug.split("_") if p]
        candidate = "".join(p.capitalize() for p in parts)
    else:
        candidate = f"Window{index + 1}"
    if not candidate or not candidate[0].isalpha():
        candidate = f"Window{index + 1}"
    name = candidate
    suffix = 1
    while name in used:
        suffix += 1
        name = f"{candidate}{suffix}"
    return name


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_")
    return value.lower()


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
        weight = '"bold"' if props.get("font_bold") else '"normal"'
        slant = '"italic"' if props.get("font_italic") else '"roman"'
        parts.extend([f"size={size}", f"weight={weight}", f"slant={slant}"])
        if props.get("font_underline"):
            parts.append("underline=True")
        if props.get("font_overstrike"):
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
    # two based on ``button_enabled`` — the builder's preview does the
    # same, so the exported file matches what the designer saw.
    # ``button_enabled`` only lives on command-capable widgets
    # (CTkButton etc.); leaf widgets without that key fall through to
    # the plain ``image_color``.
    if (
        "button_enabled" in props
        and not bool(props.get("button_enabled"))
    ):
        color = (
            props.get("image_color_disabled")
            or props.get("image_color")
        )
    else:
        color = props.get("image_color")
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
    else:
        iw = _safe_int(props.get("width"), 64)
        ih = _safe_int(props.get("height"), 64)
    normalised_path = _path_for_export(image_path)
    return (
        f"_tint_image({_py_literal(normalised_path)}, "
        f"{_py_literal(color)}, ({iw}, {ih}))"
    )


def _circle_button_class_lines() -> list[str]:
    """Inline the ``CircleButton`` runtime class (CTkButton override
    that lifts the rounded-corner reservation in ``_create_grid``) into
    generated ``.py`` files. Source lives at
    ``app/widgets/runtime/circle_button.py`` for builder use; reading
    via ``inspect`` keeps a single edit propagating to every export.
    The standard import block already covers ``customtkinter as ctk``.
    """
    import inspect

    from app.widgets.runtime.circle_button import CircleButton

    return inspect.getsource(CircleButton).splitlines()


def _circular_progress_class_lines() -> list[str]:
    """Inline the ``CircularProgress`` runtime class + its bg-resolver
    helper into generated `.py` files. The class lives in
    ``app/widgets/runtime/circular_progress.py`` for builder use; we
    read its source via ``inspect`` so a single edit propagates to
    every export. The runtime module's own ``tkinter as tk`` /
    ``customtkinter as ctk`` imports are already emitted by the
    standard import block; ``CTkScalingBaseClass`` is a deeper CTk
    internal path that the standard imports don't cover, so we emit
    it here as a sibling of the helper + class definitions.
    """
    import inspect

    from app.widgets.runtime.circular_progress import (
        CircularProgress,
        _circular_progress_resolve_bg,
    )

    lines: list[str] = [
        "from customtkinter.windows.widgets.scaling import "
        "CTkScalingBaseClass",
        "",
    ]
    lines.extend(
        inspect.getsource(_circular_progress_resolve_bg).splitlines(),
    )
    lines.append("")
    lines.append("")
    lines.extend(inspect.getsource(CircularProgress).splitlines())
    return lines


def _icon_state_helper_lines() -> list[str]:
    """Emit ``_apply_icon_state`` — the companion helper that swaps a
    button's icon + state together. CTk's own state change doesn't
    touch the image, so a disabled-tint variant never shows up without
    this wrapper. The exporter also drops a per-button comment so the
    user knows where to wire it from their own code.
    """
    return [
        "def _apply_icon_state(button, icon_on, icon_off, state):",
        '    """Swap a CTkButton\'s icon to match a state change.',
        "    Call this from your own code whenever you disable / enable",
        "    a button whose icon carries an image_color_disabled variant.",
        '    """',
        '    button.configure(',
        '        state=state,',
        '        image=icon_off if state == "disabled" else icon_on,',
        "    )",
    ]


def _align_text_label_helper_lines() -> list[str]:
    """Emit a helper that re-grids the internal `_canvas` (box / dot)
    and `_text_label` of any compound widget that follows the
    CheckBox / RadioButton / Switch grid layout. Lets the label sit
    on any side (left / top / bottom — right is CTk's default and
    a no-op). Same private-attr reach the builder uses at design
    time so canvas = preview = exported runtime.
    """
    return [
        "def _align_text_label(widget, position, spacing=6):",
        '    """Re-grid the checkbox box + label so the label sits at',
        "    `position` (left / right / top / bottom) with `spacing` px",
        "    between them. Same private-attr reach the CTk Visual",
        '    Builder uses at design time."""',
        '    canvas = getattr(widget, "_canvas", None)',
        '    label = getattr(widget, "_text_label", None)',
        '    bg = getattr(widget, "_bg_canvas", None)',
        "    if canvas is None or label is None: return",
        "    s = max(0, int(spacing))",
        "    canvas.grid_forget(); label.grid_forget()",
        "    if bg is not None: bg.grid_forget()",
        '    if position == "left":',
        '        if bg is not None: bg.grid(row=0, column=0, columnspan=3, sticky="nswe")',
        '        label.grid(row=0, column=0, sticky="e", padx=(0, s)); canvas.grid(row=0, column=2, sticky="w")',
        '        label["anchor"] = "e"',
        '    elif position == "top":',
        '        if bg is not None: bg.grid(row=0, column=0, rowspan=3, columnspan=3, sticky="nswe")',
        '        label.grid(row=0, column=0, sticky="s", pady=(0, s)); canvas.grid(row=2, column=0, sticky="n")',
        '        label["anchor"] = "center"',
        '    elif position == "bottom":',
        '        if bg is not None: bg.grid(row=0, column=0, rowspan=3, columnspan=3, sticky="nswe")',
        '        canvas.grid(row=0, column=0, sticky="s"); label.grid(row=2, column=0, sticky="n", pady=(s, 0))',
        '        label["anchor"] = "center"',
        "    else:",
        '        if bg is not None: bg.grid(row=0, column=0, columnspan=3, sticky="nswe")',
        '        canvas.grid(row=0, column=0, sticky="e"); label.grid(row=0, column=2, sticky="w", padx=(s, 0))',
        '        label["anchor"] = "w"',
    ]


def _text_clipboard_helper_lines() -> list[str]:
    """Emit a helper that wires right-click context menus and a
    keycode-based Ctrl shortcut router onto every tk.Entry / tk.Text
    widget. Lets the exported app's text fields support Cut / Copy /
    Paste / Select All via mouse AND keyboard, regardless of the
    user's keyboard layout (Latin keysyms break under non-Latin
    layouts; hardware keycodes don't).
    """
    return [
        "def _setup_text_clipboard(root):",
        '    """Add right-click menu and keyboard shortcuts to all text fields."""',
        "    import tkinter as tk",
        "    def _popup(event):",
        "        widget = event.widget",
        "        # tk.Entry uses .selection_present(); tk.Text uses",
        '        # .tag_ranges("sel"). Try both, default off.',
        "        has_sel = False",
        "        try: has_sel = bool(widget.selection_present())",
        "        except Exception:",
        "            try: has_sel = bool(widget.tag_ranges(\"sel\"))",
        "            except Exception: has_sel = False",
        "        menu = tk.Menu(widget, tearoff=0)",
        '        menu.add_command(label="Cut",   state=("normal" if has_sel else "disabled"),  command=lambda: widget.event_generate("<<Cut>>"))',
        '        menu.add_command(label="Copy",  state=("normal" if has_sel else "disabled"),  command=lambda: widget.event_generate("<<Copy>>"))',
        '        menu.add_command(label="Paste", command=lambda: widget.event_generate("<<Paste>>"))',
        "        menu.add_separator()",
        '        menu.add_command(label="Select All", command=lambda: widget.event_generate("<<SelectAll>>"))',
        "        try: menu.tk_popup(event.x_root, event.y_root)",
        "        finally: menu.grab_release()",
        "    def _ctrl(event):",
        "        # Latin layouts (V/C/X/A keysym) hit tk's defaults — skip.",
        '        if event.keysym.lower() in ("v", "c", "x", "a"): return None',
        "        kc = event.keycode",
        '        if kc == 86: event.widget.event_generate("<<Paste>>"); return "break"',
        '        if kc == 67: event.widget.event_generate("<<Copy>>");  return "break"',
        '        if kc == 88: event.widget.event_generate("<<Cut>>");   return "break"',
        '        if kc == 65:',
        '            try: event.widget.event_generate("<<SelectAll>>")',
        "            except Exception: pass",
        '            return "break"',
        '    for cls in ("Entry", "Text"):',
        '        root.bind_class(cls, "<Button-3>", _popup, add="+")',
        '        root.bind_class(cls, "<Control-KeyPress>", _ctrl, add="+")',
        "    # Clicks on non-text widgets (Frame, root, Button, etc.)",
        "    # force focus to the root so any previously-focused",
        "    # Entry / Text fires FocusOut — that's what CTk relies on",
        "    # to restore its placeholder when the field is empty.",
        "    # Without this the caret stays blinking in an Entry even",
        "    # after the user clicked somewhere else.",
        "    def _focus_restore(event):",
        "        target = event.widget",
        "        if isinstance(target, (tk.Entry, tk.Text)):",
        "            return",
        "        # Defer by one tick so the clicked widget's own focus",
        "        # handling runs first; if it takes focus, we stay out",
        "        # of its way. Otherwise focus lands on the root and",
        "        # any Entry picks up its FocusOut.",
        "        try: root.after(1, root.focus_set)",
        "        except Exception: pass",
        '    root.bind_all("<Button-1>", _focus_restore, add="+")',
    ]


def _auto_hover_text_helper_lines() -> list[str]:
    """Emit a tiny module-level helper that wires <Enter>/<Leave> on a
    button to swap its text colour. CTk's native hover only retints
    the background; this gives the label its own reactive feel.
    Reaches into ``_text_label`` directly so it doesn't trip CTk's
    full configure pipeline (which would reset the hover background
    mid-hover).
    """
    return [
        "def _auto_hover_text(button, normal, hover):",
        '    """Bind <Enter>/<Leave> to swap text_color. Same lighten/darken',
        "    direction CTkMaker uses at design time so the",
        '    runtime feel matches the canvas preview."""',
        "    def _set(colour):",
        '        lbl = getattr(button, "_text_label", None)',
        "        if lbl is not None:",
        "            lbl.configure(fg=colour)",
        '    button.bind("<Enter>", lambda e: _set(hover))',
        '    button.bind("<Leave>", lambda e: _set(normal))',
    ]


def _font_register_helper_lines() -> list[str]:
    """Emit a module-level helper that loads every ``.ttf`` / ``.otf``
    sitting in ``assets/fonts/`` next to the script via tkextrafont
    so ``CTkFont(family=...)`` resolves the bundled families. Soft
    dependency — if tkextrafont isn't installed, the helper logs and
    falls back to Tk defaults so the rest of the app still runs.
    """
    return [
        "def _register_project_fonts(root):",
        '    """Load every .ttf / .otf in assets/fonts/ next to this',
        "    script so widget CTkFont(family=...) lookups can find",
        '    families bundled with the project."""',
        "    from pathlib import Path",
        '    fonts_dir = Path(__file__).resolve().parent / "assets" / "fonts"',
        "    if not fonts_dir.exists():",
        "        return",
        "    try:",
        "        from tkextrafont import Font",
        "    except ImportError:",
        "        # tkextrafont missing — bundled fonts won't load, but",
        "        # system / Tk-default fonts still render.",
        "        return",
        '    for f in sorted(fonts_dir.iterdir()):',
        '        if f.suffix.lower() in (".ttf", ".otf", ".ttc"):',
        "            try:",
        "                Font(root, file=str(f))",
        "            except Exception:",
        "                pass",
    ]


def _tint_helper_lines() -> list[str]:
    """Emit a module-level helper that tints a PNG with an RGB hex
    color while preserving the source alpha channel. Used by every
    widget whose ``image_color`` is set (Image + CTkButton-style
    icon tint). Matches the builder's preview tint so the exported
    app renders identically.
    """
    return [
        "def _tint_image(path, hex_color, size):",
        '    """Return a CTkImage whose pixels are recoloured to `hex_color`',
        "    while keeping the source PNG's alpha. Same tint logic the CTk",
        '    Visual Builder uses at design time."""',
        "    src = Image.open(path).convert(\"RGBA\")",
        "    r = int(hex_color[1:3], 16)",
        "    g = int(hex_color[3:5], 16)",
        "    b = int(hex_color[5:7], 16)",
        "    alpha = src.split()[-1]",
        "    tinted = Image.new(\"RGBA\", src.size, (r, g, b, 255))",
        "    tinted.putalpha(alpha)",
        "    return ctk.CTkImage(",
        "        light_image=tinted, dark_image=tinted, size=size,",
        "    )",
    ]


def _py_literal(val) -> str:
    if val is None:
        return "None"
    if isinstance(val, bool):
        return "True" if val else "False"
    if isinstance(val, (int, float)):
        return repr(val)
    if isinstance(val, str):
        return repr(val)
    return repr(val)


def _safe_int(val, default: int) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


