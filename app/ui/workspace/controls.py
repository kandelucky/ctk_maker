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

# Tool identifiers — also used by ``chrome.py`` (via the workspace
# delegator) and ``drag.py`` (via the literal ``"hand"`` string).
TOOL_SELECT = "select"
TOOL_HAND = "hand"
TOOL_CURSORS: dict[str, str] = {
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

    def __init__(self, workspace) -> None:
        self.workspace = workspace
        self._tool: str = TOOL_SELECT
        self._tool_buttons: dict[str, ctk.CTkButton] = {}
        self._pan_state: dict | None = None

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
                command=lambda t=tool_id: self.set_tool(t),
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
        top.bind("<Control-equal>", lambda e: self._zoom_keyboard(1))
        top.bind("<Control-plus>", lambda e: self._zoom_keyboard(1))
        top.bind("<Control-minus>", lambda e: self._zoom_keyboard(-1))
        top.bind("<Control-Key-0>", lambda e: self._zoom_reset())
        top.bind(
            "<KeyPress-v>",
            lambda e: self._tool_shortcut(TOOL_SELECT),
        )
        top.bind(
            "<KeyPress-V>",
            lambda e: self._tool_shortcut(TOOL_SELECT),
        )
        top.bind(
            "<KeyPress-h>",
            lambda e: self._tool_shortcut(TOOL_HAND),
        )
        top.bind(
            "<KeyPress-H>",
            lambda e: self._tool_shortcut(TOOL_HAND),
        )

    def _tool_shortcut(self, tool: str) -> str | None:
        if self.workspace._input_focused():
            return None
        self.set_tool(tool)
        return "break"

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
