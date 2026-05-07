"""Boolean editor: single-click toggles the ☑ / ☐ cell."""

from __future__ import annotations

from .base import Editor


class BooleanEditor(Editor):
    def on_single_click(self, panel, pname, prop) -> bool:
        node = panel.project.get_widget(panel.current_id)
        if node is None:
            return True
        new_val = not bool(node.properties.get(pname))
        panel._commit_prop(pname, new_val)
        return True
