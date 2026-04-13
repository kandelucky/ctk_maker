"""Properties panel for the CTk Visual Builder.

Renders a schema-driven editor for the currently selected widget.
Each widget property is rendered based on its schema metadata
(type, row_label, pair, subgroup, disabled_when, ...).

Supported row layouts (selected per prop):

    [ row_label ][ spacer ][ widget ]                   single-grid row
    [ row_label ][ spacer ][ mini+entry ][ mini+entry ]  numeric paired row
    [ row_label ][ spacer ][ sub+widget ][ sub+widget ]  mixed paired row
    [ label ][ multiline textbox stretch ]               full-width editor

Features:
- Auto-hide scrollbar when content fits
- Collapsible group sections with chevron icons
- Drag-scrub on numeric labels (Photoshop-style)
- Dynamic disabled states via schema lambdas
- Debounced body hide during sash drag to mask CTk flicker
"""
import os
import tkinter as tk
from contextlib import contextmanager
from tkinter import filedialog

import customtkinter as ctk

from ctk_color_picker import ColorPickerDialog

from app.core.logger import log_error
from app.core.project import Project
from app.ui.icons import load_icon
from app.widgets.registry import get_descriptor

# ---- Style colors -----------------------------------------------------------
VALUE_BG = "#2d2d2d"
HEADER_BG = "#2a2a2a"
STATIC_FG = "#888888"        # static row labels (non-interactive)
CHECKED_FG = "#cccccc"       # checkbox label when checked
UNCHECKED_FG = "#888888"     # checkbox label when unchecked
DISABLED_FG = "#555555"
HEADER_FG = "#cccccc"
SUBGROUP_FG = "#aaaaaa"
TYPE_LABEL_FG = "#3b8ed0"

# ---- Geometry ---------------------------------------------------------------
VALUE_CORNER = 3
ROW_LABEL_WIDTH = 60
MINI_LABEL_WIDTH = 16        # X/Y/W/H in numeric paired rows
SUB_LABEL_WIDTH = 50         # size/color/Bold/Italic in mixed paired rows
ENTRY_WIDTH = 52
ENTRY_HEIGHT = 18
BUTTON_HEIGHT = 18
DROPDOWN_HEIGHT = 22
DROPDOWN_WIDTH_ANCHOR = 120
DROPDOWN_WIDTH_COMPOUND = 100
IMAGE_PICKER_WIDTH = 140
CHECKBOX_SIZE = 14

ROW_PAD_RIGHT = 5            # reserves space for scrollbar
SUBGROUP_INDENT = 14

RESIZE_HIDE_DELAY_MS = 150

# ---- Dropdown options -------------------------------------------------------
COMPOUND_OPTIONS = ["top", "left", "right", "bottom"]

ANCHOR_CODE_TO_LABEL = {
    "nw": "Top Left",    "n":  "Top Center",    "ne": "Top Right",
    "w":  "Middle Left", "center": "Center",    "e":  "Middle Right",
    "sw": "Bottom Left", "s":  "Bottom Center", "se": "Bottom Right",
}
ANCHOR_LABEL_TO_CODE = {v: k for k, v in ANCHOR_CODE_TO_LABEL.items()}
ANCHOR_DROPDOWN_ORDER = list(ANCHOR_CODE_TO_LABEL.values())


