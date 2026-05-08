"""Bug / Feature report window — opens from Help menu and toolbar.

Compact CTkToplevel that drives one of two flows:

- **GitHub** — opens a pre-filled issue URL in the browser, or copies
  the URL to clipboard. The pre-fill bypasses the YAML issue
  templates and lands on a free-form body, so the body is built
  here with structured ``**field:** value`` headers.
- **Email** — exports a markdown file the user can attach to an
  email at ``BUG_REPORT_EMAIL``. No GitHub account needed.

Visual language matches the startup dialog (``#1e1e1e`` bg, ``#252526``
panels, secondary ``#3c3c3c``/``#4a4a4a`` buttons, CTk theme font at
10-11pt — family resolves to Segoe UI on Win, SF Display on Mac, Roboto on Linux).
"""
from __future__ import annotations

import platform
import sys
import tkinter as tk
import urllib.parse
import webbrowser
from pathlib import Path

import customtkinter as ctk

try:
    from app import __version__ as APP_VERSION
except Exception:
    APP_VERSION = "unknown"

try:
    from app.ui.icons import load_icon
except Exception:
    def load_icon(*_args, **_kwargs) -> "ctk.CTkImage | None":
        return None

from app.ui.managed_window import ManagedToplevel

REPO = "kandelucky/ctk_maker"
NEW_ISSUE_URL = f"https://github.com/{REPO}/issues/new"
KNOWN_ISSUES_URL = f"https://github.com/{REPO}/issues"
WIKI_REPORTING_URL = f"https://github.com/{REPO}/wiki/Reporting-Bugs"
URL_PREFILL_LIMIT = 8000
# +ctkmaker tag routes to a Gmail filter for builder reports.
BUG_REPORT_EMAIL = "kandelucky.dev+ctkmaker@gmail.com"
MIN_DESCRIPTION_WORDS = 10

# Palette — kept in sync with startup_dialog.py / dialogs.py AboutDialog.
BG = "#1e1e1e"
PANEL_BG = "#252526"
BTN_BG = "#3c3c3c"
BTN_HOVER = "#4a4a4a"
TEXT_FG = "#cccccc"
DIM_FG = "#888888"
TITLE_FG = "#e0e0e0"
LINK_FG = "#5bc0f8"
ACCENT_WARN = "#ffb74d"
ACCENT_ERR = "#e57373"

PLACEHOLDER_SEVERITY = "- Select severity -"
PLACEHOLDER_REPRO = "- Select -"
PLACEHOLDER_AREA = "- Select area -"

PY_VALUES = ["< 3.10", "3.10", "3.11", "3.12", "3.13", "> 3.13"]

SEVERITY_VALUES = [
    PLACEHOLDER_SEVERITY,
    "Crash", "Data loss", "Wrong behavior", "Visual glitch", "Minor",
]
SEVERITY_SLUGS = {
    "Crash": "crash",
    "Data loss": "data-loss",
    "Wrong behavior": "wrong-behavior",
    "Visual glitch": "visual-glitch",
    "Minor": "minor",
}

REPRO_VALUES = [
    PLACEHOLDER_REPRO,
    "Always", "Sometimes", "Once", "Could not verify",
]

AREA_VALUES = [
    PLACEHOLDER_AREA,
    "Canvas", "Properties", "Widgets", "Export", "Save-Load", "UI", "Other",
]


def detect_os() -> str:
    name = platform.system()
    if name == "Darwin":
        return "macOS"
    if name in ("Windows", "Linux"):
        return name
    return "Other"


def detect_python_bucket() -> str:
    major, minor = sys.version_info.major, sys.version_info.minor
    explicit = f"{major}.{minor}"
    if explicit in PY_VALUES:
        return explicit
    if (major, minor) < (3, 10):
        return "< 3.10"
    return "> 3.13"


def detect_full_python() -> str:
    v = sys.version_info
    return f"{v.major}.{v.minor}.{v.micro}"


def build_bug_body(
    *,
    severity: str,
    reproducibility: str,
    area: str,
    version: str,
    os_name: str,
    py_ver: str,
    extra_env: dict,
    description: str,
    steps: str,
    expected: str,
) -> str:
    env_lines = [
        f"**CTkMaker version:** {version}",
        f"**OS:** {os_name}",
        f"**Python version:** {py_ver}",
    ]
    if extra_env.get("python_full"):
        env_lines.append(f"**Python (detailed):** {extra_env['python_full']}")
    if extra_env.get("customtkinter"):
        env_lines.append(f"**customtkinter:** {extra_env['customtkinter']}")
    if extra_env.get("tk"):
        env_lines.append(f"**Tk:** {extra_env['tk']}")
    if extra_env.get("screen"):
        env_lines.append(f"**Screen:** {extra_env['screen']}")

    parts = [
        f"**Severity:** {severity}",
        f"**Reproducibility:** {reproducibility}",
        f"**Area:** {area}",
        "",
        *env_lines,
        "",
        f"### Description\n{description}",
        "",
        f"### Steps to reproduce\n{steps}",
        "",
        f"### Expected vs Actual\n{expected}",
    ]
    return "\n".join(parts) + "\n"


