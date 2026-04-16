"""Layout-manager helpers + semantic canvas overlays.

Two concerns live together here because they share context — the
same Stage 3 WYSIWYG pipeline that picks a tk geometry manager
(``pack`` / ``place`` / ``grid``) for a child also decides whether
to draw a ``[vbox]`` badge or dashed grid lines on the canvas:

1. **Module-level functions** (no workspace needed):
    - ``_strip_layout_keys``    — filter out node-only layout keys
      so CTk constructors / ``configure`` calls never see them.
    - ``_child_manager_kwargs`` — pick the manager for a child given
      its parent's ``layout_type``.
    - ``_stretch_to_pack_kwargs`` — translate ``fixed/fill/grow`` to
      tk pack fill/expand kwargs.
    - ``_forget_current_manager`` — cross-manager safe forget.

2. **``LayoutOverlayManager``** (owns Workspace ref):
    - Draws badges + grid-cell overlays into the workspace canvas.
    - Re-applies child managers when ``layout_type`` changes.

Split out of the old monolithic ``workspace.py`` to keep Stage 3
logic in one focused module. Core ``Workspace`` holds a single
instance on ``self.layout_overlay`` and delegates to it.
"""

from __future__ import annotations

import tkinter as tk

from app.widgets.layout_schema import (
    LAYOUT_DEFAULTS,
    LAYOUT_NODE_ONLY_KEYS,
    normalise_layout_type,
    pack_side_for,
)
from app.widgets.registry import get_descriptor

# Layout-manager overlays — semantic hints (grid lines on grid
# containers, "[pack]"/"[grid]" badges) drawn on top of widgets.
# Independent from the builder's dot/line GRID_TAG.
LAYOUT_OVERLAY_TAG = "layout_overlay"
LAYOUT_BADGE_FG = "#7a7a7a"
LAYOUT_GRID_LINE = "#3d4954"
LAYOUT_OVERLAY_TRIGGERS = frozenset({
    "layout_type",
    "grid_row", "grid_column",
    "grid_rowspan", "grid_columnspan",
})


# ----------------------------------------------------------------------
# Module-level helpers — pure functions, no workspace reference
# ----------------------------------------------------------------------
def _strip_layout_keys(properties: dict) -> dict:
    """Drop layout_type / pack_* / grid_* / stretch before handing
    properties to a CTk widget. Those keys live on the node only —
    they drive the code exporter and the Properties panel, never CTk
    itself.
    """
    return {
        k: v for k, v in properties.items()
        if k not in LAYOUT_NODE_ONLY_KEYS
    }


def _stretch_to_pack_kwargs(stretch: str, layout: str) -> dict:
    """Translate a child's ``stretch`` hint into tk pack fill/expand.
    ``fill`` stretches across the layout's cross-axis (horizontal in
    vbox, vertical in hbox); ``grow`` fills both axes and asks pack
    for any extra space in the container.
    """
    if stretch == "fill":
        return {"fill": "y" if layout == "hbox" else "x"}
    if stretch == "grow":
        return {"fill": "both", "expand": True}
    return {}


