"""Keyboard-action sidecar for ``Workspace``.

Three handlers, all driven by global key bindings wired up in
``WorkspaceControls.bind_keys``:

* **Arrow keys (with Shift fast-step)** — nudge the place-managed
  members of the selection by 1 px (10 with Shift). Drop locked
  ancestors + layout-managed children since their on-screen
  position is owned by the parent layout. Coalesces every nudge
  into one history entry per direction via ``BulkMoveCommand``'s
  ``coalesce_key``.
* **Delete** — single → confirmation modal; multi → block on any
  locked member, then bulk-delete via ``DeleteMultipleCommand``.
* **Escape** — clear selection.

Each handler returns ``"break"`` whenever it acted so the rest of
the binding chain doesn't fight it (e.g. an Entry's own Delete
behaviour when the canvas didn't own the action).
"""
from __future__ import annotations

from tkinter import messagebox, ttk

from app.core.commands import (
    BulkMoveCommand,
    DeleteMultipleCommand,
    DeleteWidgetCommand,
)
from app.widgets.layout_schema import normalise_layout_type
from app.widgets.registry import get_descriptor


class KeyboardActions:
    """Arrow / Delete / Escape handlers. See module docstring."""

    def __init__(self, workspace) -> None:
        self.workspace = workspace

    def on_arrow(self, dx: int, dy: int, fast: bool) -> str | None:
        ws = self.workspace
        if ws._input_focused():
            return None
        # Tree has its own Up/Down navigation — don't fight it by also
        # nudging the selected widget on the canvas.
        if isinstance(ws.focus_get(), ttk.Treeview):
            return None
        ids = set(getattr(ws.project, "selected_ids", set()) or set())
        if not ids and ws.project.selected_id is not None:
            ids = {ws.project.selected_id}
        if not ids:
            return None
        # Match drag's eligibility rules so the gesture is consistent:
        # locked widgets (or any locked ancestor) skip; pack/grid kids
        # skip too, since their on-screen position is parent-owned and
        # any x/y we'd write is dead state.
        eligible: list[tuple[str, int, int]] = []
        for wid in ids:
            if ws._effective_locked(wid):
                continue
            node = ws.project.get_widget(wid)
            if node is None:
                continue
            parent_layout = (
                normalise_layout_type(
                    node.parent.properties.get("layout_type", "place"),
                ) if node.parent is not None else "place"
            )
            if parent_layout != "place":
                continue
            try:
                x = int(node.properties.get("x", 0))
                y = int(node.properties.get("y", 0))
            except (ValueError, TypeError):
                x, y = 0, 0
            eligible.append((wid, x, y))
        if not eligible:
            return "break"
        step = 10 if fast else 1
        moves: list = []
        for wid, x, y in eligible:
            before: dict = {}
            after: dict = {}
            if dx:
                new_x = x + dx * step
                ws.project.update_property(wid, "x", new_x)
                before["x"] = x
                after["x"] = new_x
            if dy:
                new_y = y + dy * step
                ws.project.update_property(wid, "y", new_y)
                before["y"] = y
                after["y"] = new_y
            if before:
                moves.append((wid, before, after))
        if moves:
            ws.project.history.push(
                BulkMoveCommand(moves, coalesce_key="nudge"),
            )
        return "break"

    def on_delete(self, _event=None) -> str | None:
        ws = self.workspace
        if ws._input_focused():
            return None
        selected = set(ws.project.selected_ids)
        if not selected:
            return None
        if len(selected) > 1:
            return self._delete_multi(selected)
        sid = next(iter(selected))
        if ws._effective_locked(sid):
            messagebox.showinfo(
                title="Widget locked",
                message=(
                    "This widget is locked. Unlock it from the Object "
                    "Tree (padlock icon) before deleting."
                ),
                parent=ws.winfo_toplevel(),
            )
            return "break"
        node = ws.project.get_widget(sid)
        if node is None:
            return None
        descriptor = get_descriptor(node.widget_type)
        type_label = descriptor.display_name if descriptor else node.widget_type
        confirmed = messagebox.askyesno(
            title="Delete widget",
            message=f"Delete this {type_label}?",
            icon="warning",
            parent=ws.winfo_toplevel(),
        )
        if not confirmed:
            return "break"
        snapshot = node.to_dict()
        parent_id = node.parent.id if node.parent is not None else None
        siblings = (
            node.parent.children if node.parent is not None
            else ws.project.root_widgets
        )
        try:
            index = siblings.index(node)
        except ValueError:
            index = len(siblings)
        owning_doc = ws.project.find_document_for_widget(sid)
        document_id = owning_doc.id if owning_doc is not None else None
        ws.project.remove_widget(sid)
        ws.project.history.push(
            DeleteWidgetCommand(snapshot, parent_id, index, document_id),
        )
        return "break"

    def _delete_multi(self, selected: set[str]) -> str:
        ws = self.workspace
        # Any locked widget in the set blocks the whole delete so the
        # user doesn't half-succeed and wonder which ones stayed.
        locked_ids = [
            nid for nid in selected if ws._effective_locked(nid)
        ]
        if locked_ids:
            messagebox.showinfo(
                title="Widgets locked",
                message=(
                    f"{len(locked_ids)} of the selected widgets are locked. "
                    "Unlock them from the Object Tree before deleting."
                ),
                parent=ws.winfo_toplevel(),
            )
            return "break"
        count = len(selected)
        confirmed = messagebox.askyesno(
            title="Delete widgets",
            message=f"Delete {count} selected widgets?",
            icon="warning",
            parent=ws.winfo_toplevel(),
        )
        if not confirmed:
            return "break"
        # Walk top-down so per-id parent + sibling index snapshots
        # reflect the pre-removal state; skip descendants whose
        # ancestor is also selected (the parent delete covers them).
        entries: list[tuple[dict, str | None, int, str | None]] = []
        for node in ws.project.iter_all_widgets():
            if node.id not in selected:
                continue
            ancestor = node.parent
            covered = False
            while ancestor is not None:
                if ancestor.id in selected:
                    covered = True
                    break
                ancestor = ancestor.parent
            if covered:
                continue
            parent_id = (
                node.parent.id if node.parent is not None else None
            )
            siblings = (
                node.parent.children if node.parent is not None
                else ws.project.root_widgets
            )
            try:
                index = siblings.index(node)
            except ValueError:
                index = len(siblings)
            owning_doc = ws.project.find_document_for_widget(node.id)
            document_id = owning_doc.id if owning_doc is not None else None
            entries.append((node.to_dict(), parent_id, index, document_id))
        for snapshot, _parent_id, _index, _doc_id in entries:
            ws.project.remove_widget(snapshot["id"])
        if entries:
            ws.project.history.push(DeleteMultipleCommand(entries))
        return "break"

    def on_escape(self, _event=None) -> str | None:
        ws = self.workspace
        if ws.project.selected_id is None:
            return None
        ws.project.select_widget(None)
        return "break"
