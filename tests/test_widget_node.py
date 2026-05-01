from app.core.widget_node import WidgetNode


def _populated_node():
    node = WidgetNode("CTkButton", {"text": "Hi", "fg_color": "#abc"})
    node.name = "ok_button"
    node.visible = False
    node.locked = True
    node.parent_slot = "Tab 1"
    node.group_id = "grp-1"
    node.description = "Submits the login form."
    node.handlers = {
        "command": ["on_click", "log_click"],
        "bind:<Enter>": ["highlight"],
    }
    child = WidgetNode("CTkLabel", {"text": "child"})
    child.parent = node
    node.children.append(child)
    return node


def test_to_dict_from_dict_full_round_trip():
    original = _populated_node()

    restored = WidgetNode.from_dict(original.to_dict())

    assert restored.id == original.id
    assert restored.name == original.name
    assert restored.widget_type == original.widget_type
    assert restored.properties == original.properties
    assert restored.visible is False
    assert restored.locked is True
    assert restored.parent_slot == "Tab 1"
    assert restored.group_id == "grp-1"
    assert restored.description == "Submits the login form."
    assert restored.handlers == original.handlers
    assert len(restored.children) == 1
    assert restored.children[0].widget_type == "CTkLabel"
    assert restored.children[0].parent is restored


def test_to_dict_drops_empty_handlers():
    node = WidgetNode("CTkButton")

    data = node.to_dict()

    assert "handlers" not in data


def test_to_dict_drops_empty_handler_lists():
    node = WidgetNode("CTkButton")
    node.handlers = {"command": [], "bind:<Enter>": ["highlight"]}

    data = node.to_dict()

    assert data["handlers"] == {"bind:<Enter>": ["highlight"]}


def test_from_dict_v1_string_handler_wraps_into_list():
    data = {
        "id": "abc",
        "widget_type": "CTkButton",
        "properties": {},
        "handlers": {"command": "on_click"},
    }

    node = WidgetNode.from_dict(data)

    assert node.handlers == {"command": ["on_click"]}


def test_from_dict_v2_list_handler_round_trips():
    data = {
        "id": "abc",
        "widget_type": "CTkButton",
        "properties": {},
        "handlers": {"command": ["m1", "m2"]},
    }

    node = WidgetNode.from_dict(data)

    assert node.handlers == {"command": ["m1", "m2"]}


def test_from_dict_mixed_v1_and_v2_handlers_normalised():
    data = {
        "id": "abc",
        "widget_type": "CTkButton",
        "properties": {},
        "handlers": {
            "command": "legacy_method",
            "bind:<Return>": ["new_a", "new_b"],
        },
    }

    node = WidgetNode.from_dict(data)

    assert node.handlers == {
        "command": ["legacy_method"],
        "bind:<Return>": ["new_a", "new_b"],
    }


def test_from_dict_drops_empty_string_v1_handler():
    data = {
        "id": "abc",
        "widget_type": "CTkButton",
        "properties": {},
        "handlers": {"command": ""},
    }

    node = WidgetNode.from_dict(data)

    assert node.handlers == {}


def test_from_dict_filters_non_string_list_entries():
    data = {
        "id": "abc",
        "widget_type": "CTkButton",
        "properties": {},
        "handlers": {"command": ["good", "", None, 123, "also_good"]},
    }

    node = WidgetNode.from_dict(data)

    assert node.handlers == {"command": ["good", "also_good"]}


def test_from_dict_renames_legacy_widget_types():
    data = {
        "id": "abc",
        "widget_type": "Shape",
        "properties": {},
    }

    node = WidgetNode.from_dict(data)

    assert node.widget_type == "Card"


def test_to_dict_properties_is_independent_copy():
    node = WidgetNode("CTkButton", {"text": "Hi"})

    data = node.to_dict()
    data["properties"]["text"] = "Mutated"

    assert node.properties["text"] == "Hi"
