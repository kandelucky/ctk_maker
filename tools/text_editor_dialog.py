"""Standalone multiline text editor dialog for CTkMaker.

A modal Toplevel with a `tk.Text` editor. Features:

    - Undo / redo (Ctrl+Z / Ctrl+Y + toolbar icon buttons)
    - Cut / Copy / Paste / Select All (Ctrl+X / C / V / A)
    - Right-click context menu
    - Non-Latin keyboard layout fallback (routes Ctrl shortcuts by
      hardware keycode)
    - Optional code-hint toolbar (``show_hints=True``): inserts
      common pseudo-code blocks (if/else, set/get, ...) and supports
      user-defined custom hints persisted in global settings.

Result contract:
    dialog = TextEditorDialog(parent, "Title", "initial text")
    dialog.wait_window()
    if dialog.result is not None:
        new_text = dialog.result   # str
"""
from __future__ import annotations

import re
import sys
import tkinter as tk
from pathlib import Path

# Allow running standalone from `tools/`.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import customtkinter as ctk

from app.ui.dialog_utils import safe_grab_set
from app.ui.icons import load_icon
from app.ui.toolbar import _attach_tooltip
from app.core.settings import (
    load_description_hints, save_description_hints,
)
from customtkinter.windows.widgets.utility.rich_text_parser import (
    COLOR_MAP, parse_color,
)


# Pseudo-code templates inserted by toolbar block buttons.
# Pairs ([{label, template}, ...]) become a popup menu on click.
# Single templates insert directly at cursor.
HINT_BLOCKS: list[tuple[str, list[tuple[str, str]]]] = [
    ("if/else", [
        ("if",   "if <condition>: <action>"),
        ("else", "else: <action>"),
    ]),
    ("inc/dec", [
        ("increment", "<variable> += 1"),
        ("decrement", "<variable> -= 1"),
    ]),
    ("set/get", [
        ("set", "set <variable> = <value>"),
        ("get", "get <variable>"),
    ]),
    ("show/hide", [
        ("show", "show <widget>"),
        ("hide", "hide <widget>"),
    ]),
    ("goto", [("goto", "goto <page>")]),
    ("calc", [("calc", "calc <expression>")]),
]
_PLACEHOLDER_RE = re.compile(r"<[^<>\n]+>")


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
    disabledforeground="#666666",
    bd=0, borderwidth=0, relief="flat",
    font=("Segoe UI", 10),
)


