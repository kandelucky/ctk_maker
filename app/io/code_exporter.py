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


def export_project(
    project: Project, path: str | Path,
    preview_dialog_id: str | None = None,
    single_document_id: str | None = None,
) -> None:
    source = generate_code(
        project,
        preview_dialog_id=preview_dialog_id,
        single_document_id=single_document_id,
    )
    out = Path(path)
    out.write_text(source, encoding="utf-8")
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
    """
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
    needs_tk_import = any(
        w.widget_type == "CTkRadioButton"
        and str(w.properties.get("group") or "").strip()
        for w in scoped_widgets
    )

    lines: list[str] = ["import customtkinter as ctk"]
    if needs_tk_import:
        lines.append("import tkinter as tk")
    if needs_pil:
        lines.append("from PIL import Image")
    if needs_scrollable_dropdown:
        lines.append("from scrollable_dropdown import ScrollableDropdown")
    lines.append("")

    if needs_tint:
        lines.extend(_tint_helper_lines())
        lines.append("")

    if needs_icon_state:
        lines.extend(_icon_state_helper_lines())
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

    # In single-document mode, force the class to subclass ctk.CTk so
    # the exported file is a standalone runnable app — even if the
    # source document is a CTkToplevel in the multi-doc project.
    force_main = bool(single_document_id)
    for doc, cls_name in class_names:
        lines.extend(_emit_class(doc, cls_name, force_main=force_main))
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
        lines.append(f"{INDENT}app.mainloop()")
    lines.append("")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Class + widget emission
# ----------------------------------------------------------------------
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
) -> list[str]:
    # ``force_main`` is True for single-document export: the class
    # subclasses ``ctk.CTk`` even when the source doc is a Toplevel,
    # so the exported file runs as a standalone app.
    if force_main or not doc.is_toplevel:
        base = "ctk.CTk"
    else:
        base = "ctk.CTkToplevel"
    lines: list[str] = [f"class {class_name}({base}):"]
    if base == "ctk.CTkToplevel":
        lines.append(f"{INDENT}def __init__(self, master=None):")
        lines.append(f"{INDENT}{INDENT}super().__init__(master)")
    else:
        lines.append(f"{INDENT}def __init__(self):")
        lines.append(f"{INDENT}{INDENT}super().__init__()")

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
    lines.append("")
    lines.append(f"{INDENT}def _build_ui(self):")

    counts: dict[str, int] = {}
    body_lines: list[str] = []
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
                counts=counts,
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
    counts: dict[str, int],
    instance_prefix: str = "",
    parent_layout: str = DEFAULT_LAYOUT_TYPE,
    parent_spacing: int = 0,
    child_index: int = 0,
    parent_cols: int = 1,
    parent_rows: int = 1,
    radio_var_map: dict[str, tuple[str, str]] | None = None,
) -> None:
    var_name = _make_var_name(node, counts)
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
            counts=counts,
            instance_prefix=instance_prefix,
            parent_layout=child_layout,
            parent_spacing=child_spacing,
            child_index=idx,
            parent_cols=child_cols,
            parent_rows=child_rows,
            radio_var_map=radio_var_map,
        )


def _make_var_name(node: WidgetNode, counts: dict[str, int]) -> str:
    base = node.widget_type.replace("CTk", "").lower() or "widget"
    counts[base] = counts.get(base, 0) + 1
    return f"{base}_{counts[base]}"


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

    kwargs: list[tuple[str, str]] = []

    for key, val in props.items():
        if key in node_only or key in font_keys or key == "image":
            continue
        # pack_* / grid_* / layout_type live on the node for export,
        # never as CTk constructor kwargs.
        if key in LAYOUT_NODE_ONLY_KEYS:
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
        kwargs.append(("font", _font_source(props)))

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
    lines: list[str] = list(pre_lines)
    lines.append(f"{full_name} = ctk.{ctk_class}(")
    lines.append(f"    {master_var},")
    for key, src in kwargs:
        lines.append(f"    {key}={src},")
    lines.append(")")

    lines.append(
        _geometry_call(
            full_name, props, parent_layout, parent_spacing,
            child_index, parent_cols, parent_rows,
        ),
    )
    lines.extend(descriptor.export_state(full_name, props))
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


def _font_source(props: dict) -> str:
    size = _safe_int(props.get("font_size"), 13)
    weight = '"bold"' if props.get("font_bold") else '"normal"'
    slant = '"italic"' if props.get("font_italic") else '"roman"'
    parts = [f"size={size}", f"weight={weight}", f"slant={slant}"]
    if props.get("font_underline"):
        parts.append("underline=True")
    if props.get("font_overstrike"):
        parts.append("overstrike=True")
    return f"ctk.CTkFont({', '.join(parts)})"


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
    normalised_path = str(image_path).replace("\\", "/")
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
    normalised_path = str(image_path).replace("\\", "/")
    return (
        f"_tint_image({_py_literal(normalised_path)}, "
        f"{_py_literal(color)}, ({iw}, {ih}))"
    )


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


