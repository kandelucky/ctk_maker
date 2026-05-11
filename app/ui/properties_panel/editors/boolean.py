"""Boolean editor: single-click toggles the ☑ / ☐ cell."""

from __future__ import annotations

from app.core.variables import is_var_token

from .base import Editor


class BooleanEditor(Editor):
    def on_single_click(self, panel, pname, prop) -> bool:
        node = panel.project.get_widget(panel.current_id)
        if node is None:
            return True
        current = node.properties.get(pname)
        # Var-bound row: don't clobber the binding on the first half of a
        # double-click. Double-click is intercepted in panel_commit and
        # opens the Variables window.
        if is_var_token(current):
            return True
        panel._commit_prop(pname, not bool(current))
        return True
