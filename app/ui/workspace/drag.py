"""Widget drag-to-move + drag-to-reparent controller.

Holds the per-gesture drag state (``_drag``) and the three press /
motion / release handlers every canvas widget is bound to. The
controller owns the logic for:

- press      — capture the widget's starting logical x/y
- motion     — translate the mouse delta (zoom-adjusted) into x/y
               property updates; tripping the 5 px threshold before
               committing so click-without-drag stays silent. For
               grid-parented widgets, x/y stays frozen and a cell
               highlight is drawn under the cursor instead.
- release    — either record a single ``MoveCommand`` for the
               gesture, a ``MultiChangePropertyCommand`` for a grid
               cell change, or a ``ReparentCommand`` if the widget
               was dropped into a different container / document.

Split out of the old monolithic ``workspace.py`` so drag logic lives
in one focused module. Core ``Workspace`` holds a single instance on
``self.drag_controller`` and wires widget bindings through it.
"""

from __future__ import annotations

import tkinter as tk

from app.core.commands import (
    MoveCommand,
    MultiChangePropertyCommand,
    ReparentCommand,
)
from app.widgets.layout_schema import (
    grid_effective_dims,
    normalise_layout_type,
)

DRAG_THRESHOLD = 5
GRID_HIGHLIGHT_TAG = "grid_drop_highlight"
GRID_HIGHLIGHT_COLOR = "#6fb4f0"


