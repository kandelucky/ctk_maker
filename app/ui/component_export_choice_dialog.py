"""Modal — first step of the Export flow. Asks whether the export is
for personal use (existing local-save dialog) or for publishing to the
public Component Library (placeholder window for now).
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from pathlib import Path
from typing import Any

import customtkinter as ctk

from app.ui.dialog_utils import safe_grab_set
from app.ui.system_fonts import derive_mono_font


COMPONENT_LIBRARY_URL = (
    "https://kandelucky.github.io/ctkMaker-component-library/"
)


class ComponentExportChoiceDialog(ctk.CTkToplevel):
    def __init__(self, parent, source_path: Path):
        super().__init__(parent)
        self.title("Export component")
        self.resizable(False, False)
        self.transient(parent)
        safe_grab_set(self)

        self._source_path = source_path
        self._parent = parent
        self.result: str | None = None  # "personal" | "publish" | None

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(padx=24, pady=(20, 8), fill="x")

        ctk.CTkLabel(
            body,
            text="Share your component",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#e6e6e6", anchor="w",
        ).pack(anchor="w", pady=(0, 8))

        ctk.CTkLabel(
            body,
            text=(
                "Published components appear in the public CTkMaker "
                "library — credited to you, under your chosen license. "
                "Others can discover and reuse your work, and you "
                "benefit from theirs."
            ),
            font=ctk.CTkFont(size=10),
            text_color="#bdbdbd",
            justify="left", anchor="w", wraplength=440,
        ).pack(anchor="w", pady=(0, 14))

        ctk.CTkButton(
            body, text="🌐  Visit Component Library",
            width=240, height=34, corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._on_visit_library,
        ).pack(pady=(0, 16))

        sep = ctk.CTkFrame(body, height=1, fg_color="#3a3a3a")
        sep.pack(fill="x", pady=(0, 14))

        choices = ctk.CTkFrame(body, fg_color="transparent")
        choices.pack(fill="x", pady=(0, 4))
        choices.grid_columnconfigure(0, weight=1, uniform="choice")
        choices.grid_columnconfigure(1, weight=1, uniform="choice")

        personal_col = ctk.CTkFrame(choices, fg_color="transparent")
        personal_col.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        ctk.CTkButton(
            personal_col, text="Personal Use",
            height=44, corner_radius=6,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            text_color="#e6e6e6",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._on_personal,
        ).pack(fill="x")
        ctk.CTkLabel(
            personal_col,
            text="Saves the .ctkcomp file\nlocally for your own use.",
            font=ctk.CTkFont(size=9),
            text_color="#888888",
            justify="center",
        ).pack(pady=(6, 0))

        publish_col = ctk.CTkFrame(choices, fg_color="transparent")
        publish_col.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        ctk.CTkButton(
            publish_col, text="Publish to Community",
            height=44, corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._on_publish,
        ).pack(fill="x")
        ctk.CTkLabel(
            publish_col,
            text="Prepares the file with license\n& attribution metadata.",
            font=ctk.CTkFont(size=9),
            text_color="#888888",
            justify="center",
        ).pack(pady=(6, 0))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(8, 18))
        ctk.CTkButton(
            footer, text="Cancel", width=90, height=30,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right")

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.after(100, self._center_on_parent)

    def _on_visit_library(self) -> None:
        try:
            webbrowser.open(COMPONENT_LIBRARY_URL, new=2)
        except Exception:
            pass

    def _on_personal(self) -> None:
        self.result = "personal"
        self.destroy()

    def _on_publish(self) -> None:
        self.result = "publish"
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
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


MIT_LICENSE_TEXT = """MIT License

