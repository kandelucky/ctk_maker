"""Visual reference windows for the unified design tokens.

Triggered via Ctrl+Shift+Alt+1..4 from the main window. Each renders
a different content pattern (list, form, log, cards) over the shared
``app.ui.style`` palette so the visual language can be evaluated as a
whole. Visuals only — no logic.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from app.ui import style
from app.ui.managed_window import ManagedToplevel
from app.ui.system_fonts import ui_font


# ----------------------------------------------------------------------
# A — Toolbar + Treeview list

class TestWindowA(ManagedToplevel):
    window_key = "dev_test_a"
    window_title = "A — List"
    default_size = (520, 360)
    min_size = (320, 220)
    fg_color = style.PANEL_BG
    panel_padding = (0, 0)

    def build_content(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, fg_color=style.PANEL_BG, corner_radius=0)

        bar = style.make_toolbar(frame)
        bar.pack(fill="x")
        style.pack_toolbar_button(
            style.primary_button(bar, "+ Add"), first=True,
        )
        style.pack_toolbar_button(style.secondary_button(bar, "Edit"))
        style.pack_toolbar_button(
            style.secondary_button(bar, "Duplicate", width=78),
        )
        style.pack_toolbar_button(style.danger_button(bar, "Delete"))

        wrap = tk.Frame(frame, bg=style.BG, highlightthickness=0)
        wrap.pack(fill="both", expand=True)

        style_name = "TestA.Treeview"
        style.apply_tree_style(wrap, style_name)

        tree = ttk.Treeview(
            wrap, columns=("type", "value"),
            show="tree headings",
            style=style_name,
            selectmode="browse",
        )
        tree.heading("#0", text="Name")
        tree.heading("type", text="Type")
        tree.heading("value", text="Value")
        tree.column("#0", width=160)
        tree.column("type", width=80, anchor="w")
        tree.column("value", width=200, anchor="w")
        for i, (name, t, v) in enumerate([
            ("foo", "string", "hello world"),
            ("count", "int", "42"),
            ("active", "bool", "true"),
            ("color", "color", "#ff8800"),
            ("ratio", "float", "0.75"),
            ("label", "string", "untitled"),
        ]):
            tree.insert("", "end", iid=str(i), text=name, values=(t, v))
        tree.pack(side="left", fill="both", expand=True)

        sb = style.styled_scrollbar(wrap, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

        return frame


# ----------------------------------------------------------------------
# B — Toolbar + form

class TestWindowB(ManagedToplevel):
    window_key = "dev_test_b"
    window_title = "B — Form"
    default_size = (480, 360)
    min_size = (340, 260)
    fg_color = style.PANEL_BG
    panel_padding = (0, 0)

    def build_content(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, fg_color=style.PANEL_BG, corner_radius=0)

        bar = style.make_toolbar(frame)
        bar.pack(fill="x")
        style.pack_toolbar_button(
            style.primary_button(bar, "Save"), first=True,
        )
        style.pack_toolbar_button(
            style.secondary_button(bar, "Reset", width=70),
        )

        form = ctk.CTkFrame(frame, fg_color=style.PANEL_BG, corner_radius=0)
        form.pack(fill="both", expand=True,
                  padx=style.CONTENT_PADX, pady=style.CONTENT_PADY)

        rows = [
            ("Name", "untitled"),
            ("Description", ""),
            ("Path", "C:/projects/example"),
            ("Author", ""),
            ("Tags", "tag1, tag2"),
        ]
        for label_text, default in rows:
            row = ctk.CTkFrame(form, fg_color=style.PANEL_BG, corner_radius=0)
            row.pack(fill="x", pady=4)
            style.styled_label(
                row, f"{label_text}:", width=90, anchor="w",
            ).pack(side="left", padx=(0, 8))
            entry = style.styled_entry(row, placeholder_text=label_text.lower())
            entry.pack(side="left", fill="x", expand=True)
            if default:
                entry.insert(0, default)

        return frame


# ----------------------------------------------------------------------
# C — Toolbar + log/text

class TestWindowC(ManagedToplevel):
    window_key = "dev_test_c"
    window_title = "C — Log"
    default_size = (560, 380)
    min_size = (340, 260)
    fg_color = style.PANEL_BG
    panel_padding = (0, 0)

    def build_content(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, fg_color=style.PANEL_BG, corner_radius=0)

        bar = style.make_toolbar(frame)
        bar.pack(fill="x")
        style.pack_toolbar_button(
            style.secondary_button(bar, "Copy"), first=True,
        )
        style.pack_toolbar_button(style.secondary_button(bar, "Clear"))
        style.pack_toolbar_button(style.danger_button(bar, "Stop"))

        wrap = tk.Frame(frame, bg=style.BG, highlightthickness=0)
        wrap.pack(fill="both", expand=True)

        text = tk.Text(
            wrap,
            bg=style.TREE_BG, fg=style.TREE_FG,
            insertbackground=style.TREE_FG,
            selectbackground=style.TREE_SELECTED_BG,
            selectforeground="#ffffff",
            relief="flat", borderwidth=0,
            font=("Consolas", 10),
            padx=10, pady=8,
            wrap="none",
        )
        sample = [
            "[12:00:01] INFO  app started",
            "[12:00:01] INFO  loading project: untitled.ctkproj",
            "[12:00:02] DEBUG event_bus subscribed: history_changed",
            "[12:00:02] INFO  3 widgets loaded",
            "[12:00:03] WARN  missing texture: assets/img/missing.png",
            "[12:00:04] INFO  project loaded in 0.12s",
            "[12:00:05] DEBUG render pass complete",
            "[12:00:06] INFO  user opened TestWindowC",
        ]
        text.insert("end", "\n".join(sample))
        text.configure(state="disabled")
        text.pack(side="left", fill="both", expand=True)

        sb = style.styled_scrollbar(wrap, command=text.yview)
        text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

        return frame


# ----------------------------------------------------------------------
# D — Toolbar + card grid

class TestWindowD(ManagedToplevel):
    window_key = "dev_test_d"
    window_title = "D — Cards"
    default_size = (640, 440)
    min_size = (420, 300)
    fg_color = style.PANEL_BG
    panel_padding = (0, 0)

    def build_content(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self, fg_color=style.PANEL_BG, corner_radius=0)

        bar = style.make_toolbar(frame)
        bar.pack(fill="x")
        style.pack_toolbar_button(
            style.primary_button(bar, "+ Card", width=80), first=True,
        )
        style.pack_toolbar_button(
            style.secondary_button(bar, "Refresh", width=78),
        )

        grid = ctk.CTkFrame(frame, fg_color=style.BG, corner_radius=0)
        grid.pack(fill="both", expand=True,
                  padx=style.CONTENT_PADX, pady=style.CONTENT_PADY)

        cards = [
            ("Window", "Toplevel container"),
            ("Frame", "Layout root"),
            ("Button", "Action trigger"),
            ("Entry", "Text input"),
            ("Treeview", "Hierarchical list"),
            ("Canvas", "Drawing surface"),
        ]
        for i, (title, body) in enumerate(cards):
            r, c = divmod(i, 3)
            card = ctk.CTkFrame(
                grid, fg_color=style.HEADER_BG,
                border_color=style.BORDER, border_width=1,
                corner_radius=4,
            )
            card.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")
            style.styled_label(
                card, title, font=ui_font(13, "bold"),
            ).pack(anchor="w", padx=12, pady=(10, 2))
            style.styled_label(
                card, body, text_color=style.EMPTY_FG,
            ).pack(anchor="w", padx=12, pady=(0, 12))

        for c in range(3):
            grid.columnconfigure(c, weight=1)
        for r in range(2):
            grid.rowconfigure(r, weight=1)

        return frame


DEV_TEST_WINDOW_CLASSES = (TestWindowA, TestWindowB, TestWindowC, TestWindowD)
