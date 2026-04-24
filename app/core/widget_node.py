import uuid


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

    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "name": self.name,
            "widget_type": self.widget_type,
            "properties": self.properties,
            "visible": self.visible,
            "locked": self.locked,
            "children": [c.to_dict() for c in self.children],
        }
        if self.parent_slot is not None:
            result["parent_slot"] = self.parent_slot
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "WidgetNode":
        node = cls(
            widget_type=data["widget_type"],
            properties=data.get("properties", {}),
        )
        node.id = data["id"]
        node.name = data.get("name", "")
        node.visible = bool(data.get("visible", True))
        node.locked = bool(data.get("locked", False))
        node.parent_slot = data.get("parent_slot")
        for child_data in data.get("children", []):
            child = cls.from_dict(child_data)
            child.parent = node
            node.children.append(child)
        return node
