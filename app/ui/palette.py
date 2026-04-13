"""Widget Box — palette of CTk widgets grouped by category.

Qt Designer-inspired layout:
    [ Widget Box ]            — title
    [ Filter....... ]         — realtime name filter
    ▼ Buttons                 — collapsible group header
       [icon] Button
       [icon] Check Box       (dimmed if not implemented yet)
       ...
    ▼ Inputs
    ...

Only descriptors that live in `app.widgets.registry` produce real, draggable
items. Unimplemented CTk widgets are rendered as placeholder rows (dimmed,
no click/drag handler) so the user can see the full roadmap at a glance.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass

import customtkinter as ctk

from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.ui.icons import load_icon
from app.widgets.registry import get_descriptor

DRAG_THRESHOLD = 5

# ---- Style ------------------------------------------------------------------
PANEL_BG = "#242424"
GROUP_HEADER_BG = "#2a2a2a"
GROUP_HEADER_FG = "#cccccc"
ITEM_HOVER_BG = "#2e2e2e"
ITEM_FG = "#cccccc"
ITEM_DISABLED_FG = "#555555"
TITLE_FG = "#cccccc"
FILTER_BG = "#1e1e1e"
FILTER_BORDER = "#3c3c3c"

ICON_SIZE = 16
ITEM_HEIGHT = 22
GROUP_HEADER_HEIGHT = 22


@dataclass(frozen=True)
class WidgetEntry:
    type_name: str
    display_name: str
    icon: str


@dataclass(frozen=True)
class WidgetGroup:
    title: str
    items: tuple[WidgetEntry, ...]


CATALOG: tuple[WidgetGroup, ...] = (
    WidgetGroup("Buttons", (
        WidgetEntry("CTkButton", "Button", "square"),
        WidgetEntry("CTkCheckBox", "Check Box", "square-check"),
        WidgetEntry("CTkRadioButton", "Radio Button", "circle-dot"),
        WidgetEntry("CTkSwitch", "Switch", "toggle-left"),
        WidgetEntry("CTkSegmentedButton", "Segmented Button", "rows-3"),
    )),
    WidgetGroup("Inputs", (
        WidgetEntry("CTkEntry", "Entry", "text-cursor-input"),
        WidgetEntry("CTkTextbox", "Textbox", "file-text"),
        WidgetEntry("CTkComboBox", "Combo Box", "chevrons-up-down"),
        WidgetEntry("CTkOptionMenu", "Option Menu", "menu"),
        WidgetEntry("CTkSlider", "Slider", "sliders-horizontal"),
    )),
    WidgetGroup("Containers", (
        WidgetEntry("CTkFrame", "Frame", "frame"),
        WidgetEntry("CTkScrollableFrame", "Scrollable Frame", "scroll-text"),
        WidgetEntry("CTkTabview", "Tab View", "layout-panel-top"),
    )),
    WidgetGroup("Display", (
        WidgetEntry("CTkLabel", "Label", "type"),
        WidgetEntry("CTkProgressBar", "Progress Bar", "loader"),
    )),
)


class Palette(ctk.CTkFrame):
    def __init__(self, master, project: Project):
        super().__init__(master, fg_color=PANEL_BG, corner_radius=0)
        self.project = project

        self._drag: dict | None = None
        self._ghost: tk.Toplevel | None = None
        self._filter_text: str = ""
        self._group_expanded: dict[str, bool] = {g.title: True for g in CATALOG}
        self._chevron_down = load_icon("chevron-down", size=12)
        self._chevron_right = load_icon("chevron-right", size=12)

        self._build_header()
        self._build_filter()
        self._build_scroll_body()
        self._rebuild_catalog()

    # ------------------------------------------------------------------
    # Static chrome
    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        title = ctk.CTkLabel(
            self, text="Widget Box",
            font=("", 11, "bold"), text_color=TITLE_FG, anchor="w",
        )
        title.pack(fill="x", padx=10, pady=(10, 6))

    def _build_filter(self) -> None:
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", lambda *a: self._on_filter_change())
        entry = ctk.CTkEntry(
            self,
            textvariable=self._filter_var,
            placeholder_text="Filter",
            height=24,
            fg_color=FILTER_BG,
            border_color=FILTER_BORDER,
            border_width=1,
            corner_radius=3,
        )
        entry.pack(fill="x", padx=8, pady=(0, 6))

    def _build_scroll_body(self) -> None:
        self.scroll = ctk.CTkScrollableFrame(
            self, fg_color=PANEL_BG, corner_radius=0,
        )
        self.scroll.pack(fill="both", expand=True, padx=0, pady=0)
        self.body = self.scroll  # alias for children

    # ------------------------------------------------------------------
    # Catalog render
    # ------------------------------------------------------------------
    def _rebuild_catalog(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()

        needle = self._filter_text.strip().lower()
        for group in CATALOG:
            visible_items = [
                it for it in group.items
                if not needle or needle in it.display_name.lower()
            ]
            if not visible_items:
                continue
            self._render_group(group, visible_items, force_expanded=bool(needle))

    def _render_group(self, group: WidgetGroup, items: list[WidgetEntry], *,
                      force_expanded: bool) -> None:
        header = ctk.CTkFrame(
            self.body, fg_color=GROUP_HEADER_BG, corner_radius=0,
            height=GROUP_HEADER_HEIGHT,
        )
        header.pack(fill="x", pady=(4, 0))
        header.pack_propagate(False)

        expanded = force_expanded or self._group_expanded.get(group.title, True)
        chevron_img = self._chevron_down if expanded else self._chevron_right
        chevron = ctk.CTkLabel(header, text="", image=chevron_img, width=16)
        chevron.pack(side="left", padx=(6, 2))

        title_lbl = ctk.CTkLabel(
            header, text=group.title,
            font=("", 10, "bold"), text_color=GROUP_HEADER_FG, anchor="w",
        )
        title_lbl.pack(side="left", fill="x", expand=True)

        for w in (header, chevron, title_lbl):
            w.bind(
                "<Button-1>",
                lambda e, t=group.title: self._toggle_group(t),
            )

        if not expanded:
            return

        for entry in items:
            self._render_item(entry)

    def _render_item(self, entry: WidgetEntry) -> None:
        descriptor = get_descriptor(entry.type_name)
        implemented = descriptor is not None

        row = ctk.CTkFrame(
            self.body, fg_color="transparent", height=ITEM_HEIGHT,
        )
        row.pack(fill="x", padx=0, pady=0)
        row.pack_propagate(False)

        icon = load_icon(entry.icon, size=ICON_SIZE)
        icon_lbl = ctk.CTkLabel(row, text="", image=icon, width=18)
        icon_lbl.pack(side="left", padx=(12, 6))

        fg = ITEM_FG if implemented else ITEM_DISABLED_FG
        name_lbl = ctk.CTkLabel(
            row, text=entry.display_name,
            font=("", 10), text_color=fg, anchor="w",
        )
        name_lbl.pack(side="left", fill="x", expand=True)

        if not implemented:
            return

        def on_enter(_e, r=row):
            r.configure(fg_color=ITEM_HOVER_BG)

        def on_leave(_e, r=row):
            r.configure(fg_color="transparent")

        for w in (row, icon_lbl, name_lbl):
            w.bind("<Enter>", on_enter, add="+")
            w.bind("<Leave>", on_leave, add="+")
            self._bind_drag(w, descriptor)

    def _toggle_group(self, title: str) -> None:
        self._group_expanded[title] = not self._group_expanded.get(title, True)
        self._rebuild_catalog()

    def _on_filter_change(self) -> None:
        self._filter_text = self._filter_var.get()
        self._rebuild_catalog()

    # ------------------------------------------------------------------
    # Drag / click-to-add (unchanged from previous palette)
    # ------------------------------------------------------------------
    def _bind_drag(self, widget, descriptor) -> None:
        widget.bind(
            "<ButtonPress-1>",
            lambda e, d=descriptor: self._on_press(e, d), add="+",
        )
        widget.bind("<B1-Motion>", self._on_motion, add="+")
        widget.bind("<ButtonRelease-1>", self._on_release, add="+")

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
        frame = tk.Frame(
            ghost, bg="#1f6aa5", bd=1, relief="solid",
            highlightthickness=1, highlightbackground="#3b8ed0",
        )
        frame.pack()
        tk.Label(
            frame, text=f"+ {descriptor.display_name}",
            bg="#1f6aa5", fg="white",
            font=("", 10, "bold"), padx=10, pady=4,
        ).pack()
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
