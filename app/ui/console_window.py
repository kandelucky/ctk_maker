"""In-app preview console.

Floating tool window that captures ``stdout`` / ``stderr`` of the
preview subprocess so the user can read ``print()`` output and
crash tracebacks without a separate Windows ``cmd`` window.

Pairs with ``MainWindow``:
- The buffer (list of ``(stream, ts, line)``) lives on ``MainWindow``
  so it survives close/reopen of this window. ``ts`` is the
  ``HH:MM:SS`` stamp captured at the moment the line was drained
  from the reader queue (always set; rendered as a dim prefix).
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
from app.ui.system_fonts import ui_font

CONSOLE_STDERR_FG = "#ff6b6b"
CONSOLE_MATCH_BG = "#553d00"

MAX_TEXT_LINES = 5000
TRIM_LINES = 500


def _stream_tag(stream: str) -> str:
    """Map a buffer stream value to the ``tk.Text`` tag used to render
    the body of the line. ``stdout`` is the default; ``stderr`` and
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
        self._lock_var: Optional[tk.BooleanVar] = None
        self._search_bar: Optional[tk.Frame] = None
        self._search_entry: Optional[ctk.CTkEntry] = None
        self._search_var: Optional[tk.StringVar] = None
        self._toolbar: Optional[tk.Frame] = None
        super().__init__(parent)
        self.set_on_close(on_close)

    def build_content(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, fg_color=style.PANEL_BG, corner_radius=0)

        self._toolbar = style.make_toolbar(frame)
        self._toolbar.pack(fill="x")
        style.pack_toolbar_button(
            style.secondary_button(self._toolbar, "Clear", command=self._handle_clear),
            first=True,
        )
        style.pack_toolbar_button(
            style.secondary_button(self._toolbar, "Copy", command=self._handle_copy),
        )
        style.pack_toolbar_button(
            style.danger_button(self._toolbar, "Stop", command=self._handle_stop),
        )
        # Auto-scroll lock — when checked, append_line stops auto-
        # scrolling to the end on new output. Useful when the user
        # parks the view at a specific frame mid-flood and doesn't
        # want every new line to yank them back.
        self._lock_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self._toolbar, text="Lock scroll",
            variable=self._lock_var,
            width=90, height=style.BUTTON_HEIGHT,
            checkbox_width=14, checkbox_height=14,
            corner_radius=2,
            fg_color=style.PRIMARY_BG, hover_color=style.PRIMARY_HOVER,
            text_color=style.TREE_FG,
            font=ui_font(11),
        ).pack(side="right", padx=(0, style.TOOLBAR_PADX), pady=style.TOOLBAR_PADY)

        # Search bar — built but not packed; ``_show_search`` slides it
        # in between the toolbar and the textbox on Ctrl+F.
        self._build_search_bar(frame)

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
        self._text.tag_configure("ts", foreground=style.EMPTY_FG)
        self._text.tag_configure("match", background=CONSOLE_MATCH_BG)
        self._text.pack(side="left", fill="both", expand=True)
        # Right-click → Copy / Select all / Clear. The handler also
        # auto-selects the line under the cursor (when no multi-line
        # selection already exists) so a right-click → Copy quickly
        # grabs that single line.
        self._build_context_menu()
        self._text.bind("<Button-3>", self._show_context_menu, add="+")
        # Left-click anywhere clears any selection — Tk's class
        # binding already does this for normal click-to-place-cursor,
        # but the right-click line-select tags ``sel`` programmatically;
        # an explicit remove keeps the contract obvious.
        self._text.bind("<Button-1>", self._on_text_left_click, add="+")
        # Wheel scrolling auto-locks scroll: as soon as the user moves
        # away from the bottom, "Lock scroll" checks itself; the moment
        # they wheel back to the bottom, it unchecks. Bound on the
        # textbox with ``add="+"`` so Tk's default scroll still runs.
        # ``after_idle`` reads ``yview`` AFTER the default handler has
        # advanced the view.
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._text.bind(seq, self._on_wheel_scroll, add="+")

        sb = style.styled_scrollbar(wrap, command=self._text.yview)
        self._text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

        # Ctrl+F opens the search bar; F3 jumps to next match. Bound on
        # the Toplevel so any descendant focus picks them up — bind_all
        # is unnecessary because Console focus is the only context
        # where these chords are meaningful.
        self.bind("<Control-f>", lambda e: self._show_search())
        self.bind("<F3>", lambda e: self._search_next())

        return frame

    # ------------------------------------------------------------------
    # Public API used by MainWindow

    def append_line(self, stream: str, ts: str, line: str) -> None:
        if self._text is None:
            return
        try:
            at_bottom = self._text.yview()[1] >= 0.999
            self._text.configure(state="normal")
            if ts:
                self._text.insert("end", f"[{ts}] ", ("ts",))
            tag = _stream_tag(stream)
            self._text.insert("end", line + "\n", (tag,))
            self._trim_if_needed()
            self._text.configure(state="disabled")
            locked = bool(self._lock_var.get()) if self._lock_var else False
            if at_bottom and not locked:
                self._text.see("end")
        except tk.TclError:
            pass

    def replay(self, lines) -> None:
        """Insert a sequence of ``(stream, ts, line)`` tuples from the
        parent buffer when the window is opened mid-run.
        """
        if self._text is None:
            return
        try:
            self._text.configure(state="normal")
            for stream, ts, line in lines:
                if ts:
                    self._text.insert("end", f"[{ts}] ", ("ts",))
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
            self._text.tag_remove("match", "1.0", "end")
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
        # Auto-select the line under the cursor when no selection is
        # already active. Existing multi-line selections survive — the
        # user may have intentionally selected several lines and is
        # right-clicking to copy them all at once.
        if self._text is not None:
            try:
                self._text.get("sel.first", "sel.last")
                has_sel = True
            except tk.TclError:
                has_sel = False
            if not has_sel:
                try:
                    pos = f"@{event.x},{event.y}"
                    line_start = self._text.index(f"{pos} linestart")
                    line_end = self._text.index(f"{pos} lineend")
                    self._text.tag_add("sel", line_start, line_end)
                except tk.TclError:
                    pass
        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._context_menu.grab_release()
            except tk.TclError:
                pass

    def _on_text_left_click(self, _event) -> None:
        """Clear any tagged selection on left-click. Tk's default class
        binding for ``<Button-1>`` already does this for natural
        click-to-place behaviour, but right-click line-select adds
        ``sel`` programmatically; this keeps the deselect contract
        explicit and survives any future class-binding changes.
        """
        if self._text is None:
            return
        try:
            self._text.tag_remove("sel", "1.0", "end")
        except tk.TclError:
            pass

    def _on_wheel_scroll(self, _event) -> None:
        """Mirror the textbox's bottom-state into ``_lock_var`` after
        the scroll has been applied. Defers via ``after_idle`` because
        the default class binding (which actually moves the view) runs
        AFTER instance binds in the bindtag chain — reading ``yview``
        at this point would still see the pre-scroll position.
        """
        if self._text is None or self._lock_var is None:
            return
        try:
            self.after_idle(self._sync_lock_with_scroll)
        except tk.TclError:
            pass

    def _sync_lock_with_scroll(self) -> None:
        if self._text is None or self._lock_var is None:
            return
        try:
            at_bottom = self._text.yview()[1] >= 0.999
        except tk.TclError:
            return
        # ``set`` only fires the trace if the value actually changed,
        # so this is cheap to call on every wheel event.
        self._lock_var.set(not at_bottom)

    # ------------------------------------------------------------------
    # Search bar

    def _build_search_bar(self, parent) -> None:
        """Construct the slim search row but don't pack it. Packed on
        Ctrl+F via ``_show_search``, hidden via ``_hide_search``.
        """
        bar = tk.Frame(
            parent, bg=style.PANEL_BG, height=34, highlightthickness=0,
        )
        bar.pack_propagate(False)

        self._search_var = tk.StringVar()
        entry = style.styled_entry(
            bar, textvariable=self._search_var,
            placeholder_text="Find…",
        )
        entry.bind("<KeyRelease>", lambda e: self._on_search_changed())
        entry.bind("<Return>", lambda e: (self._search_next(), "break")[1])
        entry.bind("<Escape>", lambda e: self._on_search_escape())
        entry.pack(side="left", padx=(8, 4), pady=2, fill="x", expand=True)

        ctk.CTkButton(
            bar, text="▼ Next", command=self._search_next,
            width=70, height=style.BUTTON_HEIGHT,
            corner_radius=style.BUTTON_RADIUS,
            font=ui_font(style.BUTTON_FONT_SIZE),
            fg_color=style.SECONDARY_BG, hover_color=style.SECONDARY_HOVER,
        ).pack(side="left", padx=(0, 4), pady=2)

        ctk.CTkButton(
            bar, text="×", command=self._hide_search,
            width=28, height=style.BUTTON_HEIGHT,
            corner_radius=style.BUTTON_RADIUS,
            font=ui_font(14),
            fg_color=style.SECONDARY_BG, hover_color=style.SECONDARY_HOVER,
        ).pack(side="right", padx=(0, 8), pady=2)

        self._search_bar = bar
        self._search_entry = entry

    def _show_search(self) -> None:
        if self._search_bar is None or self._toolbar is None:
            return
        try:
            if not self._search_bar.winfo_ismapped():
                self._search_bar.pack(fill="x", after=self._toolbar)
            if self._search_entry is not None:
                self._search_entry.focus_set()
                self._search_entry.select_range(0, "end")
        except tk.TclError:
            pass

    def _hide_search(self) -> None:
        if self._search_bar is None:
            return
        try:
            self._search_bar.pack_forget()
            if self._text is not None:
                self._text.tag_remove("match", "1.0", "end")
                self._text.focus_set()
        except tk.TclError:
            pass

    def _on_search_escape(self) -> str:
        self._hide_search()
        return "break"

    def _on_search_changed(self) -> None:
        if self._search_var is None or self._text is None:
            return
        query = self._search_var.get()
        self._highlight_all(query)
        if query:
            self._jump_to_first_match()

    def _highlight_all(self, query: str) -> None:
        if self._text is None:
            return
        try:
            self._text.tag_remove("match", "1.0", "end")
            if not query:
                return
            start = "1.0"
            while True:
                idx = self._text.search(query, start, "end", nocase=True)
                if not idx:
                    break
                end_idx = f"{idx}+{len(query)}c"
                self._text.tag_add("match", idx, end_idx)
                start = end_idx
        except tk.TclError:
            pass

    def _jump_to_first_match(self) -> None:
        if self._text is None:
            return
        try:
            ranges = self._text.tag_ranges("match")
            if not ranges:
                return
            self._text.mark_set("insert", ranges[0])
            self._text.see(ranges[0])
        except tk.TclError:
            pass

    def _search_next(self) -> None:
        """Advance to the next ``match`` range relative to the current
        cursor, wrapping to the start when past the last hit.
        """
        if self._text is None or self._search_var is None:
            return
        query = self._search_var.get()
        if not query:
            return
        try:
            cursor = self._text.index("insert")
            idx = self._text.search(
                query, f"{cursor}+1c", "end", nocase=True,
            )
            if not idx:
                idx = self._text.search(query, "1.0", "end", nocase=True)
            if not idx:
                return
            end_idx = f"{idx}+{len(query)}c"
            self._text.mark_set("insert", end_idx)
            self._text.see(idx)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------

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
