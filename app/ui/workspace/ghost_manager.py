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

Persistence: the desaturated PIL is cached on ``Document._cached
_ghost_pil`` and base64-PNG'd into the .ctkproj at save time. Next
load reads it back; ``freeze_from_cache`` places it without ever
touching the screen so the user sees the exact frozen image they
left behind instead of whatever pixels happened to sit at those
coords during startup.

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
        """User-toggle path — captures fresh from the live widgets,
        updates the persisted cache, then places the ghost image."""
        if doc is None or doc.id in self.ghosts:
            return
        photo, base_pil = self._capture(doc)
        if photo is None:
            return
        # Stash the desaturated PIL on the Document so the next save
        # serialises it into the .ctkproj. Survives unfreeze too —
        # toggling off and on cheaply reuses the same image (until
        # the user re-toggles to refresh).
        doc._cached_ghost_pil = base_pil
        self._destroy_widgets(doc)
        self._place_ghost(doc, photo, base_pil)

    def freeze_from_cache(self, doc) -> None:
        """Load path — places the ghost image from ``doc._cached_ghost
        _pil`` without touching the screen. Falls through to a live
        ``freeze`` only when no cached image exists (legacy .ctkproj
        files that predate screenshot persistence)."""
        if doc is None or doc.id in self.ghosts:
            return
        cached = getattr(doc, "_cached_ghost_pil", None)
        if cached is None:
            self.freeze(doc)
            return
        zoom = self.workspace.zoom.canvas_scale
        target_w = max(1, int(doc.width * zoom))
        target_h = max(1, int(doc.height * zoom))
        try:
            resized = cached.resize(
                (target_w, target_h), Image.BILINEAR,
            )
        except Exception:
            # Corrupt cached image — give up cleanly, fall through
            # to live capture so the user at least sees something.
            self.freeze(doc)
            return
        photo = ImageTk.PhotoImage(resized)
        self._destroy_widgets(doc)
        self._place_ghost(doc, photo, cached)

    def _place_ghost(self, doc, photo, base_pil) -> None:
        """Common tail of ``freeze`` / ``freeze_from_cache`` — places
        the image item on the canvas, wires its click + hover bindings,
        and registers the entry in ``self.ghosts``.
        """
        zoom = self.workspace.zoom.canvas_scale
        pad = DOCUMENT_PADDING
        x1 = pad + int(doc.canvas_x * zoom)
        y1 = pad + int(doc.canvas_y * zoom)
        ghost_tag = f"{GHOST_TAG_PREFIX}{doc.id}"
        image_id = self.canvas.create_image(
            x1, y1, image=photo, anchor="nw", tags=(ghost_tag,),
        )
        self.canvas.tag_raise(ghost_tag)
        # Click-anywhere-on-screenshot unghost — the statusbar is the
        # primary toggle, this just makes the screenshot itself
        # behave as a wake button so users who reach for the visible
        # content first aren't forced to find the strip.
        self.canvas.tag_bind(
            ghost_tag, "<Button-1>",
            lambda _e, did=doc.id: self._on_ghost_image_click(did),
        )
        self.canvas.tag_bind(
            ghost_tag, "<Enter>",
            lambda _e: self._set_canvas_cursor("hand2"),
        )
        self.canvas.tag_bind(
            ghost_tag, "<Leave>",
            lambda _e: self._set_canvas_cursor(""),
        )
        self.ghosts[doc.id] = {
            "image_id": image_id,
            "photo": photo,
            "base_pil": base_pil,
            "base_zoom": zoom,
        }

    def _on_ghost_image_click(self, doc_id: str) -> str:
        """Two-step interaction. Unghosting rebuilds every live widget
        in the doc, so a stray click while panning around shouldn't
        trigger it. First click on a non-focused ghost just focuses;
        the user has to click the same ghost again (now active) to
        actually restore live widgets.
        """
        if self.project.active_document_id != doc_id:
            self.project.set_active_document(doc_id)
        else:
            self.project.set_document_ghost(doc_id, False)
        return "break"

    def _set_canvas_cursor(self, cursor: str) -> None:
        try:
            self.canvas.configure(cursor=cursor)
        except tk.TclError:
            pass

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

    def purge(self, doc_id: str) -> None:
        """Drop the ghost image item + entry for a doc that's been
        deleted. ``unfreeze`` rebuilds widgets and assumes the doc
        still exists; deletion has no doc to rebuild into and we
        only want to peel the screenshot off the canvas.
        """
        entry = self.ghosts.pop(doc_id, None)
        if entry is None:
            return
        try:
            self.canvas.delete(entry["image_id"])
        except tk.TclError:
            pass

    def clear_all(self) -> None:
        """Wipe every ghost image + state entry. Called before a
        project load replaces ``project.documents`` wholesale — the
        loader bypasses ``document_removed`` (to avoid trashing
        behavior .py files via ``send2trash`` and other per-doc side
        effects), so the canvas-side ``ghost:<id>`` items would
        otherwise survive into the next project and overlay its docs.
        """
        for entry in self.ghosts.values():
            try:
                self.canvas.delete(entry["image_id"])
            except tk.TclError:
                pass
        self.ghosts.clear()

    def is_ghosted(self, doc_id: str) -> bool:
        return doc_id in self.ghosts

    def freeze_pending(self) -> None:
        """Apply ``_pending_ghost`` flags set by the loader. Called
        once after ``load_project``. The active doc is skipped so the
        user always lands on a live form.

        Uses ``freeze_from_cache`` instead of routing through
        ``set_document_ghost`` — bus path defaults to live capture,
        which races the startup paint and captures whatever is on the
        screen at the moment (splash, partially-rendered UI, IDE
        underneath). The persisted base64 PNG already carries the
        exact image the user left, so we use it verbatim and skip
        the screen-grab entirely.

        The event bus is deliberately NOT pinged from here either —
        ``document_ghost_changed`` triggers an auto-save subscriber on
        main_window, which would re-write the just-loaded project
        once per restored ghost. Instead we redraw the canvas once
        at the end so the per-doc statusbar repaints in its new
        colour without forcing N saves.
        """
        active_id = self.project.active_document_id
        any_frozen = False
        for doc in self.project.documents:
            pending = getattr(doc, "_pending_ghost", False)
            if not pending:
                continue
            doc._pending_ghost = False
            if doc.id == active_id:
                continue
            doc.ghosted = True
            self.freeze_from_cache(doc)
            any_frozen = True
        if any_frozen:
            try:
                self.workspace._redraw_document()
            except AttributeError:
                pass

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
