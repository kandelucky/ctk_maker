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
    DeleteWidgetCommand,
    MoveCommand,
    RenameCommand,
    ReparentCommand,
    ZOrderCommand,
)
from app.core.logger import log_error
from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.ui.dialogs import RenameDialog
from app.ui.icons import load_icon, load_tk_icon
from app.ui.selection_controller import SelectionController
from app.ui.zoom_controller import ZoomController
from app.widgets.layout_schema import (
    LAYOUT_DISPLAY_NAMES,
    LAYOUT_NODE_ONLY_KEYS,
    normalise_layout_type,
)
from app.widgets.registry import get_descriptor

# ---- Drag + canvas ----------------------------------------------------------
DRAG_THRESHOLD = 5
CANVAS_OUTSIDE_BG = "#141414"     # canvas background around the document
DOCUMENT_BG = "#1e1e1e"           # inside the document rectangle
DOCUMENT_BORDER = "#3c3c3c"
DOCUMENT_PADDING = 60             # gutter around document in canvas coords
GRID_SPACING = 20
GRID_DOT_COLOR = "#555555"
GRID_TAG = "grid_dot"
DOC_TAG = "document_bg"

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


def _strip_layout_keys(properties: dict) -> dict:
    """Drop layout_type / pack_* / grid_* before handing properties
    to a CTk widget. Those keys live on the node only — they drive
    the code exporter and the Properties panel, never CTk itself.
    """
    return {
        k: v for k, v in properties.items()
        if k not in LAYOUT_NODE_ONLY_KEYS
    }

# ---- Bottom status bar ------------------------------------------------------
STATUS_BAR_BG = "#252526"
STATUS_BAR_HEIGHT = 26

# ---- Top tool bar -----------------------------------------------------------
TOOL_BAR_BG = "#252526"
TOOL_BAR_HEIGHT = 30
TOOL_BTN_HOVER = "#3a3a3a"
TOOL_BTN_ACTIVE = "#094771"

# Window chrome — the "title bar" drawn above the document
# rectangle on the canvas. Visual representation of the form being
# designed; clicking the bar area selects the virtual Window node,
# clicking the ✕ glyph requests a project close.
CHROME_TAG = "window_chrome"
CHROME_BG_TAG = "window_chrome_bg"
CHROME_TITLE_TAG = "window_chrome_title"
CHROME_SETTINGS_TAG = "window_chrome_settings"
CHROME_SETTINGS_IMG_TAG = "window_chrome_settings_img"
CHROME_MIN_TAG = "window_chrome_min"
CHROME_CLOSE_TAG = "window_chrome_close"
CHROME_HEIGHT = 28
CHROME_BG_COLOR = "#2d2d30"
CHROME_FG_COLOR = "#cccccc"
CHROME_FG_DIM = "#666666"
CHROME_CLOSE_HOVER = "#c42b1c"

TOOL_SELECT = "select"
TOOL_HAND = "hand"

