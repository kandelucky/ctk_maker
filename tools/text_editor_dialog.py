"""Standalone multiline text editor dialog for the CTk Visual Builder.

A modal Toplevel with a `tk.Text` editor. Features:

    - Undo / redo (Ctrl+Z / Ctrl+Y + toolbar icon buttons)
    - Cut / Copy / Paste / Select All (Ctrl+X / C / V / A)
    - Right-click context menu
    - Georgian keyboard layout fallback (routes Ctrl shortcuts by
      hardware keycode)

Result contract:
    dialog = TextEditorDialog(parent, "Title", "initial text")
    dialog.wait_window()
    if dialog.result is not None:
        new_text = dialog.result   # str
"""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

# Allow running standalone from `tools/`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import customtkinter as ctk

from app.ui.icons import load_icon


# =====================================================================
# Colors / fonts
# =====================================================================
BG = "#1e1e1e"
EDITOR_BG = "#2d2d2d"
EDITOR_FG = "#cccccc"
STATUS_BG = "#252526"
STATUS_FG = "#888888"
BORDER = "#3a3a3a"
TOOLBAR_BG = "#2a2a2a"

MENU_STYLE = dict(
    bg="#2d2d30", fg="#cccccc",
    activebackground="#094771", activeforeground="#ffffff",
    bd=0, borderwidth=0, relief="flat",
    font=("Segoe UI", 10),
)


