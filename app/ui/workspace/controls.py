"""Workspace chrome controls — tool bar, status bar, pan + keys.

Everything related to switching the active tool (Select / Hand),
panning the canvas (hand mode + middle-mouse), and wiring global
keyboard shortcuts lives here. The workspace still owns the
``tk.Frame`` hierarchy (this class packs the tool bar and status
bar into it), but all state + logic for these concerns is owned
by ``WorkspaceControls``.

Split out of the old monolithic ``workspace.py`` so the bar UI,
pan state machine and keybindings are in one focused module.
Core ``Workspace`` holds a single instance on ``self.controls``
and exposes thin delegators for sibling modules (``chrome.py``,
``drag.py``) that need to read the current tool or drive panning.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from app.ui.icons import load_icon
from app.ui.toolbar import _attach_tooltip
from app.core.platform_compat import MOD_KEY, ALT_STATE_BIT

# Tool identifiers — also used by ``chrome.py`` (via the workspace
# delegator) and ``drag.py`` (via the literal ``"hand"`` string).
# ``edit`` is the original arrow — click to select, drag to move,
# resize handles visible, properties panel rebuilds on every click.
# ``select`` is the lighter-weight mode — click selects, drag moves,
# no resize handles, properties panel stays minimal. Useful for
# layout work where accidental property mutations hurt more than
# they help.
TOOL_EDIT = "edit"
TOOL_SELECT = "select"
TOOL_HAND = "hand"
TOOL_CURSORS: dict[str, str] = {
    TOOL_EDIT: "",
    TOOL_SELECT: "",
    TOOL_HAND: "hand2",
}

# Visual styles
TOOL_BAR_BG = "#252526"
TOOL_BAR_HEIGHT = 30
TOOL_BTN_HOVER = "#3a3a3a"
TOOL_BTN_ACTIVE = "#094771"
STATUS_BAR_BG = "#252526"
STATUS_BAR_HEIGHT = 26


class WorkspaceControls:
    """Per-workspace tool bar / status bar / pan / keybinding owner.

    Constructor takes a weak reference to the parent Workspace and
    stores all tool-related state on itself. Workspace reads the
    current tool via ``self.controls.tool`` and drives panning
    through the exposed pan API.
    """

    ICON_ON  = "#cccccc"
    ICON_OFF = "#555555"

    def __init__(self, workspace) -> None:
        self.workspace = workspace
        self._tool: str = TOOL_EDIT
        self._tool_buttons: dict[str, ctk.CTkButton] = {}
        self._pan_state: dict | None = None
        self._btn_preview: ctk.CTkButton | None = None
        self._btn_preview_active: ctk.CTkButton | None = None
        self._icon_play_on  = load_icon("play", size=16, color=self.ICON_ON)
        self._icon_play_off = load_icon("play", size=16, color=self.ICON_OFF)
        self._icon_sq_on    = load_icon("square-play", size=16, color=self.ICON_ON)
        self._icon_sq_off   = load_icon("square-play", size=16, color=self.ICON_OFF)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------
    @property
    def canvas(self) -> tk.Canvas:
        return self.workspace.canvas

    @property
    def zoom(self):
        return self.workspace.zoom

    @property
    def project(self):
        return self.workspace.project

    @property
    def tool(self) -> str:
        return self._tool

    def is_panning(self) -> bool:
        return self._pan_state is not None

    def default_cursor(self) -> str:
        """Cursor to restore after transient hover states
        (e.g. chrome drag).
        """
        return TOOL_CURSORS.get(self._tool, "")

    # ------------------------------------------------------------------
    # Tool bar + status bar UI
    # ------------------------------------------------------------------
    def build_tool_bar(self) -> None:
        bar = ctk.CTkFrame(
            self.workspace, fg_color=TOOL_BAR_BG, corner_radius=0,
            height=TOOL_BAR_HEIGHT,
        )
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)

        tools = [
            (TOOL_EDIT,   "vector-square",        "Edit (Q)"),
            (TOOL_SELECT, "square-mouse-pointer", "Select (W)"),
            (TOOL_HAND,   "hand",                 "Hand (E)"),
        ]
        for tool_id, icon_name, _tooltip in tools:
            icon = load_icon(icon_name, size=16)
            btn = ctk.CTkButton(
                bar, text="" if icon else tool_id[0].upper(),
                image=icon, width=28, height=24,
                corner_radius=3,
                fg_color="transparent", hover_color=TOOL_BTN_HOVER,
                command=lambda t=tool_id: self.set_tool(t),
            )
            btn.pack(
                side="left",
                padx=(4 if tool_id == TOOL_EDIT else 2, 0),
                pady=3,
            )
            self._tool_buttons[tool_id] = btn
            _attach_tooltip(btn, _tooltip)

        # Centre — Preview + Preview Active
        sq_play = load_icon("square-play", size=16)
        _btn_kw = dict(
            text="", width=28, height=24, corner_radius=3,
            fg_color="transparent", hover_color=TOOL_BTN_HOVER,
        )
        center = ctk.CTkFrame(bar, fg_color="transparent")
        center.pack(side="left", expand=True, fill="x")

        self._btn_preview = ctk.CTkButton(
            center, image=self._icon_play_off,
            command=lambda: self.project.event_bus.publish("request_preview"),
            **_btn_kw,
        )
        self._btn_preview.pack(
            side="left", expand=True, anchor="e", padx=(0, 2), pady=3,
        )
        _attach_tooltip(self._btn_preview, "Preview Project (Ctrl+R)")

        self._btn_preview_active = ctk.CTkButton(
            center, image=self._icon_sq_off,
            command=lambda: self.project.event_bus.publish(
                "request_preview_active",
            ),
            **_btn_kw,
        )
        self._btn_preview_active.pack(
            side="left", expand=True, anchor="w", padx=(2, 0), pady=3,
        )
        _attach_tooltip(self._btn_preview_active, "Preview Active Dialog (Ctrl+P)")

        # Subscribe to project events to keep button states in sync
        bus = self.project.event_bus
        for evt in (
            "widget_added", "widget_removed",
            "active_document_changed", "project_renamed",
        ):
            bus.subscribe(evt, lambda *_a, **_k: self.refresh_preview_buttons())
        self.refresh_preview_buttons()

        # Right-aligned "Add Dialog" + "All Forms ▾" group
        import tkinter as tk
        _MENU_STYLE = dict(
            bg="#2d2d30", fg="#cccccc",
            activebackground="#094771", activeforeground="#ffffff",
            bd=0, borderwidth=0, relief="flat",
            font=("Segoe UI", 10),
        )

        def _show_forms_menu(event=None, btn=None):
            menu = tk.Menu(bar, tearoff=0, **_MENU_STYLE)
            active_id = self.project.active_document_id
            for doc in self.project.documents:
                label = doc.name or "Untitled"
                if doc.is_toplevel:
                    label = f"{label}  (Dialog)"
                is_active = doc.id == active_id
                menu.add_command(
                    label=("▸ " if is_active else "   ") + label,
                    foreground="#ffffff" if is_active else "#cccccc",
                    command=lambda did=doc.id: self._focus_document(did),
                )
            try:
                x = btn.winfo_rootx()
                y = btn.winfo_rooty() + btn.winfo_height()
                menu.tk_popup(x, y)
            finally:
                menu.grab_release()

        chevron_icon = load_icon("chevron-down", size=12)
        forms_btn = ctk.CTkButton(
            bar, text="All Windows",
            image=chevron_icon, compound="right",
            width=100, height=24, corner_radius=3,
            fg_color="transparent", hover_color=TOOL_BTN_HOVER,
            text_color="#cccccc", font=("Segoe UI", 10),
        )
        forms_btn.configure(
            command=lambda b=forms_btn: _show_forms_menu(btn=b),
        )
        forms_btn.pack(side="right", padx=(0, 6), pady=3)

        # Separator between Add Dialog and All Forms
        ctk.CTkFrame(
            bar, width=1, fg_color="#3c3c3c", corner_radius=0,
        ).pack(side="right", fill="y", pady=6)

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
        add_btn.pack(side="right", padx=(0, 2), pady=3)

        # Separator between Add Dialog and Variables — mirrors the
        # Add Dialog ↔ All Windows separator so the three groups read
        # as distinct controls instead of one long button row.
        ctk.CTkFrame(
            bar, width=1, fg_color="#3c3c3c", corner_radius=0,
        ).pack(side="right", fill="y", pady=6)

        # "Data" button — opens the Data window on the Global tab.
        # Packed AFTER add_btn so it lands visually to
        # add_btn's left (side="right" stacks newer items inward).
        from app.ui.icons import VARIABLES_GLOBAL_COLOR
        vars_icon = load_icon(
            "variable", size=14, color=VARIABLES_GLOBAL_COLOR,
        )
        vars_btn = ctk.CTkButton(
            bar,
            text="Data",
            image=vars_icon,
            compound="left",
            width=100,
            height=24,
            corner_radius=3,
            fg_color="transparent",
            hover_color=TOOL_BTN_HOVER,
            text_color="#cccccc",
            font=("Segoe UI", 10),
            command=self._on_variables_click,
        )
        vars_btn.pack(side="right", padx=(0, 4), pady=3)

        self._refresh_tool_buttons()

    def build_status_bar(self) -> None:
        bar = ctk.CTkFrame(
            self.workspace, fg_color=STATUS_BAR_BG, corner_radius=0,
            height=STATUS_BAR_HEIGHT,
        )
        bar.pack(side="bottom", fill="x")
        bar.pack_propagate(False)
        self.zoom.mount_controls(bar)

    def _on_add_dialog_click(self) -> None:
        self.project.event_bus.publish("request_add_dialog")

    def _on_variables_click(self) -> None:
        self.project.event_bus.publish(
            "request_open_variables_window", "global", None,
        )

    def _focus_document(self, doc_id: str) -> None:
        self.project.set_active_document(doc_id)
        self.workspace.focus_document(doc_id)

    def refresh_preview_buttons(self) -> None:
        if self._btn_preview is None:
            return
        doc = self.project.active_document
        # Preview (main window) — active when any widget exists in project
        main_has_widgets = bool(self.project.root_widgets)
        self._btn_preview.configure(
            image=self._icon_play_on if main_has_widgets else self._icon_play_off,
        )
        # Preview Active — active when on a dialog with at least one widget
        is_dialog = getattr(doc, "is_toplevel", False)
        dialog_has_widgets = is_dialog and bool(doc.root_widgets)
        self._btn_preview_active.configure(
            image=self._icon_sq_on if dialog_has_widgets else self._icon_sq_off,
        )

    def _refresh_tool_buttons(self) -> None:
        for tool_id, btn in self._tool_buttons.items():
            if tool_id == self._tool:
                btn.configure(fg_color=TOOL_BTN_ACTIVE)
            else:
                btn.configure(fg_color="transparent")

    def set_tool(self, tool: str) -> None:
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
        # Selection handles are tool-dependent — Select mode hides them,
        # Edit mode shows them. Redraw so the change takes effect
        # without waiting for the next interaction.
        if self.workspace.project.selected_id is not None:
            self.workspace.selection.draw()
        # Properties panel also depends on tool (Select tool skips the
        # full schema rebuild). Notify listeners so the panel can
        # refresh without needing a click-through.
        try:
            self.workspace.project.event_bus.publish(
                "tool_changed", tool,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Pan (hand tool + middle-mouse)
    # ------------------------------------------------------------------
    def begin_pan(self, event) -> None:
        self.canvas.scan_mark(event.x_root, event.y_root)
        self._pan_state = {"active": True}

    def update_pan(self, event) -> None:
        if self._pan_state is None:
            return
        self.canvas.scan_dragto(event.x_root, event.y_root, gain=1)

    def end_pan(self, _event) -> None:
        self._pan_state = None

    def on_middle_press(self, event) -> str:
        self.begin_pan(event)
        try:
            self.canvas.configure(cursor=TOOL_CURSORS[TOOL_HAND])
        except tk.TclError:
            pass
        hand_btn = self._tool_buttons.get(TOOL_HAND)
        if hand_btn is not None:
            hand_btn.configure(fg_color=TOOL_BTN_ACTIVE)
        return "break"

    def on_middle_motion(self, event) -> str:
        self.update_pan(event)
        return "break"

    def on_middle_release(self, event) -> str:
        self.end_pan(event)
        try:
            self.canvas.configure(cursor=TOOL_CURSORS.get(self._tool, ""))
        except tk.TclError:
            pass
        self._refresh_tool_buttons()
        return "break"

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------
    def bind_keys(self) -> None:
        top = self.workspace.winfo_toplevel()
        for key, dx, dy in (
            ("Left", -1, 0), ("Right", 1, 0),
            ("Up", 0, -1), ("Down", 0, 1),
        ):
            top.bind(
                f"<KeyPress-{key}>",
                lambda e, ax=dx, ay=dy:
                    self.workspace._on_arrow(ax, ay, fast=False),
            )
            top.bind(
                f"<Shift-KeyPress-{key}>",
                lambda e, ax=dx, ay=dy:
                    self.workspace._on_arrow(ax, ay, fast=True),
            )
        top.bind("<Delete>", self.workspace._on_delete)
        top.bind("<Escape>", self.workspace._on_escape)
        top.bind(f"<{MOD_KEY}-equal>", lambda e: self._zoom_keyboard(1))
        top.bind(f"<{MOD_KEY}-plus>", lambda e: self._zoom_keyboard(1))
        top.bind(f"<{MOD_KEY}-minus>", lambda e: self._zoom_keyboard(-1))
        top.bind(f"<{MOD_KEY}-Key-0>", lambda e: self._zoom_reset())
        # Dispatch tool shortcuts by hardware keycode so the same
        # physical Q/W/E keys fire on Latin and non-Latin layouts
        # alike (Tk can't match Latin keysyms when a Georgian /
        # Cyrillic layout is active — bpo-46052).
        top.bind("<KeyPress>", self._on_tool_keypress, add="+")

    # Hardware keycodes for the three tool shortcuts. Identical
    # across keyboard layouts (Q, W, E physical keys).
    _KC_Q = 81
    _KC_W = 87
    _KC_E = 69
    _CTRL_MASK = 0x04

    def _on_tool_keypress(self, event) -> str | None:
        if self.workspace._input_focused():
            return None
        # Reserve Ctrl-/Alt-modified keys for accelerators
        # (Ctrl+Q quits, Ctrl+W closes the project, ...).
        if event.state & (self._CTRL_MASK | ALT_STATE_BIT):
            return None
        kc = event.keycode
        if kc == self._KC_Q:
            self.set_tool(TOOL_EDIT)
            return "break"
        if kc == self._KC_W:
            self.set_tool(TOOL_SELECT)
            return "break"
        if kc == self._KC_E:
            self.set_tool(TOOL_HAND)
            return "break"
        return None

    def _zoom_keyboard(self, delta: int) -> str | None:
        if self.workspace._input_focused():
            return None
        self.zoom.step(delta)
        return "break"

    def _zoom_reset(self) -> str | None:
        if self.workspace._input_focused():
            return None
        self.zoom.reset()
        return "break"
