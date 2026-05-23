"""Modal confirmation dialogs for the two destructive operations on a
project's structure:

- ``WindowDeleteDialog`` — runs before removing a Document (window),
  surfacing the widget + local-variable counts so the user always
  knows what's about to disappear (even for empty forms).
- ``PageDeleteDialog`` — runs before deleting a whole page.

Both dialogs return their decision via instance attributes the caller
reads after ``wait_window``.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from app.ui.managed_window import ManagedToplevel
from app.ui.system_fonts import ui_font

_BG = "#1a1a1a"
_HEADING_FG = "#e6e6e6"
_BODY_FG = "#bdbdbd"
_CARD_BG = "#252526"
_BTN_BG = "#3c3c3c"
_BTN_HOVER = "#4a4a4a"
_DANGER_BG = "#a23a3a"
_DANGER_HOVER = "#bf4646"


def _parent_centered(parent, w: int, h: int) -> tuple[int, int]:
    try:
        parent.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        return (
            max(0, px + (pw - w) // 2),
            max(0, py + (ph - h) // 2),
        )
    except tk.TclError:
        return (100, 100)


class WindowDeleteDialog(ManagedToplevel):
    """Confirmation gate for ``DeleteDocumentCommand``. Shown for every
    window deletion regardless of what the window contains — the user
    always knows what's about to disappear, even for empty forms (no
    surprise loss of an in-progress dialog).

    On ``[Delete window]`` the caller reads ``self.confirmed`` — True
    only when Delete was clicked.
    """

    window_title = "Delete window"
    min_size = (440, 200)
    fg_color = _BG
    panel_padding = (0, 0)
    modal = True
    window_resizable = (False, False)

    def __init__(
        self,
        parent,
        window_name: str,
        widget_count: int,
        local_var_count: int,
    ):
        self.confirmed: bool = False
        self._window_name = window_name
        self._widget_count = widget_count
        self._local_var_count = local_var_count
        self.default_size = (490, 240)
        super().__init__(parent)

    def default_offset(self, parent) -> tuple[int, int]:
        return _parent_centered(parent, *self.default_size)

    def build_content(self) -> ctk.CTkFrame:
        container = ctk.CTkFrame(self, fg_color="transparent")

        body = ctk.CTkFrame(container, fg_color="transparent")
        body.pack(padx=22, pady=(20, 8), fill="x")

        ctk.CTkLabel(
            body, text=f"Delete \"{self._window_name}\"?",
            font=ui_font(14, "bold"),
            text_color=_HEADING_FG, anchor="w",
        ).pack(anchor="w", pady=(0, 10))

        # Contents card — always shown so empty windows surface the
        # zero counts (the user explicitly asked for "always know
        # what gets deleted").
        info = ctk.CTkFrame(
            body, fg_color=_CARD_BG, corner_radius=4,
        )
        info.pack(fill="x", pady=(0, 12))
        bullets = [
            f"• {self._widget_count} widget"
            f"{'s' if self._widget_count != 1 else ''}",
            f"• {self._local_var_count} local variable"
            f"{'s' if self._local_var_count != 1 else ''} "
            "(will be lost)",
        ]
        ctk.CTkLabel(
            info, text="\n".join(bullets),
            font=ui_font(10),
            text_color=_BODY_FG,
            justify="left", anchor="w", wraplength=420,
        ).pack(anchor="w", padx=12, pady=10)

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(fill="x", padx=22, pady=(16, 16))
        ctk.CTkButton(
            footer, text="Delete window",
            width=140, height=34, corner_radius=4,
            fg_color=_DANGER_BG, hover_color=_DANGER_HOVER,
            command=self._on_delete,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel",
            width=90, height=34, corner_radius=4,
            fg_color=_BTN_BG, hover_color=_BTN_HOVER,
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))
        return container

    def _on_delete(self) -> None:
        self.confirmed = True
        self.destroy()

    def _on_cancel(self) -> None:
        self.confirmed = False
        self.destroy()


class PageDeleteDialog(ManagedToplevel):
    """Confirmation gate for deleting a whole page.

    On ``[Delete page]`` the caller reads ``self.confirmed`` — True
    only when Delete was clicked.
    """

    window_title = "Delete page"
    min_size = (440, 190)
    fg_color = _BG
    panel_padding = (0, 0)
    modal = True
    window_resizable = (False, False)

    def __init__(self, parent, page_name: str):
        self.confirmed: bool = False
        self._page_name = page_name
        self.default_size = (470, 210)
        super().__init__(parent)

    def default_offset(self, parent) -> tuple[int, int]:
        return _parent_centered(parent, *self.default_size)

    def build_content(self) -> ctk.CTkFrame:
        container = ctk.CTkFrame(self, fg_color="transparent")

        body = ctk.CTkFrame(container, fg_color="transparent")
        body.pack(padx=22, pady=(20, 8), fill="x")

        ctk.CTkLabel(
            body, text=f"Delete \"{self._page_name}\"?",
            font=ui_font(14, "bold"),
            text_color=_HEADING_FG, anchor="w",
        ).pack(anchor="w", pady=(0, 10))
        ctk.CTkLabel(
            body,
            text=(
                "The page file and all of its widgets will be removed."
            ),
            font=ui_font(10), text_color=_BODY_FG,
            justify="left", anchor="w", wraplength=420,
        ).pack(anchor="w", pady=(0, 4))

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(fill="x", padx=22, pady=(16, 16))
        ctk.CTkButton(
            footer, text="Delete page",
            width=130, height=34, corner_radius=4,
            fg_color=_DANGER_BG, hover_color=_DANGER_HOVER,
            command=self._on_delete,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel",
            width=90, height=34, corner_radius=4,
            fg_color=_BTN_BG, hover_color=_BTN_HOVER,
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))
        return container

    def _on_delete(self) -> None:
        self.confirmed = True
        self.destroy()

    def _on_cancel(self) -> None:
        self.confirmed = False
        self.destroy()


# ---------------------------------------------------------------------
# Orchestration helpers — keep call sites tiny
# ---------------------------------------------------------------------
def run_window_delete_flow(parent, project, doc) -> bool:
    """Pop ``WindowDeleteDialog`` for a window about to be deleted.
    Returns ``True`` when the caller should proceed with the actual
    deletion, ``False`` on Cancel.
    """
    widget_count = _count_widgets_under(doc)
    local_var_count = len(getattr(doc, "local_variables", []) or [])
    dialog = WindowDeleteDialog(
        parent,
        window_name=doc.name,
        widget_count=widget_count,
        local_var_count=local_var_count,
    )
    parent.wait_window(dialog)
    return dialog.confirmed


def run_page_delete_flow(parent, folder_path, page_entry) -> bool:
    """Pop ``PageDeleteDialog`` for a page about to be deleted. Returns
    ``True`` when the caller should proceed with the actual page
    deletion, ``False`` on Cancel.

    ``page_entry`` is the page's ``project.json`` dict (``name`` +
    ``file``). ``folder_path`` is accepted for call-site symmetry but
    no longer used now that pages own no behavior-script folder.
    """
    page_name = (
        page_entry.get("name") or "page"
        if isinstance(page_entry, dict) else "page"
    )
    dialog = PageDeleteDialog(parent, page_name=page_name)
    parent.wait_window(dialog)
    return dialog.confirmed


def _count_widgets_under(doc) -> int:
    total = 0
    stack = list(doc.root_widgets)
    while stack:
        node = stack.pop()
        total += 1
        stack.extend(node.children)
    return total
