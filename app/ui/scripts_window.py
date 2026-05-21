"""Scripts panel — per-page library `.py` files.

Shows the user's library scripts (helpers, api, sub-packages) that
live under ``<project>/assets/scripts/<active_page>/`` and are NOT
per-window behavior files. Lets the user add / rename / delete / open
those files without leaving the builder.

Mirrors ``HistoryWindow`` / ``VariablesWindow``: ``ScriptsPanel`` is
the embeddable ``CTkFrame``; ``ScriptsWindow`` is the floating
``ManagedToplevel`` wrapper opened by F6 / View → Scripts.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from app.core.logger import log_error
from app.core.settings import load_settings
from app.io.library_scripts import (
    LibraryEntry,
    create_library_script,
    create_library_subpackage,
    list_library_scripts,
    recycle_library_script,
    rename_library_script,
    script_absolute_path,
)
from app.core.script_paths import slugify_window_name
from app.io.scripts import launch_editor, resolve_project_root_for_editor
from app.ui import style
from app.ui.managed_window import ManagedToplevel
from app.ui.system_fonts import ui_font

if TYPE_CHECKING:
    from app.core.project import Project

BG = style.BG
PANEL_BG = style.PANEL_BG
TOOLBAR_BG = style.TOOLBAR_BG
TREE_BG = style.TREE_BG
TREE_FG = style.TREE_FG
TREE_SELECTED_BG = style.TREE_SELECTED_BG
TREE_HEADING_BG = style.TREE_HEADING_BG
TREE_HEADING_FG = style.TREE_HEADING_FG
EMPTY_FG = style.EMPTY_FG
SECONDARY_BG = style.SECONDARY_BG
SECONDARY_HOVER = style.SECONDARY_HOVER
DANGER_HOVER = style.DANGER_HOVER
BUTTON_RADIUS = style.BUTTON_RADIUS

DIALOG_W = 360
DIALOG_H = 440
TREE_ROW_HEIGHT = style.TREE_ROW_HEIGHT
TREE_FONT_SIZE = style.TREE_FONT_SIZE

EMPTY_TEXT = "No library scripts in this page yet — click + Add to create one"
EMPTY_NO_PROJECT = "Save the project first to add library scripts"

FOLDER_ICON = "📁"
FILE_ICON = "📄"
BEHAVIOR_ICON = "🪟"
BEHAVIOR_FG = "#e8b86d"


class ScriptsPanel(ctk.CTkFrame):
    """Embeddable list of library scripts for the active page."""

    def __init__(
        self,
        parent,
        project: "Project",
        path_provider: Callable[[], str | None],
    ):
        super().__init__(parent, fg_color=PANEL_BG, corner_radius=0, border_width=0)
        self.project = project
        self._path_provider = path_provider
        self._build()
        self._subscribe_events()
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.after(0, self.refresh)

    # ------------------------------------------------------------------
    # Event bus
    # ------------------------------------------------------------------
    _SUBSCRIBED_EVENTS = (
        "document_attached_scripts_changed",
        "document_added",
        "document_removed",
        "document_renamed",
        # Reverse direction: the Assets tree writes into
        # ``assets/scripts/`` too (new folder / .py, rename, move,
        # delete). Mirror those here so they show without a restart.
        # Our own publishes are filtered in ``_on_bus_event`` via the
        # ``_own_library_publish`` flag so the post-create selection
        # set by ``_create_script`` isn't wiped by an echo refresh.
        "library_scripts_changed",
    )

    def _subscribe_events(self) -> None:
        bus = getattr(self.project, "event_bus", None)
        if bus is None:
            return
        for evt in self._SUBSCRIBED_EVENTS:
            bus.subscribe(evt, self._on_bus_event)

    def _unsubscribe_events(self) -> None:
        bus = getattr(self.project, "event_bus", None)
        if bus is None:
            return
        for evt in self._SUBSCRIBED_EVENTS:
            bus.unsubscribe(evt, self._on_bus_event)

    def _on_bus_event(self, *_args, **_kwargs) -> None:
        """Single callback for every subscribed event — they all just
        refresh the tree. Coalesce via ``after_idle`` so a burst of
        document_* events during project load doesn't redraw N times.
        Cheap winfo_exists guard avoids scheduling on a torn-down panel
        when the bus fires between widget destroy and ``<Destroy>``
        bubbling up to ``_on_destroy``.
        """
        if getattr(self, "_own_library_publish", False):
            # Echo of our own ``library_scripts_changed`` publish — the
            # mutating handler already called ``self.refresh()`` (and may
            # have set a selection); skip the duplicate after_idle pass.
            return
        try:
            if not self.winfo_exists():
                return
            self.after_idle(self.refresh)
        except tk.TclError:
            pass

    def _on_destroy(self, event) -> None:
        # ``<Destroy>`` bubbles up from every descendant; only act when
        # the panel itself is going away. Unsubscribe early so any
        # event published mid-teardown can't re-enter the panel.
        if event.widget is self:
            self._unsubscribe_events()

    def _publish_library_changed(self) -> None:
        """Tell other panels the page's library scripts changed on disk.

        The Scripts panel refreshes itself directly after every mutation;
        this is purely a cross-panel signal so views that scan
        ``assets/scripts/`` (the Assets tree) don't stay stale until the
        next restart. Library scripts are loose files written straight to
        disk, so this intentionally does NOT mark the project dirty.
        """
        bus = getattr(self.project, "event_bus", None)
        if bus is None:
            return
        # Flag our own publish so the synchronous echo back into
        # ``_on_bus_event`` (we subscribe to this event for the reverse
        # direction) is ignored — we refresh directly right after.
        self._own_library_publish = True
        try:
            bus.publish("library_scripts_changed")
        except Exception:
            log_error("ScriptsPanel publish library_scripts_changed")
        finally:
            self._own_library_publish = False

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self._build_toolbar()
        self._build_tree()

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=TOOLBAR_BG, corner_radius=0, height=36)
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)
        ctk.CTkButton(
            bar, text="+ Add script", width=100, height=24,
            corner_radius=BUTTON_RADIUS,
            fg_color=SECONDARY_BG, hover_color=SECONDARY_HOVER,
            font=ui_font(11),
            command=self._on_add_file,
        ).pack(side="left", padx=(8, 4), pady=6)
        ctk.CTkButton(
            bar, text="+ Add folder", width=100, height=24,
            corner_radius=BUTTON_RADIUS,
            fg_color=SECONDARY_BG, hover_color=SECONDARY_HOVER,
            font=ui_font(11),
            command=self._on_add_folder,
        ).pack(side="left", padx=(0, 4), pady=6)

    def _build_tree(self) -> None:
        wrapper = ctk.CTkFrame(self, fg_color=TREE_BG, corner_radius=0)
        wrapper.pack(side="top", fill="both", expand=True)

        style_name = "Scripts.Treeview"
        ttk_style = ttk.Style(self)
        ttk_style.configure(
            style_name,
            background=TREE_BG,
            fieldbackground=TREE_BG,
            foreground=TREE_FG,
            rowheight=TREE_ROW_HEIGHT,
            borderwidth=0,
            font=ui_font(TREE_FONT_SIZE),
        )
        ttk_style.map(
            style_name,
            background=[("selected", TREE_SELECTED_BG)],
            foreground=[("selected", "#ffffff")],
        )
        ttk_style.configure(
            f"{style_name}.Heading",
            background=TREE_HEADING_BG,
            foreground=TREE_HEADING_FG,
            relief="flat",
            font=ui_font(TREE_FONT_SIZE),
        )
        ttk_style.map(
            f"{style_name}.Heading",
            background=[("active", TREE_HEADING_BG)],
        )

        self.tree = ttk.Treeview(
            wrapper,
            columns=("attached",),
            show="tree headings",
            style=style_name,
            selectmode="browse",
        )
        self.tree.heading("#0", text="Script")
        self.tree.heading("attached", text="Attached to")
        self.tree.column("#0", width=200, stretch=True, anchor="w")
        self.tree.column("attached", width=170, stretch=False, anchor="w")
        self.tree.tag_configure("empty", foreground=EMPTY_FG)
        self.tree.tag_configure("folder", foreground="#9cc7ff")
        self.tree.tag_configure("behavior", foreground=BEHAVIOR_FG)
        self.tree.tag_configure("drop_target", background="#1f3a26")
        self.tree.bind("<Double-1>", self._on_double_click, add="+")
        self.tree.bind("<Return>", self._on_double_click, add="+")
        self.tree.bind("<Button-1>", self._on_left_click, add="+")
        self.tree.bind("<B1-Motion>", self._on_drag_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self._on_drag_release, add="+")
        self.tree.bind("<Button-3>", self._on_right_click, add="+")
        self.tree.bind("<F2>", self._on_rename_shortcut, add="+")
        self.tree.bind("<Delete>", self._on_delete_shortcut, add="+")
        # Drag state — populated on press, consumed by motion + release.
        self._drag_iid: str | None = None
        self._drag_started = False
        self._drag_start_xy: tuple[int, int] = (0, 0)
        self._drop_highlight: str | None = None

        vsb = ctk.CTkScrollbar(
            wrapper, orientation="vertical",
            command=self.tree.yview,
            width=10, corner_radius=4,
            fg_color="transparent",
            button_color="#3a3a3a",
            button_hover_color="#4a4a4a",
        )
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    def _current_path(self) -> str | None:
        try:
            return self._path_provider()
        except Exception:
            return None

    def _window_names(self) -> list[str]:
        try:
            return [
                getattr(d, "name", "") or ""
                for d in (self.project.documents or [])
            ]
        except Exception:
            return []

    def refresh(self) -> None:
        # Defensive guard: the bus + after_idle scheduling can race with
        # the panel's destroy. Bail silently if the Treeview is gone.
        try:
            if not self.tree.winfo_exists():
                return
            for iid in self.tree.get_children(""):
                self.tree.delete(iid)
        except tk.TclError:
            return
        path = self._current_path()
        if not path:
            self.tree.insert(
                "", "end", iid="__empty__",
                text=EMPTY_NO_PROJECT, tags=("empty",),
                values=("",),
            )
            return
        entries = list_library_scripts(path, self._window_names())
        if not entries:
            self.tree.insert(
                "", "end", iid="__empty__",
                text=EMPTY_TEXT, tags=("empty",),
                values=("",),
            )
            return
        self._populate("", entries)

    def _populate(self, parent_iid: str, entries: list[LibraryEntry]) -> None:
        for entry in entries:
            attached_text = ""
            if entry.is_folder:
                tags: tuple[str, ...] = ("folder",)
                label = f"{FOLDER_ICON} {entry.name}"
            elif entry.is_behavior:
                tags = ("behavior",)
                label = f"{entry.name}  (window)"
                doc = self._document_for_behavior(entry.rel_path)
                if doc is not None:
                    attached_text = doc.name
            else:
                tags = ()
                label = entry.name
                names = self._documents_attached_to(entry.rel_path)
                attached_text = ", ".join(names)
            iid = self.tree.insert(
                parent_iid, "end",
                iid=entry.rel_path,
                text=f"  {label}",
                tags=tags,
                values=(attached_text,),
                open=True,
            )
            if entry.is_folder and entry.children:
                self._populate(iid, entry.children)

    # ------------------------------------------------------------------
    # Attachment helpers
    # ------------------------------------------------------------------
    def _documents(self) -> list:
        try:
            return list(self.project.documents or [])
        except Exception:
            return []

    def _document_for_behavior(self, rel_path: str):
        """``login.py`` -> the Document whose slug is ``login``. Returns
        ``None`` when no matching window exists for this stem (orphan
        behavior file, e.g. left behind after a window rename).
        """
        if "/" in rel_path or not rel_path.endswith(".py"):
            return None
        stem = rel_path[:-3]
        for doc in self._documents():
            if slugify_window_name(getattr(doc, "name", "") or "") == stem:
                return doc
        return None

    def _documents_attached_to(self, rel_path: str) -> list[str]:
        return [
            getattr(d, "name", "") or ""
            for d in self._documents()
            if rel_path in (getattr(d, "attached_scripts", []) or [])
        ]

    # ------------------------------------------------------------------
    # Toolbar actions
    # ------------------------------------------------------------------
    def _on_add_file(self) -> None:
        self._create_script(parent_folder="")

    def _on_add_folder(self) -> None:
        self._create_folder(parent_folder="")

    def _create_script(self, parent_folder: str) -> None:
        path = self._current_path()
        if not path:
            messagebox.showwarning(
                "Save first",
                "Save the project before adding library scripts.",
                parent=self,
            )
            return
        prompt = (
            f"New script in {parent_folder}/ (e.g. auth.py):"
            if parent_folder
            else "Filename (e.g. helpers.py or services/auth.py):"
        )
        name = simpledialog.askstring(
            "Add library script", prompt, parent=self,
        )
        if not name:
            return
        rel = f"{parent_folder}/{name}" if parent_folder else name
        result = create_library_script(path, rel, self._window_names())
        if result is None:
            messagebox.showerror(
                "Add failed",
                "Could not create the script.\n\n"
                "Possible reasons:\n"
                "• File already exists\n"
                "• Name clashes with a window's behavior file\n"
                "• Invalid path (absolute / .. traversal)",
                parent=self,
            )
            return
        self._publish_library_changed()
        self.refresh()
        try:
            self.tree.selection_set(result.relative_to(result.parent.parent).as_posix())
        except Exception:
            pass

    def _create_folder(self, parent_folder: str) -> None:
        path = self._current_path()
        if not path:
            messagebox.showwarning(
                "Save first",
                "Save the project before adding folders.",
                parent=self,
            )
            return
        prompt = (
            f"New subfolder in {parent_folder}/ (e.g. auth):"
            if parent_folder
            else "Folder name (e.g. services or data/models):"
        )
        name = simpledialog.askstring(
            "Add folder", prompt, parent=self,
        )
        if not name:
            return
        rel = f"{parent_folder}/{name}" if parent_folder else name
        result = create_library_subpackage(path, rel)
        if result is None:
            messagebox.showerror(
                "Add failed",
                "Could not create the folder.\n\n"
                "Possible reasons:\n"
                "• Folder already exists\n"
                "• Invalid path (absolute / .. traversal)",
                parent=self,
            )
            return
        self._publish_library_changed()
        self.refresh()

    # ------------------------------------------------------------------
    # Row actions
    # ------------------------------------------------------------------
    def _selected_rel_path(self) -> str | None:
        sel = self.tree.selection()
        if not sel:
            return None
        iid = sel[0]
        if iid.startswith("__"):
            return None
        return iid

    def _on_double_click(self, _event=None) -> None:
        rel = self._selected_rel_path()
        if not rel:
            return
        self._open_in_editor(rel)

    def _on_left_click(self, event) -> None:
        """Click on the ``Attached to`` column opens the per-script
        window picker. Clicks on the tree column record a drag-source
        candidate (consumed by ``_on_drag_motion`` once the user moves
        past a small threshold) and otherwise fall through to the
        Treeview's default row-selection behavior.
        """
        region = self.tree.identify_region(event.x, event.y)
        iid = self.tree.identify_row(event.y)
        if region == "cell" and self.tree.identify_column(event.x) == "#1":
            if not iid or iid.startswith("__"):
                return
            if self.tree.tag_has("folder", iid) or self.tree.tag_has("behavior", iid):
                return
            self._open_attached_popup(iid, event.x_root, event.y_root)
            return
        # Record a drag candidate for any draggable row on the tree
        # column. Behavior files are pinned to their structural window
        # slug and stay put. Folders ARE draggable — backend rename
        # supports moving them between parents.
        if iid and not iid.startswith("__") and not self.tree.tag_has("behavior", iid):
            self._drag_iid = iid
            self._drag_started = False
            self._drag_start_xy = (event.x, event.y)
        else:
            self._drag_iid = None

    # ------------------------------------------------------------------
    # Drag-and-drop
    # ------------------------------------------------------------------
    _DRAG_THRESHOLD_PX = 5

    def _on_drag_motion(self, event) -> None:
        if not self._drag_iid:
            return
        if not self._drag_started:
            dx = abs(event.x - self._drag_start_xy[0])
            dy = abs(event.y - self._drag_start_xy[1])
            if max(dx, dy) < self._DRAG_THRESHOLD_PX:
                return
            self._drag_started = True
            try:
                self.tree.configure(cursor="hand2")
            except tk.TclError:
                pass
        self._set_drop_highlight(self.tree.identify_row(event.y))

    def _on_drag_release(self, event) -> None:
        source = self._drag_iid
        started = self._drag_started
        self._drag_iid = None
        self._drag_started = False
        if not started or not source:
            return
        target = self.tree.identify_row(event.y)
        self._clear_drop_highlight()
        try:
            self.tree.configure(cursor="")
        except tk.TclError:
            pass
        self._drop_on(source, target)

    def _set_drop_highlight(self, iid: str | None) -> None:
        if iid == self._drop_highlight:
            return
        self._clear_drop_highlight()
        if not iid or iid.startswith("__"):
            return
        if not self.tree.tag_has("folder", iid):
            return
        if not self._is_valid_drop(self._drag_iid, iid):
            return
        try:
            tags = tuple(self.tree.item(iid, "tags")) + ("drop_target",)
            self.tree.item(iid, tags=tags)
            self._drop_highlight = iid
        except tk.TclError:
            self._drop_highlight = None

    def _clear_drop_highlight(self) -> None:
        iid = self._drop_highlight
        self._drop_highlight = None
        if not iid:
            return
        try:
            tags = tuple(t for t in self.tree.item(iid, "tags") if t != "drop_target")
            self.tree.item(iid, tags=tags)
        except tk.TclError:
            pass

    def _is_valid_drop(self, source: str | None, target: str) -> bool:
        if not source or not target:
            return False
        if source == target:
            return False
        # Dropping into the current parent is a no-op.
        current_parent = source.rsplit("/", 1)[0] if "/" in source else ""
        if target == current_parent:
            return False
        # Folder into itself or its descendant — illegal.
        if self.tree.tag_has("folder", source):
            if target == source or target.startswith(source + "/"):
                return False
        return True

    def _drop_on(self, source: str, target: str | None) -> None:
        """Move ``source`` into folder ``target``. ``target=None`` /
        empty / non-folder → cancel.
        """
        if not target or not self.tree.tag_has("folder", target):
            return
        if not self._is_valid_drop(source, target):
            return
        basename = source.rsplit("/", 1)[-1]
        new_rel = f"{target}/{basename}"
        self._move_path(source, new_rel)

    def _move_path(self, source: str, new_rel: str) -> None:
        path = self._current_path()
        if not path:
            return
        is_folder = bool(self.tree.tag_has("folder", source))
        result = rename_library_script(
            path, source, new_rel, self._window_names(),
        )
        if result is None:
            messagebox.showerror(
                "Move failed",
                "Could not move.\n\n"
                "Possible reasons:\n"
                "• Destination already contains a file/folder with this name\n"
                "• Name clashes with a window's behavior file",
                parent=self,
            )
            return
        if not is_folder and not new_rel.endswith(".py"):
            new_rel = new_rel + ".py"
        self._sweep_attached_paths(source, new_rel, is_folder)
        self._publish_library_changed()
        self.refresh()

    def _open_attached_popup(
        self, rel: str, screen_x: int, screen_y: int,
    ) -> None:
        docs = self._documents()
        if not docs:
            return
        menu = tk.Menu(
            self, tearoff=0,
            bg="#2d2d30", fg="#cccccc",
            activebackground=TREE_SELECTED_BG,
            activeforeground="#ffffff",
            disabledforeground="#888888",
            selectcolor="#cccccc",
            bd=0,
        )
        # Hold variable refs on the panel — tk.Menu doesn't own them
        # and they'd otherwise be GC'd before the user clicks.
        self._popup_vars: list[tk.BooleanVar] = []
        for doc in docs:
            attached_now = rel in (
                getattr(doc, "attached_scripts", []) or []
            )
            v = tk.BooleanVar(value=attached_now)
            self._popup_vars.append(v)
            menu.add_checkbutton(
                label=f"  {getattr(doc, 'name', '') or '(unnamed)'}",
                variable=v,
                onvalue=True, offvalue=False,
                command=lambda d=doc, vv=v: self._toggle_attachment(
                    d, rel, vv.get(),
                ),
            )
        try:
            menu.tk_popup(screen_x, screen_y)
        finally:
            menu.grab_release()

    def _toggle_attachment(self, doc, rel: str, attached: bool) -> None:
        current = list(getattr(doc, "attached_scripts", []) or [])
        if attached and rel not in current:
            current.append(rel)
        elif not attached and rel in current:
            current.remove(rel)
        else:
            return
        doc.attached_scripts = current
        try:
            self.project.event_bus.publish(
                "document_attached_scripts_changed", doc.id,
            )
            self.project.event_bus.publish("dirty_changed", True)
        except Exception:
            log_error("ScriptsPanel publish attached_scripts")
        self.refresh()

    def _on_rename_shortcut(self, _event=None) -> None:
        sel = self.tree.selection()
        if sel and self.tree.tag_has("behavior", sel[0]):
            return
        self._rename_selected()

    def _on_delete_shortcut(self, _event=None) -> None:
        sel = self.tree.selection()
        if sel and self.tree.tag_has("behavior", sel[0]):
            return
        self._delete_selected()

    def _on_right_click(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        menu = tk.Menu(self, **_menu_style())
        if not iid or iid.startswith("__"):
            # Empty area / placeholder row — offer root-level creation.
            menu.add_command(label="New script…",
                             command=lambda: self._create_script(""))
            menu.add_command(label="New folder…",
                             command=lambda: self._create_folder(""))
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
            return
        self.tree.selection_set(iid)
        is_folder = bool(self.tree.tag_has("folder", iid))
        is_behavior = bool(self.tree.tag_has("behavior", iid))
        if is_folder:
            menu.add_command(
                label="New script inside…",
                command=lambda: self._create_script(iid),
            )
            menu.add_command(
                label="New subfolder…",
                command=lambda: self._create_folder(iid),
            )
            menu.add_separator()
        else:
            menu.add_command(label="Open in editor",
                             command=self._open_selected_in_editor)
            if not is_behavior:
                attach_menu = self._build_attach_to_menu(iid)
                if attach_menu is not None:
                    menu.add_cascade(label="Attach to", menu=attach_menu)
        # Behavior files are managed via the window's chrome (rename =
        # window rename, delete = window delete). The icon + ``(window)``
        # suffix already signal this; we just skip the rename / delete
        # rows here to avoid orphaning the binding.
        if not is_behavior:
            move_menu = self._build_move_to_menu(iid)
            if move_menu is not None:
                menu.add_cascade(label="Move to", menu=move_menu)
            menu.add_separator()
            menu.add_command(label="Rename…", command=self._rename_selected)
            menu.add_command(label="Delete", command=self._delete_selected)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _build_attach_to_menu(self, rel: str) -> "tk.Menu | None":
        """Cascade submenu listing every document as a toggleable
        checkbox row. Mirrors ``_open_attached_popup`` but stays nested
        inside the right-click menu instead of opening as a separate
        popup. Returns ``None`` when no documents exist.
        """
        docs = self._documents()
        if not docs:
            return None
        sub = tk.Menu(
            self, tearoff=0,
            bg="#2d2d30", fg="#cccccc",
            activebackground=TREE_SELECTED_BG,
            activeforeground="#ffffff",
            disabledforeground="#888888",
            selectcolor="#cccccc",
            bd=0,
        )
        # Keep variable refs alive past this builder call — tk.Menu
        # doesn't own them and Python would otherwise GC them while
        # the cascade is still on screen.
        self._cascade_vars: list[tk.BooleanVar] = []
        for doc in docs:
            attached_now = rel in (
                getattr(doc, "attached_scripts", []) or []
            )
            v = tk.BooleanVar(value=attached_now)
            self._cascade_vars.append(v)
            sub.add_checkbutton(
                label=f"  {getattr(doc, 'name', '') or '(unnamed)'}",
                variable=v,
                onvalue=True, offvalue=False,
                command=lambda d=doc, vv=v: self._toggle_attachment(
                    d, rel, vv.get(),
                ),
            )
        return sub

    def _build_move_to_menu(self, source: str) -> "tk.Menu | None":
        """Cascade listing every folder + ``(root)`` as a move target.
        Returns ``None`` when nothing valid exists, so the caller can
        skip adding the cascade entirely.
        """
        path = self._current_path()
        if not path:
            return None
        entries = list_library_scripts(path, self._window_names())
        folders: list[str] = []

        def walk(items: list[LibraryEntry]) -> None:
            for e in items:
                if e.is_folder:
                    folders.append(e.rel_path)
                    walk(e.children)

        walk(entries)
        sub = tk.Menu(self, **_menu_style())
        current_parent = source.rsplit("/", 1)[0] if "/" in source else ""
        added = 0
        if current_parent:
            basename = source.rsplit("/", 1)[-1]
            sub.add_command(
                label="(root)",
                command=lambda b=basename: self._move_path(source, b),
            )
            added += 1
        valid_folders = [f for f in folders if self._is_valid_drop(source, f)]
        if valid_folders and added:
            sub.add_separator()
        for folder in valid_folders:
            basename = source.rsplit("/", 1)[-1]
            new_rel = f"{folder}/{basename}"
            sub.add_command(
                label=folder,
                command=lambda nr=new_rel: self._move_path(source, nr),
            )
            added += 1
        if added == 0:
            return None
        return sub

    def _open_selected_in_editor(self) -> None:
        rel = self._selected_rel_path()
        if rel:
            self._open_in_editor(rel)

    def _open_in_editor(self, rel: str) -> None:
        path = self._current_path()
        if not path:
            return
        abs_path = script_absolute_path(path, rel)
        if abs_path is None:
            return
        try:
            editor_command = load_settings().get("editor_command")
            launch_editor(
                abs_path,
                editor_command=editor_command,
                project_root=resolve_project_root_for_editor(self.project),
            )
        except OSError:
            log_error("ScriptsPanel open_in_editor")

    def _rename_selected(self) -> None:
        rel = self._selected_rel_path()
        if not rel:
            return
        path = self._current_path()
        if not path:
            return
        is_folder = bool(self.tree.tag_has("folder", rel))
        old_name = rel.rsplit("/", 1)[-1]
        parent_dir = rel.rsplit("/", 1)[0] if "/" in rel else ""
        new_name = simpledialog.askstring(
            "Rename",
            "New name:",
            initialvalue=old_name,
            parent=self,
        )
        if not new_name or new_name == old_name:
            return
        new_rel = (
            f"{parent_dir}/{new_name}" if parent_dir else new_name
        )
        result = rename_library_script(
            path, rel, new_rel, self._window_names(),
        )
        if result is None:
            messagebox.showerror(
                "Rename failed",
                "Could not rename.\n\n"
                "Possible reasons:\n"
                "• Target already exists\n"
                "• Name clashes with a window's behavior file\n"
                "• Invalid name",
                parent=self,
            )
            return
        # Backend auto-appends ``.py`` for files; mirror that here so
        # the sweep finds the right new path. Folders keep the raw name.
        if not is_folder and not new_rel.endswith(".py"):
            new_rel = new_rel + ".py"
        self._sweep_attached_paths(rel, new_rel, is_folder)
        self._publish_library_changed()
        self.refresh()

    def _delete_selected(self) -> None:
        rel = self._selected_rel_path()
        if not rel:
            return
        path = self._current_path()
        if not path:
            return
        is_folder = bool(self.tree.tag_has("folder", rel))
        if not messagebox.askyesno(
            "Delete",
            f"Send '{rel}' to the recycle bin?",
            parent=self,
        ):
            return
        ok = recycle_library_script(path, rel)
        if not ok:
            messagebox.showerror(
                "Delete failed",
                "Could not send the file to the recycle bin.",
                parent=self,
            )
            return
        self._sweep_attached_paths(rel, None, is_folder)
        self._publish_library_changed()
        self.refresh()

    def _sweep_attached_paths(
        self, old_rel: str, new_rel: str | None, is_folder: bool,
    ) -> None:
        """Apply a path-as-identity sweep across every document.

        ``new_rel=None`` deletes matching entries (recycle flow);
        any string remaps them. For folders, entries under the
        old prefix get the prefix swapped (rename) or removed (delete).
        """
        prefix = old_rel + "/"
        changed_docs = []
        for doc in self._documents():
            entries = list(getattr(doc, "attached_scripts", []) or [])
            updated: list[str] = []
            doc_changed = False
            for entry in entries:
                matches_self = entry == old_rel
                matches_child = is_folder and entry.startswith(prefix)
                if matches_self or matches_child:
                    if new_rel is None:
                        doc_changed = True
                        continue
                    if matches_child:
                        suffix = entry[len(old_rel):]
                        updated.append(new_rel + suffix)
                    else:
                        updated.append(new_rel)
                    doc_changed = True
                else:
                    updated.append(entry)
            if doc_changed:
                doc.attached_scripts = updated
                changed_docs.append(doc)
        if not changed_docs:
            return
        bus = getattr(self.project, "event_bus", None)
        if bus is None:
            return
        for doc in changed_docs:
            try:
                bus.publish("document_attached_scripts_changed", doc.id)
            except Exception:
                log_error("ScriptsPanel sweep publish")
        try:
            bus.publish("dirty_changed", True)
        except Exception:
            log_error("ScriptsPanel sweep dirty publish")


def _menu_style() -> dict:
    """Match the dark popup menu styling used elsewhere — keeps the
    right-click menu visually consistent with the toolbar / file menu.
    """
    return {
        "bg": "#2d2d30",
        "fg": "#cccccc",
        "activebackground": TREE_SELECTED_BG,
        "activeforeground": "#ffffff",
        "bd": 0,
        "tearoff": 0,
        "font": ui_font(11),
    }


class ScriptsWindow(ManagedToplevel):
    """Floating Scripts panel (F6)."""

    window_key = "scripts"
    window_title = "Scripts"
    default_size = (DIALOG_W, DIALOG_H)
    min_size = (260, 240)
    fg_color = BG

    def __init__(
        self,
        parent,
        project: "Project",
        path_provider: Callable[[], str | None],
        on_close: Callable[[], None] | None = None,
    ):
        self.project = project
        self._path_provider = path_provider
        super().__init__(parent)
        self.set_on_close(on_close)

    def build_content(self) -> ctk.CTkFrame:
        self.panel = ScriptsPanel(self, self.project, self._path_provider)
        # Auto-refresh whenever this window regains focus — picks up
        # any files created / renamed / deleted via an external editor
        # (VS Code Save As, Notepad++, file explorer, etc.) without a
        # dedicated refresh button.
        self.bind("<FocusIn>", self._on_focus_in, add="+")
        return self.panel

    def _on_focus_in(self, event) -> None:
        # FocusIn fires for every descendant getting focus too — only
        # refresh when the toplevel itself takes focus (cheap guard).
        if event.widget is self:
            try:
                self.panel.refresh()
            except (AttributeError, tk.TclError):
                pass

    def default_offset(self, parent) -> tuple[int, int]:
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            return (px + pw - self.default_size[0] - 30, py + 200)
        except tk.TclError:
            return (140, 140)

    def refresh(self) -> None:
        """Triggered by MainWindow on page switch."""
        try:
            self.panel.refresh()
        except (AttributeError, tk.TclError):
            pass

    def update_title(self, page_name: str | None) -> None:
        """Append the active page name to the title bar."""
        if page_name:
            try:
                self.title(f"Scripts — {page_name}")
            except tk.TclError:
                pass
