"""Phase 3 Step 1.x — Add Field dialog for Behavior Fields.

UI-driven counterpart to the manual ``ref[<WidgetType>]`` annotation
flow: open a dialog, click a widget on the scene, accept the
auto-suggested field name, hit Add. The dialog handles three side
effects so the user never edits the .py source manually:

1. Inserts ``<field_name>: ref[<WidgetType>]`` into the per-window
   behavior class (above the first method, with detected indent).
2. Adds ``from .._runtime import ref`` and
   ``from customtkinter import <WidgetType>`` to the file's import
   block when missing.
3. Pushes ``SetBehaviorFieldCommand`` so the binding round-trips
   through history + the .ctkproj.

The dialog reuses the visual treatment of ``WidgetPickerDialog`` —
same dark modal chrome, same Treeview-based widget tree — but every
widget is enabled (no type filter) since picking a widget chooses
its type for the new annotation.
"""

from __future__ import annotations

import re
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
_INPUT_BG = "#1a1a1a"
_ERROR_FG = "#ef4444"

_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


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


class AddBehaviorFieldDialog(ctk.CTkToplevel):
    """Modal "Add Field" picker. Result attributes (read after
    ``wait_window``):

    - ``self.selected_widget_id`` — the widget the user picked,
      ``None`` when they cancelled.
    - ``self.field_name`` — sanitised Python identifier for the new
      slot.
    - ``self.widget_type`` — type name to wrap as
      ``ref[<widget_type>]`` in the annotation.
    """

    def __init__(
        self,
        parent,
        document,
        existing_field_names: set[str],
    ):
        super().__init__(parent)
        self.title("Add behavior field")
        self.transient(parent)
        self.grab_set()
        self.configure(fg_color=_BG)
        self.minsize(440, 540)

        self._document = document
        self._existing_field_names = set(existing_field_names)
        self._iid_to_widget_id: dict[str, str] = {}
        self.selected_widget_id: str | None = None
        self.field_name: str = ""
        self.widget_type: str = ""
        # When True, the next widget pick should overwrite the
        # field-name input. Flips False after the user types in the
        # field — manual edits stick from then on so the auto-suggest
        # doesn't fight the user's typing.
        self._field_name_dirty = False

        self._build_ui()
        self._populate_tree()

        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.after(50, _center_on_parent, self)

    # ------------------------------------------------------------------
    # UI scaffold
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        header = ctk.CTkFrame(self, fg_color=_CARD_BG, corner_radius=0)
        header.pack(fill="x", padx=0, pady=0)
        ctk.CTkLabel(
            header, text="Add behavior field",
            text_color=_HEADING_FG,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(
            header,
            text=(
                "Pick a widget on the scene. CTkMaker will write "
                "the annotation + imports."
            ),
            text_color=_BODY_FG,
            font=ctk.CTkFont(size=11),
            anchor="w",
            wraplength=420,
            justify="left",
        ).pack(fill="x", padx=16, pady=(2, 12))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(8, 0))

        style = ttk.Style(self)
        try:
            style.theme_use("default")
        except tk.TclError:
            pass
        style.configure(
            "AddBehaviorField.Treeview",
            background=_CARD_BG,
            fieldbackground=_CARD_BG,
            foreground=_HEADING_FG,
            rowheight=24,
            borderwidth=0,
        )
        style.map(
            "AddBehaviorField.Treeview",
            background=[("selected", _ACCENT_BG)],
            foreground=[("selected", "#ffffff")],
        )
        style.layout(
            "AddBehaviorField.Treeview", [
                ("Treeview.treearea", {"sticky": "nswe"}),
            ],
        )

        tree_frame = tk.Frame(body, bg=_CARD_BG, bd=0, highlightthickness=0)
        tree_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            tree_frame, show="tree",
            style="AddBehaviorField.Treeview",
            selectmode="browse",
        )
        scroll = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview,
        )
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click)

        # Field name input row + inline help.
        input_row = ctk.CTkFrame(self, fg_color="transparent")
        input_row.pack(fill="x", padx=12, pady=(12, 0))
        ctk.CTkLabel(
            input_row, text="Field name:", text_color=_BODY_FG,
            font=ctk.CTkFont(size=11), anchor="w",
        ).pack(side="left", padx=(2, 8))
        self._name_var = tk.StringVar()
        self._name_var.trace_add(
            "write",
            lambda *_a: self._on_name_changed(),
        )
        self._name_entry = ctk.CTkEntry(
            input_row, textvariable=self._name_var, width=220,
            fg_color=_INPUT_BG, border_color=_BTN_BG,
            text_color=_HEADING_FG,
        )
        self._name_entry.pack(side="left")

        self._error_label = ctk.CTkLabel(
            self, text="", text_color=_ERROR_FG,
            font=ctk.CTkFont(size=10), anchor="w",
        )
        self._error_label.pack(fill="x", padx=14, pady=(4, 0))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=12, pady=12)
        ctk.CTkButton(
            footer, text="Cancel", width=80,
            fg_color=_BTN_BG, hover_color=_BTN_HOVER,
            text_color=_HEADING_FG,
            command=self._cancel,
        ).pack(side="right", padx=(8, 0))
        self._add_btn = ctk.CTkButton(
            footer, text="Add", width=80,
            fg_color=_ACCENT_BG, hover_color=_ACCENT_HOVER,
            text_color="#ffffff",
            state="disabled",
            command=self._commit,
        )
        self._add_btn.pack(side="right")

    # ------------------------------------------------------------------
    # Tree population
    # ------------------------------------------------------------------
    def _populate_tree(self) -> None:
        if self._document is None:
            return
        for root in self._document.root_widgets:
            self._insert_node(root, parent_iid="")
        for iid in self._iid_to_widget_id:
            self.tree.item(iid, open=True)

    def _insert_node(self, node, parent_iid: str) -> None:
        widget_label = node.name or node.widget_type
        text = f"{widget_label}   ({node.widget_type})"
        iid = f"w:{node.id}"
        self.tree.insert(parent_iid, "end", iid=iid, text=text)
        self._iid_to_widget_id[iid] = node.id
        for child in node.children:
            self._insert_node(child, parent_iid=iid)

    # ------------------------------------------------------------------
    # Selection + name handling
    # ------------------------------------------------------------------
    def _on_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            self._add_btn.configure(state="disabled")
            return
        iid = sel[0]
        widget_id = self._iid_to_widget_id.get(iid)
        if not widget_id:
            return
        node = self._find_node_by_id(widget_id)
        if node is None:
            return
        self.selected_widget_id = widget_id
        self.widget_type = node.widget_type
        if not self._field_name_dirty:
            from app.io.scripts import suggest_behavior_field_name
            suggestion = suggest_behavior_field_name(
                node.name, node.widget_type, self._existing_field_names,
            )
            # Suppress trace fire-back so writing the suggestion
            # doesn't flip ``_field_name_dirty`` to True.
            self._field_name_var_set_silently(suggestion)
        self._validate()

    def _on_double_click(self, _event=None) -> None:
        if self._add_btn.cget("state") == "normal":
            self._commit()

    def _on_name_changed(self) -> None:
        self._field_name_dirty = True
        self._validate()

    def _field_name_var_set_silently(self, value: str) -> None:
        self._field_name_dirty = False
        self._name_var.set(value)
        # Re-mark clean — the trace just fired and set dirty=True.
        self._field_name_dirty = False

    def _find_node_by_id(self, widget_id: str):
        if self._document is None:
            return None

        def walk(node):
            if node.id == widget_id:
                return node
            for child in node.children:
                hit = walk(child)
                if hit is not None:
                    return hit
            return None

        for root in self._document.root_widgets:
            hit = walk(root)
            if hit is not None:
                return hit
        return None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _validate(self) -> None:
        if self.selected_widget_id is None:
            self._error_label.configure(text="")
            self._add_btn.configure(state="disabled")
            return
        name = self._name_var.get().strip()
        if not name:
            self._error_label.configure(text="Pick a name for the field.")
            self._add_btn.configure(state="disabled")
            return
        if not _IDENT_RE.match(name):
            self._error_label.configure(
                text="Use a Python identifier "
                     "(letters, digits, underscore — no spaces).",
            )
            self._add_btn.configure(state="disabled")
            return
        if name in self._existing_field_names:
            self._error_label.configure(
                text=f"`{name}` already exists on the class.",
            )
            self._add_btn.configure(state="disabled")
            return
        self._error_label.configure(text="")
        self._add_btn.configure(state="normal")

    # ------------------------------------------------------------------
    # Commit / cancel
    # ------------------------------------------------------------------
    def _commit(self) -> None:
        if self.selected_widget_id is None:
            return
        name = self._name_var.get().strip()
        if not name or not _IDENT_RE.match(name):
            return
        if name in self._existing_field_names:
            return
        self.field_name = name
        self.destroy()

    def _cancel(self) -> None:
        self.selected_widget_id = None
        self.field_name = ""
        self.widget_type = ""
        self.destroy()


def run_add_behavior_field_dialog(
    parent,
    document,
    existing_field_names: set[str],
) -> tuple[str, str, str] | None:
    """Open the Add Field dialog modally. Returns ``None`` on cancel,
    or a ``(widget_id, field_name, widget_type)`` tuple the caller
    feeds into the annotation writer + binding command.
    """
    if document is None:
        return None
    dialog = AddBehaviorFieldDialog(
        parent,
        document=document,
        existing_field_names=existing_field_names,
    )
    parent.wait_window(dialog)
    if dialog.selected_widget_id is None or not dialog.field_name:
        return None
    return (
        dialog.selected_widget_id,
        dialog.field_name,
        dialog.widget_type,
    )
