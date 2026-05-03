"""Component library panel — folder tree over the per-project
``<project>/components/`` directory.

Phase A shell: a recursive folder browser plus
create / rename / delete / reveal-in-explorer for both folders and
``.ctkcomp`` files. Component save / drag-insert / preview live in
the workspace + dialog modules; this panel is the drag source +
catalog viewer.

Empty state — when no project is loaded (or it isn't saved yet) the
tree shows a "Save project first" hint and the toolbar disables.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Callable

import customtkinter as ctk

from app.ui.system_fonts import derive_ui_font
from app.core.component_paths import (
    COMPONENT_EXT, PUBLISH_COMPONENT_EXT,
    component_display_stem, components_root, ensure_components_root,
    is_component_file,
)
from app.core.logger import log_error

PANEL_BG = "#252526"
HEADER_BG = "#2a2a2a"
HEADER_FG = "#cccccc"
DIM_FG = "#888888"
TREE_BG = "#1e1e1e"
TREE_FG = "#cccccc"
TREE_SEL_BG = "#094771"
TREE_ROW_HEIGHT = 28
TYPE_LABEL_FG = "#3b8ed0"
FILTER_BG = "#1e1e1e"
FILTER_BORDER = "#3c3c3c"

_FORBIDDEN_NAME_CHARS = set('\\/:*?"<>|')

# Widget type → row icon for single-widget fragment components. Falls
# back to the generic frame icon when the type isn't listed.
_WIDGET_TYPE_ICONS = {
    "CTkButton": "square-mouse-pointer",
    "CTkSegmentedButton": "panel-left-right-dashed",
    "CTkLabel": "type",
    "Image": "image",
    "Card": "circle-stop",
    "CTkProgressBar": "loader",
    "CircularProgress": "circle-percent",
    "CTkCheckBox": "square-check",
    "CTkRadioButton": "circle-dot",
    "CTkSwitch": "toggle-left",
    "CTkEntry": "text-cursor-input",
    "CTkTextbox": "file-text",
    "CTkComboBox": "chevrons-up-down",
    "CTkOptionMenu": "menu",
    "CTkSlider": "sliders-horizontal",
    "CTkFrame": "frame",
    "CTkScrollableFrame": "scroll-text",
    "CTkTabview": "layout-panel-top",
}


def _is_valid_name(name: str) -> bool:
    name = name.strip()
    if not name or name in (".", ".."):
        return False
    return not any(ch in _FORBIDDEN_NAME_CHARS for ch in name)


class ComponentsPanel(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        project=None,
        path_provider: Callable[[], str | None] | None = None,
    ):
        super().__init__(
            parent, fg_color=PANEL_BG, corner_radius=0, border_width=0,
        )
        self._project = project
        self._path_provider = path_provider or (lambda: None)
        self._iid_meta: dict[str, tuple[Path, str]] = {}
        self._menu_icons: dict[str, tk.PhotoImage] = {}
        self._row_icons: dict[str, tk.PhotoImage] = {}
        self._context_menu: tk.Menu | None = None
        self._filter_text: str = ""

        self._build_header()
        self._build_filter()
        self._build_tree()
        self._build_empty_hint()
        if project is not None:
            bus = project.event_bus
            bus.subscribe(
                "component_library_changed",
                lambda *_a, **_k: self.refresh(),
            )
            # Refresh on project lifecycle events so the panel reflects
            # the current project's components folder.
            for evt in ("project_renamed", "active_document_changed"):
                bus.subscribe(evt, lambda *_a, **_k: self.refresh())
        self.after(0, self.refresh)

    def _row_icon(self, name: str) -> tk.PhotoImage | None:
        if name in self._row_icons:
            return self._row_icons[name]
        try:
            from app.ui.icons import load_tk_icon
            img = load_tk_icon(name, size=14, color="#cccccc")
        except Exception:
            img = None
        if img is not None:
            self._row_icons[name] = img
        return img

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        # Full-width "Library actions" button — opens the New Folder /
        # Import / Open-in-Explorer menu. The previous compact "+" was
        # too cryptic; pairing the icon with a label and stretching the
        # button across the panel width makes the affordance obvious.
        type_bar = ctk.CTkFrame(
            self, fg_color=HEADER_BG, height=24, corner_radius=0,
        )
        type_bar.pack(fill="x", pady=(0, 2))
        type_bar.pack_propagate(False)

        from app.ui.icons import load_icon
        plus_icon = load_icon("square-plus", size=18, color="#cccccc")
        self._add_btn = ctk.CTkButton(
            type_bar, text="Library actions",
            image=plus_icon,
            compound="left",
            height=24, corner_radius=3,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=HEADER_BG, hover_color="#3a3a3a",
            text_color="#cccccc",
            anchor="w",
            command=self._on_show_add_menu,
        )
        self._add_btn.pack(fill="x", padx=4)

    def _build_filter(self) -> None:
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add(
            "write", lambda *_a: self._on_filter_changed(),
        )
        self._filter_entry = ctk.CTkEntry(
            self,
            textvariable=self._filter_var,
            placeholder_text="Search components…",
            height=24,
            fg_color=FILTER_BG,
            border_color=FILTER_BORDER,
            border_width=1,
            corner_radius=3,
        )
        self._filter_entry.pack(fill="x", padx=4, pady=(0, 4))

    def _on_filter_changed(self) -> None:
        self._filter_text = self._filter_var.get().strip().lower()
        self.refresh()

    def _build_tree(self) -> None:
        self._tree_wrap = tk.Frame(self, bg=TREE_BG, highlightthickness=0)
        self._tree_wrap.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        style = ttk.Style(self._tree_wrap)
        try:
            style.theme_use("default")
        except tk.TclError:
            pass
        style_name = "Components.Treeview"
        style.configure(
            style_name,
            background=TREE_BG, fieldbackground=TREE_BG,
            foreground=TREE_FG, rowheight=TREE_ROW_HEIGHT,
            borderwidth=0, font=derive_ui_font(size=11),
        )
        # The default ttk Treeview layout wraps the tree area in a
        # "Treeview.field" element that paints a 1px border on focus
        # (the cyan rectangle the user sees around the panel). Strip
        # the wrapper so only the bare tree area renders.
        try:
            style.layout(
                style_name,
                [("Treeview.treearea", {"sticky": "nswe"})],
            )
        except tk.TclError:
            pass

        def _fixed_map(option: str):
            return [
                elm for elm in style.map(style_name, query_opt=option)
                if elm[:2] != ("!disabled", "!selected")
            ]
        style.map(
            style_name,
            background=_fixed_map("background") + [
                ("selected", TREE_SEL_BG),
            ],
            foreground=_fixed_map("foreground") + [
                ("selected", "#ffffff"),
            ],
        )
        self._tree = ttk.Treeview(
            self._tree_wrap, columns=(), show="tree", style=style_name,
            selectmode="browse",
            takefocus=False,
        )
        # ttk.Treeview keeps the tk-level highlight border even with
        # the wrap frame's highlightthickness zeroed — visible as a
        # cyan rectangle around the panel when the tree gets focus.
        # Strip it directly on the widget.
        try:
            self._tree.configure(highlightthickness=0, borderwidth=0)
        except tk.TclError:
            pass
        self._tree.pack(fill="both", expand=True)
        self._tree.tag_configure(
            "component_type", foreground=TYPE_LABEL_FG,
        )
        # Window-type components stand out from fragments with a
        # dark-orange tint so the user sees at a glance that drop
        # behaviour differs (creates a new Dialog instead of adding
        # widgets to the current window).
        self._tree.tag_configure(
            "window_component", foreground="#cc7e1f",
        )
        # Visual highlight for the folder row under a drag cursor —
        # blueish band signals "release here to move".
        self._tree.tag_configure(
            "drop_target", background="#26486b",
        )
        self._drop_target_iid: str | None = None
        self._tree.bind("<Button-3>", self._on_tree_right_click)
        self._tree.bind("<Double-Button-1>", self._on_tree_double_click)
        self._tree.bind("<Button-1>", self._on_tree_left_click, add="+")
        # Drag from a component row — release inside the tree on a
        # folder moves the file there; release outside the tree
        # publishes a canvas drop request.
        self._drag_state: dict | None = None
        self._drag_threshold = 5
        self._drag_ghost: tk.Toplevel | None = None
        self._tree.bind("<ButtonPress-1>", self._on_drag_press, add="+")
        self._tree.bind("<B1-Motion>", self._on_drag_motion, add="+")
        self._tree.bind("<ButtonRelease-1>", self._on_drag_release, add="+")

    def _build_empty_hint(self) -> None:
        """Inline hint shown in place of the tree when no project is
        loaded — components live next to ``assets/`` inside the
        project folder, so without a saved project there's nowhere
        to put them.
        """
        self._empty_hint = ctk.CTkLabel(
            self,
            text=(
                "Save the project first to use components.\n"
                "They live next to assets in the project folder."
            ),
            text_color=DIM_FG,
            font=ctk.CTkFont(size=10),
            wraplength=200,
            justify="center",
        )

    # ------------------------------------------------------------------
    # Refresh / populate
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        try:
            self._tree.delete(*self._tree.get_children())
        except tk.TclError:
            return
        self._iid_meta.clear()
        path = self._path_provider()
        root = ensure_components_root(path) if path else None
        if root is None:
            self._show_empty_state()
            return
        self._show_tree_state()
        self._populate_dir(root, parent_iid="")

    def _show_empty_state(self) -> None:
        self._tree_wrap.pack_forget()
        self._filter_entry.pack_forget()
        self._add_btn.configure(state="disabled")
        try:
            self._empty_hint.pack(padx=20, pady=30)
        except tk.TclError:
            pass

    def _show_tree_state(self) -> None:
        try:
            self._empty_hint.pack_forget()
        except tk.TclError:
            pass
        self._add_btn.configure(state="normal")
        if not self._filter_entry.winfo_ismapped():
            self._filter_entry.pack(fill="x", padx=4, pady=(0, 4))
        if not self._tree_wrap.winfo_ismapped():
            self._tree_wrap.pack(
                fill="both", expand=True, padx=4, pady=(0, 4),
            )

    def _populate_dir(self, dir_path: Path, parent_iid: str) -> bool:
        try:
            entries = sorted(
                dir_path.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except OSError:
            log_error(f"components read {dir_path}")
            return False
        folder_icon = self._row_icon("folder")
        component_icon = self._row_icon("frame")
        needle = self._filter_text
        any_inserted = False
        for entry in entries:
            if entry.is_dir():
                iid = self._tree.insert(
                    parent_iid, "end",
                    text=f" {entry.name}",
                    image=folder_icon if folder_icon else "",
                    open=False,
                )
                child_visible = self._populate_dir(entry, iid)
                self_matches = (not needle) or (needle in entry.name.lower())
                if not (child_visible or self_matches):
                    self._tree.delete(iid)
                    continue
                self._iid_meta[iid] = (entry, "folder")
                any_inserted = True
                if needle and child_visible:
                    self._tree.item(iid, open=True)
            elif is_component_file(entry):
                from app.io.component_io import load_metadata
                meta = load_metadata(entry) or {}
                display_name = (
                    meta.get("name") or component_display_stem(entry)
                )
                if needle and needle not in display_name.lower():
                    continue
                is_window = bool(meta.get("is_window"))
                type_label = self._format_type(meta)
                if is_window:
                    row_icon = (
                        self._row_icon("app-window") or component_icon
                    )
                    row_tag = "window_component"
                else:
                    row_icon = self._row_icon_for(meta) or component_icon
                    row_tag = "component_type"
                iid = self._tree.insert(
                    parent_iid, "end",
                    text=f" ({type_label}) {display_name}"
                    if type_label else f" {display_name}",
                    image=row_icon if row_icon else "",
                    tags=(row_tag,),
                )
                self._iid_meta[iid] = (entry, "component")
                any_inserted = True
        return any_inserted

    def _format_type(self, meta: dict) -> str:
        from app.ui.object_tree_window import _TYPE_INITIALS
        comp_type = meta.get("type", "fragment")
        node_types = meta.get("node_types") or []
        if comp_type == "fragment" and len(node_types) == 1:
            t = node_types[0]
            return _TYPE_INITIALS.get(
                t, "Frm" if t == "CTkFrame" else t[:3],
            )
        if comp_type == "fragment":
            return "Frag"
        if comp_type == "window":
            return "Window"
        return comp_type[:4].capitalize()

    def _row_icon_for(self, meta: dict) -> tk.PhotoImage | None:
        node_types = meta.get("node_types") or []
        if meta.get("type") == "fragment" and len(node_types) == 1:
            icon_name = _WIDGET_TYPE_ICONS.get(node_types[0])
            if icon_name:
                return self._row_icon(icon_name)
        return None

    # ------------------------------------------------------------------
    # Selection helpers — read by Prefab menu (Export / Preview…)
    # ------------------------------------------------------------------
    def get_selected_path(self) -> Path | None:
        """Currently-selected ``.ctkcomp`` path; ``None`` if folder /
        nothing is selected. Lets the menu enable Export / Preview
        only when a real component is highlighted.
        """
        try:
            sel = self._tree.selection()
        except tk.TclError:
            return None
        if not sel:
            return None
        meta = self._iid_meta.get(sel[0])
        if meta is None or meta[1] != "component":
            return None
        return meta[0]

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------
    def _menu_icon(self, name: str) -> tk.PhotoImage | None:
        if name in self._menu_icons:
            return self._menu_icons[name]
        try:
            from app.ui.icons import load_tk_icon
            img = load_tk_icon(name, size=14, color="#cccccc")
        except Exception:
            img = None
        if img is not None:
            self._menu_icons[name] = img
        return img

    def _menu_command(self, menu, label, icon_name, command):
        img = self._menu_icon(icon_name) if icon_name else None
        if img is not None:
            menu.add_command(
                label=label, image=img, compound="left", command=command,
            )
        else:
            menu.add_command(label=label, command=command)

    def _on_show_add_menu(self) -> None:
        path = self._path_provider()
        root = ensure_components_root(path) if path else None
        if root is None:
            return
        menu = self._make_menu()
        self._menu_command(
            menu, "New Folder...", "folder",
            lambda r=root: self._on_new_folder(r),
        )
        self._menu_command(
            menu, "Import component...", "file-plus",
            self._on_import,
        )
        menu.add_separator()
        self._menu_command(
            menu, "Open library folder in Explorer", "folder-open",
            lambda r=root: self._reveal(r),
        )
        try:
            x = self._add_btn.winfo_rootx()
            y = self._add_btn.winfo_rooty() + self._add_btn.winfo_height()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _on_tree_left_click(self, event) -> None:
        iid = self._tree.identify_row(event.y)
        if not iid:
            try:
                self._tree.selection_set([])
            except tk.TclError:
                pass

    def _on_tree_double_click(self, event) -> str | None:
        """Double-clicking a component is the keyboard-friendly twin
        of drag-onto-canvas: same routing, same confirmation modal.
        Folders fall through to the tree's native expand/collapse.
        """
        iid = self._tree.identify_row(event.y)
        if not iid:
            return None
        meta = self._iid_meta.get(iid)
        if meta is None or meta[1] != "component":
            return None
        self._request_insert(meta[0])
        return "break"

    def _request_insert(self, component_path: Path) -> None:
        """Publish the same drop event drag-and-drop would, anchored
        at the canvas's current screen center so the confirmation
        modal opens predictably.
        """
        try:
            toplevel = self.winfo_toplevel()
            x = toplevel.winfo_rootx() + toplevel.winfo_width() // 2
            y = toplevel.winfo_rooty() + toplevel.winfo_height() // 2
        except tk.TclError:
            x = y = 0
        self._project.event_bus.publish(
            "component_drop_request",
            component_path=component_path,
            x_root=x,
            y_root=y,
        )

    def _on_tree_right_click(self, event) -> None:
        iid = self._tree.identify_row(event.y)
        if iid:
            try:
                self._tree.selection_set(iid)
            except tk.TclError:
                pass
        else:
            try:
                self._tree.selection_set([])
            except tk.TclError:
                pass
        self._show_context_menu(event.x_root, event.y_root, iid or "")

    def _show_context_menu(
        self, x_root: int, y_root: int, iid: str,
    ) -> None:
        if self._context_menu is not None:
            try:
                self._context_menu.destroy()
            except tk.TclError:
                pass
        path = self._path_provider()
        root = components_root(path) if path else None
        menu = self._make_menu()
        meta = self._iid_meta.get(iid)
        if meta is None:
            if root is not None:
                self._menu_command(
                    menu, "New Folder...", "folder",
                    lambda r=root: self._on_new_folder(r),
                )
                self._menu_command(
                    menu, "Import component...", "file-plus",
                    self._on_import,
                )
                menu.add_separator()
                self._menu_command(
                    menu, "Open library folder in Explorer",
                    "folder-open", lambda r=root: self._reveal(r),
                )
        else:
            entry_path, kind = meta
            if kind == "folder":
                self._menu_command(
                    menu, "New Subfolder...", "folder",
                    lambda p=entry_path: self._on_new_folder(p),
                )
                menu.add_separator()
                self._menu_command(
                    menu, "Open in Explorer", "folder-open",
                    lambda p=entry_path: self._reveal(p),
                )
                self._menu_command(
                    menu, "Rename...", "pencil",
                    lambda p=entry_path: self._on_rename(p),
                )
                self._menu_command(
                    menu, "Delete folder...", "trash-2",
                    lambda p=entry_path: self._on_delete_folder(p),
                )
            else:
                # Insert / Preview lead the menu — they're the most
                # common actions on a component the user is browsing.
                from app.io.component_io import load_metadata
                meta = load_metadata(entry_path) or {}
                if meta.get("is_window"):
                    self._menu_command(
                        menu, "Insert as new Dialog", "app-window",
                        lambda p=entry_path: self._request_insert(p),
                    )
                else:
                    self._menu_command(
                        menu, "Insert into current window", "frame",
                        lambda p=entry_path: self._request_insert(p),
                    )
                self._menu_command(
                    menu, "Preview", "eye",
                    lambda p=entry_path: self._on_preview(p),
                )
                menu.add_separator()
                self._menu_command(
                    menu, "Export...", "save",
                    lambda p=entry_path: self._on_export(p),
                )
                self._menu_command(
                    menu, "Open in Explorer", "folder-open",
                    lambda p=entry_path: self._reveal(p),
                )
                self._menu_command(
                    menu, "Rename...", "pencil",
                    lambda p=entry_path: self._on_rename(p),
                )
                self._menu_command(
                    menu, "Delete...", "trash-2",
                    lambda p=entry_path: self._on_delete_file(p),
                )
        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()
        self._context_menu = menu

    def _make_menu(self) -> tk.Menu:
        return tk.Menu(
            self, tearoff=0,
            bg="#2d2d30", fg=HEADER_FG,
            activebackground="#094771", activeforeground="#ffffff",
            relief="flat", bd=0, font=derive_ui_font(size=10),
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_new_folder(self, parent_dir: Path) -> None:
        name = simpledialog.askstring(
            "New folder", "Folder name:",
            initialvalue="New Folder",
            parent=self.winfo_toplevel(),
        )
        if not name:
            return
        name = name.strip()
        if not _is_valid_name(name):
            messagebox.showwarning(
                "Invalid name",
                "Folder names can't contain \\ / : * ? \" < > |.",
                parent=self.winfo_toplevel(),
            )
            return
        target = parent_dir / name
        if target.exists():
            messagebox.showwarning(
                "Already exists",
                f"'{name}' already exists in '{parent_dir.name}'.",
                parent=self.winfo_toplevel(),
            )
            return
        try:
            target.mkdir(parents=True)
        except OSError:
            log_error(f"components new folder {target}")
            messagebox.showerror(
                "New folder failed",
                f"Couldn't create folder:\n{target}",
                parent=self.winfo_toplevel(),
            )
            return
        self.refresh()

    def _on_rename(self, path: Path) -> None:
        is_component = is_component_file(path)
        old = component_display_stem(path) if is_component else path.name
        name = simpledialog.askstring(
            "Rename", "New name:",
            initialvalue=old,
            parent=self.winfo_toplevel(),
        )
        if not name:
            return
        name = name.strip()
        if not _is_valid_name(name):
            messagebox.showwarning(
                "Invalid name",
                "Names can't contain \\ / : * ? \" < > |.",
                parent=self.winfo_toplevel(),
            )
            return
        if name == old:
            return
        if is_component:
            target = path.with_name(name + COMPONENT_EXT)
        else:
            target = path.with_name(name)
        if target.exists():
            messagebox.showwarning(
                "Already exists",
                f"'{target.name}' already exists.",
                parent=self.winfo_toplevel(),
            )
            return
        try:
            path.rename(target)
        except OSError:
            log_error(f"components rename {path} → {target}")
            messagebox.showerror(
                "Rename failed",
                f"Couldn't rename:\n{path}\n→\n{target}",
                parent=self.winfo_toplevel(),
            )
            return
        self.refresh()

    def _on_delete_folder(self, path: Path) -> None:
        confirm = messagebox.askyesno(
            "Delete folder",
            f"Delete folder '{path.name}' and everything inside it?",
            parent=self.winfo_toplevel(),
        )
        if not confirm:
            return
        try:
            shutil.rmtree(path)
        except OSError:
            log_error(f"components delete folder {path}")
            messagebox.showerror(
                "Delete failed",
                f"Couldn't delete folder:\n{path}",
                parent=self.winfo_toplevel(),
            )
            return
        self.refresh()

    def _on_delete_file(self, path: Path) -> None:
        confirm = messagebox.askyesno(
            "Delete component",
            f"Delete component '{component_display_stem(path)}'?",
            parent=self.winfo_toplevel(),
        )
        if not confirm:
            return
        try:
            path.unlink()
        except OSError:
            log_error(f"components delete file {path}")
            messagebox.showerror(
                "Delete failed",
                f"Couldn't delete component:\n{path}",
                parent=self.winfo_toplevel(),
            )
            return
        self.refresh()

    def _on_preview(self, path: Path) -> None:
        """Open the same read-only preview the Import dialog uses —
        builds widgets from the payload, extracts bundled assets to
        a temp dir for the duration of the preview window.
        """
        from app.io.component_io import load_payload
        from app.ui.component_preview_window import ComponentPreviewWindow
        payload = load_payload(path)
        if payload is None:
            messagebox.showerror(
                "Preview unavailable",
                f"'{path.name}' isn't a readable component.",
                parent=self.winfo_toplevel(),
            )
            return
        ComponentPreviewWindow(self.winfo_toplevel(), payload, path)

    def _on_export(self, path: Path) -> None:
        from app.ui.component_export_choice_dialog import run_export_flow
        run_export_flow(self.winfo_toplevel(), path)

    def _on_import(self) -> None:
        from tkinter import filedialog
        from app.ui.component_import_dialog import ComponentImportDialog
        path = self._path_provider()
        target_root = ensure_components_root(path) if path else None
        if target_root is None:
            messagebox.showinfo(
                "Save project first",
                "Components are stored next to assets in the project "
                "folder. Save the project before importing components.",
                parent=self.winfo_toplevel(),
            )
            return
        source = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="Import component",
            filetypes=[
                (
                    "CTkMaker component",
                    f"*{COMPONENT_EXT} *{PUBLISH_COMPONENT_EXT}",
                ),
                ("All files", "*.*"),
            ],
        )
        if not source:
            return
        source_path = Path(source)
        # Sanity-check the file is a valid component zip before
        # opening the import dialog — saves a confusing modal flow
        # when the user picks the wrong thing.
        from app.io.component_io import load_metadata
        if load_metadata(source_path) is None:
            messagebox.showerror(
                "Invalid component",
                f"'{source_path.name}' isn't a readable .ctkcomp file.",
                parent=self.winfo_toplevel(),
            )
            return
        dlg = ComponentImportDialog(
            self.winfo_toplevel(), source_path, target_root,
        )
        self.wait_window(dlg)
        if dlg.result:
            self.refresh()

    def _reveal(self, path: Path) -> None:
        try:
            if sys.platform == "win32":
                if path.is_dir():
                    os.startfile(str(path))
                else:
                    subprocess.Popen(
                        ["explorer", "/select,", str(path)],
                    )
            elif sys.platform == "darwin":
                subprocess.Popen([
                    "open", str(path.parent if path.is_file() else path),
                ])
            else:
                subprocess.Popen([
                    "xdg-open",
                    str(path.parent if path.is_file() else path),
                ])
        except OSError:
            log_error(f"components reveal {path}")

    # ------------------------------------------------------------------
    # Drag-source — release inside the tree on a folder = move; release
    # outside the tree = canvas insert (publishes ``component_drop_request``).
    # ------------------------------------------------------------------
    def _on_drag_press(self, event) -> None:
        iid = self._tree.identify_row(event.y)
        if not iid:
            self._drag_state = None
            return
        meta = self._iid_meta.get(iid)
        if meta is None or meta[1] != "component":
            self._drag_state = None
            return
        self._drag_state = {
            "path": meta[0],
            "name": component_display_stem(meta[0]),
            "source_iid": iid,
            "press_x": event.x_root,
            "press_y": event.y_root,
            "dragging": False,
        }

    def _on_drag_motion(self, event) -> None:
        state = self._drag_state
        if state is None:
            return
        if not state["dragging"]:
            dx = abs(event.x_root - state["press_x"])
            dy = abs(event.y_root - state["press_y"])
            if max(dx, dy) < self._drag_threshold:
                return
            state["dragging"] = True
            self._show_drag_ghost(state["name"])
        if self._drag_ghost is not None:
            try:
                self._drag_ghost.geometry(
                    f"+{event.x_root + 12}+{event.y_root + 12}",
                )
            except tk.TclError:
                pass
        # Highlight the folder under the cursor while inside the tree.
        target = self._resolve_inner_drop_target(
            event.x_root, event.y_root, state["path"],
        )
        self._set_drop_highlight(target["iid"] if target else None)

    def _on_drag_release(self, event) -> None:
        state = self._drag_state
        self._drag_state = None
        self._hide_drag_ghost()
        self._set_drop_highlight(None)
        if state is None or not state["dragging"]:
            return
        # If the cursor ended inside the tree on a folder (or the
        # library root area), move the file there. Otherwise treat
        # it as a canvas insert.
        target = self._resolve_inner_drop_target(
            event.x_root, event.y_root, state["path"],
        )
        if target is not None:
            self._move_into(state["path"], target["path"])
            return
        if self._cursor_inside_tree(event.x_root, event.y_root):
            return
        if self._project is None:
            return
        self._project.event_bus.publish(
            "component_drop_request",
            state["path"], event.x_root, event.y_root,
        )

    def _cursor_inside_tree(self, x_root: int, y_root: int) -> bool:
        try:
            tx = self._tree.winfo_rootx()
            ty = self._tree.winfo_rooty()
            tw = self._tree.winfo_width()
            th = self._tree.winfo_height()
        except tk.TclError:
            return False
        return tx <= x_root < tx + tw and ty <= y_root < ty + th

    def _resolve_inner_drop_target(
        self, x_root: int, y_root: int, source_path: Path,
    ) -> dict | None:
        """Returns ``{"iid": <str|None>, "path": Path}`` when the cursor
        is over a valid drop target inside the tree; ``None`` otherwise.

        - cursor on a folder row (not the source's current parent) → that folder
        - cursor on empty area below all rows + source isn't already in
          the library root → library root (no iid)
        - cursor on a component row OR the source's parent → ``None``
        """
        if not self._cursor_inside_tree(x_root, y_root):
            return None
        local_y = y_root - self._tree.winfo_rooty()
        iid = self._tree.identify_row(local_y)
        if iid:
            meta = self._iid_meta.get(iid)
            if meta is None or meta[1] != "folder":
                return None
            target_path = meta[0]
            if source_path.parent.resolve() == target_path.resolve():
                return None  # already in this folder
            return {"iid": iid, "path": target_path}
        # Empty area below all rows → drop into library root.
        path = self._path_provider()
        root = components_root(path) if path else None
        if root is None:
            return None
        if source_path.parent.resolve() == root.resolve():
            return None
        return {"iid": None, "path": root}

    def _set_drop_highlight(self, iid: str | None) -> None:
        prev = self._drop_target_iid
        if prev and prev != iid:
            try:
                meta = self._iid_meta.get(prev)
                # Restore the row's original tag so the blue band
                # doesn't linger after the cursor leaves.
                if meta and meta[1] == "component":
                    self._tree.item(prev, tags=("component_type",))
                else:
                    self._tree.item(prev, tags=())
            except tk.TclError:
                pass
        self._drop_target_iid = iid
        if iid:
            try:
                self._tree.item(iid, tags=("drop_target",))
            except tk.TclError:
                pass

    def _move_into(self, source: Path, target_dir: Path) -> None:
        dst = target_dir / source.name
        if dst.exists():
            messagebox.showwarning(
                "Already exists",
                f"'{source.name}' already exists in "
                f"'{target_dir.name}'.",
                parent=self.winfo_toplevel(),
            )
            return
        try:
            shutil.move(str(source), str(dst))
        except OSError:
            log_error(f"components move {source} → {dst}")
            messagebox.showerror(
                "Move failed",
                f"Couldn't move:\n{source}\n→\n{dst}",
                parent=self.winfo_toplevel(),
            )
            return
        self.refresh()

    def _show_drag_ghost(self, name: str) -> None:
        self._hide_drag_ghost()
        ghost = tk.Toplevel(self.winfo_toplevel())
        ghost.overrideredirect(True)
        try:
            ghost.attributes("-topmost", True)
            ghost.attributes("-alpha", 0.85)
        except tk.TclError:
            pass
        frame = tk.Frame(
            ghost, bg="#3b8ed0", bd=1, relief="solid",
            highlightbackground="#3b8ed0", highlightthickness=1,
        )
        frame.pack()
        tk.Label(
            frame, text=f"+ {name}",
            bg="#3b8ed0", fg="white",
            font=derive_ui_font(size=10, weight="bold"),
            padx=10, pady=4,
        ).pack()
        ghost.update_idletasks()
        self._drag_ghost = ghost

    def _hide_drag_ghost(self) -> None:
        if self._drag_ghost is None:
            return
        try:
            self._drag_ghost.destroy()
        except tk.TclError:
            pass
        self._drag_ghost = None
