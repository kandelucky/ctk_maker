"""Phase 3 Step 1 — modal widget picker for Behavior Field slots.

Opens from the Properties panel's "Behavior Fields" group when the
user clicks ``[Pick widget]`` next to a ``ref[<WidgetType>]`` slot.
Renders the active document's widget tree, greys out widgets whose
type doesn't match the slot's annotation, and returns the chosen
widget id (or ``None`` on cancel).

The picker scopes to the active document only — cross-document
references are out of scope for v1.8.0. A future iteration can add
a "Other windows" tab when the user actually needs it.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

_BG = "#1a1a1a"
_HEADING_FG = "#e6e6e6"
_BODY_FG = "#bdbdbd"
_CARD_BG = "#252526"
_BTN_BG = "#3c3c3c"
_BTN_HOVER = "#4a4a4a"
_ACCENT_BG = "#1f6feb"
_ACCENT_HOVER = "#388bfd"
_DISABLED_FG = "#6a6a6a"


def _center_on_parent(dialog: ctk.CTkToplevel) -> None:
    dialog.update_idletasks()
    parent = dialog.master
    try:
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
    except tk.TclError:
        return
    w = dialog.winfo_width()
    h = dialog.winfo_height()
    x = px + (pw - w) // 2
    y = py + (ph - h) // 2
    dialog.geometry(f"+{max(0, x)}+{max(0, y)}")


class WidgetPickerDialog(ctk.CTkToplevel):
    """Modal widget picker. ``expected_type`` is the annotation type
    name (e.g., ``"CTkLabel"``). Widgets whose ``widget_type`` differs
    render as disabled rows so the user sees the full tree but can
    only pick compatible items.

    Result attribute (read after ``wait_window``):
    - ``self.selected_widget_id`` — chosen id, or ``None`` on cancel.
    """

    def __init__(
        self,
        parent,
        document,
        expected_type: str,
        field_name: str,
        current_widget_id: str = "",
    ):
        super().__init__(parent)
        self.title(f"Pick widget for {field_name}")
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=_BG)
        self.minsize(420, 480)

        self._document = document
        self._expected_type = expected_type
        self._current_widget_id = current_widget_id
        self.selected_widget_id: str | None = None
        self._iid_to_widget_id: dict[str, str] = {}
        self._compatible_iids: set[str] = set()

        self._build_ui(field_name, expected_type)
        self._populate_tree()

        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.after(50, _center_on_parent, self)

    # ------------------------------------------------------------------
    # UI scaffold
    # ------------------------------------------------------------------
    def _build_ui(self, field_name: str, expected_type: str) -> None:
        header = ctk.CTkFrame(self, fg_color=_CARD_BG, corner_radius=0)
        header.pack(fill="x", padx=0, pady=0)
        ctk.CTkLabel(
            header, text=f"Pick widget for «{field_name}»",
            text_color=_HEADING_FG,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(
            header,
            text=f"Expected type: {expected_type}",
            text_color=_BODY_FG,
            font=ctk.CTkFont(size=11),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(2, 12))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(8, 0))

        # ttk Treeview gives us indented hierarchy + per-item tags
        # (so we can grey-out incompatible rows) without a custom
        # canvas paint pass. Theme it dark to match CTk surroundings.
        style = ttk.Style(self)
        try:
            style.theme_use("default")
        except tk.TclError:
            pass
        style.configure(
            "WidgetPicker.Treeview",
            background=_CARD_BG,
            fieldbackground=_CARD_BG,
            foreground=_HEADING_FG,
            rowheight=24,
            borderwidth=0,
        )
        style.map(
            "WidgetPicker.Treeview",
            background=[("selected", _ACCENT_BG)],
            foreground=[("selected", "#ffffff")],
        )
        style.layout(
            "WidgetPicker.Treeview", [
                ("Treeview.treearea", {"sticky": "nswe"}),
            ],
        )

        tree_frame = tk.Frame(body, bg=_CARD_BG, bd=0, highlightthickness=0)
        tree_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            tree_frame, show="tree",
            style="WidgetPicker.Treeview",
            selectmode="browse",
        )
        scroll = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview,
        )
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.tree.tag_configure("disabled", foreground=_DISABLED_FG)
        self.tree.tag_configure("compatible", foreground=_HEADING_FG)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=12, pady=12)
        # Clear binding (when one already exists) — sets the slot to
        # empty so the field is unbound. Hidden when the slot was
        # already empty so the dialog stays focused on positive
        # actions.
        if self._current_widget_id:
            ctk.CTkButton(
                footer, text="Clear", width=80,
                fg_color=_BTN_BG, hover_color=_BTN_HOVER,
                text_color=_HEADING_FG,
                command=self._clear,
            ).pack(side="left")
        ctk.CTkButton(
            footer, text="Cancel", width=80,
            fg_color=_BTN_BG, hover_color=_BTN_HOVER,
            text_color=_HEADING_FG,
            command=self._cancel,
        ).pack(side="right", padx=(8, 0))
        self._pick_btn = ctk.CTkButton(
            footer, text="Pick", width=80,
            fg_color=_ACCENT_BG, hover_color=_ACCENT_HOVER,
            text_color="#ffffff",
            state="disabled",
            command=self._pick,
        )
        self._pick_btn.pack(side="right")

    # ------------------------------------------------------------------
    # Tree population
    # ------------------------------------------------------------------
    def _populate_tree(self) -> None:
        if self._document is None:
            return
        for root in self._document.root_widgets:
            self._insert_node(root, parent_iid="")
        # Open the whole tree by default so the user doesn't fight
        # disclosure triangles when picking — a small project
        # benefits, a huge project still scrolls fine with the
        # scrollbar.
        for iid in self._iid_to_widget_id:
            self.tree.item(iid, open=True)
        # Pre-select the current binding when one exists; otherwise
        # focus on the first compatible row so Enter / double-click
        # works without a manual click.
        target_iid: str | None = None
        if self._current_widget_id:
            for iid, wid in self._iid_to_widget_id.items():
                if wid == self._current_widget_id:
                    target_iid = iid
                    break
        if target_iid is None and self._compatible_iids:
            target_iid = next(iter(sorted(self._compatible_iids)))
        if target_iid is not None:
            self.tree.selection_set(target_iid)
            self.tree.focus(target_iid)
            self.tree.see(target_iid)

    def _insert_node(self, node, parent_iid: str) -> None:
        widget_label = node.name or node.widget_type
        compatible = node.widget_type == self._expected_type
        type_hint = (
            f" ({node.widget_type})" if not compatible else ""
        )
        suffix = "" if compatible else "  — wrong type"
        text = f"{widget_label}{type_hint}{suffix}"
        iid = f"w:{node.id}"
        tags = ("compatible",) if compatible else ("disabled",)
        self.tree.insert(
            parent_iid, "end", iid=iid, text=text, tags=tags,
        )
        self._iid_to_widget_id[iid] = node.id
        if compatible:
            self._compatible_iids.add(iid)
        for child in node.children:
            self._insert_node(child, parent_iid=iid)

    # ------------------------------------------------------------------
    # Selection handling
    # ------------------------------------------------------------------
    def _on_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            self._pick_btn.configure(state="disabled")
            return
        iid = sel[0]
        if iid in self._compatible_iids:
            self._pick_btn.configure(state="normal")
        else:
            self._pick_btn.configure(state="disabled")

    def _on_double_click(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        if sel[0] in self._compatible_iids:
            self._pick()

    # ------------------------------------------------------------------
    # Commit / cancel
    # ------------------------------------------------------------------
    def _pick(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid not in self._compatible_iids:
            return
        self.selected_widget_id = self._iid_to_widget_id.get(iid)
        self.destroy()

    def _clear(self) -> None:
        # Sentinel — empty string distinguishes "user chose to unbind"
        # from "user cancelled". The caller checks for ``""`` explicitly.
        self.selected_widget_id = ""
        self.destroy()

    def _cancel(self) -> None:
        self.selected_widget_id = None
        self.destroy()


def run_widget_picker(
    parent,
    document,
    expected_type: str,
    field_name: str,
    current_widget_id: str = "",
) -> str | None:
    """Open the picker modally. Returns:
    - widget id string when the user picked one,
    - empty string when they hit Clear (unbind),
    - ``None`` when they cancelled.
    """
    if document is None:
        return None
    dialog = WidgetPickerDialog(
        parent,
        document=document,
        expected_type=expected_type,
        field_name=field_name,
        current_widget_id=current_widget_id,
    )
    parent.wait_window(dialog)
    return dialog.selected_widget_id
