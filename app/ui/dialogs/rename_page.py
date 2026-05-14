"""Rename-page modal — shows file/folder rename preview + backup tip."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from app.core.project_folder import slugify_page_name
from app.ui.dialog_utils import safe_grab_set
from app.ui.dialogs._base import DarkDialog
from app.ui.dialogs._colors import (
    _ABT_BG, _ABT_DIM, _ABT_FG, _ABT_LINK, _ABT_SEP,
)


class RenamePageDialog(DarkDialog):
    """Modal page-rename dialog with explicit consequences + backup
    tip. Replaces the bare ``simpledialog.askstring`` so the user
    sees what the rename will touch (page file, scripts folder,
    archive folder) before committing — and is reminded to copy the
    project folder first.

    ``result`` is the new page name (string) on Rename, ``None`` on
    Cancel / Esc / X.
    """

    def __init__(self, parent, current_name: str) -> None:
        super().__init__(parent)
        self.title("Rename page")
        self.result: str | None = None
        self._current = current_name
        self._current_slug = slugify_page_name(current_name)
        self._build()
        # Fixed dimensions — the dialog content is static at compile
        # time (label text + entry + 3 bullet preview + tip + button
        # row) so reqheight measurement isn't worth it. Pumping the
        # event loop with self.update() to coax a tighter measurement
        # also dispatches stale key events from the right-click menu
        # which destroyed the dialog mid-construction.
        W, H = 460, 380
        self.place_centered(W, H, parent)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._on_ok())
        self.lift()
        self.focus_set()
        safe_grab_set(self)
        self.reveal()
        # Defer entry focus until the window is mapped + realized.
        # Otherwise focus_set on the entry can fire before Tk has
        # finished wiring the widget into its window manager, which
        # surfaces as ``bad window path name`` on the second open.
        self.after(0, self._focus_entry_safe)

    def _focus_entry_safe(self) -> None:
        if not self.winfo_exists():
            return
        try:
            self._entry.focus_set()
            self._entry.select_range(0, tk.END)
        except tk.TclError:
            # Window already destroyed (rapid open-close). Nothing
            # to focus — silently no-op.
            pass

    def _build(self) -> None:
        from app.ui.system_fonts import derive_mono_font, derive_ui_font
        f_title = derive_ui_font(size=13, weight="bold")
        f_dim = derive_ui_font(size=9)
        f_body = derive_ui_font(size=10)
        f_body_b = derive_ui_font(size=10, weight="bold")
        f_mono = derive_mono_font(size=9)
        pad: dict[str, Any] = {"padx": 24}

        tk.Frame(self, bg=_ABT_BG, height=16).pack()
        tk.Label(
            self, text="Rename page",
            bg=_ABT_BG, fg=_ABT_FG, font=f_title,
        ).pack(**pad, anchor="w")

        tk.Label(
            self, text=f"Current name: {self._current}",
            bg=_ABT_BG, fg=_ABT_DIM, font=f_dim,
        ).pack(**pad, anchor="w", pady=(2, 8))

        tk.Label(
            self, text="New name:",
            bg=_ABT_BG, fg=_ABT_FG, font=f_body,
        ).pack(**pad, anchor="w")

        self._entry = tk.Entry(
            self, width=42,
            bg="#2a2a2a", fg=_ABT_FG, insertbackground=_ABT_FG,
            relief="flat", font=f_body,
        )
        self._entry.insert(0, self._current)
        self._entry.pack(padx=24, pady=(4, 12), fill="x")
        self._entry.bind("<KeyRelease>", lambda _e: self._refresh_preview())

        tk.Frame(self, bg=_ABT_SEP, height=1).pack(
            fill="x", padx=24, pady=(0, 12),
        )

        tk.Label(
            self, text="⚠ This rename will affect:",
            bg=_ABT_BG, fg=_ABT_FG, font=f_body_b,
        ).pack(**pad, anchor="w")

        # Bulleted list — `_refresh_preview` updates the file/folder
        # names live as the user types in the entry.
        self._preview_label = tk.Label(
            self, text="", bg=_ABT_BG, fg=_ABT_FG,
            font=f_mono, justify="left", anchor="w",
        )
        self._preview_label.pack(**pad, anchor="w", pady=(4, 8))

        tk.Label(
            self,
            text=(
                "Exported .py files reference the old scripts path —\n"
                "re-export after renaming."
            ),
            bg=_ABT_BG, fg=_ABT_DIM, font=f_dim,
            justify="left",
        ).pack(**pad, anchor="w", pady=(0, 12))

        tk.Frame(self, bg=_ABT_SEP, height=1).pack(
            fill="x", padx=24, pady=(0, 12),
        )

        tk.Label(
            self,
            text=(
                "💡 Tip: copy the project folder to a safe location\n"
                "before renaming, in case you need to revert."
            ),
            bg=_ABT_BG, fg=_ABT_LINK, font=f_dim,
            justify="left",
        ).pack(**pad, anchor="w", pady=(0, 16))

        btn_row = tk.Frame(self, bg=_ABT_BG)
        btn_row.pack(pady=(0, 16))
        tk.Button(
            btn_row, text="Cancel", command=self._on_cancel,
            bg="#3a3a3a", fg=_ABT_FG, activebackground="#4a4a4a",
            activeforeground=_ABT_FG, relief="flat", bd=0,
            font=f_body, padx=20, pady=4, cursor="hand2",
        ).pack(side="left", padx=(0, 8))
        self._ok_btn = tk.Button(
            btn_row, text="Rename", command=self._on_ok,
            bg="#6366f1", fg="#ffffff", activebackground="#4f46e5",
            activeforeground="#ffffff", relief="flat", bd=0,
            disabledforeground="#888888",
            font=f_body, padx=20, pady=4, cursor="hand2",
        )
        self._ok_btn.pack(side="left")

        self._refresh_preview()

    def _refresh_preview(self) -> None:
        new_name = self._entry.get().strip()
        new_slug = slugify_page_name(new_name) if new_name else ""
        if not new_slug or new_slug == self._current_slug:
            # Either empty or same slug — show placeholder + disable
            # the Rename button so the user can't fire a no-op.
            self._preview_label.configure(
                text="  (enter a different name to see the changes)",
                fg=_ABT_DIM,
            )
            self._ok_btn.configure(state="disabled")
            return
        old = self._current_slug
        bullets = (
            f"  • {old}.ctkproj → {new_slug}.ctkproj\n"
            f"  • assets/scripts/{old}/ → {new_slug}/\n"
            f"  • assets/scripts_archive/{old}/ → {new_slug}/"
        )
        self._preview_label.configure(text=bullets, fg=_ABT_FG)
        self._ok_btn.configure(state="normal")

    def _on_ok(self) -> None:
        new_name = self._entry.get().strip()
        if not new_name:
            self.bell()
            return
        if slugify_page_name(new_name) == self._current_slug:
            self.bell()
            return
        self.result = new_name
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()


def prompt_rename_page(parent, current_name: str) -> str | None:
    """Show ``RenamePageDialog`` modally. Returns the new name on
    Rename or ``None`` on Cancel — same shape as
    ``simpledialog.askstring`` it replaces.
    """
    dlg = RenamePageDialog(parent, current_name)
    # Defensive: if the dialog destroyed itself during construction
    # (rare race when a stale Esc/Return event from the right-click
    # menu fires), skip wait_window so we don't TclError on a dead
    # window path.
    if dlg.winfo_exists():
        parent.wait_window(dlg)
    return dlg.result
