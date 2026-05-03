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
    BindHandlerCommand,
    BulkAddCommand,
    ChangePropertyCommand,
    DeleteMultipleCommand,
    DeleteWidgetCommand,
    RenameCommand,
    build_bulk_add_entries,
    paste_target_parent_id,
    push_zorder_history,
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
from app.widgets.layout_schema import (
    is_layout_container,
    normalise_layout_type,
    resolve_grid_drop_cell,
)
from app.widgets.registry import get_descriptor
from app.core.platform_compat import MOD_KEY, MOD_LABEL_PLUS

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

        # Phase 1 binding cache. ``widget_id → {prop_name: var_id}``.
        # Tracks which property of which widget is currently wired to
        # which variable. Used by ``_handle_var_binding_change`` to
        # detect three transitions that need a widget recreate:
        # 1. literal → bound (new wiring)
        # 2. bound → literal (drop wiring)
        # 3. bound → bound to a different variable (rewire)
        # The recreate path runs through ``lifecycle.create_widget_subtree``
        # so the descriptor's ``init_kwargs`` plumbing picks up the
        # live ``tk.Variable`` cleanly, no special-case configure
        # logic needed.
        self._bound_props_cache: dict[str, dict[str, str]] = {}

        # Marquee selection (drag-rect on empty canvas) state. ``None``
        # when no marquee is in progress; otherwise carries start
        # coords, the dashed rect canvas item id, and the modifier
        # flags so the release handler can apply the right action.
        self._marquee_state: dict | None = None

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
        self.canvas.bind(f"<{MOD_KEY}-MouseWheel>", self.zoom.handle_ctrl_wheel)
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
        bus.subscribe("widget_added", self._seed_binding_cache_on_add)
        bus.subscribe("widget_removed", self._drop_binding_cache_on_remove)
        bus.subscribe(
            "variable_type_changed", self._on_variable_type_changed,
        )
        bus.subscribe(
            "font_defaults_changed",
            lambda *_a, **_k: self._reapply_fonts_to_all_widgets(),
        )
        bus.subscribe("selection_changed", self._on_selection_changed)
        bus.subscribe(
            "widget_group_changed",
            lambda *_a, **_k: self.selection.draw(),
        )
        bus.subscribe("palette_drop_request", self._on_palette_drop)
        bus.subscribe("component_drop_request", self._on_component_drop)
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
        # Center viewport on the now-active document so the user
        # never ends up looking at the wrong canvas region after a
        # cross-document switch (project load, Object Tree click on
        # a widget in another document, programmatic switch, …).
        self.focus_document(self.project.active_document_id)

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
        Must use ``canvas_scale`` (zoom × DPI) so the hit-test matches
        the DPI-scaled rect Renderer.redraw draws — otherwise drags
        that end inside the visible rect but outside logical pixel
        ``800`` get flagged as off-doc and snap back.
        """
        zoom = self.zoom.canvas_scale
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
            # Hidden widgets shouldn't act as drop targets — a hidden
            # frame is logically "not there" on the canvas, so cursor
            # tests + drag-into-frame should fall through to whatever
            # is underneath. Subtree skipped too: descendants of a
            # hidden frame would render hidden anyway.
            if not getattr(node, "visible", True):
                return
            descriptor = get_descriptor(node.widget_type)
            if descriptor is None:
                return
            if getattr(descriptor, "is_container", False):
                entry = self.widget_views.get(node.id)
                if entry is not None:
                    widget, _ = entry
                    # Composite containers (CTkScrollableFrame) expose
                    # an outer anchor widget with the correct fixed
                    # dimensions; the inner `widget` collapses to 0x0
                    # when empty and would fail the bbox size guard.
                    hit_widget = self._anchor_views.get(node.id, widget)
                    bbox = self._widget_canvas_bbox(hit_widget)
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

    def _reapply_fonts_to_all_widgets(self) -> None:
        """Walk every live CTk widget view and re-run the descriptor's
        property transform so the cascade-resolved font_family lands
        on each one. Triggered from ``font_defaults_changed`` —
        per-widget overrides aren't touched (the descriptor's own
        properties.get(\"font_family\") wins inside
        ``resolve_effective_family``), only the inherit-from-default
        cases pick up the new project / type default.
        """
        from app.widgets.registry import get_descriptor
        for widget_id, (widget, window_id) in list(
            self.widget_views.items(),
        ):
            node = self.project.get_widget(widget_id)
            if node is None:
                continue
            descriptor = get_descriptor(node.widget_type)
            if descriptor is None:
                continue
            self._apply_generic_configure(
                widget_id, "font_family",
                node.properties.get("font_family"),
                node, descriptor, widget, window_id,
            )

    def _update_widget_visibility_across_docs(self) -> None:
        if self.renderer is not None:
            self.renderer.update_visibility_across_docs()

    def _on_canvas_configure(self, event=None) -> None:
        if self.renderer is not None:
            self.renderer.on_canvas_configure(event)

    def _on_document_resized(self, *args) -> None:
        if self.renderer is not None:
            self.renderer.on_document_resized(*args)

    def focus_document(self, doc_id: str) -> None:
        """Scroll the canvas so ``doc_id``'s rectangle lands roughly
        centered in the visible viewport. Used after Add Dialog so the
        newly-placed doc doesn't stay hidden off the current scroll
        window — ``_add_document`` stacks new docs to the right of the
        existing last doc, which can easily be past the current
        viewport on zoomed-in or multi-dialog projects.
        """
        from app.ui.workspace.render import DOCUMENT_PADDING
        doc = self.project.get_document(doc_id)
        if doc is None:
            return
        self.update_idletasks()
        zoom = self.zoom.canvas_scale
        pad = DOCUMENT_PADDING
        doc_cx = pad + int((doc.canvas_x + doc.width / 2) * zoom)
        doc_cy = pad + int((doc.canvas_y + doc.height / 2) * zoom)
        try:
            scroll_l, scroll_t, scroll_r, scroll_b = (
                int(float(v)) for v in self.canvas.cget("scrollregion").split()
            )
        except (ValueError, tk.TclError):
            return
        view_w = self.canvas.winfo_width() or 800
        view_h = self.canvas.winfo_height() or 600
        scroll_w = max(1, scroll_r - scroll_l)
        scroll_h = max(1, scroll_b - scroll_t)
        frac_x = max(0.0, min(1.0, (doc_cx - view_w / 2) / scroll_w))
        frac_y = max(0.0, min(1.0, (doc_cy - view_h / 2) / scroll_h))
        try:
            self.canvas.xview_moveto(frac_x)
            self.canvas.yview_moveto(frac_y)
        except tk.TclError:
            pass

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
        the window item (physical pixel coords → ``canvas_scale``);
        nested uses `place_configure` (CTk-scaled → ``zoom.value``).
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
        try:
            if window_id is not None:
                # Canvas items live in physical pixels; match the
                # initial placement in ``_place_top_level`` so a
                # post-creation property change doesn't shrink the
                # outer frame back to ``lw * zoom.value`` while
                # CTk's own scaled widget still wants ``lw * DPI``.
                cw = max(1, int(lw * self.zoom.canvas_scale))
                ch = max(1, int(lh * self.zoom.canvas_scale))
                self.canvas.itemconfigure(window_id, width=cw, height=ch)
            elif anchor.winfo_manager() == "place":
                zw = max(1, int(lw * self.zoom.value))
                zh = max(1, int(lh * self.zoom.value))
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

    # Property-change dispatch: prop_name → handler. Groups capture
    # structural kinships (container vs child layout, coords vs
    # arbitrary configure) so ``_on_property_changed`` reads as a flat
    # router instead of the 140-line if/elif tower it used to be.
    _CONTAINER_LAYOUT_PROPS = frozenset({
        "layout_type", "layout_spacing", "grid_rows", "grid_cols",
    })
    _CHILD_LAYOUT_PROPS = frozenset({
        "grid_sticky", "grid_row", "grid_column", "stretch",
    })

    def _on_property_changed(
        self, widget_id: str, prop_name: str, value,
    ) -> None:
        from app.core.project import WINDOW_ID
        if widget_id == WINDOW_ID:
            self._handle_window_property(prop_name)
            return
        if prop_name in self._CONTAINER_LAYOUT_PROPS:
            self._handle_container_layout_prop(widget_id, prop_name)
            return
        if prop_name in self._CHILD_LAYOUT_PROPS:
            self._handle_child_layout_prop(widget_id)
            return
        if widget_id not in self.widget_views:
            return
        widget, window_id = self.widget_views[widget_id]
        node = self.project.get_widget(widget_id)
        if prop_name in ("x", "y") and node is not None:
            self._handle_coord_prop(widget_id, widget, window_id, node)
            return
        descriptor = get_descriptor(node.widget_type) if node else None
        if self._handle_var_binding_change(
            widget_id, prop_name, value, node, descriptor,
        ):
            return
        if self._handle_recreate_prop(
            widget_id, prop_name, node, descriptor,
        ):
            return
        self._apply_derived_props(widget_id, prop_name, node, descriptor)
        self._apply_generic_configure(
            widget_id, prop_name, value, node, descriptor,
            widget, window_id,
        )
        # v1.10.2 flex-shrink: width/height edits propagate to the
        # vbox/hbox rebalance loop in two directions.
        # 1. Edit on a child whose parent uses pack layout → re-budget
        #    siblings (a fixed sibling growing eats budget away from
        #    the grow ones).
        # 2. Edit on a container that *itself* uses pack layout →
        #    re-budget its children (the container's main axis
        #    changed, so each grow child's slot follows).
        if prop_name in ("width", "height") and node is not None:
            self._maybe_rebalance_after_size_edit(node)

    def _maybe_rebalance_after_size_edit(self, node) -> None:
        """Trigger ``rebalance_pack_siblings`` when a width/height
        edit lands on (a) a child of a vbox/hbox parent or (b) a
        vbox/hbox container itself. Either way the budget shifts and
        grow siblings need fresh slot math.
        """
        parent_node = getattr(node, "parent", None)
        if parent_node is not None:
            parent_layout = normalise_layout_type(
                parent_node.properties.get("layout_type", "place"),
            )
            if parent_layout in ("vbox", "hbox"):
                self.layout_overlay.rebalance_pack_siblings(
                    parent_node, parent_layout,
                )
        own_layout = normalise_layout_type(
            node.properties.get("layout_type", "place"),
        )
        if own_layout in ("vbox", "hbox") and node.children:
            self.layout_overlay.rebalance_pack_siblings(node, own_layout)

    def _handle_window_property(self, prop_name: str) -> None:
        """Window (virtual) node props don't touch a real CTk widget —
        the canvas rectangle + chrome + grid visualise the form. Most
        keys trigger a redraw; ``accent_color`` only touches chrome.
        """
        if prop_name in (
            "fg_color", "grid_style", "grid_color", "grid_spacing",
            "layout_type",
        ):
            self._redraw_document()
        elif prop_name == "accent_color":
            self._draw_window_chrome()

    def _handle_container_layout_prop(
        self, widget_id: str, prop_name: str = "",
    ) -> None:
        """Container-level layout mutation (manager swap, spacing,
        grid dims) — re-pack / re-place every child, redraw overlays.
        Grid-type containers additionally get a stacked-children
        sweep so a ``place → grid`` swap distributes the existing
        kids across free cells instead of stacking them all at (0, 0).
        A ``layout_type`` swap also re-applies fill defaults to
        fill-friendly children so Grid → vbox / hbox picks up
        ``stretch="grow"`` (and vice versa for grid) without a per-
        child manual tweak.
        """
        node = self.project.get_widget(widget_id)
        if node is not None and prop_name == "layout_type":
            self.lifecycle.apply_fill_defaults_to_children(node)
        if node is not None and normalise_layout_type(
            node.properties.get("layout_type", "place"),
        ) == "grid":
            self._redistribute_stacked_grid_children(node)
        self.layout_overlay.rearrange_container_children(widget_id)
        self._redraw_document()
        if self.project.selected_id is not None:
            self._schedule_selection_redraw()

    def _redistribute_stacked_grid_children(self, container_node) -> None:
        """Detect grid children sharing a cell and relocate the
        extras to free cells (growing the grid if needed). Triggered
        from ``_handle_container_layout_prop`` so layout-type swaps
        (place → grid, vbox → grid, etc.) stop leaving N children
        stacked at the default (0, 0). Idempotent — when no stacks
        exist this is a single dict-scan no-op, so re-entering the
        grid layout type on an already-distributed container costs
        nothing.
        """
        children = list(container_node.children)
        if len(children) < 2:
            return
        # Group children by their (row, col). A cell with 2+ kids is
        # stacked and triggers redistribution.
        cells: dict[tuple[int, int], list] = {}
        for child in children:
            try:
                r = int(child.properties.get("grid_row", 0) or 0)
                c = int(child.properties.get("grid_column", 0) or 0)
            except (TypeError, ValueError):
                r, c = 0, 0
            cells.setdefault((r, c), []).append(child)
        stacked = {cell: kids for cell, kids in cells.items() if len(kids) > 1}
        if not stacked:
            return
        # Keep the first child in each stacked cell, relocate the
        # rest. Deterministic order for reproducibility.
        for cell in sorted(stacked.keys()):
            for child_to_move in stacked[cell][1:]:
                new_r, new_c, dim_updates = resolve_grid_drop_cell(
                    container_node.children,
                    container_node.properties,
                    exclude_node=child_to_move,
                )
                if dim_updates:
                    for key, val in dim_updates.items():
                        self.project.update_property(
                            container_node.id, key, val,
                        )
                self.project.update_property(
                    child_to_move.id, "grid_row", new_r,
                )
                self.project.update_property(
                    child_to_move.id, "grid_column", new_c,
                )

    def _handle_child_layout_prop(self, widget_id: str) -> None:
        """Per-child layout tweak — re-apply the child's geometry
        manager in place. ``grid_*`` moves within the parent grid;
        ``stretch`` just swaps pack fill / expand kwargs.
        """
        self._reapply_child_manager(widget_id)
        if widget_id == self.project.selected_id:
            self._schedule_selection_redraw()

    def _handle_coord_prop(
        self, widget_id: str, widget, window_id, node,
    ) -> None:
        """x / y live update — drag motion, scrub, undo / redo all
        hit this path. Canvas items use ``canvas.coords``; placed
        widgets (non-canvas-hosted) use ``place_configure``.
        """
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
                # ``.place`` (not ``.place_configure``) routes through
                # CTk's DPI-scaling wrapper — see drag.py for the full
                # rationale. Using ``place_configure`` here would jump
                # the widget back to raw tk pixels after a drag.
                widget.place(
                    x=int(x * self.zoom.value),
                    y=int(y * self.zoom.value),
                )
        except Exception:
            log_error("workspace._on_property_changed x/y coords")
        if widget_id == self.project.selected_id:
            self._schedule_selection_redraw()

    # ------------------------------------------------------------------
    # Phase 1 binding — recreate widgets when a property toggles in / out
    # of bound state so Tkinter's ``textvariable`` / ``variable`` wiring
    # is rebuilt cleanly.
    # ------------------------------------------------------------------
    def _seed_binding_cache_on_add(self, node) -> None:
        from app.core.variables import parse_var_token
        bound: dict[str, str] = {}
        for k, v in node.properties.items():
            var_id = parse_var_token(v)
            if var_id is not None:
                bound[k] = var_id
        if bound:
            self._bound_props_cache[node.id] = bound
        else:
            self._bound_props_cache.pop(node.id, None)

    def _drop_binding_cache_on_remove(
        self, widget_id: str, parent_id: str | None = None,
    ) -> None:
        # ``widget_removed`` publishes ``(widget_id, parent_id)`` — the
        # earlier signature only accepted one positional and raised
        # TypeError, which propagated up and killed callers iterating
        # over multiple removals (e.g. the dialog-close ✕ would only
        # remove the first child widget per click).
        _ = parent_id
        self._bound_props_cache.pop(widget_id, None)

    def _on_variable_type_changed(self, var_id: str, _new_type) -> None:
        """The Project drops the cached ``tk.Variable`` when a type
        changes (so a fresh instance with the new type is built on
        next ``get_tk_var``). Every widget bound to that variable
        therefore holds a stale reference and needs a full recreate
        so the descriptor's ``init_kwargs`` plumbing rewires the new
        ``tk.Variable``.
        """
        affected_ids = [
            wid for wid, props in self._bound_props_cache.items()
            if var_id in props.values()
        ]
        for wid in affected_ids:
            node = self.project.get_widget(wid)
            descriptor = get_descriptor(node.widget_type) if node else None
            if node is None or descriptor is None:
                continue

            def _remove_subtree(n) -> None:
                for c in list(n.children):
                    _remove_subtree(c)
                self.lifecycle.on_widget_removed(n.id)
            _remove_subtree(node)
            self.lifecycle.create_widget_subtree(node)
            if wid == self.project.selected_id:
                self._schedule_selection_redraw()

    def _handle_var_binding_change(
        self, widget_id: str, prop_name: str, value,
        node, descriptor,
    ) -> bool:
        """Detect transitions in bound state for a property. Triggers
        a recreate when the property toggles literal ↔ bound, OR when
        it stays bound but switches to a different variable. Returns
        True when a recreate ran — caller skips the rest of the
        property-change pipeline.
        """
        from app.core.variables import parse_var_token
        if descriptor is None or node is None:
            return False
        bound_dict = self._bound_props_cache.setdefault(widget_id, {})
        new_var_id = parse_var_token(value)
        old_var_id = bound_dict.get(prop_name)
        if new_var_id == old_var_id:
            return False
        if new_var_id is None:
            bound_dict.pop(prop_name, None)
        else:
            bound_dict[prop_name] = new_var_id
        entry = self.widget_views.get(widget_id)
        if entry is not None:
            widget_obj, _ = entry
            try:
                descriptor.before_recreate(node, widget_obj, prop_name)
            except Exception:
                log_error(f"{node.widget_type}.before_recreate")

        def _remove_subtree(n) -> None:
            for c in list(n.children):
                _remove_subtree(c)
            self.lifecycle.on_widget_removed(n.id)
        _remove_subtree(node)
        self.lifecycle.create_widget_subtree(node)
        if widget_id == self.project.selected_id:
            self._schedule_selection_redraw()
        return True

    def _handle_recreate_prop(
        self, widget_id: str, prop_name: str, node, descriptor,
    ) -> bool:
        """Init-only kwargs (e.g. ``CTkProgressBar.orientation``)
        can't be reconfigured live — destroy and rebuild the subtree.
        Returns True when the prop was a recreate trigger and the
        rebuild was done, so the caller can short-circuit.
        """
        recreate = (
            getattr(descriptor, "recreate_triggers", None)
            if descriptor else None
        )
        if not recreate or prop_name not in recreate:
            return False
        updates = descriptor.on_prop_recreate(prop_name, node.properties)
        for k, v in updates.items():
            if node.properties.get(k) != v:
                self.project.update_property(widget_id, k, v)
        entry = self.widget_views.get(widget_id)
        if entry is not None:
            widget_obj, _ = entry
            try:
                descriptor.before_recreate(node, widget_obj, prop_name)
            except Exception:
                log_error(f"{node.widget_type}.before_recreate")

        def _remove_subtree(n) -> None:
            for c in list(n.children):
                _remove_subtree(c)
            self.lifecycle.on_widget_removed(n.id)
        _remove_subtree(node)
        self.lifecycle.create_widget_subtree(node)
        if widget_id == self.project.selected_id:
            self._schedule_selection_redraw()
        return True

    def _apply_derived_props(
        self, widget_id: str, prop_name: str, node, descriptor,
    ) -> None:
        """Descriptors can declare ``derived_triggers`` — props whose
        change should fan out into computed sibling props via
        ``compute_derived`` (e.g. Image width → height when
        ``preserve_aspect`` is on). Runs BEFORE the generic configure
        path so the derived updates land in the same widget pass.
        """
        if descriptor is None:
            return
        triggers = getattr(descriptor, "derived_triggers", None)
        if not (triggers and prop_name in triggers
                and hasattr(descriptor, "compute_derived")):
            return
        try:
            derived = descriptor.compute_derived(node.properties)
        except Exception:
            log_error(f"{node.widget_type}.compute_derived")
            derived = {}
        for k, v in derived.items():
            if node.properties.get(k) != v:
                self.project.update_property(widget_id, k, v)

    def _apply_generic_configure(
        self, widget_id: str, prop_name: str, value,
        node, descriptor, widget, window_id,
    ) -> None:
        """Fallback path for every prop that isn't special-cased above:
        run the descriptor's ``transform_properties`` + ``apply_state``,
        refresh zoom placement, resize composite wrappers, and re-lift
        CTkButton's text label (which can slip behind its background
        when corner_radius approaches half the widget height).
        """
        try:
            if descriptor is not None:
                transformed = descriptor.transform_properties(
                    _strip_layout_keys(node.properties),
                )
                if transformed:
                    widget.configure(**transformed)
                descriptor.apply_state(widget, node.properties)
                self._sync_radio_initial(widget, node)
                owning_doc = self.project.find_document_for_widget(
                    widget_id,
                )
                self.zoom.apply_to_widget(
                    widget, window_id, node.properties,
                    document=owning_doc,
                )
                if widget_id in self._anchor_views:
                    self._sync_composite_size(widget_id, node)
            else:
                widget.configure(**{prop_name: value})
        except Exception:
            log_error(
                f"workspace._on_property_changed widget.configure {prop_name}",
            )
        # Re-walk bindings — composites like CTkSegmentedButton tear
        # down inner children inside ``configure(values=…)`` (and
        # transform_properties always passes the full kwarg set, so
        # this fires on every property edit, not just values). The
        # idempotent ``_bind_widget_events`` skips already-bound
        # widgets and only attaches handlers to brand-new children.
        self._bind_widget_events(widget, widget_id)
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
        # Managed-layout children (vbox / hbox / grid) are place-managed
        # via the grid-as-place hack, but their x/y properties are 0 —
        # zoom.apply_to_widget's place_configure(x=0,y=0) just pulled
        # them to the container's top-left corner. Put them back by
        # re-running the parent's child-manager, which recomputes the
        # correct cell / pack coordinates.
        if node is not None and node.parent is not None:
            parent_lt = normalise_layout_type(
                node.parent.properties.get("layout_type", "place"),
            )
            if parent_lt != "place":
                self._reapply_child_manager(widget_id)
        if widget_id == self.project.selected_id:
            self._schedule_selection_redraw()

    def _on_component_drop(
        self, component_path, x_root: int, y_root: int,
    ) -> None:
        """Drop a component onto the canvas. Loads the ``.ctkcomp``
        payload, reconciles bundled variables against the target
        Window (auto-create / reuse / Rename / Skip via dialog),
        instantiates fresh ``WidgetNode`` trees with new UUIDs,
        offsets root coords so the component's bounding-box top-left
        lands at the drop point, and inserts under the container at
        the cursor (or top-level if outside any container).
        """
        from app.core.commands import _add_subtree_recursive
        from app.io.component_io import (
            analyze_var_conflicts, apply_var_resolutions,
            extract_component_assets, instantiate_fragment, load_payload,
        )
        from app.ui.component_var_conflict_dialog import (
            ComponentVarConflictDialog,
        )

        canvas_rx = self.canvas.winfo_rootx()
        canvas_ry = self.canvas.winfo_rooty()
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        local_x = x_root - canvas_rx
        local_y = y_root - canvas_ry
        if not (0 <= local_x < canvas_w and 0 <= local_y < canvas_h):
            return
        payload = load_payload(component_path)
        if payload is None or not payload.get("nodes"):
            return
        # Window-type components don't slot into the current canvas
        # the way fragments do — they create a new Toplevel document
        # in the project. Confirmation modal makes the side-effect
        # explicit since drag/double-click look identical to fragments.
        if payload.get("type") == "window":
            self._insert_window_component(component_path, payload)
            return

        cx, cy = self._screen_to_canvas(x_root, y_root)
        container_node = self._find_container_at(cx, cy)

        if container_node is None:
            target_doc = self._find_document_at_canvas(cx, cy)
            if target_doc is None:
                return
            self.project.set_active_document(target_doc.id)
            lx, ly = self.zoom.canvas_to_logical(
                cx, cy, document=target_doc,
            )
            target_x, target_y = max(0, lx), max(0, ly)
            parent_id = None
            document_id = target_doc.id
        else:
            container_widget, _ = self.widget_views[container_node.id]
            zoom = self.zoom.value or 1.0
            coord_ref = container_widget
            if container_node.widget_type == "CTkTabview":
                try:
                    active_tab_slot = container_widget.get() or None
                except Exception:
                    active_tab_slot = None
                if active_tab_slot:
                    try:
                        coord_ref = container_widget.tab(active_tab_slot)
                    except Exception:
                        coord_ref = container_widget
            target_x = max(0, int((x_root - coord_ref.winfo_rootx()) / zoom))
            target_y = max(0, int((y_root - coord_ref.winfo_rooty()) / zoom))
            parent_id = container_node.id
            owning_doc = self.project.find_document_for_widget(parent_id)
            document_id = owning_doc.id if owning_doc is not None else None

        target_window = (
            self.project.get_document(document_id) if document_id else None
        )
        # Variable bundle reconciliation. The target Window owns the
        # local namespace the bundled vars will land in; any conflict
        # gates the entire insert (Cancel = abort, no widgets / vars
        # touched). Auto bundles + resolved conflicts then materialise
        # via apply_var_resolutions, returning a uuid map that
        # instantiate_fragment uses to rewrite ``var:<uuid>`` tokens.
        uuid_map: dict | None = None
        if target_window is not None and payload.get("variables"):
            plan = analyze_var_conflicts(payload, target_window)
            if plan.conflicts:
                dialog = ComponentVarConflictDialog(
                    self.winfo_toplevel(), plan.conflicts,
                )
                self.wait_window(dialog)
                if not dialog.result:
                    return
            uuid_map = apply_var_resolutions(
                self.project, target_window, plan,
            )

        # Bounding-box top-left → drop point. Root nodes get offset;
        # children's coords stay relative to their parent so the
        # internal layout survives the move.
        roots = payload["nodes"]
        bbox_x = min(int(n.get("properties", {}).get("x", 0) or 0) for n in roots)
        bbox_y = min(int(n.get("properties", {}).get("y", 0) or 0) for n in roots)
        # Asset extraction: bundle tokens get rewritten to absolute
        # paths inside ``<project>/assets/components/<slug>/``. Empty
        # bundles return an empty map; rewrite_bundle_tokens then
        # leaves the property as an empty string for the descriptor
        # to handle.
        from app.core.component_paths import component_display_stem
        extracted_assets, _component_folder = extract_component_assets(
            component_path,
            getattr(self.project, "path", None),
            payload.get("name") or component_display_stem(component_path),
        )
        nodes = instantiate_fragment(
            payload,
            drop_offset=(target_x - bbox_x, target_y - bbox_y),
            var_uuid_map=uuid_map,
            asset_extracted_map=extracted_assets,
        )
        new_ids: list[str] = []
        for root in nodes:
            _add_subtree_recursive(
                self.project, root, parent_id, document_id,
            )
            new_ids.append(root.id)
        if not new_ids:
            return
        if len(new_ids) == 1:
            self.project.select_widget(new_ids[0])
        else:
            self.project.set_multi_selection(
                set(new_ids), primary=new_ids[0],
            )
        from app.core.commands import build_bulk_add_entries
        entries = build_bulk_add_entries(self.project, new_ids)
        if entries:
            label = payload.get("name") or "component"
            # NOTE: undo of this command removes the widgets but leaves
            # auto-created local variables behind. Rare edge; user can
            # delete them via the Variables window. Phase D will swap
            # in a proper composite InsertComponentCommand.
            self.project.history.push(
                BulkAddCommand(entries, label=f"Insert {label}"),
            )

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
        self._create_node_from_entry(
            entry, descriptor, container_node, cx, cy, x_root, y_root,
        )

    def _create_node_from_entry(
        self, entry, descriptor, container_node,
        cx: float, cy: float, x_root: int, y_root: int,
    ) -> None:
        """Materialise a palette entry as a new widget node. Shared
        by drag-drop and the canvas/widget right-click "Add Widget"
        menus so every entry path uses identical layout-nesting,
        Tabview routing, grid-cell snapping, and history rules.
        """
        properties = dict(descriptor.default_properties)
        for key, value in getattr(entry, "preset_overrides", ()) or ():
            properties[key] = value
        # Block layout-in-layout nesting — if the palette item is a
        # managed-layout preset (Vertical / Horizontal / Grid) and the
        # drop target is already a layout container, fall through to
        # a top-level drop instead.
        if (
            container_node is not None
            and is_layout_container(properties)
            and is_layout_container(container_node.properties)
        ):
            container_node = None
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
            # Tabview drops land inside the currently-active tab's
            # inner frame; rel_x/rel_y are computed against that frame
            # so the place() coords match what the user sees on canvas.
            coord_ref = container_widget
            active_tab_slot: str | None = None
            if container_node.widget_type == "CTkTabview":
                try:
                    active_tab_slot = container_widget.get() or None
                except Exception:
                    active_tab_slot = None
                if active_tab_slot:
                    try:
                        coord_ref = container_widget.tab(active_tab_slot)
                    except Exception:
                        coord_ref = container_widget
            rel_x = (x_root - coord_ref.winfo_rootx()) / zoom
            rel_y = (y_root - coord_ref.winfo_rooty()) / zoom
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
                row, col = self.drag_controller._grid_indicator.cell_at(
                    container_node, cx, cy,
                )
                properties["grid_row"] = row
                properties["grid_column"] = col
        node = WidgetNode(
            widget_type=descriptor.type_name,
            properties=properties,
        )
        if (
            container_node is not None
            and container_node.widget_type == "CTkTabview"
        ):
            node.parent_slot = active_tab_slot
        self.project.add_widget(
            node, parent_id=parent_id,
            name_base=getattr(entry, "default_name", None),
        )
        self.project.select_widget(node.id)
        owning_doc = self.project.find_document_for_widget(node.id)
        document_id = owning_doc.id if owning_doc is not None else None
        dim_changes = getattr(node, "_pending_parent_dim_changes", None)
        if hasattr(node, "_pending_parent_dim_changes"):
            try:
                delattr(node, "_pending_parent_dim_changes")
            except AttributeError:
                pass
        self.project.history.push(
            AddWidgetCommand(
                node.to_dict(), parent_id, document_id=document_id,
                parent_dim_changes=dim_changes,
            ),
        )

    def _build_add_widget_menu(
        self, parent_menu: tk.Menu, container_node,
        cx: float, cy: float, x_root: int, y_root: int,
    ) -> tk.Menu:
        """Build the "Add Widget" / "Add Widget as Child" cascade —
        same catalog structure as the menubar Widget menu. When
        ``container_node`` is itself a managed-layout container,
        Layouts entries that would nest layout-in-layout are disabled.
        """
        from app.ui.palette import CATALOG
        parent_is_layout = (
            container_node is not None
            and is_layout_container(container_node.properties)
        )
        submenu = tk.Menu(parent_menu, tearoff=0)
        for group in CATALOG:
            group_menu = tk.Menu(submenu, tearoff=0)
            for entry in group.items:
                descriptor = get_descriptor(entry.type_name)
                if descriptor is None:
                    continue
                entry_props = dict(descriptor.default_properties)
                for k, v in entry.preset_overrides:
                    entry_props[k] = v
                disabled = (
                    parent_is_layout and is_layout_container(entry_props)
                )
                group_menu.add_command(
                    label=entry.display_name,
                    command=(
                        lambda e=entry, d=descriptor:
                        self._create_node_from_entry(
                            e, d, container_node, cx, cy, x_root, y_root,
                        )
                    ),
                    state="disabled" if disabled else "normal",
                )
            submenu.add_cascade(label=group.title, menu=group_menu)
        return submenu

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
        #
        # Idempotent: tagged widgets are skipped on re-walk so callers
        # can safely re-invoke after a CTk configure that rebuilt
        # internal children (CTkSegmentedButton tears down its segment
        # buttons every time `values=` is reconfigured — and the
        # generic configure path passes `values` on every property
        # edit, so without this re-walk the new segments would have
        # no workspace bindings and the widget would look "dead" on
        # the canvas after any property change).
        already_bound = getattr(widget, "_ws_bound_nid", None) == nid
        if not already_bound:
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
            _safe_bind(
                "<ButtonRelease-2>", self.controls.on_middle_release,
            )
            # Ctrl+wheel forwards to ZoomController so zoom works even
            # when the pointer happens to hover a widget instead of
            # empty canvas area.
            _safe_bind(
                f"<{MOD_KEY}-MouseWheel>", self.zoom.handle_ctrl_wheel,
            )
            _safe_bind(
                "<Button-3>",
                lambda e, n=nid: self._on_widget_right_click(e, n),
            )
            try:
                widget.configure(cursor="fleur")
            except (tk.TclError, NotImplementedError, ValueError):
                pass
            widget._ws_bound_nid = nid
        # CTkOptionMenu opens its dropdown on every Button-1, which
        # makes selecting it without firing the menu impossible. Gate
        # _open_dropdown_menu so the first click only selects, then
        # arm a short window in which a follow-up click opens the
        # menu. After the window expires, plain clicks just keep the
        # selection without surprising the user with a popup.
        if (
            isinstance(widget, ctk.CTkOptionMenu)
            and not getattr(widget, "_builder_two_click_wrapped", False)
        ):
            _orig_open = widget._open_dropdown_menu

            def _gated_open(_o=_orig_open, _n=nid, _ws=self, _w=widget):
                is_selected = _n in _ws.project.selected_ids
                armed = getattr(_w, "_builder_open_armed", False)
                if is_selected and armed:
                    _w._builder_open_armed = False
                    _o()
                    return
                # Arm only if this click is the one that actually
                # selects the widget (drag_press runs after _clicked
                # so we schedule the check to after_idle).
                def _maybe_arm(w=_w, n=_n, ws=_ws):
                    try:
                        if (
                            n in ws.project.selected_ids
                            and not getattr(w, "_builder_open_armed", False)
                        ):
                            w._builder_open_armed = True
                            w.after(
                                500,
                                lambda ww=w: setattr(
                                    ww, "_builder_open_armed", False,
                                ) if ww.winfo_exists() else None,
                            )
                    except tk.TclError:
                        pass

                try:
                    _w.after_idle(_maybe_arm)
                except tk.TclError:
                    pass

            widget._open_dropdown_menu = _gated_open
            widget._builder_two_click_wrapped = True
        # Always recurse — even if THIS widget is already bound, a
        # composite CTk widget may have spawned brand-new children
        # since the last walk that still need their handlers.
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
        add_submenu = self._build_add_widget_menu(
            menu, None, cx, cy, event.x_root, event.y_root,
        )
        menu.add_cascade(label="Add Widget", menu=add_submenu)
        menu.add_separator()
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
        menu.add_separator()
        save_label = (
            "Save Dialog as Component"
            if doc.is_toplevel else "Save Window as Component"
        )
        save_state = "normal" if doc.root_widgets else "disabled"
        menu.add_command(
            label=save_label,
            command=lambda d=doc: self._save_window_as_component(d),
            state=save_state,
        )
        menu.add_separator()
        from app.core.project import WINDOW_ID
        props_label = (
            "Dialog Properties" if doc.is_toplevel else "Window Properties"
        )
        menu.add_command(
            label=props_label,
            command=lambda: self.project.select_widget(WINDOW_ID),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _paste_at_canvas(self, doc, logical_x: int, logical_y: int) -> None:
        if not self.project.clipboard:
            return
        from app.ui.variables_window import confirm_clipboard_paste_policy
        proceed, policy = confirm_clipboard_paste_policy(
            self.winfo_toplevel(), self.project, doc,
        )
        if not proceed:
            return
        new_ids = self.project.paste_from_clipboard(
            parent_id=None,
            base_position=(logical_x, logical_y),
            var_policy=policy,
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
        # Route through the same drill-down resolver as left-click so
        # right-click on a container's child first targets the parent
        # (then the child, etc., as the user repeats clicks). Without
        # this, right-click jumped straight to the deepest widget and
        # the context menu acted on a different layer than the user's
        # current selection scope.
        resolved = self.drag_controller._resolve_click_target(nid)
        if resolved is not None:
            nid = resolved
        # Preserve multi-selection when right-clicking one of its members
        # — calling select_widget here would collapse the set to a single
        # primary and make group Delete impossible from the context menu.
        multi_active = (
            len(self.project.selected_ids) > 1
            and nid in self.project.selected_ids
        )
        menu = tk.Menu(self.winfo_toplevel(), tearoff=0)
        toplevel = self.winfo_toplevel()
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
            menu.add_separator()
            menu.add_command(
                label=f"Save {count} widgets as component…",
                command=self._save_selection_as_component,
            )
            self._add_group_entries_to_menu(menu, toplevel)
        else:
            self.project.select_widget(nid)
            target_node = self.project.get_widget(nid)
            target_descriptor = (
                get_descriptor(target_node.widget_type)
                if target_node is not None else None
            )
            target_is_container = (
                target_descriptor is not None
                and getattr(target_descriptor, "is_container", False)
            )
            cx_w, cy_w = self._screen_to_canvas(event.x_root, event.y_root)
            add_submenu = self._build_add_widget_menu(
                menu,
                target_node if target_is_container else None,
                cx_w, cy_w, event.x_root, event.y_root,
            )
            menu.add_cascade(
                label="Add Widget as Child",
                menu=add_submenu,
                state="normal" if target_is_container else "disabled",
            )
            menu.add_separator()
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
            from app.ui.workspace.controls import TOOL_EDIT
            edit_state = (
                "disabled" if self.controls.tool == TOOL_EDIT
                else "normal"
            )
            menu.add_command(
                label="Edit mode",
                command=lambda: self._enter_edit_mode(nid),
                state=edit_state,
            )
            menu.add_command(
                label="Description…",
                command=lambda: self._open_widget_description(nid),
            )
            menu.add_separator()
            handler_submenu = self._build_handler_menu(target_node)
            menu.add_cascade(
                label="Add handler",
                menu=handler_submenu,
                state=("normal" if handler_submenu is not None else "disabled"),
            )
            menu.add_separator()
            menu.add_command(
                label="Save as component…",
                command=self._save_selection_as_component,
            )
            menu.add_separator()
            menu.add_command(
                label="Rename",
                command=lambda: self._prompt_rename_widget(nid),
            )
            menu.add_command(label="Delete", command=self._on_delete)
            self._add_group_entries_to_menu(menu, toplevel)
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

    def _add_group_entries_to_menu(self, menu, toplevel) -> None:
        """Append the Group / Ungroup / Select Group entries to a
        context menu — each only added when currently runnable.
        Routes to the same MainWindow handlers used by the Edit menu
        and Ctrl+G / Ctrl+Shift+G so every entry point produces the
        same history record.
        """
        sel_ids = set(self.project.selected_ids or set())
        can_group = self.project.can_group_selection(sel_ids)
        # "Select Group" only makes sense when the current selection
        # is a partial group (1 member of a 2+ member group). Whole
        # group already selected → entry would be a no-op.
        select_group_id: str | None = None
        for wid in sel_ids:
            node = self.project.get_widget(wid)
            gid = getattr(node, "group_id", None) if node else None
            if not gid:
                continue
            members = self.project.iter_group_members(gid)
            if len(members) > 1 and sel_ids != {m.id for m in members}:
                select_group_id = gid
                break
        can_ungroup = any(
            getattr(self.project.get_widget(wid), "group_id", None)
            for wid in sel_ids
        )
        if not (can_group or can_ungroup or select_group_id):
            return
        menu.add_separator()
        if can_group:
            menu.add_command(
                label="Group",
                accelerator=f"{MOD_LABEL_PLUS}G",
                command=toplevel._on_group_shortcut,
            )
        if select_group_id:
            menu.add_command(
                label="Select Group",
                command=lambda gid=select_group_id: toplevel._on_select_group(gid),
            )
        if can_ungroup:
            menu.add_command(
                label="Ungroup",
                accelerator=f"{MOD_LABEL_PLUS}Shift+G",
                command=toplevel._on_ungroup_shortcut,
            )

    def _copy_selection(self) -> None:
        ids = self.project.selected_ids
        if not ids:
            return
        self.project.copy_to_clipboard(ids)

    def _copy_single(self, nid: str) -> None:
        self.project.copy_to_clipboard({nid})

    def _enter_edit_mode(self, nid: str) -> None:
        """Right-click → Edit mode entry. Caller already selected
        ``nid``; flip the workspace tool so handles + property panel
        switch to the per-widget edit experience."""
        from app.ui.workspace.controls import TOOL_EDIT
        self.controls.set_tool(TOOL_EDIT)

    def _open_widget_description(self, nid: str) -> None:
        """Right-click → Description… entry. The widget is already
        selected, so a single event-bus publish is enough — the
        properties panel subscribes and opens the same multiline
        editor it uses for its own square-pen button."""
        self.project.event_bus.publish("request_edit_description")

    def _build_handler_menu(self, node) -> "tk.Menu | None":
        """Cascade for the right-click "Add handler" entry. Returns
        ``None`` when the widget type has no registered events.

        Each event surfaces as one row + an optional list of
        bound-method rows underneath:
        - **unbound** → ``+ <event label>`` — click stubs a fresh
          method and opens the editor.
        - **bound (≥1 method)** → one ``▶ <event label> — <method>``
          row per bound method (click → jump to editor) followed by
          a ``+ Add another <event label> action`` row that appends
          a new method (Decision #10 multi-method).
        """
        from app.widgets.event_registry import events_for
        if node is None:
            return None
        events = events_for(node.widget_type)
        if not events:
            return None
        sub = tk.Menu(self.winfo_toplevel(), tearoff=0)
        first_event = True
        for entry in events:
            methods = list(node.handlers.get(entry.key, []) or [])
            if not first_event:
                sub.add_separator()
            first_event = False
            if methods:
                for idx, method in enumerate(methods):
                    sub.add_command(
                        label=f"{entry.label}  —  {method}",
                        command=lambda nid=node.id, m=method:
                            self._jump_to_handler_method(nid, m),
                    )
                sub.add_command(
                    label=f"+  Add another {entry.label.lower()} action",
                    command=lambda nid=node.id, key=entry.key:
                        self._attach_event_handler(nid, key),
                )
            else:
                sub.add_command(
                    label=f"+  {entry.label}",
                    command=lambda nid=node.id, key=entry.key:
                        self._attach_event_handler(nid, key),
                )
        return sub

    def _attach_event_handler(self, widget_id: str, event_key: str) -> None:
        """Right-click → "+ <event>" / "+ Add another …" flow:
        1. Validate the project's saved (we need
           ``<project>/assets/scripts/``).
        2. Resolve a method name (per-window collision check —
           Decision #15 — auto-suffix ``_2`` / ``_3``).
        3. Materialise the per-window behavior file + append a stub
           to the window's class.
        4. Push a ``BindHandlerCommand`` (multi-method append) so
           undo pops the row that was just added.
        5. Open the editor at the new method.
        """
        from app.io.scripts import (
            add_handler_stub, behavior_class_name,
            load_or_create_behavior_file,
            suggest_method_name,
        )
        from app.widgets.event_registry import event_by_key

        node = self.project.get_widget(widget_id)
        if node is None:
            return
        entry = event_by_key(node.widget_type, event_key)
        if entry is None:
            return
        if not getattr(self.project, "path", None):
            messagebox.showinfo(
                "Save first",
                "Save the project before adding event handlers — the "
                "behavior file lives in assets/scripts/ in the project "
                "folder.",
                parent=self.winfo_toplevel(),
            )
            return
        document = self.project.find_document_for_widget(widget_id)
        if document is None:
            return
        method_name = suggest_method_name(node, entry, document)
        file_path = load_or_create_behavior_file(
            self.project.path, document,
        )
        if file_path is None:
            messagebox.showerror(
                "Couldn't write behavior file",
                "Failed to create assets/scripts/ folder. Check folder "
                "permissions on the project directory.",
                parent=self.winfo_toplevel(),
            )
            return
        class_name = behavior_class_name(document)
        add_handler_stub(
            file_path, class_name, method_name, entry.signature,
        )
        # Apply the binding before pushing the command so undo can
        # locate the appended row by index. ``BindHandlerCommand``
        # records the index it appended at; mirroring that here keeps
        # do/redo paths consistent.
        methods = node.handlers.setdefault(event_key, [])
        methods.append(method_name)
        appended_index = len(methods) - 1
        cmd = BindHandlerCommand(widget_id, event_key, method_name)
        cmd._appended_index = appended_index
        self.project.history.push(cmd)
        self.project.event_bus.publish(
            "widget_handler_changed", widget_id, event_key, method_name,
        )
        # Editor doesn't auto-open on action creation — the flash
        # of a VS Code window every right-click was disruptive.
        # Double-click the row, F7, or right-click → "Open in
        # editor" is the explicit jump path.

    def _jump_to_handler_method(
        self, widget_id: str, method_name: str,
    ) -> None:
        """Open the editor at the named method on the widget's
        per-window behavior class. Used by every bound-method row
        in the cascade.
        """
        from app.core.settings import load_settings
        from app.io.scripts import (
            behavior_class_name, behavior_file_path,
            find_handler_method, launch_editor,
            resolve_project_root_for_editor as _resolve_project_root,
        )

        if not method_name or not getattr(self.project, "path", None):
            return
        document = self.project.find_document_for_widget(widget_id)
        if document is None:
            return
        file_path = behavior_file_path(self.project.path, document)
        if file_path is None or not file_path.exists():
            return
        class_name = behavior_class_name(document)
        line = find_handler_method(file_path, class_name, method_name)
        editor_command = load_settings().get("editor_command")
        launch_editor(
            file_path, line=line, editor_command=editor_command,
            project_root=_resolve_project_root(self.project),
        )

    def _save_selection_as_component(self) -> None:
        """Bundle the current selection as a fragment component. Every
        resolvable variable binding (local OR global) travels with the
        component — globals get demoted to locals on insert into the
        target Window. Deleted-var tokens drop silently. Requires a
        saved project (components live next to ``assets/`` in the
        project folder); blocks with a hint otherwise.
        """
        from tkinter import messagebox
        from app.core.component_paths import ensure_components_root
        from app.io.component_io import (
            count_assets_to_bundle, count_bindings_to_bundle, save_fragment,
        )
        from app.ui.component_save_dialog import ComponentSaveDialog

        ids = list(self.project.selected_ids)
        if not ids:
            return
        nodes = [
            self.project.get_widget(nid) for nid in ids
        ]
        nodes = [n for n in nodes if n is not None]
        if not nodes:
            return
        toplevel = self.winfo_toplevel()
        current_path = getattr(toplevel, "_current_path", None)
        components_dir = ensure_components_root(current_path)
        if components_dir is None:
            messagebox.showinfo(
                "Save project first",
                "Components are stored next to assets in the project "
                "folder. Save the project before creating components.",
                parent=toplevel,
            )
            return
        owning_doc = self.project.find_document_for_widget(nodes[0].id)
        source_window_id = owning_doc.id if owning_doc is not None else None
        first = nodes[0]
        default_name = first.name or first.widget_type
        bundled_count = count_bindings_to_bundle(nodes, self.project)
        asset_count, asset_bytes = count_assets_to_bundle(
            nodes, self.project,
        )
        dialog = ComponentSaveDialog(
            toplevel,
            default_name=default_name,
            components_dir=components_dir,
            bundled_var_count=bundled_count,
            bundled_asset_count=asset_count,
            bundled_asset_bytes=asset_bytes,
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        name, target_path = dialog.result
        try:
            save_fragment(
                target_path, name, nodes, self.project,
                source_window_id=source_window_id,
            )
        except OSError as exc:
            messagebox.showerror(
                "Save component failed",
                f"Couldn't write component:\n{exc}",
                parent=toplevel,
            )
            return
        # Tell the components panel a new file appeared so its tree
        # repopulates without needing a tab switch.
        self.project.event_bus.publish("component_library_changed")

    def _insert_window_component(self, component_path, payload) -> None:
        """Insert a window-type component as a brand-new Toplevel
        document. Confirmation modal first; on accept, the new
        document gets the component's display name (auto-suffixed
        with ``_2``/``_3`` on collision), all bundled local
        variables, the saved window properties, and the widget tree
        with bundle-token assets extracted into the project.
        """
        from app.core.commands import (
            AddDocumentCommand, _add_subtree_recursive,
        )
        from app.core.component_paths import component_display_stem
        from app.io.component_io import (
            extract_component_assets, instantiate_window_document,
        )
        from app.ui.component_window_insert_dialog import (
            ComponentWindowInsertDialog,
        )

        component_name = (
            payload.get("name") or component_display_stem(component_path)
        )
        target_name = self._pick_unique_document_name(component_name)
        toplevel = self.winfo_toplevel()
        confirm = ComponentWindowInsertDialog(
            toplevel,
            component_name=component_name,
            target_doc_name=target_name,
        )
        toplevel.wait_window(confirm)
        if not confirm.result:
            return
        # Re-resolve the unique name in case the user managed to
        # add a document while the modal was open.
        target_name = self._pick_unique_document_name(component_name)
        extracted_assets, _component_folder = extract_component_assets(
            component_path,
            getattr(self.project, "path", None),
            component_name,
        )
        new_doc, root_nodes = instantiate_window_document(
            payload,
            project=self.project,
            target_name=target_name,
            asset_extracted_map=extracted_assets,
        )
        # Place the new doc to the right of the rightmost existing
        # one — same canvas-placement rule as the menubar Add Dialog.
        max_right = 0
        for doc in self.project.documents:
            right = doc.canvas_x + doc.width
            if right > max_right:
                max_right = right
        new_doc.canvas_x = max_right + 120
        new_doc.canvas_y = 0
        index = len(self.project.documents)
        self.project.documents.append(new_doc)
        self.project.set_active_document(new_doc.id)
        # Each root subtree gets registered through add_widget so the
        # workspace renderer fires widget_added per node and builds a
        # tk widget for it. Appending to doc.root_widgets directly
        # leaves the tree invisible (model present, never rendered) —
        # same trap delete-snapshot restore hits.
        for root in root_nodes:
            _add_subtree_recursive(
                self.project, root, parent_id=None, document_id=new_doc.id,
            )
        self.project.history.push(
            AddDocumentCommand(new_doc.to_dict(), index),
        )
        self.project.event_bus.publish(
            "project_renamed", self.project.name,
        )

    def _pick_unique_document_name(self, base: str) -> str:
        existing = {doc.name for doc in self.project.documents}
        if base not in existing:
            return base
        n = 2
        while True:
            candidate = f"{base}_{n}"
            if candidate not in existing:
                return candidate
            n += 1

    def _save_window_as_component(self, document) -> None:
        """Save the entire Window/Dialog as a window-type component.
        Every widget, the window_properties dict, and the document's
        full local-variable list travel with the bundle. Even a main
        window saves with ``is_toplevel=True`` in the payload — on
        insert the component always becomes a Toplevel, since a
        project only has one main window slot.
        """
        from tkinter import messagebox
        from app.core.component_paths import ensure_components_root
        from app.io.component_io import count_window_assets, save_window
        from app.ui.component_save_dialog import ComponentSaveDialog

        if not document.root_widgets:
            messagebox.showinfo(
                "Empty window",
                "This window has no widgets yet — add some before "
                "saving as a component.",
                parent=self.winfo_toplevel(),
            )
            return
        toplevel = self.winfo_toplevel()
        current_path = getattr(toplevel, "_current_path", None)
        components_dir = ensure_components_root(current_path)
        if components_dir is None:
            messagebox.showinfo(
                "Save project first",
                "Components are stored next to assets in the project "
                "folder. Save the project before creating components.",
                parent=toplevel,
            )
            return
        bundled_count = len(document.local_variables)
        asset_count, asset_bytes = count_window_assets(
            document, self.project,
        )
        dialog = ComponentSaveDialog(
            toplevel,
            default_name=document.name,
            components_dir=components_dir,
            bundled_var_count=bundled_count,
            bundled_asset_count=asset_count,
            bundled_asset_bytes=asset_bytes,
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        name, target_path = dialog.result
        try:
            save_window(
                target_path, name, document, self.project,
            )
        except OSError as exc:
            messagebox.showerror(
                "Save component failed",
                f"Couldn't write component:\n{exc}",
                parent=toplevel,
            )
            return
        self.project.event_bus.publish("component_library_changed")

    def _paste_at_widget(self, nid: str) -> None:
        if not self.project.clipboard:
            return
        parent_id = paste_target_parent_id(self.project, nid)
        target_doc = (
            self.project.find_document_for_widget(parent_id)
            if parent_id else self.project.active_document
        )
        from app.ui.variables_window import confirm_clipboard_paste_policy
        proceed, policy = confirm_clipboard_paste_policy(
            self.winfo_toplevel(), self.project, target_doc,
        )
        if not proceed:
            return
        new_ids = self.project.paste_from_clipboard(
            parent_id=parent_id, var_policy=policy,
        )
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
        push_zorder_history(self.project, nid, direction)

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
        # Marquee selection on either Select or Edit tool. Don't
        # deselect immediately — defer to release so a drag past the
        # threshold can define a new selection. State 0x0001 is the
        # Tk Shift-pressed bitmask.
        from app.ui.workspace.controls import TOOL_EDIT, TOOL_SELECT
        if self._tool in (TOOL_SELECT, TOOL_EDIT):
            self._marquee_state = {
                "start_x": cx, "start_y": cy,
                "shift": bool(event.state & 0x0001),
                "rect_id": None,
                "active": False,
            }
            return None
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
        if self._marquee_state is not None:
            return self._update_marquee(event)
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
        if self._marquee_state is not None:
            return self._finish_marquee(event)
        return None

    # ------------------------------------------------------------------
    # Marquee selection (drag-rect on empty canvas → multi-select)
    # ------------------------------------------------------------------
    _MARQUEE_THRESHOLD_PX = 5

    def _update_marquee(self, event) -> str | None:
        state = self._marquee_state
        if state is None:
            return None
        cx, cy = self._screen_to_canvas(event.x_root, event.y_root)
        sx, sy = state["start_x"], state["start_y"]
        if not state["active"]:
            # Threshold guard so a plain click doesn't draw a
            # zero-pixel rect or trigger the marquee branch in
            # release.
            if max(abs(cx - sx), abs(cy - sy)) < self._MARQUEE_THRESHOLD_PX:
                return None
            state["active"] = True
            state["rect_id"] = self.canvas.create_rectangle(
                sx, sy, cx, cy,
                outline="#5bc0f8", dash=(5, 4), width=2,
                tags=("marquee_rect",),
            )
        else:
            try:
                self.canvas.coords(state["rect_id"], sx, sy, cx, cy)
            except tk.TclError:
                pass
        return None

    def _finish_marquee(self, event) -> str | None:
        state = self._marquee_state
        self._marquee_state = None
        if state is None:
            return None
        was_drag = state["active"]
        # Tear down the dashed rect first regardless of outcome —
        # leaving it on a corrupted state would confuse the next
        # selection cycle.
        rect_id = state.get("rect_id")
        if rect_id is not None:
            try:
                self.canvas.delete(rect_id)
            except tk.TclError:
                pass
        if not was_drag:
            # Plain click on empty area — match legacy behaviour:
            # clear the selection (Shift-click on empty preserves
            # the existing set so the user can keep building it).
            if not state["shift"]:
                self.project.select_widget(None)
            return None
        # Drag completed past the threshold — compute the rect, find
        # widgets it overlaps, and apply the selection.
        cx, cy = self._screen_to_canvas(event.x_root, event.y_root)
        sx, sy = state["start_x"], state["start_y"]
        rect = (
            min(sx, cx), min(sy, cy),
            max(sx, cx), max(sy, cy),
        )
        hit_ids = self._marquee_intersected_widgets(rect)
        if state["shift"]:
            # Add to the existing selection — same modifier
            # convention as Object Tree multi-select.
            ids = set(self.project.selected_ids or set()) | hit_ids
        else:
            ids = hit_ids
        if ids:
            primary = (
                self.project.selected_id
                if state["shift"] and self.project.selected_id in ids
                else next(iter(ids))
            )
            self.project.set_multi_selection(ids, primary=primary)
            # Multi-select in Edit mode is ambiguous (resize handles
            # only target one widget), so flip to Select tool when
            # the marquee picked up more than one widget — mirrors
            # the existing _select_all_in_doc auto-switch.
            from app.ui.workspace.controls import TOOL_EDIT, TOOL_SELECT
            if len(ids) > 1 and self.controls.tool == TOOL_EDIT:
                self.controls.set_tool(TOOL_SELECT)
        elif not state["shift"]:
            self.project.select_widget(None)
        return None

    def _marquee_intersected_widgets(
        self, rect: tuple[float, float, float, float],
    ) -> set[str]:
        """Top-level widgets in the active document whose canvas
        bbox overlaps ``rect`` (touch mode — any overlap counts).
        Children stay out of the result so a marquee picks the
        whole Frame, not its inner pieces; users still drill in
        with a click for individual children.
        """
        rl, rt, rr, rb = rect
        hits: set[str] = set()
        doc = self.project.active_document
        if doc is None:
            return hits
        for node in doc.root_widgets:
            if not getattr(node, "visible", True):
                continue
            view = self.widget_views.get(node.id)
            if view is None:
                continue
            widget, _wid = view
            bbox = self._widget_canvas_bbox(widget)
            if bbox is None:
                continue
            wl, wt, wr, wb = bbox
            # Touch test — any overlap (Photoshop / Illustrator
            # convention; Figma uses fully-contained instead).
            if wr < rl or wl > rr or wb < rt or wt > rb:
                continue
            hits.add(node.id)
        return hits