def _child_manager_kwargs(
    parent_node, child_props: dict, zoom: float = 1.0,
) -> tuple[str, dict]:
    """Pick the tk geometry manager + its kwargs for a child whose
    parent is ``parent_node``. Returns ``(manager_name, kwargs)``
    with manager ∈ ``place`` / ``pack``. Grid support lands in
    Stage 3.2 — grid parents fall back to ``place`` so grid children
    keep rendering where x/y put them even though the exporter emits
    real ``.grid()`` calls.

    vbox / hbox direction comes from the parent; per-child padx/pady
    are derived from the parent's ``layout_spacing`` (half on each
    side so consecutive siblings end up one full spacing apart).
    The child's only layout knob is ``stretch`` (fixed / fill / grow).
    """
    parent_layout = "place"
    parent_props: dict = {}
    if parent_node is not None:
        parent_props = parent_node.properties
        parent_layout = parent_props.get("layout_type", "place")
    layout = normalise_layout_type(parent_layout)
    side = pack_side_for(layout)
    if side is not None:
        kwargs: dict = {"side": side}
        kwargs.update(
            _stretch_to_pack_kwargs(
                str(child_props.get("stretch", LAYOUT_DEFAULTS["stretch"])),
                layout,
            ),
        )
        try:
            spacing = int(parent_props.get("layout_spacing", 0) or 0)
        except (TypeError, ValueError):
            spacing = 0
        if spacing:
            pad = max(0, int(spacing // 2 * zoom))
            if pad:
                # pack pads both sides, so half-spacing per sibling
                # yields ``spacing`` between adjacent widgets.
                if layout == "hbox":
                    kwargs["padx"] = pad
                else:
                    kwargs["pady"] = pad
        return "pack", kwargs
    # Fall-through: place (both the legacy mode and the pre-Stage-3.2
    # grid stand-in).
    return "place", {}


def _forget_current_manager(widget) -> None:
    """tk raises ``TclError`` if you mix geometry managers in one
    container, so call the right ``*_forget`` before re-applying.
    """
    try:
        current = widget.winfo_manager()
    except tk.TclError:
        return
    if current == "pack":
        try:
            widget.pack_forget()
        except tk.TclError:
            pass
    elif current == "grid":
        try:
            widget.grid_forget()
        except tk.TclError:
            pass
    elif current == "place":
        try:
            widget.place_forget()
        except tk.TclError:
            pass


# ----------------------------------------------------------------------
# LayoutOverlayManager — stateful, holds a Workspace ref
# ----------------------------------------------------------------------
class LayoutOverlayManager:
    """Per-workspace manager for Stage 3 WYSIWYG pack / grid wiring
    + semantic overlay rendering.

    All state lives on the parent Workspace (canvas, zoom, project,
    widget_views, _anchor_views); this class only groups the logic
    that operates on those. Instantiated once per Workspace, stored
    as ``workspace.layout_overlay``.
    """

    def __init__(self, workspace) -> None:
        self.workspace = workspace

    # ------------------------------------------------------------------
    # Convenience accessors — less noise than ``self.workspace.xxx``
    # at each call site, while keeping the workspace as the single
    # source of truth.
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

    @property
    def anchor_views(self) -> dict:
        return self.workspace._anchor_views

    # ------------------------------------------------------------------
    # Overlay drawing
    # ------------------------------------------------------------------
    def draw_overlays_for_doc(
        self, doc, dx1: int, dy1: int, dx2: int, dy2: int,
    ) -> None:
        """Per-doc semantic overlay: dashed grid-cell lines on every
        container whose ``layout_type == "grid"`` plus a small badge
        on every non-default container. The Window's badge is folded
        into the chrome title strip — only Frame-level containers get
        a separate badge here.
        """
        doc_layout = normalise_layout_type(
            doc.window_properties.get("layout_type", "place"),
        )
        if doc_layout == "grid":
            self._draw_grid_overlay_lines(
                doc.root_widgets, dx1, dy1, dx2, dy2,
            )
        zoom = self.zoom.value
        for container in self.iter_containers(doc.root_widgets):
            layout = normalise_layout_type(
                container.properties.get("layout_type", "place"),
            )
            if layout == "place":
                continue
            try:
                lx = int(container.properties.get("x", 0))
                ly = int(container.properties.get("y", 0))
                lw = int(container.properties.get("width", 0) or 0)
                lh = int(container.properties.get("height", 0) or 0)
            except (TypeError, ValueError):
                continue
            if lw <= 0 or lh <= 0:
                continue
            cx1, cy1 = self.zoom.logical_to_canvas(lx, ly, document=doc)
            cx2 = cx1 + int(lw * zoom)
            cy2 = cy1 + int(lh * zoom)
            if layout == "grid":
                self._draw_grid_overlay_lines(
                    container.children, cx1, cy1, cx2, cy2,
                )
            self._draw_layout_badge(layout, cx2, cy1)

    def iter_containers(self, nodes):
        for n in nodes:
            descriptor = get_descriptor(n.widget_type)
            if descriptor is not None and getattr(
                descriptor, "is_container", False,
            ):
                yield n
            yield from self.iter_containers(n.children)

    def _draw_grid_overlay_lines(
        self, children, x1: int, y1: int, x2: int, y2: int,
    ) -> None:
        if not children or x2 <= x1 or y2 <= y1:
            return
        rows: set[int] = set()
        cols: set[int] = set()
        for c in children:
            try:
                rows.add(int(c.properties.get("grid_row", 0)))
                cols.add(int(c.properties.get("grid_column", 0)))
            except (TypeError, ValueError):
                pass
        if not rows or not cols:
            return
        nrows = max(rows) + 1
        ncols = max(cols) + 1
        cell_w = (x2 - x1) / max(ncols, 1)
        cell_h = (y2 - y1) / max(nrows, 1)
        for c in range(1, ncols):
            cx = x1 + int(cell_w * c)
            self.canvas.create_line(
                cx, y1 + 1, cx, y2 - 1,
                fill=LAYOUT_GRID_LINE, dash=(2, 4),
                tags=(LAYOUT_OVERLAY_TAG,),
            )
        for r in range(1, nrows):
            ry = y1 + int(cell_h * r)
            self.canvas.create_line(
                x1 + 1, ry, x2 - 1, ry,
                fill=LAYOUT_GRID_LINE, dash=(2, 4),
                tags=(LAYOUT_OVERLAY_TAG,),
            )

    def _draw_layout_badge(
        self, layout: str, x_right: int, y_top: int,
    ) -> None:
        self.canvas.create_text(
            x_right - 6, y_top + 4,
            text=f"[{layout}]", anchor="ne",
            fill=LAYOUT_BADGE_FG,
            font=("Segoe UI", 9, "italic"),
            tags=(LAYOUT_OVERLAY_TAG,),
        )

    # ------------------------------------------------------------------
    # Child-geometry manager switching (Stage 3.1)
    # ------------------------------------------------------------------
    def rearrange_container_children(self, container_id: str) -> None:
        """Re-apply each direct child's geometry manager against the
        container's current ``layout_type``. Forgets the old manager
        first so we never hit tk's "can't mix managers" error. Pack
        ordering follows ``container.children`` so visual order stays
        stable across edits.
        """
        container = self.project.get_widget(container_id)
        if container is None:
            return
        for child in container.children:
            entry = self.widget_views.get(child.id)
            if entry is None:
                continue
            widget, _window_id = entry
            descriptor = get_descriptor(child.widget_type)
            anchor_widget = (
                descriptor.canvas_anchor(widget)
                if descriptor is not None else widget
            )
            self.apply_child_manager(anchor_widget, container, child)

    def apply_child_manager(
        self, anchor_widget, parent_node, child_node,
    ) -> None:
        """Forget ``anchor_widget``'s current manager and re-apply the
        one that matches ``parent_node.layout_type``. Separate from
        the widget-added path so property-change reshuffles don't
        re-run the descriptor / binding pipeline.
        """
        manager, mgr_kwargs = _child_manager_kwargs(
            parent_node, child_node.properties, zoom=self.zoom.value,
        )
        _forget_current_manager(anchor_widget)
        try:
            lw = int(child_node.properties.get("width", 0) or 0)
            lh = int(child_node.properties.get("height", 0) or 0)
        except (TypeError, ValueError):
            lw = lh = 0
        is_composite = child_node.id in self.anchor_views
        if manager == "pack":
            if is_composite and lw > 0 and lh > 0:
                try:
                    anchor_widget.configure(
                        width=max(1, int(lw * self.zoom.value)),
                        height=max(1, int(lh * self.zoom.value)),
                    )
                except tk.TclError:
                    pass
            try:
                anchor_widget.pack(**mgr_kwargs)
            except tk.TclError:
                pass
            return
        # ``place`` (includes the pre-Stage-3.2 grid stand-in).
        try:
            lx = int(child_node.properties.get("x", 0))
            ly = int(child_node.properties.get("y", 0))
        except (TypeError, ValueError):
            lx = ly = 0
        place_kwargs: dict = {
            "x": int(lx * self.zoom.value),
            "y": int(ly * self.zoom.value),
        }
        if is_composite and lw > 0 and lh > 0:
            place_kwargs["width"] = max(1, int(lw * self.zoom.value))
            place_kwargs["height"] = max(1, int(lh * self.zoom.value))
        try:
            anchor_widget.place(**place_kwargs)
        except tk.TclError:
            pass
