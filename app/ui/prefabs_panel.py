"""Prefabs library panel — folder tree over the user-wide prefab
root (see ``app/core/prefab_paths.py``).

This is the v1 shell: a recursive folder browser plus
create / rename / delete / reveal-in-explorer for both folders and
``.ctkprefab`` files. Save-from-canvas, drag-to-canvas insert,
preview, and asset / variable bundling all land in later phases.

Mirrors the visual chrome of ``ProjectPanel`` (assets) so the two
panels read as siblings.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

import customtkinter as ctk

from app.core.logger import log_error
from app.core.prefab_paths import PREFAB_EXT, ensure_prefabs_root

PANEL_BG = "#252526"
HEADER_BG = "#2a2a2a"
HEADER_FG = "#cccccc"
TREE_BG = "#1e1e1e"
TREE_FG = "#cccccc"
TREE_SEL_BG = "#094771"
TREE_ROW_HEIGHT = 20
TYPE_LABEL_FG = "#3b8ed0"
FILTER_BG = "#1e1e1e"
FILTER_BORDER = "#3c3c3c"

_FORBIDDEN_NAME_CHARS = set('\\/:*?"<>|')

# Widget type → row icon for single-widget fragment prefabs. Falls
# back to the generic frame icon when the type isn't listed.
_WIDGET_TYPE_ICONS = {
    "CTkButton": "square-mouse-pointer",
    "CTkSegmentedButton": "panel-left-right-dashed",
    "CTkLabel": "type",
    "Image": "image",
    "Card": "circle-stop",
    "CTkProgressBar": "loader",
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


class PrefabsPanel(ctk.CTkFrame):
    def __init__(self, parent, project=None):
        super().__init__(
            parent, fg_color=PANEL_BG, corner_radius=0, border_width=0,
        )
        self._project = project
        self._root_dir: Path = ensure_prefabs_root()
        self._iid_meta: dict[str, tuple[Path, str]] = {}
        self._menu_icons: dict[str, tk.PhotoImage] = {}
        self._row_icons: dict[str, tk.PhotoImage] = {}
        self._context_menu: tk.Menu | None = None
        self._filter_text: str = ""

        self._build_header()
        self._build_filter()
        self._build_tree()
        if project is not None:
            project.event_bus.subscribe(
                "prefab_library_changed",
                lambda *_a, **_k: self.refresh(),
            )
        self.after(0, self.refresh)

    def _row_icon(self, name: str) -> tk.PhotoImage | None:
        """Lazy + cache row icons. ttk.Treeview keeps a weak ref to
        ``image=`` PhotoImages — without the cache they vanish on
        the next tree rebuild.
        """
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
        # Compact header — just a `+` action button, no title bar
        # (the Palette tab already labels this view as "Prefabs"
        # via the tab tooltip).
        type_bar = ctk.CTkFrame(
            self, fg_color=HEADER_BG, height=22, corner_radius=0,
        )
        type_bar.pack(fill="x", pady=(0, 2))
        type_bar.pack_propagate(False)

        from app.ui.icons import load_icon
        plus_icon = load_icon("square-plus", size=14, color="#cccccc")
        self._add_btn = ctk.CTkButton(
            type_bar, text="" if plus_icon else "+",
            image=plus_icon,
            width=22, height=18, corner_radius=3,
            font=("Segoe UI", 11, "bold"),
            fg_color=HEADER_BG, hover_color="#3a3a3a",
            text_color="#cccccc",
            command=self._on_show_add_menu,
        )
        self._add_btn.pack(side="right", padx=(0, 4))

    def _build_filter(self) -> None:
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add(
            "write", lambda *_a: self._on_filter_changed(),
        )
        self._filter_entry = ctk.CTkEntry(
            self,
            textvariable=self._filter_var,
            placeholder_text="Search prefabs…",
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
        wrap = tk.Frame(self, bg=TREE_BG, highlightthickness=0)
        wrap.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        style = ttk.Style(wrap)
        # Windows native ttk theme ignores style.configure colours on
        # Treeview — switch to "default" so our dark style actually
        # paints (otherwise the empty tree area renders white).
        try:
            style.theme_use("default")
        except tk.TclError:
            pass
        style_name = "Prefabs.Treeview"
        style.configure(
            style_name,
            background=TREE_BG, fieldbackground=TREE_BG,
            foreground=TREE_FG, rowheight=TREE_ROW_HEIGHT,
            borderwidth=0, font=("Segoe UI", 9),
        )
        # Tk Treeview's default style.map carries a `("!disabled",
        # "!selected")` entry that overrides our custom backgrounds —
        # filter it out so selection colours actually apply.
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
            wrap, columns=(), show="tree", style=style_name,
            selectmode="browse",
        )
        self._tree.pack(fill="both", expand=True)
        # Type-tag styling — prefab rows render the type prefix in the
        # blue accent the Properties panel uses for type labels.
        self._tree.tag_configure(
            "prefab_type", foreground=TYPE_LABEL_FG,
        )
        self._tree.bind("<Button-3>", self._on_tree_right_click)
        self._tree.bind("<Button-1>", self._on_tree_left_click, add="+")
        # Drag from a prefab row onto the canvas — folder rows are
        # ignored (their press toggles open/close natively).
        self._drag_state: dict | None = None
        self._drag_threshold = 5
        self._drag_ghost: tk.Toplevel | None = None
        self._tree.bind("<ButtonPress-1>", self._on_drag_press, add="+")
        self._tree.bind("<B1-Motion>", self._on_drag_motion, add="+")
        self._tree.bind("<ButtonRelease-1>", self._on_drag_release, add="+")

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
        if not self._root_dir.exists():
            try:
                self._root_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                log_error("prefabs root create")
                return
        self._populate_dir(self._root_dir, parent_iid="")

    def _populate_dir(self, dir_path: Path, parent_iid: str) -> bool:
        """Insert children of ``dir_path`` under ``parent_iid``.
        Returns True if anything ended up visible — used by the parent
        folder to decide whether to keep itself when a filter is active
        (folders without matching descendants get hidden).
        """
        try:
            entries = sorted(
                dir_path.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except OSError:
            log_error(f"prefabs read {dir_path}")
            return False
        folder_icon = self._row_icon("folder")
        prefab_icon = self._row_icon("frame")
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
                # Auto-expand folders that hold filter matches so the
                # user sees results without manually clicking each
                # disclosure triangle.
                if needle and child_visible:
                    self._tree.item(iid, open=True)
            elif entry.suffix.lower() == PREFAB_EXT:
                from app.io.prefab_io import load_metadata
                meta = load_metadata(entry) or {}
                display_name = meta.get("name") or entry.stem
                if needle and needle not in display_name.lower():
                    continue
                type_label = self._format_type(meta)
                row_icon = self._row_icon_for(meta) or prefab_icon
                iid = self._tree.insert(
                    parent_iid, "end",
                    text=f" ({type_label}) {display_name}"
                    if type_label else f" {display_name}",
                    image=row_icon if row_icon else "",
                    tags=("prefab_type",),
                )
                self._iid_meta[iid] = (entry, "prefab")
                any_inserted = True
        return any_inserted

    def _format_type(self, meta: dict) -> str:
        """Short label for the row's ``(Type)`` prefix.
        Single-widget fragments show the widget kind directly so
        ``(CTkButton) Save`` reads naturally; multi-widget fragments
        and windows fall back to the prefab's kind.
        """
        prefab_type = meta.get("type", "fragment")
        node_types = meta.get("node_types") or []
        if prefab_type == "fragment" and len(node_types) == 1:
            return node_types[0]
        if prefab_type == "fragment":
            return "Fragment"
        if prefab_type == "window":
            return "Window"
        return prefab_type.capitalize()

    def _row_icon_for(self, meta: dict) -> tk.PhotoImage | None:
        """Pick a widget-type-specific row icon for single-widget
        fragments. Multi-widget / window prefabs fall back to the
        caller's generic icon.
        """
        node_types = meta.get("node_types") or []
        if meta.get("type") == "fragment" and len(node_types) == 1:
            icon_name = _WIDGET_TYPE_ICONS.get(node_types[0])
            if icon_name:
                return self._row_icon(icon_name)
        return None

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
        menu = self._make_menu()
        self._menu_command(
            menu, "New Folder...", "folder", self._on_new_folder_root,
        )
        menu.add_separator()
        self._menu_command(
            menu, "Open library folder in Explorer", "folder-open",
            lambda: self._reveal(self._root_dir),
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
        menu = self._make_menu()
        meta = self._iid_meta.get(iid)
        if meta is None:
            self._menu_command(
                menu, "New Folder...", "folder", self._on_new_folder_root,
            )
            menu.add_separator()
            self._menu_command(
                menu, "Open library folder in Explorer", "folder-open",
                lambda: self._reveal(self._root_dir),
            )
        else:
            path, kind = meta
            if kind == "folder":
                self._menu_command(
                    menu, "New Subfolder...", "folder",
                    lambda p=path: self._on_new_folder(p),
                )
                menu.add_separator()
                self._menu_command(
                    menu, "Open in Explorer", "folder-open",
                    lambda p=path: self._reveal(p),
                )
                self._menu_command(
                    menu, "Rename...", "pencil",
                    lambda p=path: self._on_rename(p),
                )
                self._menu_command(
                    menu, "Delete folder...", "trash-2",
                    lambda p=path: self._on_delete_folder(p),
                )
            else:
                self._menu_command(
                    menu, "Open in Explorer", "folder-open",
                    lambda p=path: self._reveal(p),
                )
                self._menu_command(
                    menu, "Rename...", "pencil",
                    lambda p=path: self._on_rename(p),
                )
                self._menu_command(
                    menu, "Delete...", "trash-2",
                    lambda p=path: self._on_delete_file(p),
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
            relief="flat", bd=0, font=("Segoe UI", 10),
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_new_folder_root(self) -> None:
        self._on_new_folder(self._root_dir)

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
            log_error(f"prefabs new folder {target}")
            messagebox.showerror(
                "New folder failed",
                f"Couldn't create folder:\n{target}",
                parent=self.winfo_toplevel(),
            )
            return
        self.refresh()

    def _on_rename(self, path: Path) -> None:
        old = path.stem if path.suffix == PREFAB_EXT else path.name
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
        if path.suffix == PREFAB_EXT:
            target = path.with_name(name + PREFAB_EXT)
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
            log_error(f"prefabs rename {path} → {target}")
            messagebox.showerror(
                "Rename failed",
                f"Couldn't rename:\n{path}\n→\n{target}",
                parent=self.winfo_toplevel(),
            )
            return
        self.refresh()

    def _on_delete_folder(self, path: Path) -> None:
        if path.resolve() == self._root_dir.resolve():
            return
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
            log_error(f"prefabs delete folder {path}")
            messagebox.showerror(
                "Delete failed",
                f"Couldn't delete folder:\n{path}",
                parent=self.winfo_toplevel(),
            )
            return
        self.refresh()

    def _on_delete_file(self, path: Path) -> None:
        confirm = messagebox.askyesno(
            "Delete prefab",
            f"Delete prefab '{path.stem}'?",
            parent=self.winfo_toplevel(),
        )
        if not confirm:
            return
        try:
            path.unlink()
        except OSError:
            log_error(f"prefabs delete file {path}")
            messagebox.showerror(
                "Delete failed",
                f"Couldn't delete prefab:\n{path}",
                parent=self.winfo_toplevel(),
            )
            return
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
                subprocess.Popen(["open", str(path.parent if path.is_file() else path)])
            else:
                subprocess.Popen(["xdg-open", str(path.parent if path.is_file() else path)])
        except OSError:
            log_error(f"prefabs reveal {path}")

    # ------------------------------------------------------------------
    # Drag-source — drop onto the workspace canvas
    # ------------------------------------------------------------------
    def _on_drag_press(self, event) -> None:
        iid = self._tree.identify_row(event.y)
        if not iid:
            self._drag_state = None
            return
        meta = self._iid_meta.get(iid)
        if meta is None or meta[1] != "prefab":
            self._drag_state = None
            return
        self._drag_state = {
            "path": meta[0],
            "name": meta[0].stem,
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

    def _on_drag_release(self, event) -> None:
        state = self._drag_state
        self._drag_state = None
        self._hide_drag_ghost()
        if state is None or not state["dragging"]:
            return
        if self._project is None:
            return
        self._project.event_bus.publish(
            "prefab_drop_request",
            state["path"], event.x_root, event.y_root,
        )

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
            font=("Segoe UI", 10, "bold"),
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

