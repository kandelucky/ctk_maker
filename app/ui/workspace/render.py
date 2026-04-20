"""Canvas rendering — document rect + builder grid + visibility mask.

Every frame of the workspace canvas is produced by ``Renderer.redraw``:

1. Clear the four drawing layers (``DOC_TAG``, ``GRID_TAG``,
   ``CHROME_TAG``, ``LAYOUT_OVERLAY_TAG``).
2. Walk ``_iter_render_order()`` (active document last) and per doc
   draw: document rectangle → builder grid → chrome → raise embedded
   widgets → semantic layout overlay.
3. Fix up the canvas scroll region to the stacked bounding box.
4. Run the visibility mask that hides any widget whose canvas centre
   lands inside a *later*-rendered document (tk's embedded widgets
   always draw above canvas drawing items, so we fake the mask).

Split out of the old monolithic ``workspace.py`` so rendering logic
lives in one focused module. ``Workspace._redraw_document`` is a
thin delegator to ``self.renderer.redraw()``.
"""

from __future__ import annotations

import tkinter as tk

from app.ui.workspace.chrome import CHROME_TAG
from app.ui.workspace.layout_overlay import LAYOUT_OVERLAY_TAG

# Canvas layout constants — the surrounding ``core.py`` imports
# these back so its ``_build_canvas`` can hand them to
# ``ZoomController``. External modules (``chrome.py``) import
# ``DOCUMENT_PADDING`` from here as well.
CANVAS_OUTSIDE_BG = "#141414"   # canvas background around documents
DOCUMENT_BG = "#1e1e1e"         # inside the document rectangle
DOCUMENT_BORDER = "#3c3c3c"
DOCUMENT_PADDING = 60           # gutter around document in canvas coords
GRID_SPACING = 20
GRID_DOT_COLOR = "#555555"
GRID_TAG = "grid_dot"
DOC_TAG = "document_bg"


