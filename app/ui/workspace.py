import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from app.core.logger import log_error
from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.ui.selection_controller import SelectionController
from app.widgets.registry import get_descriptor

DRAG_THRESHOLD = 5
CANVAS_OUTSIDE_BG = "#141414"     # canvas background around the document
DOCUMENT_BG = "#1e1e1e"           # inside the document rectangle
DOCUMENT_BORDER = "#3c3c3c"
DOCUMENT_PADDING = 60             # gutter around document in canvas coords
GRID_SPACING = 20
GRID_DOT_COLOR = "#555555"
GRID_TAG = "grid_dot"
DOC_TAG = "document_bg"

ZOOM_LEVELS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0)
ZOOM_MIN = ZOOM_LEVELS[0]
ZOOM_MAX = ZOOM_LEVELS[-1]


class Workspace(ctk.CTkFrame):
    def __init__(self, master, project: Project):
        super().__init__(master)
        self.project = project
        self.widget_views: dict[str, tuple] = {}

        self._zoom: float = 1.0

        container = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        container.pack(fill="both", expand=True, padx=10, pady=10)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            container, bg=CANVAS_OUTSIDE_BG, highlightthickness=0,
        )
        self.vscroll = tk.Scrollbar(
            container, orient="vertical", command=self.canvas.yview,
        )
        self.hscroll = tk.Scrollbar(
            container, orient="horizontal", command=self.canvas.xview,
        )
        self.canvas.configure(
            yscrollcommand=self.vscroll.set,
            xscrollcommand=self.hscroll.set,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vscroll.grid(row=0, column=1, sticky="ns")
        self.hscroll.grid(row=1, column=0, sticky="ew")

        self.selection = SelectionController(
            self.canvas, project, self.widget_views,
            zoom_provider=lambda: self._zoom,
        )

        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_wheel)

        self._grid_redraw_after: str | None = None

        bus = self.project.event_bus
        bus.subscribe("widget_added", self._on_widget_added)
        bus.subscribe("widget_removed", self._on_widget_removed)
        bus.subscribe("property_changed", self._on_property_changed)
        bus.subscribe("selection_changed", self._on_selection_changed)
        bus.subscribe("palette_drop_request", self._on_palette_drop)
        bus.subscribe("widget_z_changed", self._on_widget_z_changed)
        bus.subscribe("document_resized", self._on_document_resized)

        self.after(0, self._redraw_document)

        self._drag: dict | None = None

        self.after(0, self._bind_keys)

    def _on_canvas_configure(self, _event=None) -> None:
        if self._grid_redraw_after is not None:
            try:
                self.after_cancel(self._grid_redraw_after)
            except ValueError:
                pass
        self._grid_redraw_after = self.after(30, self._draw_grid)

    # ------------------------------------------------------------------
    # Document rectangle + coordinate helpers
    # ------------------------------------------------------------------
    def _redraw_document(self) -> None:
        self.canvas.delete(DOC_TAG)
        dw = int(self.project.document_width * self._zoom)
        dh = int(self.project.document_height * self._zoom)
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

    def _logical_to_canvas(self, lx: int, ly: int) -> tuple[int, int]:
        return (
            DOCUMENT_PADDING + int(lx * self._zoom),
            DOCUMENT_PADDING + int(ly * self._zoom),
        )

    def _canvas_to_logical(self, cx: float, cy: float) -> tuple[int, int]:
        zoom = self._zoom or 1.0
        return (
            int((cx - DOCUMENT_PADDING) / zoom),
            int((cy - DOCUMENT_PADDING) / zoom),
        )

    def _screen_to_canvas(self, x_root: int, y_root: int) -> tuple[float, float]:
        vx = x_root - self.canvas.winfo_rootx()
        vy = y_root - self.canvas.winfo_rooty()
        return self.canvas.canvasx(vx), self.canvas.canvasy(vy)

    def _on_document_resized(self, *_args) -> None:
        self._redraw_document()
        self._apply_zoom_all()

    def _draw_grid(self) -> None:
        self._grid_redraw_after = None
        self.canvas.delete(GRID_TAG)
        dw = int(self.project.document_width * self._zoom)
        dh = int(self.project.document_height * self._zoom)
        if dw <= 0 or dh <= 0:
            return
        spacing = max(4, int(GRID_SPACING * self._zoom))
        pad = DOCUMENT_PADDING
        for x in range(pad, pad + dw + 1, spacing):
            for y in range(pad, pad + dh + 1, spacing):
                self.canvas.create_rectangle(
                    x, y, x + 1, y + 1,
                    outline="", fill=GRID_DOT_COLOR, tags=GRID_TAG,
                )
        self.canvas.tag_raise(GRID_TAG, DOC_TAG)

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------
    def _set_zoom(self, new_zoom: float) -> None:
        new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, new_zoom))
        if abs(new_zoom - self._zoom) < 0.001:
            return
        self._zoom = new_zoom
        self._apply_zoom_all()

    def _zoom_step(self, delta: int) -> None:
        try:
            idx = ZOOM_LEVELS.index(self._zoom)
        except ValueError:
            idx = min(
                range(len(ZOOM_LEVELS)),
                key=lambda i: abs(ZOOM_LEVELS[i] - self._zoom),
            )
        new_idx = max(0, min(len(ZOOM_LEVELS) - 1, idx + delta))
        self._set_zoom(ZOOM_LEVELS[new_idx])

    def _apply_zoom_all(self) -> None:
        for nid, (widget, window_id) in self.widget_views.items():
            node = self.project.get_widget(nid)
            if node is None:
                continue
            self._apply_zoom_to_widget(widget, window_id, node.properties)
        self._redraw_document()
        self.selection.update()

    def _apply_zoom_to_widget(self, widget, window_id, properties: dict) -> None:
        try:
            lx = int(properties.get("x", 0))
            ly = int(properties.get("y", 0))
        except (TypeError, ValueError):
            lx, ly = 0, 0
        cx, cy = self._logical_to_canvas(lx, ly)
        self.canvas.coords(window_id, cx, cy)
        try:
            lw = int(properties.get("width", 0))
            lh = int(properties.get("height", 0))
        except (TypeError, ValueError):
            return
        if lw > 0 and lh > 0:
            try:
                widget.configure(
                    width=max(1, int(lw * self._zoom)),
                    height=max(1, int(lh * self._zoom)),
                )
            except tk.TclError:
                pass

    def _on_ctrl_wheel(self, event) -> str:
        self._zoom_step(1 if event.delta > 0 else -1)
        return "break"

    def _bind_keys(self) -> None:
        top = self.winfo_toplevel()
        for key, dx, dy in (
            ("Left", -1, 0), ("Right", 1, 0),
            ("Up", 0, -1), ("Down", 0, 1),
        ):
            top.bind(f"<KeyPress-{key}>",
                     lambda e, ax=dx, ay=dy: self._on_arrow(ax, ay, fast=False))
            top.bind(f"<Shift-KeyPress-{key}>",
                     lambda e, ax=dx, ay=dy: self._on_arrow(ax, ay, fast=True))
        top.bind("<Delete>", self._on_delete)
        top.bind("<Escape>", self._on_escape)
        top.bind("<Control-equal>", lambda e: self._zoom_keyboard(1))
        top.bind("<Control-plus>", lambda e: self._zoom_keyboard(1))
        top.bind("<Control-minus>", lambda e: self._zoom_keyboard(-1))
        top.bind("<Control-Key-0>", lambda e: self._zoom_reset())

    def _zoom_keyboard(self, delta: int) -> str | None:
        if self._input_focused():
            return None
        self._zoom_step(delta)
        return "break"

    def _zoom_reset(self) -> str | None:
        if self._input_focused():
            return None
        self._set_zoom(1.0)
        return "break"

    def _input_focused(self) -> bool:
        return isinstance(self.focus_get(), (tk.Entry, tk.Text))

    def _schedule_selection_redraw(self) -> None:
        if self._drag is None and not self.selection.is_resizing():
            self.after(10, self.selection.draw)

    def _on_delete(self, _event=None) -> str | None:
        sid = self.project.selected_id
        if sid is None or self._input_focused():
            return None
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

    def _on_arrow(self, dx: int, dy: int, fast: bool) -> str | None:
        sid = self.project.selected_id
        if sid is None or self._input_focused():
            return None
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

    def _on_widget_added(self, node) -> None:
        descriptor = get_descriptor(node.widget_type)
        if descriptor is None:
            return
        widget = descriptor.create_widget(self.canvas, node.properties)
        lx = int(node.properties.get("x", 0))
        ly = int(node.properties.get("y", 0))
        cx, cy = self._logical_to_canvas(lx, ly)
        window_id = self.canvas.create_window(
            cx, cy, anchor="nw", window=widget,
        )
        self._apply_zoom_to_widget(widget, window_id, node.properties)
        self.widget_views[node.id] = (widget, window_id)
        self._bind_widget_events(widget, node.id)

    def _bind_widget_events(self, widget, nid: str) -> None:
        widget.bind("<ButtonPress-1>",
                    lambda e, n=nid: self._on_widget_press(e, n), add="+")
        widget.bind("<B1-Motion>",
                    lambda e, n=nid: self._on_widget_motion(e, n), add="+")
        widget.bind("<ButtonRelease-1>",
                    lambda e, n=nid: self._on_widget_release(e, n), add="+")
        widget.bind("<Button-3>",
                    lambda e, n=nid: self._on_widget_right_click(e, n), add="+")
        try:
            widget.configure(cursor="fleur")
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._bind_widget_events(child, nid)

    def _on_widget_press(self, event, nid: str) -> None:
        self.project.select_widget(nid)
        node = self.project.get_widget(nid)
        if node is None:
            return
        try:
            wx = int(node.properties.get("x", 0))
            wy = int(node.properties.get("y", 0))
        except (ValueError, TypeError):
            wx, wy = 0, 0
        cx, cy = self._screen_to_canvas(event.x_root, event.y_root)
        wcx, wcy = self._logical_to_canvas(wx, wy)
        self._drag = {
            "nid": nid,
            "offset_x": cx - wcx,
            "offset_y": cy - wcy,
            "press_mx": event.x_root,
            "press_my": event.y_root,
            "moved": False,
        }

    def _on_widget_motion(self, event, nid: str) -> None:
        if self._drag is None or self._drag["nid"] != nid:
            return
        if not self._drag["moved"]:
            if (abs(event.x_root - self._drag["press_mx"]) < DRAG_THRESHOLD
                    and abs(event.y_root - self._drag["press_my"]) < DRAG_THRESHOLD):
                return
            self._drag["moved"] = True
        cx, cy = self._screen_to_canvas(event.x_root, event.y_root)
        new_cx = cx - self._drag["offset_x"]
        new_cy = cy - self._drag["offset_y"]
        new_x, new_y = self._canvas_to_logical(new_cx, new_cy)
        self.project.update_property(nid, "x", new_x)
        self.project.update_property(nid, "y", new_y)
        self.selection.update()

    def _on_widget_release(self, _event, _nid: str) -> None:
        self._drag = None

    def _on_widget_right_click(self, event, nid: str) -> str:
        self.project.select_widget(nid)
        menu = tk.Menu(self.winfo_toplevel(), tearoff=0)
        menu.add_command(label="Duplicate",
                         command=lambda: self.project.duplicate_widget(nid))
        menu.add_command(label="Delete", command=self._on_delete)
        menu.add_separator()
        menu.add_command(label="Bring to Front",
                         command=lambda: self.project.bring_to_front(nid))
        menu.add_command(label="Send to Back",
                         command=lambda: self.project.send_to_back(nid))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _on_widget_z_changed(self, widget_id: str, direction: str) -> None:
        if widget_id not in self.widget_views:
            return
        widget, _ = self.widget_views[widget_id]
        if direction == "front":
            widget.lift()
        elif direction == "back":
            widget.lower()
        if widget_id == self.project.selected_id:
            self._schedule_selection_redraw()

    def _on_widget_removed(self, widget_id: str) -> None:
        if widget_id not in self.widget_views:
            return
        widget, window_id = self.widget_views.pop(widget_id)
        self.canvas.delete(window_id)
        widget.destroy()

    def _on_property_changed(self, widget_id: str, prop_name: str, value) -> None:
        if widget_id not in self.widget_views:
            return
        widget, window_id = self.widget_views[widget_id]
        node = self.project.get_widget(widget_id)

        if prop_name in ("x", "y") and node is not None:
            try:
                x = int(node.properties.get("x", 0))
                y = int(node.properties.get("y", 0))
                cx, cy = self._logical_to_canvas(x, y)
                self.canvas.coords(window_id, cx, cy)
            except Exception:
                log_error("workspace._on_property_changed x/y coords")
            if widget_id == self.project.selected_id:
                self._schedule_selection_redraw()
            return

        descriptor = get_descriptor(node.widget_type) if node else None

        triggers = getattr(descriptor, "derived_triggers", None) if descriptor else None
        if descriptor and triggers and prop_name in triggers \
                and hasattr(descriptor, "compute_derived"):
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
                self._apply_zoom_to_widget(widget, window_id, node.properties)
            else:
                widget.configure(**{prop_name: value})
        except Exception:
            log_error(f"workspace._on_property_changed widget.configure {prop_name}")
        text_label = getattr(widget, "_text_label", None)
        if text_label is not None:
            try:
                text_label.lift()
            except tk.TclError:
                pass
        if widget_id == self.project.selected_id:
            self._schedule_selection_redraw()

    def _on_palette_drop(self, descriptor, x_root: int, y_root: int) -> None:
        canvas_x = self.canvas.winfo_rootx()
        canvas_y = self.canvas.winfo_rooty()
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        local_x = x_root - canvas_x
        local_y = y_root - canvas_y
        if not (0 <= local_x < canvas_w and 0 <= local_y < canvas_h):
            return
        cx, cy = self._screen_to_canvas(x_root, y_root)
        lx, ly = self._canvas_to_logical(cx, cy)
        properties = dict(descriptor.default_properties)
        properties["x"] = max(0, lx)
        properties["y"] = max(0, ly)
        node = WidgetNode(
            widget_type=descriptor.type_name,
            properties=properties,
        )
        self.project.add_widget(node)
        self.project.select_widget(node.id)

    def _on_canvas_click(self, event) -> str | None:
        if event.widget is not self.canvas:
            return None
        handle_name = self.selection.handle_at(event.x, event.y)
        if handle_name is not None:
            self.selection.begin_resize(event, handle_name)
            return "break"
        self.project.select_widget(None)
        return None

    def _on_canvas_motion(self, event) -> str | None:
        if not self.selection.is_resizing():
            return None
        self.selection.update_resize(event)
        return "break"

    def _on_canvas_release(self, event) -> str | None:
        if not self.selection.is_resizing():
            return None
        self.selection.end_resize(event)
        return "break"

    def _on_selection_changed(self, _widget_id: str | None) -> None:
        self.selection.draw()
