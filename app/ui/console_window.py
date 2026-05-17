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

# Per-level colours — info inherits the default fg so a flat preview
# blends in; warnings and errors stand out without screaming. Critical
# is the only entry that adds bold (Unity-style attention spike).
LEVEL_COLOURS = {
    "debug": "#888888",
    "info": None,  # default fg
    "warning": "#ffb84d",
    "error": CONSOLE_STDERR_FG,
    "critical": "#ff3333",
}
SOURCE_PREFIX_FG = "#5dade2"  # editor source marker
TRUNCATED_FG = "#777777"

MAX_TEXT_LINES = 5000
TRIM_LINES = 500
# Hard per-line cap. Tk Text widget slows dramatically on multi-MB
# single lines; truncating at render time keeps the UI fluid while the
# full text remains in the MainWindow buffer for a future "expand"
# feature. Suffix annotates how much was cut.
HARD_LINE_CAP = 10000

# Console toolbar — 5px shorter than the global ``style.BUTTON_HEIGHT``
# / ``TOOLBAR_HEIGHT`` so the log surface gets back the vertical space.
# Local-only override; the global constants stay untouched so the rest
# of the app's toolbars keep their look.
CONSOLE_TOOLBAR_HEIGHT = 34
CONSOLE_BUTTON_HEIGHT = 25
CONSOLE_TOOLBAR_PADY = 2

# Stream → (level, source) classification used for tag application
# at insert time. Levels feed the colour + filter; sources feed the
# editor/preview filter dimension.
_STREAM_LEVEL_TABLE = {
    "stdout": ("info", "preview"),
    "stderr": ("error", "preview"),
    "separator": (None, None),
    "preview-debug": ("debug", "preview"),
    "preview-info": ("info", "preview"),
    "preview-warning": ("warning", "preview"),
    "preview-error": ("error", "preview"),
    "preview-critical": ("critical", "preview"),
    "editor-debug": ("debug", "editor"),
    "editor-info": ("info", "editor"),
    "editor-warning": ("warning", "editor"),
    "editor-error": ("error", "editor"),
    "editor-critical": ("critical", "editor"),
}


def _classify(stream: str) -> tuple[str | None, str | None]:
    """Return ``(level, source)`` for a given stream value, or
    ``(None, None)`` for separators / unknown streams.
    """
    return _STREAM_LEVEL_TABLE.get(stream, ("info", "preview"))