class TextEditorDialog(ctk.CTkToplevel):
    """Modal multiline text editor."""

    def __init__(
        self, parent, title: str, initial_text: str,
        *, width: int = 640, height: int = 480,
        show_hints: bool = False,
        rich_text: bool = False,
    ):
        super().__init__(parent)
        self.title(title)
        self.configure(fg_color=BG)
        self.geometry(f"{width}x{height}")
        min_w = 440
        if show_hints:
            min_w = max(min_w, 560)
        if rich_text:
            min_w = max(min_w, 620)
        self.minsize(min_w, 340)
        self.resizable(True, True)
        self.transient(parent)
        safe_grab_set(self)

        self.result: str | None = None
        self._show_hints = show_hints
        self._rich_text = rich_text

        self._icon_undo = load_icon("undo", size=16, color="#cccccc")
        self._icon_redo = load_icon("redo", size=16, color="#cccccc")
        self._icon_plus = (
            load_icon("plus", size=14, color="#cccccc")
            if show_hints else None
        )

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
        # Park cursor at end so a button press before any click/keystroke
        # appends rather than inserting at column 0.
        self._text.mark_set("insert", "end-1c")
        self._text.focus_set()

        if self._rich_text:
            self._text.bind(
                "<Double-Button-1>", self._select_word_no_tags,
            )

        self._update_status()

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    # ------------------------------------------------------------------
    # Toolbar — undo / redo icon buttons (+ optional hint blocks)
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

        if self._show_hints:
            self._build_hint_blocks(bar)
            self._build_custom_hints(bar)

        if self._rich_text:
            self._build_rich_text_buttons(bar)

    # ------------------------------------------------------------------
    # Rich-text toolbar — tag insertion buttons (b, i, u, color, bg, size)
    # ------------------------------------------------------------------
    def _build_rich_text_buttons(self, bar) -> None:
        sep = ctk.CTkFrame(bar, fg_color=BORDER, width=1, height=20)
        sep.pack(side="left", padx=(12, 8), pady=7)

        common = dict(
            width=28, height=24, corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
        )
        btn_b = ctk.CTkButton(
            bar, text="B", font=("Segoe UI", 11, "bold"),
            command=lambda: self._wrap_tag("b"), **common,
        )
        btn_b.pack(side="left", padx=(0, 4), pady=4)
        _attach_tooltip(btn_b, "Bold — <b>text</b>")

        btn_i = ctk.CTkButton(
            bar, text="I", font=("Segoe UI", 11, "italic"),
            command=lambda: self._wrap_tag("i"), **common,
        )
        btn_i.pack(side="left", padx=(0, 4), pady=4)
        _attach_tooltip(btn_i, "Italic — <i>text</i>")

        btn_u = ctk.CTkButton(
            bar, text="U", font=("Segoe UI", 11, "underline"),
            command=lambda: self._wrap_tag("u"), **common,
        )
        btn_u.pack(side="left", padx=(0, 4), pady=4)
        _attach_tooltip(btn_u, "Underline — <u>text</u>")

        size_btn = ctk.CTkButton(
            bar, text="size", font=("Segoe UI", 10),
            width=0, height=24, corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=lambda: self._wrap_tag("size", "13"),
        )
        size_btn.pack(side="left", padx=(8, 4), pady=4, ipadx=4)
        _attach_tooltip(size_btn, "Size — <size=13>text</size>")

        self._color_btn = ctk.CTkButton(
            bar, text="color  ▼", font=("Segoe UI", 10),
            width=0, height=24, corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=lambda: self._show_color_dropdown("color"),
        )
        self._color_btn.pack(side="left", padx=(8, 4), pady=4, ipadx=4)
        _attach_tooltip(
            self._color_btn, "Text color — <color=...>text</color>",
        )

        self._bg_btn = ctk.CTkButton(
            bar, text="bg  ▼", font=("Segoe UI", 10),
            width=0, height=24, corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=lambda: self._show_color_dropdown("bg"),
        )
        self._bg_btn.pack(side="left", padx=(0, 4), pady=4, ipadx=4)
        _attach_tooltip(
            self._bg_btn, "Background — <bg=...>text</bg>",
        )

        ctk.CTkLabel(
            bar, text="Select text, then click a tag",
            font=("Segoe UI", 9),
            text_color=STATUS_FG,
        ).pack(side="right", padx=(0, 12), pady=4)

    def _show_color_dropdown(self, tag: str) -> None:
        anchor = self._color_btn if tag == "color" else self._bg_btn
        _ColorDropdown(
            self, anchor, on_pick=lambda v: self._wrap_tag(tag, v),
        )

    # ------------------------------------------------------------------
    # Rich-text insertion — wrap selection, or insert empty pair at
    # the current cursor position (cursor is parked at end-of-text on
    # open, so a button press without prior interaction appends).
    # ------------------------------------------------------------------
    # Tk's default double-click word selection treats any non-whitespace
    # run as a word, so `<b>hello</b>` gets picked as one chunk. In
    # rich-text mode we override the binding to also split on tag
    # delimiters, so a double-click on `hello` selects just `hello`.
    _RICH_WORD_SEP = frozenset(" \t\n<>/=\"'")

    def _select_word_no_tags(self, event) -> str:
        idx = self._text.index(f"@{event.x},{event.y}")
        try:
            line_s, col_s = idx.split(".")
            line = int(line_s)
            col = int(col_s)
        except ValueError:
            return "break"

        line_text = self._text.get(f"{line}.0", f"{line}.end")
        if col >= len(line_text) or line_text[col] in self._RICH_WORD_SEP:
            self._text.mark_set("insert", idx)
            return "break"

        start = col
        while start > 0 and line_text[start - 1] not in self._RICH_WORD_SEP:
            start -= 1
        end = col
        while end < len(line_text) and line_text[end] not in self._RICH_WORD_SEP:
            end += 1

        self._text.tag_remove("sel", "1.0", "end")
        self._text.tag_add("sel", f"{line}.{start}", f"{line}.{end}")
        self._text.mark_set("insert", f"{line}.{end}")
        self._text.focus_set()
        return "break"

    def _wrap_tag(self, tag: str, value: str | None = None) -> None:
        open_tag = f"<{tag}={value}>" if value is not None else f"<{tag}>"
        close_tag = f"</{tag}>"

        try:
            sel_start = self._text.index("sel.first")
            sel_end = self._text.index("sel.last")
            has_selection = True
        except tk.TclError:
            has_selection = False

        if has_selection:
            selected = self._text.get(sel_start, sel_end)
            self._text.delete(sel_start, sel_end)
            self._text.insert(sel_start, open_tag + selected + close_tag)
            inner_start = f"{sel_start}+{len(open_tag)}c"
            inner_end = (
                f"{sel_start}+{len(open_tag) + len(selected)}c"
            )
            self._text.tag_remove("sel", "1.0", "end")
            self._text.tag_add("sel", inner_start, inner_end)
            self._text.mark_set("insert", inner_end)
            self._text.see(inner_end)
        else:
            insert_idx = self._text.index("insert")
            self._text.insert(insert_idx, open_tag + close_tag)
            cursor_idx = f"{insert_idx}+{len(open_tag)}c"
            self._text.mark_set("insert", cursor_idx)
            self._text.see(cursor_idx)

        self._text.focus_set()
        self._update_status()

    # ------------------------------------------------------------------
    # Hint blocks — built-in pseudo-code templates
    # ------------------------------------------------------------------
    def _build_hint_blocks(self, bar) -> None:
        sep = ctk.CTkFrame(bar, fg_color=BORDER, width=1, height=20)
        sep.pack(side="left", padx=(12, 8), pady=7)

        for label, items in HINT_BLOCKS:
            btn = ctk.CTkButton(
                bar, text=label,
                width=0, height=24, corner_radius=3,
                fg_color="#3c3c3c", hover_color="#4a4a4a",
                font=("Segoe UI", 10),
            )
            btn.pack(side="left", padx=(0, 4), pady=4, ipadx=4)
            if len(items) == 1:
                _, template = items[0]
                btn.configure(command=lambda t=template: self._insert_template(t))
            else:
                btn.configure(
                    command=lambda b=btn, its=items: self._show_block_menu(b, its),
                )

    def _show_block_menu(self, anchor_btn, items) -> None:
        menu = tk.Menu(self, tearoff=0, **MENU_STYLE)
        for sub_label, template in items:
            menu.add_command(
                label=sub_label,
                command=lambda t=template: self._insert_template(t),
            )
        x = anchor_btn.winfo_rootx()
        y = anchor_btn.winfo_rooty() + anchor_btn.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    # ------------------------------------------------------------------
    # Custom hints — user-defined snippets persisted globally
    # ------------------------------------------------------------------
    def _build_custom_hints(self, bar) -> None:
        self._custom_btn = ctk.CTkButton(
            bar, text="Custom  ▼",
            width=0, height=24, corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            font=("Segoe UI", 10),
            command=self._show_custom_menu,
        )
        self._custom_btn.pack(side="left", padx=(8, 4), pady=4, ipadx=6)

        ctk.CTkButton(
            bar, text="", image=self._icon_plus,
            width=24, height=24, corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._add_custom_hint,
        ).pack(side="left", padx=(0, 12), pady=4)

    def _show_custom_menu(self) -> None:
        hints = load_description_hints()
        menu = tk.Menu(self, tearoff=0, **MENU_STYLE)
        if not hints:
            menu.add_command(
                label="(no custom hints yet)",
                foreground="#666666",
                activeforeground="#666666",
                activebackground="#2d2d30",
            )
        else:
            for hint in hints:
                preview = hint if len(hint) <= 60 else hint[:57] + "..."
                menu.add_command(
                    label=preview,
                    command=lambda h=hint: self._insert_template(h),
                )
            menu.add_separator()
            menu.add_command(
                label="Manage...", command=self._manage_custom_hints,
            )
        x = self._custom_btn.winfo_rootx()
        y = self._custom_btn.winfo_rooty() + self._custom_btn.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _add_custom_hint(self) -> None:
        dlg = _AddHintDialog(self)
        dlg.wait_window()
        if dlg.result:
            hints = load_description_hints()
            hints.append(dlg.result)
            save_description_hints(hints)

    def _manage_custom_hints(self) -> None:
        dlg = _ManageHintsDialog(self)
        dlg.wait_window()

    # ------------------------------------------------------------------
    # Template insertion — appends template on its own new line, selects
    # the first <placeholder>. Does not consume an existing selection.
    # ------------------------------------------------------------------
    def _insert_template(self, template: str) -> None:
        self._text.tag_remove("sel", "1.0", "end")
        self._text.mark_set("insert", "end-1c")

        existing = self._text.get("1.0", "end-1c")
        prefix = "\n" if existing and not existing.endswith("\n") else ""
        start_idx = self._text.index("insert")
        self._text.insert("insert", prefix + template)

        match = _PLACEHOLDER_RE.search(template)
        if match is not None:
            offset = len(prefix) + match.start()
            length = match.end() - match.start()
            ph_start = f"{start_idx}+{offset}c"
            ph_end = f"{start_idx}+{offset + length}c"
            self._text.tag_add("sel", ph_start, ph_end)
            self._text.mark_set("insert", ph_start)
        self._text.focus_set()
        self._update_status()

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
            selectbackground="#094771", selectforeground="#ffffff",
            inactiveselectbackground="#094771",
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


