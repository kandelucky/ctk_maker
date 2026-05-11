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
from app.ui.system_fonts import ui_font

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

# Ghost statusbar — strip rendered directly below every doc's
# bottom edge. Always visible, click toggles ghost mode. Colour
# is intentionally loud when ON so the user can spot ghosted
# windows at a glance across a busy canvas.
GHOST_STATUSBAR_HEIGHT = 20
GHOST_STATUSBAR_OFF_BG = "#2a2a2c"
GHOST_STATUSBAR_OFF_FG = "#9aa0a6"
GHOST_STATUSBAR_OFF_HOVER = "#34343a"
GHOST_STATUSBAR_ON_BG = "#b8682c"
GHOST_STATUSBAR_ON_FG = "#ffffff"
GHOST_STATUSBAR_ON_HOVER = "#d48a4c"
GHOST_STATUSBAR_TAG = "ghost_statusbar"
GHOST_STATUSBAR_TOOLTIP_DELAY_MS = 450


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
        # Statusbar tooltip state — single Toplevel reused across docs,
        # debounced by ``GHOST_STATUSBAR_TOOLTIP_DELAY_MS``.
        self._sb_tooltip: tk.Toplevel | None = None
        self._sb_tooltip_after: str | None = None

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
            # Ghost images for this doc need to ride above the doc
            # rect / grid / chrome that we just (re)drew — otherwise
            # the body fill paints over the screenshot.
            try:
                canvas.tag_raise(f"ghost:{doc.id}")
            except tk.TclError:
                pass
            # Ghost statusbar — sits directly below the doc rect, drawn
            # after the ghost image so it always reads as the topmost
            # control surface (the statusbar is the primary toggle).
            self._draw_ghost_statusbar(doc, x1, x2, y2)
            sb_bottom = y2 + GHOST_STATUSBAR_HEIGHT
            if x2 > max_right:
                max_right = x2
            if sb_bottom > max_bottom:
                max_bottom = sb_bottom
        canvas.configure(
            scrollregion=(0, 0, max_right + pad, max_bottom + pad),
        )
        self.update_visibility_across_docs()

    def iter_render_order(self) -> list:
        """Documents sorted so the active one is drawn last — its
        rectangle and chrome end up on top of every inactive doc at
        overlap points. Collapsed documents are excluded — they are
        drawn separately as bottom-left tabs.
        """
        docs = [d for d in self.project.documents if not d.collapsed]
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
        # Global Preferences overrides win over per-document Window
        # Settings — set the grid once in Settings → Workspace and it
        # applies to every document in every project. Falls back to
        # the doc's own properties when settings.json is silent.
        try:
            from app.core.settings import load_settings
            global_grid = load_settings()
        except Exception:
            global_grid = {}
        style = (
            global_grid.get("grid_style")
            or doc.window_properties.get("grid_style", "dots")
        )
        if style == "none":
            return
        color = (
            global_grid.get("grid_color")
            or doc.window_properties.get("grid_color", GRID_DOT_COLOR)
        )
        if not (isinstance(color, str) and color.startswith("#")):
            color = GRID_DOT_COLOR
        try:
            logical_spacing = int(
                global_grid.get("grid_spacing")
                or doc.window_properties.get("grid_spacing", GRID_SPACING),
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
            if doc.collapsed:
                continue
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
    # Ghost statusbar (per-doc bottom strip + click toggle + tooltip)
    # ------------------------------------------------------------------
    def _draw_ghost_statusbar(
        self, doc, x1: int, x2: int, y2: int,
    ) -> None:
        """Paint the ``● Live`` / ``● GHOST`` strip below ``doc``.

        The strip occupies a constant vertical slot just under the
        document rect (so it doesn't fight any embedded widgets) and
        carries three pieces of state:

        * background colour — bright carrot when ghosted, neutral grey
          when live, so a single glance across the canvas tells the
          user which docs are paying widget-cost and which aren't.
        * inline label — explicit verb (``click to ghost`` /
          ``click to restore``) instead of an opaque icon.
        * tooltip — surfaces the *why* on hover (performance gain +
          where the live widgets go).

        Click flips ``doc.ghosted`` through ``set_document_ghost`` —
        same entry point the old chrome icon used.
        """
        canvas = self.canvas
        is_ghost = doc.ghosted
        bg = (
            GHOST_STATUSBAR_ON_BG if is_ghost
            else GHOST_STATUSBAR_OFF_BG
        )
        fg = (
            GHOST_STATUSBAR_ON_FG if is_ghost
            else GHOST_STATUSBAR_OFF_FG
        )
        label = (
            "● GHOST  —  click to restore live widgets" if is_ghost
            else "● Live  —  click to ghost (screenshot mode)"
        )
        sb_top = y2
        sb_bot = y2 + GHOST_STATUSBAR_HEIGHT
        sb_tag = f"ghost_statusbar:{doc.id}"
        # ``DOC_TAG`` so the next redraw's blanket delete clears the
        # strip too; ``chrome_doc:{doc.id}`` so chrome-drag's per-doc
        # ``canvas.move`` slides the statusbar along with the title.
        item_tags = (
            DOC_TAG, GHOST_STATUSBAR_TAG, sb_tag,
            f"chrome_doc:{doc.id}",
        )
        canvas.create_rectangle(
            x1, sb_top, x2, sb_bot,
            fill=bg, outline=bg, width=0,
            tags=item_tags,
        )
        canvas.create_text(
            (x1 + x2) // 2, (sb_top + sb_bot) // 2,
            text=label, fill=fg,
            font=ui_font(9, "bold" if is_ghost else "normal"),
            tags=item_tags,
        )
        canvas.tag_bind(
            sb_tag, "<Button-1>",
            lambda _e, did=doc.id: self._on_statusbar_click(did),
        )
        canvas.tag_bind(
            sb_tag, "<Enter>",
            lambda e, did=doc.id, on=is_ghost:
                self._on_statusbar_enter(e, did, on),
        )
        canvas.tag_bind(
            sb_tag, "<Leave>",
            lambda _e: self._on_statusbar_leave(),
        )

    def _on_statusbar_click(self, doc_id: str) -> str:
        """Same two-step rule as the ghost-image click: unghosting is
        expensive (full widget rebuild) so a click on a non-focused
        ghost just focuses. Live → ghost stays one-click — that path
        is cheap and is the action the user typically wants.
        """
        doc = self.project.get_document(doc_id)
        if doc is None:
            return "break"
        self._cancel_statusbar_tooltip()
        if doc.ghosted and self.project.active_document_id != doc_id:
            self.project.set_active_document(doc_id)
        else:
            self.project.set_document_ghost(doc_id, not doc.ghosted)
        return "break"

    def _on_statusbar_enter(
        self, event, doc_id: str, is_ghost: bool,
    ) -> None:
        try:
            self.canvas.configure(cursor="hand2")
        except tk.TclError:
            pass
        # Visual hover feedback — brighten the fill so it reads as
        # interactive. Item tag covers both rect and text.
        hover_bg = (
            GHOST_STATUSBAR_ON_HOVER if is_ghost
            else GHOST_STATUSBAR_OFF_HOVER
        )
        sb_tag = f"ghost_statusbar:{doc_id}"
        try:
            # itemconfigure(fill=) only affects rect items; text items
            # interpret ``fill`` as foreground — pass both via the per-
            # item type filter to avoid clobbering the label colour.
            for item_id in self.canvas.find_withtag(sb_tag):
                if self.canvas.type(item_id) == "rectangle":
                    self.canvas.itemconfigure(
                        item_id, fill=hover_bg, outline=hover_bg,
                    )
        except tk.TclError:
            pass
        self._schedule_statusbar_tooltip(event, is_ghost)

    def _on_statusbar_leave(self) -> None:
        try:
            self.canvas.configure(cursor="")
        except tk.TclError:
            pass
        # Tooltip cancel + force redraw to restore the resting fill —
        # cheaper than reading the doc back and itemconfiguring the
        # exact pair of items.
        self._cancel_statusbar_tooltip()
        self.redraw()

    def _schedule_statusbar_tooltip(
        self, event, is_ghost: bool,
    ) -> None:
        self._cancel_statusbar_tooltip()
        x_root = event.x_root
        y_root = event.y_root
        self._sb_tooltip_after = self.workspace.after(
            GHOST_STATUSBAR_TOOLTIP_DELAY_MS,
            lambda: self._show_statusbar_tooltip(
                x_root, y_root, is_ghost,
            ),
        )

    def _show_statusbar_tooltip(
        self, x_root: int, y_root: int, is_ghost: bool,
    ) -> None:
        self._sb_tooltip_after = None
        if is_ghost:
            text = (
                "Window is currently a screenshot — live widgets are "
                "destroyed.\nClick to rebuild the live widgets for "
                "editing."
            )
        else:
            text = (
                "Switch this window to Ghost mode.\nLive widgets are "
                "replaced by a desaturated screenshot — zoom and pan "
                "stay smooth even with many windows on the canvas."
            )
        tip = tk.Toplevel(self.workspace)
        tip.wm_overrideredirect(True)
        try:
            tip.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        tip.configure(bg="#3c3c3c")
        label = tk.Label(
            tip, text=text,
            bg="#252526", fg="#cccccc",
            font=ui_font(9),
            padx=8, pady=5, bd=0, justify="left",
        )
        label.pack(padx=1, pady=1)
        tip.update_idletasks()
        th = tip.winfo_height()
        tip.geometry(f"+{x_root + 12}+{y_root - th - 8}")
        self._sb_tooltip = tip

    def _cancel_statusbar_tooltip(self) -> None:
        if self._sb_tooltip_after is not None:
            try:
                self.workspace.after_cancel(self._sb_tooltip_after)
            except (ValueError, tk.TclError):
                pass
            self._sb_tooltip_after = None
        if self._sb_tooltip is not None:
            try:
                self._sb_tooltip.destroy()
            except tk.TclError:
                pass
            self._sb_tooltip = None

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
