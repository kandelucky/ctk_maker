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
from app.ui.managed_window import ManagedToplevel
from app.ui.system_fonts import ui_font

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

        # Helper sidecars — each takes ``self`` (the panel) and
        # reads/writes state through it. Drag/menu/pages/files/tree
        # surfaces live in app/ui/project_panel_*.py.
        from app.ui.project_panel_drag import ProjectPanelDragDrop
        from app.ui.project_panel_files import ProjectPanelFiles
        from app.ui.project_panel_menu import ProjectPanelMenu
        from app.ui.project_panel_pages import ProjectPanelPages
        from app.ui.project_panel_tree import ProjectPanelTree
        self.tree = ProjectPanelTree(self)
        self.drag = ProjectPanelDragDrop(self)
        self.menu = ProjectPanelMenu(self)
        self.pages = ProjectPanelPages(self)
        self.files = ProjectPanelFiles(self)

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

    # ------- pass-through shims — kept so the right-click menu (which
    # builds its command targets from ``panel._on_*``) doesn't need to
    # learn the new sidecar shape on every entry.
    # ------------------------------------------------------------------
    def _on_new_folder(self) -> None:
        self.files.on_new_folder()

    def _on_rename(self) -> None:
        self.files.on_rename()

    def _on_delete_folder(self) -> None:
        self.files.on_delete_folder()

    def _on_new_page(self) -> None:
        self.pages.on_new_page()

    def _on_context_switch_page(self) -> None:
        self.pages.on_context_switch_page()

    def _on_context_duplicate_page(self) -> None:
        self.pages.on_context_duplicate_page()

    def _on_context_rename_page(self) -> None:
        self.pages.on_context_rename_page()

    def _on_context_delete_page(self) -> None:
        self.pages.on_context_delete_page()

    def _resolve_pages_folder_for_meta(self) -> Path | None:
        return self.pages.resolve_pages_folder_for_meta()

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
            self.tree.populate_tree(p)
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
        # Mirrors PropertiesPanel's chrome shape so the docked
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
            font=ui_font(11, "bold"),
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
            font=ui_font(12, "bold"),
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
            font=ui_font(9), anchor="w",
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
            relief="flat", bd=0, font=ui_font(10),
        )
        self._menu_command(menu, "Folder", "folder", self.files.on_new_folder)
        menu.add_separator()
        self._menu_command(
            menu, "Lucide Icon...", "layout-list", self._on_add_lucide_icon,
        )
        self._menu_command(menu, "Image...", "image", self._on_add_image)
        self._menu_command(menu, "Font...", "type", self._on_add_font)
        menu.add_separator()
        self._menu_command(
            menu, "Python File (.py)", "file-code",
            self.files.on_new_python_file,
        )
        self._menu_command(
            menu, "Text File (.md)", "file-text", self.files.on_new_text_file,
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
            relief="flat", bd=0, font=ui_font(10),
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
            self.files.on_new_python_file,
        )
        self._menu_command(
            sub, "Text File (.md)", "file-text",
            self.files.on_new_text_file,
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
            borderwidth=0, font=ui_font(10),
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
        self._tree.bind("<Button-3>", self.menu.on_tree_right_click)
        self._tree.bind("<Double-Button-1>", self._on_tree_double_click)
        self._tree.bind("<<TreeviewOpen>>", self.tree.on_folder_toggle, add="+")
        self._tree.bind("<<TreeviewClose>>", self.tree.on_folder_toggle, add="+")
        # Drag-and-drop within the tree to move files / folders
        # between subfolders. ``ButtonPress`` records the start
        # state; motion past the threshold flips into drag mode;
        # release runs the move when the target is a folder.
        self._tree.bind("<ButtonPress-1>", self.drag.on_tree_press)
        self._tree.bind("<B1-Motion>", self.drag.on_tree_drag)
        self._tree.bind("<ButtonRelease-1>", self.drag.on_tree_release)
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
            font=ui_font(9), justify="left", anchor="nw",
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
        self.tree.refresh_info_panel()

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
        self.menu.open_with_os(file_path)
        # Returning ``"break"`` would prevent Tk's own handler from
        # firing too — but on file rows there's nothing to break, so
        # we leave it alone.




    def _selected_meta(self) -> tuple[Path, str] | None:
        sel = self._tree.selection()
        if not sel:
            return None
        return self._iid_meta.get(sel[0])

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

class ProjectWindow(ManagedToplevel):
    """Floating wrapper around ``ProjectPanel`` (opened by F10)."""

    window_key = "project"
    window_title = "Assets"
    default_size = (DIALOG_W, DIALOG_H)
    min_size = (260, 320)
    fg_color = BG
    panel_padding = (6, 6)

    def __init__(
        self,
        parent,
        project: "Project",
        path_provider: Callable[[], str | None],
        on_close: Callable[[], None] | None = None,
        on_switch_page: Callable[[str], bool] | None = None,
        on_active_page_path_changed: Callable[[str], None] | None = None,
    ):
        self._project = project
        self._path_provider = path_provider
        self._on_switch_page = on_switch_page
        self._on_active_page_path_changed = on_active_page_path_changed
        super().__init__(parent)
        self.set_on_close(on_close)

    def default_offset(self, parent) -> tuple[int, int]:
        try:
            parent.update_idletasks()
            return (
                parent.winfo_rootx() + 60,
                parent.winfo_rooty() + 80,
            )
        except tk.TclError:
            return (100, 100)

    def build_content(self) -> ctk.CTkFrame:
        self.panel = ProjectPanel(
            self, self._project, self._path_provider,
            on_switch_page=self._on_switch_page,
            on_active_page_path_changed=self._on_active_page_path_changed,
        )
        return self.panel


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