def _tags_for(stream: str) -> tuple[str, ...]:
    """Build the tag tuple applied to a line's body characters. The
    body carries the level tag so filter elide can hide / show it.
    ``stderr`` keeps a colour tag for backwards compatibility when no
    level prefix was sniffed. Source tags are not emitted — the
    Editor / Preview filters were dropped (they were a foot-gun) and
    the visual ``[E]`` prefix is enough source distinction.
    """
    level, _source = _classify(stream)
    tags: list[str] = []
    if level is not None:
        tags.append(f"level-{level}")
    if stream == "separator":
        tags.append("separator")
    elif stream == "stderr":
        # Plain ``stderr`` lines that didn't match a logging-level
        # prefix still render in the error colour.
        tags.append("level-error")
    return tuple(tags)


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
        filter_vars: Optional[dict[str, tk.BooleanVar]] = None,
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
        # Filter BooleanVars (info/warning/error/debug/editor/preview)
        # owned by MainWindow so docked + floating + persistence all
        # share state. None during very-early test usage.
        self._filter_vars = filter_vars or {}
        self._text: Optional[tk.Text] = None
        self._context_menu: Optional[tk.Menu] = None
        self._lock_var: Optional[tk.BooleanVar] = None
        self._search_bar: Optional[tk.Frame] = None
        self._search_entry: Optional[ctk.CTkEntry] = None
        self._search_var: Optional[tk.StringVar] = None
        self._toolbar: Optional[tk.Frame] = None
        # Counter labels — instances created in _build, refreshed by
        # MainWindow via refresh_counters() each time a new line lands.
        self._counter_labels: dict[str, ctk.CTkLabel] = {}
        # Last-render state for the continuation-detector. A line is a
        # continuation of the previous one if both arrive on a plain
        # ``stdout`` / ``stderr`` stream within 500ms — the typical
        # shape of a multi-line traceback. Continuation lines render
        # without the ``[ts]`` prefix so the eye can find where one
        # logical event ends and the next begins. Level-tagged
        # streams (``preview-error``, ``editor-info`` etc.) are
        # discrete events and always show the timestamp.
        self._last_render_stream: Optional[str] = None
        self._last_render_ts_cs: Optional[int] = None
        self._build()

    # ------------------------------------------------------------------
    # Construction

    def _build(self) -> None:
        # Local toolbar frame — 5px shorter than the global toolbar so
        # the log surface reclaims vertical space. ``make_toolbar``
        # hardcodes the global height, so build the bar directly.
        self._toolbar = tk.Frame(
            self, bg=style.TOOLBAR_BG,
            height=CONSOLE_TOOLBAR_HEIGHT, highlightthickness=0,
        )
        self._toolbar.pack_propagate(False)
        self._toolbar.pack(fill="x")

        # Left cluster (LTR): [Copy] [🔍 Search]
        copy_btn = ctk.CTkButton(
            self._toolbar, text="Copy", command=self._handle_copy,
            width=60, height=CONSOLE_BUTTON_HEIGHT,
            corner_radius=style.BUTTON_RADIUS,
            font=ui_font(style.BUTTON_FONT_SIZE),
            fg_color=style.SECONDARY_BG, hover_color=style.SECONDARY_HOVER,
        )
        copy_btn.pack(
            side="left", padx=(style.TOOLBAR_PADX, style.TOOLBAR_BTN_GAP),
            pady=CONSOLE_TOOLBAR_PADY,
        )
        _attach_tooltip(copy_btn, "Copy all to clipboard")
        # Search — icon-only entry point for the slide-in find bar.
        # Same handler as Ctrl+F; surfaces the feature for users who
        # don't know the shortcut.
        search_btn = ctk.CTkButton(
            self._toolbar, text="",
            image=load_icon("search", size=14, color="#cccccc"),
            command=self._show_search,
            width=24, height=CONSOLE_BUTTON_HEIGHT,
            corner_radius=style.BUTTON_RADIUS,
            fg_color=style.SECONDARY_BG, hover_color=style.SECONDARY_HOVER,
        )
        search_btn.pack(
            side="left", padx=(0, style.TOOLBAR_BTN_GAP),
            pady=CONSOLE_TOOLBAR_PADY,
        )
        _attach_tooltip(search_btn, "Search (Ctrl+F)")

        # Filter cluster — four level checkboxes (Info / Warn / Error
        # / Debug) with a separate small badge label for the three
        # severity counters. Counter labels live next to their
        # checkbox so the count is always visible regardless of the
        # filter's checked state (a filtered-out level can still have
        # a non-zero count, which is the whole point of having a
        # counter). Source-side filters (Editor / Preview) were
        # dropped — the ``[E]`` prefix gives the eye enough to tell
        # them apart, and an OR-elided "Editor" tag had a foot-gun
        # mode where flipping it off silently hid every editor line.
        self._counter_labels = {}
        for key, label in (
            ("info", "Info"),
            ("warning", "Warn"),
            ("error", "Error"),
            ("debug", "Debug"),
        ):
            var = self._filter_vars.get(key)
            if var is None:
                # No MainWindow-side state available (e.g. when the
                # panel is used standalone in a test). Create a local
                # var so the checkbox still works visually.
                var = tk.BooleanVar(value=True)
                self._filter_vars[key] = var
            cb = ctk.CTkCheckBox(
                self._toolbar, text=label,
                variable=var,
                width=72, height=CONSOLE_BUTTON_HEIGHT,
                checkbox_width=13, checkbox_height=13,
                corner_radius=2,
                fg_color=style.PRIMARY_BG,
                hover_color=style.PRIMARY_HOVER,
                text_color=style.TREE_FG,
                font=ui_font(11),
            )
            cb.pack(
                side="left",
                padx=(0, 0 if key in ("info", "warning", "error") else 4),
                pady=CONSOLE_TOOLBAR_PADY,
            )
            _attach_tooltip(cb, f"Show {label.lower()} messages")
            if key in ("info", "warning", "error"):
                # Badge label — always visible, always shows the count.
                # Tiny "0" by default so the badge slot is reserved
                # even before any entries arrive (no layout shift on
                # the first log line).
                badge = ctk.CTkLabel(
                    self._toolbar, text="0",
                    width=22, height=CONSOLE_BUTTON_HEIGHT,
                    font=ui_font(10),
                    text_color=style.EMPTY_FG,
                    anchor="w",
                )
                badge.pack(
                    side="left", padx=(0, 4),
                    pady=CONSOLE_TOOLBAR_PADY,
                )
                self._counter_labels[key] = badge

        # Right cluster — widgets built here, packed in reverse-LTR
        # order below. Visual LTR:
        #   [Clear] [Stop] [Auto-clear on preview] [Lock scroll] [×]
        # (× Close and Auto-clear are conditional.)
        clear_btn = ctk.CTkButton(
            self._toolbar, text="Clear", command=self._handle_clear,
            width=60, height=CONSOLE_BUTTON_HEIGHT,
            corner_radius=style.BUTTON_RADIUS,
            font=ui_font(style.BUTTON_FONT_SIZE),
            fg_color=style.SECONDARY_BG, hover_color=style.SECONDARY_HOVER,
        )
        stop_btn = ctk.CTkButton(
            self._toolbar, text="Stop", command=self._handle_stop,
            width=60, height=CONSOLE_BUTTON_HEIGHT,
            corner_radius=style.BUTTON_RADIUS,
            font=ui_font(style.BUTTON_FONT_SIZE),
            fg_color=style.DANGER_BG, hover_color=style.DANGER_HOVER,
        )
        # The Auto-clear BooleanVar is owned by MainWindow so both
        # console forms share state and so the preview-launch hook can
        # read it without reaching into a panel instance.
        auto_clear_cb = None
        if self._clear_on_preview_var is not None:
            auto_clear_cb = ctk.CTkCheckBox(
                self._toolbar, text="Auto-clear on preview",
                variable=self._clear_on_preview_var,
                width=150, height=CONSOLE_BUTTON_HEIGHT,
                checkbox_width=13, checkbox_height=13,
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
            width=85, height=CONSOLE_BUTTON_HEIGHT,
            checkbox_width=13, checkbox_height=13,
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
                width=24, height=CONSOLE_BUTTON_HEIGHT,
                corner_radius=style.BUTTON_RADIUS,
                font=ui_font(13),
                fg_color=style.SECONDARY_BG, hover_color=style.SECONDARY_HOVER,
            )
            close_btn.pack(
                side="right", padx=(0, style.TOOLBAR_PADX),
                pady=CONSOLE_TOOLBAR_PADY,
            )
            _attach_tooltip(close_btn, "Close")
            lock_cb.pack(
                side="right", padx=(0, 4), pady=CONSOLE_TOOLBAR_PADY,
            )
        else:
            lock_cb.pack(
                side="right", padx=(0, style.TOOLBAR_PADX),
                pady=CONSOLE_TOOLBAR_PADY,
            )
        _attach_tooltip(lock_cb, "Don't auto-scroll on new output")
        if auto_clear_cb is not None:
            auto_clear_cb.pack(
                side="right", padx=(0, 4), pady=CONSOLE_TOOLBAR_PADY,
            )
            _attach_tooltip(auto_clear_cb, "Clear log on each preview start")
        stop_btn.pack(
            side="right", padx=(0, 4), pady=CONSOLE_TOOLBAR_PADY,
        )
        _attach_tooltip(stop_btn, "Stop preview process")
        clear_btn.pack(
            side="right", padx=(0, 4), pady=CONSOLE_TOOLBAR_PADY,
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
            # Word-wrap means a multi-KB log line is fully visible
            # instead of disappearing off-screen (the old wrap="none"
            # had no horizontal scrollbar — long lines were invisible).
            wrap="word",
            # Tight spacing keeps the per-line vertical footprint close
            # to the old wrap="none" look so a busy console doesn't
            # waste rows.
            spacing1=1, spacing2=1, spacing3=1,
            state="disabled",
        )
        # Per-level body colours. Info inherits default fg; the rest
        # apply explicit foreground. Critical adds a bold weight.
        for level, colour in LEVEL_COLOURS.items():
            kw: dict = {}
            if colour is not None:
                kw["foreground"] = colour
            if level == "critical":
                kw["font"] = ("Consolas", 10, "bold")
            self._text.tag_configure(f"level-{level}", **kw)
        # ``[E]`` prefix marker on editor lines gets its own coloured
        # tag so it stays cyan regardless of the line's severity
        # colour. (Source-editor / source-preview tags were dropped
        # along with the source filters — see _tags_for.)
        self._text.tag_configure(
            "editor-prefix", foreground=SOURCE_PREFIX_FG,
        )
        self._text.tag_configure(
            "truncated", foreground=TRUNCATED_FG,
            font=("Consolas", 9, "italic"),
        )
        self._text.tag_configure(
            "separator", foreground=style.EMPTY_FG,
        )
        self._text.tag_configure("ts", foreground=style.EMPTY_FG)
        self._text.tag_configure("match", background=CONSOLE_MATCH_BG)
        # Apply persisted filter state up front so initial replay
        # respects the user's last mask without flicker.
        for key, var in self._filter_vars.items():
            self._apply_filter_locally(key, bool(var.get()))
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
            self._render_entry(stream, ts, line)
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
                self._render_entry(stream, ts, line)
            self._trim_if_needed()
            self._text.configure(state="disabled")
            self._text.see("end")
        except tk.TclError:
            pass

    def _render_entry(self, stream: str, ts: str, line: str) -> None:
        """Insert one (stream, ts, line) entry into the Text widget
        with the correct tag set. Caller is responsible for the
        state="normal"/state="disabled" bracket and the trim.

        Long lines (>``HARD_LINE_CAP``) are truncated at render time
        with a dim-italic suffix annotating how much was cut. The
        full text is still in the MainWindow buffer in case a future
        "expand" feature wants it back.

        Continuation lines (multi-line tracebacks dumped to the same
        stream within 500ms) skip the ``[ts]`` and ``[E]`` prefixes
        so the eye can spot event boundaries — see
        ``_should_show_prefix`` for the rule.
        """
        assert self._text is not None
        body_tags = _tags_for(stream)
        is_editor = stream.startswith("editor-")
        show_prefix = self._should_show_prefix(stream, ts)
        if ts and show_prefix:
            self._text.insert("end", f"[{ts}] ", ("ts",) + body_tags)
        if is_editor and show_prefix:
            self._text.insert("end", "[E] ", ("editor-prefix",) + body_tags)
        truncated_extra = len(line) - HARD_LINE_CAP
        visible = line if truncated_extra <= 0 else line[:HARD_LINE_CAP]
        self._text.insert("end", visible, body_tags)
        if truncated_extra > 0:
            self._text.insert(
                "end",
                f"  … [truncated, +{truncated_extra} chars]",
                ("truncated",) + body_tags,
            )
        self._text.insert("end", "\n", body_tags)
        # Remember this entry so the next call can decide whether it
        # is a continuation. ts conversion deferred until needed
        # (a flood of identical-ts entries hits this path).
        self._last_render_stream = stream
        self._last_render_ts_cs = self._ts_to_cs(ts) if ts else None

    @staticmethod
    def _ts_to_cs(ts: str) -> Optional[int]:
        """Parse an ``HH:MM:SS.cc`` timestamp into centiseconds since
        midnight. ``None`` on parse failure — caller treats that as
        "show timestamp" (safer default than hiding).
        """
        try:
            hms, cs = ts.split(".")
            h, m, s = hms.split(":")
            return ((int(h) * 60 + int(m)) * 60 + int(s)) * 100 + int(cs)
        except (ValueError, AttributeError):
            return None

    def _should_show_prefix(self, stream: str, ts: str) -> bool:
        """Decide whether the leading ``[ts]`` / ``[E]`` prefix is
        rendered for this entry. False means "continuation of the
        previous line" — used to fold a multi-line traceback into
        one visual block instead of repeating the timestamp on every
        frame.
        """
        if self._last_render_stream is None:
            return True
        # Level-tagged streams (preview-error, editor-info, ...) are
        # always discrete events. Plain stdout/stderr is the only path
        # that can produce a multi-line continuation.
        if stream not in ("stdout", "stderr"):
            return True
        if stream != self._last_render_stream:
            return True
        if self._last_render_ts_cs is None:
            return True
        cur_cs = self._ts_to_cs(ts)
        if cur_cs is None:
            return True
        # 50 centiseconds = 500ms — wide enough to catch slow
        # traceback emission, narrow enough that two unrelated stderr
        # bursts in the same half-second only happen rarely.
        return abs(cur_cs - self._last_render_ts_cs) > 50

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
        # Reset counter badges to "0" — the source of truth is the
        # MainWindow ``_console_counts`` dict, which Clear also resets.
        for badge in self._counter_labels.values():
            try:
                badge.configure(text="0")
            except tk.TclError:
                pass
        # Drop continuation-detector state so the next line after a
        # Clear starts a fresh group (renders its timestamp).
        self._last_render_stream = None
        self._last_render_ts_cs = None

    def apply_filter(self, key: str, show: bool) -> None:
        """Toggle the elide flag on the level- or source-tag matching
        ``key``. O(1) regardless of buffer size — Tk re-renders the
        affected ranges itself. Called by MainWindow whenever one of
        the shared filter BooleanVars flips.
        """
        if self._text is None:
            return
        self._apply_filter_locally(key, show)

    def _apply_filter_locally(self, key: str, show: bool) -> None:
        """Same as ``apply_filter`` but skips the ``_text is None``
        guard — used during ``_build`` when the widget is being
        constructed and the public method's guard would short-circuit.
        """
        assert self._text is not None
        tag = self._filter_key_to_tag(key)
        if tag is None:
            return
        try:
            self._text.tag_configure(tag, elide=not show)
        except tk.TclError:
            pass

    @staticmethod
    def _filter_key_to_tag(key: str) -> Optional[str]:
        if key in ("debug", "info", "warning", "error"):
            return f"level-{key}"
        return None

    def refresh_counters(self, counts: dict[str, int]) -> None:
        """Push the latest severity totals into the toolbar badge
        labels next to Info / Warn / Error. Counters always show the
        full count regardless of filter state — a filtered-out level
        can still carry hits, and that's exactly what a counter is
        for ("you have 5 hidden errors").
        """
        for key, badge in self._counter_labels.items():
            n = counts.get(key, 0)
            try:
                badge.configure(text=str(n))
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
        menu.add_separator()
        menu.add_command(
            label="Emit colour test palette",
            command=self._emit_palette_test,
        )
        self._context_menu = menu

    def _emit_palette_test(self) -> None:
        """Emit one editor-side line per severity so the user can eye
        the colour assignment without launching a preview. Routes
        through the standard logging path so the lines look exactly
        like real editor logs (same prefix, same tags, same counters).
        """
        import logging
        logger = logging.getLogger("console.palette-test")
        logger.debug("debug message — dim gray")
        logger.info("info message — default foreground")
        logger.warning("warning message — amber")
        logger.error("error message — red")
        logger.critical("critical message — bold red")

    def _entry_range_at(self, index: str) -> tuple[str, str]:
        """Return ``(start, end)`` covering the whole log entry that
        contains ``index``. A log entry is the line that starts with
        ``[hh:mm:ss.cc]`` plus all following continuation lines (a
        multi-line traceback emitted within the 500ms group window
        — see ``_should_show_prefix``). When no prefixed line is
        found backwards, falls back to the clicked line.
        """
        assert self._text is not None
        ts_pat = r"^\[\d\d:\d\d:\d\d\.\d\d\]"
        line_start = self._text.index(f"{index} linestart")
        line_end = self._text.index(f"{index} lineend")
        start = self._text.search(
            ts_pat, f"{line_end}", stopindex="1.0",
            backwards=True, regexp=True,
        ) or line_start
        next_start = self._text.search(
            ts_pat, f"{start}+1l linestart", stopindex="end",
            regexp=True,
        )
        end = (
            self._text.index(f"{next_start}-1c")
            if next_start
            else self._text.index("end-1c")
        )
        return start, end

    def _show_context_menu(self, event) -> None:
        if self._context_menu is None:
            return "break"
        if self._text is not None:
            try:
                click_idx = self._text.index(f"@{event.x},{event.y}")
                keep_selection = False
                try:
                    sel_first = self._text.index("sel.first")
                    sel_last = self._text.index("sel.last")
                    if (self._text.compare(sel_first, "<=", click_idx)
                            and self._text.compare(click_idx, "<", sel_last)):
                        keep_selection = True
                except tk.TclError:
                    pass
                if not keep_selection:
                    start, end = self._entry_range_at(click_idx)
                    self._text.tag_remove("sel", "1.0", "end")
                    self._text.tag_add("sel", start, end)
            except tk.TclError:
                pass
        try:
            self._context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                self._context_menu.grab_release()
            except tk.TclError:
                pass
        return "break"

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
        filter_vars: Optional[dict[str, tk.BooleanVar]] = None,
    ):
        self._on_clear_cb = on_clear
        self._on_stop_cb = on_stop
        self._clear_on_preview_var = clear_on_preview_var
        self._filter_vars = filter_vars or {}
        self._panel: Optional[ConsolePanel] = None
        super().__init__(parent)
        self.set_on_close(on_close)

    def build_content(self) -> ctk.CTkFrame:
        self._panel = ConsolePanel(
            self, on_clear=self._on_clear_cb, on_stop=self._on_stop_cb,
            clear_on_preview_var=self._clear_on_preview_var,
            filter_vars=self._filter_vars,
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

    def apply_filter(self, key: str, show: bool) -> None:
        if self._panel is not None:
            self._panel.apply_filter(key, show)

    def refresh_counters(self, counts: dict[str, int]) -> None:
        if self._panel is not None:
            self._panel.refresh_counters(counts)
