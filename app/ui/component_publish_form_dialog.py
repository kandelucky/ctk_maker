"""Modal — Publish-to-community form. Runs after the License dialog
has been accepted. Embeds an immutable ``license`` block (signed by
the typed Author at the moment of export) into the new ``.ctkcomp``
file written at the chosen folder.
"""

from __future__ import annotations

import datetime
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app.core.component_paths import COMPONENT_EXT
from app.core.logger import log_error
from app.core.settings import load_settings, save_setting
from app.io.component_io import load_metadata, rewrite_payload_for_publish

CATEGORY_GUIDE_URL = (
    "https://github.com/kandelucky/ctk_maker/wiki/Component-Categories"
)

LAST_AUTHOR_KEY = "last_component_author"
LICENSE_TEXT_VERSION = 1
DESCRIPTION_MAX = 300
# Hub site upload cap — temporary GitHub Discussions attachment limit.
PUBLISH_MAX_BYTES = 25 * 1024 * 1024

CATEGORIES: list[tuple[str, str]] = [
    ("Buttons", "Styled buttons (icon, toggle packs, action groups)"),
    ("Inputs", "Entry / Combobox / Checkbox / Slider variations"),
    ("Forms", "Multi-field configurations (login, signup, settings, contact)"),
    ("Layout", "Grid / row / column containers, splitters, scroll areas"),
    ("Navigation", "Sidebar, top bar, tab strip, breadcrumb, menu drawer"),
    ("Dialogs & Modals", "Alerts, confirms, file pickers, settings popups"),
    ("Cards & Panels", "Info card, profile card, stat tile, collapsible panel"),
    ("Mini-Apps", "Full small apps (todo, calculator, calendar, music player)"),
    ("Templates & Starters", "Empty skeletons for new projects"),
    ("Other", "Anything that doesn't fit elsewhere"),
]
CATEGORY_NAMES = [name for name, _ in CATEGORIES]
CATEGORY_HINTS = {name: hint for name, hint in CATEGORIES}

_FORBIDDEN = set('\\/:*?"<>|')


def _is_valid_name(name: str) -> bool:
    name = name.strip()
    if not name or name in (".", ".."):
        return False
    return not any(ch in _FORBIDDEN for ch in name)


def _format_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    kb = num_bytes / 1024
    if kb < 1024:
        return f"{kb:.1f} KB"
    mb = kb / 1024
    return f"{mb:.1f} MB"


def _format_date(iso: str) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso


