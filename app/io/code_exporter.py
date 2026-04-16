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
    LAYOUT_DEFAULTS,
    LAYOUT_NODE_ONLY_KEYS,
    normalise_layout_type,
)
from app.widgets.registry import get_descriptor

DEFAULT_APPEARANCE_MODE = "dark"
INDENT = "    "


def export_project(project: Project, path: str | Path) -> None:
    source = generate_code(project)
    Path(path).write_text(source, encoding="utf-8")


def generate_code(project: Project) -> str:
    needs_pil = any(
        node.properties.get("image") for node in project.iter_all_widgets()
    )

    lines: list[str] = ["import customtkinter as ctk"]
    if needs_pil:
        lines.append("from PIL import Image")
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

    first_doc, first_class = class_names[0]
    lines.append('if __name__ == "__main__":')
    lines.append(f'{INDENT}ctk.set_appearance_mode("{DEFAULT_APPEARANCE_MODE}")')
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
        doc_layout = normalise_layout_type(
            (doc.window_properties or {}).get("layout_type"),
        )
        for node in doc.root_widgets:
            _emit_subtree(
                node,
                master_var="self",
                lines=body_lines,
                counts=counts,
                instance_prefix="self.",
                parent_layout=doc_layout,
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
) -> None:
    var_name = _make_var_name(node, counts)
    lines.extend(
        _emit_widget(
            node, var_name, master_var, instance_prefix, parent_layout,
        ),
    )
    lines.append("")
    child_master = f"{instance_prefix}{var_name}"
    child_layout = normalise_layout_type(
        node.properties.get("layout_type", DEFAULT_LAYOUT_TYPE),
    )
    for child in node.children:
        _emit_subtree(
            child,
            master_var=child_master,
            lines=lines,
            counts=counts,
            instance_prefix=instance_prefix,
            parent_layout=child_layout,
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

    lines.append(_geometry_call(full_name, props, parent_layout))
    lines.extend(descriptor.export_state(full_name, props))
    return lines


def _geometry_call(
    full_name: str, props: dict, parent_layout: str,
) -> str:
    layout = normalise_layout_type(parent_layout)
    if layout == "pack":
        parts: list[str] = []
        side = props.get("pack_side", LAYOUT_DEFAULTS["pack_side"])
        if side and side != LAYOUT_DEFAULTS["pack_side"]:
            parts.append(f'side="{side}"')
        fill = props.get("pack_fill", LAYOUT_DEFAULTS["pack_fill"])
        if fill and fill != LAYOUT_DEFAULTS["pack_fill"]:
            parts.append(f'fill="{fill}"')
        expand = props.get("pack_expand", LAYOUT_DEFAULTS["pack_expand"])
        if expand:
            parts.append("expand=True")
        padx = _safe_int(
            props.get("pack_padx", LAYOUT_DEFAULTS["pack_padx"]), 0,
        )
        if padx:
            parts.append(f"padx={padx}")
        pady = _safe_int(
            props.get("pack_pady", LAYOUT_DEFAULTS["pack_pady"]), 0,
        )
        if pady:
            parts.append(f"pady={pady}")
        return f"{full_name}.pack({', '.join(parts)})"
    if layout == "grid":
        row = _safe_int(
            props.get("grid_row", LAYOUT_DEFAULTS["grid_row"]), 0,
        )
        col = _safe_int(
            props.get("grid_column", LAYOUT_DEFAULTS["grid_column"]), 0,
        )
        parts = [f"row={row}", f"column={col}"]
        rs = _safe_int(
            props.get("grid_rowspan", LAYOUT_DEFAULTS["grid_rowspan"]), 1,
        )
        if rs > 1:
            parts.append(f"rowspan={rs}")
        cs = _safe_int(
            props.get(
                "grid_columnspan", LAYOUT_DEFAULTS["grid_columnspan"],
            ),
            1,
        )
        if cs > 1:
            parts.append(f"columnspan={cs}")
        sticky = props.get("grid_sticky", LAYOUT_DEFAULTS["grid_sticky"])
        if sticky:
            parts.append(f'sticky="{sticky}"')
        padx = _safe_int(
            props.get("grid_padx", LAYOUT_DEFAULTS["grid_padx"]), 0,
        )
        if padx:
            parts.append(f"padx={padx}")
        pady = _safe_int(
            props.get("grid_pady", LAYOUT_DEFAULTS["grid_pady"]), 0,
        )
        if pady:
            parts.append(f"pady={pady}")
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
    path_src = _py_literal(image_path)
    return (
        f"ctk.CTkImage("
        f"light_image=Image.open({path_src}), "
        f"dark_image=Image.open({path_src}), "
        f"size=({iw}, {ih}))"
    )


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
