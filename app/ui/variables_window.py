"""Variables inspector — manages the project's shared-state variables.

``VariablesPanel`` is an embeddable ``CTkFrame`` (Treeview + toolbar);
``VariablesWindow`` is a thin floating wrapper around it. Variables are
the foundation of the visual scripting story (Phase 1): widgets bind
to a variable via the Properties panel, and the runtime keeps every
bound widget in sync via Tkinter's built-in ``textvariable`` /
``variable`` mechanism.

The panel is read-only mirror of ``project.variables``; mutations push
Command objects through ``project.history`` so undo / redo Just Works.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from app.core.commands import (
    AddVariableCommand,
    ChangeVariableDefaultCommand,
    ChangeVariableTypeCommand,
    DeleteVariableCommand,
    RenameVariableCommand,
)
from app.core.variables import (
    VAR_TYPES,
    VariableEntry,
    coerce_default_for_type,
    sanitize_var_name,
)

if TYPE_CHECKING:
    from app.core.project import Project

BG = "#1e1e1e"
PANEL_BG = "#252526"
TOOLBAR_BG = "#2a2a2a"
TREE_BG = "#1e1e1e"
TREE_FG = "#cccccc"
TREE_SELECTED_BG = "#094771"
TREE_HEADING_BG = "#2d2d30"
TREE_HEADING_FG = "#cccccc"
EMPTY_FG = "#666666"
BORDER = "#3a3a3a"

DIALOG_W = 420
DIALOG_H = 360
TREE_ROW_HEIGHT = 22
TREE_FONT_SIZE = 10

EMPTY_TEXT = "No variables yet — click + Add to create one"

TYPE_LABELS = {
    "str": "String",
    "int": "Integer",
    "float": "Float",
    "bool": "Boolean",
}
LABEL_TO_TYPE = {label: t for t, label in TYPE_LABELS.items()}


class VariablesPanel(ctk.CTkFrame):
    """Treeview-backed list of project variables."""

    def __init__(self, parent, project: "Project"):
        super().__init__(
            parent, fg_color=PANEL_BG, corner_radius=0, border_width=0,
        )
        self.project = project
        self._bus_subs: list[tuple[str, Callable]] = []
        self._build_toolbar()
        self._build_tree()
        bus = project.event_bus
        for event_name in (
            "variable_added", "variable_removed", "variable_renamed",
            "variable_type_changed", "variable_default_changed",
            "widget_added", "widget_removed", "property_changed",
        ):
            bus.subscribe(event_name, self._on_changed)
            self._bus_subs.append((event_name, self._on_changed))
        self.after(0, self._refresh)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        bar = tk.Frame(self, bg=TOOLBAR_BG, height=34, highlightthickness=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        self._add_btn = ctk.CTkButton(
            bar, text="+ Add", width=70, height=24,
            corner_radius=3, font=("Segoe UI", 11),
            fg_color="#0e639c", hover_color="#1177bb",
            command=self._on_add,
        )
        self._add_btn.pack(side="left", padx=(8, 4), pady=5)

        self._edit_btn = ctk.CTkButton(
            bar, text="Edit", width=60, height=24,
            corner_radius=3, font=("Segoe UI", 11),
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_edit,
        )
        self._edit_btn.pack(side="left", padx=(0, 4), pady=5)

        self._dup_btn = ctk.CTkButton(
            bar, text="Duplicate", width=78, height=24,
            corner_radius=3, font=("Segoe UI", 11),
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_duplicate,
        )
        self._dup_btn.pack(side="left", padx=(0, 4), pady=5)

        self._del_btn = ctk.CTkButton(
            bar, text="Delete", width=64, height=24,
            corner_radius=3, font=("Segoe UI", 11),
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_delete,
        )
        self._del_btn.pack(side="left", padx=(0, 4), pady=5)

    def _build_tree(self) -> None:
        wrap = tk.Frame(self, bg=BG, highlightthickness=0)
        wrap.pack(fill="both", expand=True)

        style = ttk.Style(self)
        style_name = "Variables.Treeview"
        style.configure(
            style_name,
            background=TREE_BG,
            fieldbackground=TREE_BG,
            foreground=TREE_FG,
            rowheight=TREE_ROW_HEIGHT,
            borderwidth=0,
            font=("Segoe UI", TREE_FONT_SIZE),
        )
        style.map(
            style_name,
            background=[("selected", TREE_SELECTED_BG)],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            f"{style_name}.Heading",
            background=TREE_HEADING_BG,
            foreground=TREE_HEADING_FG,
            font=("Segoe UI", TREE_FONT_SIZE, "bold"),
            relief="flat",
        )

        self.tree = ttk.Treeview(
            wrap,
            columns=("type", "default", "uses"),
            show="headings",
            style=style_name,
            selectmode="browse",
        )
        self.tree.heading("type", text="Name / Type")
        self.tree.heading("default", text="Default")
        self.tree.heading("uses", text="Used by")
        self.tree.column("type", width=180, anchor="w")
        self.tree.column("default", width=110, anchor="w")
        self.tree.column("uses", width=80, anchor="center")
        self.tree.tag_configure("empty", foreground=EMPTY_FG)
        self.tree.bind("<Double-Button-1>", self._on_double_click)

        vsb = ctk.CTkScrollbar(
            wrap, orientation="vertical",
            command=self.tree.yview,
            width=10, corner_radius=4,
            fg_color="transparent",
            button_color="#3a3a3a",
            button_hover_color="#4a4a4a",
        )
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    def _on_changed(self, *_args, **_kwargs) -> None:
        self._refresh()

    def _refresh(self) -> None:
        for iid in self.tree.get_children(""):
            self.tree.delete(iid)
        variables = self.project.variables or []
        if not variables:
            self.tree.insert(
                "", "end", iid="empty",
                values=(EMPTY_TEXT, "", ""),
                tags=("empty",),
            )
            self._set_buttons_enabled(False)
            return
        for v in variables:
            label = f"{v.name}  ({TYPE_LABELS.get(v.type, v.type)})"
            uses = sum(1 for _ in self.project.iter_bindings_for(v.id))
            self.tree.insert(
                "", "end", iid=v.id,
                values=(label, v.default, str(uses)),
            )
        self._set_buttons_enabled(True)

    def _set_buttons_enabled(self, has_any: bool) -> None:
        state = "normal" if has_any else "disabled"
        for btn in (self._edit_btn, self._dup_btn, self._del_btn):
            try:
                btn.configure(state=state)
            except tk.TclError:
                pass

    def _selected_var_id(self) -> str | None:
        sel = self.tree.selection()
        if not sel or sel[0] == "empty":
            return None
        return sel[0]

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_add(self) -> None:
        dialog = VariableEditDialog(
            self.winfo_toplevel(),
            title="Add variable",
            initial_name="",
            initial_type="str",
            initial_default="",
            existing_names={v.name for v in self.project.variables},
        )
        dialog.wait_window()
        if dialog.result is None:
            return
        name, var_type, default = dialog.result
        # Apply through Project so dedupe + coercion happen first;
        # then push the command using the realised entry's snapshot.
        entry = self.project.add_variable(name, var_type, default)
        self.project.history.push(
            AddVariableCommand(
                entry.to_dict(), len(self.project.variables) - 1,
            ),
        )
        try:
            self.tree.selection_set(entry.id)
            self.tree.see(entry.id)
        except tk.TclError:
            pass

    def _on_edit(self) -> None:
        var_id = self._selected_var_id()
        if var_id is None:
            return
        entry = self.project.get_variable(var_id)
        if entry is None:
            return
        existing = {
            v.name for v in self.project.variables if v.id != var_id
        }
        dialog = VariableEditDialog(
            self.winfo_toplevel(),
            title=f"Edit variable: {entry.name}",
            initial_name=entry.name,
            initial_type=entry.type,
            initial_default=entry.default,
            existing_names=existing,
        )
        dialog.wait_window()
        if dialog.result is None:
            return
        new_name, new_type, new_default = dialog.result
        old_name, old_type, old_default = (
            entry.name, entry.type, entry.default,
        )
        # Push individual commands per field that changed so undo /
        # redo each field separately. Order: type first (because it
        # rewrites default), then default, then rename.
        if new_type != old_type:
            self.project.change_variable_type(var_id, new_type)
            self.project.change_variable_default(var_id, new_default)
            self.project.history.push(
                ChangeVariableTypeCommand(
                    var_id, old_type, new_type,
                    old_default, new_default,
                ),
            )
        elif new_default != old_default:
            self.project.change_variable_default(var_id, new_default)
            self.project.history.push(
                ChangeVariableDefaultCommand(
                    var_id, old_default, new_default,
                ),
            )
        if new_name != old_name:
            self.project.rename_variable(var_id, new_name)
            self.project.history.push(
                RenameVariableCommand(var_id, old_name, new_name),
            )

    def _on_duplicate(self) -> None:
        var_id = self._selected_var_id()
        if var_id is None:
            return
        entry = self.project.get_variable(var_id)
        if entry is None:
            return
        new_entry = self.project.add_variable(
            f"{entry.name}_copy", entry.type, entry.default,
        )
        self.project.history.push(
            AddVariableCommand(
                new_entry.to_dict(), len(self.project.variables) - 1,
            ),
        )
        try:
            self.tree.selection_set(new_entry.id)
            self.tree.see(new_entry.id)
        except tk.TclError:
            pass

    def _on_delete(self) -> None:
        var_id = self._selected_var_id()
        if var_id is None:
            return
        entry = self.project.get_variable(var_id)
        if entry is None:
            return
        binding_count = sum(
            1 for _ in self.project.iter_bindings_for(var_id)
        )
        msg = (
            f"Delete variable '{entry.name}'?"
            if binding_count == 0
            else (
                f"Delete variable '{entry.name}'?\n\n"
                f"This will unbind it from {binding_count} widget"
                f"{'s' if binding_count != 1 else ''}.\n"
                "(Undo restores everything.)"
            )
        )
        if not messagebox.askokcancel(
            "Delete variable", msg, parent=self.winfo_toplevel(),
        ):
            return
        # Snapshot bindings BEFORE the cascade-unbind so undo can
        # rewrite the same var: tokens back into the right slots.
        bindings = [
            (n.id, pn, n.properties.get(pn))
            for n, pn in self.project.iter_bindings_for(var_id)
        ]
        index = self.project.variables.index(entry)
        entry_dict = entry.to_dict()
        self.project.remove_variable(var_id)
        self.project.history.push(
            DeleteVariableCommand(entry_dict, index, bindings),
        )

    def _on_double_click(self, _event) -> None:
        if self._selected_var_id() is None:
            return
        self._on_edit()

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------
    def destroy(self) -> None:
        self._unsubscribe_bus()
        super().destroy()

    def _unsubscribe_bus(self) -> None:
        try:
            bus = self.project.event_bus
            for event_name, handler in self._bus_subs:
                bus.unsubscribe(event_name, handler)
        except Exception:
            pass
        self._bus_subs = []


class VariableEditDialog(ctk.CTkToplevel):
    """Modal Add / Edit dialog. Result is ``(name, type, default)`` on
    OK, ``None`` on cancel.
    """

    def __init__(
        self, parent, title: str,
        initial_name: str, initial_type: str, initial_default: str,
        existing_names: set[str],
    ):
        super().__init__(parent)
        self.title(title)
        self.configure(fg_color=BG)
        self.geometry(f"{DIALOG_W}x{DIALOG_H}")
        self.minsize(360, 280)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result: tuple[str, str, str] | None = None
        self._existing_names = existing_names

        self._name_var = tk.StringVar(value=initial_name)
        self._type_var = tk.StringVar(
            value=TYPE_LABELS.get(initial_type, "String"),
        )
        self._default_var = tk.StringVar(value=initial_default)
        self._error_var = tk.StringVar(value="")

        self._build()

        self.bind("<Return>", lambda _e: self._on_ok())
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.after(50, self._center_on_parent)
        self.after(80, lambda: self._name_entry.focus_set())

    def _build(self) -> None:
        panel = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=6)
        panel.pack(padx=18, pady=(18, 10), fill="both", expand=True)

        ctk.CTkLabel(
            panel, text="Variable",
            font=("Segoe UI", 11, "bold"),
            text_color="#888888", anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 6))

        self._add_field(panel, "Name", self._build_name_row)
        self._add_field(panel, "Type", self._build_type_row)
        self._add_field(panel, "Default", self._build_default_row)

        # Error / hint line — pinned under the Default row so the user
        # sees validation feedback without the dialog reflowing.
        tk.Label(
            panel,
            textvariable=self._error_var,
            bg=PANEL_BG, fg="#e07a7a",
            font=("Segoe UI", 9, "italic"),
            anchor="w",
        ).pack(fill="x", padx=(98, 14), pady=(2, 8))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkButton(
            footer, text="OK", width=110, height=30,
            corner_radius=4, command=self._on_ok,
        ).pack(side="right")
        ctk.CTkButton(
            footer, text="Cancel", width=80, height=30,
            corner_radius=4,
            fg_color="#3c3c3c", hover_color="#4a4a4a",
            command=self._on_cancel,
        ).pack(side="right", padx=(0, 8))

    def _add_field(self, parent, label: str, builder) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(
            row, text=f"{label}:", width=80, anchor="w",
            font=("Segoe UI", 11), text_color="#cccccc",
        ).pack(side="left")
        builder(row)

    def _build_name_row(self, row) -> None:
        self._name_entry = ctk.CTkEntry(
            row, textvariable=self._name_var, height=28,
            corner_radius=3, font=("Segoe UI", 11),
            border_color=BORDER, border_width=1,
        )
        self._name_entry.pack(side="left", fill="x", expand=True)

    def _build_type_row(self, row) -> None:
        ctk.CTkOptionMenu(
            row, values=list(TYPE_LABELS.values()),
            variable=self._type_var,
            width=160, height=28, dynamic_resizing=False,
            corner_radius=3,
            fg_color="#3c3c3c", button_color="#3c3c3c",
            button_hover_color="#4a4a4a",
            text_color="#cccccc",
            dropdown_fg_color="#2d2d30",
            dropdown_hover_color="#094771",
            dropdown_text_color="#cccccc",
        ).pack(side="left")

    def _build_default_row(self, row) -> None:
        self._default_entry = ctk.CTkEntry(
            row, textvariable=self._default_var, height=28,
            corner_radius=3, font=("Segoe UI", 11),
            border_color=BORDER, border_width=1,
        )
        self._default_entry.pack(side="left", fill="x", expand=True)

    def _on_ok(self) -> None:
        raw_name = self._name_var.get().strip()
        if not raw_name:
            self._error_var.set("Name cannot be empty")
            return
        clean_name = sanitize_var_name(raw_name)
        if clean_name in self._existing_names:
            self._error_var.set(
                f"A variable named '{clean_name}' already exists",
            )
            return
        type_label = self._type_var.get()
        var_type = LABEL_TO_TYPE.get(type_label, "str")
        if var_type not in VAR_TYPES:
            var_type = "str"
        default_raw = self._default_var.get()
        default = coerce_default_for_type(default_raw, var_type)
        self.result = (clean_name, var_type, default)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self) -> None:
        try:
            parent = self.master
            parent.update_idletasks()
            self.update_idletasks()
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            x = px + (pw - DIALOG_W) // 2
            y = py + (ph - DIALOG_H) // 2
            self.geometry(f"{DIALOG_W}x{DIALOG_H}+{x}+{y}")
        except tk.TclError:
            pass


class VariablesWindow(ctk.CTkToplevel):
    """Floating window wrapper around ``VariablesPanel``."""

    def __init__(
        self, parent, project: "Project",
        on_close: Callable[[], None] | None = None,
    ):
        super().__init__(parent)
        self.title("Variables")
        self.configure(fg_color=BG)
        self.geometry("440x420")
        self.minsize(320, 240)
        try:
            self.transient(parent)
        except tk.TclError:
            pass

        self._on_close_callback = on_close
        self.panel = VariablesPanel(self, project)
        self.panel.pack(fill="both", expand=True, padx=6, pady=6)
        self._place_relative_to(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _place_relative_to(self, parent) -> None:
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            x = px + pw - 440 - 30
            y = py + 80
            self.geometry(f"440x420+{x}+{y}")
        except tk.TclError:
            pass

    def _on_close(self) -> None:
        if self._on_close_callback is not None:
            try:
                self._on_close_callback()
            except Exception:
                pass
        self.destroy()

    def destroy(self) -> None:
        if hasattr(self, "panel"):
            self.panel._unsubscribe_bus()
        super().destroy()
