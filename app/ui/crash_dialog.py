"""Crash dialog — modal Toplevel that shows a Python traceback inline.

Exists because the original "Unexpected error — see console" dialog
text was a dead end on shortcut launches (``pythonw.exe`` has no
console to see). Used by:

- the two ``log_error("...")`` callsites in ``main_window.py``
  (Open / Recover failures)
- the global ``sys.excepthook`` + ``report_callback_exception`` hooks
  installed in ``main.py``

The dialog renders the traceback in a read-only scrollable Text widget
and offers Copy + Open log + Close buttons. Falls back to a plain
``messagebox.showerror`` when no Tk root is alive (e.g. crash before
``MainWindow.__init__`` returns).
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import customtkinter as ctk

from app.core.logger import crash_log_path
from app.ui.system_fonts import derive_mono_font


def show_crash_dialog(
    parent,
    title: str,
    summary: str,
    traceback_text: str,
) -> None:
    """Show ``traceback_text`` in a modal dialog above ``parent``.

    ``summary`` is a short one-liner shown above the traceback box
    (e.g. "Open failed", "Unexpected error in canvas redraw"). When
    ``parent`` is ``None`` or unusable, falls back to a plain stdlib
    messagebox so even crashes during startup surface something.
    """
    if not _parent_is_alive(parent):
        try:
            messagebox.showerror(
                title,
                f"{summary}\n\nLog: {crash_log_path()}\n\n{traceback_text}",
            )
        except tk.TclError:
            pass
        return
    try:
        dlg = _CrashDialog(parent, title, summary, traceback_text)
        dlg.wait_window()
    except tk.TclError:
        # Parent died mid-build — best effort.
        try:
            messagebox.showerror(title, f"{summary}\n\n{traceback_text}")
        except tk.TclError:
            pass


def _parent_is_alive(parent) -> bool:
    if parent is None:
        return False
    try:
        return bool(parent.winfo_exists())
    except (tk.TclError, AttributeError):
        return False


class _CrashDialog(ctk.CTkToplevel):
    def __init__(self, parent, title: str, summary: str, tb_text: str) -> None:
        super().__init__(parent)
        self.title(title)
        self._tb_text = tb_text
        self.geometry("720x460")
        self.minsize(520, 320)
        self.transient(parent)
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.bind("<Escape>", lambda _e: self.destroy())

        log_path = crash_log_path()

        header = ctk.CTkLabel(
            self, text=summary, anchor="w", font=ctk.CTkFont(size=13, weight="bold"),
        )
        header.pack(fill="x", padx=14, pady=(14, 4))

        sub = ctk.CTkLabel(
            self,
            text=f"Saved to {log_path}",
            anchor="w",
            font=ctk.CTkFont(size=11),
            text_color="#9c9c9c",
        )
        sub.pack(fill="x", padx=14, pady=(0, 8))

        body = ctk.CTkFrame(self, fg_color="#1f1f1f")
        body.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        text = tk.Text(
            body,
            wrap="none",
            bg="#1f1f1f",
            fg="#e6e6e6",
            insertbackground="#e6e6e6",
            relief="flat",
            borderwidth=0,
            font=derive_mono_font(size=10),
        )
        yscroll = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        xscroll = ttk.Scrollbar(body, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        text.insert("1.0", tb_text)
        text.configure(state="disabled")

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=14, pady=(0, 14))
        ctk.CTkButton(
            buttons, text="Copy traceback", width=140,
            command=self._copy,
        ).pack(side="left")
        ctk.CTkButton(
            buttons, text="Open log file", width=140,
            command=lambda: _open_in_os(log_path),
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            buttons, text="Close", width=100,
            command=self.destroy,
        ).pack(side="right")

    def _copy(self) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(self._tb_text)
            self.update_idletasks()
        except tk.TclError:
            pass


def _open_in_os(path: Path) -> None:
    """Open ``path`` in the default OS handler. Best-effort — silent
    on failure (the path is shown in the dialog so the user can copy
    it manually)."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        pass