class WidgetDragController:
    """Per-workspace widget drag handler.

    All external state (project, canvas, zoom, selection, tool mode,
    lock/cover logic) is read through the workspace ref. The only
    state this class owns is the in-progress drag gesture.
    """

    def __init__(self, workspace) -> None:
        self.workspace = workspace
        self._drag: dict | None = None

    # ------------------------------------------------------------------
    # Convenience accessors — keep call sites terse.
    # ------------------------------------------------------------------
    @property
    def project(self):
        return self.workspace.project

    @property
    def zoom(self):
        return self.workspace.zoom

    @property
    def canvas(self) -> tk.Canvas:
        return self.workspace.canvas

    @property
    def widget_views(self) -> dict:
        return self.workspace.widget_views

    def is_dragging(self) -> bool:
        return self._drag is not None and self._drag.get("moved", False)

    # ------------------------------------------------------------------
    # Bound handlers
    # ------------------------------------------------------------------
    def on_press(self, event, nid: str) -> None:
        ws = self.workspace
        if ws._tool == "hand":
            ws._begin_pan(event)
            return
        # Clear any stale drag state from a prior interaction whose
        # ButtonRelease was lost (widget destroyed mid-drag, focus
        # switch to another toplevel, etc).
        self._drag = None
        self.project.select_widget(nid)
        if ws._effective_locked(nid):
            # Locked widgets are selectable (for property editing)
            # but not draggable.
            return
        node = self.project.get_widget(nid)
        if node is None:
            return
        try:
            start_x = int(node.properties.get("x", 0))
            start_y = int(node.properties.get("y", 0))
        except (ValueError, TypeError):
            start_x, start_y = 0, 0
        # Delta-based drag — works for canvas children and nested
        # children alike because we only care about the mouse delta
        # from the press point and apply it (zoom-adjusted) to the
        # logical coordinate stored in properties.
        self._drag = {
            "nid": nid,
            "start_x": start_x,
            "start_y": start_y,
            "press_mx": event.x_root,
            "press_my": event.y_root,
            "moved": False,
        }

    def on_motion(self, event, nid: str) -> None:
        ws = self.workspace
        if ws._tool == "hand":
            ws._update_pan(event)
            return
        # Defense: <B1-Motion> should only fire while button 1 is
        # held. If the state mask says otherwise, a prior release
        # was missed — drop the stale drag and refuse to move.
        if not (event.state & 0x0100):
            self._drag = None
            self._clear_grid_highlight()
            return
        if self._drag is None or self._drag["nid"] != nid:
            return
        dx_root = event.x_root - self._drag["press_mx"]
        dy_root = event.y_root - self._drag["press_my"]
        if not self._drag["moved"]:
            if (
                abs(dx_root) < DRAG_THRESHOLD
                and abs(dy_root) < DRAG_THRESHOLD
            ):
                return
            self._drag["moved"] = True
        # Determine the container under the cursor. If it's a grid
        # container, the drag switches to cell-snap mode: no x/y
        # updates, just a highlight on the target cell so the user
        # sees where the widget will land on release.
        cx, cy = ws._screen_to_canvas(event.x_root, event.y_root)
        target = ws._find_container_at(cx, cy, exclude_id=nid)
        target_grid = (
            target is not None
            and normalise_layout_type(
                target.properties.get("layout_type", "place"),
            ) == "grid"
        )
        node = self.project.get_widget(nid)
        src_grid = (
            node is not None and node.parent is not None
            and normalise_layout_type(
                node.parent.properties.get("layout_type", "place"),
            ) == "grid"
        )
        if target_grid:
            row, col = self._grid_cell_at(target, cx, cy)
            self._draw_grid_highlight(target, row, col)
            return
        # Cursor left a grid container — erase any stale highlight.
        self._clear_grid_highlight()
        if src_grid:
            # Grid-parented widget dragged outside any grid — still
            # skip x/y updates so the model stays clean; we'll either
            # reparent on release or snap back to its current cell.
            return
        zoom = self.zoom.value or 1.0
        new_x = self._drag["start_x"] + int(dx_root / zoom)
        new_y = self._drag["start_y"] + int(dy_root / zoom)
        self.project.update_property(nid, "x", new_x)
        self.project.update_property(nid, "y", new_y)
        ws.selection.update()

    def on_release(self, event, _nid: str) -> None:
        ws = self.workspace
        if ws._tool == "hand":
            ws._end_pan(event)
            return
        drag = self._drag
        # Clear drag state BEFORE firing any project mutations so
        # ``_schedule_selection_redraw`` stops short-circuiting on
        # ``is_dragging()``. With the guard on, release-time updates
        # (grid snap, reparent, move) would leave selection handles
        # lingering at the pre-drop spot until the next UI event.
        self._drag = None
        self._clear_grid_highlight()
        if drag is not None and drag.get("moved"):
            grid_handled = self._maybe_grid_drop(event, drag)
            if not grid_handled:
                reparented = self._maybe_reparent_dragged(event)
                # Skip the Move record if the widget jumped parents — a
                # proper ReparentCommand captures the full before/after,
                # Move would duplicate part of that record.
                if not reparented:
                    node = self.project.get_widget(drag["nid"])
                    if node is not None:
                        try:
                            end_x = int(node.properties.get("x", 0))
                            end_y = int(node.properties.get("y", 0))
                        except (TypeError, ValueError):
                            end_x, end_y = drag["start_x"], drag["start_y"]
                        if (
                            (end_x, end_y)
                            != (drag["start_x"], drag["start_y"])
                        ):
                            self.project.history.push(
                                MoveCommand(
                                    drag["nid"],
                                    {
                                        "x": drag["start_x"],
                                        "y": drag["start_y"],
                                    },
                                    {"x": end_x, "y": end_y},
                                ),
                            )
        # Refresh cover-mask after a drag release so a widget that
        # just slid into / out of another document's area picks up
        # the right hidden state.
        ws._update_widget_visibility_across_docs()

    # ------------------------------------------------------------------
    # Reparent detection
    # ------------------------------------------------------------------
    def _maybe_reparent_dragged(self, event) -> bool:
        """On drag release, check if the widget was dropped into a
        different container OR a different document. Either case
        reparents (containers via ``project.reparent``, cross-doc via
        a manual move between document root lists) so undo + rendering
        stay consistent. Returns True when a reparent happened so the
        caller skips the per-widget Move history record.
        """
        ws = self.workspace
        if self._drag is None:
            return False
        nid = self._drag["nid"]
        node = self.project.get_widget(nid)
        if node is None:
            return False
        self.canvas.update_idletasks()
        cx, cy = ws._screen_to_canvas(event.x_root, event.y_root)
        target = ws._find_container_at(cx, cy, exclude_id=nid)
        new_parent_id = target.id if target is not None else None
        old_parent_id = node.parent.id if node.parent is not None else None

        old_doc = self.project.find_document_for_widget(nid)
        if target is not None:
            new_doc = self.project.find_document_for_widget(target.id)
        else:
            new_doc = (
                ws._find_document_at_canvas(cx, cy)
                or old_doc
                or self.project.active_document
            )

        cross_doc = new_doc is not None and new_doc is not old_doc
        if new_parent_id == old_parent_id and not cross_doc:
            return False  # same parent, same doc — in-place drag
        # Capture the pre-reparent state for undo BEFORE any mutation.
        old_siblings = (
            node.parent.children if node.parent is not None
            else (
                old_doc.root_widgets if old_doc is not None
                else self.project.root_widgets
            )
        )
        try:
            old_index = old_siblings.index(node)
        except ValueError:
            old_index = len(old_siblings)
        old_x = self._drag["start_x"]
        old_y = self._drag["start_y"]
        # Compute the widget's new logical x/y in the target's
        # coordinate space.
        widget, _ = self.widget_views[nid]
        zoom = self.zoom.value or 1.0
        if target is None:
            # Top-level drop — logical coords relative to whichever
            # document the drop landed in.
            rx = widget.winfo_rootx() - self.canvas.winfo_rootx()
            ry = widget.winfo_rooty() - self.canvas.winfo_rooty()
            canvas_x = self.canvas.canvasx(rx)
            canvas_y = self.canvas.canvasy(ry)
            target_doc = new_doc or self.project.active_document
            new_x, new_y = self.zoom.canvas_to_logical(
                canvas_x, canvas_y, document=target_doc,
            )
        else:
            target_widget, _ = self.widget_views[target.id]
            rel_x = widget.winfo_rootx() - target_widget.winfo_rootx()
            rel_y = widget.winfo_rooty() - target_widget.winfo_rooty()
            new_x = int(rel_x / zoom)
            new_y = int(rel_y / zoom)
        # Write the new coords directly; reparent will trigger a
        # widget rebuild that picks them up.
        node.properties["x"] = max(0, new_x)
        node.properties["y"] = max(0, new_y)
        if cross_doc and target is None:
            # Cross-document top-level move: project.reparent targets
            # the active document, which isn't necessarily the drop
            # target. Pop from old doc, push to new doc manually and
            # raise the reparent event so the workspace rebuilds the
            # widget under the new root.
            if old_doc is not None and node in old_doc.root_widgets:
                old_doc.root_widgets.remove(node)
            node.parent = None
            new_doc.root_widgets.append(node)
            self.project.event_bus.publish(
                "widget_reparented", nid,
                old_parent_id, new_parent_id,
            )
        else:
            self.project.reparent(nid, new_parent_id)
        # Capture post-reparent index so redo can restore z-order.
        post_node = self.project.get_widget(nid)
        if post_node is not None:
            new_siblings = (
                post_node.parent.children if post_node.parent is not None
                else self.project.root_widgets
            )
            try:
                new_index = new_siblings.index(post_node)
            except ValueError:
                new_index = len(new_siblings) - 1
        else:
            new_index = 0
        self.project.history.push(
            ReparentCommand(
                nid,
                old_parent_id=old_parent_id,
                old_index=old_index,
                old_x=old_x,
                old_y=old_y,
                new_parent_id=new_parent_id,
                new_index=new_index,
                new_x=new_x,
                new_y=new_y,
            ),
        )
        return True

    # ------------------------------------------------------------------
    # Grid drag-to-cell
    # ------------------------------------------------------------------
    def _maybe_grid_drop(self, event, drag: dict) -> bool:
        """Explicit-cell grid drop. Cursor cell becomes the child's
        own ``grid_row`` / ``grid_column`` — no sibling shift. Cross-
        parent drops hand off to ``_maybe_reparent_dragged`` after
        pre-setting the new cell on the node so the post-reparent
        ``.grid()`` call lands in the target cell.
        """
        ws = self.workspace
        nid = drag["nid"]
        node = self.project.get_widget(nid)
        if node is None:
            return False
        self.canvas.update_idletasks()
        cx, cy = ws._screen_to_canvas(event.x_root, event.y_root)
        target = ws._find_container_at(cx, cy, exclude_id=nid)
        if target is None:
            return False
        target_layout = normalise_layout_type(
            target.properties.get("layout_type", "place"),
        )
        if target_layout != "grid":
            return False
        row, col = self._grid_cell_at(target, cx, cy)
        old_parent_id = node.parent.id if node.parent is not None else None
        new_parent_id = target.id
        try:
            old_row = int(node.properties.get("grid_row", 0) or 0)
            old_col = int(node.properties.get("grid_column", 0) or 0)
        except (TypeError, ValueError):
            old_row, old_col = 0, 0
        if new_parent_id == old_parent_id:
            if (row, col) == (old_row, old_col):
                return True  # same cell — no-op drop
            self.project.update_property(nid, "grid_row", row)
            self.project.update_property(nid, "grid_column", col)
            self.project.history.push(
                MultiChangePropertyCommand(
                    nid,
                    {
                        "grid_row": (old_row, row),
                        "grid_column": (old_col, col),
                    },
                ),
            )
            return True
        # Different parent — pre-set the new cell so the reparent's
        # widget rebuild lands at the user's chosen cell, then fall
        # through to the standard reparent flow for the destroy /
        # recreate + history push.
        node.properties["grid_row"] = row
        node.properties["grid_column"] = col
        self._maybe_reparent_dragged(event)
        return True

    def _grid_dimensions(
        self, container_node, *, extra_child: bool = False,
    ) -> tuple[int, int]:
        """Rows × cols of ``container`` — authoritative user-set
        ``grid_rows`` / ``grid_cols``. No auto-grow: children past
        capacity wrap into existing cells (see
        ``grid_cell_for_index``). ``extra_child`` kept for API
        compatibility but no longer affects the answer.
        """
        _ = extra_child
        return grid_effective_dims(
            len(container_node.children), container_node.properties,
        )

    def _grid_cell_at(
        self, container_node, canvas_x: float, canvas_y: float,
    ) -> tuple[int, int]:
        """Map a canvas position to a (row, col) cell on ``container``.
        The cell grid matches the container's current structure — the
        overlay won't show phantom rows/columns past the last filled
        one. To grow the grid the user can drag onto an already-full
        cell (overlap lands a sibling there) or edit row/col directly.
        """
        entry = self.widget_views.get(container_node.id)
        if entry is None:
            return (0, 0)
        widget, _ = entry
        bbox = self.workspace._widget_canvas_bbox(widget)
        if bbox is None:
            return (0, 0)
        x1, y1, x2, y2 = bbox
        nrows, ncols = self._grid_dimensions(container_node)
        cell_w = (x2 - x1) / max(ncols, 1)
        cell_h = (y2 - y1) / max(nrows, 1)
        if cell_w <= 0 or cell_h <= 0:
            return (0, 0)
        col = int((canvas_x - x1) / cell_w)
        row = int((canvas_y - y1) / cell_h)
        col = max(0, min(ncols - 1, col))
        row = max(0, min(nrows - 1, row))
        return (row, col)

    def _draw_grid_highlight(
        self, container_node, row: int, col: int,
    ) -> None:
        """Paint a light-blue outline on the target cell — only the
        border, so the cell's content (if any) stays visible. The
        overlay is four thin ``tk.Frame`` stripes laid out around
        the cell via ``.place()``: a single solid-bg Frame would
        cover anything below, and canvas primitives can't render
        above a window-item Frame. Frames are created ONCE per
        gesture and repositioned on subsequent motion events —
        recreating them every tick freezes the UI.
        """
        cache_key = (container_node.id, row, col)
        if getattr(self, "_grid_highlight_key", None) == cache_key:
            return  # nothing changed
        entry = self.widget_views.get(container_node.id)
        if entry is None:
            self._clear_grid_highlight()
            return
        container_widget, _ = entry
        try:
            cw = int(container_widget.winfo_width())
            ch = int(container_widget.winfo_height())
        except tk.TclError:
            self._clear_grid_highlight()
            return
        if cw <= 0 or ch <= 0:
            self._clear_grid_highlight()
            return
        nrows, ncols = self._grid_dimensions(container_node)
        cell_w = cw / max(ncols, 1)
        cell_h = ch / max(nrows, 1)
        if cell_w <= 0 or cell_h <= 0:
            self._clear_grid_highlight()
            return
        rx = int(col * cell_w) + 2
        ry = int(row * cell_h) + 2
        rw = max(1, int(cell_w) - 4)
        rh = max(1, int(cell_h) - 4)
        stripes = getattr(self, "_grid_highlight", None)
        stripe_parent = getattr(self, "_grid_highlight_parent", None)
        if stripes is not None and stripe_parent is not container_widget:
            self._clear_grid_highlight()
            stripes = None
        if stripes is None:
            try:
                stripes = tuple(
                    tk.Frame(
                        container_widget,
                        bg=GRID_HIGHLIGHT_COLOR,
                        bd=0, highlightthickness=0,
                    )
                    for _ in range(4)
                )
            except tk.TclError:
                return
            self._grid_highlight = stripes
            self._grid_highlight_parent = container_widget
        top, bottom, left, right = stripes
        bw = 2  # border thickness
        try:
            top.place(x=rx, y=ry, width=rw, height=bw)
            bottom.place(x=rx, y=ry + rh - bw, width=rw, height=bw)
            left.place(x=rx, y=ry, width=bw, height=rh)
            right.place(x=rx + rw - bw, y=ry, width=bw, height=rh)
            for stripe in stripes:
                stripe.lift()
        except tk.TclError:
            self._clear_grid_highlight()
            return
        self._grid_highlight_key = cache_key

    def _clear_grid_highlight(self) -> None:
        stripes = getattr(self, "_grid_highlight", None)
        if stripes is not None:
            for stripe in stripes:
                try:
                    stripe.destroy()
                except tk.TclError:
                    pass
        self._grid_highlight = None
        self._grid_highlight_parent = None
        self._grid_highlight_key = None
