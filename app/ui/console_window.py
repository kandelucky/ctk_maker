"""In-app preview console.

Floating tool window that captures ``stdout`` / ``stderr`` of the
preview subprocess so the user can read ``print()`` output and
crash tracebacks without a separate Windows ``cmd`` window.

Pairs with ``MainWindow``:
- The buffer (list of ``(stream, line)``) lives on ``MainWindow`` so it
  survives close/reopen of this window.
- ``MainWindow`` polls a ``queue.Queue`` filled by reader threads and
  calls ``append_line`` on the live window when one exists.
- Window close resets the parent toggle var via the standard
  ``set_on_close`` callback.

Visual base mirrors ``TestWindowC`` (toolbar + Consolas ``tk.Text`` +
scrollbar) but as a real ``ManagedToplevel`` consumer of ``style.py``.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk

from app.ui import style
from app.ui.managed_window import ManagedToplevel

CONSOLE_STDERR_FG = "#ff6b6b"

MAX_TEXT_LINES = 5000
TRIM_LINES = 500


def _stream_tag(stream: str) -> str:
    """Map a buffer stream value to the ``tk.Text`` tag used to render
    it. ``stdout`` is the default (no special tag); ``stderr`` and
    ``separator`` get their own colours.
    """
    if stream in ("stderr", "separator"):
        return stream
    return "stdout"


class ConsoleWindow(ManagedToplevel):
    """Floating preview-console window — toolbar + read-only log text."""

    window_key = "preview_console_window"
    window_title = "Console"
    default_size = (560, 380)
    min_size = (340, 220)
    fg_color = style.PANEL_BG
    panel_padding = (0, 0)
    escape_closes = True

    def __init__(
        self,
        parent,
        on_close: Optional[Callable[[], None]] = None,
        on_clear: Optional[Callable[[], None]] = None,
        on_stop: Optional[Callable[[], None]] = None,
    ):
        self._on_clear = on_clear
        self._on_stop = on_stop
        self._text: Optional[tk.Text] = None
        self._context_menu: Optional[tk.Menu] = None
        super().__init__(parent)
        self.set_on_close(on_close)

    def build_content(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, fg_color=style.PANEL_BG, corner_radius=0)

        bar = style.make_toolbar(frame)
        bar.pack(fill="x")
        style.pack_toolbar_button(
            style.secondary_button(bar, "Clear", command=self._handle_clear),
            first=True,
        )
        style.pack_toolbar_button(
            style.secondary_button(bar, "Copy", command=self._handle_copy),
        )
        style.pack_toolbar_button(
            style.danger_button(bar, "Stop", command=self._handle_stop),
        )

        wrap = tk.Frame(frame, bg=style.BG, highlightthickness=0)
        wrap.pack(fill="both", expand=True)

        self._text = tk.Text(
            wrap,
            bg=style.TREE_BG, fg=style.TREE_FG,
            insertbackground=style.TREE_FG,
            selectbackground=style.TREE_SELECTED_BG,
            selectforeground="#ffffff",
            relief="flat", borderwidth=0,
            font=("Consolas", 10),
            padx=10, pady=8,
            wrap="none",
            state="disabled",
        )
        self._text.tag_configure("stderr", foreground=CONSOLE_STDERR_FG)
        self._text.tag_configure("separator", foreground=style.EMPTY_FG)
        self._text.pack(side="left", fill="both", expand=True)
        # Right-click anywhere in the textbox pops the context menu —
        # Copy / Select all / Clear. Same actions as the toolbar, but
        # closer to the cursor when user is reading a long traceback.
        self._build_context_menu()
        self._text.bind("<Button-3>", self._show_context_menu, add="+")

        sb = style.styled_scrollbar(wrap, command=self._text.yview)
        self._text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

        return frame

    # ------------------------------------------------------------------
    # Public API used by MainWindow

    def append_line(self, stream: str, line: str) -> None:
        if self._text is None:
            return
        try:
            at_bottom = self._text.yview()[1] >= 0.999
            self._text.configure(state="normal")
            tag = _stream_tag(stream)
            self._text.insert("end", line + "\n", (tag,))
            self._trim_if_needed()
            self._text.configure(state="disabled")
            if at_bottom:
                self._text.see("end")
        except tk.TclError:
            pass

    def replay(self, lines) -> None:
        """Insert a sequence of ``(stream, line)`` from the parent
        buffer when the window is opened mid-run.
        """
        if self._text is None:
            return
        try:
            self._text.configure(state="normal")
            for stream, line in lines:
                tag = _stream_tag(stream)
                self._text.insert("end", line + "\n", (tag,))
            self._trim_if_needed()
            self._text.configure(state="disabled")
            self._text.see("end")
        except tk.TclError:
            pass

    def clear(self) -> None:
        if self._text is None:
            return
        try:
            self._text.configure(state="normal")
            self._text.delete("1.0", "end")
            self._text.configure(state="disabled")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------

    def _handle_clear(self) -> None:
        self.clear()
        if self._on_clear is not None:
            try:
                self._on_clear()
            except Exception:
                pass

    def _handle_copy(self) -> None:
        """Copy the current selection if any, else the whole buffer."""
        if self._text is None:
            return
        try:
            text = self._text.get("sel.first", "sel.last")
        except tk.TclError:
            text = self._text.get("1.0", "end-1c")
        if not text:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except tk.TclError:
            pass

    def _handle_select_all(self) -> None:
        if self._text is None:
            return
        try:
            self._text.tag_remove("sel", "1.0", "end")
            self._text.tag_add("sel", "1.0", "end-1c")
            self._text.mark_set("insert", "1.0")
            self._text.focus_set()
        except tk.TclError:
            pass

    def _handle_stop(self) -> None:
        if self._on_stop is None:
            return
        try:
            self._on_stop()
        except Exception:
            pass

    def _build_context_menu(self) -> None:
        """Lazy-build the right-click context menu mirroring the toolbar
        actions. Styled to match the menubar palette directly so this
        module stays a single-import-away from ``style.py`` (no pull
        on ``main_menu.menu_style`` and its host-class deps).
        """
        menu = tk.Menu(
            self, tearoff=0,
            bg=style.HEADER_BG, fg=style.TREE_FG,
            activebackground=style.TREE_SELECTED_BG,
            activeforeground="#ffffff",
            bd=0, borderwidth=0, activeborderwidth=0, relief="flat",
            font=("Segoe UI", 10),
        )
        menu.add_command(label="Copy", command=self._handle_copy)
        menu.add_command(label="Select all", command=self._handle_select_all)
        menu.add_separator()
        menu.add_command(label="Clear", command=self._handle_clear)
        self._context_menu = menu

    def _show_context_menu(self, event) -> None:
        if self._context_menu is None:
            return
        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._context_menu.grab_release()
            except tk.TclError:
                pass

    def _trim_if_needed(self) -> None:
        """Cap the buffer at ``MAX_TEXT_LINES`` by dropping the oldest
        ``TRIM_LINES``. Keeps a long-running preview from balooning the
        textbox without manual Clear.
        """
        if self._text is None:
            return
        try:
            count = int(self._text.index("end-1c").split(".")[0])
        except (tk.TclError, ValueError):
            return
        if count > MAX_TEXT_LINES:
            self._text.delete("1.0", f"{TRIM_LINES + 1}.0")
