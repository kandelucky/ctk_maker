"""Widget Box — palette of CTk widgets grouped by category.

Layout:
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
from typing import Callable

import customtkinter as ctk

from app.core.project import Project
from app.core.widget_node import WidgetNode
from app.ui.icons import load_icon
from app.ui.toolbar import _attach_tooltip
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
    # Preset property overrides — tuple of (key, value) pairs merged
    # on top of ``descriptor.default_properties`` when this palette
    # item creates a new node. Used to expose ready-made layout
    # containers (Vertical / Horizontal / Grid / Group) as distinct
    # palette entries backed by the same CTkFrame
    # descriptor but with different default layout_type / border.
    preset_overrides: tuple[tuple[str, object], ...] = ()
    # Slug base for the auto-generated ``node.name`` on creation
    # (``add_widget`` appends ``_1`` / ``_2`` / ...). None falls back
    # to the widget-type slug. Used so a dropped Vertical Layout
    # shows up in the Object Tree as ``vertical_layout_1`` instead
    # of ``frame_4`` — all three layouts share CTkFrame so the
    # widget-type slug alone would erase the layout-type distinction.
    default_name: str | None = None


@dataclass(frozen=True)
class WidgetGroup:
    title: str
    items: tuple[WidgetEntry, ...]


CATALOG: tuple[WidgetGroup, ...] = (
    WidgetGroup("Layouts", (
        WidgetEntry(
            "CTkFrame", "Vertical Layout", "rows-3",
            preset_overrides=(
                ("layout_type", "vbox"),
                ("fg_color", "transparent"),
                ("width", 240),
                ("height", 180),
            ),
            default_name="vertical_layout",
        ),
        WidgetEntry(
            "CTkFrame", "Horizontal Layout", "columns-3",
            preset_overrides=(
                ("layout_type", "hbox"),
                ("fg_color", "transparent"),
                ("width", 320),
                ("height", 60),
            ),
            default_name="horizontal_layout",
        ),
        WidgetEntry(
            "CTkFrame", "Grid Layout", "grid-3x3",
            preset_overrides=(
                ("layout_type", "grid"),
                ("fg_color", "transparent"),
                ("width", 320),
                ("height", 240),
            ),
            default_name="grid_layout",
        ),
    )),
    WidgetGroup("Buttons", (
        WidgetEntry("CTkButton", "Button", "square-mouse-pointer"),
        WidgetEntry("CTkSegmentedButton", "Segmented Button", "panel-left-right-dashed"),
    )),
    WidgetGroup("Display", (
        WidgetEntry("CTkLabel", "Label", "type"),
        WidgetEntry("Image", "Image", "image"),
        WidgetEntry("Card", "Card", "circle-stop"),
        WidgetEntry("CTkProgressBar", "Progress Bar", "loader"),
        WidgetEntry("CircularProgress", "Circular Progress", "circle-percent"),
    )),
    WidgetGroup("Selection", (
        WidgetEntry("CTkCheckBox", "Check Box", "square-check"),
        WidgetEntry("CTkRadioButton", "Radio Button", "circle-dot"),
        WidgetEntry("CTkSwitch", "Switch", "toggle-left"),
    )),
    WidgetGroup("Input", (
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
)


class Palette(ctk.CTkFrame):
    def __init__(
        self,
        master,
        project: Project,
        path_provider: Callable[[], str | None] | None = None,
    ):
        super().__init__(master, fg_color=PANEL_BG, corner_radius=0)
        self.project = project
        # Returns the current ``.ctkproj`` path for the components
        # panel — components live next to assets/ inside the project
        # folder and can't resolve a root without one.
        self._path_provider = path_provider or (lambda: None)

        self._drag: dict | None = None
        self._ghost: tk.Toplevel | None = None
        # Optional predicate (set by MainWindow) that returns True when
        # the cursor is over a valid drop target. When set, the drag
        # ghost tints red outside target to signal "drop will reject".
        self.drop_validator: Callable[[int, int], bool] | None = None
        self._ghost_frame: tk.Frame | None = None
        self._ghost_label: tk.Label | None = None
        self._ghost_valid: bool | None = None
        self._filter_text: str = ""
        self._group_expanded: dict[str, bool] = {g.title: True for g in CATALOG}
        self._chevron_down = load_icon("chevron-down", size=12)
        self._chevron_right = load_icon("chevron-right", size=12)

        # Tab state — Widgets (the original CATALOG drag source) vs
        # Components (per-project saved widget bundles, see
        # components_panel.py).
        self._active_tab: str = "widgets"

        self._build_tabs()
        self._build_widgets_tab()
        self._build_components_tab()
        self._rebuild_catalog()
        self._show_tab("widgets")

    # ------------------------------------------------------------------
    # Static chrome
    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        self._header = ctk.CTkFrame(
            self, fg_color="transparent", height=26,
        )
        self._header.pack(fill="x", pady=(6, 2), padx=4)
        self._header.pack_propagate(False)

        self._title_lbl = ctk.CTkLabel(
            self._header, textvariable=self._title_var,
            font=("Segoe UI", 13, "bold"), text_color=TITLE_FG,
        )
        self._title_lbl.pack(side="left", expand=True)

    def _build_tabs(self) -> None:
        self._tab_bar = ctk.CTkFrame(self, fg_color="#2a2a2a", corner_radius=5)
        self._tab_bar.pack(fill="x", padx=4, pady=(4, 4))
        self._tab_bar.columnconfigure(0, weight=1)

        btn_kw = dict(
            height=24, corner_radius=5, border_width=0,
            font=("Segoe UI", 11),
        )
        self._btn_widgets = ctk.CTkButton(
            self._tab_bar, text="Widgets",
            command=lambda: self._show_tab("widgets"),
            fg_color="#1f6aa5", text_color="#ffffff",
            hover_color="#1f6aa5", **btn_kw,
        )
        self._btn_components = ctk.CTkButton(
            self._tab_bar, text="Components",
            command=lambda: self._show_tab("components"),
            fg_color="transparent", text_color="#888888",
            hover_color="#333333", **btn_kw,
        )
        self._btn_widgets.grid(row=0, column=0, sticky="ew", padx=2, pady=(2, 1))
        self._btn_components.grid(row=1, column=0, sticky="ew", padx=2, pady=(1, 2))

    def _update_tab_buttons(self, active: str) -> None:
        if active == "widgets":
            self._btn_widgets.configure(
                fg_color="#1f6aa5", text_color="#ffffff",
                hover_color="#1f6aa5",
            )
            self._btn_components.configure(
                fg_color="transparent", text_color="#888888",
                hover_color="#333333",
            )
        else:
            self._btn_components.configure(
                fg_color="#1f6aa5", text_color="#ffffff",
                hover_color="#1f6aa5",
            )
            self._btn_widgets.configure(
                fg_color="transparent", text_color="#888888",
                hover_color="#333333",
            )

    def _build_widgets_tab(self) -> None:
        """Container for the legacy Widgets view: filter entry + the
        scrollable catalog body. Held in a wrapper Frame so the tab
        switcher can pack/forget the whole thing as one unit.
        """
        self._widgets_container = tk.Frame(self, bg=PANEL_BG)

        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", lambda *a: self._on_filter_change())
        self._filter_entry = ctk.CTkEntry(
            self._widgets_container,
            textvariable=self._filter_var,
            placeholder_text="Filter",
            height=24,
            fg_color=FILTER_BG,
            border_color=FILTER_BORDER,
            border_width=1,
            corner_radius=3,
        )
        self._filter_entry.pack(fill="x", padx=8, pady=(0, 6))

        self.scroll = ctk.CTkScrollableFrame(
            self._widgets_container, fg_color=PANEL_BG, corner_radius=0,
            scrollbar_fg_color="transparent",
            scrollbar_button_color="#3a3a3a",
            scrollbar_button_hover_color="#4a4a4a",
        )
        self.scroll.pack(fill="both", expand=True, padx=0, pady=0)
        # Slim the internal scrollbar to 10px (matches Properties/
        # Object Tree). CTkScrollableFrame exposes no kwarg for this,
        # so we reach into its internal CTkScrollbar after construction.
        self.scroll._scrollbar.configure(width=10, corner_radius=4)
        self.body = self.scroll  # alias for children

    def _build_components_tab(self) -> None:
        from app.ui.components_panel import ComponentsPanel
        self._components_panel = ComponentsPanel(
            self, self.project, path_provider=self._path_provider,
        )

    def _show_tab(self, name: str) -> None:
        self._active_tab = name
        self._apply_chrome_layout()
        if name == "components":
            self._components_panel.refresh()

    def _apply_chrome_layout(self) -> None:
        """Idempotent chrome layout: forget every chrome widget, then
        re-pack in the canonical order based on the active tab. Order:
        header (always packed) → tab bar → active tab body. Inside
        the widgets body: filter → scroll.
        """
        for w in (
            self._widgets_container, self._components_panel,
            self._filter_entry, self.scroll,
        ):
            try:
                w.pack_forget()
            except tk.TclError:
                pass

        active = self._active_tab
        if active == "widgets":
            self._widgets_container.pack(fill="both", expand=True)
            self._filter_entry.pack(fill="x", padx=8, pady=(0, 6))
            self.scroll.pack(fill="both", expand=True)
        else:
            self._components_panel.pack(fill="both", expand=True)

        self._update_tab_buttons(active)

    # ------------------------------------------------------------------
    # Catalog render
    # ------------------------------------------------------------------
    def _rebuild_catalog(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        self._first_group_rendered = False

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
            font=("Segoe UI", 10, "bold"), text_color=GROUP_HEADER_FG, anchor="w",
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
            font=("Segoe UI", 10), text_color=fg, anchor="w",
        )
        name_lbl.pack(side="left", fill="x", expand=True)
        bind_targets = (row, icon_lbl, name_lbl)

        if not implemented:
            return

        def on_enter(_e, r=row):
            r.configure(fg_color=ITEM_HOVER_BG)

        def on_leave(_e, r=row):
            r.configure(fg_color="transparent")

        for w in bind_targets:
            w.bind("<Enter>", on_enter, add="+")
            w.bind("<Leave>", on_leave, add="+")
            self._bind_drag(w, entry, descriptor)

    def _toggle_group(self, title: str) -> None:
        self._group_expanded[title] = not self._group_expanded.get(title, True)
        self._rebuild_catalog()

    def _on_filter_change(self) -> None:
        self._filter_text = self._filter_var.get()
        self._rebuild_catalog()

    # ------------------------------------------------------------------
    # Drag / click-to-add (unchanged from previous palette)
    # ------------------------------------------------------------------
    def _bind_drag(self, widget, entry: WidgetEntry, descriptor) -> None:
        widget.bind(
            "<ButtonPress-1>",
            lambda e, en=entry, d=descriptor: self._on_press(e, en, d),
            add="+",
        )
        widget.bind("<B1-Motion>", self._on_motion, add="+")
        widget.bind("<ButtonRelease-1>", self._on_release, add="+")

    def _on_press(self, event, entry: WidgetEntry, descriptor) -> None:
        self._drag = {
            "entry": entry,
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
            self._create_ghost(self._drag["entry"])
        if self._ghost is not None:
            self._ghost.geometry(f"+{event.x_root + 12}+{event.y_root + 12}")
            self._update_ghost_state(event.x_root, event.y_root)

    def _on_release(self, event) -> None:
        if self._drag is None:
            return
        was_dragging = self._drag["dragging"]
        entry = self._drag["entry"]
        descriptor = self._drag["descriptor"]
        self._destroy_ghost()
        self._drag = None
        if not was_dragging:
            self._add_widget_default(entry, descriptor)
            return
        self.project.event_bus.publish(
            "palette_drop_request", entry, descriptor,
            event.x_root, event.y_root,
        )

    def _create_ghost(self, entry: WidgetEntry) -> None:
        self._destroy_ghost()
        # Pull a hex colour off the descriptor's default `fg_color` so
        # the drag preview matches the colour the dropped widget will
        # actually have. Containers / themed defaults that store
        # "transparent" or a (light, dark) tuple fall back to the
        # generic CTk blue.
        bg_color = "#6366f1"
        descriptor = self._drag["descriptor"] if self._drag else None
        if descriptor is not None:
            candidate = descriptor.default_properties.get("fg_color")
            if isinstance(candidate, str) and candidate.startswith("#"):
                bg_color = candidate
        self._ghost_valid_bg = bg_color
        ghost = tk.Toplevel(self)
        ghost.overrideredirect(True)
        ghost.attributes("-topmost", True)
        try:
            ghost.attributes("-alpha", 0.85)
        except tk.TclError:
            pass
        frame = tk.Frame(
            ghost, bg=bg_color, bd=1, relief="solid",
            highlightthickness=1, highlightbackground=bg_color,
        )
        frame.pack()
        label = tk.Label(
            frame, text=f"+ {entry.display_name}",
            bg=bg_color, fg="white",
            font=("Segoe UI", 10, "bold"), padx=10, pady=4,
        )
        label.pack()
        ghost.update_idletasks()
        self._ghost = ghost
        self._ghost_frame = frame
        self._ghost_label = label
        self._ghost_valid = True

    def _destroy_ghost(self) -> None:
        if self._ghost is not None:
            try:
                self._ghost.destroy()
            except tk.TclError:
                pass
            self._ghost = None
        self._ghost_frame = None
        self._ghost_label = None
        self._ghost_valid = None

    def _update_ghost_state(self, x_root: int, y_root: int) -> None:
        """Tint the drag ghost green-ish when over a valid drop target,
        red when outside all documents. No-op if no validator is wired.
        """
        if self.drop_validator is None or self._ghost_frame is None:
            return
        try:
            valid = bool(self.drop_validator(x_root, y_root))
        except Exception:
            valid = True
        if valid == self._ghost_valid:
            return
        self._ghost_valid = valid
        valid_bg = getattr(self, "_ghost_valid_bg", "#6366f1")
        bg = valid_bg if valid else "#8b2a2a"
        border = valid_bg if valid else "#c44343"
        try:
            self._ghost_frame.configure(
                bg=bg, highlightbackground=border,
            )
            if self._ghost_label is not None:
                self._ghost_label.configure(bg=bg)
        except tk.TclError:
            pass

    def add_entry(self, entry: WidgetEntry) -> None:
        """Add a widget from a palette entry — called by the Widget menu."""
        descriptor = get_descriptor(entry.type_name)
        if descriptor is None:
            return
        self._add_widget_default(entry, descriptor)

    def _add_widget_default(
        self, entry: WidgetEntry, descriptor,
    ) -> None:
        from app.core.commands import AddWidgetCommand
        from app.core.project import find_free_cascade_slot

        properties = dict(descriptor.default_properties)
        for key, value in entry.preset_overrides:
            properties[key] = value
        # Cascade offset: repeated clicks on the same palette entry
        # would otherwise stack widgets at the exact default x/y.
        doc = self.project.active_document
        if doc is not None:
            start_x = int(properties.get("x", 0) or 0)
            start_y = int(properties.get("y", 0) or 0)
            x, y = find_free_cascade_slot(
                doc.root_widgets, start_xy=(start_x, start_y),
            )
            properties["x"] = x
            properties["y"] = y
        node = WidgetNode(
            widget_type=descriptor.type_name,
            properties=properties,
        )
        self.project.add_widget(node, name_base=entry.default_name)
        self.project.select_widget(node.id)
        doc_id = doc.id if doc is not None else None
        self.project.history.push(
            AddWidgetCommand(
                node.to_dict(), parent_id=None, document_id=doc_id,
            ),
        )