class _ColorDropdown(tk.Toplevel):
    """Borderless dropdown for picking a rich-text color.

    Top: free-form hex entry (default ``#FFFFFF``); Enter commits.
    Below: every named color the parser knows, rendered in its own
    color so ``red`` looks red, ``blue`` looks blue, etc.

    Outside-click closes via a class-level ``bind_all`` registered
    once per process. CTk installs its own ``bind_all("<Button-1>")``
    for focus tracking, so per-instance ``unbind_all`` would clobber
    it — we keep a single shared dispatcher that walks an instance
    list instead.
    """

    _instances: list["_ColorDropdown"] = []
    _global_bound: bool = False

    def __init__(self, parent, anchor, *, on_pick):
        super().__init__(parent)
        # Windows quirk: overrideredirect + transient before the window
        # is mapped can leave the Toplevel invisible. Stay withdrawn
        # during setup, then deiconify + lift after geometry is set.
        self.withdraw()
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.configure(bg="#2d2d30", bd=1)

        # Modal editor has a local grab that would block clicks on this
        # separate Toplevel. Release the editor's grab while the
        # dropdown is open; restore it on destroy.
        self._parent_editor = parent
        try:
            parent.grab_release()
        except tk.TclError:
            pass

        self._on_pick = on_pick

        self._var = tk.StringVar(value="#FFFFFF")
        self._entry = tk.Entry(
            self, textvariable=self._var,
            bg=EDITOR_BG, fg="#ffffff",
            insertbackground="#ffffff",
            font=("Consolas", 10), bd=0,
            highlightthickness=1,
            highlightbackground=BORDER, highlightcolor="#5a5a5a",
        )
        self._entry.pack(fill="x", padx=6, pady=(6, 4))
        self._entry.bind("<Return>", self._commit_hex)
        self._entry.bind("<Escape>", lambda _e: self.destroy())
        self._var.trace_add("write", self._on_hex_change)

        # COLOR_MAP carries both US/UK spellings of "gray" pointing at
        # the same hex. Show only the first name per unique color.
        seen_hex: set[str] = set()
        for name, hex_val in COLOR_MAP.items():
            if hex_val in seen_hex:
                continue
            seen_hex.add(hex_val)
            row = tk.Label(
                self, text=name, bg="#2d2d30",
                fg=hex_val, font=("Segoe UI", 10),
                anchor="w", padx=10, pady=2, cursor="hand2",
            )
            row.pack(fill="x")
            row.bind(
                "<Enter>",
                lambda _e, r=row: r.configure(bg="#3a3d41"),
            )
            row.bind(
                "<Leave>",
                lambda _e, r=row: r.configure(bg="#2d2d30"),
            )
            row.bind(
                "<Button-1>",
                lambda _e, n=name: self._pick(n),
            )

        # Spacer so the last row doesn't kiss the bottom border.
        tk.Frame(self, bg="#2d2d30", height=4).pack(fill="x")

        _ColorDropdown._instances.append(self)
        _ColorDropdown._ensure_global_bound(parent)
        self.bind("<Destroy>", self._cleanup)

        # Map + position + raise. Geometry must be set BEFORE deiconify
        # so the window doesn't flash at the wrong spot on Windows.
        self.update_idletasks()
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height() + 2
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.lift()

        self.after(20, self._take_focus)

    @classmethod
    def _ensure_global_bound(cls, anywidget) -> None:
        if cls._global_bound:
            return
        anywidget.bind_all(
            "<Button-1>", cls._dispatch_global_click, add="+",
        )
        cls._global_bound = True

    @classmethod
    def _dispatch_global_click(cls, event) -> None:
        for d in list(cls._instances):
            d._check_global_click(event)

    def _check_global_click(self, event) -> None:
        try:
            dx = self.winfo_rootx()
            dy = self.winfo_rooty()
            dw = self.winfo_width()
            dh = self.winfo_height()
        except tk.TclError:
            return
        if not (dx <= event.x_root < dx + dw
                and dy <= event.y_root < dy + dh):
            try:
                self.destroy()
            except tk.TclError:
                pass

    def _take_focus(self) -> None:
        try:
            self._entry.focus_force()
            self._entry.select_range(0, "end")
        except tk.TclError:
            pass

    def _cleanup(self, _e) -> None:
        try:
            _ColorDropdown._instances.remove(self)
        except ValueError:
            pass
        # Restore the editor's modal grab.
        try:
            self._parent_editor.grab_set()
        except tk.TclError:
            pass

    def _on_hex_change(self, *_) -> None:
        val = self._var.get().strip()
        parsed = parse_color(val) if val else None
        try:
            self._entry.configure(fg=parsed if parsed else "#ff6666")
        except tk.TclError:
            pass

    def _commit_hex(self, _e=None) -> str:
        val = self._var.get().strip()
        if val and parse_color(val):
            self._pick(val)
        return "break"

    def _pick(self, value: str) -> None:
        try:
            self.destroy()
        except tk.TclError:
            pass
        self._on_pick(value)