class ComponentPublishFormDialog(ctk.CTkToplevel):
    def __init__(self, parent, source_path: Path):
        super().__init__(parent)
        self.title("Publish component")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color="#1a1a1a")

        self.result: bool = False
        self._source_path = source_path
        self._destination: Path | None = None

        meta = load_metadata(source_path) or {}
        try:
            file_bytes = source_path.stat().st_size
        except OSError:
            file_bytes = 0

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(padx=22, pady=(18, 6), fill="x")

        ctk.CTkLabel(
            body, text=meta.get("name") or source_path.stem,
            font=("Segoe UI", 14, "bold"),
            text_color="#e6e6e6", anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            body,
            text=(
                f"{meta.get('view_w', 0)} × {meta.get('view_h', 0)}"
                f"  ·  {_format_size(file_bytes)}"
                f"  ·  {_format_date(meta.get('created_at', ''))}"
            ),
            font=("Segoe UI", 9),
            text_color="#888888", anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(0, 10))

        # License banner — reminder of what was just agreed to.
        banner = ctk.CTkFrame(
            body, fg_color="#262a30", corner_radius=4,
        )
        banner.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        ctk.CTkLabel(
            banner,
            text=("✓ License agreement accepted — MIT  ·  signed at export"),
            font=("Segoe UI", 9, "bold"),
            text_color="#9ec3ff", anchor="w",
        ).pack(anchor="w", padx=10, pady=6)

        ctk.CTkLabel(
            body, text="Name", font=("Segoe UI", 10),
        ).grid(row=3, column=0, sticky="w", pady=(0, 4))
        self._name_var = tk.StringVar(value=self._source_path.stem)
        ctk.CTkEntry(
            body, textvariable=self._name_var, width=340,
        ).grid(row=4, column=0, sticky="ew", pady=(0, 12))

        ctk.CTkLabel(
            body, text="Author (required — used as MIT copyright holder)",
            font=("Segoe UI", 10),
        ).grid(row=5, column=0, sticky="w", pady=(0, 4))
        cached_author = str(
            load_settings().get(LAST_AUTHOR_KEY, "") or "",
        )
        self._author_var = tk.StringVar(
            value=meta.get("author", "") or cached_author,
        )
        self._cached_author = cached_author
        ctk.CTkEntry(
            body, textvariable=self._author_var, width=340,
            placeholder_text="your name or handle",
        ).grid(row=6, column=0, sticky="ew", pady=(0, 12))

        cat_label_row = ctk.CTkFrame(body, fg_color="transparent")
        cat_label_row.grid(row=7, column=0, sticky="ew", pady=(0, 4))
        cat_label_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            cat_label_row, text="Category", font=("Segoe UI", 10),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            cat_label_row, text="Need help picking?",
            width=130, height=20, corner_radius=3,
            font=("Segoe UI", 9, "underline"),
            fg_color="transparent", hover_color="#2b2b2b",
            text_color="#9ec3ff",
            command=self._open_category_guide,
        ).grid(row=0, column=1, sticky="e")
        self._category_var = tk.StringVar(value=CATEGORY_NAMES[0])
        self._category_menu = ctk.CTkOptionMenu(
            body, values=CATEGORY_NAMES,
            variable=self._category_var, width=340,
            command=lambda _v: self._refresh_category_hint(),
        )
        self._category_menu.grid(row=8, column=0, sticky="ew", pady=(0, 2))
        self._category_hint = ctk.CTkLabel(
            body, text="", font=("Segoe UI", 9),
            text_color="#888888", anchor="w", justify="left",
        )
        self._category_hint.grid(
            row=9, column=0, sticky="w", pady=(0, 12),
        )
        self._refresh_category_hint()

        ctk.CTkLabel(
            body, text="Description", font=("Segoe UI", 10),
        ).grid(row=10, column=0, sticky="w", pady=(0, 4))
        self._desc_box = ctk.CTkTextbox(
            body, height=70, width=340,
            font=("Segoe UI", 10), wrap="word",
        )
        self._desc_box.grid(row=11, column=0, sticky="ew", pady=(0, 2))
        self._desc_box.bind(
            "<KeyRelease>", lambda _e: self._refresh_desc_counter(),
        )
        self._desc_counter = ctk.CTkLabel(
            body, text=f"0 / {DESCRIPTION_MAX}",
            font=("Segoe UI", 9), text_color="#888888", anchor="e",
        )
        self._desc_counter.grid(row=12, column=0, sticky="e", pady=(0, 12))

        ctk.CTkLabel(
            body, text="Destination folder", font=("Segoe UI", 10),
        ).grid(row=13, column=0, sticky="w", pady=(0, 4))
        path_row = ctk.CTkFrame(body, fg_color="transparent")
        path_row.grid(row=14, column=0, sticky="ew", pady=(0, 12))
        path_row.grid_columnconfigure(0, weight=1)
        self._dest_var = tk.StringVar(value="")
        ctk.CTkEntry(
            path_row, textvariable=self._dest_var,
            placeholder_text="(pick a folder)", height=28,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            path_row, text="Browse…", width=80, height=28,
            corner_radius=4, command=self._on_browse,
        ).grid(row=0, column=1)

        body.grid_columnconfigure(0, weight=1)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=22, pady=(4, 16))
        ctk.CTkButton(
            footer, text="Publish", width=130, height=32,
            corner_radius=4, command=self._on_publish,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel", width=90, height=32,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.after(100, self._center_on_parent)

    def _open_category_guide(self) -> None:
        import webbrowser
        try:
            webbrowser.open(CATEGORY_GUIDE_URL, new=2)
        except Exception:
            pass

    def _refresh_category_hint(self) -> None:
        cat = self._category_var.get()
        self._category_hint.configure(
            text=CATEGORY_HINTS.get(cat, ""),
        )

    def _refresh_desc_counter(self) -> None:
        text = self._desc_box.get("1.0", "end-1c")
        if len(text) > DESCRIPTION_MAX:
            self._desc_box.delete(f"1.0+{DESCRIPTION_MAX}c", "end")
            text = text[:DESCRIPTION_MAX]
        n = len(text)
        color = "#d68a40" if n >= DESCRIPTION_MAX else "#888888"
        self._desc_counter.configure(
            text=f"{n} / {DESCRIPTION_MAX}", text_color=color,
        )

    def _on_browse(self) -> None:
        path = filedialog.askdirectory(
            parent=self,
            title="Publish component — pick destination folder",
        )
        if not path:
            return
        self._dest_var.set(path)

    def _on_publish(self) -> None:
        try:
            source_size = self._source_path.stat().st_size
        except OSError:
            source_size = 0
        if source_size > PUBLISH_MAX_BYTES:
            self.bell()
            messagebox.showwarning(
                "Too large to publish",
                f"This component is {_format_size(source_size)}. The "
                "community site currently accepts files up to 25 MB. "
                "You can still save it for personal use.",
                parent=self,
            )
            return
        author = self._author_var.get().strip()
        if not author:
            self.bell()
            messagebox.showwarning(
                "Author required",
                "Author can't be empty — it's used as the MIT "
                "copyright holder.",
                parent=self,
            )
            return
        category = self._category_var.get().strip()
        if category not in CATEGORY_HINTS:
            self.bell()
            messagebox.showwarning(
                "Pick a category",
                "Pick a category from the dropdown.",
                parent=self,
            )
            return
        description = self._desc_box.get("1.0", "end-1c").strip()
        if not description:
            self.bell()
            messagebox.showwarning(
                "Description required",
                "Add a brief description so other users know what "
                "this component does.",
                parent=self,
            )
            return
        dest = self._dest_var.get().strip()
        if not dest:
            self.bell()
            messagebox.showwarning(
                "Pick a destination",
                "Click Browse… to choose a destination folder.",
                parent=self,
            )
            return
        name = self._name_var.get().strip()
        if name.lower().endswith(COMPONENT_EXT):
            name = name[: -len(COMPONENT_EXT)]
        if not _is_valid_name(name):
            self.bell()
            messagebox.showwarning(
                "Invalid name",
                "Names can't be empty or contain \\ / : * ? \" < > |.",
                parent=self,
            )
            return
        dest_dir = Path(dest)
        if not dest_dir.is_dir():
            self.bell()
            messagebox.showwarning(
                "Folder not found",
                f"'{dest_dir}' is not a folder. Pick another destination.",
                parent=self,
            )
            return
        dest_path = dest_dir / f"{name}{COMPONENT_EXT}"
        if dest_path.exists():
            overwrite = messagebox.askyesno(
                "Already exists",
                f"'{dest_path.name}' already exists in this folder. "
                "Overwrite?",
                parent=self,
            )
            if not overwrite:
                return

        try:
            shutil.copy2(self._source_path, dest_path)
        except OSError as exc:
            log_error(f"publish copy {self._source_path} -> {dest_path}")
            self.bell()
            messagebox.showerror(
                "Copy failed",
                f"Couldn't write the file:\n{exc}",
                parent=self,
            )
            return

        license_block = self._build_license_block(author)
        try:
            rewrite_payload_for_publish(
                dest_path,
                author=author,
                license_block=license_block,
                category=category,
                description=description,
            )
        except Exception as exc:
            log_error(f"publish rewrite {dest_path}")
            self.bell()
            messagebox.showerror(
                "License embed failed",
                f"The component was copied but the license block "
                f"couldn't be written:\n{exc}",
                parent=self,
            )
            return

        if author and author != self._cached_author:
            save_setting(LAST_AUTHOR_KEY, author)

        self._destination = dest_path
        self.result = True
        self.destroy()

    def _build_license_block(self, author: str) -> dict:
        try:
            from app import __version__ as app_version
        except ImportError:
            app_version = "unknown"
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        return {
            "type": "MIT",
            "accepted_by": author,
            "accepted_at": now_utc.isoformat(timespec="seconds").replace(
                "+00:00", "Z",
            ),
            "ctk_maker_version": app_version,
            "confirmations": {
                "rights": True,
                "mit_release": True,
                "responsibility": True,
            },
            "text_version": LICENSE_TEXT_VERSION,
        }

    def _on_cancel(self) -> None:
        self.result = False
        self.destroy()

    def _center_on_parent(self) -> None:
        self.update_idletasks()
        parent = self.master
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
        except tk.TclError:
            return
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
