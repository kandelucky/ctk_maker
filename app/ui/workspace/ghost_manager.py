"""Ghost-mode renderer — screenshot inactive docs onto the canvas.

When a doc enters ghost state the manager:
1. Scrolls the doc into the viewport so PIL.ImageGrab captures real
   pixels (off-screen pixels grab as desktop / black).
2. Pulls the live widget rectangle as a PIL image.
3. Runs the desaturate filter (Variant C — colour × 0.4 + slight
   dim) so the eye reads the doc as inactive while preserving its
   content shape.
4. Destroys the doc's live widgets via the workspace lifecycle.
5. Places the filtered image as a canvas item at the doc's logical
   rect, raised above any chrome / grid drawn underneath.

Zoom keeps the screenshot in sync via PIL.Image.resize → fresh
PhotoImage. Pan uses Tk's native viewport shift — no per-image
work needed.
"""

from __future__ import annotations

import tkinter as tk

from PIL import Image, ImageEnhance, ImageGrab, ImageTk

from app.ui.workspace.render import DOCUMENT_PADDING


GHOST_TAG_PREFIX = "ghost:"


def _desaturate(img: Image.Image) -> Image.Image:
    """Variant C — colour × 0.4 + brightness × 0.85. Reads as
    "drained" without losing the layout's shape."""
    img = img.convert("RGB")
    img = ImageEnhance.Color(img).enhance(0.4)
    return ImageEnhance.Brightness(img).enhance(0.85)


class GhostManager:
    """Per-workspace ghost-image controller. One instance per
    Workspace; tracks ``doc_id → {image_id, photo, base_pil,
    base_zoom}`` for every currently-frozen doc."""

    def __init__(self, workspace) -> None:
        self.workspace = workspace
        self.canvas = workspace.canvas
        self.project = workspace.project
        self.ghosts: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def freeze(self, doc) -> None:
        """Capture screenshot, destroy widgets, place ghost image."""
        if doc is None or doc.id in self.ghosts:
            return
        photo, base_pil = self._capture(doc)
        if photo is None:
            return
        self._destroy_widgets(doc)
        zoom = self.workspace.zoom.canvas_scale
        pad = DOCUMENT_PADDING
        x1 = pad + int(doc.canvas_x * zoom)
        y1 = pad + int(doc.canvas_y * zoom)
        ghost_tag = f"{GHOST_TAG_PREFIX}{doc.id}"
        image_id = self.canvas.create_image(
            x1, y1, image=photo, anchor="nw", tags=(ghost_tag,),
        )
        self.canvas.tag_raise(ghost_tag)
        self.ghosts[doc.id] = {
            "image_id": image_id,
            "photo": photo,
            "base_pil": base_pil,
            "base_zoom": zoom,
        }

    def unfreeze(self, doc) -> None:
        """Drop ghost image, rebuild live widgets."""
        if doc is None:
            return
        entry = self.ghosts.pop(doc.id, None)
        if entry is not None:
            try:
                self.canvas.delete(entry["image_id"])
            except tk.TclError:
                pass
        # Re-create widget subtrees via lifecycle.
        lifecycle = self.workspace.lifecycle
        for node in list(doc.root_widgets):
            lifecycle.create_widget_subtree(node)

    def is_ghosted(self, doc_id: str) -> bool:
        return doc_id in self.ghosts

    def freeze_pending(self) -> None:
        """Apply ``_pending_ghost`` flags set by the loader. Called
        once after ``load_project`` so widgets are built and visible
        before we screenshot them. The active doc is skipped so the
        user always lands on a live form."""
        active_id = self.project.active_document_id
        for doc in self.project.documents:
            pending = getattr(doc, "_pending_ghost", False)
            if not pending:
                continue
            doc._pending_ghost = False
            if doc.id == active_id:
                continue
            self.project.set_document_ghost(doc.id, True)

    # ------------------------------------------------------------------
    # Zoom hook — called from ZoomController via workspace
    # ------------------------------------------------------------------
    def on_zoom_changed(self) -> None:
        """Rescale every ghost image to match the new canvas scale."""
        if not self.ghosts:
            return
        zoom = self.workspace.zoom.canvas_scale
        pad = DOCUMENT_PADDING
        for doc_id, entry in list(self.ghosts.items()):
            doc = self.project.get_document(doc_id)
            if doc is None:
                continue
            new_w = max(1, int(doc.width * zoom))
            new_h = max(1, int(doc.height * zoom))
            try:
                resized = entry["base_pil"].resize(
                    (new_w, new_h), Image.BILINEAR,
                )
                photo = ImageTk.PhotoImage(resized)
                self.canvas.itemconfigure(
                    entry["image_id"], image=photo,
                )
                self.canvas.coords(
                    entry["image_id"],
                    pad + int(doc.canvas_x * zoom),
                    pad + int(doc.canvas_y * zoom),
                )
                entry["photo"] = photo
            except tk.TclError:
                pass

    def reposition_doc(self, doc) -> None:
        """Move the ghost image to the doc's current canvas_x/y —
        called when a doc is dragged or its position changes
        independently of zoom."""
        entry = self.ghosts.get(doc.id)
        if entry is None:
            return
        zoom = self.workspace.zoom.canvas_scale
        pad = DOCUMENT_PADDING
        try:
            self.canvas.coords(
                entry["image_id"],
                pad + int(doc.canvas_x * zoom),
                pad + int(doc.canvas_y * zoom),
            )
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _capture(self, doc) -> tuple[ImageTk.PhotoImage | None,
                                      Image.Image | None]:
        """Bring the doc into viewport, grab its rect, run filter."""
        zoom = self.workspace.zoom.canvas_scale
        pad = DOCUMENT_PADDING
        x1 = pad + int(doc.canvas_x * zoom)
        y1 = pad + int(doc.canvas_y * zoom)
        dw = max(1, int(doc.width * zoom))
        dh = max(1, int(doc.height * zoom))
        # Force the doc into the viewport so screen-grab captures
        # real pixels. ``focus_document`` centers it; idletasks +
        # update flushes the redraw before the grab.
        self.workspace.focus_document(doc.id)
        self.canvas.update_idletasks()
        self.workspace.update()
        sx = self.canvas.winfo_rootx() + (
            x1 - int(self.canvas.canvasx(0))
        )
        sy = self.canvas.winfo_rooty() + (
            y1 - int(self.canvas.canvasy(0))
        )
        try:
            pil = ImageGrab.grab(
                bbox=(sx, sy, sx + dw, sy + dh),
            )
        except Exception:
            return None, None
        filtered = _desaturate(pil)
        photo = ImageTk.PhotoImage(filtered)
        return photo, filtered

    def _destroy_widgets(self, doc) -> None:
        lifecycle = self.workspace.lifecycle
        for node in list(doc.root_widgets):
            lifecycle.destroy_widget_subtree(node)
