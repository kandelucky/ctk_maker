"""Variables inspector — manages shared-state variables.

``VariablesPanel`` is an embeddable ``CTkFrame`` (Treeview + toolbar)
parametrised by scope: a panel either lists ``project.variables``
(``scope="global"``) or one document's ``local_variables``
(``scope="local"`` + ``document_id``). ``VariablesWindow`` is a
floating wrapper that holds one global panel and one rebuildable
local panel switched by tabs. Variables are the foundation of the
visual scripting story (Phase 1): widgets bind to a variable via the
Properties panel, and the runtime keeps every bound widget in sync
via Tkinter's built-in ``textvariable`` / ``variable`` mechanism.

The panel is a read-only mirror of its scope's storage; mutations push
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
from app.ui import style
from app.ui.managed_window import ManagedToplevel
from app.ui.system_fonts import ui_font
from app.core.variables import (
    COLOR_DEFAULT,
    VAR_TYPES,
    VariableEntry,
    coerce_default_for_type,
    is_valid_hex,
    sanitize_var_name,
)
from app.core.logger import log_error

if TYPE_CHECKING:
    from app.core.project import Project

# Color / spacing tokens are sourced from app.ui.style — local aliases
# kept so the rest of this file stays terse.
BG = style.BG
PANEL_BG = style.PANEL_BG
TOOLBAR_BG = style.TOOLBAR_BG
TREE_BG = style.TREE_BG
TREE_FG = style.TREE_FG
TREE_SELECTED_BG = style.TREE_SELECTED_BG
TREE_HEADING_BG = style.TREE_HEADING_BG
TREE_HEADING_FG = style.TREE_HEADING_FG
EMPTY_FG = style.EMPTY_FG
BORDER = style.BORDER
HEADER_BG = style.HEADER_BG
SECONDARY_BG = style.SECONDARY_BG
SECONDARY_HOVER = style.SECONDARY_HOVER
DANGER_HOVER = style.DANGER_HOVER
BUTTON_RADIUS = style.BUTTON_RADIUS

DIALOG_W = 420
DIALOG_H = 360
TREE_ROW_HEIGHT = style.TREE_ROW_HEIGHT
TREE_FONT_SIZE = style.TREE_FONT_SIZE

EMPTY_TEXT_GLOBAL = "No global variables yet — click + Add to create one"
EMPTY_TEXT_LOCAL = "No local variables for this document — click + Add"

TYPE_LABELS = {
    "str": "String",
    "int": "Integer",
    "float": "Float",
    "bool": "Boolean",
    "color": "Color",
}
LABEL_TO_TYPE = {label: t for t, label in TYPE_LABELS.items()}

# Auto-fill values shown in the Add Variable dialog. Letting the user
# hit OK on a brand-new dialog and end up with a sensible
# placeholder cuts the create-flow from "type a name + a default" to
# "click +Add → click OK". Suffix dedup at add_variable time turns
# repeated OKs into ``StringValue``, ``StringValue_2``, …
TYPE_DEFAULT_NAMES = {
    "str": "StringValue",
    "int": "IntValue",
    "float": "FloatValue",
    "bool": "BoolValue",
    "color": "ColorValue",
}
TYPE_DEFAULT_VALUES = {
    "str": "",
    "int": "0",
    "float": "0.0",
    "bool": "False",
    "color": "#6366f1",
}

# Pixel size of the colour swatch rendered in the tree's #0 column
# for ``color``-typed rows. 12×12 fits comfortably inside the 22px
# row height with breathing room top/bottom.
SWATCH_PX = 12


class VariablesPanel(ctk.CTkFrame):
    """Treeview-backed list of variables for one scope.

    ``scope="global"`` mirrors ``project.variables``;
    ``scope="local"`` mirrors a single ``Document.local_variables``
    (``document_id`` picks which one). Other-scope variables are
    invisible to this panel — the visibility rule is enforced here so
    the tree, the count column, and command targets all agree.
    """

    def __init__(
        self, parent, project: "Project",
        scope: str = "global",
        document_id: str | None = None,
    ):
        super().__init__(
            parent, fg_color=PANEL_BG, corner_radius=0, border_width=0,
        )
        self.project = project
        self.scope = scope if scope in ("global", "local") else "global"
        self.document_id = document_id if self.scope == "local" else None
        self._bus_subs: list[tuple[str, Callable]] = []
        # ttk.Treeview cells render text or one image per row (#0 column
        # only), so colour swatches live as cached PhotoImages keyed by
        # their hex string. Cache lifetime == panel lifetime; reset on
        # destroy. Bounded in practice — users rarely declare more than
        # a handful of colour vars per project.
        self._swatch_cache: dict[str, tk.PhotoImage] = {}
        self._build_toolbar()
        self._build_tree()
        bus = project.event_bus
        for event_name in (
            "variable_added", "variable_removed", "variable_renamed",
            "variable_type_changed", "variable_default_changed",
            "widget_added", "widget_removed", "property_changed",
            # Project load / project switch publishes
            # ``active_document_changed`` (3x during load_project).
            # Without this subscription the panel keeps showing the
            # previous project's empty list because variable_* events
            # don't fire when ``project.variables`` is replaced
            # wholesale by the loader.
            "active_document_changed",
        ):
            bus.subscribe(event_name, self._on_changed)
            self._bus_subs.append((event_name, self._on_changed))
        self.after(0, self._refresh)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        bar = style.make_toolbar(self)
        bar.pack(fill="x")

        self._add_btn = style.primary_button(
            bar, "+ Add", command=self._on_add, width=70,
        )
        # Local panels colour the + Add button with a darkened local
        # accent so the Add affordance reads as "local-scoped" without
        # being as bright as the chrome icon's orange.
        if self.scope == "local":
            self._add_btn.configure(fg_color="#8a541a", hover_color="#a0651e")
        style.pack_toolbar_button(self._add_btn, first=True)

        self._edit_btn = style.secondary_button(
            bar, "Edit", command=self._on_edit, width=60,
        )
        style.pack_toolbar_button(self._edit_btn)

        self._dup_btn = style.secondary_button(
            bar, "Duplicate", command=self._on_duplicate, width=78,
        )
        style.pack_toolbar_button(self._dup_btn)

        self._del_btn = style.secondary_button(
            bar, "Delete", command=self._on_delete, width=64,
        )
        style.pack_toolbar_button(self._del_btn)

    def _build_tree(self) -> None:
        wrap = tk.Frame(self, bg=BG, highlightthickness=0)
        wrap.pack(fill="both", expand=True)

        style_name = "Variables.Treeview"
        style.apply_tree_style(self, style_name)

        # ``show="tree headings"`` keeps the #0 column visible so we
        # can hang a small colour swatch off rows whose variable type
        # is ``color``. Width is fixed and narrow — non-colour rows
        # leave the cell blank, which reads as a small left margin.
        self.tree = ttk.Treeview(
            wrap,
            columns=("type", "default", "uses"),
            show="tree headings",
            style=style_name,
            selectmode="browse",
        )
        self.tree.heading("#0", text="")
        self.tree.heading("type", text="Name / Type")
        self.tree.heading("default", text="Default")
        self.tree.heading("uses", text="Used by")
        self.tree.column("#0", width=24, minwidth=24, stretch=False, anchor="center")
        self.tree.column("type", width=180, anchor="w")
        self.tree.column("default", width=110, anchor="w")
        self.tree.column("uses", width=80, anchor="center")
        self.tree.tag_configure("empty", foreground=EMPTY_FG)
        self.tree.bind("<Double-Button-1>", self._on_double_click)

        vsb = style.styled_scrollbar(wrap, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    def _on_changed(self, *_args, **_kwargs) -> None:
        self._refresh()

    def _scope_variables(self) -> list:
        """Return the list of variables this panel owns. Locals
        defensively handle a stale ``document_id`` (the doc was
        deleted between window-open and this refresh) by yielding [].
        """
        if self.scope == "local":
            doc = (
                self.project.get_document(self.document_id)
                if self.document_id else None
            )
            return list(doc.local_variables) if doc is not None else []
        return list(self.project.variables or [])

    def _swatch_for(self, hex_value: str) -> tk.PhotoImage | None:
        """Build (and cache) a flat-fill ``PhotoImage`` for ``hex_value``.
        Returns ``None`` on invalid hex / Tk failure so the caller can
        skip the image kwarg cleanly. The image is owned by the panel —
        Tk would garbage-collect a freshly built PhotoImage between
        the insert call and the next event loop tick otherwise.
        """
        cached = self._swatch_cache.get(hex_value)
        if cached is not None:
            return cached
        try:
            img = tk.PhotoImage(
                master=self, width=SWATCH_PX, height=SWATCH_PX,
            )
            img.put(hex_value, to=(0, 0, SWATCH_PX, SWATCH_PX))
        except tk.TclError:
            return None
        self._swatch_cache[hex_value] = img
        return img

    def _refresh(self) -> None:
        for iid in self.tree.get_children(""):
            self.tree.delete(iid)
        variables = self._scope_variables()
        if not variables:
            self.tree.insert(
                "", "end", iid="empty",
                values=(
                    EMPTY_TEXT_LOCAL if self.scope == "local"
                    else EMPTY_TEXT_GLOBAL,
                    "", "",
                ),
                tags=("empty",),
            )
            self._set_buttons_enabled(False)
            return
        for v in variables:
            label = f"{v.name}  ({TYPE_LABELS.get(v.type, v.type)})"
            uses = sum(1 for _ in self.project.iter_bindings_for(v.id))
            kwargs: dict = {
                "values": (label, v.default, str(uses)),
            }
            if v.type == "color":
                swatch = self._swatch_for(v.default or COLOR_DEFAULT)
                if swatch is not None:
                    kwargs["image"] = swatch
            self.tree.insert("", "end", iid=v.id, **kwargs)
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

    def select_variable(self, var_id: str) -> bool:
        """Select and scroll into view the row for ``var_id``. Returns
        ``True`` on success, ``False`` if the row isn't in this panel
        (different scope) or the tree hasn't populated yet."""
        try:
            if not self.tree.exists(var_id):
                return False
            self.tree.selection_set(var_id)
            self.tree.focus(var_id)
            self.tree.see(var_id)
        except tk.TclError:
            return False
        return True

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_add(self) -> None:
        existing_names = {v.name for v in self._scope_variables()}
        # Pre-fill the Add dialog so a default OK lands a usable
        # variable. Type change inside the dialog re-syncs the
        # auto-fill while leaving any user-typed value alone.
        dialog = VariableEditDialog(
            self.winfo_toplevel(),
            title=(
                "Add local variable" if self.scope == "local"
                else "Add variable"
            ),
            initial_name=TYPE_DEFAULT_NAMES["str"],
            initial_type="str",
            initial_default=TYPE_DEFAULT_VALUES["str"],
            existing_names=existing_names,
        )
        dialog.wait_window()
        if dialog.result is None:
            return
        name, var_type, default = dialog.result
        # Apply through Project so dedupe + coercion happen first;
        # then push the command using the realised entry's snapshot.
        entry = self.project.add_variable(
            name, var_type, default,
            scope=self.scope, document_id=self.document_id,
        )
        target_list = self._scope_variables()
        self.project.history.push(
            AddVariableCommand(
                entry.to_dict(), len(target_list) - 1,
                scope=self.scope, document_id=self.document_id,
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
            v.name for v in self._scope_variables() if v.id != var_id
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
            scope=self.scope, document_id=self.document_id,
        )
        target_list = self._scope_variables()
        self.project.history.push(
            AddVariableCommand(
                new_entry.to_dict(), len(target_list) - 1,
                scope=self.scope, document_id=self.document_id,
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
        bindings: list[tuple[str, str, str]] = [
            (n.id, pn, n.properties[pn])
            for n, pn in self.project.iter_bindings_for(var_id)
        ]
        target_list = self._scope_variables()
        try:
            index = target_list.index(entry)
        except ValueError:
            index = len(target_list)
        entry_dict = entry.to_dict()
        self.project.remove_variable(var_id)
        self.project.history.push(
            DeleteVariableCommand(
                entry_dict, index, bindings,
                scope=self.scope, document_id=self.document_id,
            ),
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


class ReparentVariablesDialog(ManagedToplevel):
    """Cross-doc reparent picker for local-variable handling.

    Shown when the user moves widget(s) into another document and the
    moved subtree binds at least one local variable owned by the
    source doc. Two orthogonal radio choices:

    Q1 — what happens to the variable in the source window:
        ``"keep"``    — variable stays as-is.
        ``"delete"``  — variable removed; cascade-unbinds any external
                        widgets in the source still referencing it.

    Q2 — how the moved widget(s) deal with the variable in the target:
        ``"duplicate"`` — copy variable into the target doc (fresh
                          UUID, suffix dedup; same-name + same-type
                          reuses an existing target var).
        ``"unbind"``    — drop the binding from the moved widget(s);
                          the property reverts to its descriptor default.

    Result is a tuple ``(source_policy, target_policy)`` on OK,
    ``None`` on Cancel (which aborts the whole reparent).
    """

    window_title = "Move widget(s) across windows"
    # Content is bounded — listbox is clamped to 3 visible rows with a
    # scrollbar, so the natural height never exceeds this even for
    # large var sets. Width 460 leaves room for the long radio labels.
    default_size = (460, 380)
    min_size = (440, 0)
    fg_color = BG
    panel_padding = (0, 0)
    modal = True
    window_resizable = (False, False)

    def __init__(
        self, parent,
        source_doc_name: str,
        target_doc_name: str,
        var_entries: list,
        external_usage: int,
    ):
        self.result: tuple[str, str] | None = None
        self._source_name = source_doc_name
        self._target_name = target_doc_name
        self._var_entries = list(var_entries)
        self._external_usage = int(external_usage)
        self._source_var = tk.StringVar(value="keep")
        self._target_var = tk.StringVar(value="duplicate")
        super().__init__(parent)
        self.bind("<Return>", lambda _e: self._on_ok())

    def default_offset(self, parent) -> tuple[int, int]:
        try:
            parent.update_idletasks()
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            w, h = self.default_size
            return (px + (pw - w) // 2, py + (ph - h) // 2)
        except tk.TclError:
            return (100, 100)

    def build_content(self) -> ctk.CTkFrame:
        container = ctk.CTkFrame(self, fg_color="transparent")

        outer = ctk.CTkFrame(container, fg_color=PANEL_BG, corner_radius=6)
        outer.pack(padx=18, pady=(18, 10), fill="both", expand=True)

        ctk.CTkLabel(
            outer,
            text=(
                f"The selection uses {len(self._var_entries)} "
                f"local variable{'s' if len(self._var_entries) != 1 else ''} "
                f"from `{self._source_name}`:"
            ),
            font=ui_font(11),
            text_color="#cccccc", anchor="w", justify="left",
        ).pack(fill="x", padx=14, pady=(12, 6))

        self._build_var_list(outer)

        self._build_source_section(outer)
        self._build_target_section(outer)

        ctk.CTkLabel(
            outer,
            text="Global variables are never affected.",
            font=ui_font(10, "italic"),
            text_color="#7da7d9", anchor="w",
        ).pack(fill="x", padx=14, pady=(8, 12))

        footer = ctk.CTkFrame(container, fg_color="transparent")
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
        return container

    def _build_var_list(self, parent) -> None:
        # Three visible rows max; scrollable beyond. Tk's
        # ``Listbox(height=3)`` doesn't actually clamp the widget to
        # 3 rows when its parent is given extra space — pack/expand
        # rules let it grow vertically. Force the row count by
        # wrapping in a fixed-pixel frame with ``pack_propagate(False)``
        # so even a bigger dialog can't stretch the listbox.
        # 3 rows × ~17px line height + 4px borders ≈ 56px.
        ROW_HEIGHT_PX = 17
        VISIBLE_ROWS = 3
        WRAP_HEIGHT = ROW_HEIGHT_PX * VISIBLE_ROWS + 8
        wrap = tk.Frame(
            parent, bg=PANEL_BG,
            height=WRAP_HEIGHT, highlightthickness=0,
        )
        wrap.pack(fill="x", padx=14, pady=(0, 10))
        wrap.pack_propagate(False)

        listbox = tk.Listbox(
            wrap,
            height=VISIBLE_ROWS,
            bg=TREE_BG, fg=TREE_FG,
            selectbackground=TREE_SELECTED_BG,
            selectforeground="#ffffff",
            font=ui_font(10),
            borderwidth=0, highlightthickness=1,
            highlightbackground=BORDER,
            activestyle="none",
            exportselection=False,
        )
        for entry in self._var_entries:
            listbox.insert(
                "end", f"  •  {entry.name}    ({entry.type})",
            )

        scrollbar = ctk.CTkScrollbar(
            wrap, orientation="vertical",
            command=listbox.yview,
            width=10, corner_radius=4,
            fg_color="transparent",
            button_color="#3a3a3a",
            button_hover_color="#4a4a4a",
        )
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _build_source_section(self, parent) -> None:
        ctk.CTkLabel(
            parent,
            text=f"In the source window — `{self._source_name}`:",
            font=ui_font(11, "bold"),
            text_color="#cccccc", anchor="w",
        ).pack(fill="x", padx=14, pady=(4, 4))
        n = self._external_usage
        keep_label = (
            f"Keep variables  (used by {n} other widget"
            f"{'s' if n != 1 else ''})"
            if n > 0 else "Keep variables"
        )
        ctk.CTkRadioButton(
            parent, text=keep_label,
            variable=self._source_var, value="keep",
            font=ui_font(11),
        ).pack(fill="x", padx=24, pady=(0, 2), anchor="w")
        ctk.CTkRadioButton(
            parent, text="Delete variables",
            variable=self._source_var, value="delete",
            font=ui_font(11),
        ).pack(fill="x", padx=24, pady=(0, 6), anchor="w")

    def _build_target_section(self, parent) -> None:
        ctk.CTkLabel(
            parent,
            text=f"In the target window — `{self._target_name}`:",
            font=ui_font(11, "bold"),
            text_color="#cccccc", anchor="w",
        ).pack(fill="x", padx=14, pady=(4, 4))
        ctk.CTkRadioButton(
            parent,
            text="Duplicate (or reuse existing same-name)",
            variable=self._target_var, value="duplicate",
            font=ui_font(11),
        ).pack(fill="x", padx=24, pady=(0, 2), anchor="w")
        ctk.CTkRadioButton(
            parent, text="Unbind widgets from variables",
            variable=self._target_var, value="unbind",
            font=ui_font(11),
        ).pack(fill="x", padx=24, pady=(0, 6), anchor="w")

    def _on_ok(self) -> None:
        self.result = (
            self._source_var.get(),
            self._target_var.get(),
        )
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()


def confirm_clipboard_paste_policy(
    parent_window, project, target_doc,
) -> tuple[bool, tuple[str, str] | None]:
    """Drive the cross-doc variable dialog for a clipboard paste.

    Returns the same shape the drag controller uses:

    ``(True, None)``         no dialog needed — same-doc paste,
                             empty clipboard, or no local-var
                             bindings cross the boundary. Caller
                             should pass ``var_policy=None`` (or the
                             default) to ``paste_from_clipboard``.
    ``(True, (src, tgt))``   user picked source / target policies;
                             pass them through to
                             ``paste_from_clipboard``.
    ``(False, None)``        user cancelled — caller must abort the
                             whole paste.
    """
    if target_doc is None or not project.clipboard:
        return True, None
    source_id = getattr(project, "_clipboard_source_doc_id", None)
    if source_id is None or source_id == target_doc.id:
        return True, None
    var_entries, external = project.collect_clipboard_local_vars(target_doc)
    if not var_entries:
        return True, None
    source_doc = project.get_document(source_id)
    source_name = source_doc.name if source_doc is not None else ""
    dialog = ReparentVariablesDialog(
        parent_window,
        source_doc_name=source_name,
        target_doc_name=target_doc.name,
        var_entries=var_entries,
        external_usage=external,
    )
    dialog.wait_window()
    if dialog.result is None:
        return False, None
    return True, dialog.result


class VariableEditDialog(ManagedToplevel):
    """Modal Add / Edit dialog. Result is ``(name, type, default)`` on
    OK, ``None`` on cancel.
    """

    default_size = (DIALOG_W, DIALOG_H)
    min_size = (360, 280)
    fg_color = BG
    panel_padding = (0, 0)
    modal = True
    window_resizable = (False, False)

    def __init__(
        self, parent, title: str,
        initial_name: str, initial_type: str, initial_default: str,
        existing_names: set[str],
        allowed_types: tuple[str, ...] | None = None,
    ):
        self.result: tuple[str, str, str] | None = None
        self._existing_names = existing_names
        # When the dialog is opened from a property row's "Create new
        # variable" entry, the property's editor only accepts a
        # restricted set of variable types (e.g. a boolean row accepts
        # bool / int but not str / float). Filtering the Type dropdown
        # here keeps the dialog from offering choices that would fail
        # silently at bind time. ``None`` = no restriction (Variables
        # window add / edit flows).
        self._allowed_types: tuple[str, ...] | None = (
            tuple(t for t in allowed_types if t in TYPE_LABELS)
            if allowed_types else None
        )

        self._name_var = tk.StringVar(value=initial_name)
        self._type_var = tk.StringVar(
            value=TYPE_LABELS.get(initial_type, "String"),
        )
        self._default_var = tk.StringVar(value=initial_default)
        self._error_var = tk.StringVar(value="")

        # Track the most recent auto-filled values so a Type change
        # only swaps Name / Default when the user hasn't customised
        # them. Equality test against ``_last_auto_*`` is the cue.
        self._last_auto_name = TYPE_DEFAULT_NAMES.get(initial_type, "")
        self._last_auto_default = TYPE_DEFAULT_VALUES.get(initial_type, "")
        self._type_var.trace_add("write", self._on_type_changed)

        super().__init__(parent)
        self.title(title)
        self.bind("<Return>", lambda _e: self._on_ok())
        self.after(80, lambda: self._name_entry.focus_set())

    def default_offset(self, parent) -> tuple[int, int]:
        try:
            parent.update_idletasks()
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            w, h = self.default_size
            return (px + (pw - w) // 2, py + (ph - h) // 2)
        except tk.TclError:
            return (100, 100)

    def build_content(self) -> ctk.CTkFrame:
        container = ctk.CTkFrame(self, fg_color="transparent")

        panel = ctk.CTkFrame(
            container, fg_color=PANEL_BG, corner_radius=BUTTON_RADIUS,
        )
        panel.pack(padx=18, pady=(18, 10), fill="both", expand=True)

        style.styled_label(
            panel, "Variable",
            font=ui_font(11, "bold"),
            text_color=EMPTY_FG, anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 6))

        self._add_field(panel, "Name", self._build_name_row)
        self._add_field(panel, "Type", self._build_type_row)
        self._add_field(panel, "Default", self._build_default_row)

        # Error / hint line — pinned under the Default row so the user
        # sees validation feedback without the dialog reflowing.
        tk.Label(
            panel,
            textvariable=self._error_var,
            bg=PANEL_BG, fg=DANGER_HOVER,
            font=ui_font(9, "italic"),
            anchor="w",
        ).pack(fill="x", padx=(98, 14), pady=(2, 8))

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(0, 14))
        style.primary_button(
            footer, "OK", command=self._on_ok, width=110,
        ).pack(side="right")
        style.secondary_button(
            footer, "Cancel", command=self._on_cancel, width=80,
        ).pack(side="right", padx=(0, 8))
        return container

    def _add_field(self, parent, label: str, builder) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=4)
        style.styled_label(
            row, f"{label}:", width=80, anchor="w",
        ).pack(side="left")
        builder(row)

    def _build_name_row(self, row) -> None:
        self._name_entry = style.styled_entry(
            row, textvariable=self._name_var, height=28,
        )
        self._name_entry.pack(side="left", fill="x", expand=True)

    def _build_type_row(self, row) -> None:
        if self._allowed_types is not None:
            type_values = [
                TYPE_LABELS[t] for t in self._allowed_types
            ]
        else:
            type_values = list(TYPE_LABELS.values())
        ctk.CTkOptionMenu(
            row, values=type_values,
            variable=self._type_var,
            width=160, height=28, dynamic_resizing=False,
            corner_radius=BUTTON_RADIUS,
            fg_color=SECONDARY_BG, button_color=SECONDARY_BG,
            button_hover_color=SECONDARY_HOVER,
            text_color=TREE_FG,
            dropdown_fg_color=HEADER_BG,
            dropdown_hover_color=TREE_SELECTED_BG,
            dropdown_text_color=TREE_FG,
        ).pack(side="left")

    def _build_default_row(self, row) -> None:
        # The default editor surface depends on the current type. Both
        # widget sets are built up-front and packed/unpacked by
        # ``_apply_type_to_default_row``; building lazily would mean
        # rebuilding the row on every type swap, which flickers.
        self._default_row = row
        self._default_entry = style.styled_entry(
            row, textvariable=self._default_var, height=28,
        )
        # Color editor: swatch label + Pick… button. The swatch is a
        # plain ``tk.Label`` with a ``bg=hex`` so it tracks the hex
        # value live (no PhotoImage churn per stroke).
        self._color_frame = tk.Frame(row, bg=PANEL_BG, highlightthickness=0)
        self._color_swatch = tk.Label(
            self._color_frame, bg=COLOR_DEFAULT,
            width=4, height=1,
            relief="solid", bd=1, highlightthickness=0,
        )
        self._color_swatch.pack(side="left", padx=(0, 8), pady=2)
        self._color_pick_btn = style.secondary_button(
            self._color_frame, "Pick…",
            command=self._open_color_picker, width=70,
        )
        self._color_pick_btn.configure(height=28)
        self._color_pick_btn.pack(side="left")
        self._color_hex_label = tk.Label(
            self._color_frame,
            textvariable=self._default_var,
            bg=PANEL_BG, fg=TREE_FG,
            font=ui_font(10),
        )
        self._color_hex_label.pack(side="left", padx=(10, 0))
        # Keep the swatch fill in lock-step with the hex string —
        # picker writes the StringVar, swatch reads from the trace.
        self._default_var.trace_add("write", self._sync_color_swatch)
        self._apply_type_to_default_row()

    def _apply_type_to_default_row(self) -> None:
        """Show the entry for str/int/float/bool, the swatch+button
        for color. Called on build and on every type swap.
        """
        var_type = LABEL_TO_TYPE.get(self._type_var.get(), "str")
        if var_type == "color":
            try:
                self._default_entry.pack_forget()
            except tk.TclError:
                pass
            self._color_frame.pack(side="left", fill="x", expand=True)
            self._sync_color_swatch()
        else:
            try:
                self._color_frame.pack_forget()
            except tk.TclError:
                pass
            self._default_entry.pack(side="left", fill="x", expand=True)

    def _sync_color_swatch(self, *_args) -> None:
        """Recolour the swatch label to match the current hex string;
        invalid hex falls through to the safe default so the swatch
        never raises a TclError mid-typing (not user-facing here, but
        defensive — picker writes valid hex; future-proof against
        callers that bypass it).
        """
        hex_value = self._default_var.get() or COLOR_DEFAULT
        if not is_valid_hex(hex_value):
            hex_value = COLOR_DEFAULT
        try:
            self._color_swatch.configure(bg=hex_value)
        except tk.TclError:
            pass

    def _open_color_picker(self) -> None:
        """Launch the shared ``ColorPickerDialog`` seeded with the
        current hex; on confirm, write the chosen hex back into the
        StringVar so the swatch + tree refresh themselves via the
        trace and the existing OK-coercion path.
        """
        try:
            from ctk_color_picker import ColorPickerDialog
        except ImportError:
            return
        initial = self._default_var.get() or COLOR_DEFAULT
        dialog = ColorPickerDialog(self, initial_color=initial)
        dialog.wait_window()
        chosen = getattr(dialog, "result", None)
        if chosen:
            self._default_var.set(chosen)

    def _on_type_changed(self, *_args) -> None:
        """Swap Name / Default to the new type's auto-fill values
        only when the user hasn't customised them. ``_last_auto_*``
        carries the previous auto values; if a field still equals
        them, it's safe to update — anything else is the user's text
        and stays put.
        """
        new_type = LABEL_TO_TYPE.get(self._type_var.get(), "str")
        new_auto_name = TYPE_DEFAULT_NAMES.get(new_type, "")
        new_auto_default = TYPE_DEFAULT_VALUES.get(new_type, "")
        if self._name_var.get() == self._last_auto_name:
            self._name_var.set(new_auto_name)
        if self._default_var.get() == self._last_auto_default:
            self._default_var.set(new_auto_default)
        self._last_auto_name = new_auto_name
        self._last_auto_default = new_auto_default
        self._apply_type_to_default_row()

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


class AddGlobalReferenceDialog(ManagedToplevel):
    """v1.10.8 — Modal for declaring a global ``ref[Window]`` /
    ``ref[Dialog]``. User picks a target document + type, types a
    name. Result attributes (read after ``wait_window``):

    - ``self.target_id`` — Document.id, ``None`` on cancel.
    - ``self.target_type`` — ``"Window"`` or ``"Dialog"``.
    - ``self.name_value`` — Python identifier the slot will use.
    """

    window_title = "Add global reference"
    default_size = (440, 320)
    min_size = (420, 280)
    fg_color = BG
    panel_padding = (0, 0)
    modal = True

    def __init__(self, parent, project, existing_names: set[str]):
        self._project = project
        self._existing_names = set(existing_names)
        self.target_id: str | None = None
        self.target_type: str = "Window"
        self.name_value: str = ""
        self._name_dirty = False
        super().__init__(parent)

    def default_offset(self, parent) -> tuple[int, int]:
        try:
            parent.update_idletasks()
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            w, h = self.default_size
            return (px + (pw - w) // 2, py + (ph - h) // 2)
        except tk.TclError:
            return (100, 100)

    def on_close(self) -> None:
        # X-close / Escape land here. Clear the result so the caller's
        # ``not dlg.name_value`` check treats it as cancel.
        self.target_id = None
        self.name_value = ""

    def build_content(self) -> ctk.CTkFrame:
        container = ctk.CTkFrame(self, fg_color="transparent")

        header = ctk.CTkFrame(container, fg_color=PANEL_BG, corner_radius=0)
        header.pack(fill="x")
        style.styled_label(
            header, "Add global reference",
            font=ui_font(14, "bold"),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 0))
        style.styled_label(
            header,
            text=(
                "Pick a window or dialog from this project. "
                "Behavior code reaches it via ``self.<name>``."
            ),
            text_color=EMPTY_FG,
            font=ui_font(11),
            anchor="w", wraplength=380, justify="left",
        ).pack(fill="x", padx=14, pady=(2, 12))

        body = ctk.CTkFrame(container, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=8)

        # Type radio: Window / Dialog. Drives the target dropdown.
        type_row = ctk.CTkFrame(body, fg_color="transparent")
        type_row.pack(fill="x", pady=(2, 6))
        style.styled_label(
            type_row, "Type:", width=70, anchor="w",
        ).pack(side="left")
        self._type_var = tk.StringVar(value="Window")
        self._type_var.trace_add(
            "write", lambda *_a: self._on_type_changed(),
        )
        for label in ("Window", "Dialog"):
            rb = ctk.CTkRadioButton(
                type_row, text=label, value=label,
                variable=self._type_var,
                radiobutton_height=14, radiobutton_width=14,
                font=ui_font(11),
                text_color=TREE_FG,
            )
            rb.pack(side="left", padx=(4, 12))

        # Target dropdown — filtered by ``is_toplevel`` to match
        # the picked type. ``Window`` → main forms; ``Dialog`` →
        # CTkToplevel-style docs.
        target_row = ctk.CTkFrame(body, fg_color="transparent")
        target_row.pack(fill="x", pady=(6, 6))
        style.styled_label(
            target_row, "Target:", width=70, anchor="w",
        ).pack(side="left")
        self._target_var = tk.StringVar(value="")
        self._target_options: list[tuple[str, str]] = []
        self._target_menu = ctk.CTkOptionMenu(
            target_row, variable=self._target_var,
            values=["—"], width=240,
            corner_radius=BUTTON_RADIUS,
            fg_color=SECONDARY_BG, button_color=SECONDARY_BG,
            button_hover_color=SECONDARY_HOVER,
            text_color=TREE_FG,
            dropdown_fg_color=HEADER_BG,
            dropdown_hover_color=TREE_SELECTED_BG,
            dropdown_text_color=TREE_FG,
            command=lambda _v: self._on_target_changed(),
        )
        self._target_menu.pack(side="left")

        # Name input.
        name_row = ctk.CTkFrame(body, fg_color="transparent")
        name_row.pack(fill="x", pady=(6, 6))
        style.styled_label(
            name_row, "Name:", width=70, anchor="w",
        ).pack(side="left")
        self._name_var = tk.StringVar(value="")
        self._name_var.trace_add(
            "write", lambda *_a: self._on_name_changed(),
        )
        self._name_entry = style.styled_entry(
            name_row, textvariable=self._name_var, width=240,
        )
        self._name_entry.pack(side="left")

        self._error_label = style.styled_label(
            body, "", text_color=DANGER_HOVER,
            font=ui_font(10), anchor="w",
        )
        self._error_label.pack(fill="x", pady=(6, 0))

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(fill="x", padx=14, pady=12)
        style.secondary_button(
            footer, "Cancel", command=self._cancel, width=80,
        ).pack(side="right", padx=(8, 0))
        self._add_btn = style.primary_button(
            footer, "Add", command=self._commit, width=80,
        )
        self._add_btn.configure(state="disabled")
        self._add_btn.pack(side="right")

        self._refresh_target_options()
        return container

    def _refresh_target_options(self) -> None:
        want_toplevel = self._type_var.get() == "Dialog"
        opts: list[tuple[str, str]] = []
        for doc in self._project.documents or []:
            if bool(doc.is_toplevel) == want_toplevel:
                opts.append((doc.id, doc.name or "Untitled"))
        self._target_options = opts
        labels = [name for _id, name in opts] or ["(no matching docs)"]
        self._target_menu.configure(values=labels)
        if opts:
            self._target_var.set(opts[0][1])
            self._on_target_changed()
        else:
            self._target_var.set(labels[0])
            self.target_id = None
            self._validate()

    def _on_type_changed(self) -> None:
        self.target_type = self._type_var.get()
        self._refresh_target_options()

    def _on_target_changed(self) -> None:
        label = self._target_var.get()
        for doc_id, name in self._target_options:
            if name == label:
                self.target_id = doc_id
                if not self._name_dirty:
                    self._name_var_set_silently(
                        self._suggest_name(name),
                    )
                self._validate()
                return
        self.target_id = None
        self._validate()

    def _on_name_changed(self) -> None:
        self._name_dirty = True
        self._validate()

    def _name_var_set_silently(self, value: str) -> None:
        self._name_dirty = False
        self._name_var.set(value)
        self._name_dirty = False

    def _suggest_name(self, target_name: str) -> str:
        from app.core.object_references import (
            is_valid_python_identifier, suggest_ref_name,
        )
        if is_valid_python_identifier(target_name):
            base = target_name
        else:
            base = self._type_var.get().lower()
        return suggest_ref_name(
            base, self._type_var.get(), self._existing_names,
        )

    def _validate(self) -> None:
        from app.core.object_references import is_valid_python_identifier
        if self.target_id is None:
            self._error_label.configure(
                text="Pick a target document.",
            )
            self._add_btn.configure(state="disabled")
            return
        name = self._name_var.get().strip()
        if not name:
            self._error_label.configure(
                text="Name the reference.",
            )
            self._add_btn.configure(state="disabled")
            return
        if not is_valid_python_identifier(name):
            self._error_label.configure(
                text="Use a Python identifier.",
            )
            self._add_btn.configure(state="disabled")
            return
        if name in self._existing_names:
            self._error_label.configure(
                text=f"`{name}` is already in use.",
            )
            self._add_btn.configure(state="disabled")
            return
        self._error_label.configure(text="")
        self._add_btn.configure(state="normal")

    def _commit(self) -> None:
        self.name_value = self._name_var.get().strip()
        self.target_type = self._type_var.get()
        self.destroy()

    def _cancel(self) -> None:
        self.target_id = None
        self.name_value = ""
        self.destroy()


def run_add_global_reference_dialog(
    parent, project, existing_names: set[str],
) -> tuple[str, str, str] | None:
    """Open the Add Global Reference dialog modally. Returns
    ``(name, target_type, target_id)`` on Add or ``None`` on
    cancel / no eligible docs.
    """
    dlg = AddGlobalReferenceDialog(parent, project, existing_names)
    parent.wait_window(dlg)
    if dlg.target_id is None or not dlg.name_value:
        return None
    return (dlg.name_value, dlg.target_type, dlg.target_id)


class ObjectReferencesPanel(ctk.CTkFrame):
    """v1.10.8 — Object References tab. Shows every typed widget /
    document pointer the project owns, sectioned by scope (Global
    Window/Dialog refs at top, Local refs of the active document
    below). Right-click on a row exposes Rename / Delete; new local
    refs are created via the Properties Panel toggle, not from this
    panel.
    """

    def __init__(self, parent, project: "Project"):
        super().__init__(
            parent, fg_color=PANEL_BG, corner_radius=0, border_width=0,
        )
        self.project = project
        self._bus_subs: list[tuple[str, Callable]] = []
        self._build_toolbar()
        self._build_tree()
        bus = project.event_bus
        for ev in (
            "object_reference_added", "object_reference_removed",
            "object_reference_renamed",
            "object_reference_target_changed",
            "active_document_changed",
            "widget_renamed", "widget_removed",
        ):
            bus.subscribe(ev, self._on_changed)
            self._bus_subs.append((ev, self._on_changed))
        self.after(0, self._refresh)

    def _build_toolbar(self) -> None:
        bar = style.make_toolbar(self)
        bar.pack(fill="x")
        # Object References uses a teal accent — its own concept,
        # distinct from Global (blue) / Local (orange) variables.
        self._add_global_btn = style.primary_button(
            bar, "+ Add Window", command=self._on_add_global, width=110,
        )
        self._add_global_btn.configure(
            fg_color="#0e8a7d", hover_color="#149a8c",
        )
        style.pack_toolbar_button(self._add_global_btn, first=True)
        ctk.CTkLabel(
            bar,
            text="Window / Dialog refs only. Toggle locals via widget panel.",
            text_color="#9aa4b2",
            font=ui_font(10),
            anchor="w",
            justify="left",
        ).pack(side="left", padx=(2, 10), pady=8, fill="x", expand=True)

    def _on_add_global(self) -> None:
        """Open the Add Global Reference dialog. Result is a
        ``(name, target_type, target_id)`` tuple; we mutate state
        directly + push the command for undo / redo.
        """
        existing_names = {
            e.name for e in self.project.object_references or []
        }
        active_doc = self.project.active_document
        if active_doc is not None:
            existing_names.update(
                e.name for e in active_doc.local_object_references or []
            )
        result = run_add_global_reference_dialog(
            self.winfo_toplevel(), self.project, existing_names,
        )
        if result is None:
            return
        name, target_type, target_id = result
        from app.core.commands import AddObjectReferenceCommand
        from app.core.object_references import ObjectReferenceEntry
        entry = ObjectReferenceEntry(
            name=name,
            target_type=target_type,
            scope="global",
            target_id=target_id,
        )
        # 1. Mutate state + publish.
        index = len(self.project.object_references)
        self.project.object_references.append(entry)
        self.project.event_bus.publish("object_reference_added", entry)
        # 2. Record the command for undo / redo.
        cmd = AddObjectReferenceCommand(
            entry.to_dict(), index=index,
            scope="global", document_id=None,
        )
        self.project.history.push(cmd)

    def _build_tree(self) -> None:
        wrap = tk.Frame(self, bg=BG, highlightthickness=0)
        wrap.pack(fill="both", expand=True)
        style.apply_tree_style(self, "ObjectRefs.Treeview")
        self.tree = ttk.Treeview(
            wrap,
            columns=("type", "target"),
            show="tree headings",
            style="ObjectRefs.Treeview",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Name")
        self.tree.heading("type", text="Type")
        self.tree.heading("target", text="Target")
        self.tree.column("#0", width=160, anchor="w")
        self.tree.column("type", width=110, anchor="w")
        self.tree.column("target", width=160, anchor="w")
        self.tree.tag_configure("empty", foreground=EMPTY_FG)
        self.tree.tag_configure(
            "section", foreground="#9aa4b2",
            font=ui_font(TREE_FONT_SIZE, "bold"),
        )
        self.tree.bind("<Button-3>", self._on_right_click)
        self.tree.bind("<Double-Button-1>", self._on_double_click)
        vsb = style.styled_scrollbar(wrap, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    def _on_changed(self, *_args, **_kwargs) -> None:
        self._refresh()

    def _refresh(self) -> None:
        for iid in self.tree.get_children(""):
            self.tree.delete(iid)
        globals_list = list(self.project.object_references or [])
        active_doc = self.project.active_document
        local_list = (
            list(active_doc.local_object_references)
            if active_doc is not None else []
        )
        if not globals_list and not local_list:
            self.tree.insert(
                "", "end", iid="empty",
                text="No references yet",
                values=(
                    "",
                    "Toggle from a widget panel to create one",
                ),
                tags=("empty",),
            )
            return
        from app.core.object_references import short_type_label
        if globals_list:
            self.tree.insert(
                "", "end", iid="section:global",
                text="Global  (Window / Dialog)",
                values=("", ""), tags=("section",), open=True,
            )
            for entry in globals_list:
                target = self._resolve_target_label(entry)
                self.tree.insert(
                    "section:global", "end",
                    iid=f"ref:{entry.id}",
                    text=entry.name,
                    values=(short_type_label(entry.target_type), target),
                )
        if local_list:
            label = active_doc.name if active_doc is not None else "Local"
            self.tree.insert(
                "", "end", iid="section:local",
                text=f"Local: {label}",
                values=("", ""), tags=("section",), open=True,
            )
            for entry in local_list:
                target = self._resolve_target_label(entry)
                self.tree.insert(
                    "section:local", "end",
                    iid=f"ref:{entry.id}",
                    text=entry.name,
                    values=(short_type_label(entry.target_type), target),
                )

    def _resolve_target_label(self, entry) -> str:
        if not entry.target_id:
            return "(unbound)"
        if entry.scope == "global":
            doc = self.project.get_document(entry.target_id)
            return doc.name if doc is not None else "(missing)"
        widget = self.project.get_widget(entry.target_id)
        if widget is None:
            return "(missing)"
        return widget.name or widget.widget_type

    def _selected_ref_id(self) -> str | None:
        sel = self.tree.selection()
        if not sel or not sel[0].startswith("ref:"):
            return None
        return sel[0][4:]

    def _find_entry(self, ref_id: str):
        for entry in self.project.object_references or []:
            if entry.id == ref_id:
                return entry, "global", None
        for doc in self.project.documents:
            for entry in doc.local_object_references or []:
                if entry.id == ref_id:
                    return entry, "local", doc.id
        return None, None, None

    def _on_right_click(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if iid and iid.startswith("ref:"):
            self.tree.selection_set(iid)
        ref_id = self._selected_ref_id()
        if ref_id is None:
            return
        menu = tk.Menu(self.tree, tearoff=0)
        menu.add_command(
            label="Rename…",
            command=lambda: self._rename_ref(ref_id),
        )
        menu.add_command(
            label="Delete",
            command=lambda: self._delete_ref(ref_id),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_double_click(self, _event=None) -> None:
        ref_id = self._selected_ref_id()
        if ref_id is None:
            return
        self._rename_ref(ref_id)

    def _rename_ref(self, ref_id: str) -> None:
        entry, scope, doc_id = self._find_entry(ref_id)
        if entry is None:
            return
        from app.core.commands import RenameObjectReferenceCommand
        from app.core.object_references import (
            is_valid_python_identifier,
        )
        existing_names = {
            e.name for e in self.project.object_references or []
            if e.id != ref_id
        }
        if scope == "local" and doc_id is not None:
            doc = self.project.get_document(doc_id)
            if doc is not None:
                existing_names.update(
                    e.name for e in doc.local_object_references or []
                    if e.id != ref_id
                )
        from tkinter import simpledialog
        new_name = simpledialog.askstring(
            "Rename reference",
            f"New name for `{entry.name}`:",
            initialvalue=entry.name,
            parent=self.winfo_toplevel(),
        )
        if not new_name or new_name == entry.name:
            return
        if not is_valid_python_identifier(new_name):
            messagebox.showerror(
                "Invalid name",
                "Use a Python identifier "
                "(letters / digits / _; not a keyword).",
                parent=self.winfo_toplevel(),
            )
            return
        if new_name in existing_names:
            messagebox.showerror(
                "Name in use",
                f"`{new_name}` is already used by another reference.",
                parent=self.winfo_toplevel(),
            )
            return
        # Annotation rename: delete old line, add new one (best
        # effort — model mutation runs even when the file write
        # fails so the in-memory truth keeps moving).
        old_name = entry.name
        self._maybe_rename_annotation(
            entry, scope, doc_id, old_name, new_name,
        )
        # 1. Mutate state + publish — history.push only RECORDS, it
        #    doesn't apply, so the rename has to happen here.
        entry.name = new_name
        self.project.event_bus.publish(
            "object_reference_renamed", entry,
        )
        # 2. Record the command for undo / redo.
        cmd = RenameObjectReferenceCommand(
            ref_id, old_name, new_name,
        )
        self.project.history.push(cmd)

    def _delete_ref(self, ref_id: str) -> None:
        entry, scope, doc_id = self._find_entry(ref_id)
        if entry is None or scope is None:
            return
        from app.core.commands import DeleteObjectReferenceCommand
        if scope == "local" and doc_id is not None:
            doc = self.project.get_document(doc_id)
            if doc is None:
                return
            target_list = doc.local_object_references
        else:
            target_list = self.project.object_references
        idx = next(
            (i for i, e in enumerate(target_list) if e.id == ref_id),
            None,
        )
        if idx is None:
            return
        # 1. Strip annotation (best effort, file may not exist).
        self._maybe_delete_annotation(entry, scope, doc_id)
        # 2. Mutate state + publish.
        target_list.pop(idx)
        self.project.event_bus.publish("object_reference_removed", entry)
        # 3. Record the command for undo / redo.
        cmd = DeleteObjectReferenceCommand(
            entry.to_dict(), index=idx,
            scope=scope, document_id=doc_id,
        )
        self.project.history.push(cmd)

    def _maybe_rename_annotation(
        self, entry, scope, doc_id, old_name, new_name,
    ) -> None:
        if scope != "local" or doc_id is None:
            return
        doc = self.project.get_document(doc_id)
        if doc is None:
            return
        path = getattr(self.project, "path", None)
        if not path:
            return
        try:
            from app.core.script_paths import (
                behavior_class_name, behavior_file_path,
            )
            from app.io.scripts import (
                add_object_reference_annotation,
                delete_object_reference_annotation,
            )
            file_path = behavior_file_path(path, doc)
            if file_path is None or not file_path.exists():
                return
            class_name = behavior_class_name(doc)
            removed = delete_object_reference_annotation(
                file_path, class_name, old_name,
            )
            if not removed:
                log_error(
                    f"rename ref annotation: {old_name!r} not found in "
                    f"{file_path.name} (continuing with add for "
                    f"{new_name!r})",
                )
            add_object_reference_annotation(
                file_path, class_name, new_name, entry.target_type,
            )
        except Exception:
            log_error(
                f"rename ref annotation: {old_name!r} → {new_name!r} "
                f"in doc {doc_id}",
            )

    def _maybe_delete_annotation(self, entry, scope, doc_id) -> None:
        if scope != "local" or doc_id is None:
            return
        doc = self.project.get_document(doc_id)
        if doc is None:
            return
        path = getattr(self.project, "path", None)
        if not path:
            return
        try:
            from app.core.script_paths import (
                behavior_class_name, behavior_file_path,
            )
            from app.io.scripts import (
                delete_object_reference_annotation,
            )
            file_path = behavior_file_path(path, doc)
            if file_path is None or not file_path.exists():
                return
            removed = delete_object_reference_annotation(
                file_path, behavior_class_name(doc), entry.name,
            )
            if not removed:
                log_error(
                    f"delete ref annotation: {entry.name!r} not found "
                    f"in {file_path.name} (orphan or stale annotation)",
                )
        except Exception:
            log_error(
                f"delete ref annotation: {entry.name!r} in doc {doc_id}",
            )

    def _unsubscribe_bus(self) -> None:
        try:
            bus = self.project.event_bus
            for ev, handler in self._bus_subs:
                bus.unsubscribe(ev, handler)
        except Exception:
            pass

    def destroy(self) -> None:
        self._unsubscribe_bus()
        super().destroy()


class VariablesWindow(ManagedToplevel):
    """Floating window wrapper around two ``VariablesPanel`` instances.

    Two tabs at the top — **Global** (blue, page-scoped — shared by
    every window in the active page) and **Local: <doc-name>**
    (orange, per-document). The local panel is rebuilt against the
    active document whenever it changes, so the label and contents
    always match what the workspace is showing.
    """

    window_key = "variables"
    window_title = "Data"
    default_size = (460, 440)
    min_size = (360, 260)
    fg_color = BG
    # Tab strip + panel area drive their own padx/pady inside the
    # wrapper, so suppress ManagedToplevel's outer padding.
    panel_padding = (0, 0)

    def __init__(
        self, parent, project: "Project",
        on_close: Callable[[], None] | None = None,
        initial_scope: str = "global",
        initial_variable_id: str | None = None,
    ):
        from app.ui.icons import (
            VARIABLES_GLOBAL_COLOR, VARIABLES_LOCAL_COLOR,
        )
        self.project = project
        self._global_color = VARIABLES_GLOBAL_COLOR
        self._local_color = VARIABLES_LOCAL_COLOR
        self._active_scope = "global"
        self._local_doc_id: str | None = None
        self._bus_subs: list[tuple[str, Callable]] = []
        self._initial_scope = initial_scope
        self._initial_variable_id = initial_variable_id
        super().__init__(parent)
        self.set_on_close(on_close)

        # Subscribe so a doc switch / rename behind the scenes reflows
        # the Local tab. Stored on the instance so destroy() can clean
        # up — leaving subscribers behind would keep the closed window
        # alive across the project's lifetime.
        self._subscribe(
            "active_document_changed",
            lambda *_a, **_k: self._on_active_doc_changed(),
        )
        # ``widget_renamed`` doubles as the doc-rename signal because
        # renaming the virtual Window node mutates ``Document.name``.
        # Filter for that case so unrelated widget renames are no-ops.
        self._subscribe(
            "widget_renamed", self._on_widget_renamed,
        )

        self._show_scope(self._initial_scope)
        if self._initial_variable_id is not None:
            # Panels populate via after(0, _refresh) so the tree row
            # we want to select doesn't exist yet — defer onto the
            # same queue (FIFO → refresh first, then our select).
            self.after(
                0,
                lambda v=self._initial_variable_id: self._select_variable(v),
            )

    def build_content(self) -> tk.Frame:
        wrapper = tk.Frame(self, bg=BG, highlightthickness=0)
        self._build_tab_strip(wrapper)
        self._panel_area = tk.Frame(wrapper, bg=BG, highlightthickness=0)
        self._panel_area.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # Global panel — never rebuilt; always points at project.variables.
        self._global_panel = VariablesPanel(
            self._panel_area, self.project, scope="global",
        )
        # Local panel — built against the currently active document.
        # Rebuilt on active_document_changed so the title and the
        # backing list track the workspace's current selection.
        self._local_panel: VariablesPanel | None = None
        self._build_local_panel()
        # v1.10.8 — Object References panel (third tab). Combined view
        # over globals + active-doc locals; refreshes on its own bus
        # subscriptions, no rebuild on doc change.
        self._objrefs_panel = ObjectReferencesPanel(
            self._panel_area, self.project,
        )
        return wrapper

    def default_offset(self, parent) -> tuple[int, int]:
        try:
            parent.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            w, h = self.default_size
            return (px + (pw - w) // 2, py + (ph - h) // 2)
        except tk.TclError:
            return (100, 100)

    def _select_variable(self, var_id: str) -> None:
        """Select ``var_id`` in whichever panel currently owns it.
        Idempotent and tolerant of an unknown / orphaned id — leaves
        the tree's existing selection alone if the row is missing."""
        for panel in (self._global_panel, self._local_panel):
            if panel is None:
                continue
            if panel.select_variable(var_id):
                return

    def _subscribe(self, event_name: str, handler: Callable) -> None:
        self.project.event_bus.subscribe(event_name, handler)
        self._bus_subs.append((event_name, handler))

    def _build_local_panel(self) -> None:
        doc = self.project.active_document
        self._local_doc_id = doc.id if doc is not None else None
        self._local_panel = VariablesPanel(
            self._panel_area, self.project,
            scope="local", document_id=self._local_doc_id,
        )

    def _on_active_doc_changed(self) -> None:
        """Active document switched — drop the old Local panel and
        build a fresh one against the new document. Keeps the panel's
        backing list and the displayed tab label in sync."""
        was_visible = self._active_scope == "local"
        if self._local_panel is not None:
            try:
                self._local_panel.pack_forget()
            except tk.TclError:
                pass
            try:
                self._local_panel.destroy()
            except tk.TclError:
                pass
        self._build_local_panel()
        self._refresh_local_tab_label()
        if was_visible and self._local_panel is not None:
            self._local_panel.pack(fill="both", expand=True)

    def _refresh_local_tab_label(self) -> None:
        try:
            self._local_tab.configure(text=self._local_tab_label())
        except (tk.TclError, AttributeError):
            pass

    def _on_widget_renamed(self, widget_id, *_args, **_kwargs) -> None:
        # The virtual Window node renames the active Document, so a
        # WINDOW_ID rename is the only case relevant to our tab label.
        from app.core.project import WINDOW_ID
        if widget_id == WINDOW_ID:
            self._refresh_local_tab_label()

    # ------------------------------------------------------------------
    # Tab strip
    # ------------------------------------------------------------------
    def _build_tab_strip(self, parent) -> None:
        strip = tk.Frame(parent, bg=BG, highlightthickness=0)
        strip.pack(fill="x", padx=6, pady=(6, 0))
        # Three equal columns so Global / Local / Object References
        # tabs share the window's full width — v1.10.8 added the
        # third tab.
        for col in (0, 1, 2):
            strip.grid_columnconfigure(col, weight=1, uniform="tab")
        self._global_tab = self._make_tab_button(
            strip, "Global", self._global_color,
            command=lambda: self._show_scope("global"),
        )
        self._global_tab.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        self._local_tab = self._make_tab_button(
            strip, self._local_tab_label(), self._local_color,
            command=lambda: self._show_scope("local"),
        )
        self._local_tab.grid(row=0, column=1, sticky="ew", padx=(2, 2))
        # Object References tab — neutral teal so it reads as its
        # own concept rather than a third variable scope.
        self._objrefs_color = "#0e8a7d"
        self._objrefs_tab = self._make_tab_button(
            strip, "Object References", self._objrefs_color,
            command=lambda: self._show_scope("objrefs"),
        )
        self._objrefs_tab.grid(row=0, column=2, sticky="ew", padx=(2, 0))

    def _make_tab_button(
        self, parent, text: str, accent: str, command,
    ) -> ctk.CTkButton:
        # Solid background instead of ``fg_color="transparent"`` —
        # CTk 5.2 occasionally resolves transparent fg_color to an
        # empty bg string in `_on_enter`, raising
        # ``TclError: unknown color name ""``. Matching the strip's
        # bg gives the same visual result without the hover risk.
        return ctk.CTkButton(
            parent, text=text, width=10, height=28,
            corner_radius=4, font=ui_font(11, "bold"),
            fg_color=BG, hover_color="#2a2a2a",
            text_color="#888888",
            border_width=0,
            command=command,
        )

    def _local_tab_label(self) -> str:
        doc = self.project.active_document
        name = (doc.name if doc is not None else "Local") or "Local"
        if len(name) > 18:
            name = name[:17] + "…"
        return f"Local: {name}"

    def _show_scope(self, scope: str) -> None:
        if scope not in ("global", "local", "objrefs"):
            scope = "global"
        self._active_scope = scope
        # Hide every panel first; the active branch packs its own.
        try:
            self._global_panel.pack_forget()
        except tk.TclError:
            pass
        if self._local_panel is not None:
            try:
                self._local_panel.pack_forget()
            except tk.TclError:
                pass
        try:
            self._objrefs_panel.pack_forget()
        except tk.TclError:
            pass
        if scope == "global":
            self._global_panel.pack(fill="both", expand=True)
            self.title("Data — Global Variables")
        elif scope == "local":
            if self._local_panel is not None:
                self._local_panel.pack(fill="both", expand=True)
            self.title(
                f"Data — {self._local_tab_label()}",
            )
        else:  # objrefs
            self._objrefs_panel.pack(fill="both", expand=True)
            self.title("Data — Object References")
        self._set_tab_state(
            self._global_tab, self._global_color, scope == "global",
        )
        self._set_tab_state(
            self._local_tab, self._local_color, scope == "local",
        )
        self._set_tab_state(
            self._objrefs_tab, self._objrefs_color, scope == "objrefs",
        )

    def _set_tab_state(
        self, btn: ctk.CTkButton, accent: str, active: bool,
    ) -> None:
        if active:
            btn.configure(
                text_color="#ffffff",
                fg_color=accent,
                hover_color=accent,
            )
        else:
            btn.configure(
                text_color="#888888",
                fg_color=BG,
                hover_color="#2a2a2a",
            )

    # ------------------------------------------------------------------
    # External hooks
    # ------------------------------------------------------------------
    def show_scope(
        self, scope: str, variable_id: str | None = None,
    ) -> None:
        """Public switcher used by the chrome / toolbar entry points.
        ``variable_id`` (optional) pre-selects the matching row in the
        scope's tree — used by panel double-click to land the user on
        the bound variable."""
        # Active doc may have changed since this window was last
        # opened — rebuild the local panel so we don't show another
        # doc's variables under the wrong tab title.
        doc = self.project.active_document
        new_doc_id = doc.id if doc is not None else None
        if new_doc_id != self._local_doc_id:
            self._on_active_doc_changed()
        self._refresh_local_tab_label()
        self._show_scope(scope)
        if variable_id is not None:
            self._select_variable(variable_id)
        try:
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass

    def destroy(self) -> None:
        # Drop the window-level bus subscriptions we registered in
        # __init__ so nothing keeps a reference to this dead Toplevel.
        try:
            bus = self.project.event_bus
            for event_name, handler in getattr(self, "_bus_subs", []):
                bus.unsubscribe(event_name, handler)
        except Exception:
            pass
        # Embedded panels do their own teardown in CTkFrame.destroy(),
        # but we call _unsubscribe_bus() defensively in case the panel
        # is still un-packed (and so destroy hasn't propagated yet).
        for panel in (
            getattr(self, "_global_panel", None),
            getattr(self, "_local_panel", None),
            getattr(self, "_objrefs_panel", None),
        ):
            if panel is not None:
                try:
                    panel._unsubscribe_bus()
                except Exception:
                    pass
        super().destroy()
