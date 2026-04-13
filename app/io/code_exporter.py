"""Generate a runnable Python source file from a Project.

Walks `project.root_widgets` and produces a self-contained `.py` file that,
when run, recreates the designed UI using real CustomTkinter widgets.

Per-widget convention (matches WidgetDescriptor.transform_properties):
- Keys in `descriptor._NODE_ONLY_KEYS` are stripped from kwargs (still used
  for `place(x=x, y=y)` and image size).
- `state_disabled` bool → `state="disabled"/"normal"`.
- `font_*` keys → `font=ctk.CTkFont(...)`.
- `image` path + `image_width/height` → `image=ctk.CTkImage(...)`.

Window settings (title/size/theme) are hardcoded for now; Phase 5 adds a
proper Window settings panel that feeds this exporter.
"""

from __future__ import annotations

from pathlib import Path

from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.widgets.registry import get_descriptor

WINDOW_TITLE = "CTk App"
APPEARANCE_MODE = "dark"


def export_project(project: Project, path: str | Path) -> None:
    source = generate_code(project)
    Path(path).write_text(source, encoding="utf-8")


def generate_code(project: Project) -> str:
    needs_pil = any(node.properties.get("image") for node in project.root_widgets)

    geometry = f"{project.document_width}x{project.document_height}"

    lines: list[str] = ["import customtkinter as ctk"]
    if needs_pil:
        lines.append("from PIL import Image")
    lines += [
        "",
        f'ctk.set_appearance_mode("{APPEARANCE_MODE}")',
        "",
        "app = ctk.CTk()",
        f'app.title("{WINDOW_TITLE}")',
        f'app.geometry("{geometry}")',
        "",
    ]

    name_counts: dict[str, int] = {}
    for node in project.root_widgets:
        var_name = _make_var_name(node, name_counts)
        lines += _emit_widget(node, var_name)
        lines.append("")

    lines += ["app.mainloop()", ""]
    return "\n".join(lines)


def _make_var_name(node: WidgetNode, counts: dict[str, int]) -> str:
    base = node.widget_type.replace("CTk", "").lower() or "widget"
    counts[base] = counts.get(base, 0) + 1
    return f"{base}_{counts[base]}"


def _emit_widget(node: WidgetNode, var_name: str) -> list[str]:
    descriptor = get_descriptor(node.widget_type)
    if descriptor is None:
        return [f"# unknown widget type: {node.widget_type}"]

    props = node.properties
    node_only: set[str] = getattr(descriptor, "_NODE_ONLY_KEYS", set())
    font_keys: set[str] = getattr(descriptor, "_FONT_KEYS", set())

    kwargs: list[tuple[str, str]] = []

    for key, val in props.items():
        if key in node_only or key in font_keys or key == "image":
            continue
        kwargs.append((key, _py_literal(val)))

    if "state_disabled" in props:
        state_src = '"disabled"' if props.get("state_disabled") else '"normal"'
        kwargs.append(("state", state_src))

    if font_keys and any(k in props for k in font_keys):
        kwargs.append(("font", _font_source(props)))

    image_path = props.get("image")
    if image_path:
        kwargs.append(("image", _image_source(props, image_path)))
        if "compound" not in props:
            kwargs.append(("compound", '"left"'))

    lines = [f"{var_name} = ctk.{node.widget_type}("]
    lines.append("    app,")
    for key, src in kwargs:
        lines.append(f"    {key}={src},")
    lines.append(")")

    x = _safe_int(props.get("x"), 0)
    y = _safe_int(props.get("y"), 0)
    lines.append(f"{var_name}.place(x={x}, y={y})")
    return lines


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
    iw = _safe_int(props.get("image_width"), 20)
    ih = _safe_int(props.get("image_height"), 20)
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
