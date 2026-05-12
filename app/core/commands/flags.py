"""Builder-only flag toggles — visibility / lock / group membership."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.commands.base import Command

if TYPE_CHECKING:
    from app.core.project import Project


class ToggleFlagCommand(Command):
    """Visibility or lock toggle — both flags live on WidgetNode
    outside the normal ``properties`` dict, so they need their own
    setter routing rather than ChangePropertyCommand.
    """

    def __init__(
        self,
        widget_id: str,
        flag: str,
        before: bool,
        after: bool,
    ):
        self.widget_id = widget_id
        self.flag = flag
        self.before = before
        self.after = after
        self.description = {
            "visible": (
                "Hide widget" if not after else "Show widget"
            ),
            "locked": (
                "Lock widget" if after else "Unlock widget"
            ),
        }.get(flag, f"Toggle {flag}")

    def _apply(self, project: "Project", value: bool) -> None:
        if self.flag == "visible":
            project.set_visibility(self.widget_id, value)
        elif self.flag == "locked":
            project.set_locked(self.widget_id, value)

    def undo(self, project: "Project") -> None:
        self._apply(project, self.before)

    def redo(self, project: "Project") -> None:
        self._apply(project, self.after)


class BulkToggleFlagCommand(Command):
    """Batch visibility / lock toggle for a set of widgets — used by
    Object Tree's virtual Group row so toggling the group is one undo
    step rather than N. Each entry remembers its own before-state so
    undo restores the exact mix even if some members were already ON.
    """

    def __init__(
        self,
        flag: str,
        entries: list[tuple[str, bool, bool]],
        label: str | None = None,
    ):
        self.flag = flag
        self._entries = list(entries)
        if label is None:
            verb = {
                ("visible", True): "Show",
                ("visible", False): "Hide",
                ("locked", True): "Lock",
                ("locked", False): "Unlock",
            }
            after_state = entries[0][2] if entries else True
            label = verb.get(
                (flag, after_state), f"Toggle {flag}",
            )
        self.description = f"{label} group ({len(entries)})"

    def _apply_one(
        self, project: "Project", widget_id: str, value: bool,
    ) -> None:
        if self.flag == "visible":
            project.set_visibility(widget_id, value)
        elif self.flag == "locked":
            project.set_locked(widget_id, value)

    def undo(self, project: "Project") -> None:
        for widget_id, before, _after in self._entries:
            self._apply_one(project, widget_id, before)

    def redo(self, project: "Project") -> None:
        for widget_id, _before, after in self._entries:
            self._apply_one(project, widget_id, after)


class SetGroupCommand(Command):
    """Group / ungroup tag mutation — records before/after group_id
    per widget so undo restores prior group memberships exactly,
    even for widgets that were already in a (possibly different)
    group before the change.
    """

    def __init__(
        self,
        before: dict,
        after: dict,
        description: str = "Group widgets",
    ):
        self.before = dict(before)
        self.after = dict(after)
        self.description = description

    def _apply(self, project: "Project", values: dict) -> None:
        for widget_id, group_id in values.items():
            project.set_group_id(widget_id, group_id)

    def undo(self, project: "Project") -> None:
        self._apply(project, self.before)

    def redo(self, project: "Project") -> None:
        self._apply(project, self.after)
