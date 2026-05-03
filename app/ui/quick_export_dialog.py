"""Quick Export dialog — single-document, single-question UX.

Shown by File → Export Active Document and the per-form chrome
Export icon. The whole point is "one click and you're done":
- Always exports the named document (Main Window or Dialog).
- Always asset-filters to the form's own references.
- Output lands at ``<project>/exports/<doc_slug>.{py|zip}``.

The dialog asks one thing only: ``.py`` or ``.zip`` (or Cancel).
The body explains *what* it's about to do — different from the
broader Export dialog, which gives full scope / asset / after-action
control. Use this when speed matters more than configuration.

Result is exposed via ``.result`` as one of:
    "py"   — user picked Export as Python
    "zip"  — user picked Export as ZIP
    None   — user cancelled
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from app.ui.dialog_utils import safe_grab_set

DIALOG_W = 500

PANEL_BG = "#252526"
SUBTITLE_FG = "#888888"
HEADER_FG = "#cccccc"
BODY_FG = "#bbbbbb"
PATH_FG = "#888888"
ACCENT = "#5bc0f8"


class QuickExportDialog(ctk.CTkToplevel):
    """Compact "what format?" picker for the Quick Export flow.

    Parameters
    ----------
    parent : Tk widget
        Owner toplevel.
    document_name : str
        Display name of the form being exported (drives the body
        text + the resolved output filename in the preview line).
    output_path_preview : str
        The exact ``<project>/exports/<slug>.*`` path the export
        will write to (extension shown as ``.*`` since the user
        is choosing it). Already truncated for display.
    """

    def __init__(
        self,
        parent,
        document_name: str,
        output_path_preview: str,
    ):
        super().__init__(parent)
        self.result: str | None = None

        self.title("Quick Export")
        self.resizable(False, False)
        self.transient(parent)
        safe_grab_set(self)
        self.configure(fg_color="#1e1e1e")

        self._build(document_name, output_path_preview)
        self.update_idletasks()
        self._center_on_parent(parent)

        self.bind("<Return>", lambda _e: self._pick("py"))
        self.bind("<Escape>", lambda _e: self._pick(None))
        self.protocol("WM_DELETE_WINDOW", lambda: self._pick(None))

    def _build(
        self, document_name: str, output_path_preview: str,
    ) -> None:
        outer = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=6)
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            outer, text="Quick Export",
            font=("Segoe UI", 11, "bold"),
            text_color=SUBTITLE_FG, anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 8))

        # Header row — what's being exported.
        head = ctk.CTkFrame(outer, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(0, 6))
        ctk.CTkLabel(
            head, text="Exporting document:",
            font=("Segoe UI", 10),
            text_color=SUBTITLE_FG, anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            head, text=document_name,
            font=("Segoe UI", 11, "bold"),
            text_color=ACCENT, anchor="w",
        ).pack(side="left", padx=(6, 0))

        # Body — what's included / what's not.
        body = (
            "Only this form's widgets and the assets it references will "
            "be included. Other dialogs and pages stay behind."
        )
        tk.Label(
            outer, text=body,
            font=("Segoe UI", 10), fg=BODY_FG, bg=PANEL_BG,
            anchor="w", justify="left",
            wraplength=DIALOG_W - 60,
        ).pack(fill="x", padx=14, pady=(0, 10))

        # Output preview line so the user knows where the file lands.
        out_row = ctk.CTkFrame(outer, fg_color="transparent")
        out_row.pack(fill="x", padx=14, pady=(0, 12))
        tk.Label(
            out_row, text="Output:",
            font=("Segoe UI", 9), fg=SUBTITLE_FG, bg=PANEL_BG,
        ).pack(side="left")
        tk.Label(
            out_row, text=output_path_preview,
            font=("Segoe UI", 9, "italic"), fg=PATH_FG, bg=PANEL_BG,
        ).pack(side="left", padx=(6, 0))

        # Format explainer block — one line per format so the
        # difference is obvious before the user picks a button.
        ctk.CTkFrame(outer, height=1, fg_color="#333333").pack(
            fill="x", padx=14, pady=(0, 8),
        )
        ctk.CTkLabel(
            outer, text="Choose format:",
            font=("Segoe UI", 10, "bold"),
            text_color=HEADER_FG, anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 6))

        for icon, title, blurb in (
            (
                "•",
                "Python file",
                ".py + sibling assets/ folder — best for editing "
                "and running the code locally.",
            ),
            (
                "•",
                "ZIP archive",
                ".zip bundling code + assets — easy to share or "
                "send (one file, no missing dependencies).",
            ),
        ):
            row = ctk.CTkFrame(outer, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=(0, 4))
            tk.Label(
                row, text=icon,
                font=("Segoe UI", 11), fg=ACCENT, bg=PANEL_BG,
            ).pack(side="left", padx=(2, 6), anchor="n")
            text = ctk.CTkFrame(row, fg_color="transparent")
            text.pack(side="left", fill="x", expand=True)
            tk.Label(
                text, text=title,
                font=("Segoe UI", 10, "bold"),
                fg=HEADER_FG, bg=PANEL_BG, anchor="w",
            ).pack(fill="x")
            tk.Label(
                text, text=blurb,
                font=("Segoe UI", 9), fg=BODY_FG, bg=PANEL_BG,
                anchor="w", justify="left",
                wraplength=DIALOG_W - 80,
            ).pack(fill="x")

        # Footer buttons — Cancel + the two format choices. Python
        # is the primary (default Enter) since it's the more common
        # choice for "I just want the code".
        footer = ctk.CTkFrame(outer, fg_color="transparent")
        footer.pack(fill="x", padx=14, pady=(12, 12), side="bottom")
        ctk.CTkButton(
            footer, text="Export as ZIP",
            width=130, height=30, corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=lambda: self._pick("zip"),
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Export as Python",
            width=150, height=30, corner_radius=4,
            command=lambda: self._pick("py"),
        ).pack(side="right", padx=(0, 8))
        ctk.CTkButton(
            footer, text="Cancel",
            width=80, height=30, corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=lambda: self._pick(None),
        ).pack(side="right", padx=(0, 8))

    def _pick(self, fmt: str | None) -> None:
        self.result = fmt
        self.destroy()

    def _center_on_parent(self, parent) -> None:
        try:
            parent.update_idletasks()
            self.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            dw = self.winfo_width()
            dh = self.winfo_height()
            x = px + (pw - dw) // 2
            y = py + (ph - dh) // 2
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            pass