class TextEditorDialog(ctk.CTkToplevel):
    """Modal multiline text editor."""

    def __init__(
        self, parent, title: str, initial_text: str,
        *, width: int = 640, height: int = 480,
    ):
        super().__init__(parent)
        self.title(title)
        self.configure(fg_color=BG)
        self.geometry(f"{width}x{height}")
        self.minsize(440, 340)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.result: str | None = None

        self._icon_undo = load_icon("undo", size=16, color="#cccccc")
        self._icon_redo = load_icon("redo", size=16, color="#cccccc")

        # Build order matters for pack geometry — fixed-size regions
        # (toolbar, status, footer) must be packed BEFORE the expanding
        # editor so they reserve their space first and can't be pushed
        # off-screen when the window shrinks.
        self._build_toolbar()
        self._build_footer()
        self._build_status_bar()
        self._build_editor()

        self._text.insert("1.0", initial_text)
        self._text.edit_reset()
        self._text.focus_set()

        self._update_status()

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    # ------------------------------------------------------------------
    # Toolbar — undo / redo icon buttons
    # ------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(
            self, fg_color=TOOLBAR_BG, height=34, corner_radius=0,
        )
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)

        ctk.CTkButton(
            bar, text="", image=self._icon_undo,
            width=28, height=24, corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._do_undo,
        ).pack(side="left", padx=(12, 0), pady=4)
        ctk.CTkButton(
            bar, text="", image=self._icon_redo,
            width=28, height=24, corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._do_redo,
        ).pack(side="left", padx=(4, 0), pady=4)

        ctk.CTkLabel(
            bar, text="Ctrl+Z / Ctrl+Y",
            font=("Segoe UI", 9), text_color=STATUS_FG,
        ).pack(side="left", padx=(12, 0))

    # ------------------------------------------------------------------
    # Footer — OK / Cancel
    # ------------------------------------------------------------------
    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent", height=44)
        footer.pack(side="bottom", fill="x", padx=12, pady=(8, 10))
        footer.pack_propagate(False)

        ctk.CTkButton(
            footer, text="OK", width=80, height=26, corner_radius=3,
            command=self._on_ok,
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            footer, text="Cancel", width=80, height=26, corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right")

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------
    def _build_status_bar(self) -> None:
        bar = ctk.CTkFrame(
            self, fg_color=STATUS_BG, height=22, corner_radius=0,
        )
        bar.pack(side="bottom", fill="x")
        bar.pack_propagate(False)

        self._status_label = ctk.CTkLabel(
            bar, text="",
            font=("Segoe UI", 9), text_color=STATUS_FG, anchor="w",
        )
        self._status_label.pack(side="left", padx=(12, 0))

    # ------------------------------------------------------------------
    # Editor
    # ------------------------------------------------------------------
    def _build_editor(self) -> None:
        wrap = tk.Frame(self, bg=BG, highlightthickness=0)
        wrap.pack(fill="both", expand=True, padx=12, pady=(8, 0))

        self._text = tk.Text(
            wrap, bg=EDITOR_BG, fg=EDITOR_FG,
            insertbackground=EDITOR_FG,
            font=("Segoe UI", 11), wrap="word",
            bd=0, relief="flat",
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=BORDER, undo=True, maxundo=-1,
            padx=8, pady=6,
        )
        vscroll = ctk.CTkScrollbar(
            wrap, orientation="vertical", command=self._text.yview,
            width=10, corner_radius=4,
            fg_color="#1a1a1a", button_color="#3a3a3a",
            button_hover_color="#4a4a4a",
        )
        self._text.configure(yscrollcommand=vscroll.set)

        self._text.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y", padx=(2, 0))

        self._menu = tk.Menu(self, tearoff=0, **MENU_STYLE)
        self._menu.add_command(
            label="Cut",
            command=lambda: self._text.event_generate("<<Cut>>"),
        )
        self._menu.add_command(
            label="Copy",
            command=lambda: self._text.event_generate("<<Copy>>"),
        )
        self._menu.add_command(
            label="Paste",
            command=lambda: self._text.event_generate("<<Paste>>"),
        )
        self._menu.add_separator()
        self._menu.add_command(label="Select All", command=self._select_all)
        self._menu.add_separator()
        self._menu.add_command(label="Undo", command=self._do_undo)
        self._menu.add_command(label="Redo", command=self._do_redo)

        self._text.bind("<Button-3>", self._show_context_menu)
        self._text.bind("<Control-KeyPress>", self._on_ctrl_keypress)
        for seq in ("<KeyRelease>", "<ButtonRelease-1>", "<<Modified>>"):
            self._text.bind(seq, lambda _e: self._update_status(), add="+")

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------
    def _on_ok(self) -> None:
        self.result = self._text.get("1.0", "end-1c")
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    # ------------------------------------------------------------------
    # Undo / redo
    # ------------------------------------------------------------------
    def _do_undo(self) -> None:
        try:
            self._text.event_generate("<<Undo>>")
        except tk.TclError:
            pass

    def _do_redo(self) -> None:
        try:
            self._text.event_generate("<<Redo>>")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Context menu + shortcuts
    # ------------------------------------------------------------------
    def _show_context_menu(self, event) -> str:
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()
        return "break"

    def _select_all(self) -> str:
        try:
            self._text.tag_add("sel", "1.0", "end-1c")
            self._text.mark_set("insert", "1.0")
            self._text.see("insert")
        except tk.TclError:
            pass
        return "break"

    def _on_ctrl_keypress(self, event) -> str | None:
        kc = event.keycode
        if kc == 67:   # C
            self._text.event_generate("<<Copy>>")
            return "break"
        if kc == 88:   # X
            self._text.event_generate("<<Cut>>")
            return "break"
        if kc == 86:   # V
            self._text.event_generate("<<Paste>>")
            return "break"
        if kc == 65:   # A
            return self._select_all()
        if kc == 90:   # Z
            self._do_undo()
            return "break"
        if kc == 89:   # Y
            self._do_redo()
            return "break"
        return None

    # ------------------------------------------------------------------
    # Status bar update
    # ------------------------------------------------------------------
    def _update_status(self) -> None:
        try:
            self._text.edit_modified(False)
        except tk.TclError:
            pass
        try:
            cursor = self._text.index("insert")
            line, col = cursor.split(".")
            text = self._text.get("1.0", "end-1c")
            chars = len(text)
            lines = text.count("\n") + 1 if text else 1
            msg = (
                f"Line {line}, Col {int(col) + 1}  ·  "
                f"{chars} chars  ·  {lines} lines"
            )
            self._status_label.configure(text=msg)
        except tk.TclError:
            pass


if __name__ == "__main__":
    root = ctk.CTk()
    ctk.set_appearance_mode("dark")
    root.geometry("220x100")
    root.title("Text Editor — Smoke Test")

    def open_editor():
        d = TextEditorDialog(
            root, "Edit Label",
            "Sample text\nSecond line\nThird line with more words",
        )
        d.wait_window()
        print("Result:", repr(d.result))

    ctk.CTkButton(root, text="Open Editor", command=open_editor).pack(
        pady=32,
    )
    root.mainloop()
