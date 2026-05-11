"""Project-scoped image picker.

The Image widget no longer accepts arbitrary on-disk paths — every
image must live inside ``<project>/assets/images/``. This dialog
lets the user either pick an already-imported image or import a
fresh one (file picker → SHA-deduped copy into the project's assets
folder, then immediately picked).

Returns the absolute path of the picked image when the user clicks
OK / double-clicks, or ``None`` on Cancel. Caller writes the path
into the node's ``image`` property; the save layer converts it to
an ``asset:images/<name>`` token automatically.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from PIL import ImageTk

import customtkinter as ctk

from app.core.assets import copy_to_assets, resolve_asset_token
from app.core.logger import log_error
from app.core.paths import ASSETS_DIR_NAME
from app.ui import style
from app.ui.icons import load_tk_icon
from app.ui.managed_window import ManagedToplevel
from app.ui.system_fonts import ui_font

HELP_TEXT = (
    "Image widgets only accept files that live inside the\n"
    "project's assets/images/ folder.\n\n"
    "• + Import — copy a file from anywhere on disk into\n"
    "    the project (deduped by content; safe to re-import\n"
    "    the same file).\n"
    "• Pick a row — use an image that's already in the\n"
    "    project. Saved as an asset:images/<name> token so\n"
    "    the .ctkproj stays portable across machines."
)

BG = style.BG
PANEL_BG = style.PANEL_BG
HEADER_BG = style.HEADER_BG
HEADER_FG = style.TREE_FG
DIM_FG = "#888888"  # local — slightly lighter than style.EMPTY_FG
ROW_SELECTED = style.TREE_SELECTED_BG
DIVIDER = style.BORDER

DIALOG_W = 480
DIALOG_H = 480
THUMB = 40

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico"}


class ImagePickerDialog(ManagedToplevel):
    window_title = "Select image"
    default_size = (DIALOG_W, DIALOG_H)
    min_size = (DIALOG_W, DIALOG_H)
    fg_color = BG
    panel_padding = (0, 0)
    modal = True
    window_resizable = (False, False)

    def __init__(self, parent, project_file: str, event_bus=None):
        self.project_file = project_file
        self._event_bus = event_bus
        self.result: str | None = None
        self._selected_path: Path | None = None
        self._row_widgets: dict[str, dict] = {}
        self._thumb_cache: dict[str, ImageTk.PhotoImage] = {}
        self._tip_window: tk.Toplevel | None = None
        super().__init__(parent)
        self.bind("<Return>", lambda _e: self._on_ok())
        # Defer the first list build until the CTkScrollableFrame is
        # realised — packing into an unmapped scrollable canvas can
        # leave children invisible until the next layout pass.
        self.after_idle(self._refresh)

    def default_offset(self, parent) -> tuple[int, int]:
        try:
            parent.update_idletasks()
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            w, h = self.default_size
            return (
                max(0, px + (pw - w) // 2),
                max(0, py + (ph - h) // 2),
            )
        except tk.TclError:
            return (100, 100)

    def build_content(self) -> ctk.CTkFrame:
        container = ctk.CTkFrame(self, fg_color="transparent")
        self._build_header(container)
        self._build_list(container)
        self._build_footer(container)
        return container

    def _build_header(self, parent) -> None:
        bar = tk.Frame(parent, bg=HEADER_BG)
        bar.pack(fill="x")
        style.primary_button(
            bar, "+ Import image...",
            command=self._on_import, width=140,
        ).pack(side="left", padx=(10, 4), pady=10)
        style.secondary_button(
            bar, "+ Lucide icon...",
            command=self._on_pick_lucide, width=140,
        ).pack(side="left", padx=(0, 4), pady=10)

        # Hover-help icon, pinned to the right edge of the bar.
        # tk.Label needs a tk.PhotoImage; CTkImage from load_icon()
        # doesn't render on a tk widget.
        help_img = load_tk_icon("circle-help", size=20, color="#aaaaaa")
        self._help_lbl = tk.Label(
            bar, bg=HEADER_BG, image=help_img if help_img else "",
            text="" if help_img else "?", fg=HEADER_FG,
            font=ui_font(12, "bold"), cursor="hand2",
        )
        self._help_lbl.image = help_img  # type: ignore[attr-defined]
        self._help_lbl.pack(side="right", padx=14, pady=8)
        self._help_lbl.bind("<Enter>", self._show_help)
        self._help_lbl.bind("<Leave>", self._hide_help)
        self._help_lbl.bind("<Button-1>", self._show_help)

    def _build_list(self, parent) -> None:
        wrap = ctk.CTkScrollableFrame(
            parent, fg_color=PANEL_BG, corner_radius=0,
        )
        wrap.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        self._list_wrap = wrap

    def _build_footer(self, parent) -> None:
        foot = tk.Frame(parent, bg=BG)
        foot.pack(fill="x", padx=10, pady=(4, 10))
        self._ok_btn = style.primary_button(
            foot, "OK", command=self._on_ok, width=90,
        )
        self._ok_btn.configure(state="disabled")
        self._ok_btn.pack(side="right")
        style.secondary_button(
            foot, "Cancel", command=self._on_cancel, width=90,
        ).pack(side="right", padx=(0, 8))

    # ------- list population -------

    def _images_dir(self) -> Path:
        from app.core.assets import project_assets_dir
        a = project_assets_dir(self.project_file)
        if a is not None:
            return a / "images"
        return Path(self.project_file).parent / ASSETS_DIR_NAME / "images"

    def _list_images(self) -> list[Path]:
        # Recursive scan over the whole ``assets/`` folder so images
        # the user reorganised into custom subfolders (e.g.
        # ``assets/icons/``) still surface in the picker.
        from app.core.assets import project_assets_dir
        a_dir = project_assets_dir(self.project_file)
        if a_dir is None:
            a_dir = Path(self.project_file).parent / ASSETS_DIR_NAME
        if not a_dir.exists():
            return []
        return sorted(
            (p for p in a_dir.rglob("*")
             if p.is_file() and p.suffix.lower() in IMAGE_EXTS),
            key=lambda p: p.name.lower(),
        )

    def _refresh(self, select: Path | None = None) -> None:
        # Drop existing row frames (cheap — list rebuilt on every
        # import / refresh).
        for child in list(self._list_wrap.winfo_children()):
            try:
                child.destroy()
            except tk.TclError:
                pass
        self._row_widgets.clear()

        images = self._list_images()
        if not images:
            ctk.CTkLabel(
                self._list_wrap,
                text="No images yet. Click + Import to add one.",
                font=ui_font(10), text_color=DIM_FG,
            ).pack(pady=40)
            self._set_selected(None)
            return

        for path in images:
            self._build_row(path)

        if select is not None:
            self._set_selected(select)
        else:
            self._set_selected(None)

    def _build_row(self, path: Path) -> None:
        row = tk.Frame(self._list_wrap, bg=PANEL_BG, cursor="hand2")
        row.pack(fill="x", padx=2, pady=1)

        thumb = self._thumb_for(path)
        thumb_lbl = tk.Label(
            row, bg=PANEL_BG,
            image=thumb if thumb else "",
            text="" if thumb else "?",
            fg=HEADER_FG, width=THUMB, height=THUMB,
        )
        thumb_lbl.pack(side="left", padx=8, pady=4)

        name_lbl = tk.Label(
            row, text=path.name, bg=PANEL_BG, fg=HEADER_FG,
            font=ui_font(11), anchor="w",
        )
        name_lbl.pack(side="left", fill="x", expand=True, padx=4)

        for w in (row, thumb_lbl, name_lbl):
            w.bind("<Button-1>", lambda _e, p=path: self._set_selected(p))
            w.bind(
                "<Double-Button-1>",
                lambda _e, p=path: self._on_double_click(p),
            )
            w.bind(
                "<Button-3>",
                lambda e, p=path: self._on_row_right_click(e, p),
            )

        self._row_widgets[str(path)] = {
            "row": row, "thumb": thumb_lbl, "name": name_lbl,
        }

    # ------- row context menu (Remove from project) -------

    def _on_row_right_click(self, event, path: Path) -> None:
        self._set_selected(path)
        menu = tk.Menu(
            self, tearoff=0,
            bg=HEADER_BG, fg=HEADER_FG,
            activebackground=ROW_SELECTED, activeforeground="#ffffff",
            relief="flat", bd=0, font=ui_font(10),
        )
        menu.add_command(
            label=f"Remove '{path.name}' from project...",
            command=lambda: self._remove_image(path),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _remove_image(self, path: Path) -> None:
        """Delete an image from ``assets/images/``. Widgets that still
        reference the file render a missing-image placeholder at next
        re-paint — the user is responsible for swapping in another
        image afterwards. Save layer turns dangling tokens into broken
        paths the same way fonts handle a removed family.
        """
        if not messagebox.askyesno(
            "Remove from project",
            f"Remove '{path.name}' from this project?\n\n"
            f"File: {path}\n\n"
            "The image file is deleted from disk. This cannot be "
            "undone. Widgets that referenced this image will render a "
            "broken-image placeholder at next paint.",
            parent=self,
            icon="warning",
        ):
            return
        try:
            if path.exists():
                path.unlink()
        except OSError:
            log_error("image picker remove unlink")
            messagebox.showerror(
                "Remove failed",
                f"Couldn't delete:\n{path}",
                parent=self,
            )
            return
        # Drop selection if we just removed the picked image so OK
        # doesn't try to commit a deleted file.
        if self._selected_path == path:
            self._selected_path = None
        # Drop the cached thumbnail so a future reimport with the same
        # filename gets a fresh PhotoImage instead of the dead handle.
        self._thumb_cache.pop(str(path), None)
        self._notify_assets_changed()
        self._refresh()

    def _thumb_for(self, path: Path) -> ImageTk.PhotoImage | None:
        # Cache thumbnails per session — ttk treeview-style preview.
        key = str(path)
        if key in self._thumb_cache:
            return self._thumb_cache[key]
        try:
            from PIL import Image, ImageTk
            img = Image.open(path)
            img.thumbnail((THUMB, THUMB))
            tk_img = ImageTk.PhotoImage(img)
            self._thumb_cache[key] = tk_img
            return tk_img
        except Exception:
            return None

    # ------- selection handling -------

    def _set_selected(self, path: Path | None) -> None:
        self._selected_path = path
        for key, widgets in self._row_widgets.items():
            is_sel = path is not None and key == str(path)
            bg = ROW_SELECTED if is_sel else PANEL_BG
            for w in widgets.values():
                try:
                    w.configure(bg=bg)
                except tk.TclError:
                    pass
        try:
            self._ok_btn.configure(
                state="normal" if path is not None else "disabled",
            )
        except tk.TclError:
            pass

    def _on_double_click(self, path: Path) -> None:
        self._selected_path = path
        self._on_ok()

    # ------- actions -------

    def _on_import(self) -> None:
        src = filedialog.askopenfilename(
            parent=self, title="Import image into project",
            filetypes=[
                ("Image files",
                 "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.ico"),
                ("All files", "*.*"),
            ],
        )
        if not src:
            return
        if Path(src).suffix.lower() not in IMAGE_EXTS:
            messagebox.showwarning(
                "Not an image",
                f"{Path(src).name} doesn't look like an image file.",
                parent=self,
            )
            return
        try:
            token = copy_to_assets(src, self.project_file, "images")
        except OSError:
            log_error("image picker import")
            messagebox.showerror(
                "Import failed",
                "Could not copy the image into the project's "
                "assets folder.",
                parent=self,
            )
            return
        resolved = resolve_asset_token(token, self.project_file)
        # Refresh + auto-select the newly imported image.
        self._refresh(select=resolved if resolved else None)
        self._notify_assets_changed()

    def _on_pick_lucide(self) -> None:
        # Bundled Lucide picker writes the tinted PNG straight into
        # ``<project>/assets/images/`` so the result file is already
        # part of the project — no extra copy step.
        from app.ui.lucide_icon_picker_dialog import LucideIconPickerDialog
        target_dir = self._images_dir()
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            log_error("image picker lucide target dir")
            return
        dlg = LucideIconPickerDialog(self, target_dir)
        dlg.wait_window()
        if not dlg.result:
            return
        self._refresh(select=Path(dlg.result))
        self._notify_assets_changed()

    def _notify_assets_changed(self) -> None:
        # Wake up any docked Assets panel that's listening to the
        # project's event bus. Without this, importing through this
        # dialog leaves the docked tree showing stale contents until
        # the next manual refresh.
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish("dirty_changed", True)
        except Exception:
            pass

    def _on_ok(self) -> None:
        if self._selected_path is None:
            return
        self.result = str(self._selected_path)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def destroy(self) -> None:
        # Tooltip is a child Toplevel — drop it on every close path
        # (Cancel button, OK button, X-close, Escape) so it doesn't
        # outlive the dialog and float orphaned on screen.
        self._hide_help()
        super().destroy()

    # ------- help tooltip -------

    def _show_help(self, _event=None) -> None:
        if self._tip_window is not None:
            return
        try:
            x = self._help_lbl.winfo_rootx() + 22
            y = self._help_lbl.winfo_rooty() + 24
        except tk.TclError:
            return
        tip = tk.Toplevel(self)
        tip.overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        tip.configure(bg=BG)
        frame = tk.Frame(tip, bg=BG, padx=10, pady=8)
        frame.pack()
        tk.Label(
            frame, text=HELP_TEXT, bg=BG, fg=HEADER_FG,
            font=ui_font(11), justify="left", anchor="w",
        ).pack()
        tip.geometry(f"+{x}+{y}")
        self._tip_window = tip

    def _hide_help(self, _event=None) -> None:
        if self._tip_window is not None:
            try:
                self._tip_window.destroy()
            except tk.TclError:
                pass
            self._tip_window = None
