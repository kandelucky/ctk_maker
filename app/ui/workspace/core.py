"""Workspace — the canvas editor where the user drags and arranges widgets.

Owns:
- Top tool bar (Select / Hand mode toggles)
- Canvas with fixed-size document rectangle, dot grid, and CTk scrollbars
- Bottom status bar (zoom controls + readout + font-scale warning)
- Widget drag / resize / keyboard nudge / delete / context menu
- Event-bus subscriptions that turn model changes into canvas updates

Coordinate systems:
- **Logical** coordinates live in `node.properties["x"/"y"/"width"/"height"]`
  and are zoom-independent (single source of truth).
- **Canvas** coordinates are logical * zoom + DOCUMENT_PADDING.
- **Screen** (root) coordinates arrive on mouse events; helpers convert
  them via `canvas.canvasx/canvasy` to canvas coords, then to logical.
"""

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from app.core.commands import (
    AddWidgetCommand,
    BulkAddCommand,
    ChangePropertyCommand,
    DeleteMultipleCommand,
    DeleteWidgetCommand,
    RenameCommand,
    ZOrderCommand,
    build_bulk_add_entries,
)
from app.core.logger import log_error
from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.ui.dialogs import RenameDialog
from app.ui.selection_controller import SelectionController
from app.ui.zoom_controller import ZoomController
from app.ui.workspace.chrome import (
    CHROME_TAG,
    ChromeManager,
)
from app.ui.workspace.controls import (
    TOOL_CURSORS,
    TOOL_HAND,
    WorkspaceControls,
)
from app.ui.workspace.drag import WidgetDragController
from app.ui.workspace.render import (
    CANVAS_OUTSIDE_BG,
    DOCUMENT_PADDING,
    Renderer,
)
from app.ui.workspace.layout_overlay import (
    LayoutOverlayManager,
    _child_manager_kwargs,  # noqa: F401 — re-exported for tests
    _forget_current_manager,  # noqa: F401 — re-exported for tests
    _strip_layout_keys,
)
from app.ui.workspace.widget_lifecycle import WidgetLifecycle
from app.widgets.layout_schema import normalise_layout_type
from app.widgets.registry import get_descriptor

# ---- Drag + canvas ----------------------------------------------------------
DRAG_THRESHOLD = 5
# Canvas layout + grid constants live in ``render.py``; re-imported
# below through the ``Renderer`` module so ``_build_canvas`` can
# pass ``DOCUMENT_PADDING`` on to ``ZoomController``.

# Chrome constants live in ``chrome.py``; ``CHROME_TAG`` is
# re-imported above because ``_on_canvas_click`` still peeks at it.
# Tool / pan / status-bar constants live in ``controls.py``;
# ``TOOL_HAND`` + ``TOOL_CURSORS`` are re-imported above because
# ``default_tool_cursor`` + canvas event handlers still read them.


