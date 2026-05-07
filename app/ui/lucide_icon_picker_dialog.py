"""Lucide icon picker dialog.

Browse and pick a Lucide icon from the bundled set (~1700 icons,
42 categories). Tints with a chosen hex color and writes the
result PNG to a target directory the caller specifies.

Returns ``self.result`` — absolute path of the saved tinted PNG, or
``None`` on Cancel.

Used by:
    - Image picker dialog ("+ Lucide icon..." button)
    - Project window + menu ("Lucide Icon..." entry)
"""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image, ImageTk

from app.ui.dialog_utils import prepare_dialog, reveal_dialog, safe_grab_set

LUCIDE_DIR = Path(__file__).resolve().parent.parent / "assets" / "lucide"
PNG_DIR = LUCIDE_DIR / "png-icons"
CATS_FILE = LUCIDE_DIR / "categories.json"

BG = "#1e1e1e"
PANEL_BG = "#252526"
HEADER_BG = "#2d2d30"
HEADER_FG = "#cccccc"
DIM_FG = "#888888"
ROW_SELECTED = "#094771"
GRID_BG = "#1a1a1a"
GRID_HOVER = "#2a2a2a"
GRID_SELECTED = "#094771"

DIALOG_W = 760
DIALOG_H = 580
SIDEBAR_W = 180
PREVIEW_W = 200
THUMB = 28
PREVIEW_SIZE = 64
GRID_COLS = 6
# Hard cap so "All" / a vague search doesn't try to render 1700
# Tk widgets at once. Beyond this, the user is told to refine.
MAX_ICONS = 400

DEFAULT_TINT = "#ffffff"
SIZE_OPTIONS = (24, 32, 48, 64, 96, 128)
DEFAULT_OUTPUT_SIZE = 64


