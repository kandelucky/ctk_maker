"""Rename-page modal — shows the file rename preview + backup tip."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from app.core.project_folder import slugify_page_name
from app.ui.dialog_utils import safe_grab_set
from app.ui.dialogs._base import DarkDialog
from app.ui.dialogs._colors import (
    _ABT_LINK,
    _ABT_SEP,
    FG,
    FG_DIM,
    PANEL,
    dialog_scaling,
    flat_button,
    hero_header,
)


class RenamePageDialog(DarkDialog):
    """Modal page-rename dialog with explicit consequences + backup
    tip. Replaces the bare ``simpledialog.askstring`` so the user
    sees what the rename will touch (the page's ``.ctkproj`` file)
    before committing — and is reminded to copy the project folder
    first.

    ``result`` is the new page name (string) on Rename, ``None`` on
    Cancel / Esc / X.
    """

    def __init__(self, parent, current_name: str) -> None:
        super().__init__(parent, fg_color=PANEL)
        self.title("Rename page")
        self.result: str | None = None
        self._current = current_name
        self._current_slug = slugify_page_name(current_name)
        self._s = dialog_scaling(self)
        self._build()
        # Fixed dimensions — the dialog content is static at compile
        # time (label text + entry + bullet preview + tip + button
        # row) so reqheight measurement isn't worth it. Pumping the
        # event loop with self.update() to coax a tighter measurement
        # also dispatches stale key events from the right-click menu
        # which destroyed the dialog mid-construction.
        s = self._s
        self.place_centered(round(460 * s), round(390 * s), parent)
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
        s = self._s
        f_dim = derive_ui_font(size=round(9 * s))
        f_body = derive_ui_font(size=round(10 * s))
        f_body_b = derive_ui_font(size=round(10 * s), weight="bold")
        f_mono = derive_mono_font(size=round(9 * s))
        # Body aligns with the hero title text (18 bar-pad + 3 bar
        # + 10 gap), same as MessageDialog.
        pad: dict[str, Any] = {"padx": round(31 * s)}

        hero_header(self, "Rename page", "info", s)

        tk.Label(
            self, text=f"Current name: {self._current}",
            bg=PANEL, fg=FG_DIM, font=f_dim,
        ).pack(**pad, anchor="w", pady=(round(4 * s), round(8 * s)))

        tk.Label(
            self, text="New name:",
            bg=PANEL, fg=FG, font=f_body,
        ).pack(**pad, anchor="w")

        self._entry = tk.Entry(
            self, width=42,
            bg="#2a2a2a", fg=FG, insertbackground=FG,
            relief="flat", font=f_body,
        )
        self._entry.insert(0, self._current)
        self._entry.pack(
            padx=round(31 * s), pady=(round(4 * s), round(12 * s)),
            fill="x",
        )
        self._entry.bind("<KeyRelease>", lambda _e: self._refresh_preview())

        tk.Frame(self, bg=_ABT_SEP, height=1).pack(
            fill="x", padx=round(31 * s), pady=(0, round(12 * s)),
        )

        tk.Label(
            self, text="⚠ This rename will affect:",
            bg=PANEL, fg=FG, font=f_body_b,
        ).pack(**pad, anchor="w")

        # Bulleted list — `_refresh_preview` updates the file/folder
        # names live as the user types in the entry.
        self._preview_label = tk.Label(
            self, text="", bg=PANEL, fg=FG,
            font=f_mono, justify="left", anchor="w",
        )
        self._preview_label.pack(
            **pad, anchor="w", pady=(round(4 * s), round(8 * s)),
        )

        tk.Label(
            self,
            text=(
                "Previously exported .py files keep the old name —\n"
                "re-export after renaming if you want it updated."
            ),
            bg=PANEL, fg=FG_DIM, font=f_dim,
            justify="left",
        ).pack(**pad, anchor="w", pady=(0, round(12 * s)))

        tk.Frame(self, bg=_ABT_SEP, height=1).pack(
            fill="x", padx=round(31 * s), pady=(0, round(12 * s)),
        )

        tk.Label(
            self,
            text=(
                "💡 Tip: copy the project folder to a safe location\n"
                "before renaming, in case you need to revert."
            ),
            bg=PANEL, fg=_ABT_LINK, font=f_dim,
            justify="left",
        ).pack(**pad, anchor="w", pady=(0, round(14 * s)))

        btn_row = tk.Frame(self, bg=PANEL)
        btn_row.pack(fill="x", padx=round(18 * s), pady=(0, round(16 * s)))
        self._ok_btn = flat_button(
            btn_row, "Rename", "accent", self._on_ok, s,
        )
        self._ok_btn.configure(disabledforeground="#888888")
        self._ok_btn.pack(side="right")
        flat_button(
            btn_row, "Cancel", "ghost", self._on_cancel, s,
        ).pack(side="right", padx=(0, round(8 * s)))

        self._refresh_preview()

    def _refresh_preview(self) -> None:
        new_name = self._entry.get().strip()
        new_slug = slugify_page_name(new_name) if new_name else ""
        if not new_slug or new_slug == self._current_slug:
            # Either empty or same slug — show placeholder + disable
            # the Rename button so the user can't fire a no-op.
            self._preview_label.configure(
                text="  (enter a different name to see the changes)",
                fg=FG_DIM,
            )
            self._ok_btn.configure(state="disabled")
            return
        old = self._current_slug
        bullets = f"  • {old}.ctkproj → {new_slug}.ctkproj"
        self._preview_label.configure(text=bullets, fg=FG)
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
