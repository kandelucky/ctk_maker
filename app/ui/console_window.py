"""In-app preview console.

Shows ``stdout`` / ``stderr`` of the preview subprocess so the user
can read ``print()`` output and crash tracebacks without a separate
Windows ``cmd`` window.

Two coordinated forms:
- ``ConsolePanel`` — embeddable ``ctk.CTkFrame``. Used by the docked
  bottom dock in ``MainWindow``.
- ``ConsoleWindow`` — floating ``ManagedToplevel`` wrapper. Builds a
  ``ConsolePanel`` as its content frame and forwards the public API
  (``append_line`` / ``replay`` / ``clear``) to it.

Both forms share one buffer that lives on ``MainWindow`` (a list of
``(stream, ts, line)`` tuples). The parent's queue drainer pushes new
entries to every live form, so docked + floating can be open
simultaneously and stay in sync. ``ts`` is the ``HH:MM:SS.cc`` stamp
captured at the moment the line was drained from the reader queue
(always set; rendered as a dim prefix).

Visual base mirrors ``TestWindowC`` (toolbar + Consolas ``tk.Text`` +
scrollbar) styled via ``style.py``.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk

from app.ui import style
from app.ui.icons import load_icon
from app.ui.managed_window import ManagedToplevel
from app.ui.system_fonts import ui_font
from app.ui.toolbar import _attach_tooltip

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


class ConsolePanel(ctk.CTkFrame):
    """Embeddable console UI — toolbar + read-only log text + search.

    Used both as the docked bottom panel inside ``MainWindow`` and as
    the content frame of the floating ``ConsoleWindow``. All actual
    behavior (append, search, copy, clear, scroll-lock, context menu)
    lives here; ``ConsoleWindow`` is a thin floating wrapper.
    """

    def __init__(
        self,
        parent,
        on_clear: Optional[Callable[[], None]] = None,
        on_stop: Optional[Callable[[], None]] = None,
        on_close: Optional[Callable[[], None]] = None,
        clear_on_preview_var: Optional[tk.BooleanVar] = None,
    ):
        super().__init__(parent, fg_color=style.PANEL_BG, corner_radius=0)
        self._on_clear = on_clear
        self._on_stop = on_stop
        # ``on_close`` is only meaningful for the docked form — the
        # floating ConsoleWindow closes via the OS title bar so its
        # wrapper leaves this None and the toolbar omits the X.
        self._on_close = on_close
        # Shared across docked + floating forms by MainWindow so both
        # checkboxes flip together and the chosen state is what the
        # preview-launch hook reads.
        self._clear_on_preview_var = clear_on_preview_var
        self._text: Optional[tk.Text] = None
        self._context_menu: Optional[tk.Menu] = None
        self._lock_var: Optional[tk.BooleanVar] = None
        self._search_bar: Optional[tk.Frame] = None
        self._search_entry: Optional[ctk.CTkEntry] = None
        self._search_var: Optional[tk.StringVar] = None
        self._toolbar: Optional[tk.Frame] = None
        self._build()

    # ------------------------------------------------------------------
    # Construction

    def _build(self) -> None:
        self._toolbar = style.make_toolbar(self)
        self._toolbar.pack(fill="x")

        # Left cluster (LTR): [Copy] [🔍 Search]
        copy_btn = style.secondary_button(
            self._toolbar, "Copy", command=self._handle_copy,
        )
        style.pack_toolbar_button(copy_btn, first=True)
        _attach_tooltip(copy_btn, "Copy all to clipboard")
        # Search — icon-only entry point for the slide-in find bar.
        # Same handler as Ctrl+F; surfaces the feature for users who
        # don't know the shortcut.
        search_btn = ctk.CTkButton(
            self._toolbar, text="",
            image=load_icon("search", size=16, color="#cccccc"),
            command=self._show_search,
            width=28, height=style.BUTTON_HEIGHT,
            corner_radius=style.BUTTON_RADIUS,
            fg_color=style.SECONDARY_BG, hover_color=style.SECONDARY_HOVER,
        )
        style.pack_toolbar_button(search_btn)
        _attach_tooltip(search_btn, "Search (Ctrl+F)")

        # Right cluster — widgets built here, packed in reverse-LTR
        # order below. Visual LTR:
        #   [Clear] [Stop] [Auto-clear on preview] [Lock scroll] [×]
        # (× Close and Auto-clear are conditional.)
        clear_btn = style.secondary_button(
            self._toolbar, "Clear", command=self._handle_clear,
        )
        stop_btn = style.danger_button(
            self._toolbar, "Stop", command=self._handle_stop,
        )
        # The Auto-clear BooleanVar is owned by MainWindow so both
        # console forms share state and so the preview-launch hook can
        # read it without reaching into a panel instance.
        auto_clear_cb = None
        if self._clear_on_preview_var is not None:
            auto_clear_cb = ctk.CTkCheckBox(
                self._toolbar, text="Auto-clear on preview",
                variable=self._clear_on_preview_var,
                width=160, height=style.BUTTON_HEIGHT,
                checkbox_width=14, checkbox_height=14,
                corner_radius=2,
                fg_color=style.PRIMARY_BG, hover_color=style.PRIMARY_HOVER,
                text_color=style.TREE_FG,
                font=ui_font(11),
            )
        # Auto-scroll lock — when checked, append_line stops auto-
        # scrolling to the end on new output. Useful when the user
        # parks the view at a specific frame mid-flood and doesn't
        # want every new line to yank them back.
        self._lock_var = tk.BooleanVar(value=False)
        lock_cb = ctk.CTkCheckBox(
            self._toolbar, text="Lock scroll",
            variable=self._lock_var,
            width=90, height=style.BUTTON_HEIGHT,
            checkbox_width=14, checkbox_height=14,
            corner_radius=2,
            fg_color=style.PRIMARY_BG, hover_color=style.PRIMARY_HOVER,
            text_color=style.TREE_FG,
            font=ui_font(11),
        )

        # Pack right cluster: ``side="right"`` stacks right-to-left, so
        # the rightmost slot is packed first. Order: × → Lock →
        # Auto-clear → Stop → Clear (leftmost of right cluster).
        if self._on_close is not None:
            close_btn = ctk.CTkButton(
                self._toolbar, text="×", command=self._handle_close,
                width=28, height=style.BUTTON_HEIGHT,
                corner_radius=style.BUTTON_RADIUS,
                font=ui_font(14),
                fg_color=style.SECONDARY_BG, hover_color=style.SECONDARY_HOVER,
            )
            close_btn.pack(
                side="right", padx=(0, style.TOOLBAR_PADX),
                pady=style.TOOLBAR_PADY,
            )
            _attach_tooltip(close_btn, "Close")
            lock_cb.pack(
                side="right", padx=(0, 4), pady=style.TOOLBAR_PADY,
            )
        else:
            lock_cb.pack(
                side="right", padx=(0, style.TOOLBAR_PADX),
                pady=style.TOOLBAR_PADY,
            )
        _attach_tooltip(lock_cb, "Don't auto-scroll on new output")
        if auto_clear_cb is not None:
            auto_clear_cb.pack(
                side="right", padx=(0, 4), pady=style.TOOLBAR_PADY,
            )
            _attach_tooltip(auto_clear_cb, "Clear log on each preview start")
        stop_btn.pack(
            side="right", padx=(0, 4), pady=style.TOOLBAR_PADY,
        )
        _attach_tooltip(stop_btn, "Stop preview process")
        clear_btn.pack(
            side="right", padx=(0, 4), pady=style.TOOLBAR_PADY,
        )
        _attach_tooltip(clear_btn, "Clear log")

        # Search bar — built but not packed; ``_show_search`` slides it
        # in between the toolbar and the textbox on Ctrl+F.
        self._build_search_bar(self)

        wrap = tk.Frame(self, bg=style.BG, highlightthickness=0)
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
        self._build_context_menu()
        self._text.bind("<Button-3>", self._show_context_menu, add="+")
        self._text.bind("<Button-1>", self._on_text_left_click, add="+")
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._text.bind(seq, self._on_wheel_scroll, add="+")
        # Ctrl+F / F3 are bound on the textbox so they fire whenever
        # the user has focus inside the log — works for both docked
        # and floating forms without needing a Toplevel-level bind
        # (a docked Frame isn't in its children's bindtag chain by
        # default, so binding on the panel itself wouldn't fire from
        # the textbox).
        self._text.bind("<Control-f>", lambda e: self._show_search())
        self._text.bind("<F3>", lambda e: self._search_next())

        sb = style.styled_scrollbar(wrap, command=self._text.yview)
        self._text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

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
        parent buffer when the panel is opened mid-run.
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
    # Toolbar handlers

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

    def _handle_close(self) -> None:
        if self._on_close is None:
            return
        try:
            self._on_close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Right-click menu + click handlers

    def _build_context_menu(self) -> None:
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
        if self._text is None:
            return
        try:
            self._text.tag_remove("sel", "1.0", "end")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Scroll lock

    def _on_wheel_scroll(self, _event) -> None:
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
        self._lock_var.set(not at_bottom)

    # ------------------------------------------------------------------
    # Search bar

    def _build_search_bar(self, parent) -> None:
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
        if self._text is None:
            return
        try:
            count = int(self._text.index("end-1c").split(".")[0])
        except (tk.TclError, ValueError):
            return
        if count > MAX_TEXT_LINES:
            self._text.delete("1.0", f"{TRIM_LINES + 1}.0")


class ConsoleWindow(ManagedToplevel):
    """Floating wrapper around ``ConsolePanel`` (View → Console floating).

    Built so MainWindow can have one or both forms alive at once
    (docked panel + floating window) sharing a single buffer. The
    public API (``append_line`` / ``replay`` / ``clear``) just forwards
    to the contained panel.
    """

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
        clear_on_preview_var: Optional[tk.BooleanVar] = None,
    ):
        self._on_clear_cb = on_clear
        self._on_stop_cb = on_stop
        self._clear_on_preview_var = clear_on_preview_var
        self._panel: Optional[ConsolePanel] = None
        super().__init__(parent)
        self.set_on_close(on_close)

    def build_content(self) -> ctk.CTkFrame:
        self._panel = ConsolePanel(
            self, on_clear=self._on_clear_cb, on_stop=self._on_stop_cb,
            clear_on_preview_var=self._clear_on_preview_var,
        )
        return self._panel

    # Forward the public API to the embedded panel.
    def append_line(self, stream: str, ts: str, line: str) -> None:
        if self._panel is not None:
            self._panel.append_line(stream, ts, line)

    def replay(self, lines) -> None:
        if self._panel is not None:
            self._panel.replay(lines)

    def clear(self) -> None:
        if self._panel is not None:
            self._panel.clear()