TOOL_CURSORS = {
    TOOL_SELECT: "",
    TOOL_HAND: "hand2",
}


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
        self._build_tool_bar()
        self._build_canvas()
        self._build_status_bar()
        self._subscribe_events()

        self.after(0, self._redraw_document)
        self.after(0, self._bind_keys)

    # ------------------------------------------------------------------
    # __init__ helpers
    # ------------------------------------------------------------------
    def _init_state(self) -> None:
        self.zoom: ZoomController | None = None  # set in _build_canvas
        self._tool: str = TOOL_SELECT
        self._tool_buttons: dict[str, ctk.CTkButton] = {}
        # Mirrors main_window's dirty flag so the canvas title strip
        # can show a trailing "*" next to the project name.
        self._dirty: bool = False
        # tk PhotoImage pair for the canvas title-bar settings icon.
        # Normal (dim) + hover (bright) variants swapped via
        # itemconfigure on mouse enter / leave. Kept alive here so
        # tk doesn't garbage-collect them out from under the canvas.
        self._chrome_settings_icon = load_tk_icon(
            "settings", size=14, color=CHROME_FG_DIM,
        )
        # (app-window is the Window widget icon — separate from the
        # tab view's layout-panel-top used elsewhere.)
        self._chrome_settings_icon_hover = load_tk_icon(
            "settings", size=14, color="#ffffff",
        )

        self._drag: dict | None = None
        self._pan_state: dict | None = None
        self._grid_redraw_after: str | None = None

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

        self.selection = SelectionController(
            self.canvas, self.project, self.widget_views,
            zoom_provider=lambda: self.zoom.value,
            anchor_views=self._anchor_views,
        )

        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Button-2>", self._on_middle_press)
        self.canvas.bind("<B2-Motion>", self._on_middle_motion)
        self.canvas.bind("<ButtonRelease-2>", self._on_middle_release)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Control-MouseWheel>", self.zoom.handle_ctrl_wheel)

    def _after_zoom_changed(self) -> None:
        """Callback invoked by ZoomController after a zoom update +
        apply_all. Redraws the document rect / grid and refreshes
        selection chrome around the currently selected widget."""
        self._redraw_document()
        if hasattr(self, "selection"):
            self.selection.update()

    def _subscribe_events(self) -> None:
        bus = self.project.event_bus
        bus.subscribe("widget_added", self._on_widget_added)
        bus.subscribe("widget_removed", self._on_widget_removed)
        bus.subscribe("property_changed", self._on_property_changed)
        bus.subscribe("selection_changed", self._on_selection_changed)
        bus.subscribe("palette_drop_request", self._on_palette_drop)
        bus.subscribe("widget_z_changed", self._on_widget_z_changed)
        bus.subscribe("widget_reparented", self._on_widget_reparented)
        bus.subscribe(
            "widget_visibility_changed", self._on_widget_visibility_changed,
        )
        bus.subscribe(
            "widget_locked_changed", self._on_widget_locked_changed,
        )
        bus.subscribe("document_resized", self._on_document_resized)
        bus.subscribe("project_renamed", self._on_project_renamed)
        bus.subscribe("dirty_changed", self._on_dirty_changed)
        bus.subscribe("widget_renamed", self._on_any_widget_renamed)
        bus.subscribe(
            "active_document_changed",
            self._on_active_document_changed,
        )

    def _on_active_document_changed(self, *_args, **_kwargs) -> None:
        # Add / remove / active-switch of a document changes which
        # chrome strip is highlighted and, on add/remove, the total
        # scroll region. A full redraw covers both cheaply.
        self._redraw_document()

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
        if self._drag is None and not self.selection.is_resizing():
            self.after(10, self.selection.draw)

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

    def _redraw_document(self) -> None:
        # Wipe every layer up front so stacking starts from a clean
        # state. Each document is then drawn in render order (active
        # last) as a single stacked block: rect → grid → chrome →
        # widgets. Tk's per-item Z order means later blocks cover
        # earlier ones at overlap points — exactly what you want for
        # multi-document forms sitting on top of each other.
        self.canvas.delete(DOC_TAG)
        self.canvas.delete(GRID_TAG)
        self.canvas.delete(CHROME_TAG)
        self.canvas.delete(LAYOUT_OVERLAY_TAG)
        zoom = self.zoom.value
        pad = DOCUMENT_PADDING
        max_right = pad
        max_bottom = pad
        for doc in self._iter_render_order():
            dw = int(doc.width * zoom)
            dh = int(doc.height * zoom)
            x1 = pad + int(doc.canvas_x * zoom)
            y1 = pad + int(doc.canvas_y * zoom)
            x2, y2 = x1 + dw, y1 + dh
            fill = self._doc_fill_color(doc)
            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                fill=fill, outline=DOCUMENT_BORDER, width=1,
                tags=(DOC_TAG, f"doc_rect:{doc.id}"),
            )
            self._draw_grid_for_doc(doc, x1, y1, dw, dh, zoom)
            self._draw_single_chrome(doc)
            # Raise this document's top-level widgets so they sit on
            # top of its rect / grid / chrome and also above every
            # earlier document's stack.
            for node in list(doc.root_widgets):
                entry = self.widget_views.get(node.id)
                if entry is None:
                    continue
                _w, window_id = entry
                if window_id is None:
                    continue
                try:
                    self.canvas.tag_raise(window_id)
                except tk.TclError:
                    pass
            self._draw_layout_overlays_for_doc(doc, x1, y1, x2, y2)
            if x2 > max_right:
                max_right = x2
            if y2 > max_bottom:
                max_bottom = y2
        self.canvas.configure(
            scrollregion=(0, 0, max_right + pad, max_bottom + pad),
        )
        self._update_widget_visibility_across_docs()

    def _doc_fill_color(self, doc) -> str:
        """Resolve the rectangle fill for a document. ``transparent``
        falls back to the canvas document background so the form
        keeps looking like a workspace; explicit hex colours render
        as their actual colour for live preview of the exported
        ``fg_color`` setting.
        """
        value = doc.window_properties.get("fg_color")
        if isinstance(value, str) and value.startswith("#"):
            return value
        return DOCUMENT_BG

    def _iter_render_order(self) -> list:
        docs = list(self.project.documents)
        active_id = self.project.active_document_id
        docs.sort(key=lambda d: 1 if d.id == active_id else 0)
        return docs

    def _raise_active_document_widgets(self) -> None:
        # No-op kept as a stable hook: the `_redraw_document` loop
        # now raises every document's widgets in render order, so a
        # separate "lift active widgets" pass is redundant.
        return

    # ------------------------------------------------------------------
    # Layout overlays — semantic hints for pack/grid containers
    # ------------------------------------------------------------------
    def _draw_layout_overlays_for_doc(
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
        for container in self._iter_containers(doc.root_widgets):
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

    def _iter_containers(self, nodes):
        for n in nodes:
            descriptor = get_descriptor(n.widget_type)
            if descriptor is not None and getattr(
                descriptor, "is_container", False,
            ):
                yield n
            yield from self._iter_containers(n.children)

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

    def _update_widget_visibility_across_docs(self) -> None:
        """Hide top-level widgets whose canvas centre falls inside a
        later-rendered document's rectangle. Works around tk's two-
        layer limit — embedded ``create_window`` items always render
        above drawing items like rectangles, so a widget in Main
        would otherwise punch through Dialog when Dialog is dragged
        on top of it. We fake the mask by flipping the widget item's
        ``state`` to ``hidden`` whenever it's covered.
        """
        zoom = self.zoom.value
        pad = DOCUMENT_PADDING
        render_order = self._iter_render_order()
        # Cache each document's canvas bbox once per pass.
        doc_bboxes: dict[str, tuple[int, int, int, int]] = {}
        for doc in render_order:
            dw = int(doc.width * zoom)
            dh = int(doc.height * zoom)
            x1 = pad + int(doc.canvas_x * zoom)
            y1 = pad + int(doc.canvas_y * zoom)
            doc_bboxes[doc.id] = (x1, y1, x1 + dw, y1 + dh)
        # Render order is [inactive… , active]. A widget belonging
        # to index i is "behind" every doc at index > i, so only
        # those are candidates for covering it.
        for i, doc in enumerate(render_order):
            covering = [
                doc_bboxes[other.id]
                for other in render_order[i + 1:]
            ]
            if not covering:
                # Frontmost doc — its widgets never get hidden.
                for node in list(doc.root_widgets):
                    entry = self.widget_views.get(node.id)
                    if entry is None:
                        continue
                    _w, window_id = entry
                    if window_id is None:
                        continue
                    try:
                        self.canvas.itemconfigure(
                            window_id, state="normal",
                        )
                    except tk.TclError:
                        pass
                continue
            for node in list(doc.root_widgets):
                entry = self.widget_views.get(node.id)
                if entry is None:
                    continue
                widget, window_id = entry
                if window_id is None:
                    continue
                bbox = self._widget_canvas_bbox(widget)
                if bbox is None:
                    continue
                wx1, wy1, wx2, wy2 = bbox
                # Bbox-vs-bbox intersection — a single-pixel touch
                # with any covering document hides the widget.
                hidden = any(
                    wx1 < x2 and wx2 > x1 and wy1 < y2 and wy2 > y1
                    for (x1, y1, x2, y2) in covering
                )
                try:
                    self.canvas.itemconfigure(
                        window_id,
                        state="hidden" if hidden else "normal",
                    )
                except tk.TclError:
                    pass

    def _draw_grid(self) -> None:
        # Legacy debounced entry point — `_on_canvas_configure`
        # schedules this after a resize. Now that grid is drawn
        # inside `_redraw_document` alongside rect + chrome, just
        # bounce through to a full redraw so everything lines up.
        self._grid_redraw_after = None
        self._redraw_document()

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
        if style == "lines":
            for x in range(x1, x1 + dw + 1, spacing):
                self.canvas.create_line(
                    x, y1, x, y1 + dh, fill=color, tags=tag_set,
                )
            for y in range(y1, y1 + dh + 1, spacing):
                self.canvas.create_line(
                    x1, y, x1 + dw, y, fill=color, tags=tag_set,
                )
        else:  # dots (default)
            for x in range(x1, x1 + dw + 1, spacing):
                for y in range(y1, y1 + dh + 1, spacing):
                    self.canvas.create_rectangle(
                        x, y, x + 1, y + 1,
                        outline="", fill=color, tags=tag_set,
                    )

    def _on_canvas_configure(self, _event=None) -> None:
        if self._grid_redraw_after is not None:
            try:
                self.after_cancel(self._grid_redraw_after)
            except ValueError:
                pass
        self._grid_redraw_after = self.after(30, self._draw_grid)

    def _on_document_resized(self, *_args) -> None:
        self._redraw_document()
        self.zoom.apply_all()

    # ==================================================================
    # Top tool bar (Select / Hand)
    # ==================================================================
    def _build_tool_bar(self) -> None:
        bar = ctk.CTkFrame(
            self, fg_color=TOOL_BAR_BG, corner_radius=0,
            height=TOOL_BAR_HEIGHT,
        )
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)

        tools = [
            (TOOL_SELECT, "mouse-pointer-2", "Select (V)"),
            (TOOL_HAND,   "hand",            "Hand (H)"),
        ]
        for tool_id, icon_name, _tooltip in tools:
            icon = load_icon(icon_name, size=16)
            btn = ctk.CTkButton(
                bar, text="" if icon else tool_id[0].upper(),
                image=icon, width=28, height=24,
                corner_radius=3,
                fg_color="transparent", hover_color=TOOL_BTN_HOVER,
                command=lambda t=tool_id: self._set_tool(t),
            )
            btn.pack(
                side="left",
                padx=(4 if tool_id == TOOL_SELECT else 2, 0),
                pady=3,
            )
            self._tool_buttons[tool_id] = btn

        # Right-aligned "Add Dialog" shortcut — mirrors Form → Add
        # Dialog. Explicit text beside the icon so users discover
        # the multi-document flow without hunting through the menu.
        plus_icon = load_icon("plus", size=14)
        add_btn = ctk.CTkButton(
            bar,
            text="Add Dialog",
            image=plus_icon,
            compound="left",
            width=110,
            height=24,
            corner_radius=3,
            fg_color="transparent",
            hover_color=TOOL_BTN_HOVER,
            text_color="#cccccc",
            font=("Segoe UI", 10),
            command=self._on_add_dialog_click,
        )
        add_btn.pack(side="right", padx=(0, 6), pady=3)

        self._refresh_tool_buttons()

    def _on_add_dialog_click(self) -> None:
        self.project.event_bus.publish("request_add_dialog")

    # ==================================================================
    # Canvas window chrome — title bar drawn above the document rect
    # ==================================================================
    def _draw_window_chrome(self) -> None:
        # Chrome is painted per-document inside `_redraw_document`
        # now; this entry point is a thin passthrough kept for
        # legacy callers that want a chrome-only refresh.
        self._redraw_document()

    def _draw_single_chrome(self, doc) -> None:
        zoom = self.zoom.value
        dw = int(doc.width * zoom)
        pad = DOCUMENT_PADDING
        doc_left = pad + int(doc.canvas_x * zoom)
        doc_top = pad + int(doc.canvas_y * zoom)
        top = doc_top - CHROME_HEIGHT
        mid = top + CHROME_HEIGHT // 2
        left = doc_left
        right = doc_left + dw

        title_raw = str(doc.name or "Untitled")
        is_active = doc.id == self.project.active_document_id
        if is_active and self._dirty:
            title_raw = f"{title_raw} *"
        layout = normalise_layout_type(
            doc.window_properties.get("layout_type", "place"),
        )
        if layout != "place":
            display = LAYOUT_DISPLAY_NAMES.get(layout, layout).lower()
            title_raw = f"{title_raw}  · {display}"
        max_chars = max(8, dw // 9)
        if len(title_raw) > max_chars:
            title_raw = title_raw[: max_chars - 1] + "…"

        # Per-document tags so hit-testing + drag know *which*
        # document the click landed on.
        doc_bg_tag = f"chrome_bg:{doc.id}"
        doc_title_tag = f"chrome_title:{doc.id}"
        doc_settings_tag = f"chrome_settings:{doc.id}"
        doc_settings_img_tag = f"chrome_settings_img:{doc.id}"
        doc_close_tag = f"chrome_close:{doc.id}"

        bg_fill = CHROME_BG_COLOR if is_active else "#222222"
        title_fg = CHROME_FG_COLOR if is_active else CHROME_FG_DIM

        self.canvas.create_rectangle(
            left, top, right, doc_top,
            fill=bg_fill, outline=bg_fill,
            tags=(CHROME_TAG, CHROME_BG_TAG, doc_bg_tag),
        )
        self.canvas.create_text(
            left + 14, mid,
            text=title_raw,
            anchor="w",
            fill=title_fg,
            font=("Segoe UI", 10),
            tags=(CHROME_TAG, CHROME_TITLE_TAG, doc_title_tag),
        )
        # Right-hand action cluster: settings, minimize, close.
        if self._chrome_settings_icon is not None:
            sx = right - 78
            self.canvas.create_rectangle(
                sx - 10, top + 2, sx + 10, doc_top - 2,
                fill=bg_fill, outline="",
                tags=(CHROME_TAG, CHROME_SETTINGS_TAG, doc_settings_tag),
            )
            self.canvas.create_image(
                sx, mid,
                image=self._chrome_settings_icon,
                anchor="center",
                tags=(
                    CHROME_TAG, CHROME_SETTINGS_TAG,
                    CHROME_SETTINGS_IMG_TAG,
                    doc_settings_tag, doc_settings_img_tag,
                ),
            )
        self.canvas.create_text(
            right - 48, mid,
            text="−",
            anchor="center",
            fill=CHROME_FG_DIM,
            font=("Segoe UI", 16, "bold"),
            tags=(CHROME_TAG, CHROME_MIN_TAG),
        )
        self.canvas.create_text(
            right - 20, mid,
            text="✕",
            anchor="center",
            fill=title_fg,
            font=("Segoe UI", 12, "bold"),
            tags=(CHROME_TAG, CHROME_CLOSE_TAG, doc_close_tag),
        )
        # Per-document drag binding so clicking / dragging THIS
        # document's strip moves THIS document only (next chunk
        # wires the actual drag handler).
        self._bind_chrome_for_document(
            doc,
            doc_bg_tag, doc_title_tag,
            doc_settings_tag, doc_close_tag,
        )

    def _bind_chrome_for_document(
        self, doc, bg_tag, title_tag, settings_tag, close_tag,
    ) -> None:
        """Wire the click / drag / hover bindings for a single
        document's chrome strip. Each document gets its own tag
        namespace (``chrome_bg:{doc.id}`` etc.) so handlers know
        which form to mutate — essential for multi-document layouts
        where dragging one form must not touch the others.
        """
        doc_id = doc.id
        for tag in (bg_tag, title_tag):
            self.canvas.tag_bind(
                tag, "<ButtonPress-1>",
                lambda e, d=doc_id: self._on_chrome_press(e, d),
            )
            self.canvas.tag_bind(
                tag, "<B1-Motion>",
                lambda e, d=doc_id: self._on_chrome_motion(e, d),
            )
            self.canvas.tag_bind(
                tag, "<ButtonRelease-1>",
                lambda e, d=doc_id: self._on_chrome_release(e, d),
            )
            self.canvas.tag_bind(
                tag, "<Enter>",
                lambda _e: self._set_chrome_cursor("fleur"),
            )
            self.canvas.tag_bind(
                tag, "<Leave>",
                lambda _e: self._set_chrome_cursor(""),
            )
        self.canvas.tag_bind(
            settings_tag, "<Button-1>",
            lambda e, d=doc_id: self._on_chrome_settings_click(e, d),
        )
        self.canvas.tag_bind(
            settings_tag, "<Enter>", self._on_chrome_settings_enter,
        )
        self.canvas.tag_bind(
            settings_tag, "<Leave>", self._on_chrome_settings_leave,
        )
        self.canvas.tag_bind(
            close_tag, "<Button-1>",
            lambda e, d=doc_id: self._on_chrome_close_click(e, d),
        )
        self.canvas.tag_bind(
            close_tag, "<Enter>",
            lambda _e, t=close_tag: self.canvas.itemconfigure(
                t, fill=CHROME_CLOSE_HOVER,
            ),
        )
        self.canvas.tag_bind(
            close_tag, "<Leave>",
            lambda _e, t=close_tag: self.canvas.itemconfigure(
                t, fill=CHROME_FG_COLOR,
            ),
        )

    def _on_chrome_select(self, doc_id: str | None = None) -> None:
        from app.core.project import WINDOW_ID
        if doc_id is not None:
            self.project.set_active_document(doc_id)
        self.project.select_widget(WINDOW_ID)

    def _on_chrome_settings_click(
        self, _event=None, doc_id: str | None = None,
    ) -> str:
        self._on_chrome_select(doc_id)
        return "break"

    def _on_chrome_settings_enter(self, _event=None) -> None:
        if self._chrome_settings_icon_hover is None:
            return
        try:
            self.canvas.itemconfigure(
                CHROME_SETTINGS_IMG_TAG,
                image=self._chrome_settings_icon_hover,
            )
            self.canvas.configure(cursor="hand2")
        except tk.TclError:
            pass

    def _on_chrome_settings_leave(self, _event=None) -> None:
        if self._chrome_settings_icon is None:
            return
        try:
            self.canvas.itemconfigure(
                CHROME_SETTINGS_IMG_TAG,
                image=self._chrome_settings_icon,
            )
            self.canvas.configure(cursor="")
        except tk.TclError:
            pass

    def _set_chrome_cursor(self, cursor: str) -> None:
        # Don't fight the current tool's cursor (Hand mode owns
        # the cursor for the whole canvas).
        if self._tool == TOOL_HAND and cursor == "":
            cursor = TOOL_CURSORS[TOOL_HAND]
        try:
            self.canvas.configure(cursor=cursor)
        except tk.TclError:
            pass

    def _on_chrome_close_click(
        self, _event=None, doc_id: str | None = None,
    ) -> str:
        # Dialog chrome close = remove that dialog from the project.
        # Main window chrome close = project-level close (File/Close).
        # This mirrors OS native behaviour: closing the main window
        # quits the app, closing a dialog just dismisses it.
        if doc_id is not None:
            doc = self.project.get_document(doc_id)
            if doc is not None and doc.is_toplevel:
                self._remove_document(doc_id)
                return "break"
        self.project.event_bus.publish("request_close_project")
        return "break"

    def _remove_document(self, doc_id: str) -> None:
        from app.core.commands import DeleteDocumentCommand
        doc = self.project.get_document(doc_id)
        if doc is None or not doc.is_toplevel:
            return
        # Confirm before destroying the dialog — chrome ✕ used to
        # disappear silently, which was surprising when it happened
        # on an accidental click.
        confirmed = messagebox.askyesno(
            title="Remove dialog",
            message=f"Remove '{doc.name}' from the project?",
            icon="warning",
            parent=self.winfo_toplevel(),
        )
        if not confirmed:
            return
        snapshot = doc.to_dict()
        index = self.project.documents.index(doc)
        for node in list(doc.root_widgets):
            self.project.remove_widget(node.id)
        self.project.documents.remove(doc)
        if self.project.active_document_id == doc_id:
            self.project.active_document_id = (
                self.project.documents[0].id
            )
            self.project.event_bus.publish(
                "active_document_changed",
                self.project.active_document_id,
            )
        self._redraw_document()
        self.project.history.push(
            DeleteDocumentCommand(snapshot, index),
        )

    def _on_chrome_press(self, event, doc_id: str) -> str:
        # Capture the starting logical position of this document so
        # motion events can slide it around the canvas. Dragging one
        # document must not affect the others.
        doc = self.project.get_document(doc_id)
        if doc is None:
            return "break"
        self._chrome_drag = {
            "doc_id": doc_id,
            "start_canvas_x": doc.canvas_x,
            "start_canvas_y": doc.canvas_y,
            "press_x_root": event.x_root,
            "press_y_root": event.y_root,
            "moved": False,
        }
        # Activate the clicked document up front so the title bar
        # immediately reflects focus during the drag.
        self.project.set_active_document(doc_id)
        return "break"

    def _on_chrome_motion(self, event, doc_id: str) -> str:
        # Delegated to the canvas-level motion handler once the
        # press has started — tag_bind motion stops firing the
        # instant the cursor slips off the moving chrome, but the
        # canvas-level bind catches every motion while Button-1 is
        # held. This shim just funnels the event into the same path.
        return self._drive_chrome_drag(event)

    def _drive_chrome_drag(self, event) -> str:
        drag = getattr(self, "_chrome_drag", None)
        if drag is None:
            return ""
        if not drag["moved"]:
            dx = abs(event.x_root - drag["press_x_root"])
            dy = abs(event.y_root - drag["press_y_root"])
            if dx < DRAG_THRESHOLD and dy < DRAG_THRESHOLD:
                return "break"
            drag["moved"] = True
        zoom = self.zoom.value or 1.0
        dx_logical = int((event.x_root - drag["press_x_root"]) / zoom)
        dy_logical = int((event.y_root - drag["press_y_root"]) / zoom)
        doc = self.project.get_document(drag["doc_id"])
        if doc is None:
            return "break"
        doc.canvas_x = max(0, drag["start_canvas_x"] + dx_logical)
        doc.canvas_y = max(0, drag["start_canvas_y"] + dy_logical)
        self._redraw_document()
        self.zoom.apply_all()
        if self.project.selected_id:
            self.selection.update()
        return "break"

    def _on_chrome_release(
        self, _event=None, doc_id: str | None = None,
    ) -> str:
        from app.core.commands import MoveDocumentCommand
        drag = getattr(self, "_chrome_drag", None)
        self._chrome_drag = None
        if drag is None or doc_id is None:
            return "break"
        if not drag["moved"]:
            # Click without drag → activate the document (no
            # automatic Properties panel open; that's the settings
            # icon's job, same as before).
            self.project.set_active_document(doc_id)
            self._redraw_document()
            return "break"
        # Title bar drag finished → push a single undo entry for
        # the whole press→release gesture.
        doc = self.project.get_document(doc_id)
        if doc is None:
            return "break"
        before = (drag["start_canvas_x"], drag["start_canvas_y"])
        after = (doc.canvas_x, doc.canvas_y)
        if before != after:
            self.project.history.push(
                MoveDocumentCommand(doc_id, before, after),
            )
        return "break"

    def _refresh_tool_buttons(self) -> None:
        for tool_id, btn in self._tool_buttons.items():
            if tool_id == self._tool:
                btn.configure(fg_color=TOOL_BTN_ACTIVE)
            else:
                btn.configure(fg_color="transparent")

    def _set_tool(self, tool: str) -> None:
        if tool not in TOOL_CURSORS:
            return
        if tool == self._tool:
            return
        self._tool = tool
        self._pan_state = None
        self._refresh_tool_buttons()
        try:
            self.canvas.configure(cursor=TOOL_CURSORS.get(tool, ""))
        except tk.TclError:
            pass

    # ==================================================================
    # Bottom status bar (zoom controls mounted by ZoomController)
    # ==================================================================
    def _build_status_bar(self) -> None:
        bar = ctk.CTkFrame(
            self, fg_color=STATUS_BAR_BG, corner_radius=0,
            height=STATUS_BAR_HEIGHT,
        )
        bar.pack(side="bottom", fill="x")
        bar.pack_propagate(False)
        self.zoom.mount_controls(bar)

    # ==================================================================
    # Hand-tool pan + middle-mouse pan
    # ==================================================================
    def _begin_pan(self, event) -> None:
        self.canvas.scan_mark(event.x_root, event.y_root)
        self._pan_state = {"active": True}

    def _update_pan(self, event) -> None:
        if self._pan_state is None:
            return
        self.canvas.scan_dragto(event.x_root, event.y_root, gain=1)

    def _end_pan(self, _event) -> None:
        self._pan_state = None

    def _on_middle_press(self, event) -> str:
        self._begin_pan(event)
        try:
            self.canvas.configure(cursor=TOOL_CURSORS[TOOL_HAND])
        except tk.TclError:
            pass
        hand_btn = self._tool_buttons.get(TOOL_HAND)
        if hand_btn is not None:
            hand_btn.configure(fg_color=TOOL_BTN_ACTIVE)
        return "break"

    def _on_middle_motion(self, event) -> str:
        self._update_pan(event)
        return "break"

    def _on_middle_release(self, event) -> str:
        self._end_pan(event)
        try:
            self.canvas.configure(cursor=TOOL_CURSORS.get(self._tool, ""))
        except tk.TclError:
            pass
        self._refresh_tool_buttons()
        return "break"

    # ==================================================================
    # Keyboard shortcuts
    # ==================================================================
    def _bind_keys(self) -> None:
        top = self.winfo_toplevel()
        for key, dx, dy in (
            ("Left", -1, 0), ("Right", 1, 0),
            ("Up", 0, -1), ("Down", 0, 1),
        ):
            top.bind(
                f"<KeyPress-{key}>",
                lambda e, ax=dx, ay=dy: self._on_arrow(ax, ay, fast=False),
            )
            top.bind(
                f"<Shift-KeyPress-{key}>",
                lambda e, ax=dx, ay=dy: self._on_arrow(ax, ay, fast=True),
            )
        top.bind("<Delete>", self._on_delete)
        top.bind("<Escape>", self._on_escape)
        top.bind("<Control-equal>", lambda e: self._zoom_keyboard(1))
        top.bind("<Control-plus>", lambda e: self._zoom_keyboard(1))
        top.bind("<Control-minus>", lambda e: self._zoom_keyboard(-1))
        top.bind("<Control-Key-0>", lambda e: self._zoom_reset())
        top.bind("<KeyPress-v>", lambda e: self._tool_shortcut(TOOL_SELECT))
        top.bind("<KeyPress-V>", lambda e: self._tool_shortcut(TOOL_SELECT))
        top.bind("<KeyPress-h>", lambda e: self._tool_shortcut(TOOL_HAND))
        top.bind("<KeyPress-H>", lambda e: self._tool_shortcut(TOOL_HAND))

    def _tool_shortcut(self, tool: str) -> str | None:
        if self._input_focused():
            return None
        self._set_tool(tool)
        return "break"

    def _zoom_keyboard(self, delta: int) -> str | None:
        if self._input_focused():
            return None
        self.zoom.step(delta)
        return "break"

    def _zoom_reset(self) -> str | None:
        if self._input_focused():
            return None
        self.zoom.reset()
        return "break"

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
        sid = self.project.selected_id
        if sid is None or self._input_focused():
            return None
        if self._effective_locked(sid):
            try:
                self.bell()
            except tk.TclError:
                pass
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
        self.project.remove_widget(sid)
        self.project.history.push(
            DeleteWidgetCommand(snapshot, parent_id, index),
        )
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
    # Widget lifecycle (event-bus → canvas)
    # ==================================================================
    def _on_widget_added(self, node) -> None:
        descriptor = get_descriptor(node.widget_type)
        if descriptor is None:
            return
        parent_node = node.parent
        if parent_node is None:
            master = self.canvas
        else:
            parent_entry = self.widget_views.get(parent_node.id)
            if parent_entry is None:
                master = self.canvas
            else:
                master, _ = parent_entry
        init_kwargs = self._get_radio_init_kwargs(node)
        widget = descriptor.create_widget(
            master, _strip_layout_keys(node.properties),
            init_kwargs=init_kwargs,
        )
        self._sync_radio_initial(widget, node)
        anchor_widget = descriptor.canvas_anchor(widget)
        if anchor_widget is not widget:
            self._anchor_views[node.id] = anchor_widget

        lx = int(node.properties.get("x", 0))
        ly = int(node.properties.get("y", 0))
        lw = int(node.properties.get("width", 0) or 0)
        lh = int(node.properties.get("height", 0) or 0)
        is_composite = anchor_widget is not widget
        owning_doc = self.project.find_document_for_widget(node.id)
        if parent_node is None:
            # Top-level widgets sit inside a specific document; the
            # document's canvas_x/y offset feeds into logical_to_canvas
            # so a second document at canvas_x=900 lands its widgets
            # at (pad + 900*zoom + x*zoom).
            cx, cy = self.zoom.logical_to_canvas(
                lx, ly, document=owning_doc,
            )
            kwargs = {"anchor": "nw", "window": anchor_widget}
            # Composite widgets (CTkScrollableFrame) don't propagate
            # their requested size to the canvas; pin the canvas item
            # size explicitly so the outer container doesn't grow.
            if is_composite and lw > 0 and lh > 0:
                kwargs["width"] = max(1, int(lw * self.zoom.value))
                kwargs["height"] = max(1, int(lh * self.zoom.value))
            window_id = self.canvas.create_window(cx, cy, **kwargs)
        else:
            # nested: place inside parent widget, local coords scaled
            # by zoom. No canvas window id.
            place_kwargs = {
                "x": int(lx * self.zoom.value),
                "y": int(ly * self.zoom.value),
            }
            if is_composite and lw > 0 and lh > 0:
                place_kwargs["width"] = max(1, int(lw * self.zoom.value))
                place_kwargs["height"] = max(1, int(lh * self.zoom.value))
            anchor_widget.place(**place_kwargs)
            window_id = None
        # Pass the owning document so apply_to_widget lands the
        # canvas coords against the *correct* form's offset — not the
        # currently-active one, which for a cross-doc drag is still
        # the source document.
        self.zoom.apply_to_widget(
            widget, window_id, node.properties, document=owning_doc,
        )
        self.widget_views[node.id] = (widget, window_id)
        self._bind_widget_events(anchor_widget, node.id)
        if not node.visible:
            self._set_widget_visibility(widget, window_id, node, False)

    def _on_widget_locked_changed(
        self, widget_id: str, _locked: bool,
    ) -> None:
        # Locked state affects whether selection handles render;
        # redraw if this or an ancestor change touched the selection.
        if self.project.selected_id is not None:
            self.selection.draw()

    def _on_widget_visibility_changed(
        self, widget_id: str, visible: bool,
    ) -> None:
        entry = self.widget_views.get(widget_id)
        if entry is None:
            return
        widget, window_id = entry
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        self._set_widget_visibility(widget, window_id, node, visible)
        if widget_id == self.project.selected_id:
            if visible:
                self._schedule_selection_redraw()
            else:
                self.selection.clear()

    def _set_widget_visibility(
        self, widget, window_id, node, visible: bool,
    ) -> None:
        """Show or hide a widget in the workspace without destroying
        it. Canvas children toggle via `canvas.itemconfigure(state=…)`,
        nested children toggle via fresh `place()` / `place_forget()`
        (can't use `place_configure` after a forget — no place info
        to edit). The model is unchanged — pure rendering control."""
        if window_id is not None:
            try:
                self.canvas.itemconfigure(
                    window_id, state="normal" if visible else "hidden",
                )
            except tk.TclError:
                pass
            return
        if visible:
            try:
                lx = int(node.properties.get("x", 0))
                ly = int(node.properties.get("y", 0))
                widget.place(
                    x=int(lx * self.zoom.value),
                    y=int(ly * self.zoom.value),
                )
                lw = int(node.properties.get("width", 0))
                lh = int(node.properties.get("height", 0))
                if lw > 0 and lh > 0:
                    widget.configure(
                        width=max(1, int(lw * self.zoom.value)),
                        height=max(1, int(lh * self.zoom.value)),
                    )
            except (TypeError, ValueError, tk.TclError):
                pass
        else:
            try:
                widget.place_forget()
            except tk.TclError:
                pass

    def _on_widget_reparented(
        self, widget_id: str,
        _old_parent_id: str | None, _new_parent_id: str | None,
    ) -> None:
        """When a widget's parent changes, destroy its widget view
        subtree and recreate it under the new parent.

        Tkinter doesn't let a widget change its master after creation,
        so reparenting means destroying the CTk/tk widget(s) and
        rebuilding them inside the new master.
        """
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        was_selected = self.project.selected_id == widget_id
        if was_selected:
            self.selection.clear()
        self._destroy_widget_subtree(node)
        self._create_widget_subtree(node)
        if was_selected:
            self.after(20, self.selection.draw)

    def _destroy_widget_subtree(self, node) -> None:
        for child in list(node.children):
            self._destroy_widget_subtree(child)
        entry = self.widget_views.pop(node.id, None)
        if entry is None:
            return
        widget, window_id = entry
        if window_id is not None:
            try:
                self.canvas.delete(window_id)
            except tk.TclError:
                pass
        try:
            widget.destroy()
        except tk.TclError:
            pass

    def _create_widget_subtree(self, node) -> None:
        self._on_widget_added(node)
        for child in node.children:
            self._create_widget_subtree(child)

    def _on_widget_removed(self, widget_id: str) -> None:
        if widget_id not in self.widget_views:
            return
        widget, window_id = self.widget_views.pop(widget_id)
        self._unbind_radio_group(widget_id)
        anchor = self._anchor_views.pop(widget_id, None)
        if window_id is not None:
            try:
                self.canvas.delete(window_id)
            except tk.TclError:
                pass
        try:
            (anchor or widget).destroy()
        except tk.TclError:
            pass

    def _on_widget_z_changed(self, widget_id: str, direction: str) -> None:
        """Restack the reordered widget's siblings in project order.

        Using `widget.lower()` directly on a nested child would push it
        behind CTkFrame's internal drawing canvas and hide it forever.
        Instead we re-`lift()` every sibling from bottom to top so the
        stacking order matches `parent.children`, leaving CTk internals
        below everything we control.
        """
        node = self.project.get_widget(widget_id)
        if node is None:
            return
        siblings = (
            node.parent.children if node.parent is not None
            else self.project.root_widgets
        )
        for sibling in siblings:
            entry = self.widget_views.get(sibling.id)
            if entry is None:
                continue
            try:
                entry[0].lift()
            except tk.TclError:
                pass
        if widget_id == self.project.selected_id:
            self._schedule_selection_redraw()
        _ = direction  # retained in signature for future use

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
            return
        if prop_name in LAYOUT_OVERLAY_TRIGGERS:
            # Layout-overlay props don't change the CTk widget itself;
            # they only affect the semantic hint rendered on the canvas.
            self._redraw_document()
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
            self._on_widget_removed(widget_id)
            self._create_widget_subtree(node)
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
        if widget_id == self.project.selected_id:
            self._schedule_selection_redraw()

    def _on_palette_drop(self, descriptor, x_root: int, y_root: int) -> None:
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
        if container_node is None:
            # Top-level drop: figure out which document the cursor
            # is over and add the widget to that doc's tree. Drops
            # that land outside every document fall through to the
            # active one (default), which matches single-document
            # behaviour.
            target_doc = self._find_document_at_canvas(cx, cy)
            if target_doc is not None:
                self.project.set_active_document(target_doc.id)
            else:
                target_doc = self.project.active_document
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
            properties["x"] = max(0, int(rel_x))
            properties["y"] = max(0, int(rel_y))
            parent_id = container_node.id

        node = WidgetNode(
            widget_type=descriptor.type_name,
            properties=properties,
        )
        self.project.add_widget(node, parent_id=parent_id)
        self.project.select_widget(node.id)
        self.project.history.push(
            AddWidgetCommand(node.to_dict(), parent_id),
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
            lambda e, n=nid: self._on_widget_press(e, n),
        )
        _safe_bind(
            "<B1-Motion>",
            lambda e, n=nid: self._on_widget_motion(e, n),
        )
        _safe_bind(
            "<ButtonRelease-1>",
            lambda e, n=nid: self._on_widget_release(e, n),
        )
        _safe_bind("<Button-2>", self._on_middle_press)
        _safe_bind("<B2-Motion>", self._on_middle_motion)
        _safe_bind("<ButtonRelease-2>", self._on_middle_release)
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

    def _on_widget_press(self, event, nid: str) -> None:
        if self._tool == TOOL_HAND:
            self._begin_pan(event)
            return
        # Clear any stale drag state from a prior interaction whose
        # ButtonRelease was lost (widget destroyed mid-drag, focus
        # switch to another toplevel, etc).
        self._drag = None
        self.project.select_widget(nid)
        if self._effective_locked(nid):
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

    def _on_widget_motion(self, event, nid: str) -> None:
        if self._tool == TOOL_HAND:
            self._update_pan(event)
            return
        # Defense: <B1-Motion> should only fire while button 1 is held.
        # If state says otherwise, a prior release was missed — drop
        # the stale drag and refuse to move the widget.
        if not (event.state & 0x0100):
            self._drag = None
            return
        if self._drag is None or self._drag["nid"] != nid:
            return
        dx_root = event.x_root - self._drag["press_mx"]
        dy_root = event.y_root - self._drag["press_my"]
        if not self._drag["moved"]:
            if abs(dx_root) < DRAG_THRESHOLD and abs(dy_root) < DRAG_THRESHOLD:
                return
            self._drag["moved"] = True
        zoom = self.zoom.value or 1.0
        new_x = self._drag["start_x"] + int(dx_root / zoom)
        new_y = self._drag["start_y"] + int(dy_root / zoom)
        self.project.update_property(nid, "x", new_x)
        self.project.update_property(nid, "y", new_y)
        self.selection.update()

    def _on_widget_release(self, event, _nid: str) -> None:
        if self._tool == TOOL_HAND:
            self._end_pan(event)
            return
        drag = self._drag
        if drag is not None and drag.get("moved"):
            reparented = self._maybe_reparent_dragged(event)
            # Skip the Move record if the widget jumped parents —
            # a proper ReparentCommand would need to capture the full
            # before/after (parent_id, coords) and is out of scope
            # for the first undo/redo pass.
            if not reparented:
                node = self.project.get_widget(drag["nid"])
                if node is not None:
                    try:
                        end_x = int(node.properties.get("x", 0))
                        end_y = int(node.properties.get("y", 0))
                    except (TypeError, ValueError):
                        end_x, end_y = drag["start_x"], drag["start_y"]
                    if (end_x, end_y) != (drag["start_x"], drag["start_y"]):
                        self.project.history.push(
                            MoveCommand(
                                drag["nid"],
                                {"x": drag["start_x"], "y": drag["start_y"]},
                                {"x": end_x, "y": end_y},
                            ),
                        )
        self._drag = None
        # Refresh cover-mask after a drag release so a widget that
        # just slid into / out of another document's area picks up
        # the right hidden state.
        self._update_widget_visibility_across_docs()

    def _maybe_reparent_dragged(self, event) -> bool:
        """On drag release, check if the widget was dropped into a
        different container OR a different document. Either case
        reparents (containers via ``project.reparent``, cross-doc via
        a manual move between document root lists) so undo + rendering
        stay consistent. Returns True when a reparent happened so the
        caller skips the per-widget Move history record.
        """
        if self._drag is None:
            return False
        nid = self._drag["nid"]
        node = self.project.get_widget(nid)
        if node is None:
            return False
        self.canvas.update_idletasks()
        cx, cy = self._screen_to_canvas(event.x_root, event.y_root)
        target = self._find_container_at(cx, cy, exclude_id=nid)
        new_parent_id = target.id if target is not None else None
        old_parent_id = node.parent.id if node.parent is not None else None

        old_doc = self.project.find_document_for_widget(nid)
        if target is not None:
            new_doc = self.project.find_document_for_widget(target.id)
        else:
            new_doc = (
                self._find_document_at_canvas(cx, cy)
                or old_doc
                or self.project.active_document
            )

        cross_doc = new_doc is not None and new_doc is not old_doc
        if new_parent_id == old_parent_id and not cross_doc:
            return False  # same parent, same doc — in-place drag
        # Capture the pre-reparent state for undo BEFORE any mutation.
        old_siblings = (
            node.parent.children if node.parent is not None
            else (old_doc.root_widgets if old_doc is not None
                  else self.project.root_widgets)
        )
        try:
            old_index = old_siblings.index(node)
        except ValueError:
            old_index = len(old_siblings)
        old_x = self._drag["start_x"]
        old_y = self._drag["start_y"]
        # Compute the widget's new logical x/y in the target's coord space.
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

    def _on_widget_right_click(self, event, nid: str) -> str:
        self.project.select_widget(nid)
        menu = tk.Menu(self.winfo_toplevel(), tearoff=0)
        menu.add_command(
            label="Rename",
            command=lambda: self._prompt_rename_widget(nid),
        )
        menu.add_command(
            label="Duplicate",
            command=lambda: self._duplicate_with_history(nid),
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

    def _duplicate_with_history(self, nid: str) -> None:
        new_id = self.project.duplicate_widget(nid)
        if new_id is None:
            return
        clone = self.project.get_widget(new_id)
        if clone is None:
            return
        parent_id = clone.parent.id if clone.parent is not None else None
        siblings = (
            clone.parent.children if clone.parent is not None
            else self.project.root_widgets
        )
        try:
            index = siblings.index(clone)
        except ValueError:
            index = len(siblings) - 1
        self.project.history.push(
            BulkAddCommand(
                [(clone.to_dict(), parent_id, index)],
                label="Duplicate",
            ),
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
        self.project.select_widget(None)
        return None

    def _on_canvas_motion(self, event) -> str | None:
        # Chrome drag in progress wins over every other motion
        # handler — it needs every single Button-1 motion, even when
        # the cursor slips off the title bar items mid-gesture.
        if getattr(self, "_chrome_drag", None) is not None:
            return self._drive_chrome_drag(event)
        if self._tool == TOOL_HAND and self._pan_state is not None:
            self._update_pan(event)
            return "break"
        return None

    def _on_canvas_release(self, event) -> str | None:
        # Canvas-level release terminates any in-progress chrome drag
        # that started on a title bar but slipped off — same reason
        # the motion handler has a canvas-level fallback.
        if getattr(self, "_chrome_drag", None) is not None:
            doc_id = self._chrome_drag.get("doc_id")
            self._on_chrome_release(event, doc_id=doc_id)
            return "break"
        if self._tool == TOOL_HAND:
            self._end_pan(event)
            return "break"
        return None
