import uuid

# Backwards-compat widget type renames. Older ``.ctkproj`` files
# stored the historical type name; on load we silently translate to
# the current one so existing projects don't break after a rename.
# Rename only — kwargs / properties are unchanged across these mappings.
_WIDGET_TYPE_RENAMES = {
    "Shape": "Card",  # 2026-04-27: Shape → Card
}


class WidgetNode:
    def __init__(self, widget_type: str, properties: dict | None = None):
        self.id: str = str(uuid.uuid4())
        self.name: str = ""
        self.widget_type: str = widget_type
        self.properties: dict = dict(properties) if properties else {}
        self.children: list[WidgetNode] = []
        self.parent: WidgetNode | None = None
        # Parent-slot name for container parents whose tk master is a
        # named sub-widget rather than the container itself — currently
        # only CTkTabview (tab name). None for plain parents.
        self.parent_slot: str | None = None
        # Builder-only visibility flag. Hidden nodes still exist in the
        # model, still save/load, and still export — they just skip
        # rendering in the workspace so the editor stays uncluttered.
        self.visible: bool = True
        # Builder-only lock flag. Locked nodes can still be selected
        # (to view their properties) but reject drag / resize /
        # arrow-nudge / delete — protects background containers from
        # accidental edits. Cascades through descendants.
        self.locked: bool = False
        # Builder-only group tag. Widgets sharing a group_id are
        # selected together by a single click and are dragged /
        # deleted as one unit. Cross-parent groups are allowed —
        # group_id is metadata, not hierarchy. Skipped from code
        # export (the generated Python sees only individual widgets).
        self.group_id: str | None = None
        # AI-bridge meta-property. Plain-language description of what
        # this widget should do. Emitted as Python comments above the
        # widget's constructor call in code export so an AI can read
        # the structure + intent and fill in the missing logic. Never
        # reaches CTk constructors.
        self.description: str = ""
        # Phase 2 visual scripting — event handler bindings. Maps an
        # event key (``"command"`` for click-style; ``"bind:<seq>"`` for
        # Tk bind-style) to a method name on the page's behavior class.
        # Empty by default. The behavior file lives at
        # ``<project>/scripts/<page>.py`` and is co-edited by the user.
        self.handlers: dict[str, str] = {}

    def to_dict(self) -> dict:
        # Shallow-copy ``properties`` so callers (project_saver
        # tokenisation, copy/paste snapshot, undo recording) can mutate
        # the returned dict without aliasing back into the live
        # widget. Without this, ``_walk_widget_tokenize`` rewrote
        # ``props["image"]`` to an ``asset:images/...`` token and the
        # canvas's PIL.open then choked on a path it couldn't read.
        result = {
            "id": self.id,
            "name": self.name,
            "widget_type": self.widget_type,
            "properties": dict(self.properties),
            "visible": self.visible,
            "locked": self.locked,
            "children": [c.to_dict() for c in self.children],
        }
        if self.parent_slot is not None:
            result["parent_slot"] = self.parent_slot
        if self.group_id is not None:
            result["group_id"] = self.group_id
        if self.description:
            result["description"] = self.description
        if self.handlers:
            result["handlers"] = dict(self.handlers)
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "WidgetNode":
        widget_type = _WIDGET_TYPE_RENAMES.get(
            data["widget_type"], data["widget_type"],
        )
        node = cls(
            widget_type=widget_type,
            properties=data.get("properties", {}),
        )
        node.id = data["id"]
        node.name = data.get("name", "")
        node.visible = bool(data.get("visible", True))
        node.locked = bool(data.get("locked", False))
        node.parent_slot = data.get("parent_slot")
        node.group_id = data.get("group_id")
        node.description = data.get("description", "")
        raw_handlers = data.get("handlers")
        if isinstance(raw_handlers, dict):
            node.handlers = {
                str(k): str(v) for k, v in raw_handlers.items()
                if isinstance(v, str) and v
            }
        for child_data in data.get("children", []):
            child = cls.from_dict(child_data)
            child.parent = node
            node.children.append(child)
        return node
