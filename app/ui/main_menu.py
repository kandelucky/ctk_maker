"""Menubar construction + Edit-menu state + dispatchers mixin.

Split out of the monolithic ``main_window.py`` (v0.0.15.17 refactor).
Owns every tk.Menu the top menubar renders:

- File (New / Open / Recent Forms / Save / Save As / Export / Close / Quit)
- Edit (Undo / Redo / Copy / Paste / Delete / Select All / Bring to Front / Send to Back)
- Form (Preview / Add Dialog / Remove Current)
- View (Object Tree checkbutton / History checkbutton)
- Settings (Appearance Mode submenu)
- Help (Widget Docs / About)

Plus the per-menu dispatchers that wrap project mutations — Edit menu
entries route through here so the same action runs from both the
menubar and the keyboard shortcut layer (``main_shortcuts.py``).

Menu colours / styling constants live here (shared only within this
mixin); the MainWindow imports ``MENU_STYLE`` etc. via
``from app.ui.main_menu import MENU_STYLE`` for the very few call
sites that need them directly.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from app.ui.icons import load_tk_icon
from app.ui.palette import CATALOG


MENU_BG = "#2d2d30"
MENU_FG = "#cccccc"
MENU_ACTIVE_BG = "#094771"
MENU_ACTIVE_FG = "#ffffff"
MENU_DISABLED_FG = "#888888"
MENU_FONT = ("Segoe UI", 11)
MENU_ICON_SIZE = 18

MENU_STYLE = dict(
    bg=MENU_BG,
    fg=MENU_FG,
    activebackground=MENU_ACTIVE_BG,
    activeforeground=MENU_ACTIVE_FG,
    disabledforeground=MENU_DISABLED_FG,
    bd=0,
    borderwidth=0,
    activeborderwidth=0,
    relief="flat",
    font=MENU_FONT,
)

APPEARANCE_MODES = ["Light", "Dark", "System"]


class MenuMixin:
    """Menubar + Edit-menu dispatch. See module docstring."""

    def _rebuild_windows_menu(self) -> None:
        m = getattr(self, "_windows_menu", None)
        if m is None:
            return
        m.delete(0, "end")
        active_id = self.project.active_document_id
        for doc in self.project.documents:
            label = doc.name or "Untitled"
            if doc.is_toplevel:
                label = f"{label}  (Dialog)"
            is_active = doc.id == active_id
            fg = MENU_ACTIVE_FG if is_active else MENU_FG
            m.add_command(
                label=("▸ " if is_active else "   ") + label,
                foreground=fg,
                command=lambda did=doc.id: self._on_focus_document(did),
            )

    def _on_focus_document(self, doc_id: str) -> None:
        self.project.set_active_document(doc_id)
        self.workspace.focus_document(doc_id)

    def _refresh_form_menu_state(self) -> None:
        m = getattr(self, "_form_menu", None)
        if m is None:
            return
        doc = self.project.active_document
        is_dialog = getattr(doc, "is_toplevel", False)
        docs = self.project.documents
        idx = docs.index(doc) if doc in docs else 0
        on = MENU_FG
        off = MENU_DISABLED_FG
        # Remove (index 4) — disabled on main window
        m.entryconfig(4, foreground=on if is_dialog else off)
        # Move Up (index 9) — dialog and not first dialog (idx>1)
        m.entryconfig(9, foreground=on if (is_dialog and idx > 1) else off)
        # Move Down (index 10) — dialog and not last
        m.entryconfig(
            10, foreground=on if (is_dialog and idx < len(docs) - 1) else off,
        )

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------
    def _menu_icon(self, name: str):
        icon = load_tk_icon(name, size=MENU_ICON_SIZE)
        if icon is not None:
            self._menu_icons.append(icon)  # prevent GC
        return icon

    def _add_cmd(
        self, menu: tk.Menu, label: str, command,
        icon: str | None = None, accelerator: str | None = None,
    ) -> None:
        kwargs = dict(label=label, command=command)
        if accelerator:
            kwargs["accelerator"] = accelerator
        img = self._menu_icon(icon) if icon else None
        if img is not None:
            kwargs["image"] = img
            kwargs["compound"] = "left"
        menu.add_command(**kwargs)

    def _add_cascade(
        self, parent: tk.Menu, label: str, submenu: tk.Menu,
        icon: str | None = None,
    ) -> None:
        kwargs = dict(label=label, menu=submenu)
        img = self._menu_icon(icon) if icon else None
        if img is not None:
            kwargs["image"] = img
            kwargs["compound"] = "left"
        parent.add_cascade(**kwargs)

    # ------------------------------------------------------------------
    # Menubar construction
    # ------------------------------------------------------------------
    def _build_menubar(self) -> None:
        self._menu_icons: list = []
        menubar = tk.Menu(self, **MENU_STYLE)

        # ---- File ----
        file_menu = tk.Menu(menubar, tearoff=0, **MENU_STYLE)
        self._add_cmd(file_menu, "New...", self._on_new, icon="file-plus", accelerator="Ctrl+N")
        self._add_cmd(file_menu, "New Untitled", self._on_new_untitled, icon="file-plus-corner")
        self._add_cmd(file_menu, "Open...", self._on_open, icon="folder-open", accelerator="Ctrl+O")

        self._recent_menu = tk.Menu(file_menu, tearoff=0, **MENU_STYLE)
        self._add_cascade(file_menu, "Recent Forms", self._recent_menu, icon="history")
        self._rebuild_recent_menu()

        file_menu.add_separator()
        self._add_cmd(file_menu, "Save", self._on_save, icon="save", accelerator="Ctrl+S")
        self._add_cmd(file_menu, "Save As...", self._on_save_as, icon="save-all", accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        self._add_cmd(file_menu, "Export to Python...", self._on_export, icon="file-code")
        self._add_cmd(
            file_menu, "Export Active Document...",
            self._on_export_active_document, icon="file-code",
        )
        self._add_cmd(
            file_menu, "Run Python Script...",
            self._on_run_script, icon="tv-minimal-play",
        )
        file_menu.add_separator()
        self._add_cmd(file_menu, "Quit", self._on_quit, icon="log-out", accelerator="Ctrl+Q")
        menubar.add_cascade(label="File", menu=file_menu)

        # ---- Edit ----
        # postcommand recomputes enabled/disabled state just before
        # the menu drops open so it always reflects current selection,
        # clipboard, and history state.
        edit_menu = tk.Menu(
            menubar, tearoff=0,
            postcommand=self._refresh_edit_menu_state,
            **MENU_STYLE,
        )
        self._edit_menu = edit_menu
        self._add_cmd(
            edit_menu, "Undo", self._on_undo, accelerator="Ctrl+Z",
        )
        self._add_cmd(
            edit_menu, "Redo", self._on_redo, accelerator="Ctrl+Y",
        )
        edit_menu.add_separator()
        self._add_cmd(
            edit_menu, "Cut", self._on_menu_cut,
            accelerator="Ctrl+X",
        )
        self._add_cmd(
            edit_menu, "Copy", self._on_menu_copy,
            accelerator="Ctrl+C",
        )
        self._add_cmd(
            edit_menu, "Paste", self._on_menu_paste,
            accelerator="Ctrl+V",
        )
        self._add_cmd(
            edit_menu, "Duplicate", self._on_menu_duplicate,
            accelerator="Ctrl+D",
        )
        self._add_cmd(
            edit_menu, "Rename", self._on_menu_rename,
            accelerator="Ctrl+I",
        )
        self._add_cmd(
            edit_menu, "Delete", self._on_menu_delete,
            accelerator="Del",
        )
        edit_menu.add_separator()
        self._add_cmd(
            edit_menu, "Select All", self._on_menu_select_all,
            accelerator="Ctrl+A",
        )
        edit_menu.add_separator()
        self._add_cmd(
            edit_menu, "Bring to Front", self._on_menu_bring_to_front,
        )
        self._add_cmd(
            edit_menu, "Send to Back", self._on_menu_send_to_back,
        )
        menubar.add_cascade(label="Edit", menu=edit_menu)

        # ---- Form ----
        form_menu = tk.Menu(
            menubar, tearoff=0,
            postcommand=self._refresh_form_menu_state,
            **MENU_STYLE,
        )
        self._form_menu = form_menu
        # indices: 0=Preview, 1=Preview Active, 2=sep,
        #          3=Add Dialog, 4=Remove, 5=sep,
        #          6=Rename, 7=Form Settings, 8=sep,
        #          9=Move Up, 10=Move Down
        self._add_cmd(form_menu, "Preview", self._on_preview,
                      icon="play", accelerator="Ctrl+R")
        self._add_cmd(form_menu, "Preview Active", self._on_preview_active,
                      icon="play", accelerator="Ctrl+P")
        form_menu.add_separator()
        self._add_cmd(form_menu, "Add Dialog", self._on_add_dialog,
                      icon="plus", accelerator="Ctrl+M")
        self._add_cmd(form_menu, "Remove", self._on_remove_current_document,
                      icon="trash-2")
        form_menu.add_separator()
        self._add_cmd(form_menu, "Rename", self._on_rename_current_doc,
                      icon="pencil", accelerator="Ctrl+I")
        self._add_cmd(form_menu, "Form Settings", self._on_form_settings,
                      icon="settings")
        form_menu.add_separator()
        self._add_cmd(form_menu, "Move Up", self._on_move_doc_up,
                      icon="arrow-up")
        self._add_cmd(form_menu, "Move Down", self._on_move_doc_down,
                      icon="arrow-down")
        form_menu.add_separator()
        self._windows_menu = tk.Menu(
            form_menu, tearoff=0,
            postcommand=self._rebuild_windows_menu,
            **MENU_STYLE,
        )
        form_menu.add_cascade(label="All Forms", menu=self._windows_menu)
        menubar.add_cascade(label="Form", menu=form_menu)

        # ---- Widget ----
        widget_menu = tk.Menu(menubar, tearoff=0, **MENU_STYLE)
        for group in CATALOG:
            group_menu = tk.Menu(widget_menu, tearoff=0, **MENU_STYLE)
            for entry in group.items:
                self._add_cmd(
                    group_menu,
                    entry.display_name,
                    lambda e=entry: self.palette.add_entry(e),
                    icon=entry.icon,
                )
            self._add_cascade(widget_menu, group.title, group_menu)
        menubar.add_cascade(label="Widget", menu=widget_menu)

        # ---- View ----
        view_menu = tk.Menu(menubar, tearoff=0, **MENU_STYLE)
        view_menu.add_checkbutton(
            label="Object Tree",
            variable=self._object_tree_var,
            command=self._on_toggle_object_tree,
            accelerator="F8",
        )
        view_menu.add_checkbutton(
            label="History",
            variable=self._history_var,
            command=self._on_toggle_history_window,
            accelerator="F9",
        )
        menubar.add_cascade(label="View", menu=view_menu)

        # ---- Tools ----
        tools_menu = tk.Menu(menubar, tearoff=0, **MENU_STYLE)
        self._add_cmd(
            tools_menu, "Inspect CTk Widget...",
            self._on_inspect_widget, icon="search",
        )
        menubar.add_cascade(label="Tools", menu=tools_menu)

        # ---- Settings ----
        settings_menu = tk.Menu(menubar, tearoff=0, **MENU_STYLE)
        appearance_menu = tk.Menu(settings_menu, tearoff=0, **MENU_STYLE)
        for mode in APPEARANCE_MODES:
            appearance_menu.add_radiobutton(
                label=mode,
                variable=self._appearance_var,
                value=mode,
                command=self._on_appearance_change,
            )
        self._add_cascade(settings_menu, "Appearance Mode", appearance_menu, icon="palette")
        settings_menu.add_separator()
        self._add_cmd(
            settings_menu, "Reset Dismissed Warnings",
            self._on_reset_advisories, icon="bell",
        )
        menubar.add_cascade(
            label="Settings", menu=settings_menu, state="disabled",
        )

        # ---- Help ----
        help_menu = tk.Menu(menubar, tearoff=0, **MENU_STYLE)
        self._add_cmd(help_menu, "Documentation", self._on_widget_docs,
                      icon="book-open", accelerator="Ctrl+Shift+I")
        help_menu.add_separator()
        self._add_cmd(help_menu, "About...", self._on_about, icon="info")
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    # ------------------------------------------------------------------
    # Recent Forms submenu
    # ------------------------------------------------------------------
    def _rebuild_recent_menu(self) -> None:
        from pathlib import Path
        from app.core.recent_files import load_recent
        self._recent_menu.delete(0, "end")
        # Filter missing files — the entry stays in recent.json so a
        # temporarily-unmounted drive doesn't lose its history, but
        # the menu only offers rows that would actually open.
        paths = [p for p in load_recent() if Path(p).exists()]
        if not paths:
            self._recent_menu.add_command(label="(empty)", state="disabled")
        else:
            for p in paths:
                label = Path(p).name
                self._recent_menu.add_command(
                    label=label,
                    command=lambda path=p: self._open_path(path),
                )
        self._recent_menu.add_separator()
        self._recent_menu.add_command(
            label="Clear Menu", command=self._on_clear_recent,
        )

    def _on_clear_recent(self) -> None:
        from app.core.recent_files import clear_recent
        clear_recent()
        self._rebuild_recent_menu()

    # ------------------------------------------------------------------
    # Edit-menu state
    # ------------------------------------------------------------------
    def _refresh_edit_menu_state(self) -> None:
        """Dims menu entries whose action can't run right now.

        Windows tk.Menu draws a nasty emboss/shadow effect on
        ``state=disabled`` entries, so we keep them enabled and only
        swap the foreground colour. The command callbacks themselves
        no-op when the action can't run, and the inert-color rows
        visually communicate 'not available'.
        """
        menu = getattr(self, "_edit_menu", None)
        if menu is None:
            return
        has_selection = bool(self.project.selected_ids)
        has_clipboard = bool(self.project.clipboard)
        has_any = any(True for _ in self.project.iter_all_widgets())
        states = {
            "Undo": self.project.history.can_undo(),
            "Redo": self.project.history.can_redo(),
            "Copy": has_selection,
            "Paste": has_clipboard,
            "Delete": has_selection,
            "Select All": has_any,
            "Bring to Front": has_selection,
            "Send to Back": has_selection,
        }
        try:
            last = menu.index("end")
        except tk.TclError:
            return
        if last is None:
            return
        for i in range(last + 1):
            try:
                if menu.type(i) != "command":
                    continue
                label = menu.entrycget(i, "label")
            except tk.TclError:
                continue
            if label in states:
                menu.entryconfigure(
                    i,
                    foreground=MENU_FG if states[label] else MENU_DISABLED_FG,
                )

    # ------------------------------------------------------------------
    # Edit menu dispatchers — route to project methods so the same
    # action works regardless of which window has focus.
    # ------------------------------------------------------------------
    def _on_menu_cut(self) -> None:
        ids = self.project.selected_ids
        if not ids:
            return
        self.project.copy_to_clipboard(ids)
        # Delete without confirmation
        for wid in list(ids):
            node = self.project.get_widget(wid)
            if node is None:
                continue
            from app.core.commands import DeleteWidgetCommand
            snapshot = node.to_dict()
            parent_id = node.parent.id if node.parent is not None else None
            siblings = (
                node.parent.children if node.parent is not None
                else self.project.root_widgets
            )
            try:
                index = siblings.index(node)
            except ValueError:
                index = len(siblings)
            owning_doc = self.project.find_document_for_widget(wid)
            doc_id = owning_doc.id if owning_doc is not None else None
            self.project.remove_widget(wid)
            self.project.history.push(
                DeleteWidgetCommand(snapshot, parent_id, index, doc_id),
            )

    def _on_menu_duplicate(self) -> None:
        if hasattr(self, "workspace"):
            self.workspace._duplicate_selection()

    def _on_menu_rename(self) -> None:
        from app.ui.dialogs import RenameDialog
        from app.core.commands import RenameCommand
        sid = self.project.selected_id
        if sid is None:
            return
        node = self.project.get_widget(sid)
        if node is None:
            return
        dialog = RenameDialog(self, node.name)
        if dialog.result and dialog.result != node.name:
            before = node.name
            self.project.rename_widget(sid, dialog.result)
            self.project.history.push(
                RenameCommand(sid, before, dialog.result),
            )

    def _on_menu_copy(self) -> None:
        ids = self.project.selected_ids
        if ids:
            self.project.copy_to_clipboard(ids)

    def _on_menu_paste(self) -> None:
        if not self.project.clipboard:
            return
        from app.core.commands import paste_target_parent_id
        parent_id = paste_target_parent_id(
            self.project, self.project.selected_id,
        )
        new_ids = self.project.paste_from_clipboard(parent_id=parent_id)
        self._push_paste_history(new_ids)

    def _push_paste_history(self, new_ids: list[str]) -> None:
        if not new_ids:
            return
        from app.core.commands import BulkAddCommand, build_bulk_add_entries
        entries = build_bulk_add_entries(self.project, new_ids)
        if entries:
            self.project.history.push(
                BulkAddCommand(entries, label="Paste"),
            )

    def _on_menu_delete(self) -> None:
        sid = self.project.selected_id
        if sid is None:
            return
        node = self.project.get_widget(sid)
        if node is None:
            return
        from app.core.commands import DeleteWidgetCommand
        from app.widgets.registry import get_descriptor
        descriptor = get_descriptor(node.widget_type)
        type_label = (
            descriptor.display_name if descriptor else node.widget_type
        )
        confirmed = messagebox.askyesno(
            title="Delete widget",
            message=f"Delete this {type_label}?",
            icon="warning",
            parent=self,
        )
        if not confirmed:
            return
        snapshot = node.to_dict()
        parent_id = node.parent.id if node.parent is not None else None
        siblings = (
            node.parent.children if node.parent is not None
            else self.project.root_widgets
        )
        try:
            index = siblings.index(node)
        except ValueError:
            index = len(siblings)
        owning_doc = self.project.find_document_for_widget(sid)
        document_id = owning_doc.id if owning_doc is not None else None
        self.project.remove_widget(sid)
        self.project.history.push(
            DeleteWidgetCommand(snapshot, parent_id, index, document_id),
        )

    def _on_menu_select_all(self) -> None:
        def _walk(nodes):
            for n in nodes:
                yield n
                yield from _walk(n.children)
        doc = self.project.active_document
        all_ids = {n.id for n in _walk(doc.root_widgets)}
        if not all_ids:
            return
        primary = self.project.selected_id or next(iter(all_ids))
        self.project.set_multi_selection(all_ids, primary=primary)

    def _on_menu_bring_to_front(self) -> None:
        sid = self.project.selected_id
        if sid is not None:
            self._z_order_with_history(sid, "front")

    def _on_menu_send_to_back(self) -> None:
        sid = self.project.selected_id
        if sid is not None:
            self._z_order_with_history(sid, "back")

    def _z_order_with_history(self, nid: str, direction: str) -> None:
        from app.core.commands import push_zorder_history
        push_zorder_history(self.project, nid, direction)

    # ------------------------------------------------------------------
    # Advisory-dialog reset — clears every "don't show again" setting
    # so the dismissable warnings pop up again on their triggers.
    # ------------------------------------------------------------------
    def _on_reset_advisories(self) -> None:
        from app.core.settings import load_settings, save_setting
        settings = load_settings()
        advisory_keys = [
            k for k in settings if k.startswith("advisory_")
        ]
        if not advisory_keys:
            messagebox.showinfo(
                "Warnings reset",
                "No dismissed warnings to reset.",
                parent=self,
            )
            return
        for key in advisory_keys:
            save_setting(key, False)
        messagebox.showinfo(
            "Warnings reset",
            f"Cleared {len(advisory_keys)} dismissed warning(s). "
            "They'll surface again on their next trigger.",
            parent=self,
        )
