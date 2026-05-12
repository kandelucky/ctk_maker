"""Right-click context-menu sidecar for ``Workspace``.

Two top-level entry points + everything they delegate to:

* ``on_canvas_right_click`` — right-click on empty canvas. Shows
  Add Widget cascade (built by ``DropDispatcher._build_add_widget_menu``),
  Paste, Select All, Deselect All, Save Window as Component, Minimize
  Window, Window Properties.
* ``on_widget_right_click`` — right-click on a widget. Drills through
  the drag-controller's click-target resolver so the menu acts on the
  same layer left-click would have selected. Different menus depending
  on whether the click is on a multi-selection vs single widget.

Plus the action handlers wired from those menus: copy / paste /
duplicate / z-order / rename / Group / Ungroup / Save as component /
Insert window component / Add handler / Jump to handler method.

Cross-sidecar references:
* ``DropDispatcher._build_add_widget_menu`` for the Add Widget cascade
* ``Workspace._on_delete`` (delegated to ``KeyboardActions``) for
  Delete entries on the menus
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from app.core.commands import (
    BindHandlerCommand,
    BulkAddCommand,
    RenameCommand,
    build_bulk_add_entries,
    paste_target_parent_id,
    push_zorder_history,
)
from app.core.platform_compat import MOD_LABEL_PLUS
from app.ui.dialogs import RenameDialog
from app.widgets.registry import get_descriptor


class ContextMenu:
    """Canvas + widget right-click menus + their action handlers.
    See module docstring.
    """

    def __init__(self, workspace) -> None:
        self.workspace = workspace

    # ------------------------------------------------------------------
    # Canvas right-click (empty area)
    # ------------------------------------------------------------------
    def on_canvas_right_click(self, event) -> str:
        ws = self.workspace
        # Find the doc under the cursor — paste + Select All only make
        # sense when anchored to one. Empty workspace area shows no menu.
        cx, cy = ws._screen_to_canvas(event.x_root, event.y_root)
        doc = ws._find_document_at_canvas(cx, cy)
        if doc is None:
            return "break"
        if doc.id != ws.project.active_document_id:
            ws.project.set_active_document(doc.id)
        lx, ly = ws.zoom.canvas_to_logical(cx, cy, document=doc)
        menu = tk.Menu(ws.winfo_toplevel(), tearoff=0)
        add_submenu = ws.drops._build_add_widget_menu(
            menu, None, cx, cy, event.x_root, event.y_root,
        )
        menu.add_cascade(label="Add Widget", menu=add_submenu)
        menu.add_separator()
        paste_state = "normal" if ws.project.clipboard else "disabled"
        menu.add_command(
            label="Paste",
            command=lambda d=doc, x=lx, y=ly: self._paste_at_canvas(d, x, y),
            state=paste_state,
        )
        menu.add_separator()
        top_ids = {n.id for n in doc.root_widgets}
        select_state = "normal" if top_ids else "disabled"
        menu.add_command(
            label="Select All",
            command=lambda d=doc: self._select_all_in_doc(d),
            state=select_state,
        )
        deselect_state = (
            "normal" if ws.project.selected_ids else "disabled"
        )
        menu.add_command(
            label="Deselect All",
            command=lambda: ws.project.select_widget(None),
            state=deselect_state,
        )
        menu.add_separator()
        save_label = (
            "Save Dialog as Component"
            if doc.is_toplevel else "Save Window as Component"
        )
        save_state = "normal" if doc.root_widgets else "disabled"
        menu.add_command(
            label=save_label,
            command=lambda d=doc: self._save_window_as_component(d),
            state=save_state,
        )
        menu.add_separator()
        menu.add_command(
            label="Minimize Window",
            command=lambda d=doc: ws.project.set_document_collapsed(
                d.id, True,
            ),
        )
        from app.core.project import WINDOW_ID
        props_label = (
            "Dialog Properties" if doc.is_toplevel else "Window Properties"
        )
        menu.add_command(
            label=props_label,
            command=lambda: ws.project.select_widget(WINDOW_ID),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _paste_at_canvas(self, doc, logical_x: int, logical_y: int) -> None:
        ws = self.workspace
        if not ws.project.clipboard:
            return
        from app.ui.variables_window import confirm_clipboard_paste_policy
        proceed, policy = confirm_clipboard_paste_policy(
            ws.winfo_toplevel(), ws.project, doc,
        )
        if not proceed:
            return
        new_ids = ws.project.paste_from_clipboard(
            parent_id=None,
            base_position=(logical_x, logical_y),
            var_policy=policy,
        )
        if not new_ids:
            return
        entries = build_bulk_add_entries(ws.project, new_ids)
        if entries:
            ws.project.history.push(
                BulkAddCommand(entries, label="Paste"),
            )
        _ = doc  # active doc was set above; paste went there

    def _select_all_in_doc(self, doc) -> None:
        ws = self.workspace
        ids = {node.id for node in self._iter_doc_widgets(doc)}
        if not ids:
            return
        primary = next(iter(ids))
        ws.project.set_multi_selection(ids, primary=primary)
        # Multi-select in Edit mode is ambiguous (resize handles, single-
        # widget property edits) — mirror the Ctrl+click auto-switch so
        # the tool reflects the selection state.
        from app.ui.workspace.controls import TOOL_EDIT, TOOL_SELECT
        if len(ids) > 1 and ws.controls.tool == TOOL_EDIT:
            ws.controls.set_tool(TOOL_SELECT)

    def _iter_doc_widgets(self, doc):
        stack = list(doc.root_widgets)
        while stack:
            node = stack.pop()
            yield node
            stack.extend(node.children)

    # ------------------------------------------------------------------
    # Widget right-click
    # ------------------------------------------------------------------
    def on_widget_right_click(self, event, nid: str) -> str:
        ws = self.workspace
        # Route through the same drill-down resolver as left-click so
        # right-click on a container's child first targets the parent
        # (then the child, etc., as the user repeats clicks). Without
        # this, right-click jumped straight to the deepest widget and
        # the context menu acted on a different layer than the user's
        # current selection scope.
        resolved = ws.drag_controller._resolve_click_target(nid)
        if resolved is not None:
            nid = resolved
        # Preserve multi-selection when right-clicking one of its members
        # — calling select_widget here would collapse the set to a single
        # primary and make group Delete impossible from the context menu.
        multi_active = (
            len(ws.project.selected_ids) > 1
            and nid in ws.project.selected_ids
        )
        menu = tk.Menu(ws.winfo_toplevel(), tearoff=0)
        toplevel = ws.winfo_toplevel()
        if multi_active:
            count = len(ws.project.selected_ids)
            menu.add_command(
                label=f"Copy {count} widgets",
                command=self._copy_selection,
            )
            menu.add_command(
                label=f"Duplicate {count} widgets",
                command=self._duplicate_selection,
            )
            menu.add_separator()
            menu.add_command(
                label=f"Delete {count} widgets",
                command=ws._on_delete,
            )
            menu.add_separator()
            menu.add_command(
                label=f"Save {count} widgets as component…",
                command=self._save_selection_as_component,
            )
            self._add_group_entries_to_menu(menu, toplevel)
        else:
            ws.project.select_widget(nid)
            target_node = ws.project.get_widget(nid)
            target_descriptor = (
                get_descriptor(target_node.widget_type)
                if target_node is not None else None
            )
            target_is_container = (
                target_descriptor is not None
                and getattr(target_descriptor, "is_container", False)
            )
            cx_w, cy_w = ws._screen_to_canvas(event.x_root, event.y_root)
            add_submenu = ws.drops._build_add_widget_menu(
                menu,
                target_node if target_is_container else None,
                cx_w, cy_w, event.x_root, event.y_root,
            )
            menu.add_cascade(
                label="Add Widget as Child",
                menu=add_submenu,
                state="normal" if target_is_container else "disabled",
            )
            menu.add_separator()
            menu.add_command(
                label="Copy",
                command=lambda: self._copy_single(nid),
            )
            paste_state = "normal" if ws.project.clipboard else "disabled"
            menu.add_command(
                label="Paste",
                command=lambda: self._paste_at_widget(nid),
                state=paste_state,
            )
            menu.add_command(
                label="Duplicate",
                command=lambda: self._duplicate_with_history(nid),
            )
            menu.add_separator()
            from app.ui.workspace.controls import TOOL_EDIT
            edit_state = (
                "disabled" if ws.controls.tool == TOOL_EDIT
                else "normal"
            )
            menu.add_command(
                label="Edit mode",
                command=lambda: self._enter_edit_mode(nid),
                state=edit_state,
            )
            menu.add_command(
                label="Description…",
                command=lambda: self._open_widget_description(nid),
            )
            menu.add_separator()
            handler_submenu = self._build_handler_menu(target_node)
            menu.add_cascade(
                label="Add handler",
                menu=handler_submenu,
                state=("normal" if handler_submenu is not None else "disabled"),
            )
            menu.add_separator()
            menu.add_command(
                label="Save as component…",
                command=self._save_selection_as_component,
            )
            menu.add_separator()
            menu.add_command(
                label="Rename",
                command=lambda: self._prompt_rename_widget(nid),
            )
            menu.add_command(label="Delete", command=ws._on_delete)
            self._add_group_entries_to_menu(menu, toplevel)
            menu.add_separator()
            menu.add_command(
                label="Bring to Front",
                command=lambda: self._z_order_with_history(nid, "front"),
            )
            menu.add_command(
                label="Send to Back",
                command=lambda: self._z_order_with_history(nid, "back"),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _add_group_entries_to_menu(self, menu, toplevel) -> None:
        """Append the Group / Ungroup / Select Group entries to a
        context menu — each only added when currently runnable.
        Routes to the same MainWindow handlers used by the Edit menu
        and Ctrl+G / Ctrl+Shift+G so every entry point produces the
        same history record.
        """
        ws = self.workspace
        sel_ids = set(ws.project.selected_ids or set())
        can_group = ws.project.can_group_selection(sel_ids)
        # "Select Group" only makes sense when the current selection
        # is a partial group (1 member of a 2+ member group). Whole
        # group already selected → entry would be a no-op.
        select_group_id: str | None = None
        for wid in sel_ids:
            node = ws.project.get_widget(wid)
            gid = getattr(node, "group_id", None) if node else None
            if not gid:
                continue
            members = ws.project.iter_group_members(gid)
            if len(members) > 1 and sel_ids != {m.id for m in members}:
                select_group_id = gid
                break
        can_ungroup = any(
            getattr(ws.project.get_widget(wid), "group_id", None)
            for wid in sel_ids
        )
        if not (can_group or can_ungroup or select_group_id):
            return
        menu.add_separator()
        if can_group:
            menu.add_command(
                label="Group",
                accelerator=f"{MOD_LABEL_PLUS}G",
                command=toplevel._on_group_shortcut,
            )
        if select_group_id:
            menu.add_command(
                label="Select Group",
                command=lambda gid=select_group_id: toplevel._on_select_group(gid),
            )
        if can_ungroup:
            menu.add_command(
                label="Ungroup",
                accelerator=f"{MOD_LABEL_PLUS}Shift+G",
                command=toplevel._on_ungroup_shortcut,
            )

    # ------------------------------------------------------------------
    # Copy / duplicate / z-order / rename
    # ------------------------------------------------------------------
    def _copy_selection(self) -> None:
        ws = self.workspace
        ids = ws.project.selected_ids
        if not ids:
            return
        ws.project.copy_to_clipboard(ids)

    def _copy_single(self, nid: str) -> None:
        self.workspace.project.copy_to_clipboard({nid})

    def _enter_edit_mode(self, nid: str) -> None:
        """Right-click → Edit mode entry. Caller already selected
        ``nid``; flip the workspace tool so handles + property panel
        switch to the per-widget edit experience."""
        from app.ui.workspace.controls import TOOL_EDIT
        self.workspace.controls.set_tool(TOOL_EDIT)

    def _open_widget_description(self, nid: str) -> None:
        """Right-click → Description… entry. The widget is already
        selected, so a single event-bus publish is enough — the
        properties panel subscribes and opens the same multiline
        editor it uses for its own square-pen button."""
        self.workspace.project.event_bus.publish("request_edit_description")

    def _paste_at_widget(self, nid: str) -> None:
        ws = self.workspace
        if not ws.project.clipboard:
            return
        parent_id = paste_target_parent_id(ws.project, nid)
        target_doc = (
            ws.project.find_document_for_widget(parent_id)
            if parent_id else ws.project.active_document
        )
        from app.ui.variables_window import confirm_clipboard_paste_policy
        proceed, policy = confirm_clipboard_paste_policy(
            ws.winfo_toplevel(), ws.project, target_doc,
        )
        if not proceed:
            return
        new_ids = ws.project.paste_from_clipboard(
            parent_id=parent_id, var_policy=policy,
        )
        if not new_ids:
            return
        entries = build_bulk_add_entries(ws.project, new_ids)
        if entries:
            ws.project.history.push(
                BulkAddCommand(entries, label="Paste"),
            )

    def _duplicate_selection(self) -> None:
        ws = self.workspace
        ids = list(ws.project.selected_ids)
        if not ids:
            return
        new_ids: list[str] = []
        for nid in ids:
            new_id = ws.project.duplicate_widget(nid)
            if new_id is not None:
                new_ids.append(new_id)
        entries = build_bulk_add_entries(ws.project, new_ids)
        if entries:
            ws.project.history.push(
                BulkAddCommand(entries, label="Duplicate"),
            )

    def _duplicate_with_history(self, nid: str) -> None:
        ws = self.workspace
        new_id = ws.project.duplicate_widget(nid)
        if new_id is None:
            return
        entries = build_bulk_add_entries(ws.project, [new_id])
        if entries:
            ws.project.history.push(
                BulkAddCommand(entries, label="Duplicate"),
            )

    def _z_order_with_history(self, nid: str, direction: str) -> None:
        push_zorder_history(self.workspace.project, nid, direction)

    def _prompt_rename_widget(self, nid: str) -> None:
        ws = self.workspace
        node = ws.project.get_widget(nid)
        if node is None:
            return
        dialog = RenameDialog(ws.winfo_toplevel(), node.name)
        if dialog.result and dialog.result != node.name:
            before = node.name
            ws.project.rename_widget(nid, dialog.result)
            ws.project.history.push(
                RenameCommand(nid, before, dialog.result),
            )

    # ------------------------------------------------------------------
    # Event handler attach + jump
    # ------------------------------------------------------------------
    def _build_handler_menu(self, node) -> "tk.Menu | None":
        """Cascade for the right-click "Add handler" entry. Returns
        ``None`` when the widget type has no registered events.

        Each event surfaces as one row + an optional list of
        bound-method rows underneath:
        - **unbound** → ``+ <event label>`` — click stubs a fresh
          method and opens the editor.
        - **bound (≥1 method)** → one ``▶ <event label> — <method>``
          row per bound method (click → jump to editor) followed by
          a ``+ Add another <event label> action`` row that appends
          a new method (Decision #10 multi-method).

        Advanced events (``EventEntry.advanced=True``) render under a
        nested ``Advanced ▸`` submenu instead of the top-level list,
        so widgets with many bind-style events (CTkLabel) keep the
        default surface short.
        """
        ws = self.workspace
        from app.widgets.event_registry import events_partitioned
        if node is None:
            return None
        default_events, advanced_events = events_partitioned(node.widget_type)
        if not default_events and not advanced_events:
            return None
        sub = tk.Menu(ws.winfo_toplevel(), tearoff=0)

        def _render_into(menu: tk.Menu, entries) -> None:
            first = True
            for entry in entries:
                methods = list(node.handlers.get(entry.key, []) or [])
                if not first:
                    menu.add_separator()
                first = False
                if methods:
                    for method in methods:
                        menu.add_command(
                            label=f"{entry.label}  —  {method}",
                            command=lambda nid=node.id, m=method:
                                self._jump_to_handler_method(nid, m),
                        )
                    menu.add_command(
                        label=f"+  Add another {entry.label.lower()} action",
                        command=lambda nid=node.id, key=entry.key:
                            self._attach_event_handler(nid, key),
                    )
                else:
                    menu.add_command(
                        label=f"+  {entry.label}",
                        command=lambda nid=node.id, key=entry.key:
                            self._attach_event_handler(nid, key),
                    )

        _render_into(sub, default_events)
        if advanced_events:
            adv = tk.Menu(sub, tearoff=0)
            _render_into(adv, advanced_events)
            if default_events:
                sub.add_separator()
            sub.add_cascade(label="Advanced", menu=adv)
        return sub

    def _attach_event_handler(self, widget_id: str, event_key: str) -> None:
        """Right-click → "+ <event>" / "+ Add another …" flow:
        1. Validate the project's saved (we need
           ``<project>/assets/scripts/``).
        2. Resolve a method name (per-window collision check —
           Decision #15 — auto-suffix ``_2`` / ``_3``).
        3. Materialise the per-window behavior file + append a stub
           to the window's class.
        4. Push a ``BindHandlerCommand`` (multi-method append) so
           undo pops the row that was just added.
        5. Open the editor at the new method.
        """
        ws = self.workspace
        from app.io.scripts import (
            add_handler_stub, behavior_class_name,
            load_or_create_behavior_file,
            suggest_method_name,
        )
        from app.widgets.event_registry import event_by_key

        node = ws.project.get_widget(widget_id)
        if node is None:
            return
        entry = event_by_key(node.widget_type, event_key)
        if entry is None:
            return
        if not getattr(ws.project, "path", None):
            messagebox.showinfo(
                "Save first",
                "Save the project before adding event handlers — the "
                "behavior file lives in assets/scripts/ in the project "
                "folder.",
                parent=ws.winfo_toplevel(),
            )
            return
        document = ws.project.find_document_for_widget(widget_id)
        if document is None:
            return
        method_name = suggest_method_name(node, entry, document)
        file_path = load_or_create_behavior_file(
            ws.project.path, document,
        )
        if file_path is None:
            messagebox.showerror(
                "Couldn't write behavior file",
                "Failed to create assets/scripts/ folder. Check folder "
                "permissions on the project directory.",
                parent=ws.winfo_toplevel(),
            )
            return
        class_name = behavior_class_name(document)
        add_handler_stub(
            file_path, class_name, method_name, entry.signature,
        )
        # Apply the binding before pushing the command so undo can
        # locate the appended row by index. ``BindHandlerCommand``
        # records the index it appended at; mirroring that here keeps
        # do/redo paths consistent.
        methods = node.handlers.setdefault(event_key, [])
        methods.append(method_name)
        appended_index = len(methods) - 1
        cmd = BindHandlerCommand(widget_id, event_key, method_name)
        cmd._appended_index = appended_index
        ws.project.history.push(cmd)
        ws.project.event_bus.publish(
            "widget_handler_changed", widget_id, event_key, method_name,
        )
        # Editor doesn't auto-open on action creation — the flash
        # of a VS Code window every right-click was disruptive.
        # Double-click the row, F7, or right-click → "Open in
        # editor" is the explicit jump path.

    def _jump_to_handler_method(
        self, widget_id: str, method_name: str,
    ) -> None:
        """Open the editor at the named method on the widget's
        per-window behavior class. Used by every bound-method row
        in the cascade.
        """
        ws = self.workspace
        from app.core.settings import load_settings
        from app.io.scripts import (
            behavior_class_name, behavior_file_path,
            find_handler_method, launch_editor,
            resolve_project_root_for_editor as _resolve_project_root,
        )

        if not method_name or not getattr(ws.project, "path", None):
            return
        document = ws.project.find_document_for_widget(widget_id)
        if document is None:
            return
        file_path = behavior_file_path(ws.project.path, document)
        if file_path is None or not file_path.exists():
            return
        class_name = behavior_class_name(document)
        line = find_handler_method(file_path, class_name, method_name)
        editor_command = load_settings().get("editor_command")
        launch_editor(
            file_path, line=line, editor_command=editor_command,
            project_root=_resolve_project_root(ws.project),
        )

    # ------------------------------------------------------------------
    # Component save / window insert
    # ------------------------------------------------------------------
    def _save_selection_as_component(self) -> None:
        """Bundle the current selection as a fragment component. Every
        resolvable variable binding (local OR global) travels with the
        component — globals get demoted to locals on insert into the
        target Window. Deleted-var tokens drop silently. Requires a
        saved project (components live next to ``assets/`` in the
        project folder); blocks with a hint otherwise.
        """
        ws = self.workspace
        from app.core.component_paths import ensure_components_root
        from app.io.component_io import (
            count_assets_to_bundle, count_bindings_to_bundle, save_fragment,
        )
        from app.ui.component_save_dialog import ComponentSaveDialog

        ids = list(ws.project.selected_ids)
        if not ids:
            return
        nodes = [
            ws.project.get_widget(nid) for nid in ids
        ]
        nodes = [n for n in nodes if n is not None]
        if not nodes:
            return
        toplevel = ws.winfo_toplevel()
        current_path = getattr(toplevel, "_current_path", None)
        components_dir = ensure_components_root(current_path)
        if components_dir is None:
            messagebox.showinfo(
                "Save project first",
                "Components are stored next to assets in the project "
                "folder. Save the project before creating components.",
                parent=toplevel,
            )
            return
        owning_doc = ws.project.find_document_for_widget(nodes[0].id)
        source_window_id = owning_doc.id if owning_doc is not None else None
        first = nodes[0]
        default_name = first.name or first.widget_type
        bundled_count = count_bindings_to_bundle(nodes, ws.project)
        asset_count, asset_bytes = count_assets_to_bundle(
            nodes, ws.project,
        )
        dialog = ComponentSaveDialog(
            toplevel,
            default_name=default_name,
            components_dir=components_dir,
            bundled_var_count=bundled_count,
            bundled_asset_count=asset_count,
            bundled_asset_bytes=asset_bytes,
        )
        ws.wait_window(dialog)
        if dialog.result is None:
            return
        name, target_path = dialog.result
        try:
            save_fragment(
                target_path, name, nodes, ws.project,
                source_window_id=source_window_id,
            )
        except OSError as exc:
            messagebox.showerror(
                "Save component failed",
                f"Couldn't write component:\n{exc}",
                parent=toplevel,
            )
            return
        # Tell the components panel a new file appeared so its tree
        # repopulates without needing a tab switch.
        ws.project.event_bus.publish("component_library_changed")

    def _insert_window_component(self, component_path, payload) -> None:
        """Insert a window-type component as a brand-new Toplevel
        document. Confirmation modal first; on accept, the new
        document gets the component's display name (auto-suffixed
        with ``_2``/``_3`` on collision), all bundled local
        variables, the saved window properties, and the widget tree
        with bundle-token assets extracted into the project.
        """
        ws = self.workspace
        from app.core.commands import (
            AddDocumentCommand, _add_subtree_recursive,
        )
        from app.core.component_paths import component_display_stem
        from app.io.component_io import (
            extract_component_assets, instantiate_window_document,
        )
        from app.ui.component_window_insert_dialog import (
            ComponentWindowInsertDialog,
        )

        component_name = (
            payload.get("name") or component_display_stem(component_path)
        )
        target_name = self._pick_unique_document_name(component_name)
        toplevel = ws.winfo_toplevel()
        confirm = ComponentWindowInsertDialog(
            toplevel,
            component_name=component_name,
            target_doc_name=target_name,
        )
        toplevel.wait_window(confirm)
        if not confirm.result:
            return
        # Re-resolve the unique name in case the user managed to
        # add a document while the modal was open.
        target_name = self._pick_unique_document_name(component_name)
        extracted_assets, _component_folder = extract_component_assets(
            component_path,
            getattr(ws.project, "path", None),
            component_name,
        )
        new_doc, root_nodes = instantiate_window_document(
            payload,
            project=ws.project,
            target_name=target_name,
            asset_extracted_map=extracted_assets,
        )
        # Place the new doc to the right of the rightmost existing
        # one — same canvas-placement rule as the menubar Add Dialog.
        max_right = 0
        for doc in ws.project.documents:
            right = doc.canvas_x + doc.width
            if right > max_right:
                max_right = right
        new_doc.canvas_x = max_right + 120
        new_doc.canvas_y = 0
        index = len(ws.project.documents)
        ws.project.documents.append(new_doc)
        ws.project.set_active_document(new_doc.id)
        # Each root subtree gets registered through add_widget so the
        # workspace renderer fires widget_added per node and builds a
        # tk widget for it. Appending to doc.root_widgets directly
        # leaves the tree invisible (model present, never rendered) —
        # same trap delete-snapshot restore hits.
        for root in root_nodes:
            _add_subtree_recursive(
                ws.project, root, parent_id=None, document_id=new_doc.id,
            )
        ws.project.history.push(
            AddDocumentCommand(new_doc.to_dict(), index),
        )
        ws.project.event_bus.publish(
            "project_renamed", ws.project.name,
        )

    def _pick_unique_document_name(self, base: str) -> str:
        existing = {doc.name for doc in self.workspace.project.documents}
        if base not in existing:
            return base
        n = 2
        while True:
            candidate = f"{base}_{n}"
            if candidate not in existing:
                return candidate
            n += 1

    def _save_window_as_component(self, document) -> None:
        """Save the entire Window/Dialog as a window-type component.
        Every widget, the window_properties dict, and the document's
        full local-variable list travel with the bundle. Even a main
        window saves with ``is_toplevel=True`` in the payload — on
        insert the component always becomes a Toplevel, since a
        project only has one main window slot.
        """
        ws = self.workspace
        from app.core.component_paths import ensure_components_root
        from app.io.component_io import count_window_assets, save_window
        from app.ui.component_save_dialog import ComponentSaveDialog

        if not document.root_widgets:
            messagebox.showinfo(
                "Empty window",
                "This window has no widgets yet — add some before "
                "saving as a component.",
                parent=ws.winfo_toplevel(),
            )
            return
        toplevel = ws.winfo_toplevel()
        current_path = getattr(toplevel, "_current_path", None)
        components_dir = ensure_components_root(current_path)
        if components_dir is None:
            messagebox.showinfo(
                "Save project first",
                "Components are stored next to assets in the project "
                "folder. Save the project before creating components.",
                parent=toplevel,
            )
            return
        bundled_count = len(document.local_variables)
        asset_count, asset_bytes = count_window_assets(
            document, ws.project,
        )
        dialog = ComponentSaveDialog(
            toplevel,
            default_name=document.name,
            components_dir=components_dir,
            bundled_var_count=bundled_count,
            bundled_asset_count=asset_count,
            bundled_asset_bytes=asset_bytes,
        )
        ws.wait_window(dialog)
        if dialog.result is None:
            return
        name, target_path = dialog.result
        try:
            save_window(
                target_path, name, document, ws.project,
            )
        except OSError as exc:
            messagebox.showerror(
                "Save component failed",
                f"Couldn't write component:\n{exc}",
                parent=toplevel,
            )
            return
        ws.project.event_bus.publish("component_library_changed")
