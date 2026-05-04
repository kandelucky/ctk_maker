"""Asset inspector — floating panel + docked tab that shows the
current project's ``assets/`` folder as a recursive tree.

``ProjectPanel`` is the embeddable widget; ``ProjectWindow`` is the
floating-toplevel wrapper opened by F10 / View menu. Both share the
same component so the tree state stays consistent whether the user
keeps the panel docked next to Properties or pops it out.

Capabilities:
- Recursive folder browsing under ``assets/``. Default
  ``images / fonts / sounds`` subfolders ship as a starting point
  but the user can create / rename / delete arbitrary folder
  structures.
- Toolbar: + Image, + Font, + Folder, + Text File (.md). The kind
  buttons preserve the legacy auto-routing (image picker imports
  go to ``images/``, font imports to ``fonts/``).
- Right-click on a file → Open in Explorer, Reimport, Remove.
- Right-click on a folder → New Subfolder, Rename, Delete (recursive).
- Double-click → opens the file with the OS default application
  (``os.startfile`` Windows, ``open`` macOS, ``xdg-open`` Linux).
- Selecting a row populates an info panel: name, size, image
  dimensions, font family, etc.

Asset references are graceful: deleted images render as no-image
(CTkImage construction try/except already swallows missing files);
deleted font families fall back to Tk defaults via the cascade.
That keeps the Remove flow a single "are you sure?" confirmation
instead of a per-widget reference scan.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from app.core.logger import log_error
from app.core.paths import (
    ASSET_SUBDIRS, assets_dir, ensure_project_folder,
)

if TYPE_CHECKING:
    from app.core.project import Project

BG = "#1e1e1e"
PANEL_BG = "#252526"
HEADER_BG = "#2d2d30"
HEADER_FG = "#cccccc"
DIM_FG = "#888888"
ACCENT = "#5bc0f8"
TREE_BG = "#1e1e1e"
TREE_FG = "#cccccc"
TREE_SEL_BG = "#094771"

DIALOG_W = 340
DIALOG_H = 560
TREE_ROW_HEIGHT = 22

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico"}
FONT_EXTS = {".ttf", ".otf", ".ttc"}
SOUND_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
TEXT_EXTS = {".md", ".txt"}
CODE_EXTS = {".py"}

# Maps an asset kind key to ``(extensions set, filedialog filter spec)``.
# Used by import / reimport file pickers + by ``_kind_for_path`` to
# tag tree rows so the context menu and info panel can specialise.
ASSET_KINDS = {
    "images": (
        IMAGE_EXTS,
        ("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.ico"),
    ),
    "fonts": (
        FONT_EXTS,
        ("Fonts", "*.ttf *.otf *.ttc"),
    ),
    "sounds": (
        SOUND_EXTS,
        ("Sounds", "*.wav *.mp3 *.ogg *.flac *.m4a"),
    ),
    "text": (
        TEXT_EXTS,
        ("Text / Markdown", "*.md *.txt"),
    ),
    "code": (
        CODE_EXTS,
        ("Python", "*.py"),
    ),
}

# Filename validation — illegal on Windows, ambiguous on POSIX.
_FORBIDDEN_NAME_CHARS = set('\\/:*?"<>|')


def _kind_for_path(path: Path) -> str:
    """Classify ``path`` by extension. Folders return ``"folder"``;
    unknown extensions return ``"other"`` so the info panel just
    shows generic metadata.
    """
    if path.is_dir():
        return "folder"
    ext = path.suffix.lower()
    for key, (exts, _) in ASSET_KINDS.items():
        if ext in exts:
            return key
    return "other"


def _human_size(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}".replace(".0 ", " ")
        num_bytes //= 1024 if unit != "GB" else 1
        if unit == "GB":
            return f"{num_bytes:.1f} GB"
    return f"{num_bytes} B"


class ProjectPanel(ctk.CTkFrame):
    """Embeddable Project panel. The MainWindow owns one of these
    inside ``ProjectWindow`` (floating). A future Phase C will dock
    this into the right sidebar as a 4th tab.
    """

    def __init__(
        self,
        parent,
        project: "Project",
        path_provider: Callable[[], str | None],
        on_switch_page: Callable[[str], bool] | None = None,
        on_active_page_path_changed: Callable[[str], None] | None = None,
    ):
        super().__init__(
            parent, fg_color=PANEL_BG, corner_radius=0, border_width=0,
        )
        self.project = project
        self.path_provider = path_provider
        # Page-switch callback wired through MainWindow's
        # ``_switch_to_page`` (Ctrl+O-style flow with dirty check).
        # When unset, .ctkproj rows in the pages folder still render
        # but double-click is a no-op — the floating ProjectWindow
        # leaves it ``None`` because its switching is gated by the
        # docked panel's wiring.
        self.on_switch_page = on_switch_page
        # Notification when the active page's on-disk filename
        # changes (e.g. user renamed the currently-loaded page).
        # MainWindow updates ``_current_path`` so subsequent saves
        # land at the new path.
        self.on_active_page_path_changed = on_active_page_path_changed

        self._name_var = tk.StringVar()
        self._path_var = tk.StringVar()
        self._info_var = tk.StringVar(value="")

        # Maps tree iid → (file path, kind). ``kind`` is a subfolder
        # key from ASSET_KINDS (``"images"`` / ``"fonts"`` / etc.).
        # Folder rows aren't included.
        self._iid_meta: dict[str, tuple[Path, str]] = {}
        self._context_menu: tk.Menu | None = None
        # Per-kind row icon cache so the tree row indicates folder
        # vs file vs image at a glance. Loaded lazily on first
        # populate; PhotoImage refs live on this dict so Tk doesn't
        # GC them between rebuilds.
        self._kind_icons: dict[str, tk.PhotoImage] = {}
        # Menu icon cache — tk.Menu's ``image=`` needs a
        # ``tk.PhotoImage`` (not a CTkImage) and Tk drops the
        # PhotoImage reference as soon as the local var goes out
        # of scope. Stash refs on self so the menu actually
        # renders the glyph instead of a blank slot.
        self._menu_icons: dict[str, tk.PhotoImage] = {}

        self._build_header()
        self._build_tree()
        self._build_info_panel()
        self._build_footer()

        # Refresh whenever project name / save target / dirty state
        # changes — keeps the header text current after Save As, New
        # Project, etc.
        bus = project.event_bus
        for evt in (
            "project_renamed", "dirty_changed",
            # Phase 2 Step 3 — document add/remove/rename can move
            # behavior files in/out of ``assets/scripts/``; the asset
            # tree was reading stale state until refresh fired again.
            "document_added", "document_removed", "document_renamed",
        ):
            bus.subscribe(evt, lambda *_a, **_k: self.refresh())
        self.after(0, self.refresh)

    # ------- public API -------

    def refresh(self) -> None:
        # Event-bus subscribers from a closed Project window can fire
        # after their panel has been destroyed — the lambdas captured
        # ``self`` and live on past the panel's lifetime. Guard with a
        # widget-existence check so a stale dirty_changed publish
        # doesn't surface a Tcl "invalid command name" traceback.
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        path = self.path_provider()
        if path:
            p = Path(path)
            self._name_var.set(p.stem)
            self._path_var.set(_truncate_path(str(p.parent)))
            self._populate_tree(p)
            self._set_buttons_enabled(True)
        else:
            self._name_var.set("(untitled)")
            self._path_var.set("save first")
            try:
                self._tree.delete(*self._tree.get_children())
            except tk.TclError:
                pass
            self._set_buttons_enabled(False)

    # ------- internal layout -------

    def _build_header(self) -> None:
        # Mirrors PropertiesPanelV2's chrome shape so the docked
        # Assets tab reads as a sibling of Properties: a dark
        # ``type_bar``-like stripe with folder icon + project name
        # bold (header foreground, NOT a coloured accent — Assets
        # is descriptive metadata, not a typed selection like
        # Properties' widget kind), then a thinner row underneath
        # with the path.
        type_bar = ctk.CTkFrame(
            self, fg_color="#2a2a2a", height=26, corner_radius=0,
        )
        type_bar.pack(fill="x", pady=(0, 2))
        type_bar.pack_propagate(False)

        from app.ui.icons import load_icon
        folder_icon = load_icon("folder", size=14, color="#cccccc")
        ctk.CTkLabel(
            type_bar, text="", fg_color="#2a2a2a",
            image=folder_icon, width=16, height=18,
        ).pack(side="left", padx=(10, 0))

        ctk.CTkLabel(
            type_bar, textvariable=self._name_var,
            fg_color="#2a2a2a",
            font=("Segoe UI", 11, "bold"),
            text_color=HEADER_FG, height=18, anchor="w",
        ).pack(side="left", padx=(6, 0))

        # ``+`` button on the right of the type bar — same slot
        # Properties' help button uses, so muscle memory carries
        # between panels. Size 16 reads cleanly at 100% / 150% DPI
        # scale; the standard ``#cccccc`` colour matches the rest
        # of the chrome icons.
        plus_icon = load_icon("square-plus", size=16, color="#cccccc")
        self._add_btn = ctk.CTkButton(
            type_bar, text="" if plus_icon else "+",
            image=plus_icon,
            width=24, height=20, corner_radius=3,
            font=("Segoe UI", 12, "bold"),
            fg_color="#2a2a2a", hover_color="#3a3a3a",
            text_color="#cccccc",
            command=self._on_show_add_menu,
        )
        self._add_btn.pack(side="right", padx=(0, 8))

        # Path row — similar height to Properties' name row but
        # static text only (no edit affordance).
        path_row = tk.Frame(self, bg=BG, height=22, highlightthickness=0)
        path_row.pack(fill="x", pady=(0, 4), padx=6)
        path_row.pack_propagate(False)
        tk.Label(
            path_row, textvariable=self._path_var,
            bg=BG, fg=DIM_FG,
            font=("Segoe UI", 9), anchor="w",
        ).pack(side="left", padx=(6, 6), fill="x", expand=True)

    def _menu_icon(self, name: str) -> tk.PhotoImage | None:
        """Lazy-load + cache a Lucide icon for tk.Menu rows. Tk's
        menu widget keeps a weak ref to the PhotoImage; without
        the cache the icon vanishes on the second popup.
        """
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
        """Add a command to ``menu`` with a Lucide icon on the left.
        Falls back to a plain text entry if the icon failed to load
        so a missing PNG doesn't take the whole menu down with it.
        """
        img = self._menu_icon(icon_name) if icon_name else None
        if img is not None:
            menu.add_command(
                label=label, image=img, compound="left", command=command,
            )
        else:
            menu.add_command(label=label, command=command)

    def _on_show_add_menu(self) -> None:
        """Pop the + menu anchored under the button. Order:
        Folder (organise) → Image / Font (assets) → Python /
        Text (text content). Same kind icons the tree uses so
        the menu reads as a preview of what a new row would
        look like.
        """
        menu = tk.Menu(
            self, tearoff=0,
            bg="#2d2d30", fg=HEADER_FG,
            activebackground="#094771", activeforeground="#ffffff",
            relief="flat", bd=0, font=("Segoe UI", 10),
        )
        self._menu_command(menu, "Folder", "folder", self._on_new_folder)
        menu.add_separator()
        self._menu_command(
            menu, "Lucide Icon...", "layout-list", self._on_add_lucide_icon,
        )
        self._menu_command(menu, "Image...", "image", self._on_add_image)
        self._menu_command(menu, "Font...", "type", self._on_add_font)
        menu.add_separator()
        self._menu_command(
            menu, "Python File (.py)", "file-code",
            self._on_new_python_file,
        )
        self._menu_command(
            menu, "Text File (.md)", "file-text", self._on_new_text_file,
        )
        try:
            x = self._add_btn.winfo_rootx()
            y = self._add_btn.winfo_rooty() + self._add_btn.winfo_height()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _build_add_submenu(self, parent_menu: tk.Menu) -> tk.Menu:
        """Reusable ``Add here ▶`` submenu — the four content-import
        actions (Image / Font / Python / Text) packed into a single
        cascade so the right-click menus stay short. ``parent_menu``
        is the owner; tk requires the submenu to share the parent's
        master.
        """
        sub = tk.Menu(
            parent_menu, tearoff=0,
            bg="#2d2d30", fg=HEADER_FG,
            activebackground="#094771", activeforeground="#ffffff",
            relief="flat", bd=0, font=("Segoe UI", 10),
        )
        self._menu_command(
            sub, "Lucide Icon...", "layout-list", self._on_add_lucide_icon,
        )
        self._menu_command(
            sub, "Image...", "image", self._on_add_image,
        )
        self._menu_command(
            sub, "Font...", "type", self._on_add_font,
        )
        sub.add_separator()
        self._menu_command(
            sub, "Python File (.py)", "file-code",
            self._on_new_python_file,
        )
        self._menu_command(
            sub, "Text File (.md)", "file-text",
            self._on_new_text_file,
        )
        return sub

    def _menu_cascade(
        self, menu: tk.Menu, label: str, icon_name: str | None,
        submenu: tk.Menu,
    ) -> None:
        """Add a cascade entry with a leading icon. tk.Menu.add_cascade
        supports ``image=`` + ``compound=`` the same way ``add_command``
        does — wrap with the same null-fallback shape so a missing
        PNG doesn't break the menu.
        """
        img = self._menu_icon(icon_name) if icon_name else None
        if img is not None:
            menu.add_cascade(
                label=label, image=img, compound="left", menu=submenu,
            )
        else:
            menu.add_cascade(label=label, menu=submenu)

    def _build_tree(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0)
        wrap.pack(fill="both", expand=True, padx=10, pady=(2, 4))

        style = ttk.Style(wrap)
        style_name = "Project.Treeview"
        style.configure(
            style_name,
            background=TREE_BG, fieldbackground=TREE_BG,
            foreground=TREE_FG, rowheight=TREE_ROW_HEIGHT,
            borderwidth=0, font=("Segoe UI", 10),
        )
        style.map(
            style_name,
            background=[("selected", TREE_SEL_BG)],
            foreground=[("selected", "#ffffff")],
        )
        self._tree = ttk.Treeview(
            wrap, columns=(), show="tree", style=style_name,
            selectmode="extended",
        )
        self._tree.pack(fill="both", expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Button-3>", self._on_tree_right_click)
        self._tree.bind("<Double-Button-1>", self._on_tree_double_click)
        # Drag-and-drop within the tree to move files / folders
        # between subfolders. ``ButtonPress`` records the start
        # state; motion past the threshold flips into drag mode;
        # release runs the move when the target is a folder.
        self._tree.bind("<ButtonPress-1>", self._on_tree_press)
        self._tree.bind("<B1-Motion>", self._on_tree_drag)
        self._tree.bind("<ButtonRelease-1>", self._on_tree_release)
        self._drag_state: dict | None = None
        self._drag_threshold = 6  # pixels before press becomes drag
        # Tag for visual highlight of the active drop target — the
        # ttk.Style entry below assigns the colours.
        style.configure(
            "Project.Treeview.Item",
            background=TREE_BG,
        )
        self._tree.tag_configure(
            "drop_target", background="#26486b",
        )
        self._drop_target_iid: str | None = None

    def _build_info_panel(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0)
        wrap.pack(fill="x", padx=10, pady=(2, 4))
        # Multiline-friendly label with a fixed height so the panel
        # doesn't resize when switching between selections of
        # different metadata depth.
        self._info_label = tk.Label(
            wrap, textvariable=self._info_var,
            bg=PANEL_BG, fg=DIM_FG,
            font=("Segoe UI", 9), justify="left", anchor="nw",
            wraplength=DIALOG_W - 30, height=4,
        )
        self._info_label.pack(fill="x", padx=2)
        # Optional image thumbnail — packed only when the selection
        # is an image. ``height=1`` keeps the empty label tight when
        # no preview is showing; the image swap drives the actual
        # height. Tk holds the PhotoImage by attribute reference so
        # GC doesn't blank the widget after the next refresh.
        self._preview_label = tk.Label(
            wrap, bg=PANEL_BG, anchor="center",
        )
        self._preview_thumb_ref = None  # PhotoImage retain

    def _build_footer(self) -> None:
        # The four-button footer was consolidated into the header's
        # "+" menu — no widget here. Method kept (called from
        # ``__init__``) so the layout sequence reads top-to-bottom
        # as before; if a future panel needs footer chrome it lands
        # here without changing the constructor.
        return

    # ------- actions -------

    def _on_add_lucide_icon(self) -> None:
        """Open the bundled Lucide icon picker. Saves the tinted PNG
        into the right-clicked folder (or ``assets/images/`` by
        default), then refreshes the tree so the new file appears.
        """
        path = self.path_provider()
        if not path:
            return
        ensure_project_folder(Path(path).parent)
        target_dir = self._resolve_target_dir(fallback_subdir="images")
        if target_dir is None:
            target_dir = assets_dir(path) / "images"
        from app.ui.lucide_icon_picker_dialog import LucideIconPickerDialog
        dlg = LucideIconPickerDialog(self.winfo_toplevel(), target_dir)
        dlg.wait_window()
        if not dlg.result:
            return
        self.project.event_bus.publish("dirty_changed", True)
        self.refresh()

    def _on_add_image(self) -> None:
        self._add_asset(
            kind="images",
            title="Add image to project",
            error_label="image",
        )

    def _on_add_font(self) -> None:
        if not self._add_asset(
            kind="fonts",
            title="Add font to project",
            error_label="font",
        ):
            return
        # Register freshly imported fonts so the next picker open
        # shows them without needing a relaunch.
        path = self.path_provider()
        if path:
            try:
                from app.core.fonts import register_project_fonts
                register_project_fonts(path, root=self.winfo_toplevel())
            except Exception:
                log_error("project window font register")

    def _add_asset(
        self, kind: str, title: str, error_label: str,
    ) -> bool:
        path = self.path_provider()
        if not path:
            return False
        exts, filter_spec = ASSET_KINDS[kind]
        src = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title=title,
            filetypes=[filter_spec, ("All files", "*.*")],
        )
        if not src:
            return False
        src_path = Path(src)
        if src_path.suffix.lower() not in exts:
            messagebox.showwarning(
                f"Not a {error_label}",
                f"{src_path.name} doesn't look like a "
                f"{error_label} file.",
                parent=self.winfo_toplevel(),
            )
            return False
        project_folder = Path(path).parent
        ensure_project_folder(project_folder)
        # Selected folder (right-click target) wins; otherwise legacy
        # auto-route into the matching kind subfolder.
        target_dir = self._resolve_target_dir(fallback_subdir=kind)
        if target_dir is None:
            target_dir = assets_dir(path) / kind
        try:
            sha = _sha256(src_path)
        except OSError:
            log_error(f"add asset sha ({kind})")
            messagebox.showerror(
                f"Add {error_label} failed",
                f"Couldn't read the {error_label} file.",
                parent=self.winfo_toplevel(),
            )
            return False
        existing = _find_by_sha(target_dir, sha)
        if existing is None:
            dst = _unique_dest(target_dir, src_path.name)
            try:
                shutil.copy2(src_path, dst)
            except OSError:
                log_error(f"add asset copy ({kind})")
                messagebox.showerror(
                    f"Add {error_label} failed",
                    f"Couldn't copy:\n{src_path}\n→\n{dst}",
                    parent=self.winfo_toplevel(),
                )
                return False
        # Emit so the docked tab + the floating F10 window stay in
        # sync — without this, importing into one instance leaves
        # the other showing stale tree contents until the user
        # reopens it.
        self.project.event_bus.publish("dirty_changed", True)
        self.refresh()
        return True

    # ------- tree interactions -------

    def _on_tree_select(self, _event=None) -> None:
        self._refresh_info_panel()

    def _on_tree_double_click(self, _event=None) -> None:
        # Open the file with the OS default application
        # (``os.startfile`` on Windows, ``open`` macOS, ``xdg-open``
        # Linux). Folders toggle their open / closed state — Tk's
        # native double-click handler already does that, so a NO-OP
        # here is fine for folder rows.
        meta = self._selected_meta()
        if meta is None:
            return
        file_path, kind = meta
        if kind == "folder":
            return  # let Tk's expand/collapse default fire
        if kind == "page":
            # In-app page switch. Routes through MainWindow's
            # _switch_to_page (Ctrl+O-style dirty check + load).
            if self.on_switch_page is not None:
                self.on_switch_page(str(file_path))
            return "break"
        self._open_with_os(file_path)
        # Returning ``"break"`` would prevent Tk's own handler from
        # firing too — but on file rows there's nothing to break, so
        # we leave it alone.

    # ------- drag-and-drop move -------

    def _on_tree_press(self, event) -> None:
        """Stamp the start state for a potential drag. Letting Tk's
        own ``Button-1`` handler run first means we get its updated
        selection — Ctrl-click / Shift-click multi-select works
        without us reimplementing the selection rules.

        Empty-area click also clears the selection: ttk.Treeview
        keeps the previous selection alive when the user clicks
        below the last row, which made + Folder land inside the
        previously-selected folder instead of at the assets root.
        """
        iid = self._tree.identify_row(event.y)
        if not iid:
            self._drag_state = None
            try:
                self._tree.selection_set([])
            except tk.TclError:
                pass
            self._refresh_info_panel()
            return
        # Snapshot the selection BEFORE Tk's default Button-1 handler
        # fires — when the press lands on an already-selected row in a
        # multi-select state, Tk collapses the selection to just that
        # row, which would lose the other items the user wanted to
        # drag together.
        prev_sel = list(self._tree.selection())
        was_multi_press = iid in prev_sel and len(prev_sel) > 1
        self.after_idle(
            lambda: self._stamp_drag(
                event, iid,
                preserve_items=prev_sel if was_multi_press else None,
            )
        )

    def _stamp_drag(
        self, event, iid: str,
        preserve_items: list[str] | None = None,
    ) -> None:
        if preserve_items is not None:
            # Pressed on a multi-selected row — keep all the previously
            # selected items as the drag set even though Tk collapsed
            # the visual selection to one. Selection itself will be
            # restored on the actual drag start so a plain click that
            # never moves still collapses to single (expected Tk UX).
            items = preserve_items
        else:
            sel = self._tree.selection()
            # Only drag if the press landed on a row that's now
            # selected. ``identify_row`` may return iid even if the
            # user just clicked an inert region — guard against
            # dragging "nothing".
            if iid not in sel:
                self._drag_state = None
                return
            items = list(sel)
        self._drag_state = {
            "start_y": event.y, "start_x": event.x,
            "items": items, "active": False,
        }

    def _on_tree_drag(self, event) -> None:
        state = self._drag_state
        if not state:
            return
        # Wait until the cursor moves past the threshold before
        # showing the drag indicator — single clicks shouldn't trip
        # drag visual chrome.
        if not state["active"]:
            dx = abs(event.x - state["start_x"])
            dy = abs(event.y - state["start_y"])
            if max(dx, dy) < self._drag_threshold:
                return
            state["active"] = True
            # Restore the multi-selection visually now that we're
            # genuinely dragging — the press handler intentionally
            # leaves Tk's collapsed selection alone so a plain click
            # without drag still behaves like a normal single-select.
            try:
                self._tree.selection_set(state["items"])
            except tk.TclError:
                pass
            self._show_drag_ghost(state["items"])
        # Update ghost position so the icon trails the cursor.
        self._move_drag_ghost(event)
        target = self._resolve_drop_target(event.y)
        if target is not None and self._is_valid_drop_target(
            target, state["items"],
        ):
            self._set_drop_highlight(target.get("iid"))
        else:
            self._set_drop_highlight(None)

    def _on_tree_release(self, event) -> None:
        state = self._drag_state
        self._drag_state = None
        self._hide_drag_ghost()
        self._set_drop_highlight(None)
        if not state or not state.get("active"):
            return
        target = self._resolve_drop_target(event.y)
        if target is None or not self._is_valid_drop_target(
            target, state["items"],
        ):
            return
        target_dir = target["path"]
        sources = [
            self._iid_meta[i][0] for i in state["items"]
            if i in self._iid_meta
        ]
        self._move_into(sources, target_dir)

    def _resolve_drop_target(self, y: int) -> dict | None:
        """Return either ``{"iid": <folder_iid>, "path": Path}`` for a
        folder row under the cursor, or ``{"iid": None, "path":
        <assets root>}`` when the cursor is past the last row (treat
        the empty area below the tree as a drop into ``assets/``).
        Returns ``None`` only when the cursor is over a non-folder
        row OR there's no project loaded.
        """
        path = self.path_provider()
        if not path:
            return None
        iid = self._tree.identify_row(y)
        if iid:
            meta = self._iid_meta.get(iid)
            if meta is None:
                return None
            if meta[1] == "folder":
                return {"iid": iid, "path": meta[0]}
            return None
        # Empty area below all rows → drop into assets root.
        return {"iid": None, "path": assets_dir(path)}

    def _is_valid_drop_target(
        self, target: dict, source_iids: list[str],
    ) -> bool:
        """Forbid dropping a folder into itself or a descendant —
        ``shutil.move`` would either error or create an infinite
        loop. Also forbid a no-op drop where the target is already
        the source's parent.
        """
        target_path = target["path"]
        for src_iid in source_iids:
            src_meta = self._iid_meta.get(src_iid)
            if src_meta is None:
                continue
            src_path = src_meta[0]
            if src_path == target_path:
                return False  # self-drop
            try:
                if target_path.resolve().is_relative_to(
                    src_path.resolve(),
                ):
                    return False  # target is inside the source folder
            except (OSError, ValueError, AttributeError):
                pass
            if src_path.parent == target_path:
                return False  # already in this folder
        return True

    def _set_drop_highlight(self, iid: str | None) -> None:
        prev = self._drop_target_iid
        if prev and prev != iid:
            try:
                self._tree.item(prev, tags=())
            except tk.TclError:
                pass
        self._drop_target_iid = iid
        if iid:
            try:
                self._tree.item(iid, tags=("drop_target",))
            except tk.TclError:
                pass

    # ------- drag ghost (small floating icon following cursor) -------

    def _show_drag_ghost(self, source_iids: list[str]) -> None:
        """Spawn a tiny overrideredirect Toplevel with a file/folder
        icon — gives drag visual feedback without overriding the
        system cursor.
        """
        from app.ui.icons import load_tk_icon
        # Pick the icon by what's being dragged: folder if any
        # source is a folder, file otherwise.
        kinds = {
            self._iid_meta.get(i, (None, ""))[1] for i in source_iids
        }
        icon_name = "folder" if "folder" in kinds else "file"
        try:
            icon = load_tk_icon(icon_name, size=16, color="#cccccc")
        except Exception:
            icon = None
        ghost = tk.Toplevel(self.winfo_toplevel())
        ghost.overrideredirect(True)
        try:
            ghost.attributes("-topmost", True)
            ghost.attributes("-alpha", 0.85)
        except tk.TclError:
            pass
        ghost.configure(bg="#1c1c1c")
        frame = tk.Frame(
            ghost, bg="#1c1c1c", padx=6, pady=3,
            highlightbackground="#3c3c3c", highlightthickness=1,
        )
        frame.pack()
        if icon is not None:
            lbl_icon = tk.Label(
                frame, image=icon, bg="#1c1c1c",
            )
            lbl_icon.image = icon  # GC retain
            lbl_icon.pack(side="left", padx=(0, 4))
        count = len(source_iids)
        text = f"{count} item" if count == 1 else f"{count} items"
        tk.Label(
            frame, text=text, bg="#1c1c1c", fg="#cccccc",
            font=("Segoe UI", 9),
        ).pack(side="left")
        ghost.geometry("+0+0")
        self._drag_ghost = ghost

    def _move_drag_ghost(self, event) -> None:
        ghost = getattr(self, "_drag_ghost", None)
        if ghost is None:
            return
        try:
            x = self.winfo_pointerx() + 14
            y = self.winfo_pointery() + 10
            ghost.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def _hide_drag_ghost(self) -> None:
        ghost = getattr(self, "_drag_ghost", None)
        if ghost is None:
            return
        try:
            ghost.destroy()
        except tk.TclError:
            pass
        self._drag_ghost = None

    def _move_into(self, sources: list[Path], target_dir: Path) -> None:
        """Move every ``sources`` file / folder into ``target_dir``.
        Conflicts (file with same name in target) are reported
        per-item; the rest of the move continues so a partial drop
        still does what it can. After all moves finish, mark dirty
        + emit ``font_defaults_changed`` so widget render-paths
        re-resolve any newly-stale references gracefully.
        """
        moved = 0
        for src in sources:
            dst = target_dir / src.name
            if dst.exists():
                messagebox.showwarning(
                    "Already exists",
                    f"'{src.name}' already exists in '{target_dir.name}'."
                    " Skipping.",
                    parent=self.winfo_toplevel(),
                )
                continue
            try:
                shutil.move(str(src), str(dst))
                moved += 1
            except OSError:
                log_error(f"move {src} → {dst}")
                messagebox.showerror(
                    "Move failed",
                    f"Couldn't move:\n{src}\n→\n{dst}",
                    parent=self.winfo_toplevel(),
                )
        if moved:
            self.project.event_bus.publish("dirty_changed", True)
            self.project.event_bus.publish(
                "font_defaults_changed", self.project.font_defaults,
            )
        self.refresh()

    def _on_tree_right_click(self, event) -> None:
        iid = self._tree.identify_row(event.y)
        if iid:
            try:
                self._tree.selection_set(iid)
            except tk.TclError:
                pass
        else:
            # Empty-area right-click clears the previous selection
            # so + Folder / Add ▶ entries from the empty-area menu
            # actually land at the assets root, not inside whatever
            # folder was selected before.
            try:
                self._tree.selection_set([])
            except tk.TclError:
                pass
        self._refresh_info_panel()
        # Empty-area right-click pops the same menu but with file-only
        # entries disabled — the user can still create a folder/text
        # file at the assets root.
        self._show_context_menu(event.x_root, event.y_root, iid or "")

    def _show_context_menu(
        self, x_root: int, y_root: int, iid: str,
    ) -> None:
        if self._context_menu is not None:
            try:
                self._context_menu.destroy()
            except tk.TclError:
                pass
        menu = tk.Menu(
            self, tearoff=0,
            bg="#2d2d30", fg=HEADER_FG,
            activebackground="#094771", activeforeground="#ffffff",
            relief="flat", bd=0, font=("Segoe UI", 10),
        )
        meta = self._iid_meta.get(iid)
        if meta is None:
            # Right-clicked on the empty area below all rows.
            # Compact: New Folder + an "Add ▶" cascade for the
            # four content-import actions, then Open in Explorer.
            self._menu_command(
                menu, "New Folder...", "folder", self._on_new_folder,
            )
            self._menu_cascade(
                menu, "Add", "square-plus",
                self._build_add_submenu(menu),
            )
            menu.add_separator()
            self._menu_command(
                menu, "Open assets folder in Explorer",
                "folder-open", self._on_reveal_assets_root,
            )
        else:
            folder_path, kind = meta
            if kind == "folder":
                pages_root = self._resolve_pages_folder_for_meta()
                is_pages_folder = (
                    pages_root is not None
                    and folder_path.resolve() == pages_root.resolve()
                )
                if is_pages_folder:
                    # Pages folder — only New Page makes sense here.
                    # Generic "New Subfolder" / "Add ▶" would create
                    # asset-files inside a directory the schema
                    # expects to hold .ctkproj pages only.
                    self._menu_command(
                        menu, "New Page...", "layout-template",
                        self._on_new_page,
                    )
                    menu.add_separator()
                    self._menu_command(
                        menu, "Open in Explorer", "folder-open",
                        self._on_context_reveal,
                    )
                else:
                    # Folder right-click — same compact shape:
                    # New Subfolder + Add here ▶ + actions.
                    self._menu_command(
                        menu, "New Subfolder...", "folder",
                        self._on_new_folder,
                    )
                    self._menu_cascade(
                        menu, "Add here", "square-plus",
                        self._build_add_submenu(menu),
                    )
                    menu.add_separator()
                    self._menu_command(
                        menu, "Open in Explorer", "folder-open",
                        self._on_context_reveal,
                    )
                    self._menu_command(
                        menu, "Rename...", "pencil", self._on_rename,
                    )
                    self._menu_command(
                        menu, "Delete folder...", "trash-2",
                        self._on_delete_folder,
                    )
            elif kind == "page":
                # Page right-click — switch / duplicate / rename /
                # delete. Filesystem-level operations (Open with OS,
                # Reimport) don't apply to pages — they're routed
                # through the page CRUD helpers so project.json
                # stays in sync with the disk.
                self._menu_command(
                    menu, "Switch to this page", "external-link",
                    self._on_context_switch_page,
                )
                self._menu_command(
                    menu, "Duplicate", "copy",
                    self._on_context_duplicate_page,
                )
                self._menu_command(
                    menu, "Rename...", "pencil",
                    self._on_context_rename_page,
                )
                menu.add_separator()
                self._menu_command(
                    menu, "Open in Explorer", "folder-open",
                    self._on_context_reveal,
                )
                self._menu_command(
                    menu, "Delete page...", "trash-2",
                    self._on_context_delete_page,
                )
            else:
                self._menu_command(
                    menu, "Open", "external-link", self._on_context_open,
                )
                self._menu_command(
                    menu, "Open in Explorer", "folder-open",
                    self._on_context_reveal,
                )
                # Reimport is hidden for fonts because tkextrafont
                # caches the registration in the running Tk
                # interpreter — replacing the file on disk doesn't
                # reload the glyphs until a relaunch. Users can drop
                # a new font through the + menu instead.
                if kind != "fonts":
                    self._menu_command(
                        menu, "Reimport...", "rotate-cw",
                        self._on_context_reimport,
                    )
                menu.add_separator()
                self._menu_command(
                    menu, "Rename...", "pencil", self._on_rename,
                )
                self._menu_command(
                    menu, "Remove from project...", "trash-2",
                    self._on_context_remove,
                )
        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()
        self._context_menu = menu

    def _on_context_open(self) -> None:
        meta = self._selected_meta()
        if meta is None:
            return
        self._open_with_os(meta[0])

    def _on_context_reveal(self) -> None:
        meta = self._selected_meta()
        if meta is None:
            return
        self._reveal_file(meta[0])

    def _on_reveal_assets_root(self) -> None:
        """Empty-area menu hook → open the project's ``assets/``
        folder in the OS file manager. Useful when the user wants
        to drop in files via Explorer drag-drop or inspect the
        on-disk layout the tree is mirroring.
        """
        path = self.path_provider()
        if not path:
            return
        a_dir = assets_dir(path)
        if not a_dir.exists():
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(a_dir))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(a_dir)])
            else:
                subprocess.Popen(["xdg-open", str(a_dir)])
        except OSError:
            log_error("open assets root")

    def _on_context_remove(self) -> None:
        meta = self._selected_meta()
        if meta is None:
            return
        file_path, kind = meta
        self._remove_asset(file_path, kind)

    # ------- page CRUD (P3) -------

    def _resolve_pages_folder_for_meta(self) -> Path | None:
        """Same as ``_resolve_pages_folder`` but uses the current
        path_provider rather than a passed-in project file. Used by
        right-click handlers that don't already have a file path."""
        path = self.path_provider()
        if not path:
            return None
        return self._resolve_pages_folder(Path(path))

    def _selected_page_id(self) -> str | None:
        """Look up the project.json page id for the currently
        right-clicked page row. Walks ``project.pages`` matching the
        filename — id<->file is stable across rename within a session.
        """
        meta = self._selected_meta()
        if meta is None:
            return None
        file_path, kind = meta
        if kind != "page":
            return None
        target = file_path.name
        for entry in self.project.pages or []:
            if isinstance(entry, dict) and entry.get("file") == target:
                return entry.get("id")
        return None

    def _on_new_page(self) -> None:
        """Prompt for a name and create a new empty page in the
        project. The new page is added after the current one in
        project.json; the user explicitly switches to it via a
        follow-up double-click (matches "Ctrl+O within project").
        """
        if not self.project.folder_path:
            return
        from tkinter import simpledialog
        name = simpledialog.askstring(
            "New page", "Page name:",
            initialvalue="New page",
            parent=self.winfo_toplevel(),
        )
        if not name or not name.strip():
            return
        name = name.strip()
        from app.core.project_folder import (
            ProjectMetaError, add_page, seed_multi_page_meta_from_disk,
        )
        try:
            entry = add_page(self.project.folder_path, name)
        except ProjectMetaError as exc:
            messagebox.showerror(
                "New page failed", str(exc),
                parent=self.winfo_toplevel(),
            )
            return
        # Re-read project.json so project.pages reflects the new
        # entry — without this, _selected_page_id wouldn't find the
        # page if the user immediately right-clicks it.
        if self.path_provider():
            seed_multi_page_meta_from_disk(
                self.project, self.path_provider(),
            )
        self.refresh()
        # Auto-switch to the new page so the user can start editing
        # it immediately. Same dirty-prompt + load flow as a manual
        # double-click. ``add_page`` returned the entry; the file
        # lives at <pages>/<entry.file>.
        if self.on_switch_page is not None:
            from app.core.project_folder import pages_dir
            page_path = pages_dir(self.project.folder_path) / entry["file"]
            self.on_switch_page(str(page_path))

    def _on_context_switch_page(self) -> None:
        meta = self._selected_meta()
        if meta is None or self.on_switch_page is None:
            return
        file_path, kind = meta
        if kind != "page":
            return
        self.on_switch_page(str(file_path))

    def _on_context_duplicate_page(self) -> None:
        page_id = self._selected_page_id()
        if not page_id or not self.project.folder_path:
            return
        from app.core.project_folder import (
            ProjectMetaError, duplicate_page, seed_multi_page_meta_from_disk,
        )
        try:
            duplicate_page(self.project.folder_path, page_id)
        except ProjectMetaError as exc:
            messagebox.showerror(
                "Duplicate failed", str(exc),
                parent=self.winfo_toplevel(),
            )
            return
        if self.path_provider():
            seed_multi_page_meta_from_disk(
                self.project, self.path_provider(),
            )
        self.refresh()

    def _on_context_rename_page(self) -> None:
        page_id = self._selected_page_id()
        meta = self._selected_meta()
        if not page_id or meta is None or not self.project.folder_path:
            return
        # Pull current display name from project.pages so the prompt
        # pre-fills what the user sees in the tree, not the slugged
        # filename stem.
        current_name = next(
            (
                p.get("name", "") for p in (self.project.pages or [])
                if isinstance(p, dict) and p.get("id") == page_id
            ),
            "",
        )
        from app.ui.dialogs import prompt_rename_page
        new_name = prompt_rename_page(
            self.winfo_toplevel(), current_name,
        )
        if not new_name:
            return
        new_name = new_name.strip()
        if not new_name or new_name == current_name:
            return
        from app.core.project_folder import (
            ProjectMetaError, rename_page, seed_multi_page_meta_from_disk,
        )
        try:
            rename_page(self.project.folder_path, page_id, new_name)
        except ProjectMetaError as exc:
            messagebox.showerror(
                "Rename failed", str(exc),
                parent=self.winfo_toplevel(),
            )
            return
        # If the active page got renamed, the on-disk filename
        # changed too — notify MainWindow via the callback so it
        # can update ``_current_path`` and re-prime path-derived
        # state (autosave path, recent files, title bar).
        active_id = self.project.active_page_id
        if active_id == page_id and self.on_active_page_path_changed:
            from app.core.project_folder import (
                find_active_page_entry, page_file_path, read_project_meta,
            )
            try:
                meta_now = read_project_meta(self.project.folder_path)
                entry = find_active_page_entry(meta_now)
                if entry is not None:
                    new_path = page_file_path(
                        self.project.folder_path, entry["file"],
                    )
                    self.on_active_page_path_changed(str(new_path))
            except Exception:
                log_error("rename_page active sync")
        if self.path_provider():
            try:
                seed_multi_page_meta_from_disk(
                    self.project, self.path_provider(),
                )
            except Exception:
                log_error("rename_page reseed")
        self.refresh()

    def _on_context_delete_page(self) -> None:
        # Defer until the context menu's grab fully releases so the
        # askyesno dialog actually pops modal — without after_idle
        # the menu was still holding focus and the dialog flashed
        # behind / didn't surface for some users.
        self.after_idle(self._do_delete_page)

    def _do_delete_page(self) -> None:
        page_id = self._selected_page_id()
        if not page_id or not self.project.folder_path:
            return
        # Block deleting the only page — a project must always have
        # one. Surface the rule explicitly so the user understands
        # why the operation no-ops, instead of silently failing.
        if len(self.project.pages or []) <= 1:
            messagebox.showinfo(
                "Cannot delete page",
                "A project must have at least one page. Add another "
                "page first if you want to remove this one.",
                parent=self.winfo_toplevel(),
            )
            return
        # Resolve display name for the confirmation prompt.
        display = next(
            (
                p.get("name", "") for p in (self.project.pages or [])
                if isinstance(p, dict) and p.get("id") == page_id
            ),
            "",
        )
        if not messagebox.askyesno(
            "Delete page",
            f"Delete page '{display}'?\n\n"
            "The page file and its backups will be removed from disk. "
            "This can't be undone via Ctrl+Z.",
            parent=self.winfo_toplevel(),
        ):
            return
        # If the deleted page is the currently-active one, we need
        # to switch to the new active first so the editor isn't
        # holding state for a file that's about to vanish. Resolve
        # the new active id, switch, THEN delete.
        from app.core.project_folder import (
            ProjectMetaError, delete_page,
            page_file_path, read_project_meta,
            seed_multi_page_meta_from_disk,
        )
        was_active = self.project.active_page_id == page_id
        try:
            new_active_id = delete_page(self.project.folder_path, page_id)
        except ProjectMetaError as exc:
            messagebox.showerror(
                "Delete failed", str(exc),
                parent=self.winfo_toplevel(),
            )
            return
        if new_active_id is None:
            return  # last-page guard fired inside delete_page
        if was_active and self.on_switch_page is not None:
            try:
                meta_now = read_project_meta(self.project.folder_path)
                entry = next(
                    (
                        p for p in meta_now.get("pages", [])
                        if isinstance(p, dict) and p.get("id") == new_active_id
                    ),
                    None,
                )
                if entry is not None:
                    target = page_file_path(
                        self.project.folder_path, entry["file"],
                    )
                    # Skip the dirty prompt — the page being deleted
                    # took its dirty state with it. Just load the
                    # replacement directly.
                    self.on_switch_page(str(target))
            except Exception:
                log_error("delete_page switch")
        if self.path_provider():
            try:
                seed_multi_page_meta_from_disk(
                    self.project, self.path_provider(),
                )
            except Exception:
                log_error("delete_page reseed")
        self.refresh()

    def _on_context_reimport(self) -> None:
        meta = self._selected_meta()
        if meta is None:
            return
        file_path, kind = meta
        self._reimport_asset(file_path, kind)

    def _selected_meta(self) -> tuple[Path, str] | None:
        sel = self._tree.selection()
        if not sel:
            return None
        return self._iid_meta.get(sel[0])

    def _reveal_file(self, file_path: Path) -> None:
        if not file_path.exists():
            return
        try:
            if sys.platform == "win32":
                # ``/select,`` opens Explorer with the file highlighted
                # rather than the parent folder generic-open.
                subprocess.Popen(
                    ["explorer", "/select,", str(file_path)],
                )
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(file_path)])
            else:
                subprocess.Popen(["xdg-open", str(file_path.parent)])
        except OSError:
            log_error("reveal asset")

    _TEXT_LIKE_EXTS = {
        ".md", ".txt", ".py", ".json", ".yaml", ".yml",
        ".toml", ".cfg", ".ini", ".log",
    }

    def _open_with_os(self, file_path: Path) -> None:
        """Hand a file off to the OS default application — image
        viewer for .png, default font preview for .ttf, the user's
        preferred Markdown editor for .md, etc.

        Fallback chain when the default association doesn't open:
        1. text-like extensions (.md / .py / .txt / ...) → Notepad
           on Windows, TextEdit on macOS, xdg-open on Linux. Most
           users without an .md association still have a text
           editor that handles the file fine.
        2. otherwise: reveal in Explorer so the user sees the file.
        """
        if not file_path.exists():
            return
        # ``.py`` opens through the user's configured editor
        # (Settings → Editor tab) so free-form scripts land in the
        # same editor F7 uses for behavior files. ``launch_editor``
        # falls back to the Auto chain (VS Code → Notepad++ → IDLE),
        # so something runnable always wins out — no need for the
        # ``.py``-specific OS branch below.
        if file_path.suffix.lower() == ".py":
            from app.core.settings import load_settings
            from app.io.scripts import (
                launch_editor,
                resolve_project_root_for_editor,
            )
            editor_command = load_settings().get("editor_command")
            if launch_editor(
                file_path,
                editor_command=editor_command,
                project_root=resolve_project_root_for_editor(self.project),
            ):
                return
        try:
            if sys.platform == "win32":
                # Everything routes through ``explorer.exe``, which
                # delegates to Windows' normal double-click path.
                # Handles UWP / Microsoft Store associations cleanly.
                subprocess.Popen(
                    ["explorer.exe", str(file_path)],
                )
                return
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(file_path)])
                return
            subprocess.Popen(["xdg-open", str(file_path)])
            return
        except (OSError, FileNotFoundError):
            log_error("open with os default")

        # Default-app handler refused — usually means no
        # association. Try a text-editor fallback for text-like
        # extensions; everything else lands in the file manager.
        if file_path.suffix.lower() in self._TEXT_LIKE_EXTS:
            try:
                if sys.platform == "win32":
                    subprocess.Popen(["notepad.exe", str(file_path)])
                    return
                if sys.platform == "darwin":
                    subprocess.Popen(
                        ["open", "-a", "TextEdit", str(file_path)],
                    )
                    return
                # Linux xdg-open already attempted; keep falling
                # through to the file-manager reveal.
            except (OSError, FileNotFoundError):
                log_error("open with notepad fallback")
        self._reveal_file(file_path)

    # ------- folder + text file creation -------

    def _resolve_target_dir(
        self, fallback_subdir: str | None = None,
    ) -> Path | None:
        """Return the directory the next + Folder / + Text File /
        + Image / + Font click should land in. Selected folder wins
        (right-clicked folder gets the import); a selected file uses
        its parent; nothing selected falls back to
        ``assets/<fallback_subdir>/`` when given (legacy auto-route
        for + Image → ``images/``) or ``assets/`` root otherwise.
        """
        path = self.path_provider()
        if not path:
            return None
        a_dir = assets_dir(path)
        meta = self._selected_meta()
        if meta is None:
            if fallback_subdir:
                return a_dir / fallback_subdir
            return a_dir
        sel_path, kind = meta
        if kind == "folder":
            return sel_path
        return sel_path.parent

    def _on_new_folder(self) -> None:
        target = self._resolve_target_dir()
        if target is None:
            return
        from tkinter import simpledialog
        name = simpledialog.askstring(
            "New folder",
            "Folder name:",
            parent=self.winfo_toplevel(),
        )
        if not name:
            return
        name = name.strip()
        if not name or set(name) & _FORBIDDEN_NAME_CHARS:
            messagebox.showwarning(
                "Invalid name",
                "Folder name contains forbidden characters or is empty.",
                parent=self.winfo_toplevel(),
            )
            return
        new_dir = target / name
        if new_dir.exists():
            messagebox.showwarning(
                "Folder exists",
                f"'{name}' already exists in this location.",
                parent=self.winfo_toplevel(),
            )
            return
        try:
            new_dir.mkdir(parents=True)
        except OSError:
            log_error("new folder mkdir")
            messagebox.showerror(
                "New folder failed",
                f"Couldn't create:\n{new_dir}",
                parent=self.winfo_toplevel(),
            )
            return
        self.project.event_bus.publish("dirty_changed", True)
        self.refresh()

    def _on_new_text_file(self) -> None:
        self._create_text_file(
            kind="text",
            default_name="NOTES",
            allowed_exts=(".md", ".txt"),
            default_ext=".md",
            initial_content_for=lambda stem: f"# {stem}\n\n",
            dialog_title="New text file",
            error_label="text file",
        )

    def _on_new_python_file(self) -> None:
        # Starter docstring sets clear expectations about v0.1
        # behaviour-layer status, points users at the issue tracker
        # for prioritisation, and threads the support link. Plain
        # text (no emoji) so Windows default fonts render it
        # cleanly across every editor.
        self._create_text_file(
            kind="code",
            default_name="script",
            allowed_exts=(".py",),
            default_ext=".py",
            initial_content_for=_python_starter_template,
            dialog_title="New Python file",
            error_label="Python file",
        )

    def _create_text_file(
        self,
        *,
        kind: str,
        default_name: str,
        allowed_exts: tuple[str, ...],
        default_ext: str,
        initial_content_for,
        dialog_title: str,
        error_label: str,
    ) -> None:
        """Shared body for ``_on_new_text_file`` /
        ``_on_new_python_file`` (and any future text-class file the
        panel adds). Same prompt + extension-coercion + write-and-open
        flow with a per-kind starter template.
        """
        target = self._resolve_target_dir()
        if target is None:
            return
        from tkinter import simpledialog
        name = simpledialog.askstring(
            dialog_title,
            "Filename (without extension):",
            initialvalue=default_name,
            parent=self.winfo_toplevel(),
        )
        if not name:
            return
        name = name.strip()
        if not name or set(name) & _FORBIDDEN_NAME_CHARS:
            messagebox.showwarning(
                "Invalid name",
                "Filename contains forbidden characters or is empty.",
                parent=self.winfo_toplevel(),
            )
            return
        if not name.lower().endswith(allowed_exts):
            name = f"{name}{default_ext}"
        new_file = target / name
        if new_file.exists():
            messagebox.showwarning(
                "File exists",
                f"'{name}' already exists in this location.",
                parent=self.winfo_toplevel(),
            )
            return
        try:
            target.mkdir(parents=True, exist_ok=True)
            new_file.write_text(
                initial_content_for(Path(name).stem),
                encoding="utf-8",
            )
        except OSError:
            log_error(f"new {error_label} write")
            messagebox.showerror(
                f"New {error_label} failed",
                f"Couldn't create:\n{new_file}",
                parent=self.winfo_toplevel(),
            )
            return
        self.project.event_bus.publish("dirty_changed", True)
        self.refresh()
        # No auto-open. The user just typed a filename and clicked
        # OK — they expect to see the file land in the tree, not
        # for the OS to immediately steal focus into VSCode /
        # Notepad. Double-click on the row opens it when the user
        # is ready.

    # ------- rename / delete folder -------

    def _on_rename(self) -> None:
        meta = self._selected_meta()
        if meta is None:
            return
        old_path, kind = meta
        from tkinter import simpledialog
        new_name = simpledialog.askstring(
            "Rename",
            "New name:",
            initialvalue=old_path.name,
            parent=self.winfo_toplevel(),
        )
        if not new_name:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old_path.name:
            return
        if set(new_name) & _FORBIDDEN_NAME_CHARS:
            messagebox.showwarning(
                "Invalid name",
                "Name contains forbidden characters.",
                parent=self.winfo_toplevel(),
            )
            return
        new_path = old_path.parent / new_name
        if new_path.exists():
            messagebox.showwarning(
                "Already exists",
                f"'{new_name}' already exists.",
                parent=self.winfo_toplevel(),
            )
            return
        try:
            old_path.rename(new_path)
        except OSError:
            log_error("rename asset")
            messagebox.showerror(
                "Rename failed",
                f"Couldn't rename:\n{old_path}\n→\n{new_path}",
                parent=self.winfo_toplevel(),
            )
            return
        # File renames break references in widget properties (image
        # paths) — let the workspace re-render so missing files fall
        # back to defaults gracefully.
        self.project.event_bus.publish("dirty_changed", True)
        self.project.event_bus.publish(
            "font_defaults_changed", self.project.font_defaults,
        )
        self.refresh()

    def _on_delete_folder(self) -> None:
        meta = self._selected_meta()
        if meta is None or meta[1] != "folder":
            return
        folder = meta[0]
        # Count contents so the warning carries weight on big trees.
        try:
            count = sum(1 for _ in folder.rglob("*"))
        except OSError:
            count = 0
        if not messagebox.askyesno(
            "Delete folder",
            f"Delete '{folder.name}' and {count} item(s) inside it?\n\n"
            f"Path: {folder}\n\n"
            "This deletes the folder from disk and cannot be undone. "
            "Widgets that referenced any of these files fall back to "
            "a default at the next render.",
            parent=self.winfo_toplevel(),
            icon="warning",
        ):
            return
        try:
            # ``onerror`` flips read-only attributes + retries —
            # without it Windows refuses to delete folders that
            # got marked read-only by tools like git or git-lfs,
            # and shutil.rmtree errors out silently in some
            # callers' eyes.
            shutil.rmtree(folder, onerror=_force_remove_readonly)
        except Exception:
            log_error("delete folder rmtree")
            messagebox.showerror(
                "Delete failed",
                f"Couldn't delete:\n{folder}\n\nThe folder may be open "
                "in another program (Explorer window, terminal). "
                "Close it and try again.",
                parent=self.winfo_toplevel(),
            )
            return
        # Confirm the folder is actually gone — rmtree can sometimes
        # complete partially without raising on Windows.
        if folder.exists():
            log_error(f"delete folder still exists: {folder}")
            messagebox.showerror(
                "Delete failed",
                f"The folder couldn't be removed:\n{folder}\n\n"
                "It may be open in Explorer or a terminal. "
                "Close those windows and try again.",
                parent=self.winfo_toplevel(),
            )
            return
        self.project.event_bus.publish("dirty_changed", True)
        self.project.event_bus.publish(
            "font_defaults_changed", self.project.font_defaults,
        )
        self.refresh()

    # ------- info panel -------

    def _refresh_info_panel(self) -> None:
        meta = self._selected_meta()
        if meta is None:
            self._info_var.set("")
            self._hide_preview()
            return
        file_path, kind = meta
        try:
            if kind == "folder":
                # Path.stat().st_size on a directory returns the
                # directory entry size on Windows (~4 KB block) — not
                # the recursive content total. Sum file sizes manually.
                size_bytes = sum(
                    p.stat().st_size for p in file_path.rglob("*")
                    if p.is_file()
                )
            else:
                size_bytes = file_path.stat().st_size
        except OSError:
            size_bytes = 0
        lines = [
            file_path.name,
            f"Size: {_human_size(size_bytes)}",
        ]
        if kind == "images":
            dims = _read_image_size(file_path)
            if dims is not None:
                lines.append(f"Dimensions: {dims[0]} × {dims[1]} px")
            self._show_image_preview(file_path)
        elif kind == "fonts":
            family = _read_font_family(file_path)
            if family:
                lines.append(f"Family: {family}")
            lines.append(f"Format: {file_path.suffix.lstrip('.').upper()}")
            self._hide_preview()
        elif kind == "sounds":
            lines.append(f"Format: {file_path.suffix.lstrip('.').upper()}")
            self._hide_preview()
        else:
            self._hide_preview()
        self._info_var.set("\n".join(lines))

    def _show_image_preview(self, file_path: Path) -> None:
        try:
            from PIL import Image, ImageTk
            with Image.open(file_path) as img:
                preview = img.copy()
            preview.thumbnail((140, 140))
            tk_img = ImageTk.PhotoImage(preview)
        except Exception:
            self._hide_preview()
            return
        self._preview_thumb_ref = tk_img
        self._preview_label.configure(image=tk_img)
        try:
            self._preview_label.pack(pady=(4, 6))
        except tk.TclError:
            pass

    def _hide_preview(self) -> None:
        try:
            self._preview_label.pack_forget()
            self._preview_label.configure(image="")
        except tk.TclError:
            pass
        self._preview_thumb_ref = None

    # ------- asset removal / reimport -------

    def _remove_asset(self, file_path: Path, kind: str) -> None:
        """Delete an asset from disk after a single irreversible-action
        warning. References on widgets or in the font cascade fall
        back to Tk / CTk defaults at next render — descriptors already
        try/except around image loads, and Tk silently substitutes
        unknown font families. Skipping the project-wide reference
        scan keeps the dialog instant on big projects.
        """
        if not messagebox.askyesno(
            "Remove asset",
            f"Remove '{file_path.name}' from the project?\n\n"
            f"File: {file_path}\n\n"
            "This deletes the file from disk and cannot be undone. "
            "Widgets that referenced this asset fall back to a "
            "default at the next render.",
            parent=self.winfo_toplevel(),
            icon="warning",
        ):
            return
        # Resolve the font family BEFORE unlinking — once the file is
        # gone PIL can't read its name table and the cleanup pass
        # below would silently skip system_fonts / cascade / per-widget
        # references.
        family_to_purge: str | None = None
        if kind == "fonts":
            family_to_purge = _read_font_family(file_path)
        try:
            file_path.unlink()
        except OSError:
            log_error("remove asset unlink")
            messagebox.showerror(
                "Remove failed",
                f"Couldn't delete:\n{file_path}",
                parent=self.winfo_toplevel(),
            )
            return
        if family_to_purge:
            from app.core.fonts import purge_family_from_project
            purge_family_from_project(self.project, family_to_purge)
        self.project.event_bus.publish("dirty_changed", True)
        # Force a re-render so references that became stale (image
        # widgets pointing at a deleted file, font cascade entries
        # pointing at an uninstalled family) refresh to fallbacks.
        self.project.event_bus.publish(
            "font_defaults_changed", self.project.font_defaults,
        )
        self.refresh()

    def _reimport_asset(self, file_path: Path, kind: str) -> None:
        """Replace an existing asset's content in place — useful when
        the user has an updated version on disk (e.g. higher-res icon)
        and wants the swap to ripple through the whole project
        without renaming or rewiring anything. Path stays the same so
        every widget reference keeps working.
        """
        exts, filter_spec = ASSET_KINDS[kind]
        src = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title=f"Reimport {file_path.name}",
            filetypes=[filter_spec, ("All files", "*.*")],
        )
        if not src:
            return
        src_path = Path(src)
        if src_path.suffix.lower() not in exts:
            messagebox.showwarning(
                "Wrong file type",
                f"Picked file's extension doesn't match the asset's "
                f"kind ({kind}). Reimport keeps the existing filename, "
                "so the new file's content must be the same kind.",
                parent=self.winfo_toplevel(),
            )
            return
        try:
            shutil.copy2(src_path, file_path)
        except OSError:
            log_error("reimport asset copy")
            messagebox.showerror(
                "Reimport failed",
                f"Couldn't copy:\n{src_path}\n→\n{file_path}",
                parent=self.winfo_toplevel(),
            )
            return
        # Tkextrafont is per-file-path: re-register so the running Tk
        # interpreter picks up the new bytes without a relaunch.
        if kind == "fonts":
            try:
                from app.core.fonts import (
                    _loaded_files, register_font_file,
                )
                _loaded_files.pop(file_path.resolve(), None)
                register_font_file(
                    file_path, root=self.winfo_toplevel(),
                )
            except Exception:
                log_error("reimport font register")
        self.project.event_bus.publish("dirty_changed", True)
        # Trigger a re-render — image widgets need their CTkImage
        # rebuilt against the new file content.
        self.project.event_bus.publish(
            "font_defaults_changed", self.project.font_defaults,
        )
        self.refresh()

    # ------- tree population -------

    def _populate_tree(self, project_file: Path) -> None:
        # Snapshot expanded folders + selection so a refresh
        # (folder added / file moved) preserves the user's view.
        prev_open = self._snapshot_open_paths()
        prev_sel = self._selected_meta()
        prev_sel_path = prev_sel[0] if prev_sel else None

        self._tree.delete(*self._tree.get_children())
        self._iid_meta.clear()
        a_dir = assets_dir(project_file)
        if not a_dir.exists():
            return
        # Make sure the default skeleton exists for fresh projects so
        # the tree isn't empty on first open. Users can rename /
        # delete these later without breaking anything.
        for sub in ASSET_SUBDIRS:
            try:
                (a_dir / sub).mkdir(exist_ok=True)
            except OSError:
                log_error(f"ensure {sub} dir")

        # Bold tag for the active page — set up once, reused on every
        # populate so reload doesn't re-define the tag on every row.
        try:
            self._tree.tag_configure(
                "active_page",
                font=("Segoe UI", 10, "bold"),
                foreground="#5bc0f8",
            )
        except tk.TclError:
            pass

        # Resolve the pages folder for this project so we can flag
        # ``.ctkproj`` rows nested under it as "page" kind. Empty in
        # legacy single-file projects (no project.json marker).
        pages_root = self._resolve_pages_folder(project_file)
        active_page_file = self._resolve_active_page_file()

        # Recursive populate. Folders first, then files within each
        # level so the tree reads as a normal file browser.
        new_sel_iid: str | None = None
        self._ensure_kind_icons()

        def walk(parent_iid: str, dir_path: Path) -> None:
            nonlocal new_sel_iid
            try:
                entries = list(dir_path.iterdir())
            except OSError:
                return
            folders = sorted(
                (e for e in entries if e.is_dir()),
                key=lambda p: p.name.lower(),
            )
            files = sorted(
                (
                    e for e in entries
                    if e.is_file()
                    # Hide builder-managed sidecars: .bak rotations,
                    # .autosave snapshots, .tmp atomic-write residue.
                    # User-relevant files are .ctkproj pages + assets.
                    and not e.name.endswith(".bak")
                    and not e.name.endswith(".autosave")
                    and not e.name.endswith(".tmp")
                ),
                key=lambda p: p.name.lower(),
            )
            for folder in folders:
                count = sum(1 for _ in folder.iterdir())
                # Leading spaces buy a small gap between icon and
                # text — ttk.Treeview has no native icon→text
                # padding knob, and adjusting the row image element
                # would touch the global Treeview style.
                label = f"  {folder.name}  ({count})"
                is_open = (
                    str(folder.resolve()) in prev_open
                    or parent_iid == ""  # default top-level open
                )
                # Pages folder defaults to expanded so the user sees
                # their page list without an extra click — pages are
                # the primary navigation, not a buried subfolder.
                if (
                    pages_root is not None
                    and folder.resolve() == pages_root.resolve()
                ):
                    is_open = True
                fid = self._tree.insert(
                    parent_iid, "end", text=label, open=is_open,
                    image=self._kind_icons.get("folder", ""),
                )
                self._iid_meta[fid] = (folder, "folder")
                if (
                    prev_sel_path is not None
                    and folder.resolve() == prev_sel_path.resolve()
                ):
                    new_sel_iid = fid
                walk(fid, folder)
            for f in files:
                kind = _kind_for_path(f)
                # Reclassify .ctkproj inside the pages folder as
                # "page" so the icon + context menu specialise.
                if (
                    pages_root is not None
                    and f.suffix.lower() == ".ctkproj"
                    and f.parent.resolve() == pages_root.resolve()
                ):
                    kind = "page"
                is_active = (
                    kind == "page"
                    and active_page_file is not None
                    and f.resolve() == active_page_file.resolve()
                )
                icon_key = "page_active" if is_active else kind
                tags = ("active_page",) if is_active else ()
                # "(active)" badge is the explicit cue; bold + cyan
                # are reinforcing visual cues.
                row_text = f"  {f.name}"
                if is_active:
                    row_text += "   (active)"
                iid = self._tree.insert(
                    parent_iid, "end", text=row_text,
                    image=self._kind_icons.get(
                        icon_key, self._kind_icons.get("other", ""),
                    ),
                    tags=tags,
                )
                self._iid_meta[iid] = (f, kind)
                if (
                    prev_sel_path is not None
                    and f.resolve() == prev_sel_path.resolve()
                ):
                    new_sel_iid = iid

        walk("", a_dir)
        if new_sel_iid is not None:
            try:
                self._tree.selection_set(new_sel_iid)
                self._tree.see(new_sel_iid)
            except tk.TclError:
                pass
        self._refresh_info_panel()

    def _resolve_pages_folder(self, project_file: Path) -> Path | None:
        """Return ``<root>/assets/pages/`` for multi-page projects,
        ``None`` for legacy single-file. Used to flag rows in the
        tree as page-kind so the icon + context menu specialise.
        """
        from app.core.project_folder import find_project_root, pages_dir
        root = find_project_root(project_file)
        if root is None:
            return None
        pdir = pages_dir(root)
        return pdir if pdir.is_dir() else None

    def _resolve_active_page_file(self) -> Path | None:
        """Absolute path to the current page's .ctkproj, used by the
        tree populate to bold the active row. Falls back to the
        ``path_provider`` value (which is already the active page)
        so the bold logic also works during the moment between
        in-memory change and project.json sync.
        """
        try:
            path = self.path_provider()
        except Exception:
            path = None
        return Path(path) if path else None

    def _ensure_kind_icons(self) -> None:
        """Lazy-load Lucide icons for the row leading column. Caches
        on ``self._kind_icons`` keyed by row kind so a re-populate
        doesn't reload the PNGs from disk.
        """
        if self._kind_icons:
            return
        from app.ui.icons import load_tk_icon
        kind_to_icon_name = {
            "folder": "folder",
            "images": "image",
            "fonts": "type",
            "sounds": "music",
            "text": "file-text",
            "code": "file-code",
            "other": "file",
            # Page (.ctkproj inside assets/pages/) — same icon as
            # the canvas/window concept so it reads "this is a UI
            # design", distinct from generic files.
            "page": "layout-template",
            "page_active": "layout-template",
        }
        for kind, icon_name in kind_to_icon_name.items():
            try:
                color = "#5bc0f8" if kind == "page_active" else "#cccccc"
                img = load_tk_icon(icon_name, size=14, color=color)
            except Exception:
                img = None
            if img is not None:
                self._kind_icons[kind] = img

    def _snapshot_open_paths(self) -> set[str]:
        """Capture every currently-expanded folder iid → resolved
        path so a re-populate keeps user's expand state. Without
        this, every refresh would collapse the whole tree.
        """
        opened: set[str] = set()
        for iid, (path, kind) in self._iid_meta.items():
            if kind != "folder":
                continue
            try:
                if self._tree.item(iid, "open"):
                    opened.add(str(path.resolve()))
            except tk.TclError:
                continue
        return opened

    def _set_buttons_enabled(self, enabled: bool) -> None:
        # Only the "+" button is project-state-gated now — the four
        # action buttons it replaced lived in the footer. Disabled
        # while the project is untitled (no save target → asset
        # imports would fail at copy time).
        try:
            self._add_btn.configure(
                state="normal" if enabled else "disabled",
            )
        except tk.TclError:
            pass


