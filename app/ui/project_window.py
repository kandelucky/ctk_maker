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
- Right-click on a file → Reveal in Explorer, Reimport, Remove.
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
    ):
        super().__init__(
            parent, fg_color=PANEL_BG, corner_radius=0, border_width=0,
        )
        self.project = project
        self.path_provider = path_provider

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

        self._build_header()
        self._build_tree()
        self._build_info_panel()
        self._build_footer()

        # Refresh whenever project name / save target / dirty state
        # changes — keeps the header text current after Save As, New
        # Project, etc.
        bus = project.event_bus
        for evt in ("project_renamed", "dirty_changed"):
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
        # Compact one-row header: bold name + dim path + "+" menu
        # button. The plus replaces the four-button footer — clicking
        # it pops a menu (Image / Font / Folder / Text File) so the
        # tree gets the freed-up vertical space and the panel reads
        # cleaner on narrow docks.
        body = tk.Frame(self, bg=PANEL_BG)
        body.pack(fill="x", padx=10, pady=(6, 4))

        # ``+`` lives on the right; pack it FIRST so left-side labels
        # get whatever horizontal space remains and don't push the
        # button off the panel on a long path.
        self._add_btn = ctk.CTkButton(
            body, text="+", width=24, height=22,
            corner_radius=4, font=("Segoe UI", 12, "bold"),
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_show_add_menu,
        )
        self._add_btn.pack(side="right")

        tk.Label(
            body, textvariable=self._name_var,
            bg=PANEL_BG, fg=HEADER_FG,
            font=("Segoe UI", 10, "bold"), anchor="w",
        ).pack(side="left")
        tk.Label(
            body, text="·",
            bg=PANEL_BG, fg=DIM_FG,
            font=("Segoe UI", 10),
        ).pack(side="left", padx=6)
        tk.Label(
            body, textvariable=self._path_var,
            bg=PANEL_BG, fg=DIM_FG,
            font=("Segoe UI", 9), anchor="w",
        ).pack(side="left", fill="x", expand=True)

    def _on_show_add_menu(self) -> None:
        """Pop the + menu anchored under the button. Mirrors the
        old four-button footer one-for-one — no behaviour change,
        just a UI consolidation.
        """
        menu = tk.Menu(
            self, tearoff=0,
            bg="#2d2d30", fg=HEADER_FG,
            activebackground="#094771", activeforeground="#ffffff",
            relief="flat", bd=0, font=("Segoe UI", 10),
        )
        menu.add_command(label="Image...", command=self._on_add_image)
        menu.add_command(label="Font...", command=self._on_add_font)
        menu.add_separator()
        menu.add_command(label="Folder", command=self._on_new_folder)
        menu.add_command(label="Text File (.md)", command=self._on_new_text_file)
        menu.add_command(label="Python File (.py)", command=self._on_new_python_file)
        try:
            x = self._add_btn.winfo_rootx()
            y = self._add_btn.winfo_rooty() + self._add_btn.winfo_height()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

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
        """
        iid = self._tree.identify_row(event.y)
        if not iid:
            self._drag_state = None
            return
        # Defer the snapshot to after Tk's selection handler fires —
        # by-press selection gets included.
        self.after_idle(lambda: self._stamp_drag(event, iid))

    def _stamp_drag(self, event, iid: str) -> None:
        sel = self._tree.selection()
        # Only drag if the press landed on a row that's now selected.
        # ``identify_row`` may return iid even if the user just
        # clicked an inert region — guard against dragging "nothing".
        if iid not in sel:
            self._drag_state = None
            return
        self._drag_state = {
            "start_y": event.y, "start_x": event.x,
            "items": list(sel), "active": False,
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
            # Right-clicked on the empty area below all rows — only
            # creation actions make sense. Same set as the header
            # "+" menu: import + create-new.
            menu.add_command(
                label="Import Image...",
                command=self._on_add_image,
            )
            menu.add_command(
                label="Import Font...",
                command=self._on_add_font,
            )
            menu.add_separator()
            menu.add_command(
                label="New Folder...",
                command=self._on_new_folder,
            )
            menu.add_command(
                label="New Text File...",
                command=self._on_new_text_file,
            )
            menu.add_command(
                label="New Python File...",
                command=self._on_new_python_file,
            )
        else:
            _, kind = meta
            if kind == "folder":
                menu.add_command(
                    label="Reveal in Explorer",
                    command=self._on_context_reveal,
                )
                menu.add_separator()
                # Imports route into the right-clicked folder thanks
                # to ``_resolve_target_dir`` (selected folder wins).
                menu.add_command(
                    label="Import Image here...",
                    command=self._on_add_image,
                )
                menu.add_command(
                    label="Import Font here...",
                    command=self._on_add_font,
                )
                menu.add_separator()
                menu.add_command(
                    label="New Subfolder...",
                    command=self._on_new_folder,
                )
                menu.add_command(
                    label="New Text File...",
                    command=self._on_new_text_file,
                )
                menu.add_command(
                    label="New Python File...",
                    command=self._on_new_python_file,
                )
                menu.add_separator()
                menu.add_command(
                    label="Rename...",
                    command=self._on_rename,
                )
                menu.add_command(
                    label="Delete folder...",
                    command=self._on_delete_folder,
                )
            else:
                menu.add_command(
                    label="Open",
                    command=self._on_context_open,
                )
                menu.add_command(
                    label="Reveal in Explorer",
                    command=self._on_context_reveal,
                )
                menu.add_command(
                    label="Reimport...",
                    command=self._on_context_reimport,
                )
                menu.add_separator()
                menu.add_command(
                    label="Rename...",
                    command=self._on_rename,
                )
                menu.add_command(
                    label="Remove from project...",
                    command=self._on_context_remove,
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

    def _on_context_remove(self) -> None:
        meta = self._selected_meta()
        if meta is None:
            return
        file_path, kind = meta
        self._remove_asset(file_path, kind)

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

    def _open_with_os(self, file_path: Path) -> None:
        """Hand a file off to the OS default application — image
        viewer for .png, default font preview for .ttf, the user's
        preferred Markdown editor for .md, etc. Falls back to a
        Reveal-in-Explorer when the OS refuses (no association set).
        """
        if not file_path.exists():
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(file_path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(file_path)])
            else:
                subprocess.Popen(["xdg-open", str(file_path)])
        except OSError:
            log_error("open with os")
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
        self._create_text_file(
            kind="code",
            default_name="script",
            allowed_exts=(".py",),
            default_ext=".py",
            initial_content_for=lambda stem: (
                f'"""{stem}.py — module description here."""\n\n'
            ),
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
        self.refresh()
        self._open_with_os(new_file)

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
            shutil.rmtree(folder)
        except OSError:
            log_error("delete folder rmtree")
            messagebox.showerror(
                "Delete failed",
                f"Couldn't delete:\n{folder}",
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
        # Drop a matching system_fonts entry — that list pairs each
        # name with a file in assets/fonts/ in the common case, and a
        # bare reference reads as broken once the file is gone.
        if kind == "fonts":
            family = _read_font_family(file_path)
            if family and family in self.project.system_fonts:
                self.project.system_fonts = [
                    f for f in self.project.system_fonts if f != family
                ]
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
                (e for e in entries if e.is_file()),
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
                iid = self._tree.insert(
                    parent_iid, "end", text=f"  {f.name}",
                    image=self._kind_icons.get(kind, self._kind_icons.get("other", "")),
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
        }
        for kind, icon_name in kind_to_icon_name.items():
            try:
                img = load_tk_icon(icon_name, size=14, color="#cccccc")
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
        self.panel = ProjectPanel(self, project, path_provider)
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
