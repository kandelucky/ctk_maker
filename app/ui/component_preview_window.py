"""Read-only preview of a ``.ctkcomp`` component.

Renders the component's widget tree using each descriptor's
``create_widget`` + ``apply_state`` so the user sees roughly what
they'll be inserting before they commit. Variable bindings collapse
to their bundled default values — the preview is a visual snapshot,
not a live runtime.

Limitations (Phase D v1):
- Layout managers (vbox / hbox / grid) collapse to ``place``; nested
  layouts may render at unexpected positions.
- Image properties resolve only if the descriptor accepts a path /
  URL on its own; bundled-asset support arrives in Phase B2.
- CTkTabview children land in the default tab slot.
"""

from __future__ import annotations

import shutil
import tempfile
import tkinter as tk
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import customtkinter as ctk

from app.core.logger import log_error
from app.core.variables import is_var_token, parse_var_token
from app.io.component_assets import (
    extract_assets_to_folder, rewrite_bundle_tokens_to_paths,
)
from app.widgets.registry import get_descriptor

if TYPE_CHECKING:
    pass


class ComponentPreviewWindow(ctk.CTkToplevel):
    def __init__(self, parent, payload: dict, component_path: Path | None = None):
        super().__init__(parent)
        name = payload.get("name") or "(component)"
        self.title(f"{name} — Preview")
        self.transient(parent)

        # Bundle tokens point at archive-relative names that don't
        # resolve on disk, so for previews we extract to a temp dir
        # and rewrite the tokens in a copy of the node tree. The temp
        # dir is cleaned up when the preview window closes.
        self._temp_assets_dir: Path | None = None
        if component_path is not None:
            try:
                tmp = Path(tempfile.mkdtemp(prefix="ctkcomp_preview_"))
                with zipfile.ZipFile(component_path, "r") as zf:
                    extracted = extract_assets_to_folder(zf, tmp)
                if extracted:
                    self._temp_assets_dir = tmp
                    rewrite_bundle_tokens_to_paths(
                        payload.get("nodes", []), extracted,
                    )
                else:
                    shutil.rmtree(tmp, ignore_errors=True)
            except (OSError, zipfile.BadZipFile):
                log_error(f"preview asset extract {component_path}")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Map var-uuid → default literal so var-tokens in properties
        # render as plain values inside the preview.
        var_defaults: dict[str, str] = {
            v.get("id", ""): str(v.get("default", "") or "")
            for v in payload.get("variables", [])
        }

        nodes = payload.get("nodes", [])
        # Compute the actual bounding box of root nodes so the preview
        # surface can be sized to fit + every root gets shifted so the
        # bbox top-left lands at (margin, margin) inside the surface.
        # The saved ``view_size`` is just (max_x, max_y) and ignores
        # the leftmost / topmost offset, which made widgets that were
        # placed deep into a canvas render off-screen here.
        min_x, min_y, max_x, max_y = self._bbox(nodes)
        bbox_w = max(max_x - min_x, 100)
        bbox_h = max(max_y - min_y, 60)
        margin = 28
        # Toplevel chrome eats ~30px vertically on Windows; account
        # for that on top of the surface margin so the bottom widget
        # row isn't clipped behind the window edge.
        title_chrome = 32
        self.geometry(
            f"{bbox_w + margin * 2}x{bbox_h + margin * 2 + title_chrome}"
        )
        self.minsize(220, 160)

        surface = ctk.CTkFrame(
            self, fg_color="#1e1e1e", corner_radius=0,
            width=bbox_w + margin * 2, height=bbox_h + margin * 2,
        )
        surface.pack(fill="both", expand=True, padx=8, pady=8)
        surface.pack_propagate(False)

        offset = (margin - min_x, margin - min_y)
        for raw in nodes:
            self._render(surface, raw, var_defaults, offset)

        self.bind("<Escape>", lambda _e: self._on_close())
        self.after(100, self._center_on_parent)

    def _on_close(self) -> None:
        if self._temp_assets_dir is not None:
            shutil.rmtree(self._temp_assets_dir, ignore_errors=True)
            self._temp_assets_dir = None
        self.destroy()

    @staticmethod
    def _bbox(nodes: list[dict]) -> tuple[int, int, int, int]:
        if not nodes:
            return (0, 0, 0, 0)
        min_x = min_y = 10 ** 9
        max_x = max_y = 0
        for n in nodes:
            props = n.get("properties", {})
            x = int(props.get("x", 0) or 0)
            y = int(props.get("y", 0) or 0)
            w = int(props.get("width", 0) or 0)
            h = int(props.get("height", 0) or 0)
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + w)
            max_y = max(max_y, y + h)
        return (min_x, min_y, max_x, max_y)

    def _render(
        self,
        parent,
        raw_node: dict,
        var_defaults: dict[str, str],
        offset: tuple[int, int] = (0, 0),
    ) -> object | None:
        wtype = raw_node.get("widget_type", "")
        descriptor = get_descriptor(wtype)
        if descriptor is None:
            return None
        properties = self._cleaned_properties(
            raw_node.get("properties", {}), var_defaults,
        )
        try:
            widget = descriptor.create_widget(parent, properties)
        except Exception:
            log_error(f"preview create {wtype}")
            return None
        try:
            descriptor.apply_state(widget, properties)
        except Exception:
            pass
        # CTk widgets reject ``width=`` / ``height=`` on .place() —
        # apply the dimensions through configure() instead.
        w_val = properties.get("width")
        h_val = properties.get("height")
        size_kwargs: dict = {}
        if w_val:
            size_kwargs["width"] = w_val
        if h_val:
            size_kwargs["height"] = h_val
        if size_kwargs:
            try:
                widget.configure(**size_kwargs)
            except Exception:
                pass
        x = int(properties.get("x", 0) or 0) + offset[0]
        y = int(properties.get("y", 0) or 0) + offset[1]
        try:
            widget.place(x=x, y=y)
        except Exception:
            pass
        # Descendants live in the parent widget's own coord space, so
        # the bbox-shift offset stops at this level.
        if descriptor.is_container and raw_node.get("children"):
            try:
                child_master = descriptor.child_master(widget, None)
            except Exception:
                child_master = widget
            for child in raw_node.get("children", []):
                self._render(child_master, child, var_defaults)
        return widget

    def _cleaned_properties(
        self,
        raw_props: dict,
        var_defaults: dict[str, str],
    ) -> dict:
        cleaned: dict = {}
        for key, value in raw_props.items():
            if is_var_token(value):
                var_id = parse_var_token(value) or ""
                cleaned[key] = var_defaults.get(var_id, "")
                continue
            cleaned[key] = value
        return cleaned

    def _center_on_parent(self) -> None:
        self.update_idletasks()
        parent = self.master
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
        except tk.TclError:
            return
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
