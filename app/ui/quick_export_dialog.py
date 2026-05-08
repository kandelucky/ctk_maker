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

from app.ui.managed_window import ManagedToplevel
from app.ui.system_fonts import ui_font

DIALOG_W = 500

PANEL_BG = "#252526"
SUBTITLE_FG = "#888888"
HEADER_FG = "#cccccc"
BODY_FG = "#bbbbbb"
PATH_FG = "#888888"
ACCENT = "#5bc0f8"


class QuickExportDialog(ManagedToplevel):
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

    window_title = "Quick Export"
    default_size = (DIALOG_W, 480)
    min_size = (DIALOG_W - 20, 440)
    fg_color = "#1e1e1e"
    panel_padding = (0, 0)
    modal = True
    window_resizable = (False, False)

    def __init__(
        self,
        parent,
        document_name: str,
        output_path_preview: str,
    ):
        self.result: str | None = None
        self._document_name = document_name
        self._output_path_preview = output_path_preview
        super().__init__(parent)
        self.bind("<Return>", lambda _e: self._pick("py"))

    def default_offset(self, parent) -> tuple[int, int]:
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            w, h = self.default_size
            return (
                max(0, px + (pw - w) // 2),
                max(0, py + (ph - h) // 2),
            )
        except tk.TclError:
            return (100, 100)

    def build_content(self) -> ctk.CTkFrame:
        container = ctk.CTkFrame(self, fg_color="transparent")
        outer = ctk.CTkFrame(container, fg_color=PANEL_BG, corner_radius=6)
        outer.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(
            outer, text="Quick Export",
            font=ui_font(11, "bold"),
            text_color=SUBTITLE_FG, anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 8))

        # Header row — what's being exported.
        head = ctk.CTkFrame(outer, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(0, 6))
        ctk.CTkLabel(
            head, text="Exporting document:",
            font=ui_font(10),
            text_color=SUBTITLE_FG, anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            head, text=self._document_name,
            font=ui_font(11, "bold"),
            text_color=ACCENT, anchor="w",
        ).pack(side="left", padx=(6, 0))

        # Body — what's included / what's not.
        body_text = (
            "Only this form's widgets and the assets it references will "
            "be included. Other dialogs and pages stay behind."
        )
        tk.Label(
            outer, text=body_text,
            font=ui_font(10), fg=BODY_FG, bg=PANEL_BG,
            anchor="w", justify="left",
            wraplength=DIALOG_W - 60,
        ).pack(fill="x", padx=14, pady=(0, 10))

        # Output preview line so the user knows where the file lands.
        out_row = ctk.CTkFrame(outer, fg_color="transparent")
        out_row.pack(fill="x", padx=14, pady=(0, 12))
        tk.Label(
            out_row, text="Output:",
            font=ui_font(9), fg=SUBTITLE_FG, bg=PANEL_BG,
        ).pack(side="left")
        tk.Label(
            out_row, text=self._output_path_preview,
            font=ui_font(9, "italic"), fg=PATH_FG, bg=PANEL_BG,
        ).pack(side="left", padx=(6, 0))

        # Format explainer block — one line per format so the
        # difference is obvious before the user picks a button.
        ctk.CTkFrame(outer, height=1, fg_color="#333333").pack(
            fill="x", padx=14, pady=(0, 8),
        )
        ctk.CTkLabel(
            outer, text="Choose format:",
            font=ui_font(10, "bold"),
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
                font=ui_font(11), fg=ACCENT, bg=PANEL_BG,
            ).pack(side="left", padx=(2, 6), anchor="n")
            text = ctk.CTkFrame(row, fg_color="transparent")
            text.pack(side="left", fill="x", expand=True)
            tk.Label(
                text, text=title,
                font=ui_font(10, "bold"),
                fg=HEADER_FG, bg=PANEL_BG, anchor="w",
            ).pack(fill="x")
            tk.Label(
                text, text=blurb,
                font=ui_font(9), fg=BODY_FG, bg=PANEL_BG,
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
        return container

    def _pick(self, fmt: str | None) -> None:
        self.result = fmt
        self.destroy()