class PropertiesPanel(ctk.CTkFrame):
    """Schema-driven property editor panel for the currently selected widget.

    Listens to `selection_changed` and `property_changed` on the project
    event bus, and rebuilds or patches its content accordingly.
    """

    def __init__(self, master, project: Project):
        super().__init__(master)
        self.project = project
        self.current_id: str | None = None

        # Editor state
        self._editor_vars: dict[str, tk.Variable] = {}
        self._color_buttons: dict[str, ctk.CTkButton] = {}
        self._image_labels: dict[str, ctk.CTkLabel] = {}
        self._editor_disabled: dict[str, bool] = {}
        self._suspend_trace = False
        self._row_padx: int = 2

        # UI state
        self._collapsed_groups: set[str] = set()
        self._resize_timer: str | None = None
        self._body_hidden = False
        self._last_width = 0

        title = ctk.CTkLabel(self, text="Properties", font=("", 13, "bold"))
        title.pack(pady=(5, 2), padx=10)

        self.body = ctk.CTkScrollableFrame(self)
        self.body.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        self._install_autohide_scrollbar()

        self.project.event_bus.subscribe("selection_changed", self._on_selection)
        self.project.event_bus.subscribe("property_changed", self._on_property_changed)
        self.bind("<Configure>", self._on_panel_configure)

        self._show_empty()

    # ======================================================================
    # Scrollbar auto-hide (CTkScrollableFrame internals)
    # ======================================================================
    def _install_autohide_scrollbar(self) -> None:
        """Wrap `_parent_canvas.yscrollcommand` to hide the scrollbar when
        (first, last) == (0, 1), meaning all content fits the viewport."""
        scrollbar = getattr(self.body, "_scrollbar", None)
        canvas = getattr(self.body, "_parent_canvas", None)
        if scrollbar is None or canvas is None:
            return

        def yscroll_handler(first, last):
            try:
                scrollbar.set(first, last)
            except tk.TclError:
                return
            try:
                if float(first) <= 0.0 and float(last) >= 1.0:
                    scrollbar.grid_remove()
                else:
                    scrollbar.grid()
            except tk.TclError:
                pass

        try:
            canvas.configure(yscrollcommand=yscroll_handler)
        except tk.TclError:
            pass

    # ======================================================================
    # Resize debounce (mask sash-drag flicker of CTkScrollableFrame)
    # ======================================================================
    def _on_panel_configure(self, event) -> None:
        if event.width == self._last_width:
            return
        self._last_width = event.width
        if not self._body_hidden:
            self.body.pack_forget()
            self._body_hidden = True
        if self._resize_timer is not None:
            self.after_cancel(self._resize_timer)
        self._resize_timer = self.after(RESIZE_HIDE_DELAY_MS, self._show_body)

    def _show_body(self) -> None:
        self._resize_timer = None
        if self._body_hidden:
            self.body.pack(fill="both", expand=True, padx=6, pady=(0, 4))
            self._body_hidden = False

    # ======================================================================
    # Event handlers
    # ======================================================================
    def _on_selection(self, widget_id: str | None) -> None:
        self.current_id = widget_id
        self._rebuild()

    def _on_property_changed(self, widget_id: str, prop_name: str, value) -> None:
        """Patch the editor var for a single property change.

        If any disabled_when result changes as a side effect (e.g. Best Fit
        disables Size), do a full rebuild instead — editors need to be
        recreated in their new state.
        """
        if widget_id != self.current_id:
            return
        if self._current_disabled_states() != self._editor_disabled:
            self._rebuild()
            return
        var = self._editor_vars.get(prop_name)
        if var is None:
            return
        self._sync_var(var, value)

    def _sync_var(self, var, value) -> None:
        """Sync an editor var with a new project value.

        Only StringVar updates need the trace-suspend guard — `trace_add`
        callbacks fire on programmatic `var.set()` and would otherwise
        loop back into `_update`. CTkTextbox (KeyRelease-bound) and
        BooleanVar (command-bound on the checkbox) do NOT fire on
        programmatic updates, so no suspend is needed for them.
        """
        if isinstance(var, ctk.CTkTextbox):
            new_text = "" if value is None else str(value)
            if var.get("1.0", "end-1c") == new_text:
                return
            var.delete("1.0", "end")
            if new_text:
                var.insert("1.0", new_text)
            return
        if isinstance(var, tk.BooleanVar):
            new_val = bool(value)
            if var.get() == new_val:
                return
            var.set(new_val)
            return
        new_text = "" if value is None else str(value)
        if var.get() == new_text:
            return
        with self._suspend_traces():
            var.set(new_text)

    @contextmanager
    def _suspend_traces(self):
        """Temporarily suppress trace callbacks.

        Re-entrant: nested `with` blocks preserve the outer suspension
        state (restore old value, not always False).
        """
        old = self._suspend_trace
        self._suspend_trace = True
        try:
            yield
        finally:
            self._suspend_trace = old

    # ======================================================================
    # Rebuild flow
    # ======================================================================
    def _rebuild(self) -> None:
        """Full panel rebuild wrapped with body hide to mask CTk flicker."""
        body_was_visible = False
        try:
            body_was_visible = bool(self.body.winfo_ismapped())
        except tk.TclError:
            pass
        if body_was_visible:
            try:
                self.body.pack_forget()
            except tk.TclError:
                pass
        try:
            self._populate_body()
        finally:
            if body_was_visible:
                try:
                    self.body.pack(fill="both", expand=True,
                                   padx=6, pady=(0, 4))
                except tk.TclError:
                    pass
                self.after_idle(self._refresh_scrollbar_state)

    def _refresh_scrollbar_state(self) -> None:
        """Force CTkScrollableFrame's internal <Configure> layout handler
        to re-run after a rebuild. This is exactly what a user resize does
        to "fix" the stale scrollbar — we generate the same event manually."""
        canvas = getattr(self.body, "_parent_canvas", None)
        if canvas is None:
            return
        try:
            self.update_idletasks()
            canvas.event_generate("<Configure>")
        except tk.TclError:
            pass

    def _populate_body(self) -> None:
        if self.current_id is None:
            self._show_empty()
            return
        node = self.project.get_widget(self.current_id)
        if node is None:
            self._show_empty()
            return
        descriptor = get_descriptor(node.widget_type)
        if descriptor is None:
            self._show_empty()
            return

        self._clear_body()

        type_label = ctk.CTkLabel(
            self.body, text=descriptor.type_name,
            font=("", 11, "bold"), text_color=TYPE_LABEL_FG, height=14,
        )
        type_label.pack(pady=(0, 2), padx=4, anchor="w")

        self._render_schema(descriptor.property_schema, node.properties)
        self._editor_disabled = self._current_disabled_states()

    def _render_schema(self, schema: list, properties: dict) -> None:
        """Walk the schema and dispatch each prop to the right row builder."""
        current_group = None
        current_subgroup = None
        self._row_padx = 2

        i = 0
        while i < len(schema):
            prop = schema[i]
            group = prop.get("group", "General")

            if group != current_group:
                self._build_group_header(group)
                current_group = group
                current_subgroup = None
                self._row_padx = 2

            if group in self._collapsed_groups:
                i += 1
                continue

            subgroup = prop.get("subgroup")
            if subgroup != current_subgroup:
                if subgroup:
                    self._build_subgroup_header(subgroup)
                    self._row_padx = SUBGROUP_INDENT
                else:
                    self._row_padx = 2
                current_subgroup = subgroup

            pair_id = prop.get("pair")
            if pair_id:
                items = []
                j = i
                while j < len(schema) and schema[j].get("pair") == pair_id:
                    items.append(
                        (schema[j], properties.get(schema[j]["name"])),
                    )
                    j += 1
                self._build_paired_row(items)
                i = j
            elif prop.get("row_label"):
                self._build_single_grid_row(
                    prop, properties.get(prop["name"]),
                )
                i += 1
            else:
                self._build_full_width_editor(
                    prop, properties.get(prop["name"]),
                )
                i += 1

    def _show_empty(self) -> None:
        self._clear_body()
        ctk.CTkLabel(
            self.body, text="No selection", text_color="gray",
        ).pack(pady=20)

    def _clear_body(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        self._editor_vars = {}
        self._color_buttons = {}
        self._image_labels = {}
        self._editor_disabled = {}

    # ======================================================================
    # Group / subgroup headers
    # ======================================================================
    def _build_group_header(self, name: str) -> None:
        """Render a dark bar header with chevron; clicking it toggles collapse."""
        is_collapsed = name in self._collapsed_groups
        wrap = ctk.CTkFrame(
            self.body, fg_color=HEADER_BG, height=22, corner_radius=0,
        )
        wrap.pack(fill="x", pady=(4, 2))
        wrap.pack_propagate(False)

        arrow_icon = load_icon("chevron-right" if is_collapsed else "chevron-down")
        if arrow_icon is not None:
            arrow = ctk.CTkLabel(
                wrap, text="", image=arrow_icon, fg_color=HEADER_BG,
                width=16, height=16,
            )
        else:
            arrow = ctk.CTkLabel(
                wrap, text="▶" if is_collapsed else "▼",
                font=("", 9, "bold"), text_color=SUBGROUP_FG,
                fg_color=HEADER_BG, width=12, height=16,
            )
        arrow.pack(side="left", padx=(6, 2))

        header = ctk.CTkLabel(
            wrap, text=name, fg_color=HEADER_BG,
            font=("", 10, "bold"), text_color=HEADER_FG,
            anchor="w", height=16,
        )
        header.pack(side="left", padx=(2, 6))

        for clickable in (wrap, arrow, header):
            clickable.bind(
                "<Button-1>", lambda _e, n=name: self._toggle_group(n),
            )
            try:
                clickable.configure(cursor="hand2")
            except tk.TclError:
                pass

    def _toggle_group(self, name: str) -> None:
        if name in self._collapsed_groups:
            self._collapsed_groups.discard(name)
        else:
            self._collapsed_groups.add(name)
        self._rebuild()

    def _build_subgroup_header(self, name: str) -> None:
        header = ctk.CTkLabel(
            self.body, text=name,
            font=("", 9, "bold"), text_color=SUBGROUP_FG,
            anchor="w", height=12,
        )
        header.pack(fill="x", pady=(2, 1), padx=4)

    # ======================================================================
    # Row builders
    # ======================================================================
    def _new_row_frame(self) -> ctk.CTkFrame:
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x", pady=0, padx=(self._row_padx, ROW_PAD_RIGHT))
        return row

    def _configure_row_grid(self, row: ctk.CTkFrame) -> None:
        """Set up standard grid columns: col 0 = row label, col 1 = spacer."""
        row.grid_columnconfigure(0, minsize=ROW_LABEL_WIDTH)
        row.grid_columnconfigure(1, weight=1)

    def _build_row_label(
        self, row: ctk.CTkFrame, text: str, *,
        draggable: bool = False, disabled: bool = False,
    ) -> ctk.CTkLabel:
        kwargs = dict(text=text, anchor="w", font=("", 10))
        if not draggable:
            kwargs["text_color"] = DISABLED_FG if disabled else STATIC_FG
        label = ctk.CTkLabel(row, **kwargs)
        label.grid(row=0, column=0, sticky="w", padx=(4, 0))
        return label

    def _build_paired_row(self, items: list) -> None:
        """Dispatcher for a group of props sharing the same `pair` key."""
        row = self._new_row_frame()
        first_prop = items[0][0] if items else None
        row_label_text = first_prop.get("row_label") if first_prop else None

        if not row_label_text:
            # No row_label → can't happen in current schema; fall back.
            for i, (prop, value) in enumerate(items):
                cell = ctk.CTkFrame(row, fg_color="transparent")
                cell.pack(side="left", padx=(0 if i == 0 else 6, 0))
                self._build_full_width_editor(prop, value, parent=cell)
            return

        all_numbers = all(p["type"] == "number" for p, _ in items)
        if all_numbers:
            self._render_numeric_paired_row(row, row_label_text, items)
        else:
            self._render_mixed_paired_row(row, row_label_text, items)

    def _render_numeric_paired_row(
        self, row: ctk.CTkFrame, row_label_text: str, items: list,
    ) -> None:
        """Geometry-style: row_label + (mini_label + entry) pairs.

            Position   X [120]  Y [80]
        """
        self._configure_row_grid(row)
        self._build_row_label(row, row_label_text)

        col = 2
        for i, (prop, value) in enumerate(items):
            row.grid_columnconfigure(col, minsize=MINI_LABEL_WIDTH)
            row.grid_columnconfigure(col + 1, minsize=ENTRY_WIDTH)

            disabled = self._eval_disabled(prop)
            label = ctk.CTkLabel(
                row, text=prop["label"], width=MINI_LABEL_WIDTH,
                anchor="e", font=("", 10),
            )
            if disabled:
                label.configure(text_color=DISABLED_FG)
            label.grid(
                row=0, column=col, sticky="ew",
                padx=(6 if i > 0 else 0, 6),
            )

            entry = self._create_number_entry(row, prop, value, drag_label=label)
            entry.grid(row=0, column=col + 1, sticky="ew")
            col += 2

    def _render_mixed_paired_row(
        self, row: ctk.CTkFrame, row_label_text: str, items: list,
    ) -> None:
        """Mixed row: row_label + spacer + (optional sub_label + widget) pairs.

            Size       [13]    Best Fit [☐]
            Style      Bold [☐]   Italic [☐]

        The row_label becomes draggable only if the row holds exactly one
        number item that has no sub_label of its own (so the row label
        itself unambiguously represents that number).
        """
        self._configure_row_grid(row)

        number_items = [p for p, _ in items if p["type"] == "number"]
        single_number_no_sub = (
            len(number_items) == 1
            and not self._eval_disabled(number_items[0])
            and not number_items[0].get("label")
        )
        row_label = self._build_row_label(
            row, row_label_text, draggable=single_number_no_sub,
        )

        col = 2
        for i, (prop, value) in enumerate(items):
            ptype = prop["type"]
            disabled = self._eval_disabled(prop)
            sub_text = prop.get("label", "")
            use_sub_label = bool(sub_text)

            sub_label = None
            if use_sub_label:
                row.grid_columnconfigure(col, minsize=SUB_LABEL_WIDTH)
                sub_label = ctk.CTkLabel(
                    row, text=sub_text, anchor="e", font=("", 10),
                )
                if disabled:
                    sub_label.configure(text_color=DISABLED_FG)
                sub_label.grid(
                    row=0, column=col, sticky="e",
                    padx=(8 if i > 0 else 0, 4),
                )
                col += 1

            if ptype == "color":
                row.grid_columnconfigure(col, minsize=ENTRY_WIDTH)
                btn = self._create_color_button(row, prop, value)
                btn.grid(
                    row=0, column=col, sticky="ew",
                    padx=(8 if i > 0 and not use_sub_label else 0, 0),
                )
            elif ptype == "number":
                row.grid_columnconfigure(col, minsize=ENTRY_WIDTH)
                drag_label = sub_label or (
                    row_label if single_number_no_sub else None
                )
                entry = self._create_number_entry(
                    row, prop, value, drag_label=drag_label,
                )
                entry.grid(
                    row=0, column=col, sticky="ew",
                    padx=(8 if i > 0 and not use_sub_label else 0, 0),
                )
            elif ptype == "boolean":
                cb = self._create_boolean_checkbox(
                    row, prop, value, sub_label=sub_label,
                )
                cb.grid(
                    row=0, column=col, sticky="w",
                    padx=(0 if use_sub_label
                          else (10 if i > 0 else 0), 0),
                )

            col += 1

    def _build_single_grid_row(self, prop: dict, value) -> None:
        """Single-prop row: row_label + spacer + widget.

        Supports all editor types (number/color/boolean/anchor/compound/image).
        The row_label is draggable only for number props (drag-scrub target).
        """
        row = self._new_row_frame()
        self._configure_row_grid(row)
        row.grid_columnconfigure(2, minsize=ENTRY_WIDTH)

        ptype = prop["type"]
        disabled = self._eval_disabled(prop)
        draggable = (ptype == "number") and not disabled

        row_label = self._build_row_label(
            row, prop["row_label"], draggable=draggable, disabled=disabled,
        )

        if ptype == "number":
            entry = self._create_number_entry(
                row, prop, value,
                drag_label=row_label if draggable else None,
            )
            entry.grid(row=0, column=2, sticky="ew")
        elif ptype == "color":
            btn = self._create_color_button(row, prop, value)
            btn.grid(row=0, column=2, sticky="ew")
        elif ptype == "boolean":
            cb = self._create_boolean_checkbox(row, prop, value, sub_label=None)
            cb.grid(row=0, column=2, sticky="w")
        elif ptype == "anchor":
            row.grid_columnconfigure(2, minsize=DROPDOWN_WIDTH_ANCHOR)
            menu = self._create_anchor_dropdown(row, prop, value)
            menu.grid(row=0, column=2, sticky="ew")
        elif ptype == "compound":
            row.grid_columnconfigure(2, minsize=DROPDOWN_WIDTH_COMPOUND)
            menu = self._create_compound_dropdown(row, prop, value)
            menu.grid(row=0, column=2, sticky="ew")
        elif ptype == "image":
            row.grid_columnconfigure(2, minsize=IMAGE_PICKER_WIDTH)
            picker = self._create_image_picker(row, prop, value)
            picker.grid(row=0, column=2, sticky="ew")

    def _build_full_width_editor(
        self, prop: dict, value, parent: ctk.CTkFrame | None = None,
    ) -> None:
        """Full-width row used for the multiline button-text editor.

        Currently only `multiline` type reaches this path in the CTkButton
        schema (all other props use row_label).
        """
        if parent is None:
            parent = ctk.CTkFrame(self.body, fg_color="transparent")
            parent.pack(fill="x", pady=0, padx=(self._row_padx, ROW_PAD_RIGHT))

        pname = prop["name"]
        disabled = self._eval_disabled(prop)
        label_text = prop.get("label", "")

        if label_text:
            label = ctk.CTkLabel(
                parent, text=label_text, width=70, anchor="w",
                font=("", 10), height=18,
            )
            label.pack(side="left", anchor="n", pady=(2, 0))
            if disabled:
                label.configure(text_color=DISABLED_FG)

        if prop["type"] != "multiline":
            return

        tb = ctk.CTkTextbox(
            parent, height=58, font=("", 10), wrap="word",
            border_width=0, fg_color=VALUE_BG, corner_radius=VALUE_CORNER,
        )
        tb.pack(side="left", fill="x", expand=True)
        if value is not None and value != "":
            tb.insert("1.0", str(value))
        if disabled:
            tb.configure(state="disabled")
        else:
            def on_change(_e=None, p=pname, t=tb):
                self._update(p, t.get("1.0", "end-1c"))
            tb.bind("<KeyRelease>", on_change)
        self._editor_vars[pname] = tb

    # ======================================================================
    # Widget creators (shared between row builders)
    # ======================================================================
    def _create_number_entry(
        self, parent, prop: dict, value, *,
        drag_label: ctk.CTkLabel | None = None,
    ) -> ctk.CTkEntry:
        pname = prop["name"]
        disabled = self._eval_disabled(prop)
        state = "disabled" if disabled else "normal"
        var = tk.StringVar(value="" if value is None else str(value))

        entry = ctk.CTkEntry(
            parent, textvariable=var, width=ENTRY_WIDTH,
            height=ENTRY_HEIGHT, font=("", 10), state=state,
            border_width=0, fg_color=VALUE_BG, corner_radius=VALUE_CORNER,
        )

        if not disabled:
            def on_change(*_, p=pname, v=var):
                if self._suspend_trace:
                    return
                text = v.get().strip()
                if not text:
                    return
                try:
                    self._update(p, int(text))
                except ValueError:
                    pass

            var.trace_add("write", on_change)
            if drag_label is not None:
                self._make_label_draggable(drag_label, var, prop)

        self._editor_vars[pname] = var
        return entry

    def _create_color_button(self, parent, prop: dict, value) -> ctk.CTkButton:
        pname = prop["name"]
        disabled = self._eval_disabled(prop)
        state = "disabled" if disabled else "normal"
        color_value = value if value else "#1f6aa5"
        btn = ctk.CTkButton(
            parent, text="",
            fg_color=color_value, hover_color=color_value,
            width=ENTRY_WIDTH, height=BUTTON_HEIGHT,
            border_width=0, corner_radius=0, state=state,
            command=None if disabled else (
                lambda p=pname: self._pick_color(p)),
        )
        self._color_buttons[pname] = btn
        return btn

    def _create_boolean_checkbox(
        self, parent, prop: dict, value, *,
        sub_label: ctk.CTkLabel | None = None,
    ) -> ctk.CTkCheckBox:
        """Checkbox with optional sub_label whose color tracks checked state."""
        pname = prop["name"]
        disabled = self._eval_disabled(prop)
        state = "disabled" if disabled else "normal"
        var = tk.BooleanVar(value=bool(value))

        def on_toggle(p=pname, v=var, sl=sub_label):
            if sl is not None:
                sl.configure(text_color=CHECKED_FG if v.get() else UNCHECKED_FG)
            self._update(p, v.get())

        cb = ctk.CTkCheckBox(
            parent, text="", variable=var,
            height=16, width=20,
            checkbox_width=CHECKBOX_SIZE, checkbox_height=CHECKBOX_SIZE,
            corner_radius=2, border_width=2, state=state,
            command=None if disabled else on_toggle,
        )

        if sub_label is not None and not disabled:
            sub_label.configure(
                text_color=CHECKED_FG if bool(value) else UNCHECKED_FG,
            )

        self._editor_vars[pname] = var
        return cb

    def _create_anchor_dropdown(self, parent, prop: dict, value) -> ctk.CTkOptionMenu:
        pname = prop["name"]
        disabled = self._eval_disabled(prop)
        state = "disabled" if disabled else "normal"
        current_label = ANCHOR_CODE_TO_LABEL.get(value or "center", "Center")
        menu = ctk.CTkOptionMenu(
            parent, values=ANCHOR_DROPDOWN_ORDER,
            width=DROPDOWN_WIDTH_ANCHOR, height=DROPDOWN_HEIGHT,
            font=("", 10), dropdown_font=("", 10),
            fg_color=VALUE_BG, button_color=VALUE_BG,
            button_hover_color="#3a3a3a",
            corner_radius=VALUE_CORNER, state=state,
            command=None if disabled else (
                lambda lbl, p=pname: self._update(
                    p, ANCHOR_LABEL_TO_CODE.get(lbl, "center"))),
        )
        menu.set(current_label)
        return menu

    def _create_compound_dropdown(self, parent, prop: dict, value) -> ctk.CTkOptionMenu:
        pname = prop["name"]
        disabled = self._eval_disabled(prop)
        state = "disabled" if disabled else "normal"
        menu = ctk.CTkOptionMenu(
            parent, values=COMPOUND_OPTIONS,
            width=DROPDOWN_WIDTH_COMPOUND, height=DROPDOWN_HEIGHT,
            font=("", 10), dropdown_font=("", 10),
            fg_color=VALUE_BG, button_color=VALUE_BG,
            button_hover_color="#3a3a3a",
            corner_radius=VALUE_CORNER, state=state,
            command=None if disabled else (
                lambda v, p=pname: self._update(p, v)),
        )
        menu.set(value if value in COMPOUND_OPTIONS else "left")
        return menu

    def _create_image_picker(self, parent, prop: dict, value) -> ctk.CTkFrame:
        pname = prop["name"]
        disabled = self._eval_disabled(prop)
        state = "disabled" if disabled else "normal"

        sub = ctk.CTkFrame(parent, fg_color="transparent")
        name_label = ctk.CTkLabel(
            sub, text=self._image_display_name(value),
            anchor="w",
            text_color=DISABLED_FG if disabled else "#cccccc",
            font=("", 9),
        )
        name_label.pack(fill="x", padx=(0, 2))
        self._image_labels[pname] = name_label

        btn_row = ctk.CTkFrame(sub, fg_color="transparent")
        btn_row.pack(fill="x", pady=(1, 0))

        browse = ctk.CTkButton(
            btn_row, text="Browse...",
            width=70, height=BUTTON_HEIGHT, font=("", 9),
            fg_color=VALUE_BG, hover_color="#3a3a3a",
            border_width=0, corner_radius=VALUE_CORNER, state=state,
            command=None if disabled else (
                lambda p=pname: self._pick_image(p)),
        )
        browse.pack(side="left", padx=(0, 4))

        clear = ctk.CTkButton(
            btn_row, text="Clear",
            width=44, height=BUTTON_HEIGHT, font=("", 9),
            fg_color=VALUE_BG, hover_color="#3a3a3a",
            border_width=0, corner_radius=VALUE_CORNER, state=state,
            command=None if disabled else (
                lambda p=pname: self._clear_image(p)),
        )
        clear.pack(side="left")
        return sub

    # ======================================================================
    # Pickers (image, color)
    # ======================================================================
    def _image_display_name(self, value: str | None) -> str:
        if not value:
            return "(no image)"
        return os.path.basename(value)

    def _pick_image(self, prop_name: str) -> None:
        path = filedialog.askopenfilename(
            title="Select image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self._update(prop_name, path)
        lbl = self._image_labels.get(prop_name)
        if lbl is not None:
            lbl.configure(text=self._image_display_name(path))

    def _clear_image(self, prop_name: str) -> None:
        self._update(prop_name, None)
        lbl = self._image_labels.get(prop_name)
        if lbl is not None:
            lbl.configure(text=self._image_display_name(None))

    def _pick_color(self, prop_name: str) -> None:
        node = self.project.get_widget(self.current_id) if self.current_id else None
        initial = (node.properties.get(prop_name) if node else None) or "#1f6aa5"
        dialog = ColorPickerDialog(self.winfo_toplevel(), initial_color=initial)
        dialog.wait_window()
        hex_value = dialog.result
        if hex_value:
            self._update(prop_name, hex_value)
            btn = self._color_buttons.get(prop_name)
            if btn is not None:
                btn.configure(fg_color=hex_value, hover_color=hex_value)

    # ======================================================================
    # Schema helpers (disabled_when / bounds)
    # ======================================================================
    def _current_disabled_states(self) -> dict[str, bool]:
        if self.current_id is None:
            return {}
        node = self.project.get_widget(self.current_id)
        if node is None:
            return {}
        descriptor = get_descriptor(node.widget_type)
        if descriptor is None:
            return {}
        result: dict[str, bool] = {}
        for prop in descriptor.property_schema:
            fn = prop.get("disabled_when")
            if not callable(fn):
                continue
            try:
                result[prop["name"]] = bool(fn(node.properties))
            except Exception:
                log_error(f"disabled_when lambda for {prop.get('name')}")
                result[prop["name"]] = False
        return result

    def _eval_disabled(self, prop: dict) -> bool:
        fn = prop.get("disabled_when")
        if not callable(fn):
            return False
        if self.current_id is None:
            return False
        node = self.project.get_widget(self.current_id)
        if node is None:
            return False
        try:
            return bool(fn(node.properties))
        except Exception:
            log_error(f"_eval_disabled for {prop.get('name')}")
            return False

    def _resolve_bound(self, bound) -> int | None:
        """Resolve a schema min/max, which may be an int or a lambda(props)."""
        if bound is None:
            return None
        if callable(bound):
            if self.current_id is None:
                return None
            node = self.project.get_widget(self.current_id)
            if node is None:
                return None
            try:
                return int(bound(node.properties))
            except Exception:
                log_error("_resolve_bound lambda")
                return None
        try:
            return int(bound)
        except (ValueError, TypeError):
            return None

    # ======================================================================
    # Drag-scrub (Photoshop-style horizontal drag on numeric labels)
    # ======================================================================
    def _make_label_draggable(
        self, label: ctk.CTkLabel, var: tk.StringVar, prop: dict,
    ) -> None:
        """Bind drag events on a label to scrub the bound number var.

        - Mouse cursor becomes a horizontal double arrow while hovering.
        - Drag horizontally to change value by ±1 per pixel.
        - Hold Alt for 0.2× fine-scrub sensitivity.
        - Clamped to prop's min/max (which may be ints or lambdas).
        """
        prop_name = prop["name"]
        state = {
            "dragging": False, "last_x": 0, "current": 0, "accumulator": 0.0,
        }

        def set_cursor(cursor: str) -> None:
            try:
                label.configure(cursor=cursor)
            except Exception:
                pass

        def on_enter(_e):
            if not state["dragging"]:
                set_cursor("sb_h_double_arrow")

        def on_leave(_e):
            if not state["dragging"]:
                set_cursor("")

        def on_press(e):
            value = 0
            if self.current_id is not None:
                node = self.project.get_widget(self.current_id)
                if node is not None:
                    try:
                        value = int(node.properties.get(prop_name, 0))
                    except (ValueError, TypeError):
                        value = 0
            state["current"] = value
            state["last_x"] = e.x_root
            state["accumulator"] = 0.0
            state["dragging"] = True

        def on_motion(e):
            if not state["dragging"]:
                return
            dx = e.x_root - state["last_x"]
            state["last_x"] = e.x_root
            slow = bool(e.state & 0x20000)
            sensitivity = 0.2 if slow else 1.0
            state["accumulator"] += dx * sensitivity
            delta = int(state["accumulator"])
            if delta == 0:
                return
            state["accumulator"] -= delta
            new_val = state["current"] + delta
            min_val = self._resolve_bound(prop.get("min"))
            max_val = self._resolve_bound(prop.get("max"))
            if min_val is not None and new_val < min_val:
                new_val = min_val
            if max_val is not None and new_val > max_val:
                new_val = max_val
            if new_val == state["current"]:
                return
            state["current"] = new_val
            var.set(str(new_val))

        def on_release(_e):
            state["dragging"] = False
            set_cursor("")

        label.bind("<Enter>", on_enter)
        label.bind("<Leave>", on_leave)
        label.bind("<ButtonPress-1>", on_press)
        label.bind("<B1-Motion>", on_motion)
        label.bind("<ButtonRelease-1>", on_release)

    # ======================================================================
    # Update project
    # ======================================================================
    def _update(self, prop_name: str, value) -> None:
        if self.current_id is None:
            return
        self.project.update_property(self.current_id, prop_name, value)
