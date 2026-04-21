"""Commit path + editor lifecycle mixin for PropertiesPanelV2.

Split out of the monolithic ``panel.py`` (v0.0.15.11 refactor round).
Covers every user-interaction path that turns a value into a
``ChangePropertyCommand``:

- Enum popup (layout_type / anchor / compound dropdown)
- Inline `tk.Entry` overlay for single-line text
- Inline multiline edit (via ``_edit_text_inline``)
- Click routing (dispatch to editor's on_single_click / on_double_click)
- Color / image / text pickers
- ``_commit_prop`` — the commit bottleneck with container-bound clamp

The mixin relies on attributes set up by ``PropertiesPanelV2.__init__``
(``self.tree``, ``self.project``, ``self.current_id``, ``self.overlays``,
``self._active_editor`` family, ``self._disabled_states``,
``self._prop_iids``, ``self._suspend_history``) plus the schema helpers
(``_find_prop``, ``_current_descriptor``, etc.).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog

from ctk_color_picker import ColorPickerDialog

from app.core.commands import (
    ChangePropertyCommand,
    MultiChangePropertyCommand,
)
from app.ui.icons import load_tk_icon
from app.widgets.layout_schema import (
    LAYOUT_DISPLAY_NAMES,
    LAYOUT_ICON_NAMES,
)
from tools.text_editor_dialog import TextEditorDialog

from .constants import ANCHOR_LABEL_TO_CODE, MENU_STYLE, VALUE_BG
from .editors import get_editor
from .format_utils import coerce_value, enum_options_for
from .overlays import SLOT_TEXT_VALUE


class CommitMixin:
    """Editor lifecycle + commit bottleneck. See module docstring."""

    # ------------------------------------------------------------------
    # Enum popup
    # ------------------------------------------------------------------
    def _popup_enum_menu_at(
        self, pname: str, ptype: str, x_root: int, y_root: int,
    ) -> None:
        options = enum_options_for(ptype)
        if not options:
            return
        node = self.project.get_widget(self.current_id)
        current = node.properties.get(pname) if node else None
        menu = tk.Menu(self, tearoff=0, **MENU_STYLE)
        # tk.Menu drops PhotoImage refs as soon as the caller scope
        # returns — stash them on the menu itself so the icons
        # actually render.
        icon_refs: list = []
        for opt in options:
            stored = (
                ANCHOR_LABEL_TO_CODE.get(opt, opt)
                if ptype == "anchor" else opt
            )
            prefix = "• " if stored == current else "   "
            if ptype == "anchor":
                commit_val = ANCHOR_LABEL_TO_CODE.get(opt, "center")
            else:
                commit_val = opt
            label_text = opt
            icon_image = None
            if ptype == "layout_type":
                label_text = LAYOUT_DISPLAY_NAMES.get(opt, opt)
                icon_name = LAYOUT_ICON_NAMES.get(opt)
                if icon_name:
                    icon_image = load_tk_icon(icon_name, size=14)
                    if icon_image is not None:
                        icon_refs.append(icon_image)
            kwargs = {
                "label": f"{prefix}{label_text}",
                "command": lambda v=commit_val, p=pname:
                    self._commit_prop(p, v),
            }
            if icon_image is not None:
                kwargs["image"] = icon_image
                kwargs["compound"] = "left"
            menu.add_command(**kwargs)
        menu._layout_icon_refs = icon_refs  # keep refs alive
        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()

    # ------------------------------------------------------------------
    # Text inline edit (fast single-line)
    # ------------------------------------------------------------------
    def _edit_text_inline(self, pname: str) -> None:
        iid = self._prop_iids.get(pname)
        if iid is None or self.overlays is None:
            return
        overlay = self.overlays.get(iid, SLOT_TEXT_VALUE)
        if overlay is None:
            return
        self._commit_active_editor()
        self.tree.update_idletasks()
        x = overlay.winfo_x()
        y = overlay.winfo_y()
        w = overlay.winfo_width()
        h = overlay.winfo_height()

        node = self.project.get_widget(self.current_id)
        current = node.properties.get(pname, "") if node else ""
        entry = tk.Entry(
            self.tree, font=("Segoe UI", 11),
            bg=VALUE_BG, fg="#cccccc", insertbackground="#cccccc",
            bd=1, relief="flat",
            highlightthickness=1, highlightbackground="#3a3a3a",
            highlightcolor="#3b8ed0",
        )
        entry.insert(0, str(current))
        entry.place(x=x, y=y, width=w, height=h)
        entry.select_range(0, tk.END)
        entry.focus_set()
        self._active_editor = entry
        self._active_prop = pname
        self._active_prop_type = "multiline"
        entry.bind("<Return>", lambda _e: self._commit_active_editor())
        entry.bind("<FocusOut>", lambda _e: self._commit_active_editor())
        entry.bind("<Escape>", lambda _e: self._cancel_active_editor())

    # ------------------------------------------------------------------
    # Click routing
    # ------------------------------------------------------------------
    def _on_single_click(self, event) -> None:
        region = self.tree.identify_region(event.x, event.y)
        if region == "nothing":
            self.tree.selection_remove(*self.tree.selection())
            try:
                self.tree.focus("")
            except tk.TclError:
                pass
            self.winfo_toplevel().focus_set()
            return
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        if col != "#1":
            return
        iid = self.tree.identify_row(event.y)
        if not iid or not iid.startswith("p:"):
            return
        pname = iid[2:]
        if self._disabled_states.get(pname):
            return
        prop = self._find_prop_by_name(pname)
        if prop is None:
            return
        get_editor(prop["type"]).on_single_click(self, pname, prop)

    def _on_double_click(self, event) -> str | None:
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return None
        col = self.tree.identify_column(event.x)
        if col != "#1":
            return None
        iid = self.tree.identify_row(event.y)
        if not iid or not iid.startswith("p:"):
            return None
        pname = iid[2:]
        if self._disabled_states.get(pname):
            return "break"
        prop = self._find_prop_by_name(pname)
        if prop is None:
            return None
        if get_editor(prop["type"]).on_double_click(self, pname, prop, event):
            return "break"
        return None

    def _find_prop_by_name(self, pname: str):
        descriptor = self._current_descriptor()
        if descriptor is None:
            return None
        return self._find_prop(descriptor, pname)

    # ------------------------------------------------------------------
    # Editors — inline Entry
    # ------------------------------------------------------------------
    def _open_entry_overlay(
        self, iid: str, pname: str, prop: dict, bbox,
    ) -> None:
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        current = node.properties.get(pname, "")
        entry = tk.Entry(
            self.tree,
            font=("Segoe UI", 11),
            bg=VALUE_BG, fg="#cccccc", insertbackground="#cccccc",
            bd=1, relief="flat",
            highlightthickness=1, highlightbackground="#3a3a3a",
            highlightcolor="#3b8ed0",
        )
        entry.insert(0, str(current) if current is not None else "")
        entry.place(
            x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3],
        )
        entry.select_range(0, tk.END)
        entry.focus_set()
        self._active_editor = entry
        self._active_prop = pname
        self._active_prop_type = prop["type"]

        entry.bind("<Return>", lambda _e: self._commit_active_editor())
        entry.bind("<FocusOut>", lambda _e: self._commit_active_editor())
        entry.bind("<Escape>", lambda _e: self._cancel_active_editor())

    def _commit_active_editor(self) -> None:
        if self._active_editor is None or self._active_prop is None:
            return
        pname = self._active_prop
        ptype = getattr(self, "_active_prop_type", None)
        try:
            raw = self._active_editor.get()
        except tk.TclError:
            raw = ""
        new_value = coerce_value(ptype, raw)
        try:
            self._active_editor.destroy()
        except tk.TclError:
            pass
        self._active_editor = None
        self._active_prop = None
        self._active_prop_type = None
        if new_value is not None:
            self._commit_prop(pname, new_value)

    def _cancel_active_editor(self) -> None:
        if self._active_editor is None:
            return
        try:
            self._active_editor.destroy()
        except tk.TclError:
            pass
        self._active_editor = None
        self._active_prop = None
        self._active_prop_type = None

    # ------------------------------------------------------------------
    # Pickers
    # ------------------------------------------------------------------
    def _pick_color(self, pname: str) -> None:
        if self.current_id is None:
            return
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        initial = node.properties.get(pname) or "#1f6aa5"
        dialog = ColorPickerDialog(
            self.winfo_toplevel(), initial_color=initial,
        )
        dialog.wait_window()
        hex_value = getattr(dialog, "result", None)
        if hex_value:
            self._commit_prop(pname, hex_value)

    def _pick_image(self, pname: str) -> None:
        path = filedialog.askopenfilename(
            title="Select image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._commit_prop(pname, path)

    def _open_text_editor(self, pname: str, prop: dict) -> None:
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        current = node.properties.get(pname) or ""
        label = prop.get("row_label") or prop.get("label") or pname
        dialog = TextEditorDialog(
            self.winfo_toplevel(), f"Edit: {label}", str(current),
        )
        dialog.wait_window()
        if dialog.result is not None:
            self._commit_prop(pname, dialog.result)

    # ------------------------------------------------------------------
    # Commit path
    # ------------------------------------------------------------------
    def _commit_prop(self, pname: str, value) -> None:
        if self.current_id is None:
            return
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        # Clamp geometry writes to the container's bounds — typed values
        # (Inspector entry, spinner, drag-scrub) used to accept anything,
        # so it was trivial to shove a widget outside the window via
        # Properties. Drag already snaps back at release; this closes
        # the same gap for keyboard-driven edits.
        value = self._clamp_to_container_bounds(node, pname, value)
        # Full-dict snapshot so `compute_derived` side-effect changes
        # (e.g. Image width→height recompute on preserve_aspect) end
        # up in the same undo entry as the primary commit. Without
        # this, the derived prop silently drifts during undo/redo.
        before_snapshot = dict(node.properties)
        self.project.update_property(self.current_id, pname, value)
        if getattr(self, "_suspend_history", False):
            return
        after_snapshot = dict(node.properties)
        changed = {
            k: (before_snapshot.get(k), after_snapshot.get(k))
            for k in set(before_snapshot) | set(after_snapshot)
            if before_snapshot.get(k) != after_snapshot.get(k)
        }
        if not changed:
            return
        if len(changed) == 1:
            (k, (b, a)), = changed.items()
            self.project.history.push(
                ChangePropertyCommand(self.current_id, k, b, a),
            )
            return
        self.project.history.push(
            MultiChangePropertyCommand(self.current_id, changed),
        )

    # ------------------------------------------------------------------
    # Geometry bounds
    # ------------------------------------------------------------------
    def _clamp_to_container_bounds(self, node, pname: str, value):
        """Clamp x / y / width / height so the widget stays inside its
        container. Top-level widgets sit in the owning document's
        rectangle (the Main Window / Dialog); nested widgets in a
        ``place`` parent sit in that Frame's rectangle. Widgets under
        a managed layout (vbox / hbox / grid) skip the clamp — the
        layout manager owns their geometry and the x/y fields are
        either ignored (vbox/hbox) or paired with grid_row/column.
        """
        if pname not in ("x", "y", "width", "height", "corner_radius"):
            return value
        if pname == "corner_radius":
            try:
                v = int(value)
            except (TypeError, ValueError):
                return value
            try:
                w = int(node.properties.get("width", 0) or 0)
                h = int(node.properties.get("height", 0) or 0)
            except (TypeError, ValueError):
                w = h = 0
            half = max(0, min(w, h) // 2) if w > 0 and h > 0 else 0
            return max(0, min(v, half) if half > 0 else v)
        try:
            value = int(value)
        except (TypeError, ValueError):
            return value
        from app.widgets.layout_schema import normalise_layout_type
        container_w, container_h = self._resolve_container_size(node)
        # If the node is under a managed-layout parent, skip — layout
        # manager controls placement/size.
        parent = node.parent
        if parent is not None:
            parent_layout = normalise_layout_type(
                parent.properties.get("layout_type", "place"),
            )
            if parent_layout != "place":
                return max(0, value) if pname in ("x", "y") else value
        if container_w <= 0 or container_h <= 0:
            return max(0, value) if pname in ("x", "y") else value
        try:
            node_w = int(node.properties.get("width", 0) or 0)
            node_h = int(node.properties.get("height", 0) or 0)
            node_x = int(node.properties.get("x", 0) or 0)
            node_y = int(node.properties.get("y", 0) or 0)
        except (TypeError, ValueError):
            node_w = node_h = node_x = node_y = 0
        if pname == "x":
            return max(0, min(value, max(0, container_w - node_w)))
        if pname == "y":
            return max(0, min(value, max(0, container_h - node_h)))
        if pname == "width":
            return max(1, min(value, max(1, container_w - node_x)))
        if pname == "height":
            return max(1, min(value, max(1, container_h - node_y)))
        return value

    def _resolve_container_size(self, node) -> tuple[int, int]:
        """Container dimensions for bound clamping. Top-level widgets
        → owning document (Main Window / Dialog); nested widgets →
        parent node's ``width``/``height`` properties.
        """
        parent = node.parent
        if parent is None:
            doc = self.project.find_document_for_widget(node.id)
            if doc is None:
                return 0, 0
            try:
                return int(getattr(doc, "width", 0) or 0), int(
                    getattr(doc, "height", 0) or 0,
                )
            except (TypeError, ValueError):
                return 0, 0
        try:
            return (
                int(parent.properties.get("width", 0) or 0),
                int(parent.properties.get("height", 0) or 0),
            )
        except (TypeError, ValueError):
            return 0, 0
