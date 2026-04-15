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

from app.core.logger import log_error
from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.ui.dialogs import RenameDialog
from app.ui.icons import load_icon
from app.ui.selection_controller import SelectionController
from app.ui.zoom_controller import ZoomController
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

# ---- Bottom status bar ------------------------------------------------------
STATUS_BAR_BG = "#252526"
STATUS_BAR_HEIGHT = 26

# ---- Top tool bar -----------------------------------------------------------
TOOL_BAR_BG = "#252526"
TOOL_BAR_HEIGHT = 30
TOOL_BTN_HOVER = "#3a3a3a"
TOOL_BTN_ACTIVE = "#094771"

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
            fg_color="#1a1a1a",
            button_color="#3a3a3a",
            button_hover_color="#4a4a4a",
        )
        self.hscroll = ctk.CTkScrollbar(
            container, orientation="horizontal",
            command=self.canvas.xview,
            height=10, corner_radius=4,
            fg_color="#1a1a1a",
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
        self.canvas.delete(DOC_TAG)
        zoom = self.zoom.value
        dw = int(self.project.document_width * zoom)
        dh = int(self.project.document_height * zoom)
        pad = DOCUMENT_PADDING
        x1, y1 = pad, pad
        x2, y2 = pad + dw, pad + dh
        self.canvas.create_rectangle(
            x1, y1, x2, y2,
            fill=DOCUMENT_BG, outline=DOCUMENT_BORDER, width=1,
            tags=DOC_TAG,
        )
        self.canvas.tag_lower(DOC_TAG)
        self.canvas.configure(
            scrollregion=(0, 0, pad * 2 + dw, pad * 2 + dh),
        )
        self._draw_grid()

    def _draw_grid(self) -> None:
        self._grid_redraw_after = None
        self.canvas.delete(GRID_TAG)
        zoom = self.zoom.value
        dw = int(self.project.document_width * zoom)
        dh = int(self.project.document_height * zoom)
        if dw <= 0 or dh <= 0:
            return
        spacing = max(4, int(GRID_SPACING * zoom))
        pad = DOCUMENT_PADDING
        for x in range(pad, pad + dw + 1, spacing):
            for y in range(pad, pad + dh + 1, spacing):
                self.canvas.create_rectangle(
                    x, y, x + 1, y + 1,
                    outline="", fill=GRID_DOT_COLOR, tags=GRID_TAG,
                )
        self.canvas.tag_raise(GRID_TAG, DOC_TAG)

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

        self._refresh_tool_buttons()

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
            self.project.update_property(sid, "x", x + dx * step)
        if dy:
            self.project.update_property(sid, "y", y + dy * step)
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
        self.project.remove_widget(sid)
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
                # parent hasn't been rendered yet (shouldn't normally
                # happen); fall back to canvas to avoid dropping the node
                master = self.canvas
            else:
                master, _ = parent_entry
        init_kwargs = self._get_radio_init_kwargs(node)
        widget = descriptor.create_widget(
            master, node.properties, init_kwargs=init_kwargs,
        )
        self._sync_radio_initial(widget, node)
        # Composite widgets (e.g. CTkScrollableFrame) expose a
        # different outer container for `canvas.create_window` / place
        # / event binding / selection bbox.
        anchor_widget = descriptor.canvas_anchor(widget)
        if anchor_widget is not widget:
            self._anchor_views[node.id] = anchor_widget

        lx = int(node.properties.get("x", 0))
        ly = int(node.properties.get("y", 0))
        lw = int(node.properties.get("width", 0) or 0)
        lh = int(node.properties.get("height", 0) or 0)
        is_composite = anchor_widget is not widget
        if parent_node is None:
            cx, cy = self.zoom.logical_to_canvas(lx, ly)
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
        self.zoom.apply_to_widget(widget, window_id, node.properties)
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
        if widget_id not in self.widget_views:
            return
        widget, window_id = self.widget_views[widget_id]
        node = self.project.get_widget(widget_id)

        if prop_name in ("x", "y") and node is not None:
            try:
                x = int(node.properties.get("x", 0))
                y = int(node.properties.get("y", 0))
                if window_id is not None:
                    cx, cy = self.zoom.logical_to_canvas(x, y)
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
                transformed = descriptor.transform_properties(node.properties)
                if transformed:
                    widget.configure(**transformed)
                descriptor.apply_state(widget, node.properties)
                # Radio group: reflect `initially_checked` changes on
                # the shared IntVar — `group` changes themselves trip
                # recreate_triggers above, not here.
                self._sync_radio_initial(widget, node)
                self.zoom.apply_to_widget(widget, window_id, node.properties)
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
            # Top-level drop on the canvas document.
            lx, ly = self.zoom.canvas_to_logical(cx, cy)
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
        except (tk.TclError, NotImplementedError):
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
        if self._drag is not None and self._drag.get("moved"):
            self._maybe_reparent_dragged(event)
        self._drag = None

    def _maybe_reparent_dragged(self, event) -> None:
        """On drag release, check if the widget was dropped into a
        different container. If so, convert its coordinates to the
        new parent's system and reparent via `project.reparent`.
        """
        if self._drag is None:
            return
        nid = self._drag["nid"]
        node = self.project.get_widget(nid)
        if node is None:
            return
        self.canvas.update_idletasks()
        cx, cy = self._screen_to_canvas(event.x_root, event.y_root)
        target = self._find_container_at(cx, cy, exclude_id=nid)
        new_parent_id = target.id if target is not None else None
        old_parent_id = node.parent.id if node.parent is not None else None
        if new_parent_id == old_parent_id:
            return  # same parent — drag was in-place
        # Compute the widget's new logical x/y in the target's coord space.
        widget, _ = self.widget_views[nid]
        zoom = self.zoom.value or 1.0
        if target is None:
            # Back to top-level — use canvas doc coords.
            rx = widget.winfo_rootx() - self.canvas.winfo_rootx()
            ry = widget.winfo_rooty() - self.canvas.winfo_rooty()
            canvas_x = self.canvas.canvasx(rx)
            canvas_y = self.canvas.canvasy(ry)
            new_x = int((canvas_x - DOCUMENT_PADDING) / zoom)
            new_y = int((canvas_y - DOCUMENT_PADDING) / zoom)
        else:
            target_widget, _ = self.widget_views[target.id]
            rel_x = widget.winfo_rootx() - target_widget.winfo_rootx()
            rel_y = widget.winfo_rooty() - target_widget.winfo_rooty()
            new_x = int(rel_x / zoom)
            new_y = int(rel_y / zoom)
        # Write the new coords directly; reparent will trigger a
        # widget rebuild that picks them up.
        node.properties["x"] = new_x
        node.properties["y"] = new_y
        self.project.reparent(nid, new_parent_id)

    def _on_widget_right_click(self, event, nid: str) -> str:
        self.project.select_widget(nid)
        menu = tk.Menu(self.winfo_toplevel(), tearoff=0)
        menu.add_command(
            label="Rename",
            command=lambda: self._prompt_rename_widget(nid),
        )
        menu.add_command(
            label="Duplicate",
            command=lambda: self.project.duplicate_widget(nid),
        )
        menu.add_command(label="Delete", command=self._on_delete)
        menu.add_separator()
        menu.add_command(
            label="Bring to Front",
            command=lambda: self.project.bring_to_front(nid),
        )
        menu.add_command(
            label="Send to Back",
            command=lambda: self.project.send_to_back(nid),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _prompt_rename_widget(self, nid: str) -> None:
        node = self.project.get_widget(nid)
        if node is None:
            return
        dialog = RenameDialog(self.winfo_toplevel(), node.name)
        if dialog.result:
            self.project.rename_widget(nid, dialog.result)

    # ==================================================================
    # Canvas mouse events (click / motion / release)
    # ==================================================================
    def _on_canvas_click(self, event) -> str | None:
        if event.widget is not self.canvas:
            return None
        if self._tool == TOOL_HAND:
            self._begin_pan(event)
            return "break"
        # Selection handles are now embedded widgets that capture
        # Button-1 directly, so canvas clicks can't land on them.
        self.project.select_widget(None)
        return None

    def _on_canvas_motion(self, event) -> str | None:
        if self._tool == TOOL_HAND and self._pan_state is not None:
            self._update_pan(event)
            return "break"
        return None

    def _on_canvas_release(self, event) -> str | None:
        if self._tool == TOOL_HAND:
            self._end_pan(event)
            return "break"
        return None
