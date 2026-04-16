"""Widget drag-to-move + drag-to-reparent controller.

Holds the per-gesture drag state (``_drag``) and the three press /
motion / release handlers every canvas widget is bound to. The
controller owns the logic for:

- press      — capture the widget's starting logical x/y
- motion     — translate the mouse delta (zoom-adjusted) into x/y
               property updates; tripping the 5 px threshold before
               committing so click-without-drag stays silent
- release    — either record a single ``MoveCommand`` for the
               gesture or, if the widget was dropped on a different
               container / document, a ``ReparentCommand`` instead

Split out of the old monolithic ``workspace.py`` so drag logic lives
in one focused module. Core ``Workspace`` holds a single instance on
``self.drag_controller`` and wires widget bindings through it.
"""

from __future__ import annotations

import tkinter as tk

from app.core.commands import MoveCommand, ReparentCommand

DRAG_THRESHOLD = 5


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
        if drag is not None and drag.get("moved"):
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
        self._drag = None
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
