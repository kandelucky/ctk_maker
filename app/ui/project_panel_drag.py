"""Tree drag-and-drop sidecar for ``ProjectPanel``.

Wraps the Treeview drag gesture from press through release:

* ``on_tree_press`` snapshots the selection (preserving the prior
  multi-select set even when Tk collapses the visual selection on
  press) and stamps the drag-start state via ``after_idle``.
* ``on_tree_drag`` waits for the cursor to cross the threshold,
  surfaces the floating drag ghost + drop-target highlight, then
  tracks both as the cursor moves.
* ``on_tree_release`` resolves the drop target (folder under
  cursor or assets-root when below the last row), validates it
  (no self-drop, no descendant target, no same-parent no-op), and
  hands off to ``_move_into`` for the per-source ``shutil.move``.

The drag ghost is a small ``overrideredirect`` Toplevel with the
folder/file icon + an "N items" label that follows the cursor
without overriding the system cursor.

State lives on the panel (``_drag_state``, ``_drag_threshold``,
``_drop_target_iid``, ``_drag_ghost``) so the helper is purely
behavioural.
"""
from __future__ import annotations

import shutil
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from app.core.logger import log_error
from app.core.paths import assets_dir
from app.ui.system_fonts import ui_font


class ProjectPanelDragDrop:
    """Tree drag/drop + drag-ghost helper. See module docstring."""

    def __init__(self, panel) -> None:
        self.panel = panel

    def on_tree_press(self, event) -> None:
        """Stamp the start state for a potential drag. Letting Tk's
        own ``Button-1`` handler run first means we get its updated
        selection — Ctrl-click / Shift-click multi-select works
        without us reimplementing the selection rules.

        Empty-area click also clears the selection: ttk.Treeview
        keeps the previous selection alive when the user clicks
        below the last row, which made + Folder land inside the
        previously-selected folder instead of at the assets root.
        """
        panel = self.panel
        iid = panel._tree.identify_row(event.y)
        if not iid:
            panel._drag_state = None
            try:
                panel._tree.selection_set([])
            except tk.TclError:
                pass
            panel.tree.refresh_info_panel()
            return
        # Snapshot the selection BEFORE Tk's default Button-1 handler
        # fires — when the press lands on an already-selected row in a
        # multi-select state, Tk collapses the selection to just that
        # row, which would lose the other items the user wanted to
        # drag together.
        prev_sel = list(panel._tree.selection())
        was_multi_press = iid in prev_sel and len(prev_sel) > 1
        panel.after_idle(
            lambda: self._stamp_drag(
                event, iid,
                preserve_items=prev_sel if was_multi_press else None,
            )
        )

    def _stamp_drag(
        self, event, iid: str,
        preserve_items: list[str] | None = None,
    ) -> None:
        panel = self.panel
        if preserve_items is not None:
            # Pressed on a multi-selected row — keep all the previously
            # selected items as the drag set even though Tk collapsed
            # the visual selection to one. Selection itself will be
            # restored on the actual drag start so a plain click that
            # never moves still collapses to single (expected Tk UX).
            items = preserve_items
        else:
            sel = panel._tree.selection()
            # Only drag if the press landed on a row that's now
            # selected. ``identify_row`` may return iid even if the
            # user just clicked an inert region — guard against
            # dragging "nothing".
            if iid not in sel:
                panel._drag_state = None
                return
            items = list(sel)
        panel._drag_state = {
            "start_y": event.y, "start_x": event.x,
            "items": items, "active": False,
        }

    def on_tree_drag(self, event) -> None:
        panel = self.panel
        state = panel._drag_state
        if not state:
            return
        # Wait until the cursor moves past the threshold before
        # showing the drag indicator — single clicks shouldn't trip
        # drag visual chrome.
        if not state["active"]:
            dx = abs(event.x - state["start_x"])
            dy = abs(event.y - state["start_y"])
            if max(dx, dy) < panel._drag_threshold:
                return
            state["active"] = True
            # Restore the multi-selection visually now that we're
            # genuinely dragging — the press handler intentionally
            # leaves Tk's collapsed selection alone so a plain click
            # without drag still behaves like a normal single-select.
            try:
                panel._tree.selection_set(state["items"])
            except tk.TclError:
                pass
            self._show_drag_ghost(state["items"])
        # Update ghost position so the icon trails the cursor.
        self._move_drag_ghost(event)
        target = self._resolve_drop_target(event.y)
        if target is not None and self._is_valid_drop_target(
            target, state["items"],
        ):
            self._set_drop_highlight(target.get("iid"))
        else:
            self._set_drop_highlight(None)

    def on_tree_release(self, event) -> None:
        panel = self.panel
        state = panel._drag_state
        panel._drag_state = None
        self._hide_drag_ghost()
        self._set_drop_highlight(None)
        if not state or not state.get("active"):
            return
        target = self._resolve_drop_target(event.y)
        if target is None or not self._is_valid_drop_target(
            target, state["items"],
        ):
            return
        target_dir = target["path"]
        sources = [
            panel._iid_meta[i][0] for i in state["items"]
            if i in panel._iid_meta
        ]
        self._move_into(sources, target_dir)

    def _resolve_drop_target(self, y: int) -> dict | None:
        """Return either ``{"iid": <folder_iid>, "path": Path}`` for a
        folder row under the cursor, or ``{"iid": None, "path":
        <assets root>}`` when the cursor is past the last row (treat
        the empty area below the tree as a drop into ``assets/``).
        Returns ``None`` only when the cursor is over a non-folder
        row OR there's no project loaded.
        """
        panel = self.panel
        path = panel.path_provider()
        if not path:
            return None
        iid = panel._tree.identify_row(y)
        if iid:
            meta = panel._iid_meta.get(iid)
            if meta is None:
                return None
            if meta[1] == "folder":
                return {"iid": iid, "path": meta[0]}
            return None
        # Empty area below all rows → drop into assets root.
        return {"iid": None, "path": assets_dir(path)}

    def _is_valid_drop_target(
        self, target: dict, source_iids: list[str],
    ) -> bool:
        """Forbid dropping a folder into itself or a descendant —
        ``shutil.move`` would either error or create an infinite
        loop. Also forbid a no-op drop where the target is already
        the source's parent.
        """
        panel = self.panel
        target_path = target["path"]
        for src_iid in source_iids:
            src_meta = panel._iid_meta.get(src_iid)
            if src_meta is None:
                continue
            src_path = src_meta[0]
            if src_path == target_path:
                return False  # self-drop
            try:
                if target_path.resolve().is_relative_to(
                    src_path.resolve(),
                ):
                    return False  # target is inside the source folder
            except (OSError, ValueError, AttributeError):
                pass
            if src_path.parent == target_path:
                return False  # already in this folder
        return True

    def _set_drop_highlight(self, iid: str | None) -> None:
        panel = self.panel
        prev = panel._drop_target_iid
        if prev and prev != iid:
            try:
                panel._tree.item(prev, tags=())
            except tk.TclError:
                pass
        panel._drop_target_iid = iid
        if iid:
            try:
                panel._tree.item(iid, tags=("drop_target",))
            except tk.TclError:
                pass

    # ------- drag ghost (small floating icon following cursor) -------

    def _show_drag_ghost(self, source_iids: list[str]) -> None:
        """Spawn a tiny overrideredirect Toplevel with a file/folder
        icon — gives drag visual feedback without overriding the
        system cursor.
        """
        panel = self.panel
        from app.ui.icons import load_tk_icon
        # Pick the icon by what's being dragged: folder if any
        # source is a folder, file otherwise.
        kinds = {
            panel._iid_meta.get(i, (None, ""))[1] for i in source_iids
        }
        icon_name = "folder" if "folder" in kinds else "file"
        try:
            icon = load_tk_icon(icon_name, size=16, color="#cccccc")
        except Exception:
            icon = None
        ghost = tk.Toplevel(panel.winfo_toplevel())
        ghost.overrideredirect(True)
        try:
            ghost.attributes("-topmost", True)
            ghost.attributes("-alpha", 0.85)
        except tk.TclError:
            pass
        ghost.configure(bg="#1c1c1c")
        frame = tk.Frame(
            ghost, bg="#1c1c1c", padx=6, pady=3,
            highlightbackground="#3c3c3c", highlightthickness=1,
        )
        frame.pack()
        if icon is not None:
            lbl_icon = tk.Label(
                frame, image=icon, bg="#1c1c1c",
            )
            lbl_icon.image = icon  # GC retain
            lbl_icon.pack(side="left", padx=(0, 4))
        count = len(source_iids)
        text = f"{count} item" if count == 1 else f"{count} items"
        tk.Label(
            frame, text=text, bg="#1c1c1c", fg="#cccccc",
            font=ui_font(9),
        ).pack(side="left")
        ghost.geometry("+0+0")
        panel._drag_ghost = ghost

    def _move_drag_ghost(self, event) -> None:
        panel = self.panel
        ghost = getattr(panel, "_drag_ghost", None)
        if ghost is None:
            return
        try:
            x = panel.winfo_pointerx() + 14
            y = panel.winfo_pointery() + 10
            ghost.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def _hide_drag_ghost(self) -> None:
        panel = self.panel
        ghost = getattr(panel, "_drag_ghost", None)
        if ghost is None:
            return
        try:
            ghost.destroy()
        except tk.TclError:
            pass
        panel._drag_ghost = None

    def _move_into(self, sources: list[Path], target_dir: Path) -> None:
        """Move every ``sources`` file / folder into ``target_dir``.
        Conflicts (file with same name in target) are reported
        per-item; the rest of the move continues so a partial drop
        still does what it can. After all moves finish, mark dirty
        + emit ``font_defaults_changed`` so widget render-paths
        re-resolve any newly-stale references gracefully.
        """
        panel = self.panel
        moved = 0
        for src in sources:
            dst = target_dir / src.name
            if dst.exists():
                messagebox.showwarning(
                    "Already exists",
                    f"'{src.name}' already exists in '{target_dir.name}'."
                    " Skipping.",
                    parent=panel.winfo_toplevel(),
                )
                continue
            try:
                shutil.move(str(src), str(dst))
                moved += 1
            except OSError:
                log_error(f"move {src} → {dst}")
                messagebox.showerror(
                    "Move failed",
                    f"Couldn't move:\n{src}\n→\n{dst}",
                    parent=panel.winfo_toplevel(),
                )
        if moved:
            panel.project.event_bus.publish("dirty_changed", True)
            panel.project.event_bus.publish(
                "font_defaults_changed", panel.project.font_defaults,
            )
        panel.refresh()
