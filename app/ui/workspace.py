import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from app.core.logger import log_error
from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.ui.selection_controller import SelectionController
from app.widgets.registry import get_descriptor

DRAG_THRESHOLD = 5


class Workspace(ctk.CTkFrame):
    def __init__(self, master, project: Project):
        super().__init__(master)
        self.project = project
        self.widget_views: dict[str, tuple] = {}

        self.canvas = tk.Canvas(self, bg="#1e1e1e", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)

        self.selection = SelectionController(self.canvas, project, self.widget_views)

        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        bus = self.project.event_bus
        bus.subscribe("widget_added", self._on_widget_added)
        bus.subscribe("widget_removed", self._on_widget_removed)
        bus.subscribe("property_changed", self._on_property_changed)
        bus.subscribe("selection_changed", self._on_selection_changed)
        bus.subscribe("palette_drop_request", self._on_palette_drop)
        bus.subscribe("widget_z_changed", self._on_widget_z_changed)

        self._drag: dict | None = None

        self.after(0, self._bind_keys)

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
        x = int(node.properties.get("x", 0))
        y = int(node.properties.get("y", 0))
        window_id = self.canvas.create_window(x, y, anchor="nw", window=widget)
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
        canvas_rx = self.canvas.winfo_rootx()
        canvas_ry = self.canvas.winfo_rooty()
        mx_canvas = event.x_root - canvas_rx
        my_canvas = event.y_root - canvas_ry
        self._drag = {
            "nid": nid,
            "offset_x": mx_canvas - wx,
            "offset_y": my_canvas - wy,
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
        canvas_rx = self.canvas.winfo_rootx()
        canvas_ry = self.canvas.winfo_rooty()
        new_x = event.x_root - canvas_rx - self._drag["offset_x"]
        new_y = event.y_root - canvas_ry - self._drag["offset_y"]
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
                self.canvas.coords(window_id, x, y)
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
        properties = dict(descriptor.default_properties)
        properties["x"] = local_x
        properties["y"] = local_y
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