Copyright (c) <year> <author>

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."""


class _MITTextWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("MIT License — full text")
        self.geometry("560x440")
        self.transient(parent)
        safe_grab_set(self)
        self.configure(fg_color="#1a1a1a")

        textbox = ctk.CTkTextbox(
            self, font=derive_mono_font(size=10),  # type: ignore[arg-type]
            fg_color="#111111", text_color="#cfcfcf",
            wrap="word",
        )
        textbox.pack(fill="both", expand=True, padx=14, pady=(14, 8))
        textbox.insert("1.0", MIT_LICENSE_TEXT)
        textbox.configure(state="disabled")

        ctk.CTkButton(
            self, text="Close", width=90, height=30,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self.destroy,
        ).pack(side="bottom", pady=(0, 14))
        self.bind("<Escape>", lambda _e: self.destroy())


class ComponentPublishLicenseDialog(ctk.CTkToplevel):
    """License-agreement gate before the actual Publish form. Three
    required confirmations + MIT-text viewer. ``result`` is True when
    the user accepts.
    """

    def __init__(self, parent, source_path: Path):
        super().__init__(parent)
        self.title("License agreement")
        self.resizable(False, False)
        self.transient(parent)
        safe_grab_set(self)
        self.configure(fg_color="#1a1a1a")

        self._source_path = source_path
        self.result: bool = False

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(padx=24, pady=(20, 8), fill="x")

        ctk.CTkLabel(
            body,
            text="License agreement",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#e6e6e6", anchor="w",
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            body,
            text="By publishing, you confirm:",
            font=ctk.CTkFont(size=10),
            text_color="#bdbdbd", anchor="w",
        ).pack(anchor="w", pady=(0, 14))

        self._var_rights = tk.BooleanVar(value=False)
        self._var_mit = tk.BooleanVar(value=False)
        self._var_responsibility = tk.BooleanVar(value=False)

        check_kwargs: dict[str, Any] = dict(
            font=ctk.CTkFont(size=10),
            text_color="#dcdcdc",
            checkbox_width=18, checkbox_height=18,
            corner_radius=3,
            command=self._refresh_accept,
        )

        ctk.CTkCheckBox(
            body,
            text=(
                "I have the right to redistribute everything bundled "
                "in this component (my own work, or assets I'm "
                "permitted to redistribute)."
            ),
            variable=self._var_rights,
            **check_kwargs,
        ).pack(anchor="w", pady=(0, 12), fill="x")

        ctk.CTkCheckBox(
            body,
            text=(
                "I release this component under the MIT license. "
                "Anyone can use, modify, and redistribute it. I "
                "retain copyright; my name appears as the author."
            ),
            variable=self._var_mit,
            **check_kwargs,
        ).pack(anchor="w", pady=(0, 12), fill="x")

        ctk.CTkCheckBox(
            body,
            text=(
                "Responsibility for the contents stays with me, "
                "the submitter."
            ),
            variable=self._var_responsibility,
            **check_kwargs,
        ).pack(anchor="w", pady=(0, 14), fill="x")

        # CTkCheckBox doesn't natively wrap; nudge the inner label.
        for child in body.winfo_children():
            if isinstance(child, ctk.CTkCheckBox):
                label = getattr(child, "_text_label", None)
                if label is not None:
                    label.configure(wraplength=420, justify="left")

        ctk.CTkButton(
            body, text="Read full MIT text",
            width=170, height=28, corner_radius=4,
            fg_color="#2b2b2b", hover_color="#3a3a3a",
            text_color="#9ec3ff",
            font=ctk.CTkFont(size=10, underline=True),
            command=self._show_mit_text,
        ).pack(anchor="w", pady=(0, 4))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(8, 18))
        self._accept_btn = ctk.CTkButton(
            footer, text="Accept & continue",
            width=170, height=32, corner_radius=4,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._on_accept,
            state="disabled",
        )
        self._accept_btn.pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel", width=90, height=32,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.after(100, self._center_on_parent)

    def _refresh_accept(self) -> None:
        all_checked = (
            self._var_rights.get()
            and self._var_mit.get()
            and self._var_responsibility.get()
        )
        self._accept_btn.configure(
            state="normal" if all_checked else "disabled",
        )

    def _show_mit_text(self) -> None:
        _MITTextWindow(self)

    def _on_accept(self) -> None:
        self.result = True
        self.destroy()

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


def run_export_flow(parent, source_path: Path) -> None:
    """Run the full Export flow: choice dialog → either personal
    export dialog or publish placeholder. Blocks until the chosen
    sub-dialog closes.
    """
    choice = ComponentExportChoiceDialog(parent, source_path)
    parent.wait_window(choice)
    if choice.result == "personal":
        from app.ui.component_export_dialog import ComponentExportDialog
        dlg = ComponentExportDialog(parent, source_path)
        parent.wait_window(dlg)
    elif choice.result == "publish":
        license_dlg = ComponentPublishLicenseDialog(parent, source_path)
        parent.wait_window(license_dlg)
        if not license_dlg.result:
            return
        from app.ui.component_publish_form_dialog import (
            ComponentPublishFormDialog,
        )
        form = ComponentPublishFormDialog(parent, source_path)
        parent.wait_window(form)