class Renderer:
    """Per-workspace canvas drawing + visibility-mask controller.

    Owns nothing but the debounce handle for ``<Configure>`` events.
    Everything else (canvas, zoom, project, widget_views, sibling
    managers) is read through the workspace reference.
    """

    def __init__(self, workspace) -> None:
        self.workspace = workspace
        # Debounce id for the ``<Configure>``-triggered redraw so
        # resize bursts collapse into a single redraw pass.
        self._configure_after: str | None = None

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------
    @property
    def canvas(self) -> tk.Canvas:
        return self.workspace.canvas

    @property
    def zoom(self):
        return self.workspace.zoom

    @property
    def project(self):
        return self.workspace.project

    @property
    def widget_views(self) -> dict:
        return self.workspace.widget_views

    # ------------------------------------------------------------------
    # Main render pass
    # ------------------------------------------------------------------
    def redraw(self) -> None:
        """Repaint the canvas. Each document is drawn as a single
        stacked block (rect → grid → chrome → widgets → overlay) so
        multi-document forms sitting on top of each other stack
        consistently with tk's per-item Z order.
        """
        canvas = self.canvas
        canvas.delete(DOC_TAG)
        canvas.delete(GRID_TAG)
        canvas.delete(CHROME_TAG)
        canvas.delete(LAYOUT_OVERLAY_TAG)
        # Canvas coords use ``canvas_scale`` (user zoom × OS DPI) so
        # the doc rect expands to match CTk widgets' DPI-aware
        # physical size. Without the DPI factor, a 125 % display drew
        # the rect 20 % smaller than the widgets placed inside it.
        zoom = self.zoom.canvas_scale
        pad = DOCUMENT_PADDING
        max_right = pad
        max_bottom = pad
        chrome = self.workspace.chrome
        layout_overlay = self.workspace.layout_overlay
        for doc in self.iter_render_order():
            dw = int(doc.width * zoom)
            dh = int(doc.height * zoom)
            x1 = pad + int(doc.canvas_x * zoom)
            y1 = pad + int(doc.canvas_y * zoom)
            x2, y2 = x1 + dw, y1 + dh
            fill = self._doc_fill_color(doc)
            canvas.create_rectangle(
                x1, y1, x2, y2,
                fill=fill, outline=DOCUMENT_BORDER, width=1,
                tags=(DOC_TAG, f"doc_rect:{doc.id}"),
            )
            self._draw_grid_for_doc(doc, x1, y1, dw, dh, zoom)
            chrome.draw_for(doc)
            # Raise this document's top-level widgets so they sit on
            # top of its rect / grid / chrome AND above every earlier
            # document's stack.
            for node in list(doc.root_widgets):
                entry = self.widget_views.get(node.id)
                if entry is None:
                    continue
                _w, window_id = entry
                if window_id is None:
                    continue
                try:
                    canvas.tag_raise(window_id)
                except tk.TclError:
                    pass
            layout_overlay.draw_overlays_for_doc(doc, x1, y1, x2, y2)
            if x2 > max_right:
                max_right = x2
            if y2 > max_bottom:
                max_bottom = y2
        canvas.configure(
            scrollregion=(0, 0, max_right + pad, max_bottom + pad),
        )
        self.update_visibility_across_docs()

    def iter_render_order(self) -> list:
        """Documents sorted so the active one is drawn last — its
        rectangle and chrome end up on top of every inactive doc at
        overlap points.
        """
        docs = list(self.project.documents)
        active_id = self.project.active_document_id
        docs.sort(key=lambda d: 1 if d.id == active_id else 0)
        return docs

    def _doc_fill_color(self, doc) -> str:
        """Resolve the rectangle fill for a document. ``transparent``
        falls back to the canvas document background so the form
        still reads like a workspace; explicit hex colours render as
        their actual value for live preview of the exported
        ``fg_color`` setting.
        """
        value = doc.window_properties.get("fg_color")
        if isinstance(value, str) and value.startswith("#"):
            return value
        return DOCUMENT_BG

    # ------------------------------------------------------------------
    # Builder grid (dots / lines) per document
    # ------------------------------------------------------------------
    def _draw_grid_for_doc(
        self, doc, x1: int, y1: int, dw: int, dh: int, zoom: float,
    ) -> None:
        if zoom <= 0 or dw <= 0 or dh <= 0:
            return
        style = doc.window_properties.get("grid_style", "dots")
        if style == "none":
            return
        color = doc.window_properties.get("grid_color", GRID_DOT_COLOR)
        if not (isinstance(color, str) and color.startswith("#")):
            color = GRID_DOT_COLOR
        try:
            logical_spacing = int(
                doc.window_properties.get("grid_spacing", GRID_SPACING),
            )
        except (TypeError, ValueError):
            logical_spacing = GRID_SPACING
        logical_spacing = max(4, logical_spacing)
        spacing = max(4, int(logical_spacing * zoom))
        tag_set = (GRID_TAG, f"grid:{doc.id}")
        canvas = self.canvas
        if style == "lines":
            for x in range(x1, x1 + dw + 1, spacing):
                canvas.create_line(
                    x, y1, x, y1 + dh, fill=color, tags=tag_set,
                )
            for y in range(y1, y1 + dh + 1, spacing):
                canvas.create_line(
                    x1, y, x1 + dw, y, fill=color, tags=tag_set,
                )
        else:  # dots (default)
            for x in range(x1, x1 + dw + 1, spacing):
                for y in range(y1, y1 + dh + 1, spacing):
                    canvas.create_rectangle(
                        x, y, x + 1, y + 1,
                        outline="", fill=color, tags=tag_set,
                    )

    # ------------------------------------------------------------------
    # Visibility masking (tk two-layer workaround)
    # ------------------------------------------------------------------
    def update_visibility_across_docs(self) -> None:
        """Hide top-level widgets whose canvas centre falls inside a
        later-rendered document's rectangle. Works around tk's two-
        layer limit — embedded ``create_window`` items always render
        above drawing items like rectangles, so a widget in Main
        would otherwise punch through Dialog when Dialog is dragged
        on top of it. The mask is faked by flipping the widget item's
        ``state`` to ``hidden`` whenever it's covered.
        """
        if self._is_doc_drag_active():
            return
        doc_bboxes = self._compute_doc_bboxes()
        render_order = self.iter_render_order()
        # Render order is [inactive… , active]. A widget belonging
        # to index ``i`` is "behind" every doc at index > i, so only
        # those are candidates for covering it.
        for i, doc in enumerate(render_order):
            covering_bboxes = [
                doc_bboxes[other.id]
                for other in render_order[i + 1:]
            ]
            self._update_visibility_for_document(doc, covering_bboxes)

    def _is_doc_drag_active(self) -> bool:
        """Doc drag hide-mode intentionally hides every widget in the
        dragged document; flipping their state back to ``normal``
        here would defeat the optimisation on every motion event.
        Skip the whole pass — the release-time ``apply_all`` +
        visibility refresh resyncs state once the drag ends.
        """
        return bool(
            getattr(self.workspace, "_doc_drag_hide_active", False),
        )

    def _compute_doc_bboxes(
        self,
    ) -> dict[str, tuple[int, int, int, int]]:
        """Canvas-space rectangle for every document, keyed by doc id.
        Used to intersect each widget against every doc that sits
        above its owning doc in render order. Uses ``canvas_scale``
        so the bbox tracks the DPI-scaled rect drawn in ``redraw``.
        """
        zoom = self.zoom.canvas_scale
        pad = DOCUMENT_PADDING
        bboxes: dict[str, tuple[int, int, int, int]] = {}
        for doc in self.project.documents:
            dw = int(doc.width * zoom)
            dh = int(doc.height * zoom)
            x1 = pad + int(doc.canvas_x * zoom)
            y1 = pad + int(doc.canvas_y * zoom)
            bboxes[doc.id] = (x1, y1, x1 + dw, y1 + dh)
        return bboxes

    def _update_visibility_for_document(
        self, doc, covering_bboxes: list,
    ) -> None:
        """Flip ``state`` for every top-level widget in ``doc``. A
        widget hides if the user hid it OR its bbox intersects any
        doc that sits above ``doc`` in render order.
        """
        canvas = self.canvas
        for node in list(doc.root_widgets):
            entry = self.widget_views.get(node.id)
            if entry is None:
                continue
            widget, window_id = entry
            if window_id is None:
                continue
            widget_bbox = (
                self.workspace._widget_canvas_bbox(widget)
                if covering_bboxes else None
            )
            # When no covering docs exist (frontmost), skip the bbox
            # lookup entirely — ``_should_hide_widget`` only needs
            # ``node.visible`` in that case.
            if covering_bboxes and widget_bbox is None:
                continue
            hidden = self._should_hide_widget(
                node, widget_bbox, covering_bboxes,
            )
            try:
                canvas.itemconfigure(
                    window_id,
                    state="hidden" if hidden else "normal",
                )
            except tk.TclError:
                pass

    def _should_hide_widget(
        self, node, widget_bbox, covering_bboxes: list,
    ) -> bool:
        """Decide whether a widget's canvas item should be hidden.
        User visibility wins unconditionally; otherwise a single-pixel
        bbox overlap with any covering doc hides the widget (tk's
        two-layer limit workaround).
        """
        if not node.visible:
            return True
        if not covering_bboxes or widget_bbox is None:
            return False
        wx1, wy1, wx2, wy2 = widget_bbox
        return any(
            wx1 < x2 and wx2 > x1 and wy1 < y2 and wy2 > y1
            for (x1, y1, x2, y2) in covering_bboxes
        )

    # ------------------------------------------------------------------
    # Event hooks
    # ------------------------------------------------------------------
    def on_canvas_configure(self, _event=None) -> None:
        """Debounce bursts of ``<Configure>`` events — resize storms
        (scrollbars showing / hiding, window animations) should
        collapse into a single redraw pass.
        """
        if self._configure_after is not None:
            try:
                self.workspace.after_cancel(self._configure_after)
            except ValueError:
                pass
        self._configure_after = self.workspace.after(
            30, self._after_configure,
        )

    def _after_configure(self) -> None:
        self._configure_after = None
        self.redraw()

    def on_document_resized(self, *_args) -> None:
        self.redraw()
        self.zoom.apply_all()
