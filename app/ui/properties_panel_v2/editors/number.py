"""Number editor: inline tk.Entry overlay on double-click."""

from __future__ import annotations

from .base import Editor


class NumberEditor(Editor):
    def on_double_click(self, panel, pname, prop, event) -> bool:
        iid = panel._prop_iids.get(pname)
        if iid is None:
            return False
        bbox = panel.tree.bbox(iid, "#1")
        if not bbox:
            return False
        panel._commit_active_editor()
        panel._open_entry_overlay(iid, pname, prop, bbox)
        return True
