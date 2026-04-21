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
) -> None:
    source = generate_code(project, preview_dialog_id=preview_dialog_id)
    Path(path).write_text(source, encoding="utf-8")


def generate_code(
    project: Project, preview_dialog_id: str | None = None,
) -> str:
    """Generate the project's ``.py`` source.

    When ``preview_dialog_id`` names one of the Toplevel documents,
    the ``__main__`` block is rewritten to open JUST that dialog on top
    of a withdrawn root — used by the per-dialog "▶ Preview" button in
    the canvas chrome so the designer can test a Toplevel in isolation
    without wiring a real event handler. All classes are still emitted
    unchanged so dialog-to-dialog references would resolve; only the
    ``__main__`` entry point differs.
    """
    needs_pil = any(
        node.properties.get("image") for node in project.iter_all_widgets()
    )
    needs_tint = any(
        node.properties.get("image") and node.properties.get("image_color")
        for node in project.iter_all_widgets()
    )

    lines: list[str] = ["import customtkinter as ctk"]
    if needs_pil:
        lines.append("from PIL import Image")
    lines.append("")

    if needs_tint:
        lines.extend(_tint_helper_lines())
        lines.append("")

    used_class_names: set[str] = set()
    class_names: list[tuple[Document, str]] = []
    for index, doc in enumerate(project.documents):
        cls_name = _class_name_for(doc, index, used_class_names)
        used_class_names.add(cls_name)
        class_names.append((doc, cls_name))

    for doc, cls_name in class_names:
        lines.extend(_emit_class(doc, cls_name))
        lines.append("")
        lines.append("")

    preview_match: tuple[Document, str] | None = None
    if preview_dialog_id:
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
        lines.append(f"{INDENT}app.mainloop()")
    lines.append("")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Class + widget emission
# ----------------------------------------------------------------------
def _emit_class(doc: Document, class_name: str) -> list[str]:
    base = "ctk.CTkToplevel" if doc.is_toplevel else "ctk.CTk"
    lines: list[str] = [f"class {class_name}({base}):"]
    if doc.is_toplevel:
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
) -> None:
    var_name = _make_var_name(node, counts)
    lines.extend(
        _emit_widget(
            node, var_name, master_var, instance_prefix,
            parent_layout, parent_spacing, child_index,
            parent_cols, parent_rows,
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
    if child_layout != DEFAULT_LAYOUT_TYPE and node.children:
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
    for idx, child in enumerate(node.children):
        _emit_subtree(
            child,
            master_var=child_master,
            lines=lines,
            counts=counts,
            instance_prefix=instance_prefix,
            parent_layout=child_layout,
            parent_spacing=child_spacing,
            child_index=idx,
            parent_cols=child_cols,
            parent_rows=child_rows,
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

    if "button_enabled" in props:
        state_src = (
            '"normal"' if props.get("button_enabled", True)
            else '"disabled"'
        )
        kwargs.append(("state", state_src))
    elif "state_disabled" in props:
        state_src = (
            '"disabled"' if props.get("state_disabled") else '"normal"'
        )
        kwargs.append(("state", state_src))

    if "border_enabled" in props and not props.get("border_enabled"):
        kwargs = [
            (k, '0' if k == "border_width" else v) for k, v in kwargs
        ]

    if font_keys and any(k in props for k in font_keys):
        kwargs.append(("font", _font_source(props)))

    image_path = props.get("image")
    if image_path:
        kwargs.append(("image", _image_source(props, image_path)))
        if "compound" not in props:
            kwargs.append(("compound", '"left"'))

    ctk_class = (
        getattr(descriptor, "ctk_class_name", "") or node.widget_type
    )
    full_name = f"{instance_prefix}{var_name}"
    lines = [f"{full_name} = ctk.{ctk_class}("]
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
    # image_color is a builder-only tint applied via PIL (CTk doesn't
    # expose a native tint param). When set, route through the helper
    # emitted at module top so one PNG can back many colored variants.
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


