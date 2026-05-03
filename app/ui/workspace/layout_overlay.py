"""Layout-manager helpers for the WYSIWYG pipeline.

1. **Module-level functions** (no workspace needed):
    - ``_strip_layout_keys``    — filter out node-only layout keys
      so CTk constructors / ``configure`` calls never see them.
    - ``_child_manager_kwargs`` — pick the manager for a child given
      its parent's ``layout_type``.
    - ``_stretch_to_pack_kwargs`` — translate ``fixed/fill/grow`` to
      tk pack fill/expand kwargs.
    - ``_sticky_axis`` — single-axis position+size from sticky flags;
      the table both grid axes share.
    - ``_grid_child_place_kwargs`` — compute place() coords that
      centre a grid child in its cell (CTkFrame's internal canvas
      breaks tk's native grid centring, so canvas preview uses
      place instead; runtime export still emits real ``.grid()``).
    - ``_composite_configure`` / ``_composite_place_size`` — pin a
      composite widget's size via configure() or as place/create_window
      kwargs; shared by every layout branch.
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

from app.widgets.content_min import content_min_axis
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


def _sticky_axis(
    has_lo: bool, has_hi: bool,
    avail_pos: float, avail_size: float, child_size: float,
) -> tuple[float, float]:
    """Resolve one axis of a grid child's position + size from its
    sticky flags. ``has_lo`` is north / west, ``has_hi`` is south /
    east. Both anchors → fill the cell; one anchor → align to that
    edge at natural size; neither → centre at natural size. Same
    table for horizontal + vertical axes — caller picks which one.
    """
    if has_lo and has_hi:
        return avail_pos, avail_size
    if has_lo:
        return avail_pos, child_size
    if has_hi:
        return avail_pos + avail_size - child_size, child_size
    return avail_pos + (avail_size - child_size) / 2, child_size


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

    x, w = _sticky_axis(
        "w" in sticky, "e" in sticky, avail_x, avail_w, child_w,
    )
    y, h = _sticky_axis(
        "n" in sticky, "s" in sticky, avail_y, avail_h, child_h,
    )

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


def _composite_configure(widget, lw: int, lh: int, zoom: float) -> None:
    """Apply a composite widget's configured size via ``configure``.
    Composite widgets (CTkScrollableFrame, anything with an inner
    container) don't auto-size from their children, so the workspace
    has to pin them explicitly. No-op when either dimension is 0.
    Used by the pack and grid branches that hand the widget to a
    geometry manager via configure-then-pack/place.
    """
    if lw <= 0 or lh <= 0:
        return
    try:
        widget.configure(
            width=max(1, int(lw * zoom)),
            height=max(1, int(lh * zoom)),
        )
    except tk.TclError:
        pass


def _composite_place_size(lw: int, lh: int, zoom: float) -> dict:
    """Return ``width`` / ``height`` kwargs for a composite widget's
    ``place()`` call, or an empty dict when either dimension is 0.
    Sibling of ``_composite_configure`` for the place branch where
    sizing rides on the place call itself instead of a separate
    ``configure``.
    """
    if lw <= 0 or lh <= 0:
        return {}
    return {
        "width": max(1, int(lw * zoom)),
        "height": max(1, int(lh * zoom)),
    }


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
        re-run the descriptor / binding pipeline. Body is just a
        dispatch — the per-manager bodies are split into their own
        methods for readability + testability.
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
            self._apply_pack_manager(
                anchor_widget, parent_node, child_node,
                mgr_kwargs, lw, lh, is_composite,
            )
        elif manager == "grid":
            self._apply_grid_manager(anchor_widget, parent_node, child_node)
        else:
            self._apply_place_manager(
                anchor_widget, child_node, lw, lh, is_composite,
            )

    def _apply_pack_manager(
        self, anchor_widget, parent_node, child_node,
        mgr_kwargs: dict, lw: int, lh: int, is_composite: bool,
    ) -> None:
        """pack() branch — equal-split sizing for grow children, then
        ``before=`` anchoring so the visual queue tracks model order
        even when only one sibling is being re-applied."""
        stretch = str(child_node.properties.get("stretch", "fixed"))
        parent_layout = normalise_layout_type(
            parent_node.properties.get("layout_type", "place"),
        ) if parent_node is not None else "place"
        if parent_layout in ("vbox", "hbox"):
            # Always rebalance — fixed siblings keep their nominal
            # width, grow/fill siblings flex-shrink with content_min
            # floor. Old behavior gated on stretch=="grow" only,
            # which left fresh "fill"/"fixed" drops un-rebalanced
            # against existing siblings.
            self.rebalance_pack_siblings(parent_node, parent_layout)
        elif is_composite:
            _composite_configure(anchor_widget, lw, lh, self.zoom.value)
        # pack()-ing a fresh widget appends it to the end of its
        # parent's pack queue. When we re-apply a manager for a child
        # that already has siblings (e.g. stretch changed), we must
        # anchor it to its model position via ``before=`` the next
        # sibling's widget, otherwise the widget sinks to the bottom
        # of the stack. The ``before=`` widget MUST currently be
        # packed — during a full rearrange (iterating children in
        # order after a reorder) the next sibling is already
        # forgotten, so passing before= would land the current child
        # at the wrong queue position. Append instead and rely on the
        # iteration order.
        before_widget = self._next_sibling_anchor(parent_node, child_node)
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

    def rebalance_pack_siblings(
        self, parent_node, parent_layout: str,
    ) -> None:
        """Flex-shrink the parent's main axis across pack children.

        Mirrors CSS flex on a vbox/hbox container, with three
        ``stretch`` semantics:

        - ``"fixed"`` — user controls both axes (CSS ``flex: 0 0 W``).
          Main-axis size = ``node.properties[axis]`` at face value;
          cross-axis stays at its configured size.
        - ``"fill"`` — user controls main axis (same as fixed),
          cross axis fills the container (CSS ``flex: 0 0 W`` with
          ``align-self: stretch``). Helper does NOT touch main axis.
        - ``"grow"`` — main axis is auto-distributed (CSS ``flex: 1``):
          ``slot = avail / N_grow`` floored at ``content_min_axis``.
          Cross axis fills the container.

        When even content-min × N exceeds the container's remaining
        budget, every grow sibling sits at its floor and tk silently
        clips the overflow at the right/bottom edge — matches the
        user's "no scrollbar" requirement (v1.10.2).

        Replaces the old ``_apply_grow_equal_split`` which (a) didn't
        subtract fixed siblings from the budget, (b) had no min-floor
        so grow children could squash text into nothing, (c) was
        only invoked on layout-type swaps, not on fresh add/remove —
        leaving newly-packed siblings to overflow off the right edge,
        and (d) treated ``fill`` like ``grow`` so users couldn't pin
        a specific width on a fill child.
        """
        all_siblings = list(parent_node.children)
        if not all_siblings:
            return
        try:
            spacing = int(
                parent_node.properties.get("layout_spacing", 0) or 0,
            )
        except (TypeError, ValueError):
            spacing = 0
        zoom = self.zoom.value or 1.0
        axis_key = "height" if parent_layout == "vbox" else "width"
        try:
            container_size = int(
                parent_node.properties.get(axis_key, 0) or 0,
            )
        except (TypeError, ValueError):
            container_size = 0
        if container_size <= 0:
            return

        fixed_total = 0
        fixed_siblings: list = []
        grow_siblings: list = []
        for sib in all_siblings:
            stretch = str(sib.properties.get("stretch", "fixed"))
            # Both ``fixed`` and ``fill`` keep user-set main-axis size;
            # only ``grow`` participates in helper-driven distribution.
            # ``fill``'s cross-axis stretch is owned by pack's
            # ``fill="x"`` / ``"y"`` kwarg, not the main-axis math here.
            if stretch in ("fixed", "fill"):
                try:
                    w = int(sib.properties.get(axis_key, 0) or 0)
                except (TypeError, ValueError):
                    w = 0
                fixed_total += max(0, w)
                fixed_siblings.append((sib, max(0, w)))
            else:
                grow_siblings.append(sib)
        total_spacing = spacing * max(0, len(all_siblings) - 1)
        avail = container_size - fixed_total - total_spacing
        if grow_siblings:
            grow_slot = max(1, avail // len(grow_siblings))
        else:
            grow_slot = 0

        widget_views = getattr(self.workspace, "widget_views", {}) or {}
        anchor_views = getattr(self.workspace, "_anchor_views", {}) or {}
        # Restore fixed/fill siblings to their model-stored size on
        # the main axis. Without this, a stretch transition (grow →
        # fixed / fill) leaves the widget at whatever slot the helper
        # had configured under the previous stretch — visually stuck
        # at the old grow_slot instead of jumping to the user's
        # nominal width. Cross-axis is left to pack's fill kwarg.
        #
        # Note on DPI: ``widget.configure(width=N)`` takes N in CTk
        # units and ScalingTracker multiplies by the DPI factor
        # internally, so the canvas helper must NOT divide by scale
        # again — the runtime ``_ctkmaker_balance_pack`` does because
        # there ``container.winfo_width()`` arrives in raw pixels and
        # the helper needs to convert into CTk units before configure;
        # the canvas helper already starts from ``container_size`` in
        # model units, which is the same coordinate space configure()
        # expects. See ``zoom_controller._dpi_factor`` for the rule.
        for sibling, model_size in fixed_siblings:
            if model_size <= 0:
                continue
            entry = widget_views.get(sibling.id)
            if entry is None:
                continue
            widget, _ = entry
            sib_anchor = anchor_views.get(sibling.id, widget)
            target = max(1, int(model_size * zoom))
            self._resize_image_if_needed(
                sibling, widget, axis_key, target, zoom,
            )
            try:
                sib_anchor.configure(**{axis_key: target})
            except tk.TclError:
                pass
        for sibling in grow_siblings:
            entry = widget_views.get(sibling.id)
            if entry is None:
                continue
            widget, _ = entry
            sib_anchor = anchor_views.get(sibling.id, widget)
            floor = content_min_axis(sibling, axis_key)
            slot = max(floor, grow_slot)
            target = max(1, int(slot * zoom))
            self._resize_image_if_needed(
                sibling, widget, axis_key, target, zoom,
            )
            try:
                sib_anchor.configure(**{axis_key: target})
            except tk.TclError:
                pass

    def _resize_image_if_needed(
        self, sibling, widget, axis_key, target_main, zoom,
    ) -> None:
        """Image is a CTkLabel wrapping a CTkImage. The label box
        shrinks via ``configure(width=N)`` like every other widget,
        but the embedded CTkImage carries its own ``size=(W, H)``
        from its constructor and ignores the label's resize. Reach
        through to the CTkImage and resize it explicitly so the
        rendered picture actually shrinks/grows alongside the label.
        Cross axis follows the model — pack's fill kwarg handles
        cross-axis stretch separately and the user-set value is the
        right reference here.
        """
        if getattr(sibling, "widget_type", "") != "Image":
            return
        ctk_img = getattr(widget, "_image", None)
        if ctk_img is None:
            return
        cross_key = "height" if axis_key == "width" else "width"
        try:
            cross_model = int(sibling.properties.get(cross_key, 0) or 0)
        except (TypeError, ValueError):
            cross_model = 0
        target_cross = (
            max(1, int(cross_model * zoom)) if cross_model > 0
            else target_main
        )
        try:
            if axis_key == "width":
                ctk_img.configure(size=(target_main, target_cross))
            else:
                ctk_img.configure(size=(target_cross, target_main))
        except Exception:
            pass

    def _apply_grid_manager(
        self, anchor_widget, parent_node, child_node,
    ) -> None:
        """grid branch — `_grid_child_place_kwargs` does the cell
        math; we configure the cell-sized dimensions and place the
        widget at the computed coords."""
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

    def _apply_place_manager(
        self, anchor_widget, child_node,
        lw: int, lh: int, is_composite: bool,
    ) -> None:
        """place branch — absolute x/y from the child, optional size
        kwargs for composites that won't auto-size."""
        try:
            lx = int(child_node.properties.get("x", 0))
            ly = int(child_node.properties.get("y", 0))
        except (TypeError, ValueError):
            lx = ly = 0
        place_kwargs: dict = {
            "x": int(lx * self.zoom.value),
            "y": int(ly * self.zoom.value),
        }
        if is_composite:
            place_kwargs.update(
                _composite_place_size(lw, lh, self.zoom.value),
            )
        try:
            anchor_widget.place(**place_kwargs)
        except tk.TclError:
            pass
