"""Horizontal drag-scrub for numeric property rows.

Photoshop / Figma-style scrubber: press on a number row's name column
and drag horizontally to change the value by ±1 per pixel. Alt-hold
switches to 0.2× fine-scrub. The schema's `min` / `max` (ints or
lambdas over the current property dict) are respected.

Attaches to an existing `PropertiesPanelV2` by binding mouse events on
its Treeview. All state lives inside this controller — the panel only
wires it up once in `_build_tree`.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .panel import PropertiesPanelV2


_ALT_MASK = 0x20000  # Tk event.state bit for the Alt modifier


class DragScrubController:
    def __init__(self, panel: "PropertiesPanelV2"):
        self.panel = panel
        self._state: dict | None = None
        self._cursor_mode: str = ""

        tree = panel.tree
        tree.bind("<ButtonPress-1>", self._on_press, add="+")
        tree.bind("<B1-Motion>", self._on_motion, add="+")
        tree.bind("<ButtonRelease-1>", self._on_release, add="+")
        tree.bind("<Motion>", self._on_hover, add="+")

    # ==================================================================
    # Hit testing
    # ==================================================================
    def _target_at(self, event) -> tuple[str, str, dict] | None:
        """Return (iid, pname, prop) if the event lands on a draggable
        number row's name column; otherwise None.
        """
        tree = self.panel.tree
        try:
            col = tree.identify_column(event.x)
            region = tree.identify_region(event.x, event.y)
        except tk.TclError:
            return None
        if region not in ("tree", "cell") or col != "#0":
            return None
        iid = tree.identify_row(event.y)
        if not iid or not iid.startswith("p:"):
            return None
        pname = iid[2:]
        if self.panel._disabled_states.get(pname):
            return None
        prop = self.panel._find_prop_by_name(pname)
        if prop is None or prop.get("type") != "number":
            return None
        return iid, pname, prop

    # ==================================================================
    # Event handlers
    # ==================================================================
    def _on_press(self, event) -> None:
        target = self._target_at(event)
        if target is None:
            self._state = None
            return
        _iid, pname, prop = target
        node = self.panel.project.get_widget(self.panel.current_id)
        if node is None:
            return
        try:
            current = int(node.properties.get(pname, 0) or 0)
        except (ValueError, TypeError):
            current = 0
        self._state = {
            "pname": pname,
            "prop": prop,
            "last_x": event.x_root,
            "current": current,
            "accumulator": 0.0,
        }

    def _on_motion(self, event) -> None:
        if self._state is None:
            return
        dx = event.x_root - self._state["last_x"]
        self._state["last_x"] = event.x_root
        fine = bool(event.state & _ALT_MASK)
        sensitivity = 0.2 if fine else 1.0
        self._state["accumulator"] += dx * sensitivity
        delta = int(self._state["accumulator"])
        if delta == 0:
            return
        self._state["accumulator"] -= delta
        new_value = self._state["current"] + delta
        new_value = self._clamp(new_value, self._state["prop"])
        if new_value == self._state["current"]:
            return
        self._state["current"] = new_value
        self.panel._commit_prop(self._state["pname"], new_value)

    def _on_release(self, _event) -> None:
        self._state = None
        self._set_cursor("")

    def _on_hover(self, event) -> None:
        if self._state is not None:
            return
        target = self._target_at(event)
        new_mode = "drag" if target is not None else ""
        if new_mode == self._cursor_mode:
            return
        self._cursor_mode = new_mode
        self._set_cursor(
            "sb_h_double_arrow" if new_mode == "drag" else "",
        )

    # ==================================================================
    # Helpers
    # ==================================================================
    def _set_cursor(self, cursor: str) -> None:
        try:
            self.panel.tree.configure(cursor=cursor)
        except tk.TclError:
            pass

    def _clamp(self, value: int, prop: dict) -> int:
        node = self.panel.project.get_widget(self.panel.current_id)
        props = node.properties if node is not None else {}
        min_val = prop.get("min")
        max_val = prop.get("max")
        if callable(min_val):
            try:
                min_val = min_val(props)
            except Exception:
                min_val = None
        if callable(max_val):
            try:
                max_val = max_val(props)
            except Exception:
                max_val = None
        if min_val is not None:
            try:
                value = max(int(min_val), value)
            except (ValueError, TypeError):
                pass
        if max_val is not None:
            try:
                value = min(int(max_val), value)
            except (ValueError, TypeError):
                pass
        return value
