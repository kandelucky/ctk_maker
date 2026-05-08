"""Visual design tokens and widget factories for the app.

Centralizes the color palette, spacing constants, and pre-styled
button helpers so every ``ManagedToplevel``-based window shares one
visual language. Modeled after the Variables window's look — VS
Code-adjacent dark theme with a blue primary, neutral secondary, and
muted-red destructive action.

Adopt for new windows; existing ones (Variables, History, ...) keep
their inline constants until the bulk migration.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

import customtkinter as ctk

from app.ui.system_fonts import ui_font  # re-exported for callers

# ----------------------------------------------------------------------
# Color tokens

BG = "#1e1e1e"
PANEL_BG = "#252526"
TOOLBAR_BG = "#2a2a2a"
HEADER_BG = "#2d2d30"
TREE_BG = "#1e1e1e"
TREE_FG = "#cccccc"
TREE_SELECTED_BG = "#094771"
TREE_HEADING_BG = HEADER_BG
TREE_HEADING_FG = TREE_FG
EMPTY_FG = "#666666"
BORDER = "#3a3a3a"

# Buttons
PRIMARY_BG = "#0e639c"
PRIMARY_HOVER = "#1177bb"
SECONDARY_BG = "#3c3c3c"
SECONDARY_HOVER = "#4a4a4a"
DANGER_BG = "#7a2c2c"
DANGER_HOVER = "#9c3838"

# Inputs
ENTRY_BG = "#1e1e1e"
ENTRY_FG = TREE_FG
ENTRY_BORDER = BORDER

# Scrollbar
SCROLLBAR_BUTTON = "#3a3a3a"
SCROLLBAR_HOVER = "#4a4a4a"

# ----------------------------------------------------------------------
# Spacing

TOOLBAR_HEIGHT = 44
TOOLBAR_PADX = 8
TOOLBAR_BTN_GAP = 4
TOOLBAR_PADY = 4

BUTTON_HEIGHT = 30
BUTTON_RADIUS = 3
BUTTON_FONT_SIZE = 11

CONTENT_PADX = 12
CONTENT_PADY = 12

TREE_ROW_HEIGHT = 22
TREE_FONT_SIZE = 10


# ----------------------------------------------------------------------
# Toolbar

def make_toolbar(parent) -> tk.Frame:
    """Return a 54px-high toolbar frame in the app's toolbar color."""
    bar = tk.Frame(
        parent, bg=TOOLBAR_BG,
        height=TOOLBAR_HEIGHT, highlightthickness=0,
    )
    bar.pack_propagate(False)
    return bar


def pack_toolbar_button(btn, first: bool = False) -> None:
    """Pack a button into a toolbar row with consistent spacing."""
    padx = (TOOLBAR_PADX, TOOLBAR_BTN_GAP) if first else (0, TOOLBAR_BTN_GAP)
    btn.pack(side="left", padx=padx, pady=TOOLBAR_PADY)


# ----------------------------------------------------------------------
# Buttons

def primary_button(
    parent, text: str,
    command: Optional[Callable] = None,
    width: int = 70,
) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, width=width, height=BUTTON_HEIGHT,
        corner_radius=BUTTON_RADIUS, font=ui_font(BUTTON_FONT_SIZE),
        fg_color=PRIMARY_BG, hover_color=PRIMARY_HOVER,
        command=command,
    )


def secondary_button(
    parent, text: str,
    command: Optional[Callable] = None,
    width: int = 64,
) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, width=width, height=BUTTON_HEIGHT,
        corner_radius=BUTTON_RADIUS, font=ui_font(BUTTON_FONT_SIZE),
        fg_color=SECONDARY_BG, hover_color=SECONDARY_HOVER,
        command=command,
    )


def danger_button(
    parent, text: str,
    command: Optional[Callable] = None,
    width: int = 64,
) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, width=width, height=BUTTON_HEIGHT,
        corner_radius=BUTTON_RADIUS, font=ui_font(BUTTON_FONT_SIZE),
        fg_color=DANGER_BG, hover_color=DANGER_HOVER,
        command=command,
    )


# ----------------------------------------------------------------------
# Tree style

def apply_tree_style(parent: tk.Misc, style_name: str) -> ttk.Style:
    """Configure a ttk Treeview style with the app's dark palette."""
    s = ttk.Style(parent)
    s.configure(
        style_name,
        background=TREE_BG,
        fieldbackground=TREE_BG,
        foreground=TREE_FG,
        rowheight=TREE_ROW_HEIGHT,
        borderwidth=0,
        font=ui_font(TREE_FONT_SIZE),
    )
    s.map(
        style_name,
        background=[("selected", TREE_SELECTED_BG)],
        foreground=[("selected", "#ffffff")],
    )
    s.configure(
        f"{style_name}.Heading",
        background=TREE_HEADING_BG,
        foreground=TREE_HEADING_FG,
        font=ui_font(TREE_FONT_SIZE, "bold"),
        relief="flat",
    )
    return s


# ----------------------------------------------------------------------
# Inputs

def styled_entry(parent, **kwargs) -> ctk.CTkEntry:
    defaults = dict(
        fg_color=ENTRY_BG,
        text_color=ENTRY_FG,
        border_color=ENTRY_BORDER,
        border_width=1,
        corner_radius=3,
        height=BUTTON_HEIGHT,
        font=ui_font(BUTTON_FONT_SIZE),
    )
    defaults.update(kwargs)
    return ctk.CTkEntry(parent, **defaults)


def styled_label(parent, text: str, **kwargs) -> ctk.CTkLabel:
    defaults = dict(
        text=text,
        text_color=TREE_FG,
        font=ui_font(BUTTON_FONT_SIZE),
        fg_color="transparent",
    )
    defaults.update(kwargs)
    return ctk.CTkLabel(parent, **defaults)


def styled_scrollbar(parent, command, orientation: str = "vertical") -> ctk.CTkScrollbar:
    return ctk.CTkScrollbar(
        parent, orientation=orientation, command=command,
        width=10, corner_radius=4,
        fg_color="transparent",
        button_color=SCROLLBAR_BUTTON,
        button_hover_color=SCROLLBAR_HOVER,
    )
