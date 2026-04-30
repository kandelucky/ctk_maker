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
from tkinter import filedialog, messagebox

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
        node = self.project.get_widget(self.current_id)
        # Dynamic enums — options computed from the current widget's
        # data, not a static list. ``segment_initial`` reads the
        # sibling ``values`` prop so the dropdown reflects whatever
        # segments the user just typed in the table editor.
        if ptype == "segment_initial":
            options = self._segment_initial_options(node)
            if not options:
                # Empty values → show a single disabled hint instead
                # of an empty menu the user can't interact with.
                menu = tk.Menu(self, tearoff=0, **MENU_STYLE)
                menu.add_command(
                    label="(no segments)",
                    foreground="#555555",
                )
                try:
                    menu.tk_popup(x_root, y_root)
                finally:
                    menu.grab_release()
                return
        else:
            options = enum_options_for(ptype)
        if not options:
            return
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
        self._attach_inline_context_menu(entry, prop=None)

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
        iid = self.tree.identify_row(event.y)
        if iid and iid.startswith("localvar:") and iid != "localvar:empty":
            doc_id = (
                self.project.active_document_id if self.project else None
            )
            self.project.event_bus.publish(
                "request_open_variables_window", "local", doc_id,
            )
            return "break"
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return None
        col = self.tree.identify_column(event.x)
        if col != "#1":
            return None
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
        self._attach_inline_context_menu(entry, prop=prop)

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
        initial = node.properties.get(pname) or "#6366f1"
        dialog = ColorPickerDialog(
            self.winfo_toplevel(), initial_color=initial,
        )
        dialog.wait_window()
        hex_value = getattr(dialog, "result", None)
        if hex_value:
            self._commit_prop(pname, hex_value)

    def _pick_image(self, pname: str) -> None:
        # Project-scoped picker — only shows images already in
        # ``<project>/assets/images/``, with an "Import..." button
        # that copies a file off-disk into the project's assets
        # folder before selecting it. Keeps every Image reference
        # inside the project so the .ctkproj stays portable.
        from app.ui.image_picker_dialog import ImagePickerDialog
        project_file = getattr(self.project, "path", None)
        if not project_file:
            return  # Untitled state shouldn't be reachable.
        dialog = ImagePickerDialog(
            self.winfo_toplevel(), project_file,
            event_bus=getattr(self.project, "event_bus", None),
        )
        dialog.wait_window()
        if dialog.result:
            self._commit_prop(pname, dialog.result)

    def _pick_font(self, pname: str) -> None:
        """Open the font picker for the focused widget. The picker
        carries a scope selector — "this widget" commits via the
        normal property path; "all [Type]" / "all in project" writes
        into ``project.font_defaults`` and triggers a workspace
        refresh so every text widget that doesn't have its own
        override updates immediately.
        """
        if self.current_id is None:
            return
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        descriptor = self._current_descriptor()
        type_name = (
            getattr(descriptor, "type_name", None) if descriptor else None
        )
        type_display = (
            getattr(descriptor, "display_name", None) if descriptor else None
        )
        from app.ui.font_picker_dialog import (
            FontPickerDialog, SCOPE_ALL, SCOPE_TYPE, SCOPE_WIDGET,
        )
        # Snapshot the system-fonts list so we can detect a "+ Add
        # system font" mutation inside the picker and mark the
        # project dirty accordingly — regardless of whether the user
        # ends up changing the widget's font_family on top of that.
        system_fonts_before = list(
            getattr(self.project, "system_fonts", []) or [],
        )
        dialog = FontPickerDialog(
            self.winfo_toplevel(), self.project,
            current=node.properties.get(pname),
            type_name=type_name,
            type_display=type_display,
        )
        dialog.wait_window()
        system_fonts_after = list(
            getattr(self.project, "system_fonts", []) or [],
        )
        if system_fonts_after != system_fonts_before:
            # The picker added a system font to the palette. That's a
            # project-state change in its own right — even if the user
            # cancels the font apply, the palette update should be
            # remembered on next save.
            self.project.event_bus.publish("dirty_changed", True)
        result = getattr(dialog, "result", None)
        if result is None:
            return
        family, scope = result
        if scope == SCOPE_WIDGET:
            self._commit_prop(pname, family)
            return
        # Scope = type / all-in-project — writes the cascade default
        # rather than a per-widget override. Using ``family is None``
        # as the "Use default" intent: drops the entry instead of
        # storing an empty string.
        from app.core.fonts import (
            ALL_DEFAULT_KEY, set_active_project_defaults,
        )
        # Pure cascade behaviour was confusing: the user picked "All
        # Buttons" expecting every button to change, but per-widget
        # overrides survived because cascade lookup hit them first.
        # Reinterpret scope literally — "all" means all. When the
        # user picks scope=type/all with a real family:
        #   • clear per-widget font_family on every affected widget
        #   • for scope=ALL also clear sibling per-type defaults
        #   • set the cascade entry for the chosen scope key
        # Show an informational confirmation only when overrides
        # actually exist — silent apply is faster when there's
        # nothing to lose.
        widget_overrides = self._widgets_with_font_override(
            scope, type_name,
        )
        type_overrides: list[str] = []
        if scope == SCOPE_ALL:
            type_overrides = [
                k for k in self.project.font_defaults
                if k != ALL_DEFAULT_KEY
            ]
        if family and (widget_overrides or type_overrides):
            scope_label = (
                f"every {type_display or type_name}"
                if scope == SCOPE_TYPE else "every text widget"
            )
            lines = [
                f"Apply {family!r} to {scope_label} in this project?",
                "",
            ]
            if widget_overrides:
                lines.append(
                    f"{len(widget_overrides)} widget(s) currently "
                    "use a custom font. Their override will be cleared.",
                )
            if type_overrides:
                lines.append(
                    f"{len(type_overrides)} per-type default(s) "
                    f"will be removed ({', '.join(type_overrides)}).",
                )
            from tkinter import messagebox
            if not messagebox.askokcancel(
                "Apply font",
                "\n".join(lines),
                parent=self.winfo_toplevel(),
                icon="info",
            ):
                return
        defaults = dict(self.project.font_defaults)
        key = type_name if scope == SCOPE_TYPE else ALL_DEFAULT_KEY
        if key is None:
            return
        if family and scope == SCOPE_ALL:
            # Wipe sibling per-type defaults so the new "_all" entry
            # actually applies project-wide instead of being shadowed
            # by every existing per-type default.
            defaults = {}
        if family:
            defaults[key] = family
        else:
            defaults.pop(key, None)
        self.project.font_defaults = defaults
        set_active_project_defaults(defaults)
        if family:
            # Scope literalism — drop per-widget font_family on
            # every affected widget so the cascade default actually
            # wins. ``Use default`` (family is None) intentionally
            # leaves overrides alone; clearing the cascade slot is
            # never destructive on its own.
            for w in widget_overrides:
                self.project.update_property(w.id, "font_family", None)
        # Mark dirty so the new defaults make it into the next save.
        self.project.event_bus.publish("dirty_changed", True)
        self.project.event_bus.publish("font_defaults_changed", defaults)

    def _widgets_with_font_override(
        self, scope: str, type_name: str | None,
    ) -> list:
        """Return every widget the cascade scope would affect that
        carries its own ``font_family`` value. Used by ``_pick_font``
        to ask the user whether per-widget overrides should fall back
        to the new default too.
        """
        from app.ui.font_picker_dialog import SCOPE_TYPE
        out = []
        for node in self.project.iter_all_widgets():
            if not node.properties.get("font_family"):
                continue
            if scope == SCOPE_TYPE and node.widget_type != type_name:
                continue
            out.append(node)
        return out

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

    def _segment_initial_options(self, node) -> list[str]:
        """Read the current node's segment/tab names and split into
        dropdown options. Checks ``values`` (CTkSegmentedButton) and
        ``tab_names`` (CTkTabview) — whichever is present.
        """
        if node is None:
            return []
        raw = (
            node.properties.get("values")
            or node.properties.get("tab_names")
            or ""
        )
        return [
            line for line in str(raw).splitlines() if line.strip()
        ]

    def _open_segment_values_editor(self, pname: str) -> None:
        """Table-based +/- editor for ``CTkSegmentedButton.values``.
        Stored on the node as the same newline-separated string the
        old multiline editor produced — exporter / runtime are
        unchanged. Empty rows are dropped on save.
        """
        from tools.segment_values_dialog import SegmentValuesDialog
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        current = node.properties.get(pname) or ""
        values = [
            line for line in str(current).splitlines() if line.strip()
        ]
        is_tabview = pname == "tab_names"
        if is_tabview:
            title = "Edit Tabs"
        elif node.widget_type == "CTkSegmentedButton":
            title = "Edit Segments"
        else:
            title = "Edit Values"
        dialog = SegmentValuesDialog(
            self.winfo_toplevel(), title, values,
        )
        dialog.wait_window()
        if dialog.result is None:
            return
        new_values = dialog.result
        if is_tabview and not self._confirm_tabview_change(
            node, values, new_values,
        ):
            return
        self._commit_prop(pname, "\n".join(new_values))

    def _confirm_tabview_change(
        self, node, old_names: list[str], new_names: list[str],
    ) -> bool:
        """Ask the user to confirm a tab-list edit that would affect
        nested children. Detects a single-tab rename (one removed, one
        added) and previews the auto-migration; any other delta that
        orphans children warns they'll be moved to the first tab.
        Returns True to proceed with the commit, False to cancel.
        """
        removed = [n for n in old_names if n not in new_names]
        if not removed:
            return True
        affected_slots = {
            getattr(c, "parent_slot", None) for c in node.children
        }
        affected_count = sum(
            1 for c in node.children
            if getattr(c, "parent_slot", None) in removed
        )
        if affected_count == 0:
            return True
        _ = affected_slots  # kept for future per-tab breakdown
        added = [n for n in new_names if n not in old_names]
        if len(removed) == 1 and len(added) == 1:
            msg = (
                f"Renaming tab '{removed[0]}' to '{added[0]}'.\n"
                f"{affected_count} widget(s) will move to the "
                f"renamed tab."
            )
        else:
            first = new_names[0] if new_names else "Tab 1"
            msg = (
                f"{affected_count} widget(s) are in tabs being "
                f"deleted or renamed.\n"
                f"They will be moved to '{first}'.\n\n"
                f"Tip: rename tabs one at a time to keep widgets "
                f"attached to the renamed tab."
            )
        from app.ui.dialogs import ConfirmDialog
        dialog = ConfirmDialog(
            self.winfo_toplevel(), "Tab change", msg,
            ok_text="Continue", cancel_text="Back",
        )
        dialog.wait_window()
        return dialog.result

    # ------------------------------------------------------------------
    # Commit path
    # ------------------------------------------------------------------
    def _commit_prop(self, pname: str, value) -> None:
        if self.current_id is None:
            return
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        # Grid shrink guard — block grid_rows/grid_cols going below the
        # max row/column index actually occupied by a child, otherwise
        # children silently disappear from the canvas (still in the
        # model, just out-of-bounds for the new grid).
        if pname in ("grid_rows", "grid_cols"):
            ok, msg = self._validate_grid_shrink(node, pname, value)
            if not ok:
                messagebox.showerror(
                    "Cannot shrink grid", msg,
                    parent=self.winfo_toplevel(),
                )
                self._refresh_row_after_reject(pname)
                return
        # Disabled-icon-colour advisory: the exported code has to run
        # a helper to swap the tinted image when the widget flips to
        # disabled state (CTk doesn't do it natively). Warn once per
        # pick, dismissable via ``~/.ctk_visual_builder/settings.json``
        # key ``advisory_image_color_disabled_dismissed``.
        if pname == "image_color_disabled" and value:
            self._maybe_show_disabled_icon_advisory()
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
    # Advisory dialog — disabled-icon tint requires runtime helper
    # ------------------------------------------------------------------
    _ADVISORY_KEY = "advisory_image_color_disabled_dismissed"

    def _maybe_show_disabled_icon_advisory(self) -> None:
        """Pop a one-shot warning when the user picks an
        ``image_color_disabled`` value. CTk has no native icon-tint-on-
        state-change mechanism, so the exported file can't just
        forward the builder's disabled colour — it needs a runtime
        helper to swap images. The exporter emits that helper + a
        comment per affected button; this dialog surfaces the same
        advisory at design time so the designer isn't surprised by
        the runtime behaviour.
        """
        from app.core.settings import load_settings, save_setting
        if load_settings().get(self._ADVISORY_KEY):
            return
        top = self.winfo_toplevel()
        dont_show = tk.BooleanVar(value=False)
        dialog = tk.Toplevel(top)
        dialog.title("Disabled icon colour")
        dialog.transient(top)
        dialog.grab_set()
        dialog.configure(bg="#2b2b2b")
        dialog.resizable(False, False)
        msg = (
            "Heads up — disabled-state icon colour isn't automatic.\n\n"
            "CTk swaps the button's text colour on state change, but\n"
            "images don't follow. The exporter adds a helper\n"
            "(_apply_icon_state) + a comment on every affected button\n"
            "so you can wire the swap from your own state-change code.\n"
        )
        lbl = tk.Label(
            dialog, text=msg, bg="#2b2b2b", fg="#cccccc",
            font=("Segoe UI", 10), justify="left", anchor="w",
            padx=20, pady=16,
        )
        lbl.pack(fill="x")
        chk = tk.Checkbutton(
            dialog, text="Don't show this again",
            variable=dont_show,
            bg="#2b2b2b", fg="#cccccc",
            activebackground="#2b2b2b", activeforeground="#ffffff",
            selectcolor="#2b2b2b", bd=0, padx=20,
            font=("Segoe UI", 10),
        )
        chk.pack(anchor="w", pady=(0, 12))

        def _on_ok():
            if dont_show.get():
                save_setting(self._ADVISORY_KEY, True)
            dialog.destroy()

        btn = tk.Button(
            dialog, text="OK", width=10,
            bg="#3b8ed0", fg="#ffffff",
            activebackground="#4f46e5", activeforeground="#ffffff",
            bd=0, font=("Segoe UI", 10, "bold"), relief="flat",
            command=_on_ok,
        )
        btn.pack(pady=(0, 16))
        dialog.bind("<Return>", lambda _e: _on_ok())
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        dialog.update_idletasks()
        # Centre on parent.
        try:
            px = top.winfo_rootx()
            py = top.winfo_rooty()
            pw = top.winfo_width()
            ph = top.winfo_height()
            dw = dialog.winfo_width()
            dh = dialog.winfo_height()
            dialog.geometry(
                f"+{px + (pw - dw) // 2}+{py + (ph - dh) // 2}",
            )
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Grid shrink validation
    # ------------------------------------------------------------------
    def _validate_grid_shrink(
        self, node, pname: str, value,
    ) -> tuple[bool, str]:
        """Block grid_rows/grid_cols changes that would orphan children.

        Returns ``(True, "")`` when the change is fine; otherwise
        ``(False, message)`` with a user-facing explanation listing the
        occupied row/column index.
        """
        try:
            new_val = int(value)
        except (TypeError, ValueError):
            return True, ""
        try:
            current = int(node.properties.get(pname, 1) or 1)
        except (TypeError, ValueError):
            current = 1
        if new_val >= current:
            return True, ""
        axis_key = "grid_row" if pname == "grid_rows" else "grid_column"
        max_used = -1
        for child in node.children:
            try:
                idx = int(child.properties.get(axis_key, 0) or 0)
            except (TypeError, ValueError):
                continue
            if idx > max_used:
                max_used = idx
        if new_val <= max_used:
            unit_word = "row" if pname == "grid_rows" else "column"
            return False, (
                f"Cannot shrink to {new_val} "
                f"{unit_word}{'s' if new_val != 1 else ''} — "
                f"a child widget occupies {unit_word} {max_used}. "
                f"Move or delete that widget first."
            )
        return True, ""

    def _refresh_row_after_reject(self, pname: str) -> None:
        """Repaint the schema row for ``pname`` so the spinner / inline
        editor snaps back to the stored value when a commit is blocked.
        """
        if self.current_id is None:
            return
        descriptor = self._current_descriptor()
        if descriptor is None:
            return
        node = self.project.get_widget(self.current_id)
        if node is None:
            return
        prop = self._find_prop(descriptor, pname)
        iid = self._prop_iids.get(pname)
        if prop is not None and iid is not None:
            self._refresh_cell(iid, prop, node.properties.get(pname))

    # ------------------------------------------------------------------
    # Inline editor right-click menu
    # ------------------------------------------------------------------
    def _attach_inline_context_menu(self, entry, prop: dict | None) -> None:
        """Right-click on an inline tk.Entry overlay → Cut / Copy /
        Paste / Select All. For number rows, also offer two
        quick-fill commands that drop the schema's min / max value
        straight into the field. ``prop=None`` skips the min/max
        section (used for the multi-line text inline editor).
        """
        def _popup(event):
            menu = tk.Menu(entry, tearoff=0, **MENU_STYLE)
            has_selection = bool(entry.selection_present()) \
                if hasattr(entry, "selection_present") else False
            try:
                # ``selection_present`` may raise on stale widget — guard.
                has_selection = bool(entry.selection_present())
            except tk.TclError:
                has_selection = False
            _fg = MENU_STYLE.get("fg", "#cccccc")
            _dim = "#555555"
            menu.add_command(
                label="Cut",
                command=(
                    lambda: entry.event_generate("<<Cut>>")
                    if has_selection else None
                ),
                foreground=_fg if has_selection else _dim,
            )
            menu.add_command(
                label="Copy",
                command=(
                    lambda: entry.event_generate("<<Copy>>")
                    if has_selection else None
                ),
                foreground=_fg if has_selection else _dim,
            )
            menu.add_command(
                label="Paste",
                command=lambda: entry.event_generate("<<Paste>>"),
            )
            menu.add_separator()
            menu.add_command(
                label="Select All",
                command=lambda: (
                    entry.select_range(0, tk.END),
                    entry.icursor(tk.END),
                ),
            )
            if prop is not None and prop.get("type") == "number":
                self._append_min_max_menu_items(menu, entry, prop)
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        entry.bind("<Button-3>", _popup, add="+")

    def _append_min_max_menu_items(self, menu, entry, prop) -> None:
        """Add ``Min: <value>`` / ``Max: <value>`` rows that, when
        clicked, replace the entry contents with the schema's
        clamp value. Lambdas in the schema are evaluated against the
        current widget's properties so context-sensitive bounds
        (e.g. corner_radius capped to half the widget height)
        resolve correctly.
        """
        node = (
            self.project.get_widget(self.current_id)
            if self.current_id else None
        )
        props = node.properties if node is not None else {}

        def _resolve(key):
            raw = prop.get(key)
            if callable(raw):
                try:
                    return raw(props)
                except Exception:
                    return None
            return raw

        lo = _resolve("min")
        hi = _resolve("max")
        if lo is None and hi is None:
            return

        def _replace(value):
            entry.delete(0, tk.END)
            entry.insert(0, str(value))
            entry.select_range(0, tk.END)
            entry.icursor(tk.END)
            entry.focus_set()

        menu.add_separator()
        if lo is not None:
            menu.add_command(
                label=f"Min: {lo}",
                command=lambda v=lo: _replace(v),
            )
        if hi is not None:
            menu.add_command(
                label=f"Max: {hi}",
                command=lambda v=hi: _replace(v),
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
            cap = max(0, min(w, h)) if w > 0 and h > 0 else 0
            return max(0, min(v, cap) if cap > 0 else v)
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
