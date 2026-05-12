"""Small pure helpers used across the export pipeline.

No module-level state, no project dependencies — safe to call from
anywhere in the package.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.document import Document


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_")
    return value.lower()


def _class_name_for(
    doc: "Document", index: int, used: set[str],
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


def _aspect_corrected_size(
    props: dict, image_path: str, iw: int, ih: int,
) -> tuple[int, int]:
    """Contain-fit ``(iw, ih)`` against the image's native dimensions
    when ``preserve_aspect=True``. Scales by the smaller side so the
    icon fits inside the (image_width, image_height) box with native
    aspect intact. Mirrors the runtime ``_build_image`` rule so the
    exported code matches what the designer sees, regardless of what
    ``image_height`` was stored in the project file. Returns the
    inputs unchanged when the flag is off or the file can't be read.
    """
    if not props.get("preserve_aspect"):
        return iw, ih
    try:
        from PIL import Image as PILImage
        with PILImage.open(image_path) as probe:
            nw, nh = probe.size
        if nw > 0 and nh > 0:
            scale = min(iw / nw, ih / nh)
            return (
                max(1, int(round(nw * scale))),
                max(1, int(round(nh * scale))),
            )
    except Exception:
        pass
    return iw, ih


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
