"""Tools → Inspect CTk Widget — side-by-side CTk vs builder comparison.

Toplevel window that lists every widget the builder knows about and,
for the selected widget, shows every kwarg from CTk's actual
`__init__` signature (ground truth via `inspect.signature`) plus
every property the matching descriptor exposes — flagging which side
each row belongs to.

Status legend:

    ✓  Exposed       — CTk kwarg AND builder property
    ⚠  CTk-only      — CTk accepts it, builder doesn't expose it
                       (often runtime-only: command / textvariable / …)
    ★  Builder helper — builder-side property that's not a raw CTk
                       kwarg (x / y / border_enabled toggle / font_*
                       composed into a single CTkFont, etc.)

The window deliberately reads through `app.widgets.registry` so any
descriptor we add later shows up automatically.
"""

from __future__ import annotations

import inspect
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

import customtkinter as ctk

from app.ui.palette import CATALOG
from app.widgets.registry import get_descriptor


WINDOW_BG = "#1e1e1e"
HEADER_BG = "#2d2d30"
ROW_FG = "#cccccc"
DIM_FG = "#888888"
ACCENT_GOOD = "#6fcf6a"
ACCENT_WARN = "#e0a44a"
ACCENT_HELPER = "#6aa3e0"

STATUS_EXPOSED = "✓"
STATUS_CTK_ONLY = "⚠"
STATUS_BUILDER_ONLY = "★"


def _ctk_class_for(descriptor) -> type | None:
    """Resolve descriptor → real CTk class. Honours
    ``ctk_class_name`` so descriptors that map onto a different CTk
    class (e.g. an Image widget backed by CTkLabel) still compare
    against the right `__init__` signature.
    """
    name = (
        getattr(descriptor, "ctk_class_name", "")
        or getattr(descriptor, "type_name", "")
    )
    cls = getattr(ctk, name, None)
    return cls if inspect.isclass(cls) else None


def _ctk_kwargs(cls: type) -> dict[str, object]:
    """Return ``{name: default}`` for every keyword arg of CTk's
    ``__init__`` (skips ``self`` / ``master`` / ``**kwargs``).
    """
    try:
        sig = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return {}
    out: dict[str, object] = {}
    for p in sig.parameters.values():
        if p.name in ("self", "master") or p.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        out[p.name] = (
            p.default if p.default is not inspect._empty else "<required>"
        )
    return out


class WidgetInspectorWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Inspect CTk Widget")
        self.geometry("760x560")
        self.minsize(560, 380)
        self.configure(fg_color=WINDOW_BG)

        # CTkToplevel on Windows ships behind the parent window by
        # default — ``transient`` keeps it on top of the builder, plus
        # one explicit ``lift()`` after the window has rendered ensures
        # focus actually lands here on first open.
        try:
            self.transient(master)
        except tk.TclError:
            pass
        self.after(50, self._raise_self)

        # Pull every palette entry — Vertical / Horizontal / Grid
        # Layout share the CTkFrame descriptor but each carries its
        # own preset_overrides, so they show up as distinct rows with
        # different "Builder default" values. Label format keeps the
        # underlying CTk class visible: "Vertical Layout  (CTkFrame)".
        entries: list[tuple[str, object, dict]] = []
        for group in CATALOG:
            for entry in group.items:
                descriptor = get_descriptor(entry.type_name)
                if descriptor is None:
                    continue
                label = f"{entry.display_name}  ({entry.type_name})"
                preset = dict(entry.preset_overrides or ())
                entries.append((label, descriptor, preset))
        # Stable display order = palette order; dedupe identical labels
        # in case a duplicate ever sneaks into the catalog.
        seen: set[str] = set()
        self._entries: list[tuple[object, dict]] = []
        labels: list[str] = []
        for label, descriptor, preset in entries:
            if label in seen:
                continue
            seen.add(label)
            labels.append(label)
            self._entries.append((descriptor, preset))
        self._label_to_index = {lbl: i for i, lbl in enumerate(labels)}

        self._build_chrome(labels)
        self._build_table()

        if labels:
            self._dropdown.set(labels[0])
            self._on_widget_change(labels[0])

    def _raise_self(self) -> None:
        try:
            self.lift()
            self.focus_set()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Chrome
    # ------------------------------------------------------------------
    def _build_chrome(self, labels: list[str]) -> None:
        bar = ctk.CTkFrame(self, fg_color=HEADER_BG, corner_radius=0)
        bar.pack(fill="x")

        ctk.CTkLabel(
            bar, text="Widget:", text_color=ROW_FG,
            font=("Segoe UI", 11),
        ).pack(side="left", padx=(12, 6), pady=8)

        self._dropdown = ctk.CTkOptionMenu(
            bar, values=labels, command=self._on_widget_change,
            width=260,
        )
        self._dropdown.pack(side="left", pady=8)

        legend = ctk.CTkLabel(
            bar,
            text=(
                f"  {STATUS_EXPOSED} exposed     "
                f"{STATUS_CTK_ONLY} CTk-only     "
                f"{STATUS_BUILDER_ONLY} builder helper"
            ),
            text_color=DIM_FG, font=("Segoe UI", 10),
        )
        legend.pack(side="right", padx=12)

    def _build_table(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color=WINDOW_BG, corner_radius=0)
        wrap.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        # ttk.Treeview gives us a real, scrollable, multi-column grid
        # with negligible code. ttk.Style is a *global* singleton —
        # never call `theme_use(...)` here or every other ttk widget
        # in the app (Object Tree, Inspector, …) instantly loses its
        # styling. Just configure a uniquely-named style on top of
        # whatever theme is already active.
        style = ttk.Style(self)
        style.configure(
            "Inspector.Treeview",
            background="#252526",
            foreground=ROW_FG,
            fieldbackground="#252526",
            bordercolor="#3c3c3c",
            borderwidth=0,
            rowheight=22,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Inspector.Treeview.Heading",
            background=HEADER_BG, foreground=ROW_FG,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
        )
        style.map(
            "Inspector.Treeview",
            background=[("selected", "#094771")],
            foreground=[("selected", "#ffffff")],
        )

        cols = ("status", "name", "ctk_default", "builder_default")
        self._tree = ttk.Treeview(
            wrap, columns=cols, show="headings",
            style="Inspector.Treeview", selectmode="browse",
        )
        self._tree.heading("status", text="")
        self._tree.heading("name", text="Property")
        self._tree.heading("ctk_default", text="CTk default")
        self._tree.heading("builder_default", text="Builder default")
        self._tree.column("status", width=40, anchor="center", stretch=False)
        self._tree.column("name", width=200, stretch=False)
        self._tree.column("ctk_default", width=200, stretch=True)
        self._tree.column("builder_default", width=200, stretch=True)

        # Coloured tags so the status column reads at a glance.
        bold = (tkfont.nametofont("TkDefaultFont").cget("family"), 10, "bold")
        self._tree.tag_configure("good", foreground=ACCENT_GOOD, font=bold)
        self._tree.tag_configure("warn", foreground=ACCENT_WARN, font=bold)
        self._tree.tag_configure("helper", foreground=ACCENT_HELPER, font=bold)

        sb = ttk.Scrollbar(wrap, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Status footer — surfaced summary counts so you can see at a
        # glance how complete coverage is for the chosen widget.
        self._status_lbl = ctk.CTkLabel(
            self, text="", text_color=DIM_FG,
            font=("Segoe UI", 10), anchor="w",
        )
        self._status_lbl.pack(fill="x", padx=12, pady=(0, 8))

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------
    def _on_widget_change(self, label: str) -> None:
        idx = self._label_to_index.get(label)
        if idx is None:
            return
        descriptor, preset = self._entries[idx]
        self._populate(descriptor, preset)

    def _populate(self, descriptor, preset: dict) -> None:
        self._tree.delete(*self._tree.get_children())

        ctk_cls = _ctk_class_for(descriptor)
        ctk_defaults: dict[str, object] = (
            _ctk_kwargs(ctk_cls) if ctk_cls is not None else {}
        )
        # Preset overrides win over the descriptor's bare defaults so
        # the Builder column reflects what the palette entry actually
        # commits on drop (Vertical Layout's `layout_type=vbox`, etc.).
        builder_defaults = dict(getattr(descriptor, "default_properties", {}))
        builder_defaults.update(preset)

        # Honour each schema row's `hidden_when` lambda against the
        # effective preset state — keeps misleading rows like
        # `grid_rows` / `grid_cols` out of the table for vbox/hbox
        # presets, where they exist in default_properties but the
        # Properties panel never shows them.
        hidden_keys: set[str] = set()
        for prop in getattr(descriptor, "property_schema", ()):
            name = prop.get("name")
            hide_fn = prop.get("hidden_when")
            if not name or hide_fn is None:
                continue
            try:
                if hide_fn(builder_defaults):
                    hidden_keys.add(name)
            except Exception:
                pass
        for k in hidden_keys:
            builder_defaults.pop(k, None)

        # Stable display order: every CTk kwarg first (their own order
        # from the signature), then any builder-only helpers sorted
        # alphabetically so they're easy to scan.
        ctk_keys = list(ctk_defaults.keys())
        ctk_keyset = set(ctk_keys)
        builder_only_keys = sorted(
            k for k in builder_defaults if k not in ctk_keyset
        )

        good = warn = helper = 0

        for name in ctk_keys:
            ctk_val = _format_value(ctk_defaults[name])
            if name in builder_defaults:
                status, tag = STATUS_EXPOSED, "good"
                builder_val = _format_value(builder_defaults[name])
                good += 1
            else:
                status, tag = STATUS_CTK_ONLY, "warn"
                builder_val = "—"
                warn += 1
            self._tree.insert(
                "", "end",
                values=(status, name, ctk_val, builder_val),
                tags=(tag,),
            )

        for name in builder_only_keys:
            self._tree.insert(
                "", "end",
                values=(
                    STATUS_BUILDER_ONLY, name,
                    "—", _format_value(builder_defaults[name]),
                ),
                tags=("helper",),
            )
            helper += 1

        ctk_label = ctk_cls.__name__ if ctk_cls is not None else "—"
        self._status_lbl.configure(
            text=(
                f"CTk class: {ctk_label}    "
                f"{STATUS_EXPOSED} {good} exposed    "
                f"{STATUS_CTK_ONLY} {warn} CTk-only    "
                f"{STATUS_BUILDER_ONLY} {helper} builder helper"
            ),
        )


def _format_value(value: object) -> str:
    if value is None:
        return "None"
    if isinstance(value, str):
        return repr(value)
    return repr(value)