# ---------------------------------------------------------------------------
# Floating window wrapper
# ---------------------------------------------------------------------------

class ProjectWindow(ctk.CTkToplevel):
    """Floating wrapper around ``ProjectPanel`` (opened by F10)."""

    def __init__(
        self,
        parent,
        project: "Project",
        path_provider: Callable[[], str | None],
        on_close: Callable[[], None] | None = None,
        on_switch_page: Callable[[str], bool] | None = None,
        on_active_page_path_changed: Callable[[str], None] | None = None,
    ):
        super().__init__(parent)
        self.title("Assets")
        self.configure(fg_color=BG)
        self.geometry(f"{DIALOG_W}x{DIALOG_H}")
        self.minsize(260, 320)
        try:
            self.transient(parent)
        except tk.TclError:
            pass

        self._on_close_callback = on_close
        self.panel = ProjectPanel(
            self, project, path_provider,
            on_switch_page=on_switch_page,
            on_active_page_path_changed=on_active_page_path_changed,
        )
        self.panel.pack(fill="both", expand=True, padx=6, pady=6)
        self._place_relative_to(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _place_relative_to(self, parent) -> None:
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            x = px + 60
            y = py + 80
            self.geometry(f"{DIALOG_W}x{DIALOG_H}+{x}+{y}")
        except tk.TclError:
            pass

    def _on_close(self) -> None:
        if self._on_close_callback is not None:
            try:
                self._on_close_callback()
            except Exception:
                pass
        self.destroy()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_by_sha(folder: Path, sha: str) -> Path | None:
    if not folder.exists():
        return None
    for f in folder.iterdir():
        if not f.is_file():
            continue
        try:
            if _sha256(f) == sha:
                return f
        except OSError:
            continue
    return None


def _unique_dest(folder: Path, name: str) -> Path:
    """Avoid filename collision — append `_2`, `_3`, ... before suffix."""
    folder.mkdir(parents=True, exist_ok=True)
    candidate = folder / name
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    n = 2
    while True:
        candidate = folder / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def _truncate_path(text: str, max_len: int = 32) -> str:
    """Front-truncated path so the trailing project folder stays
    visible. Designed for the inline header in the project panel
    where horizontal real estate is tight.
    """
    if len(text) <= max_len:
        return text
    return "..." + text[-(max_len - 3):]


def _python_starter_template(stem: str) -> str:
    """Body of every newly-created ``.py`` in the Assets panel.
    Plain helper module — write functions / classes here and import
    them from per-window behavior files when you want to share
    logic between windows.
    """
    return (
        f'"""{stem}.py — helper module.\n'
        f"\n"
        f"Free-form Python file. Use it to share helpers / classes\n"
        f"between per-window behavior files (the .py files under\n"
        f"assets/scripts/<page>/ that back each window's events).\n"
        f"\n"
        f"Per-widget event handlers belong in those per-window\n"
        f"files (Events group in the Properties panel), not here.\n"
        f'"""\n'
        f"\n"
    )


def _force_remove_readonly(func, path, _exc_info):
    """``shutil.rmtree`` ``onerror`` hook — chmod-ω files Windows
    has flagged read-only and retry. Without this, folders that
    contain anything checked out by tools that set the read-only
    bit (git-lfs pointers, some Windows installers) silently fail
    to delete; the user clicks Delete and nothing happens.
    """
    try:
        import os as _os
        import stat
        _os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        # Re-raise via shutil's normal path so the caller's
        # try/except still sees a failure rather than silently
        # leaving partial state.
        raise


def _read_image_size(path: Path) -> tuple[int, int] | None:
    """PIL is already a project dependency (CTkImage uses it under
    the hood) — leverage it for image dimension lookup. Returns
    ``None`` when the file isn't a valid image PIL can decode.
    """
    try:
        from PIL import Image
        with Image.open(path) as img:
            return (int(img.width), int(img.height))
    except Exception:
        return None


def _read_font_family(path: Path) -> str | None:
    """Read a TTF / OTF's family name from its metadata via PIL —
    same call ``app.core.fonts._read_ttf_family`` uses. Duplicated
    here to keep ``project_window`` independent of the font loader's
    cache logic.
    """
    try:
        from PIL import ImageFont
        font = ImageFont.truetype(str(path), 12)
        names = font.getname()
        if names and names[0]:
            return str(names[0])
    except Exception:
        pass
    return None