class _AddHintDialog(ctk.CTkToplevel):
    """Single-line input for adding a custom hint to global settings."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add custom hint")
        self.configure(fg_color=BG)
        self.geometry("440x140")
        self.minsize(360, 140)
        self.resizable(True, False)
        self.transient(parent)
        safe_grab_set(self)
        self.result: str | None = None

        ctk.CTkLabel(
            self, text="Hint text:",
            font=("Segoe UI", 10), text_color=EDITOR_FG, anchor="w",
        ).pack(fill="x", padx=14, pady=(14, 4))

        self._entry = ctk.CTkEntry(
            self, height=30, fg_color=EDITOR_BG, border_color=BORDER,
            text_color=EDITOR_FG,
        )
        self._entry.pack(fill="x", padx=14)
        self._entry.focus_set()
        self._entry.bind("<Return>", lambda _e: self._on_ok())
        self._entry.bind("<Escape>", lambda _e: self._on_cancel())

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=14, pady=(12, 12))
        ctk.CTkButton(
            footer, text="Add", width=80, height=26, corner_radius=3,
            command=self._on_ok,
        ).pack(side="right", padx=(4, 0))
        ctk.CTkButton(
            footer, text="Cancel", width=80, height=26, corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _on_ok(self) -> None:
        text = self._entry.get().strip()
        self.result = text or None
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()


class _ManageHintsDialog(ctk.CTkToplevel):
    """Lists existing custom hints and lets the user delete them."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Manage custom hints")
        self.configure(fg_color=BG)
        self.geometry("520x360")
        self.minsize(380, 240)
        self.transient(parent)
        safe_grab_set(self)

        wrap = tk.Frame(self, bg=BG, highlightthickness=0)
        wrap.pack(fill="both", expand=True, padx=14, pady=(14, 0))
        self._listbox = tk.Listbox(
            wrap, bg=EDITOR_BG, fg=EDITOR_FG,
            selectbackground="#094771", selectforeground="#ffffff",
            font=("Segoe UI", 10), bd=0, relief="flat",
            highlightthickness=1, highlightbackground=BORDER,
            activestyle="none",
        )
        self._listbox.pack(side="left", fill="both", expand=True)
        vscroll = ctk.CTkScrollbar(
            wrap, orientation="vertical", command=self._listbox.yview,
            width=10, corner_radius=4,
            fg_color="#1a1a1a", button_color="#3a3a3a",
            button_hover_color="#4a4a4a",
        )
        self._listbox.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side="right", fill="y", padx=(2, 0))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=14, pady=12)
        ctk.CTkButton(
            footer, text="Delete selected", width=120, height=26,
            corner_radius=3,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._delete_selected,
        ).pack(side="left")
        ctk.CTkButton(
            footer, text="Close", width=80, height=26, corner_radius=3,
            command=self.destroy,
        ).pack(side="right")

        self._reload()

    def _reload(self) -> None:
        self._listbox.delete(0, "end")
        for hint in load_description_hints():
            self._listbox.insert("end", hint)

    def _delete_selected(self) -> None:
        sel = self._listbox.curselection()
        if not sel:
            return
        hints = load_description_hints()
        idx = sel[0]
        if 0 <= idx < len(hints):
            del hints[idx]
            save_description_hints(hints)
            self._reload()


if __name__ == "__main__":
    root = ctk.CTk()
    ctk.set_appearance_mode("dark")
    root.geometry("260x160")
    root.title("Text Editor — Smoke Test")

    def open_hints():
        d = TextEditorDialog(
            root, "Edit Description",
            "Sample text\nSecond line\nThird line with more words",
            show_hints=True,
        )
        d.wait_window()
        print("Hints result:", repr(d.result))

    def open_rich():
        d = TextEditorDialog(
            root, "Edit Rich Label",
            "<b>Rich</b> <color=#50fa7b>Text</color>",
            rich_text=True,
        )
        d.wait_window()
        print("Rich result:", repr(d.result))

    ctk.CTkButton(root, text="Open (hints)", command=open_hints).pack(
        pady=(20, 6),
    )
    ctk.CTkButton(root, text="Open (rich text)", command=open_rich).pack(
        pady=6,
    )
    root.mainloop()