def build_feature_body(
    *,
    problem: str,
    solution: str,
    alternatives: str,
) -> str:
    parts = [
        f"### Problem it solves\n{problem}",
        "",
        f"### Proposed solution\n{solution}",
        "",
        f"### Alternatives considered\n{alternatives}",
    ]
    return "\n".join(parts) + "\n"


def build_url(title: str, body: str, labels: list[str]) -> str:
    """Free-form ``/issues/new`` URL — kept for the email flow's
    markdown export, not used by the GitHub button anymore."""
    params = {
        "title": title,
        "body": body,
        "labels": ",".join(labels),
    }
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"{NEW_ISSUE_URL}?{query}"


def build_template_url(
    template: str, *, title: str, fields: dict, labels: list[str],
) -> str:
    """Open the structured Issue Form template with per-field
    pre-fills. Field IDs come from the YAML in
    ``.github/ISSUE_TEMPLATE/`` and must match exactly — GitHub
    silently drops unknown params.

    Empty values are skipped so the template's own placeholder text
    remains visible for fields the user left blank.
    """
    params: dict = {"template": template}
    if title:
        params["title"] = title
    for key, value in fields.items():
        if value is None or value == "":
            continue
        params[key] = value
    if labels:
        params["labels"] = ",".join(labels)
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"{NEW_ISSUE_URL}?{query}"