class Workspace(ctk.CTkFrame):
    """Canvas editor panel.

    Composed of three stacked regions:
        - top tool bar        (Select / Hand tool buttons)
        - canvas + scrollbars (document, grid, widgets, selection handles)
        - bottom status bar   (zoom controls + font-scale warning)

    The class is intentionally one big orchestrator — it holds the Tk
    bindings for widget drag/resize/arrow-nudge/delete plus the event-bus
    wiring that turns model changes into canvas renders.
    """

    def __init__(self, master, project: Project):
        super().__init__(master)
        self.project = project
        self.widget_views: dict[str, tuple] = {}

        self._init_state()
        self.controls = WorkspaceControls(self)
        self.controls.build_tool_bar()
        self._build_canvas()
        self.controls.build_status_bar()
        self._subscribe_events()

        self.after(0, self._redraw_document)
        self.after(0, self.controls.bind_keys)

    # ------------------------------------------------------------------
    # __init__ helpers
    # ------------------------------------------------------------------
    def _init_state(self) -> None:
        self.zoom: ZoomController | None = None  # set in _build_canvas
        # Mirrors main_window's dirty flag so the canvas title strip
        # can show a trailing "*" next to the project name.
        self._dirty: bool = False
        # Sidecar managers — all built in __init__ once core is
        # wired. ``controls`` owns tool state + pan + keybindings;
        # ``renderer`` / ``chrome`` / ``drag_controller`` are wired
        # in ``_build_canvas`` once the canvas exists.
        self.controls: WorkspaceControls | None = None
        self.chrome: ChromeManager | None = None
        self.drag_controller: WidgetDragController | None = None
        self.renderer: Renderer | None = None

        # Shared tk.StringVar per radio-button `group` name so multiple
        # CTkRadioButton widgets with the same group name coordinate
        # their selection state like a real radio group. StringVar is
        # used (not IntVar) because CTk's `.deselect()` sets the
        # variable to "" which blows up an IntVar's .get().
        self._radio_groups: dict[str, tk.StringVar] = {}
        # Per-widget string value within its group (assigned on first
        # bind — encoded as "r<n>" for readability in the exporter).
        self._radio_values: dict[str, str] = {}
        self._radio_group_counts: dict[str, int] = {}

        # Composite widgets (e.g. CTkScrollableFrame) expose a
        # different outer container for canvas embedding + event
        # binding than the widget stored in `widget_views`. Absent
        # entries mean "outer == inner" (the default).
        self._anchor_views: dict[str, tk.Widget] = {}

    def _build_canvas(self) -> None:
        container = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        container.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            container, bg=CANVAS_OUTSIDE_BG, highlightthickness=0,
        )
        self.vscroll = ctk.CTkScrollbar(
            container, orientation="vertical",
            command=self.canvas.yview,
            width=10, corner_radius=4,
            fg_color="transparent",
            button_color="#3a3a3a",
            button_hover_color="#4a4a4a",
        )
        self.hscroll = ctk.CTkScrollbar(
            container, orientation="horizontal",
            command=self.canvas.xview,
            height=10, corner_radius=4,
            fg_color="transparent",
            button_color="#3a3a3a",
            button_hover_color="#4a4a4a",
        )
        self.canvas.configure(
            yscrollcommand=self.vscroll.set,
            xscrollcommand=self.hscroll.set,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vscroll.grid(row=0, column=1, sticky="ns", padx=(2, 0))
        self.hscroll.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        self.zoom = ZoomController(
            self.canvas, self.widget_views, self.project,
            document_padding=DOCUMENT_PADDING,
            on_zoom_changed=self._after_zoom_changed,
        )

        from app.ui.workspace.controls import TOOL_EDIT
        self.selection = SelectionController(
            self.canvas, self.project, self.widget_views,
            zoom_provider=lambda: self.zoom.value,
            anchor_views=self._anchor_views,
            handles_enabled=lambda: self._tool == TOOL_EDIT,
        )
        # Layout manager switching + weight / manager-kwargs helpers.
        self.layout_overlay = LayoutOverlayManager(self)
        # Per-document chrome (title strip, drag, settings / close).
        self.chrome = ChromeManager(self)
        # Widget drag / reparent gesture handler.
        self.drag_controller = WidgetDragController(self)
        # Widget add / remove / reparent / z-order / visibility handler.
        self.lifecycle = WidgetLifecycle(self)
        # Canvas rendering — document rect + builder grid +
        # visibility mask. Declared last so every other sidecar is
        # alive before the first redraw fires.
        self.renderer = Renderer(self)

        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Button-2>", self.controls.on_middle_press)
        self.canvas.bind("<B2-Motion>", self.controls.on_middle_motion)
        self.canvas.bind(
            "<ButtonRelease-2>", self.controls.on_middle_release,
        )
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Control-MouseWheel>", self.zoom.handle_ctrl_wheel)
        self.canvas.bind("<Button-3>", self._on_canvas_right_click)

    def _after_zoom_changed(self) -> None:
        """Callback invoked by ZoomController after a zoom update +
        apply_all. Redraws the document rect / grid and refreshes
        selection chrome around the currently selected widget."""
        self._redraw_document()
        if hasattr(self, "selection"):
            self.selection.update()

    def _subscribe_events(self) -> None:
        bus = self.project.event_bus
        self.lifecycle.subscribe(bus)
        bus.subscribe("property_changed", self._on_property_changed)
        bus.subscribe("selection_changed", self._on_selection_changed)
        bus.subscribe("palette_drop_request", self._on_palette_drop)
        bus.subscribe("document_resized", self._on_document_resized)
        bus.subscribe("project_renamed", self._on_project_renamed)
        bus.subscribe("dirty_changed", self._on_dirty_changed)
        bus.subscribe("widget_renamed", self._on_any_widget_renamed)
        bus.subscribe(
            "active_document_changed",
            self._on_active_document_changed,
        )
        bus.subscribe("documents_reordered", self._on_documents_reordered)
        bus.subscribe(
            "document_position_changed",
            self._on_document_position_changed,
        )

    def _on_active_document_changed(self, *_args, **_kwargs) -> None:
        # Add / remove / active-switch of a document changes which
        # chrome strip is highlighted and, on add/remove, the total
        # scroll region. A full redraw covers both cheaply.
        self._redraw_document()

    def _on_documents_reordered(self, *_args, **_kwargs) -> None:
        # Send-to-Back / Bring-to-Front swap the drawing order; a
        # full redraw rebuilds the canvas stack in the new order.
        self._redraw_document()

    def _on_document_position_changed(self, *_args, **_kwargs) -> None:
        # MoveDocumentCommand undo/redo path — mirror the live drag:
        # redraw background/chrome, re-place every widget against the
        # new canvas offset, refresh selection chrome if any.
        self._redraw_document()
        self.zoom.apply_all()
        if self.project.selected_id:
            self.selection.update()

    def _on_any_widget_renamed(
        self, widget_id: str, _new_name: str,
    ) -> None:
        # Window renames retarget the active document's title —
        # repaint the canvas chrome so the new title shows up.
        from app.core.project import WINDOW_ID
        if widget_id == WINDOW_ID:
            self._draw_window_chrome()

    def _on_project_renamed(self, *_args, **_kwargs) -> None:
        # The canvas title strip mirrors `project.name`; New / Open /
        # Save As all publish this event so the chrome repaints
        # without needing a full document rebuild.
        self._draw_window_chrome()

    def _on_dirty_changed(self, dirty, *_args, **_kwargs) -> None:
        new_dirty = bool(dirty)
        if new_dirty == self._dirty:
            return
        self._dirty = new_dirty
        self._draw_window_chrome()

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _input_focused(self) -> bool:
        return isinstance(self.focus_get(), (tk.Entry, tk.Text))

    def _effective_locked(self, widget_id: str) -> bool:
        """True if the node or any ancestor is locked. Locked nodes
        still render and can be selected, but reject drag / resize /
        arrow-nudge / delete so background containers can't be
        touched by accident."""
        node = self.project.get_widget(widget_id)
        while node is not None:
            if getattr(node, "locked", False):
                return True
            node = node.parent
        return False

    def _schedule_selection_redraw(self) -> None:
        # Skip while a drag or resize is in flight so we don't fight
        # the live-preview handles.
        dragging = (
            self.drag_controller is not None
            and self.drag_controller.is_dragging()
        )
        if not dragging and not self.selection.is_resizing():
            self.after(10, self.selection.draw)

    def _reapply_child_manager(self, widget_id: str) -> None:
        """Re-pack / re-place the child widget through its parent's
        layout manager without destroying it. Used by property-change
        branches (grid_row / grid_column / grid_sticky / stretch) that
        just need a fresh ``.pack()`` / ``.grid()`` call with the new
        kwargs. No-op if the widget has no parent or no view yet.
        """
        node = self.project.get_widget(widget_id)
        if node is None or node.parent is None:
            return
        entry = self.widget_views.get(widget_id)
        if entry is None:
            return
        widget, _ = entry
        descriptor = get_descriptor(node.widget_type)
        anchor_widget = (
            descriptor.canvas_anchor(widget)
            if descriptor is not None else widget
        )
        self.layout_overlay.apply_child_manager(
            anchor_widget, node.parent, node,
        )

    # ==================================================================
    # Document rectangle + coordinate helpers
    # ==================================================================
    def _screen_to_canvas(self, x_root: int, y_root: int) -> tuple[float, float]:
        vx = x_root - self.canvas.winfo_rootx()
        vy = y_root - self.canvas.winfo_rooty()
        return self.canvas.canvasx(vx), self.canvas.canvasy(vy)

    def _widget_canvas_bbox(
        self, widget,
    ) -> tuple[int, int, int, int] | None:
        """Return the widget's bbox in canvas coords (works for any
        widget regardless of nesting)."""
        try:
            rx = widget.winfo_rootx() - self.canvas.winfo_rootx()
            ry = widget.winfo_rooty() - self.canvas.winfo_rooty()
            w = widget.winfo_width()
            h = widget.winfo_height()
        except tk.TclError:
            return None
        if w <= 1 or h <= 1:
            return None
        cx1 = int(self.canvas.canvasx(rx))
        cy1 = int(self.canvas.canvasy(ry))
        return cx1, cy1, cx1 + w, cy1 + h

    def is_cursor_over_document(self, x_root: int, y_root: int) -> bool:
        """Return True when the screen point is inside any document's
        rectangle on the canvas. Used by the palette to colour its
        drag ghost so the user sees before release whether the drop
        will land.
        """
        canvas_rx = self.canvas.winfo_rootx()
        canvas_ry = self.canvas.winfo_rooty()
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        local_x = x_root - canvas_rx
        local_y = y_root - canvas_ry
        if not (0 <= local_x < canvas_w and 0 <= local_y < canvas_h):
            return False
        cx, cy = self._screen_to_canvas(x_root, y_root)
        return self._find_document_at_canvas(cx, cy) is not None

    def _find_document_at_canvas(self, canvas_x: float, canvas_y: float):
        """Return the Document whose rectangle contains the canvas
        point, or None when the point is in empty workspace space.
        """
        zoom = self.zoom.value
        pad = DOCUMENT_PADDING
        for doc in self.project.documents:
            dx1 = pad + int(doc.canvas_x * zoom)
            dy1 = pad + int(doc.canvas_y * zoom)
            dx2 = dx1 + int(doc.width * zoom)
            dy2 = dy1 + int(doc.height * zoom)
            if dx1 <= canvas_x <= dx2 and dy1 <= canvas_y <= dy2:
                return doc
        return None

    def _find_container_at(
        self, canvas_x: float, canvas_y: float, exclude_id: str | None = None,
    ):
        """Find the deepest container WidgetNode whose canvas bbox
        contains (canvas_x, canvas_y). Returns None for plain-canvas
        drops. `exclude_id` skips a specific node (and the search
        ignores its subtree so a widget can't drop into itself)."""
        found = None
        found_depth = -1

        def walk(node, depth: int) -> None:
            nonlocal found, found_depth
            if exclude_id is not None and node.id == exclude_id:
                return  # skip self + entire subtree
            descriptor = get_descriptor(node.widget_type)
            if descriptor is None:
                return
            if getattr(descriptor, "is_container", False):
                entry = self.widget_views.get(node.id)
                if entry is not None:
                    widget, _ = entry
                    bbox = self._widget_canvas_bbox(widget)
                    if bbox is not None:
                        x1, y1, x2, y2 = bbox
                        if x1 <= canvas_x <= x2 and y1 <= canvas_y <= y2:
                            if depth > found_depth:
                                found = node
                                found_depth = depth
            for child in node.children:
                walk(child, depth + 1)

        for root in self.project.root_widgets:
            walk(root, 0)
        return found

    # Rendering (document rect + grid + visibility mask) lives in
    # ``render.py``; these thin delegators keep the many internal
    # callers working unchanged.

    def _redraw_document(self) -> None:
        if self.renderer is not None:
            self.renderer.redraw()

    def _update_widget_visibility_across_docs(self) -> None:
        if self.renderer is not None:
            self.renderer.update_visibility_across_docs()

    def _on_canvas_configure(self, event=None) -> None:
        if self.renderer is not None:
            self.renderer.on_canvas_configure(event)

    def _on_document_resized(self, *args) -> None:
        if self.renderer is not None:
            self.renderer.on_document_resized(*args)

    # ==================================================================
    # Top tool bar (Select / Hand)
    # ==================================================================
    # Tool bar, status bar, pan, keybindings all live in
    # ``controls.py`` now. Access the controller via
    # ``self.controls``; canvas event handlers still read
    # ``self._tool`` / ``self._pan_state`` through the properties
    # below so the existing call sites stay unchanged.

    @property
    def _tool(self) -> str:
        return self.controls.tool if self.controls is not None else ""

    @property
    def _pan_state(self):
        return (
            self.controls._pan_state if self.controls is not None else None
        )

    def _begin_pan(self, event) -> None:
        if self.controls is not None:
            self.controls.begin_pan(event)

    def _update_pan(self, event) -> None:
        if self.controls is not None:
            self.controls.update_pan(event)

    def _end_pan(self, event) -> None:
        if self.controls is not None:
            self.controls.end_pan(event)

    def _draw_window_chrome(self) -> None:
        # Chrome is painted per-document inside ``_redraw_document``;
        # this entry point is a thin passthrough kept for legacy
        # callers that want a chrome-only refresh.
        self._redraw_document()

    def default_tool_cursor(self) -> str:
        """Resolve the default cursor for the current tool — read by
        sibling controllers (e.g. ``ChromeManager``) that need to
        restore the tool's cursor after a hover state.
        """
        if self.controls is None:
            return ""
        return self.controls.default_cursor()

    def _on_arrow(self, dx: int, dy: int, fast: bool) -> str | None:
        sid = self.project.selected_id
        if sid is None or self._input_focused():
            return None
        if self._effective_locked(sid):
            return "break"
        node = self.project.get_widget(sid)
        if node is None:
            return None
        step = 10 if fast else 1
        try:
            x = int(node.properties.get("x", 0))
            y = int(node.properties.get("y", 0))
        except (ValueError, TypeError):
            x, y = 0, 0
        if dx:
            new_x = x + dx * step
            self.project.update_property(sid, "x", new_x)
            self.project.history.push(
                ChangePropertyCommand(
                    sid, "x", x, new_x, coalesce_key="nudge",
                ),
            )
        if dy:
            new_y = y + dy * step
            self.project.update_property(sid, "y", new_y)
            self.project.history.push(
                ChangePropertyCommand(
                    sid, "y", y, new_y, coalesce_key="nudge",
                ),
            )
        return "break"

    def _on_delete(self, _event=None) -> str | None:
        if self._input_focused():
            return None
        selected = set(self.project.selected_ids)
        if not selected:
            return None
        if len(selected) > 1:
            return self._delete_multi(selected)
        sid = next(iter(selected))
        if self._effective_locked(sid):
            messagebox.showinfo(
                title="Widget locked",
                message=(
                    "This widget is locked. Unlock it from the Object "
                    "Tree (padlock icon) before deleting."
                ),
                parent=self.winfo_toplevel(),
            )
            return "break"
        node = self.project.get_widget(sid)
        if node is None:
            return None
        descriptor = get_descriptor(node.widget_type)
        type_label = descriptor.display_name if descriptor else node.widget_type
        confirmed = messagebox.askyesno(
            title="Delete widget",
            message=f"Delete this {type_label}?",
            icon="warning",
            parent=self.winfo_toplevel(),
        )
        if not confirmed:
            return "break"
        snapshot = node.to_dict()
        parent_id = node.parent.id if node.parent is not None else None
        siblings = (
            node.parent.children if node.parent is not None
            else self.project.root_widgets
        )
        try:
            index = siblings.index(node)
        except ValueError:
            index = len(siblings)
        owning_doc = self.project.find_document_for_widget(sid)
        document_id = owning_doc.id if owning_doc is not None else None
        self.project.remove_widget(sid)
        self.project.history.push(
            DeleteWidgetCommand(snapshot, parent_id, index, document_id),
        )
        return "break"

    def _delete_multi(self, selected: set[str]) -> str:
        # Any locked widget in the set blocks the whole delete so the
        # user doesn't half-succeed and wonder which ones stayed.
        locked_ids = [
            nid for nid in selected if self._effective_locked(nid)
        ]
        if locked_ids:
            messagebox.showinfo(
                title="Widgets locked",
                message=(
                    f"{len(locked_ids)} of the selected widgets are locked. "
                    "Unlock them from the Object Tree before deleting."
                ),
                parent=self.winfo_toplevel(),
            )
            return "break"
        count = len(selected)
        confirmed = messagebox.askyesno(
            title="Delete widgets",
            message=f"Delete {count} selected widgets?",
            icon="warning",
            parent=self.winfo_toplevel(),
        )
        if not confirmed:
            return "break"
        # Walk top-down so per-id parent + sibling index snapshots
        # reflect the pre-removal state; skip descendants whose
        # ancestor is also selected (the parent delete covers them).
        entries: list[tuple[dict, str | None, int, str | None]] = []
        for node in self.project.iter_all_widgets():
            if node.id not in selected:
                continue
            ancestor = node.parent
            covered = False
            while ancestor is not None:
                if ancestor.id in selected:
                    covered = True
                    break
                ancestor = ancestor.parent
            if covered:
                continue
            parent_id = (
                node.parent.id if node.parent is not None else None
            )
            siblings = (
                node.parent.children if node.parent is not None
                else self.project.root_widgets
            )
            try:
                index = siblings.index(node)
            except ValueError:
                index = len(siblings)
            owning_doc = self.project.find_document_for_widget(node.id)
            document_id = owning_doc.id if owning_doc is not None else None
            entries.append((node.to_dict(), parent_id, index, document_id))
        for snapshot, _parent_id, _index, _doc_id in entries:
            self.project.remove_widget(snapshot["id"])
        if entries:
            self.project.history.push(DeleteMultipleCommand(entries))
        return "break"

    def _on_escape(self, _event=None) -> str | None:
        if self.project.selected_id is None:
            return None
        self.project.select_widget(None)
        return "break"

    # ==================================================================
    # Radio button group coordination
    # ==================================================================
    def _get_radio_init_kwargs(self, node) -> dict | None:
        """Compute the `variable` + `value` constructor kwargs for a
        CTkRadioButton node that belongs to a named group. Returns
        None for standalone radios (empty group).
        """
        group = str(node.properties.get("group") or "").strip()
        if not group:
            return None
        var = self._radio_groups.setdefault(
            group, tk.StringVar(master=self, value=""),
        )
        if node.id not in self._radio_values:
            next_val = self._radio_group_counts.get(group, 0) + 1
            self._radio_group_counts[group] = next_val
            self._radio_values[node.id] = f"r{next_val}"
        value = self._radio_values[node.id]
        return {"variable": var, "value": value}

    def _sync_radio_initial(self, widget, node) -> None:
        """Push the radio's `initially_checked` bool onto the shared
        group variable. Standalone radios fall through to the
        descriptor's `apply_state` select/deselect path.
        """
        if not isinstance(widget, ctk.CTkRadioButton):
            return
        group = str(node.properties.get("group") or "").strip()
        if not group or group not in self._radio_groups:
            return
        var = self._radio_groups[group]
        value = self._radio_values.get(node.id)
        if value is None:
            return
        try:
            if node.properties.get("initially_checked"):
                var.set(value)
            elif var.get() == value:
                var.set("")
        except Exception:
            log_error("workspace._sync_radio_initial")

    def _unbind_radio_group(self, widget_id: str) -> None:
        self._radio_values.pop(widget_id, None)

    def _sync_composite_size(self, widget_id: str, node) -> None:
        """Push width/height onto the outer anchor container for
        composite widgets. Top-level uses `canvas.itemconfigure` on
        the window item; nested uses `place_configure`.
        """
        anchor = self._anchor_views.get(widget_id)
        if anchor is None:
            return
        _widget, window_id = self.widget_views[widget_id]
        try:
            lw = int(node.properties.get("width", 0) or 0)
            lh = int(node.properties.get("height", 0) or 0)
        except (TypeError, ValueError):
            return
        if lw <= 0 or lh <= 0:
            return
        zw = max(1, int(lw * self.zoom.value))
        zh = max(1, int(lh * self.zoom.value))
        try:
            if window_id is not None:
                self.canvas.itemconfigure(window_id, width=zw, height=zh)
            elif anchor.winfo_manager() == "place":
                anchor.place_configure(width=zw, height=zh)
        except tk.TclError:
            pass

    # ==================================================================
    # Widget lifecycle delegation
    # ==================================================================
    # Event-bus handlers for widget_added / removed / reparented /
    # z_changed / visibility / locked live in ``widget_lifecycle.py``
    # now; the workspace holds a ``self.lifecycle`` instance and the
    # property-change path below delegates the destroy-and-rebuild
    # recreate flow through it.

    def _on_property_changed(self, widget_id: str, prop_name: str, value) -> None:
        from app.core.project import WINDOW_ID
        if widget_id == WINDOW_ID:
            # Window properties don't feed a real CTk widget — the
            # canvas shows the form through its rectangle, chrome
            # and grid. These keys trigger a redraw of the document
            # surface; everything else is window metadata only.
            if prop_name in (
                "fg_color", "grid_style", "grid_color", "grid_spacing",
                "layout_type",
            ):
                self._redraw_document()
            elif prop_name == "accent_color":
                # Only the chrome title uses the accent — no need to
                # repaint the document body.
                self._draw_window_chrome()
            return
        if prop_name in (
            "layout_type", "layout_spacing", "grid_rows", "grid_cols",
        ):
            # Container-level layout changes — manager swap, spacing
            # tweak, or grid dimensions — re-pack / re-place every
            # child through the new config, then redraw overlays.
            self.layout_overlay.rearrange_container_children(widget_id)
            self._redraw_document()
            if self.project.selected_id is not None:
                self._schedule_selection_redraw()
            return
        if prop_name in ("grid_sticky", "grid_row", "grid_column", "stretch"):
            # Per-child layout tweak — re-apply the child's geometry
            # manager in place. ``grid_*`` moves the child in its
            # parent grid; ``stretch`` just swaps pack fill/expand
            # kwargs. Either way no sibling shift is needed.
            self._reapply_child_manager(widget_id)
            if widget_id == self.project.selected_id:
                self._schedule_selection_redraw()
            return
        if widget_id not in self.widget_views:
            return
        widget, window_id = self.widget_views[widget_id]
        node = self.project.get_widget(widget_id)

        if prop_name in ("x", "y") and node is not None:
            try:
                x = int(node.properties.get("x", 0))
                y = int(node.properties.get("y", 0))
                if window_id is not None:
                    owning_doc = self.project.find_document_for_widget(
                        widget_id,
                    )
                    cx, cy = self.zoom.logical_to_canvas(
                        x, y, document=owning_doc,
                    )
                    self.canvas.coords(window_id, cx, cy)
                elif widget.winfo_manager() == "place":
                    widget.place_configure(
                        x=int(x * self.zoom.value),
                        y=int(y * self.zoom.value),
                    )
            except Exception:
                log_error("workspace._on_property_changed x/y coords")
            if widget_id == self.project.selected_id:
                self._schedule_selection_redraw()
            return

        descriptor = get_descriptor(node.widget_type) if node else None

        # Init-only kwargs (e.g. CTkProgressBar.orientation) can't be
        # reconfigured live — destroy and recreate the widget subtree.
        recreate = (
            getattr(descriptor, "recreate_triggers", None)
            if descriptor else None
        )
        if recreate and prop_name in recreate:
            # Pre-recreate hook — e.g. swap w/h when orientation flips.
            updates = descriptor.on_prop_recreate(prop_name, node.properties)
            for k, v in updates.items():
                if node.properties.get(k) != v:
                    self.project.update_property(widget_id, k, v)
            self.lifecycle.on_widget_removed(widget_id)
            self.lifecycle.create_widget_subtree(node)
            if widget_id == self.project.selected_id:
                self._schedule_selection_redraw()
            return

        triggers = (
            getattr(descriptor, "derived_triggers", None) if descriptor else None
        )
        if (descriptor and triggers and prop_name in triggers
                and hasattr(descriptor, "compute_derived")):
            try:
                derived = descriptor.compute_derived(node.properties)
            except Exception:
                log_error(f"{node.widget_type}.compute_derived")
                derived = {}
            for k, v in derived.items():
                if node.properties.get(k) != v:
                    self.project.update_property(widget_id, k, v)

        try:
            if descriptor is not None:
                transformed = descriptor.transform_properties(
                    _strip_layout_keys(node.properties),
                )
                if transformed:
                    widget.configure(**transformed)
                descriptor.apply_state(widget, node.properties)
                # Radio group: reflect `initially_checked` changes on
                # the shared IntVar — `group` changes themselves trip
                # recreate_triggers above, not here.
                self._sync_radio_initial(widget, node)
                owning_doc = self.project.find_document_for_widget(widget_id)
                self.zoom.apply_to_widget(
                    widget, window_id, node.properties,
                    document=owning_doc,
                )
                # Composite widgets (CTkScrollableFrame) need the
                # canvas item / place size updated separately because
                # their inner widget's configure doesn't reach the
                # outer container.
                if widget_id in self._anchor_views:
                    self._sync_composite_size(widget_id, node)
            else:
                widget.configure(**{prop_name: value})
        except Exception:
            log_error(
                f"workspace._on_property_changed widget.configure {prop_name}",
            )
        # CTkButton's text label occasionally slips behind its rounded
        # background when corner_radius approaches half the widget
        # height; lift it back so the text stays visible.
        text_label = getattr(widget, "_text_label", None)
        if text_label is not None:
            try:
                text_label.lift()
            except tk.TclError:
                pass
        if prop_name in ("width", "height") and node is not None:
            lt = normalise_layout_type(
                node.properties.get("layout_type", "place"),
            )
            if lt == "grid" and getattr(descriptor, "is_container", False):
                self.layout_overlay.rearrange_container_children(widget_id)
        if widget_id == self.project.selected_id:
            self._schedule_selection_redraw()

    def _on_palette_drop(
        self, entry, descriptor, x_root: int, y_root: int,
    ) -> None:
        canvas_rx = self.canvas.winfo_rootx()
        canvas_ry = self.canvas.winfo_rooty()
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        local_x = x_root - canvas_rx
        local_y = y_root - canvas_ry
        if not (0 <= local_x < canvas_w and 0 <= local_y < canvas_h):
            return

        cx, cy = self._screen_to_canvas(x_root, y_root)
        container_node = self._find_container_at(cx, cy)

        properties = dict(descriptor.default_properties)
        for key, value in getattr(entry, "preset_overrides", ()) or ():
            properties[key] = value
        if container_node is None:
            # Top-level drop: figure out which document the cursor
            # is over and add the widget to that doc's tree. Drops
            # that land outside every document are rejected — with
            # multi-document canvases, silently falling through to
            # the active form lands widgets on the wrong surface.
            target_doc = self._find_document_at_canvas(cx, cy)
            if target_doc is None:
                return
            self.project.set_active_document(target_doc.id)
            lx, ly = self.zoom.canvas_to_logical(
                cx, cy, document=target_doc,
            )
            properties["x"] = max(0, lx)
            properties["y"] = max(0, ly)
            parent_id = None
        else:
            # Nested drop — coords relative to the container widget.
            container_widget, _ = self.widget_views[container_node.id]
            zoom = self.zoom.value or 1.0
            rel_x = (x_root - container_widget.winfo_rootx()) / zoom
            rel_y = (y_root - container_widget.winfo_rooty()) / zoom
            parent_layout = normalise_layout_type(
                container_node.properties.get("layout_type", "place"),
            )
            # Non-place containers ignore child x/y at render time, so
            # writing cursor-relative coords there would just land as
            # stale Inspector values. Clamp to 0 / 0 for vbox / hbox
            # / grid drops; ``place`` parents keep the pixel offset.
            if parent_layout == "place":
                properties["x"] = max(0, int(rel_x))
                properties["y"] = max(0, int(rel_y))
            else:
                properties["x"] = 0
                properties["y"] = 0
            parent_id = container_node.id

        # Grid target: snap to whatever cell is under the cursor so
        # the drop lands visibly where the user aimed. Sets the cell
        # BEFORE add_widget so the initial render uses it.
        if container_node is not None:
            if normalise_layout_type(
                container_node.properties.get("layout_type", "place"),
            ) == "grid":
                row, col = self.drag_controller._grid_cell_at(
                    container_node, cx, cy,
                )
                properties["grid_row"] = row
                properties["grid_column"] = col
        node = WidgetNode(
            widget_type=descriptor.type_name,
            properties=properties,
        )
        if getattr(entry, "default_name", None):
            node.name = entry.default_name
        self.project.add_widget(node, parent_id=parent_id)
        self.project.select_widget(node.id)
        owning_doc = self.project.find_document_for_widget(node.id)
        document_id = owning_doc.id if owning_doc is not None else None
        self.project.history.push(
            AddWidgetCommand(
                node.to_dict(), parent_id, document_id=document_id,
            ),
        )

    def _on_selection_changed(self, _widget_id: str | None) -> None:
        self.selection.draw()

    # ==================================================================
    # Widget mouse events (press / motion / release / right-click)
    # ==================================================================
    def _bind_widget_events(self, widget, nid: str) -> None:
        # Some composite CTk widgets (e.g. CTkSegmentedButton) raise
        # NotImplementedError from `.bind()` because they compose
        # multiple inner clickable widgets — the children loop below
        # is what actually wires the handlers for those.
        def _safe_bind(seq, cb):
            try:
                widget.bind(seq, cb, add="+")
            except NotImplementedError:
                pass
            except tk.TclError:
                pass

        _safe_bind(
            "<ButtonPress-1>",
            lambda e, n=nid: self.drag_controller.on_press(e, n),
        )
        _safe_bind(
            "<B1-Motion>",
            lambda e, n=nid: self.drag_controller.on_motion(e, n),
        )
        _safe_bind(
            "<ButtonRelease-1>",
            lambda e, n=nid: self.drag_controller.on_release(e, n),
        )
        _safe_bind("<Button-2>", self.controls.on_middle_press)
        _safe_bind("<B2-Motion>", self.controls.on_middle_motion)
        _safe_bind("<ButtonRelease-2>", self.controls.on_middle_release)
        # Ctrl+wheel forwards to ZoomController so zoom works even
        # when the pointer happens to hover a widget instead of empty
        # canvas area.
        _safe_bind("<Control-MouseWheel>", self.zoom.handle_ctrl_wheel)
        _safe_bind(
            "<Button-3>",
            lambda e, n=nid: self._on_widget_right_click(e, n),
        )
        try:
            widget.configure(cursor="fleur")
        except (tk.TclError, NotImplementedError, ValueError):
            pass
        for child in widget.winfo_children():
            self._bind_widget_events(child, nid)

    # Widget drag / reparent logic lives in ``drag.py`` —
    # ``self.drag_controller`` owns the gesture state.

    def _on_canvas_right_click(self, event) -> str:
        # Find the doc under the cursor — paste + Select All only make
        # sense when anchored to one. Empty workspace area shows no menu.
        cx, cy = self._screen_to_canvas(event.x_root, event.y_root)
        doc = self._find_document_at_canvas(cx, cy)
        if doc is None:
            return "break"
        if doc.id != self.project.active_document_id:
            self.project.set_active_document(doc.id)
        lx, ly = self.zoom.canvas_to_logical(cx, cy, document=doc)
        menu = tk.Menu(self.winfo_toplevel(), tearoff=0)
        paste_state = "normal" if self.project.clipboard else "disabled"
        menu.add_command(
            label="Paste",
            command=lambda d=doc, x=lx, y=ly: self._paste_at_canvas(d, x, y),
            state=paste_state,
        )
        menu.add_separator()
        top_ids = {n.id for n in doc.root_widgets}
        select_state = "normal" if top_ids else "disabled"
        menu.add_command(
            label="Select All",
            command=lambda d=doc: self._select_all_in_doc(d),
            state=select_state,
        )
        deselect_state = (
            "normal" if self.project.selected_ids else "disabled"
        )
        menu.add_command(
            label="Deselect All",
            command=lambda: self.project.select_widget(None),
            state=deselect_state,
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _paste_at_canvas(self, doc, logical_x: int, logical_y: int) -> None:
        if not self.project.clipboard:
            return
        new_ids = self.project.paste_from_clipboard(
            parent_id=None,
            base_position=(logical_x, logical_y),
        )
        if not new_ids:
            return
        entries = build_bulk_add_entries(self.project, new_ids)
        if entries:
            self.project.history.push(
                BulkAddCommand(entries, label="Paste"),
            )
        _ = doc  # active doc was set above; paste went there

    def _select_all_in_doc(self, doc) -> None:
        ids = {node.id for node in self._iter_doc_widgets(doc)}
        if not ids:
            return
        primary = next(iter(ids))
        self.project.set_multi_selection(ids, primary=primary)
        # Multi-select in Edit mode is ambiguous (resize handles, single-
        # widget property edits) — mirror the Ctrl+click auto-switch so
        # the tool reflects the selection state.
        from app.ui.workspace.controls import TOOL_EDIT, TOOL_SELECT
        if len(ids) > 1 and self.controls.tool == TOOL_EDIT:
            self.controls.set_tool(TOOL_SELECT)

    def _iter_doc_widgets(self, doc):
        stack = list(doc.root_widgets)
        while stack:
            node = stack.pop()
            yield node
            stack.extend(node.children)

    def _on_widget_right_click(self, event, nid: str) -> str:
        # Preserve multi-selection when right-clicking one of its members
        # — calling select_widget here would collapse the set to a single
        # primary and make group Delete impossible from the context menu.
        multi_active = (
            len(self.project.selected_ids) > 1
            and nid in self.project.selected_ids
        )
        menu = tk.Menu(self.winfo_toplevel(), tearoff=0)
        if multi_active:
            count = len(self.project.selected_ids)
            menu.add_command(
                label=f"Copy {count} widgets",
                command=self._copy_selection,
            )
            menu.add_command(
                label=f"Duplicate {count} widgets",
                command=self._duplicate_selection,
            )
            menu.add_separator()
            menu.add_command(
                label=f"Delete {count} widgets",
                command=self._on_delete,
            )
        else:
            self.project.select_widget(nid)
            menu.add_command(
                label="Copy",
                command=lambda: self._copy_single(nid),
            )
            paste_state = "normal" if self.project.clipboard else "disabled"
            menu.add_command(
                label="Paste",
                command=lambda: self._paste_at_widget(nid),
                state=paste_state,
            )
            menu.add_command(
                label="Duplicate",
                command=lambda: self._duplicate_with_history(nid),
            )
            menu.add_separator()
            menu.add_command(
                label="Rename",
                command=lambda: self._prompt_rename_widget(nid),
            )
            menu.add_command(label="Delete", command=self._on_delete)
            menu.add_separator()
            menu.add_command(
                label="Bring to Front",
                command=lambda: self._z_order_with_history(nid, "front"),
            )
            menu.add_command(
                label="Send to Back",
                command=lambda: self._z_order_with_history(nid, "back"),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _copy_selection(self) -> None:
        ids = self.project.selected_ids
        if not ids:
            return
        self.project.copy_to_clipboard(ids)

    def _copy_single(self, nid: str) -> None:
        self.project.copy_to_clipboard({nid})

    def _paste_at_widget(self, nid: str) -> None:
        if not self.project.clipboard:
            return
        node = self.project.get_widget(nid)
        if node is None:
            return
        descriptor = get_descriptor(node.widget_type)
        if descriptor is not None and getattr(
            descriptor, "is_container", False,
        ):
            parent_id: str | None = nid
        else:
            parent_id = node.parent.id if node.parent is not None else None
        new_ids = self.project.paste_from_clipboard(parent_id=parent_id)
        if not new_ids:
            return
        entries = build_bulk_add_entries(self.project, new_ids)
        if entries:
            self.project.history.push(
                BulkAddCommand(entries, label="Paste"),
            )

    def _duplicate_selection(self) -> None:
        ids = list(self.project.selected_ids)
        if not ids:
            return
        new_ids: list[str] = []
        for nid in ids:
            new_id = self.project.duplicate_widget(nid)
            if new_id is not None:
                new_ids.append(new_id)
        entries = build_bulk_add_entries(self.project, new_ids)
        if entries:
            self.project.history.push(
                BulkAddCommand(entries, label="Duplicate"),
            )

    def _duplicate_with_history(self, nid: str) -> None:
        new_id = self.project.duplicate_widget(nid)
        if new_id is None:
            return
        entries = build_bulk_add_entries(self.project, [new_id])
        if entries:
            self.project.history.push(
                BulkAddCommand(entries, label="Duplicate"),
            )

    def _z_order_with_history(self, nid: str, direction: str) -> None:
        node = self.project.get_widget(nid)
        if node is None:
            return
        siblings = (
            node.parent.children if node.parent is not None
            else self.project.root_widgets
        )
        try:
            old_index = siblings.index(node)
        except ValueError:
            return
        if direction == "front":
            self.project.bring_to_front(nid)
        else:
            self.project.send_to_back(nid)
        try:
            new_index = siblings.index(node)
        except ValueError:
            return
        if old_index == new_index:
            return
        parent_id = node.parent.id if node.parent is not None else None
        self.project.history.push(
            ZOrderCommand(nid, parent_id, old_index, new_index, direction),
        )

    def _prompt_rename_widget(self, nid: str) -> None:
        node = self.project.get_widget(nid)
        if node is None:
            return
        dialog = RenameDialog(self.winfo_toplevel(), node.name)
        if dialog.result and dialog.result != node.name:
            before = node.name
            self.project.rename_widget(nid, dialog.result)
            self.project.history.push(
                RenameCommand(nid, before, dialog.result),
            )

    # ==================================================================
    # Canvas mouse events (click / motion / release)
    # ==================================================================
    def _on_canvas_click(self, event) -> str | None:
        if event.widget is not self.canvas:
            return None
        # If the click landed on a chrome item (title bar strip,
        # settings icon, min/close glyphs), the tag_bind handlers
        # already processed it — do NOT run the default
        # deselect-everything behaviour which would undo the
        # selection the tag handler just set. `"current"` is tk's
        # special tag for the item the cursor is hovering over.
        for item in self.canvas.find_withtag("current"):
            if CHROME_TAG in self.canvas.gettags(item):
                return "break"
        if self._tool == TOOL_HAND:
            self._begin_pan(event)
            return "break"
        # Selection handles are now embedded widgets that capture
        # Button-1 directly, so canvas clicks can't land on them.
        # If the click landed on empty area of a non-active document,
        # switch to that doc before deselecting — otherwise clicking
        # into a background form does nothing and the user has to
        # tap the title bar to change focus.
        cx, cy = self._screen_to_canvas(event.x_root, event.y_root)
        doc = self._find_document_at_canvas(cx, cy)
        if doc is not None and doc.id != self.project.active_document_id:
            self.project.set_active_document(doc.id)
        self.project.select_widget(None)
        return None

    def _on_canvas_motion(self, event) -> str | None:
        # Chrome drag in progress wins over every other motion
        # handler — it needs every single Button-1 motion, even when
        # the cursor slips off the title bar items mid-gesture.
        if self.chrome is not None and self.chrome.is_dragging():
            return self.chrome.drive_drag(event)
        if self._tool == TOOL_HAND and self._pan_state is not None:
            self._update_pan(event)
            return "break"
        return None

    def _on_canvas_release(self, event) -> str | None:
        # Canvas-level release terminates any in-progress chrome drag
        # that started on a title bar but slipped off — same reason
        # the motion handler has a canvas-level fallback.
        if self.chrome is not None and self.chrome.is_dragging():
            self.chrome.end_drag(self.chrome.current_drag_doc_id())
            return "break"
        if self._tool == TOOL_HAND:
            self._end_pan(event)
            return "break"
        return None
