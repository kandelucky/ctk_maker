"""Layout-manager helpers for the WYSIWYG pipeline.

1. **Module-level functions** (no workspace needed):
    - ``_strip_layout_keys``    — filter out node-only layout keys
      so CTk constructors / ``configure`` calls never see them.
    - ``_child_manager_kwargs`` — pick the manager for a child given
      its parent's ``layout_type``.
    - ``_stretch_to_pack_kwargs`` — translate ``fixed/fill/grow`` to
      tk pack fill/expand kwargs.
    - ``_grid_child_place_kwargs`` — compute place() coords that
      centre a grid child in its cell (CTkFrame's internal canvas
      breaks tk's native grid centring, so canvas preview uses
      place instead; runtime export still emits real ``.grid()``).
    - ``_forget_current_manager`` — cross-manager safe forget.

2. **``LayoutOverlayManager``** (owns Workspace ref):
    - Re-applies child managers when ``layout_type`` changes.
    - Reserved overlay hook — currently draws nothing (see the
      docstring on ``draw_overlays_for_doc`` for why).

Split out of the old monolithic ``workspace.py`` to keep layout
manager logic in one focused module. Core ``Workspace`` holds a
single instance on ``self.layout_overlay`` and delegates to it.
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


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

# Canvas tag reserved for future layout-semantic overlays. No overlay
# is currently drawn — a real tk Frame (canvas window item) always
# renders above canvas primitives, so in-Frame grid hints need a
# different host than the main canvas.
LAYOUT_OVERLAY_TAG = "layout_overlay"


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


def _grid_child_place_kwargs(
    parent_props: dict, child_props: dict, zoom: float = 1.0,
) -> dict:
    """Calculate place() kwargs for a grid child centered in its cell."""
    container_w = _safe_int(parent_props.get("width", 0), 0)
    container_h = _safe_int(parent_props.get("height", 0), 0)
    if container_w <= 0 or container_h <= 0:
        return {"x": 0, "y": 0}
    rows = max(1, _safe_int(parent_props.get("grid_rows", 2), 2))
    cols = max(1, _safe_int(parent_props.get("grid_cols", 2), 2))
    spacing = _safe_int(parent_props.get("layout_spacing", 0), 0)
    half_sp = spacing / 2

    cell_w = container_w / cols
    cell_h = container_h / rows

    row = _safe_int(child_props.get("grid_row", 0), 0)
    col = _safe_int(child_props.get("grid_column", 0), 0)
    sticky = (child_props.get("grid_sticky", "") or "").lower()

    child_w = _safe_int(child_props.get("width", 0), 0)
    child_h = _safe_int(child_props.get("height", 0), 0)

    avail_x = col * cell_w + half_sp
    avail_y = row * cell_h + half_sp
    avail_w = cell_w - spacing
    avail_h = cell_h - spacing

    has_n, has_s = "n" in sticky, "s" in sticky
    has_e, has_w = "e" in sticky, "w" in sticky

    if has_w and has_e:
        x, w = avail_x, avail_w
    elif has_w:
        x, w = avail_x, child_w
    elif has_e:
        x, w = avail_x + avail_w - child_w, child_w
    else:
        x, w = avail_x + (avail_w - child_w) / 2, child_w

    if has_n and has_s:
        y, h = avail_y, avail_h
    elif has_n:
        y, h = avail_y, child_h
    elif has_s:
        y, h = avail_y + avail_h - child_h, child_h
    else:
        y, h = avail_y + (avail_h - child_h) / 2, child_h

    result: dict = {
        "x": max(0, int(x * zoom)),
        "y": max(0, int(y * zoom)),
    }
    if w > 0 and h > 0:
        result["_cfg_width"] = max(1, int(w * zoom))
        result["_cfg_height"] = max(1, int(h * zoom))
    return result


def _child_manager_kwargs(
    parent_node, child_props: dict, zoom: float = 1.0,
) -> tuple[str, dict]:
    """Pick the tk geometry manager + its kwargs for a child whose
    parent is ``parent_node``. Returns ``(manager_name, kwargs)``
    with manager ∈ ``place`` / ``pack`` / ``grid``. Grid kwargs are
    empty — callers call ``_grid_child_place_kwargs`` directly since
    canvas preview uses place()-based centring.
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
    if layout == "grid":
        return "grid", {}
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
    """Per-workspace manager for WYSIWYG pack / grid wiring
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
        """No semantic overlays are drawn — layout type is surfaced via
        the palette preset name / Properties panel / Object Tree icon,
        and grid-cell structure is surfaced through each child's
        Inspector row/column fields. The method is kept as a stable
        hook so the renderer can call it every redraw without a
        conditional, and so a future overlay can be re-enabled in one
        place.
        """
        # Parameters retained in signature for future overlay work.
        _ = (doc, dx1, dy1, dx2, dy2)

    # ------------------------------------------------------------------
    # Child-geometry manager switching
    # ------------------------------------------------------------------
    def rearrange_container_children(self, container_id: str) -> None:
        """Re-apply each direct child's geometry manager against the
        container's current ``layout_type``. Pack queue visual order
        must match the model order in ``container.children``, so we
        do this in two passes: forget every child first (queue goes
        empty), then pack them in order so each call lands at the
        end of the queue. A single-pass forget-and-repack would pin
        the current child ``before=`` a still-packed next sibling,
        which leaves the queue in a stale, pre-reorder order.
        """
        container = self.project.get_widget(container_id)
        if container is None:
            return
        anchor_widgets: list[tuple[object, object]] = []
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
            anchor_widgets.append((anchor_widget, child))
        for anchor_widget, _child in anchor_widgets:
            _forget_current_manager(anchor_widget)
        for anchor_widget, child in anchor_widgets:
            self.apply_child_manager(anchor_widget, container, child)

    def _next_sibling_anchor(self, parent_node, child_node):
        """Return the anchor widget of the first sibling that comes
        after ``child_node`` in the model and is already on-canvas.
        Used by ``apply_child_manager`` to pin a re-packed child to
        its correct slot via tk's ``pack(before=...)``. Returns
        ``None`` if there's no next sibling with a view — caller
        should append.
        """
        if parent_node is None:
            return None
        siblings = parent_node.children
        try:
            idx = siblings.index(child_node)
        except ValueError:
            return None
        for sibling in siblings[idx + 1:]:
            entry = self.widget_views.get(sibling.id)
            if entry is None:
                continue
            widget, _ = entry
            descriptor = get_descriptor(sibling.widget_type)
            return (
                descriptor.canvas_anchor(widget)
                if descriptor is not None else widget
            )
        return None

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
            stretch = str(
                child_node.properties.get("stretch", "fixed"),
            )
            parent_layout = normalise_layout_type(
                parent_node.properties.get("layout_type", "place"),
            ) if parent_node is not None else "place"
            if stretch == "grow" and parent_layout in ("vbox", "hbox"):
                # Equal-split main axis among grow siblings so a
                # grid → vbox swap (or a fresh grow drop) divides the
                # container height (vbox) / width (hbox) evenly instead
                # of leaving widgets at their prior configured size.
                # tk pack's ``expand=True`` alone won't shrink a widget
                # below its configured natural size, so we size each
                # grow child explicitly. Cross-axis stays on ``fill=both``.
                grow_siblings = [
                    c for c in parent_node.children
                    if str(c.properties.get("stretch", "fixed")) == "grow"
                ]
                count = max(1, len(grow_siblings))
                try:
                    spacing = int(
                        parent_node.properties.get("layout_spacing", 0)
                        or 0,
                    )
                except (TypeError, ValueError):
                    spacing = 0
                zoom = self.zoom.value or 1.0
                if parent_layout == "vbox":
                    try:
                        container_h = int(
                            parent_node.properties.get("height", 0) or 0,
                        )
                    except (TypeError, ValueError):
                        container_h = 0
                    slot = max(
                        1,
                        (container_h - spacing * (count - 1)) // count,
                    )
                    try:
                        anchor_widget.configure(
                            height=max(1, int(slot * zoom)),
                        )
                    except tk.TclError:
                        pass
                else:  # hbox
                    try:
                        container_w = int(
                            parent_node.properties.get("width", 0) or 0,
                        )
                    except (TypeError, ValueError):
                        container_w = 0
                    slot = max(
                        1,
                        (container_w - spacing * (count - 1)) // count,
                    )
                    try:
                        anchor_widget.configure(
                            width=max(1, int(slot * zoom)),
                        )
                    except tk.TclError:
                        pass
            elif is_composite and lw > 0 and lh > 0:
                try:
                    anchor_widget.configure(
                        width=max(1, int(lw * self.zoom.value)),
                        height=max(1, int(lh * self.zoom.value)),
                    )
                except tk.TclError:
                    pass
            # pack()-ing a fresh widget appends it to the end of its
            # parent's pack queue. When we re-apply a manager for a
            # child that already has siblings (e.g. stretch changed),
            # we must anchor it to its model position via ``before=``
            # the next sibling's widget, otherwise the widget sinks
            # to the bottom of the stack. The ``before=`` widget MUST
            # currently be packed — during a full rearrange (iterating
            # children in order after a reorder) the next sibling is
            # already forgotten, so passing before= would land the
            # current child at the wrong queue position. Append
            # instead and rely on the iteration order.
            before_widget = self._next_sibling_anchor(
                parent_node, child_node,
            )
            if before_widget is not None:
                try:
                    if before_widget.winfo_manager() == "pack":
                        mgr_kwargs = {**mgr_kwargs, "before": before_widget}
                except tk.TclError:
                    pass
            try:
                anchor_widget.pack(**mgr_kwargs)
            except tk.TclError:
                pass
            return
        if manager == "grid":
            place_kw = _grid_child_place_kwargs(
                parent_node.properties if parent_node else {},
                child_node.properties,
                zoom=self.zoom.value,
            )
            cfg_w = place_kw.pop("_cfg_width", None)
            cfg_h = place_kw.pop("_cfg_height", None)
            if cfg_w and cfg_h:
                try:
                    anchor_widget.configure(width=cfg_w, height=cfg_h)
                except (tk.TclError, ValueError):
                    pass
            try:
                anchor_widget.place(**place_kw)
            except tk.TclError:
                pass
            return
        # ``place`` (default).
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