def attach_context_menu(widget) -> None:
    """Cut/Copy/Paste/Select-All right-click menu for entries + textboxes.

    CTkEntry wraps a tk.Entry as ``_entry``; CTkTextbox wraps a tk.Text
    as ``_textbox`` — bind on the inner widget so the menu fires on the
    actual editable surface, not the rounded frame around it.
    """
    inner = getattr(widget, "_entry", None) or getattr(
        widget, "_textbox", widget,
    )
    is_text = isinstance(inner, tk.Text)
    menu = tk.Menu(inner, tearoff=0)

    def has_selection() -> bool:
        try:
            if is_text:
                return bool(inner.tag_ranges("sel"))
            return inner.selection_present()
        except Exception:
            return False

    def has_clipboard() -> bool:
        try:
            return bool(inner.clipboard_get())
        except Exception:
            return False

    def select_all() -> None:
        if is_text:
            inner.tag_add("sel", "1.0", "end-1c")
            inner.mark_set("insert", "end-1c")
        else:
            inner.select_range(0, "end")
            inner.icursor("end")

    menu.add_command(
        label="Cut", command=lambda: inner.event_generate("<<Cut>>"),
    )
    menu.add_command(
        label="Copy", command=lambda: inner.event_generate("<<Copy>>"),
    )
    menu.add_command(
        label="Paste", command=lambda: inner.event_generate("<<Paste>>"),
    )
    menu.add_separator()
    menu.add_command(label="Select All", command=select_all)

    def show(event):
        menu.entryconfig(
            "Cut", state="normal" if has_selection() else "disabled",
        )
        menu.entryconfig(
            "Copy", state="normal" if has_selection() else "disabled",
        )
        menu.entryconfig(
            "Paste", state="normal" if has_clipboard() else "disabled",
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    inner.bind("<Button-3>", show)


def _make_button(parent, *, text, command, primary=False, **kwargs):
    """Standard secondary button — startup-style ``#3c3c3c``/``#4a4a4a``.

    ``primary=True`` keeps the CTk default accent (used only for the
    Submit-equivalent button so the call to action stands out).
    """
    if primary:
        return ctk.CTkButton(
            parent, text=text, command=command,
            corner_radius=4, height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            **kwargs,
        )
    return ctk.CTkButton(
        parent, text=text, command=command,
        corner_radius=4, height=30,
        fg_color=BTN_BG, hover_color=BTN_HOVER, text_color=TEXT_FG,
        font=ctk.CTkFont(size=11),
        **kwargs,
    )


def build_screenshot_hint_panel(
    parent, *, icon_size: int = 22, compact: bool = False,
) -> ctk.CTkFrame:
    if compact:
        heading_size, text_size = 11, 10
        pad_x, pad_y = 10, 8
    else:
        heading_size, text_size = 12, 10
        pad_x, pad_y = 12, 10

    section = ctk.CTkFrame(
        parent, fg_color=PANEL_BG, corner_radius=6,
    )
    inner = ctk.CTkFrame(section, fg_color="transparent")
    inner.pack(fill="x", padx=pad_x, pady=pad_y)

    icon_img = load_icon("image-plus", size=icon_size, color=DIM_FG)
    if icon_img is not None:
        ctk.CTkLabel(inner, image=icon_img, text="").pack(
            side="left", padx=(0, 10), anchor="n",
        )

    text_col = ctk.CTkFrame(inner, fg_color="transparent")
    text_col.pack(side="left", fill="x", expand=True)
    ctk.CTkLabel(
        text_col, text="Attaching a screenshot",
        font=ctk.CTkFont(size=heading_size, weight="bold"),
        text_color=TITLE_FG, anchor="w",
    ).pack(fill="x")
    ctk.CTkLabel(
        text_col,
        text="GitHub: drop or paste it on the page after it opens.",
        font=ctk.CTkFont(size=text_size),
        text_color=DIM_FG, anchor="w", justify="left",
        wraplength=460,
    ).pack(fill="x", pady=(2, 0))
    ctk.CTkLabel(
        text_col,
        text=(
            "Email: attach the image to your email along with the "
            "report file."
        ),
        font=ctk.CTkFont(size=text_size),
        text_color=DIM_FG, anchor="w", justify="left",
        wraplength=460,
    ).pack(fill="x", pady=(1, 0))

    return section


class BugReporterWindow(ManagedToplevel):
    window_key = "bug_reporter"
    window_title = "Report a Bug — CTkMaker"
    default_size = (660, 590)
    min_size = (560, 540)
    fg_color = BG
    panel_padding = (0, 0)
    modal = True

    def __init__(self, master) -> None:
        self._mode = ctk.StringVar(master=master, value="Bug Report")
        self._title_var = ctk.StringVar(master=master)
        self._severity_var = ctk.StringVar(
            master=master, value=PLACEHOLDER_SEVERITY,
        )
        self._repro_var = ctk.StringVar(master=master, value=PLACEHOLDER_REPRO)
        self._area_var = ctk.StringVar(master=master, value=PLACEHOLDER_AREA)
        self._version_var = ctk.StringVar(master=master, value=APP_VERSION)
        self._os_var = ctk.StringVar(master=master, value=detect_os())
        self._py_var = ctk.StringVar(master=master, value=detect_python_bucket())
        self._extra_env: dict[str, str] = {}

        for v in (
            self._title_var, self._severity_var, self._repro_var,
            self._area_var, self._version_var, self._os_var, self._py_var,
        ):
            v.trace_add("write", lambda *_: self._refresh_all())

        super().__init__(master)

        self._show_picker()
        self._refresh_all()
        self._on_autodetect()

    def build_content(self) -> ctk.CTkFrame:
        # The window swaps between two top-level views: a picker that
        # fills the whole content area on open, and the form that
        # appears after the user commits to a mode. Both live as
        # sibling frames inside ``container`` so swapping is a
        # pack_forget / pack pair.
        container = ctk.CTkFrame(self, fg_color="transparent")
        self._picker_container = self._build_picker(container)
        self._form_container = ctk.CTkFrame(container, fg_color="transparent")
        self._build_form(self._form_container)
        return container

    # ------------------------------------------------------------------
    # View state — picker on open, form after the user picks a mode.
    # ------------------------------------------------------------------
    def _show_picker(self) -> None:
        self._form_container.pack_forget()
        self._picker_container.pack(fill="both", expand=True)

    def _show_form(self, mode: str) -> None:
        self._mode.set(mode)
        self._picker_container.pack_forget()
        self._form_container.pack(fill="both", expand=True)
        self._switch_mode(mode)

    def _build_picker(self, parent) -> ctk.CTkFrame:
        f = ctk.CTkFrame(parent, fg_color="transparent")

        self._build_intro_banner(f).pack(
            fill="x", padx=20, pady=(18, 44),
        )

        ctk.CTkLabel(
            f, text="What would you like to report?",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=TITLE_FG,
        ).pack(pady=(0, 6))
        ctk.CTkLabel(
            f,
            text="Pick a track to start filling out the report.",
            font=ctk.CTkFont(size=11),
            text_color=DIM_FG,
        ).pack(pady=(0, 24))

        cards_row = ctk.CTkFrame(f, fg_color="transparent")
        cards_row.pack(padx=24)

        self._build_picker_card(
            cards_row,
            icon_name="bug",
            icon_color="#e09c5c",
            title="Bug Report",
            title_color="#e09c5c",
            subtitle=(
                "Something is broken or behaves\n"
                "differently than expected."
            ),
            on_click=lambda: self._show_form("Bug Report"),
        ).pack(side="left", padx=(0, 12))

        self._build_picker_card(
            cards_row,
            icon_name="lightbulb",
            icon_color="#5bc0f8",
            title="Feature Request",
            title_color="#5bc0f8",
            subtitle=(
                "Suggest a new capability or an\n"
                "improvement to an existing one."
            ),
            on_click=lambda: self._show_form("Feature Request"),
        ).pack(side="left")

        ctk.CTkFrame(f, fg_color="transparent").pack(
            fill="both", expand=True,
        )

        return f

    def _build_intro_banner(self, parent) -> ctk.CTkFrame:
        # Why-this-matters banner — sits at the top of the picker so
        # the user reads the intent before picking a track. Mirrors
        # the wiki Reporting-Bugs page so the language is consistent.
        banner = ctk.CTkFrame(
            parent, fg_color=PANEL_BG, corner_radius=8,
        )
        inner = ctk.CTkFrame(banner, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)

        head_row = ctk.CTkFrame(inner, fg_color="transparent")
        head_row.pack(fill="x")
        icon_img = load_icon("book-open", size=20, color=LINK_FG)
        if icon_img is not None:
            ctk.CTkLabel(head_row, image=icon_img, text="").pack(
                side="left", padx=(0, 8),
            )
        ctk.CTkLabel(
            head_row, text="Why this matters",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TITLE_FG, anchor="w",
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            inner,
            text=(
                "CTkMaker is a one-person project — clear bug reports "
                "and well-described feature requests directly shape "
                "what gets fixed and built next. Thanks for taking "
                "the time to write one."
            ),
            font=ctk.CTkFont(size=11),
            text_color=TEXT_FG, anchor="w", justify="left",
            wraplength=560,
        ).pack(fill="x", pady=(8, 4))

        ctk.CTkLabel(
            inner,
            text=(
                "Please check existing issues first to avoid duplicates."
            ),
            font=ctk.CTkFont(size=11),
            text_color=DIM_FG, anchor="w", justify="left",
            wraplength=560,
        ).pack(fill="x", pady=(0, 6))

        action_row = ctk.CTkFrame(inner, fg_color="transparent")
        action_row.pack(fill="x", pady=(4, 0))

        guide_btn = ctk.CTkButton(
            action_row,
            text="Read the full reporting guide  →",
            command=lambda: webbrowser.open(WIKI_REPORTING_URL),
            fg_color=BTN_BG, hover_color=BTN_HOVER,
            text_color=LINK_FG,
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28, corner_radius=4,
        )
        guide_btn.pack(side="left")

        issues_btn = ctk.CTkButton(
            action_row,
            text="Browse open issues first  →",
            command=lambda: webbrowser.open(KNOWN_ISSUES_URL),
            fg_color=BTN_BG, hover_color=BTN_HOVER,
            text_color=LINK_FG,
            font=ctk.CTkFont(size=11, weight="bold"),
            height=28, corner_radius=4,
        )
        issues_btn.pack(side="right")

        for btn in (guide_btn, issues_btn):
            try:
                btn.configure(cursor="hand2")
            except Exception:
                pass

        return banner

    def _build_picker_card(
        self, parent, *, icon_name: str, icon_color: str,
        title: str, subtitle: str, on_click,
        title_color: str = TITLE_FG,
    ) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent, fg_color=PANEL_BG, corner_radius=8,
            width=240, height=190,
        )
        card.pack_propagate(False)

        icon_img = load_icon(icon_name, size=42, color=icon_color)
        ctk.CTkLabel(card, image=icon_img, text="").pack(pady=(20, 6))
        ctk.CTkLabel(
            card, text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=title_color,
        ).pack(pady=(0, 4))
        ctk.CTkLabel(
            card, text=subtitle,
            font=ctk.CTkFont(size=10),
            text_color=DIM_FG, justify="center",
        ).pack(pady=(0, 12))

        # Bind on the card and every child so the entire surface
        # behaves as the click target (CTkFrame doesn't forward
        # press events to its children automatically).
        for w in (card, *card.winfo_children()):
            w.bind("<Button-1>", lambda _e: on_click())
            try:
                w.configure(cursor="hand2")
            except Exception:
                pass

        # Light hover lift via fg_color swap on the card frame.
        def _on_enter(_e):
            try:
                card.configure(fg_color=BTN_HOVER)
            except Exception:
                pass

        def _on_leave(_e):
            try:
                card.configure(fg_color=PANEL_BG)
            except Exception:
                pass

        card.bind("<Enter>", _on_enter)
        card.bind("<Leave>", _on_leave)

        return card

    def _build_form(self, parent) -> None:
        # Top row: back-link on the left, mode heading on the right
        # (or below). Mirrors the picker's "What would you like to
        # report?" so the user always sees where they are.
        topbar = ctk.CTkFrame(parent, fg_color="transparent")
        topbar.pack(fill="x", padx=16, pady=(14, 2))
        ctk.CTkButton(
            topbar, text="← Change mode",
            command=self._show_picker,
            fg_color="transparent", hover_color=BTN_HOVER,
            text_color=LINK_FG,
            font=ctk.CTkFont(size=10, underline=True),
            width=120, height=22, anchor="w",
            corner_radius=4,
        ).pack(side="left")

        self._form_heading = ctk.CTkLabel(
            parent, text="",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=TITLE_FG, anchor="w",
        )
        self._form_heading.pack(fill="x", padx=16, pady=(0, 8))

        title_frame = ctk.CTkFrame(parent, fg_color="transparent")
        title_frame.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(
            title_frame, text="Title *",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_FG, anchor="w",
        ).pack(fill="x")
        title_entry = ctk.CTkEntry(
            title_frame,
            textvariable=self._title_var,
            placeholder_text="Short summary",
            corner_radius=4, height=28,
            font=ctk.CTkFont(size=11),
            fg_color=PANEL_BG, border_color=BTN_BG,
        )
        title_entry.pack(fill="x")
        attach_context_menu(title_entry)

        self._forms = ctk.CTkScrollableFrame(
            parent, fg_color="transparent",
        )
        self._forms.pack(fill="both", expand=True, padx=10, pady=8)
        self._bug_frame = self._build_bug_form(self._forms)
        self._feature_frame = self._build_feature_form(self._forms)

        btns = ctk.CTkFrame(parent, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=(0, 4))
        self._report_btn = _make_button(
            btns, text="Report", command=self._on_report,
            primary=True, width=140,
        )
        self._report_btn.pack(side="right", ipadx=8)

        self._stats_label = ctk.CTkLabel(
            parent, text="",
            font=ctk.CTkFont(size=10),
            anchor="w", text_color=DIM_FG,
        )
        self._stats_label.pack(fill="x", padx=16, pady=(0, 1))
        self._status_label = ctk.CTkLabel(
            parent, text="",
            font=ctk.CTkFont(size=10),
            anchor="w", text_color=DIM_FG,
        )
        self._status_label.pack(fill="x", padx=16, pady=(0, 10))

    def _build_bug_form(self, parent) -> ctk.CTkFrame:
        f = ctk.CTkFrame(parent, fg_color="transparent")

        triage = ctk.CTkFrame(f, fg_color="transparent")
        triage.pack(fill="x", pady=(0, 6))
        triage.columnconfigure((0, 1, 2), weight=1, uniform="triage")

        col_s = ctk.CTkFrame(triage, fg_color="transparent")
        col_s.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._mini_label(col_s, "Severity")
        self._mini_optionmenu(col_s, self._severity_var, SEVERITY_VALUES)

        col_r = ctk.CTkFrame(triage, fg_color="transparent")
        col_r.grid(row=0, column=1, sticky="ew", padx=4)
        self._mini_label(col_r, "Reproducibility")
        self._mini_optionmenu(col_r, self._repro_var, REPRO_VALUES)

        col_a = ctk.CTkFrame(triage, fg_color="transparent")
        col_a.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        self._mini_label(col_a, "Area")
        self._mini_optionmenu(col_a, self._area_var, AREA_VALUES)

        ctk.CTkLabel(
            f, text="Environment",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=TITLE_FG, anchor="w",
        ).pack(fill="x", pady=(8, 4))

        meta = ctk.CTkFrame(f, fg_color="transparent")
        meta.pack(fill="x", pady=(0, 4))
        meta.columnconfigure((0, 1, 2), weight=1, uniform="meta")

        col_v = ctk.CTkFrame(meta, fg_color="transparent")
        col_v.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._mini_label(col_v, "CTkMaker version")
        version_entry = ctk.CTkEntry(
            col_v, textvariable=self._version_var, state="readonly",
            corner_radius=4, height=26,
            font=ctk.CTkFont(size=11),
            fg_color=PANEL_BG, border_color=BTN_BG,
        )
        version_entry.pack(fill="x")
        attach_context_menu(version_entry)

        col_o = ctk.CTkFrame(meta, fg_color="transparent")
        col_o.grid(row=0, column=1, sticky="ew", padx=4)
        self._mini_label(col_o, "OS")
        self._mini_optionmenu(
            col_o, self._os_var,
            ["Windows", "macOS", "Linux", "Other"],
        )

        col_p = ctk.CTkFrame(meta, fg_color="transparent")
        col_p.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        self._mini_label(col_p, "Python version")
        self._mini_optionmenu(col_p, self._py_var, PY_VALUES)

        self._env_preview = ctk.CTkLabel(
            f, text="",
            font=ctk.CTkFont(size=10),
            anchor="w", text_color=DIM_FG, justify="left",
            wraplength=600,
        )
        self._env_preview.pack(fill="x", pady=(4, 4))

        self._desc_box, self._desc_counter = (
            self._labeled_textbox_with_counter(
                f, "Description",
                min_words=MIN_DESCRIPTION_WORDS, height=70,
            )
        )
        self._steps_box = self._labeled_textbox(
            f, "Steps to reproduce", height=70,
        )
        self._expected_box = self._labeled_textbox(
            f, "Expected vs Actual", height=70,
        )

        build_screenshot_hint_panel(f, icon_size=22).pack(
            fill="x", pady=(10, 4),
        )

        return f

    def _build_feature_form(self, parent) -> ctk.CTkFrame:
        f = ctk.CTkFrame(parent, fg_color="transparent")
        self._problem_box, self._problem_counter = (
            self._labeled_textbox_with_counter(
                f, "Problem it solves",
                min_words=MIN_DESCRIPTION_WORDS, height=80,
            )
        )
        self._solution_box = self._labeled_textbox(
            f, "Proposed solution", height=100,
        )
        self._alternatives_box = self._labeled_textbox(
            f, "Alternatives considered", height=80,
        )
        build_screenshot_hint_panel(f, icon_size=22).pack(
            fill="x", pady=(10, 4),
        )
        return f

    def _mini_label(self, parent, text: str) -> None:
        ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont(size=10),
            text_color=DIM_FG, anchor="w",
        ).pack(fill="x")

    def _mini_optionmenu(self, parent, var, values) -> ctk.CTkOptionMenu:
        om = ctk.CTkOptionMenu(
            parent, variable=var, values=values,
            corner_radius=4, height=26,
            font=ctk.CTkFont(size=11),
            fg_color=BTN_BG, button_color=BTN_BG,
            button_hover_color=BTN_HOVER, text_color=TEXT_FG,
        )
        om.pack(fill="x")
        return om

    def _labeled_textbox(
        self, parent, label: str, height: int = 70,
    ) -> ctk.CTkTextbox:
        ctk.CTkLabel(
            parent, text=label,
            font=ctk.CTkFont(size=11),
            text_color=TEXT_FG, anchor="w",
        ).pack(fill="x", pady=(6, 2))
        box = ctk.CTkTextbox(
            parent, height=height, wrap="word",
            corner_radius=4,
            font=ctk.CTkFont(size=11),
            fg_color=PANEL_BG, border_color=BTN_BG,
        )
        box.pack(fill="x")
        box.bind("<KeyRelease>", lambda _e: self._refresh_all())
        attach_context_menu(box)
        return box

    def _labeled_textbox_with_counter(
        self, parent, label: str,
        min_words: int, height: int = 70,
    ) -> tuple:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(6, 2))
        ctk.CTkLabel(
            row, text=f"{label} *",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_FG, anchor="w",
        ).pack(side="left", fill="x", expand=True)
        counter = ctk.CTkLabel(
            row, text=f"0 / {min_words} words",
            font=ctk.CTkFont(size=10),
            text_color=DIM_FG, anchor="e",
        )
        counter.pack(side="right")
        box = ctk.CTkTextbox(
            parent, height=height, wrap="word",
            corner_radius=4,
            font=ctk.CTkFont(size=11),
            fg_color=PANEL_BG, border_color=BTN_BG,
        )
        box.pack(fill="x")
        box.bind("<KeyRelease>", lambda _e: self._refresh_all())
        attach_context_menu(box)
        return box, counter

    def _switch_mode(self, mode: str) -> None:
        self._bug_frame.pack_forget()
        self._feature_frame.pack_forget()
        if mode == "Bug Report":
            self._bug_frame.pack(fill="x")
        else:
            self._feature_frame.pack(fill="x")
        if hasattr(self, "_form_heading"):
            self._form_heading.configure(text=mode)
        self._refresh_all()

    def _on_autodetect(self) -> None:
        self._os_var.set(detect_os())
        self._py_var.set(detect_python_bucket())
        env: dict[str, str] = {"python_full": detect_full_python()}
        try:
            env["customtkinter"] = getattr(ctk, "__version__", "unknown")
        except Exception:
            pass
        try:
            env["tk"] = self.tk.call("info", "patchlevel")
        except Exception:
            pass
        try:
            env["screen"] = (
                f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}"
            )
        except Exception:
            pass
        self._extra_env = env

        if env:
            lines = "  |  ".join(f"{k}: {v}" for k, v in env.items())
            self._env_preview.configure(text=f"Auto-detected: {lines}")
        else:
            self._env_preview.configure(
                text="Auto-detect produced no extra info.",
            )
        self._refresh_all()

    def _on_report(self) -> None:
        ReportDialog(self)

    def _on_open(self) -> None:
        url = self._current_url()
        webbrowser.open(url)
        self._status_label.configure(text="Opened in browser.")

    def _on_export(self) -> None:
        import re
        from datetime import datetime
        from tkinter import filedialog

        title = self._title_var.get().strip() or "report"
        mode_prefix = (
            "bug" if self._mode.get() == "Bug Report" else "feature"
        )
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50]
        if slug:
            suggested = f"ctkmaker_{mode_prefix}_{slug}.md"
        else:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            suggested = f"ctkmaker_{mode_prefix}_{stamp}.md"

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export report",
            defaultextension=".md",
            initialfile=suggested,
            filetypes=[
                ("Markdown", "*.md"),
                ("Text", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        content = (
            f"# {title}\n\n"
            f"**Send this report to:** {BUG_REPORT_EMAIL}\n\n"
            f"---\n\n"
            f"{self._current_body()}"
        )
        try:
            Path(path).write_text(content, encoding="utf-8")
        except OSError as exc:
            self._status_label.configure(text=f"Export failed: {exc}")
            return
        self._status_label.configure(text=f"Exported to: {path}")

    def _current_body(self) -> str:
        if self._mode.get() == "Bug Report":
            return build_bug_body(
                severity=self._severity_var.get(),
                reproducibility=self._repro_var.get(),
                area=self._area_var.get(),
                version=self._version_var.get().strip(),
                os_name=self._os_var.get(),
                py_ver=self._py_var.get(),
                extra_env=self._extra_env,
                description=self._desc_box.get("1.0", "end").strip(),
                steps=self._steps_box.get("1.0", "end").strip(),
                expected=self._expected_box.get("1.0", "end").strip(),
            )
        return build_feature_body(
            problem=self._problem_box.get("1.0", "end").strip(),
            solution=self._solution_box.get("1.0", "end").strip(),
            alternatives=self._alternatives_box.get("1.0", "end").strip(),
        )

    def _current_labels(self) -> list[str]:
        # Templates already attach the base label ("bug" or
        # "enhancement"); URL labels merge in additive, so we only
        # contribute the extras (severity / area slugs).
        if self._mode.get() == "Bug Report":
            sev_slug = SEVERITY_SLUGS.get(self._severity_var.get(), "minor")
            area_slug = {
                "Canvas": "canvas", "Properties": "properties",
                "Widgets": "widgets", "Export": "export",
                "Save-Load": "save-load", "UI": "ui", "Other": "other",
            }.get(self._area_var.get(), "other")
            return [f"severity:{sev_slug}", f"area:{area_slug}"]
        return []

    def _current_url(self) -> str:
        # Issue Form template URL — per-field ids match the YAML
        # in .github/ISSUE_TEMPLATE/. Title prefix ("[Bug]:" /
        # "[Feature]:") is preserved manually because the template's
        # built-in prefix only fires when no ?title= is supplied.
        raw_title = self._title_var.get().strip()
        if self._mode.get() == "Bug Report":
            full_title = f"[Bug]: {raw_title}" if raw_title else ""
            fields = {
                "severity": self._dropdown_value(self._severity_var),
                "reproducibility": self._dropdown_value(self._repro_var),
                "area": self._dropdown_value(self._area_var),
                "version": self._version_var.get().strip(),
                "os": self._os_var.get(),
                "python": self._py_var.get(),
                "description": self._desc_box.get("1.0", "end").strip(),
                "steps": self._steps_box.get("1.0", "end").strip(),
                "expected": self._expected_box.get("1.0", "end").strip(),
            }
            return build_template_url(
                "bug_report.yml",
                title=full_title, fields=fields,
                labels=self._current_labels(),
            )
        full_title = (
            f"[Feature]: {raw_title}" if raw_title else ""
        )
        fields = {
            "problem": self._problem_box.get("1.0", "end").strip(),
            "solution": self._solution_box.get("1.0", "end").strip(),
            "alternatives": (
                self._alternatives_box.get("1.0", "end").strip()
            ),
        }
        return build_template_url(
            "feature_request.yml",
            title=full_title, fields=fields,
            labels=self._current_labels(),
        )

    def _dropdown_value(self, var) -> str:
        """Return the raw dropdown value or '' for placeholders.
        Placeholders would otherwise leak into the URL as
        ``severity=- Select severity -`` and break the template's
        dropdown match."""
        value = var.get()
        if value in (
            PLACEHOLDER_SEVERITY, PLACEHOLDER_REPRO, PLACEHOLDER_AREA,
        ):
            return ""
        return value

    def _refresh_all(self) -> None:
        if not hasattr(self, "_report_btn"):
            return
        self._refresh_word_counters()
        self._refresh_button_state()
        self._refresh_url_stats()

    def _word_count(self, box: ctk.CTkTextbox) -> int:
        return len(box.get("1.0", "end").split())

    def _refresh_word_counters(self) -> None:
        for box, counter in (
            (self._desc_box, self._desc_counter),
            (self._problem_box, self._problem_counter),
        ):
            words = self._word_count(box)
            counter.configure(
                text=f"{words} / {MIN_DESCRIPTION_WORDS} words",
            )

    def _validation_errors(self) -> list[str]:
        errors: list[str] = []
        if not self._title_var.get().strip():
            errors.append("title required")
        if self._mode.get() == "Bug Report":
            words = self._word_count(self._desc_box)
            if words < MIN_DESCRIPTION_WORDS:
                errors.append("description too short")
            if self._severity_var.get() == PLACEHOLDER_SEVERITY:
                errors.append("choose severity")
            if self._repro_var.get() == PLACEHOLDER_REPRO:
                errors.append("choose reproducibility")
            if self._area_var.get() == PLACEHOLDER_AREA:
                errors.append("choose area")
        else:
            words = self._word_count(self._problem_box)
            if words < MIN_DESCRIPTION_WORDS:
                errors.append("problem too short")
        return errors

    def _refresh_button_state(self) -> None:
        errors = self._validation_errors()
        self._report_btn.configure(
            state="normal" if not errors else "disabled",
        )

    def _refresh_url_stats(self) -> None:
        body = self._current_body()
        url = self._current_url()
        text = f"Body: {len(body)} chars  |  URL: {len(url)} chars"
        if len(url) > URL_PREFILL_LIMIT:
            color = ACCENT_ERR
            text += f"  (over GitHub pre-fill limit of {URL_PREFILL_LIMIT})"
        elif len(url) > URL_PREFILL_LIMIT * 0.9:
            color = ACCENT_WARN
        else:
            color = DIM_FG
        self._stats_label.configure(text=text, text_color=color)


class ReportDialog(ManagedToplevel):
    window_title = "Report"
    default_size = (520, 460)
    min_size = (480, 420)
    fg_color = BG
    panel_padding = (0, 0)
    modal = True

    def __init__(self, master: "BugReporterWindow") -> None:
        self._owner = master
        super().__init__(master)

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

        ctk.CTkLabel(
            container,
            text="How would you like to send this report?",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TITLE_FG,
        ).pack(pady=(16, 6))

        build_screenshot_hint_panel(
            container, icon_size=18, compact=True,
        ).pack(fill="x", padx=16, pady=(0, 10))

        self._add_card(
            container,
            title="On GitHub",
            description=(
                "Open the pre-filled report on GitHub to review and "
                "submit. GitHub account required."
            ),
            actions=[
                ("Copy URL", self._do_copy),
                ("Open in Browser", self._do_github),
            ],
            link_text="See known issues first →",
            link_command=lambda: webbrowser.open(KNOWN_ISSUES_URL),
        )
        self._add_card(
            container,
            title="By Email",
            description=(
                "Save the report as a file and attach it to an "
                "email. No GitHub account needed."
            ),
            actions=[("Save as File...", self._do_email)],
            email=BUG_REPORT_EMAIL,
            link_text="See known issues first →",
            link_command=lambda: webbrowser.open(KNOWN_ISSUES_URL),
        )

        cancel_row = ctk.CTkFrame(container, fg_color="transparent")
        cancel_row.pack(fill="x", padx=16, pady=(6, 12))
        _make_button(
            cancel_row, text="Cancel", command=self.destroy,
            width=90,
        ).pack(side="right")
        return container

    def _add_card(
        self,
        parent,
        *,
        title: str,
        description: str,
        actions: list,
        link_text: str | None = None,
        link_command=None,
        email: str | None = None,
    ) -> None:
        card = ctk.CTkFrame(parent, fg_color=PANEL_BG, corner_radius=6)
        card.pack(fill="x", padx=16, pady=4)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)
        ctk.CTkLabel(
            inner, text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TITLE_FG, anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            inner, text=description,
            font=ctk.CTkFont(size=10),
            text_color=DIM_FG, anchor="w",
            wraplength=440, justify="left",
        ).pack(fill="x", pady=(2, 6))

        if email:
            email_row = ctk.CTkFrame(inner, fg_color="transparent")
            email_row.pack(fill="x", pady=(0, 8))
            ctk.CTkLabel(
                email_row, text="Send to:",
                font=ctk.CTkFont(size=10),
                text_color=DIM_FG,
            ).pack(side="left", padx=(0, 6))
            ctk.CTkLabel(
                email_row, text=email,
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=LINK_FG,
            ).pack(side="left")

            def _copy_email():
                try:
                    self.clipboard_clear()
                    self.clipboard_append(email)
                    copy_btn.configure(text="Copied")
                    self.after(
                        1500, lambda: copy_btn.configure(text="Copy"),
                    )
                except Exception:
                    pass

            copy_btn = ctk.CTkButton(
                email_row, text="Copy", command=_copy_email,
                width=56, height=22, corner_radius=4,
                fg_color=BTN_BG, hover_color=BTN_HOVER,
                text_color=TEXT_FG,
                font=ctk.CTkFont(size=10),
            )
            copy_btn.pack(side="left", padx=(8, 0))

        bottom = ctk.CTkFrame(inner, fg_color="transparent")
        bottom.pack(fill="x")

        if link_text and link_command:
            link_btn = ctk.CTkButton(
                bottom, text=link_text, command=link_command,
                fg_color="transparent", hover_color=BTN_HOVER,
                text_color=LINK_FG,
                font=ctk.CTkFont(size=10, underline=True),
                width=170, height=26, anchor="w",
            )
            link_btn.pack(side="left")
            try:
                link_btn.configure(cursor="hand2")
            except Exception:
                pass

        action_box = ctk.CTkFrame(bottom, fg_color="transparent")
        action_box.pack(side="right")
        for label, cmd in actions:
            _make_button(
                action_box, text=label, command=cmd, width=120,
            ).pack(side="left", padx=(6, 0))

    def _do_email(self) -> None:
        self.destroy()
        self._owner._on_export()

    def _do_github(self) -> None:
        self.destroy()
        self._owner._on_open()

    def _do_copy(self) -> None:
        url = self._owner._current_url()
        self.clipboard_clear()
        self.clipboard_append(url)
        self._owner._status_label.configure(
            text=f"Copied {len(url)} chars to clipboard.",
        )