class LucideIconPickerDialog(tk.Toplevel):
    """Pick a Lucide icon, tint it, save to ``target_dir``.

    Caller passes ``target_dir`` — absolute path where the tinted
    PNG should be written (e.g. ``<project>/assets/images/`` or a
    user-selected subfolder). On Apply, the tinted icon is saved
    as ``<target_dir>/<icon-name>.png`` and the path is exposed via
    ``self.result``.
    """

    _meta_cache: dict | None = None

    def __init__(self, parent, target_dir: Path | str) -> None:
        super().__init__(parent)
        prepare_dialog(self)
        self.target_dir = Path(target_dir)
        self.result: str | None = None

        self.title("Lucide icons")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        safe_grab_set(self)
        self.geometry(f"{DIALOG_W}x{DIALOG_H}")
        self._center_on_parent(parent)

        self._meta = self._load_meta()
        self._categories: dict[str, dict] = self._meta.get("categories", {})
        self._icons_meta: dict[str, dict] = self._meta.get("icons", {})

        self._tint = DEFAULT_TINT
        self._output_size = DEFAULT_OUTPUT_SIZE
        self._search = ""
        # Open on the first sorted category instead of "All" — "All"
        # renders ~400 cells at once which is slow and unnecessary
        # given the sidebar + search are right there.
        sorted_cats = sorted(self._categories.keys())
        self._active_cat: str = sorted_cats[0] if sorted_cats else "_all"
        self._selected: str | None = None
        self._thumb_cache: dict[tuple[str, str, int], tk.PhotoImage] = {}
        self._cat_buttons: dict[str, tk.Frame] = {}
        self._grid_cells: dict[str, tk.Frame] = {}

        self._build()

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._on_apply())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        reveal_dialog(self)
        # Defer first paint until the scrollable frames are realised —
        # tk's CTkScrollableFrame leaves children unmapped if you push
        # them in before the canvas has been packed.
        self.after_idle(self._populate_categories)
        self.after_idle(self._refresh_grid)

    # ------------------------------------------------------------------
    # Meta loading
    # ------------------------------------------------------------------
    @classmethod
    def _load_meta(cls) -> dict:
        if cls._meta_cache is None:
            try:
                cls._meta_cache = json.loads(
                    CATS_FILE.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                cls._meta_cache = {"categories": {}, "icons": {}}
        return cls._meta_cache

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build(self) -> None:
        self._build_header()
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=8, pady=(4, 4))
        self._build_sidebar(body)
        self._build_grid(body)
        self._build_preview(body)
        self._build_footer()

    def _build_header(self) -> None:
        bar = tk.Frame(self, bg=HEADER_BG)
        bar.pack(fill="x")

        tk.Label(
            bar, text="Search:", bg=HEADER_BG, fg=HEADER_FG,
            font=("Segoe UI", 10),
        ).pack(side="left", padx=(12, 6), pady=8)

        self._search_var = tk.StringVar()
        self._search_var.trace_add(
            "write", lambda *_: self._on_search_change(),
        )
        ctk.CTkEntry(
            bar, textvariable=self._search_var, width=240, height=28,
            placeholder_text="filter by name or tag...",
        ).pack(side="left", padx=(0, 8), pady=6)

        self._count_lbl = tk.Label(
            bar, text="", bg=HEADER_BG, fg=DIM_FG, font=("Segoe UI", 10),
        )
        self._count_lbl.pack(side="left", padx=(8, 0), pady=8)

    def _build_sidebar(self, parent: tk.Misc) -> None:
        wrap = tk.Frame(parent, bg=PANEL_BG, width=SIDEBAR_W)
        wrap.pack(side="left", fill="y", padx=(0, 6))
        wrap.pack_propagate(False)

        self._cat_scroll = ctk.CTkScrollableFrame(
            wrap, fg_color=PANEL_BG, corner_radius=0,
            width=SIDEBAR_W - 16,
        )
        self._cat_scroll.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_grid(self, parent: tk.Misc) -> None:
        self._grid_scroll = ctk.CTkScrollableFrame(
            parent, fg_color=GRID_BG, corner_radius=0,
        )
        self._grid_scroll.pack(side="left", fill="both", expand=True)
        for c in range(GRID_COLS):
            self._grid_scroll.grid_columnconfigure(
                c, weight=1, uniform="cells",
            )

    def _build_preview(self, parent: tk.Misc) -> None:
        wrap = tk.Frame(parent, bg=PANEL_BG, width=PREVIEW_W)
        wrap.pack(side="left", fill="y", padx=(6, 0))
        wrap.pack_propagate(False)

        self._preview_lbl = tk.Label(
            wrap, bg=PANEL_BG, width=PREVIEW_SIZE, height=PREVIEW_SIZE,
        )
        self._preview_lbl.pack(pady=(20, 8))

        self._name_lbl = tk.Label(
            wrap, text="(no selection)", bg=PANEL_BG, fg="#cccccc",
            font=("Segoe UI", 11, "bold"),
            wraplength=PREVIEW_W - 16,
        )
        self._name_lbl.pack(pady=(0, 4))

        self._tags_lbl = tk.Label(
            wrap, text="", bg=PANEL_BG, fg=DIM_FG,
            font=("Segoe UI", 9), wraplength=PREVIEW_W - 16,
            justify="center",
        )
        self._tags_lbl.pack(pady=(0, 12))

        tint_row = tk.Frame(wrap, bg=PANEL_BG)
        tint_row.pack(pady=(8, 0))
        tk.Label(
            tint_row, text="Tint:", bg=PANEL_BG, fg=HEADER_FG,
            font=("Segoe UI", 10),
        ).pack(side="left", padx=(0, 4))
        self._tint_entry = ctk.CTkEntry(
            tint_row, width=80, height=26,
        )
        self._tint_entry.insert(0, self._tint)
        # ``return "break"`` so Enter inside the entry only commits
        # the tint — without it, the toplevel <Return> binding (Apply)
        # would also fire and close the dialog.
        self._tint_entry.bind(
            "<Return>", lambda _e: (self._on_tint_commit(), "break")[1],
        )
        self._tint_entry.bind(
            "<FocusOut>", lambda _e: self._on_tint_commit(),
        )
        self._tint_entry.pack(side="left")

        self._swatch = tk.Frame(
            tint_row, bg=self._tint, width=24, height=24,
            cursor="hand2", relief="solid", bd=1,
        )
        self._swatch.pack(side="left", padx=(6, 0))
        self._swatch.bind("<Button-1>", lambda _e: self._open_color_picker())

        size_row = tk.Frame(wrap, bg=PANEL_BG)
        size_row.pack(pady=(8, 0))
        tk.Label(
            size_row, text="Size:", bg=PANEL_BG, fg=HEADER_FG,
            font=("Segoe UI", 10),
        ).pack(side="left", padx=(0, 4))
        self._size_var = tk.StringVar(value=str(self._output_size))
        self._size_menu = ctk.CTkOptionMenu(
            size_row, values=[f"{s} px" for s in SIZE_OPTIONS],
            width=100, height=26, dynamic_resizing=False,
            command=self._on_size_change,
        )
        self._size_menu.set(f"{self._output_size} px")
        self._size_menu.pack(side="left")

    def _build_footer(self) -> None:
        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=10, pady=(4, 10))
        self._apply_btn = ctk.CTkButton(
            foot, text="Apply", width=140, height=32, corner_radius=4,
            command=self._on_apply, state="disabled",
        )
        self._apply_btn.pack(side="right")
        ctk.CTkButton(
            foot, text="Cancel", width=90, height=32, corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))

    # ------------------------------------------------------------------
    # Categories sidebar
    # ------------------------------------------------------------------
    def _populate_categories(self) -> None:
        self._build_cat_button("_all", "All", len(self._icons_meta))
        for key in sorted(self._categories.keys()):
            cat = self._categories[key]
            count = len(cat.get("icons", []))
            if count == 0:
                continue
            self._build_cat_button(key, cat.get("title", key), count)
        self._highlight_cat(self._active_cat)

    def _build_cat_button(
        self, key: str, title: str, count: int,
    ) -> None:
        row = tk.Frame(self._cat_scroll, bg=PANEL_BG, cursor="hand2")
        row.pack(fill="x", padx=2, pady=1)
        lbl = tk.Label(
            row, text=f"  {title}  ({count})", bg=PANEL_BG, fg=HEADER_FG,
            font=("Segoe UI", 10), anchor="w",
        )
        lbl.pack(fill="x", padx=4, pady=4)
        for w in (row, lbl):
            w.bind("<Button-1>", lambda _e, k=key: self._on_cat_click(k))
        self._cat_buttons[key] = row

    def _on_cat_click(self, key: str) -> None:
        self._active_cat = key
        self._highlight_cat(key)
        self._refresh_grid()
        # Reset scroll to top so the new category opens at its first
        # row regardless of where the previous category was scrolled.
        # CTkScrollableFrame doesn't expose ``yview_moveto`` directly —
        # reach into the inner canvas. Defer with after_idle so the
        # grid rebuild has time to update the scroll region first;
        # otherwise yview_moveto sees stale dimensions and lands at
        # the wrong fraction.
        try:
            self._grid_scroll.after_idle(
                lambda: self._grid_scroll._parent_canvas.yview_moveto(0.0),
            )
        except Exception:
            pass

    def _highlight_cat(self, active_key: str | None) -> None:
        for key, row in self._cat_buttons.items():
            bg = ROW_SELECTED if key == active_key else PANEL_BG
            try:
                row.configure(bg=bg)
                for child in row.winfo_children():
                    child.configure(bg=bg)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Icon grid
    # ------------------------------------------------------------------
    def _on_search_change(self) -> None:
        self._search = self._search_var.get().strip().lower()
        self._refresh_grid()

    def _filtered_icons(self) -> list[str]:
        q = self._search
        cat_key = self._active_cat
        if cat_key and cat_key != "_all":
            cat = self._categories.get(cat_key, {})
            names = list(cat.get("icons", []))
        else:
            names = list(self._icons_meta.keys())
        if q:
            def matches(n: str) -> bool:
                if q in n:
                    return True
                meta = self._icons_meta.get(n, {})
                tags = meta.get("tags", [])
                return any(q in t.lower() for t in tags)
            names = [n for n in names if matches(n)]
        names.sort()
        return names

    def _refresh_grid(self) -> None:
        for child in list(self._grid_scroll.winfo_children()):
            try:
                child.destroy()
            except tk.TclError:
                pass
        self._grid_cells.clear()

        names = self._filtered_icons()
        total = len(names)
        capped = names[:MAX_ICONS]
        truncated = total > MAX_ICONS

        try:
            self._count_lbl.configure(
                text=(
                    f"{total} icons" if not truncated
                    else f"showing {MAX_ICONS} of {total} — refine search"
                )
            )
        except tk.TclError:
            pass

        if not capped:
            ctk.CTkLabel(
                self._grid_scroll, text="No icons match.",
                text_color=DIM_FG, font=("Segoe UI", 11),
            ).grid(row=0, column=0, columnspan=GRID_COLS, pady=40)
            return

        for i, name in enumerate(capped):
            self._build_cell(name, i // GRID_COLS, i % GRID_COLS)

        if self._selected and self._selected in self._grid_cells:
            self._highlight_cell(self._selected, True)

    def _build_cell(self, name: str, row: int, col: int) -> None:
        cell = tk.Frame(
            self._grid_scroll, bg=GRID_BG, cursor="hand2",
            width=THUMB + 16, height=THUMB + 16,
        )
        cell.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")
        cell.grid_propagate(False)
        thumb = self._thumb_for(name, self._tint, THUMB)
        lbl = tk.Label(
            cell, bg=GRID_BG,
            image=thumb if thumb else None,
            text="" if thumb else "?", fg="#888888",
        )
        if thumb is not None:
            lbl.image = thumb  # keep ref
        lbl.place(relx=0.5, rely=0.5, anchor="center")
        for w in (cell, lbl):
            w.bind("<Button-1>", lambda _e, n=name: self._on_cell_click(n))
            w.bind(
                "<Double-Button-1>",
                lambda _e, n=name: self._on_cell_double(n),
            )
            w.bind("<Enter>", lambda _e, n=name: self._on_cell_enter(n))
            w.bind("<Leave>", lambda _e, n=name: self._on_cell_leave(n))
        self._grid_cells[name] = cell

    def _on_cell_click(self, name: str) -> None:
        prev = self._selected
        self._selected = name
        if prev and prev in self._grid_cells:
            self._highlight_cell(prev, False)
        self._highlight_cell(name, True)
        self._refresh_preview()
        try:
            self._apply_btn.configure(state="normal")
        except tk.TclError:
            pass

    def _on_cell_double(self, name: str) -> None:
        self._on_cell_click(name)
        self._on_apply()

    def _on_cell_enter(self, name: str) -> None:
        if name == self._selected:
            return
        self._set_cell_bg(name, GRID_HOVER)

    def _on_cell_leave(self, name: str) -> None:
        if name == self._selected:
            return
        self._set_cell_bg(name, GRID_BG)

    def _highlight_cell(self, name: str, selected: bool) -> None:
        self._set_cell_bg(name, GRID_SELECTED if selected else GRID_BG)

    def _set_cell_bg(self, name: str, bg: str) -> None:
        cell = self._grid_cells.get(name)
        if cell is None:
            return
        try:
            cell.configure(bg=bg)
            for c in cell.winfo_children():
                c.configure(bg=bg)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    def _refresh_preview(self) -> None:
        if not self._selected:
            return
        big = self._thumb_for(self._selected, self._tint, PREVIEW_SIZE)
        try:
            if big is not None:
                self._preview_lbl.configure(image=big, text="")
                self._preview_lbl.image = big
            else:
                self._preview_lbl.configure(image="", text="?")
            self._name_lbl.configure(text=self._selected)
            tags = self._icons_meta.get(self._selected, {}).get("tags", [])
            self._tags_lbl.configure(
                text=", ".join(tags[:8]) if tags else "",
            )
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Tint
    # ------------------------------------------------------------------
    def _on_tint_commit(self) -> None:
        new = self._tint_entry.get().strip()
        if not new:
            return
        if not new.startswith("#"):
            new = "#" + new
        try:
            self._parse_hex(new)
        except ValueError:
            self._tint_entry.delete(0, "end")
            self._tint_entry.insert(0, self._tint)
            return
        if new.lower() == self._tint.lower():
            return
        self._tint = new
        try:
            self._swatch.configure(bg=new)
            self._tint_entry.delete(0, "end")
            self._tint_entry.insert(0, new)
        except tk.TclError:
            pass
        # New tint invalidates every cached thumbnail.
        self._thumb_cache.clear()
        self._refresh_grid()
        self._refresh_preview()

    def _on_size_change(self, value: str) -> None:
        try:
            self._output_size = int(value.split()[0])
        except (ValueError, IndexError):
            return

    def _open_color_picker(self) -> None:
        try:
            from ctk_color_picker import ColorPickerDialog
        except ImportError:
            return
        dlg = ColorPickerDialog(self, initial_color=self._tint)
        dlg.wait_window()
        new = getattr(dlg, "result", None)
        if not new:
            return
        self._tint_entry.delete(0, "end")
        self._tint_entry.insert(0, new)
        self._on_tint_commit()

    @staticmethod
    def _parse_hex(color: str) -> tuple[int, int, int]:
        v = color.lstrip("#")
        if len(v) == 3:
            v = "".join(c * 2 for c in v)
        if len(v) != 6:
            raise ValueError(color)
        return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)

    # ------------------------------------------------------------------
    # Thumbnail tinting
    # ------------------------------------------------------------------
    def _thumb_for(
        self, name: str, tint: str, size: int,
    ) -> tk.PhotoImage | None:
        key = (name, tint, size)
        cached = self._thumb_cache.get(key)
        if cached is not None:
            return cached
        path = PNG_DIR / f"{name}.png"
        if not path.exists():
            return None
        try:
            tinted = self._tint_image(path, tint, size)
            photo = ImageTk.PhotoImage(tinted)
            self._thumb_cache[key] = photo
            return photo
        except Exception:
            return None

    def _tint_image(
        self, path: Path, tint: str, size: int | None = None,
    ) -> Image.Image:
        r, g, b = self._parse_hex(tint)
        src = Image.open(path).convert("RGBA")
        solid = Image.new("RGBA", src.size, (r, g, b, 255))
        empty = Image.new("RGBA", src.size, (0, 0, 0, 0))
        alpha = src.split()[3]
        tinted = Image.composite(solid, empty, alpha)
        if size is not None and tinted.size != (size, size):
            tinted = tinted.resize((size, size), Image.LANCZOS)
        return tinted

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------
    def _center_on_parent(self, parent: tk.Misc) -> None:
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + (pw - DIALOG_W) // 2
            y = py + (ph - DIALOG_H) // 2
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Apply / Cancel
    # ------------------------------------------------------------------
    def _on_apply(self) -> None:
        if not self._selected:
            return
        src = PNG_DIR / f"{self._selected}.png"
        if not src.exists():
            messagebox.showerror(
                "Icon missing",
                f"Bundled icon file is missing: {src.name}",
                parent=self,
            )
            return
        try:
            self.target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                "Save failed",
                f"Could not create target folder:\n{exc}",
                parent=self,
            )
            return
        dst = self.target_dir / f"{self._selected}.png"
        try:
            tinted = self._tint_image(src, self._tint, self._output_size)
            tinted.save(dst, "PNG")
        except Exception as exc:
            messagebox.showerror(
                "Save failed",
                f"Could not save tinted icon:\n{exc}",
                parent=self,
            )
            return
        self.result = str(dst)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()
