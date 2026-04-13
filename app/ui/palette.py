import tkinter as tk

import customtkinter as ctk

from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.widgets.registry import all_descriptors

DRAG_THRESHOLD = 5


class Palette(ctk.CTkFrame):
    def __init__(self, master, project: Project):
        super().__init__(master)
        self.project = project

        self._drag: dict | None = None
        self._ghost: tk.Toplevel | None = None

        title = ctk.CTkLabel(self, text="Widgets", font=("", 14, "bold"))
        title.pack(pady=(12, 8), padx=10)

        for descriptor in all_descriptors():
            btn = ctk.CTkButton(
                self,
                text=descriptor.display_name,
                anchor="w",
            )
            btn.pack(pady=4, padx=10, fill="x")
            self._bind_drag(btn, descriptor)

    def _bind_drag(self, widget, descriptor) -> None:
        widget.bind("<ButtonPress-1>",
                    lambda e, d=descriptor: self._on_press(e, d), add="+")
        widget.bind("<B1-Motion>", self._on_motion, add="+")
        widget.bind("<ButtonRelease-1>", self._on_release, add="+")
        for child in widget.winfo_children():
            self._bind_drag(child, descriptor)

    def _on_press(self, event, descriptor) -> None:
        self._drag = {
            "descriptor": descriptor,
            "press_x": event.x_root,
            "press_y": event.y_root,
            "dragging": False,
        }

    def _on_motion(self, event) -> None:
        if self._drag is None:
            return
        if not self._drag["dragging"]:
            dx = abs(event.x_root - self._drag["press_x"])
            dy = abs(event.y_root - self._drag["press_y"])
            if dx < DRAG_THRESHOLD and dy < DRAG_THRESHOLD:
                return
            self._drag["dragging"] = True
            self._create_ghost(self._drag["descriptor"])
        if self._ghost is not None:
            self._ghost.geometry(f"+{event.x_root + 12}+{event.y_root + 12}")

    def _on_release(self, event) -> None:
        if self._drag is None:
            return
        was_dragging = self._drag["dragging"]
        descriptor = self._drag["descriptor"]
        self._destroy_ghost()
        self._drag = None
        if not was_dragging:
            self._add_widget_default(descriptor)
            return
        self.project.event_bus.publish(
            "palette_drop_request", descriptor, event.x_root, event.y_root,
        )

    def _create_ghost(self, descriptor) -> None:
        self._destroy_ghost()
        ghost = tk.Toplevel(self)
        ghost.overrideredirect(True)
        ghost.attributes("-topmost", True)
        try:
            ghost.attributes("-alpha", 0.85)
        except tk.TclError:
            pass
        frame = tk.Frame(ghost, bg="#1f6aa5", bd=1, relief="solid",
                         highlightthickness=1, highlightbackground="#3b8ed0")
        frame.pack()
        tk.Label(frame, text=f"+ {descriptor.display_name}",
                 bg="#1f6aa5", fg="white",
                 font=("", 10, "bold"), padx=10, pady=4).pack()
        ghost.update_idletasks()
        self._ghost = ghost

    def _destroy_ghost(self) -> None:
        if self._ghost is not None:
            try:
                self._ghost.destroy()
            except tk.TclError:
                pass
            self._ghost = None

    def _add_widget_default(self, descriptor) -> None:
        node = WidgetNode(
            widget_type=descriptor.type_name,
            properties=dict(descriptor.default_properties),
        )
        self.project.add_widget(node)
        self.project.select_widget(node.id)
