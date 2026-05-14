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
from tkinter import messagebox, ttk

import customtkinter as ctk

from app.core.commands import (
    AddWidgetCommand,
    BindHandlerCommand,
    BulkAddCommand,
    BulkMoveCommand,
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
from app.ui.workspace.collapsed_tabs_bar import CollapsedTabsBar
from app.ui.workspace.controls import (
    TOOL_CURSORS,
    TOOL_HAND,
    WorkspaceControls,
)
from app.ui.workspace.context_menu import ContextMenu
from app.ui.workspace.drag import WidgetDragController
from app.ui.workspace.drops import DropDispatcher
from app.ui.workspace.event_subs import EventSubscriberRouter
from app.ui.workspace.keyboard import KeyboardActions
from app.ui.workspace.marquee import MarqueeSelection
from app.ui.workspace.props import PropertyRouter
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
from app.ui.workspace.ghost_manager import GhostManager
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
        # Pack order: status bar first (side=bottom), tabs bar after
        # (also side=bottom) so the tabs strip ends up directly above
        # the zoom/status bar. The bar hides itself when no doc is
        # collapsed so the workspace doesn't reserve dead space.
        self.collapsed_tabs_bar = CollapsedTabsBar(self, self)
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
        # Ghost manager — captures inactive docs as desaturated PIL
        # screenshots and swaps in a single canvas image item, freeing
        # tk widget cost while keeping the doc visually present.
        self.ghost_manager = GhostManager(self)
        # Canvas rendering — document rect + builder grid +
        # visibility mask. Declared last so every other sidecar is
        # alive before the first redraw fires.
        self.renderer = Renderer(self)
        # Stateless action sidecars — extracted from core in the
        # v0.0.15.18 refactor. ``event_subs`` owns project.event_bus
        # callback bodies; ``keyboard`` owns arrow/Delete/Escape;
        # ``marquee`` owns the canvas Button-1 dispatch + drag-rect
        # multi-select; ``props`` owns the property_changed router +
        # var binding cache + radio group state; ``drops`` owns
        # palette/component drops + Add Widget cascade;
        # ``context_menu`` owns the canvas/widget right-click menus.
        # ``_subscribe_events`` + canvas bindings below forward to
        # these.
        self.event_subs = EventSubscriberRouter(self)
        self.keyboard = KeyboardActions(self)
        self.marquee = MarqueeSelection(self)
        self.props = PropertyRouter(self)
        self.drops = DropDispatcher(self)
        self.context_menu = ContextMenu(self)

        self.canvas.bind("<Button-1>", self.marquee.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.marquee.on_canvas_motion)
        self.canvas.bind("<ButtonRelease-1>", self.marquee.on_canvas_release)
        self.canvas.bind("<Button-2>", self.controls.on_middle_press)
        self.canvas.bind("<B2-Motion>", self.controls.on_middle_motion)
        self.canvas.bind(
            "<ButtonRelease-2>", self.controls.on_middle_release,
        )
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind(f"<{MOD_KEY}-MouseWheel>", self.zoom.handle_ctrl_wheel)
        self.canvas.bind("<Button-3>", self.context_menu.on_canvas_right_click)

    def _after_zoom_changed(self) -> None:
        """Callback invoked by ZoomController after a zoom update +
        apply_all. Redraws the document rect / grid and refreshes
        selection chrome around the currently selected widget."""
        self._redraw_document()
        # Ghost screenshot images live on the canvas but aren't
        # touched by apply_all — rescale them to match the new zoom.
        if getattr(self, "ghost_manager", None) is not None:
            self.ghost_manager.on_zoom_changed()
        if hasattr(self, "selection"):
            self.selection.update()

    def _subscribe_events(self) -> None:
        bus = self.project.event_bus
        self.lifecycle.subscribe(bus)
        bus.subscribe("property_changed", self.props.on_property_changed)
        bus.subscribe("widget_added", self.props.seed_binding_cache_on_add)
        bus.subscribe(
            "widget_removed", self.props.drop_binding_cache_on_remove,
        )
        bus.subscribe(
            "variable_type_changed", self.props.on_variable_type_changed,
        )
        bus.subscribe(
            "variable_default_changed",
            self.props.on_variable_default_changed,
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
        bus.subscribe("palette_drop_request", self.drops.on_palette_drop)
        bus.subscribe("component_drop_request", self.drops.on_component_drop)
        bus.subscribe("document_resized", self._on_document_resized)
        bus.subscribe("project_renamed", self.event_subs.on_project_renamed)
        bus.subscribe("dirty_changed", self.event_subs.on_dirty_changed)
        bus.subscribe("widget_renamed", self.event_subs.on_any_widget_renamed)
        bus.subscribe(
            "active_document_changed",
            self.event_subs.on_active_document_changed,
        )
        bus.subscribe(
            "documents_reordered", self.event_subs.on_documents_reordered,
        )
        bus.subscribe(
            "document_position_changed",
            self.event_subs.on_document_position_changed,
        )
        bus.subscribe(
            "document_collapsed_changed",
            self.event_subs.on_document_collapsed_changed,
        )
        bus.subscribe(
            "document_ghost_changed",
            self.event_subs.on_document_ghost_changed,
        )
        bus.subscribe(
            "document_removed",
            self.event_subs.on_document_removed_ghost_cleanup,
        )

    # ------------------------------------------------------------------
    # Keyboard-action shims — kept as thin forwards so existing
    # callers (``WorkspaceControls.bind_keys`` + the right-click menu
    # that points ``command=`` at these) don't need to learn the new
    # ``self.keyboard.on_*`` shape. The bodies live in
    # ``app/ui/workspace/keyboard.py``.
    # ------------------------------------------------------------------
    def _on_arrow(self, dx: int, dy: int, fast: bool) -> str | None:
        return self.keyboard.on_arrow(dx, dy, fast)

    def _on_delete(self, _event=None) -> str | None:
        return self.keyboard.on_delete(_event)

    def _on_escape(self, _event=None) -> str | None:
        return self.keyboard.on_escape(_event)

    # ------------------------------------------------------------------
    # Sidecar shims — kept as thin forwards so existing out-of-package
    # callers (``WidgetLifecycle`` for the radio-group hooks,
    # ``MenuMixin`` for the duplicate-selection shortcut) don't need to
    # learn the new ``self.props.*`` / ``self.context_menu.*`` shape.
    # ------------------------------------------------------------------
    def _get_radio_init_kwargs(self, node) -> dict | None:
        return self.props.get_radio_init_kwargs(node)

    def _sync_radio_initial(self, widget, node) -> None:
        self.props.sync_radio_initial(widget, node)

    def _unbind_radio_group(self, widget_id: str) -> None:
        self.props.unbind_radio_group(widget_id)

    def _duplicate_selection(self) -> None:
        self.context_menu._duplicate_selection()

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
                lambda e, n=nid: self.context_menu.on_widget_right_click(e, n),
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
        # Exception: CTkLabel.bind() already reaches its inner canvas +
        # label (routed when unified_bind=True, dual-bound otherwise),
        # so recursing here would stack a second binding on those
        # sub-widgets and every event would fire the handler twice.
        if isinstance(widget, ctk.CTkLabel):
            return
        for child in widget.winfo_children():
            self._bind_widget_events(child, nid)

    # Widget drag / reparent logic lives in ``drag.py`` —
    # ``self.drag_controller`` owns the gesture state.


    # ==================================================================
    # Canvas mouse events (click / motion / release)
    # ==================================================================
