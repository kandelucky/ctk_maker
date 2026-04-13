from app.core.event_bus import EventBus
from app.core.widget_node import WidgetNode


DEFAULT_DOCUMENT_WIDTH = 800
DEFAULT_DOCUMENT_HEIGHT = 600


class Project:
    def __init__(self):
        self.event_bus = EventBus()
        self.root_widgets: list[WidgetNode] = []
        self.selected_id: str | None = None
        self.document_width: int = DEFAULT_DOCUMENT_WIDTH
        self.document_height: int = DEFAULT_DOCUMENT_HEIGHT
        self.name: str = "Untitled"

    def resize_document(self, width: int, height: int) -> None:
        width = max(100, int(width))
        height = max(100, int(height))
        if width == self.document_width and height == self.document_height:
            return
        self.document_width = width
        self.document_height = height
        self.event_bus.publish("document_resized", width, height)

    def add_widget(self, node: WidgetNode) -> None:
        self.root_widgets.append(node)
        self.event_bus.publish("widget_added", node)

    def clear(self) -> None:
        for node in list(self.root_widgets):
            self.remove_widget(node.id)

    def remove_widget(self, widget_id: str) -> None:
        node = self.get_widget(widget_id)
        if node is None:
            return
        self.root_widgets.remove(node)
        if self.selected_id == widget_id:
            self.select_widget(None)
        self.event_bus.publish("widget_removed", widget_id)

    def get_widget(self, widget_id: str) -> WidgetNode | None:
        for node in self.root_widgets:
            if node.id == widget_id:
                return node
        return None

    def select_widget(self, widget_id: str | None) -> None:
        if widget_id == self.selected_id:
            return
        self.selected_id = widget_id
        self.event_bus.publish("selection_changed", widget_id)

    def update_property(self, widget_id: str, prop_name: str, value) -> None:
        node = self.get_widget(widget_id)
        if node is None:
            return
        node.properties[prop_name] = value
        self.event_bus.publish("property_changed", widget_id, prop_name, value)

    def duplicate_widget(self, widget_id: str) -> str | None:
        node = self.get_widget(widget_id)
        if node is None:
            return None
        new_props = dict(node.properties)
        try:
            new_props["x"] = int(new_props.get("x", 0)) + 20
            new_props["y"] = int(new_props.get("y", 0)) + 20
        except (ValueError, TypeError):
            pass
        clone = WidgetNode(
            widget_type=node.widget_type,
            properties=new_props,
        )
        self.root_widgets.append(clone)
        self.event_bus.publish("widget_added", clone)
        self.select_widget(clone.id)
        return clone.id

    def bring_to_front(self, widget_id: str) -> None:
        node = self.get_widget(widget_id)
        if node is None or self.root_widgets[-1] is node:
            return
        self.root_widgets.remove(node)
        self.root_widgets.append(node)
        self.event_bus.publish("widget_z_changed", widget_id, "front")

    def send_to_back(self, widget_id: str) -> None:
        node = self.get_widget(widget_id)
        if node is None or self.root_widgets[0] is node:
            return
        self.root_widgets.remove(node)
        self.root_widgets.insert(0, node)
        self.event_bus.publish("widget_z_changed", widget_id, "back")
